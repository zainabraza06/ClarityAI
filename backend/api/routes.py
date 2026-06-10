import json
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from pydantic import BaseModel

from . import app_state

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


def _extract_interrupt_question(graph_state) -> str:
    default = "Could you please clarify your query?"
    for task in graph_state.tasks:
        for intr in task.interrupts:
            if isinstance(intr.value, dict) and "question" in intr.value:
                return intr.value["question"]
    return default


def _build_initial_state(message: str, template: str = "standard") -> dict:
    """Fresh state for a new query (or follow-up on a completed thread)."""
    return {
        "messages": [HumanMessage(content=message)],
        "user_query": message,
        "attempts": 0,
        "clarity_status": None,
        "clarified_query": None,
        "research_findings": None,
        "confidence_score": None,
        "validation_result": None,
        "final_response": None,
        "template": template,
        "sources": None,
    }


# ---------- Endpoints ----------


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint.

    - New thread: starts a fresh graph invocation.
    - Existing completed thread: starts a new invocation on the same thread (history preserved).
    - Interrupted thread: resumes the paused graph with the user's clarification.
    """
    graph = _get_graph()
    thread_id = request.thread_id or str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    try:
        current_state = graph.get_state(config)

        if current_state.next:
            result = await graph.ainvoke(Command(resume=request.message), config)
        else:
            result = await graph.ainvoke(
                _build_initial_state(request.message, request.template or "standard"),
                config,
            )

        new_state = graph.get_state(config)
        if new_state.next:
            return ChatResponse(
                status="needs_clarification",
                question=_extract_interrupt_question(new_state),
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
    """
    Streaming chat endpoint using Server-Sent Events.

    Emits agent lifecycle events so the frontend can render a live activity timeline.

    Event types:
      { type: "agent_start", agent: "Research Agent", thread_id: "..." }
      { type: "agent_end",   agent: "Research Agent", output: {...} }
      { type: "needs_clarification", question: "...", thread_id: "..." }
      { type: "final", response: "...", confidence_score: 8, sources: [...], thread_id: "..." }
      { type: "error", message: "..." }
      data: [DONE]
    """
    graph = _get_graph()
    thread_id = request.thread_id or str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    current_state = graph.get_state(config)
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
            yield _sse({"type": "error", "message": str(exc)})

        # Determine final outcome after the stream completes
        final_state = graph.get_state(config)

        if final_state.next:
            yield _sse(
                {
                    "type": "needs_clarification",
                    "question": _extract_interrupt_question(final_state),
                    "thread_id": thread_id,
                }
            )
        else:
            vals = final_state.values
            yield _sse(
                {
                    "type": "final",
                    "response": vals.get("final_response", ""),
                    "confidence_score": vals.get("confidence_score"),
                    "sources": vals.get("sources") or [],
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
