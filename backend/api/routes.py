import json
import logging
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from pydantic import BaseModel

from . import app_state

logger = logging.getLogger("clarityai.routes")

router = APIRouter(prefix="/api")

AGENT_DISPLAY_NAMES = {
    "clarity": "Clarity Agent",
    "research": "Research Agent",
    "validator": "Validator Agent",
    "synthesis": "Synthesis Agent",
}


# ---------- Request / Response models ----------


class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None
    template: Optional[str] = "standard"


class ChatResponse(BaseModel):
    status: str  # "success" | "needs_clarification" | "error"
    response: Optional[str] = None
    question: Optional[str] = None
    thread_id: str
    confidence_score: Optional[int] = None
    sources: Optional[list] = None


# ---------- Helpers ----------


def _get_graph():
    graph = app_state.get("graph")
    if graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialised")
    return graph


def _build_initial_state(message: str, template: str = "standard") -> dict:
    """Fresh state for a new query (or follow-up on a completed thread)."""
    return {
        "messages": [HumanMessage(content=message)],
        "user_query": message,
        "attempts": 0,
        "clarity_status": None,
        "clarification_question": None,
        "clarified_query": None,
        "research_findings": None,
        "confidence_score": None,
        "validation_result": None,
        "final_response": None,
        "template": template,
        "sources": None,
        "document_sources": None,
        "document_query": False,
    }


def _is_awaiting_clarification(state_values: dict) -> bool:
    return state_values.get("clarity_status") == "needs_clarification"


def _get_clarification_question(state_values: dict) -> str:
    return (
        state_values.get("clarification_question")
        or "Could you please clarify your query?"
    )


# ---------- Endpoints ----------


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    graph = _get_graph()
    thread_id = request.thread_id or str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    try:
        current_state = await graph.aget_state(config)
        prev_values = current_state.values if current_state else {}

        # Resume an interrupt-paused graph (legacy path) or treat clarification
        # as a fresh run with the clarified query as the new message.
        if current_state.next:
            result = await graph.ainvoke(Command(resume=request.message), config)
        else:
            result = await graph.ainvoke(
                _build_initial_state(request.message, request.template or "standard"),
                config,
            )

        new_state = await graph.aget_state(config)
        new_vals = new_state.values if new_state else {}

        # State-based clarification detection (no interrupt() needed)
        if _is_awaiting_clarification(new_vals):
            return ChatResponse(
                status="needs_clarification",
                question=_get_clarification_question(new_vals),
                thread_id=thread_id,
            )

        # Legacy interrupt detection
        if new_state.next:
            return ChatResponse(
                status="needs_clarification",
                question=_get_clarification_question(new_vals),
                thread_id=thread_id,
            )

        return ChatResponse(
            status="success",
            response=result.get("final_response", ""),
            confidence_score=result.get("confidence_score"),
            sources=result.get("sources") or [],
            thread_id=thread_id,
        )

    except Exception as exc:
        err_str = str(exc)
        if "429" in err_str or "rate" in err_str.lower():
            raise HTTPException(
                status_code=429,
                detail="All LLM providers are rate-limited. Please wait a moment and retry.",
            )
        raise HTTPException(status_code=500, detail=err_str)


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    graph = _get_graph()
    thread_id = request.thread_id or str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    current_state = await graph.aget_state(config)
    stream_input = (
        Command(resume=request.message)
        if current_state.next
        else _build_initial_state(request.message, request.template or "standard")
    )

    async def generate():
        try:
            async for event in graph.astream_events(
                stream_input, config, version="v2"
            ):
                event_type = event.get("event", "")
                node_name = event.get("name", "")

                if event_type == "on_chain_start" and node_name in AGENT_DISPLAY_NAMES:
                    yield _sse(
                        {
                            "type": "agent_start",
                            "agent": AGENT_DISPLAY_NAMES[node_name],
                            "thread_id": thread_id,
                        }
                    )

                elif event_type == "on_chain_end" and node_name in AGENT_DISPLAY_NAMES:
                    raw_output = event.get("data", {}).get("output") or {}
                    safe_output = {
                        k: raw_output[k]
                        for k in ("clarity_status", "confidence_score", "validation_result")
                        if k in raw_output
                    }
                    yield _sse(
                        {
                            "type": "agent_end",
                            "agent": AGENT_DISPLAY_NAMES[node_name],
                            "output": safe_output,
                        }
                    )

        except Exception as exc:
            logger.error("SSE stream error: %s", exc, exc_info=True)
            # Suppress LangGraph interrupt-related config errors — final_state handles them
            if "get_config" not in str(exc) and "runnable context" not in str(exc):
                yield _sse({"type": "error", "message": str(exc)})

        # Determine final outcome after the stream completes
        final_state = await graph.aget_state(config)
        final_vals = final_state.values if final_state else {}

        # State-based clarification (preferred path — no interrupt() required)
        if _is_awaiting_clarification(final_vals):
            yield _sse(
                {
                    "type": "needs_clarification",
                    "question": _get_clarification_question(final_vals),
                    "thread_id": thread_id,
                }
            )
        # Legacy interrupt-based clarification
        elif final_state.next:
            yield _sse(
                {
                    "type": "needs_clarification",
                    "question": _get_clarification_question(final_vals),
                    "thread_id": thread_id,
                }
            )
        else:
            yield _sse(
                {
                    "type": "final",
                    "response": final_vals.get("final_response", ""),
                    "confidence_score": final_vals.get("confidence_score"),
                    "sources": final_vals.get("sources") or [],
                    "thread_id": thread_id,
                }
            )

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/health")
async def health():
    from llm.provider import get_provider_names

    graph = app_state.get("graph")
    tools = app_state.get("tools", [])
    tool_names = [t.name for t in tools]
    return {
        "status": "ok" if graph else "initialising",
        "tools_loaded": bool(tool_names),
        "tools": tool_names,
        "llm_providers": get_provider_names(),
    }


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"
