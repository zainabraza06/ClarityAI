from typing import Literal, Optional
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.types import interrupt

from llm.provider import create_structured_llm


class ClarityOutput(BaseModel):
    clarity_status: Literal["clear", "needs_clarification"]
    clarification_question: Optional[str] = None


CLARITY_SYSTEM_PROMPT = """You are the Clarity Agent for ClarityAI, a business research assistant.

Evaluate whether the user's query is specific enough for business research.

A query is CLEAR when:
- A specific company name is provided (e.g., "Tesla", "OpenAI", "Apple Inc.", "NVIDIA")
- The research intent is understandable
- Enough context exists to proceed with research

A query NEEDS_CLARIFICATION when:
- No company name is provided at all
- The company name is genuinely ambiguous (e.g., "Apple" without context could mean Apple Inc. or Apple Corps)
- The query is too vague to research meaningfully (e.g., "tell me about tech companies")

IMPORTANT: Check the conversation history first. If a company was mentioned earlier in the conversation,
a follow-up like "What about their competitors?" is CLEAR — the company is already established.

If clarification is needed, write a concise, specific question to ask the user."""


async def clarity_node(state: dict) -> dict:
    llm = create_structured_llm(ClarityOutput)

    messages = state.get("messages", [])
    user_query = state.get("user_query", "")

    history_lines = []
    for m in messages[:-1]:
        role = "User" if isinstance(m, HumanMessage) else "Assistant"
        history_lines.append(f"{role}: {m.content}")
    history = "\n".join(history_lines) if history_lines else "No prior conversation."

    prompt = f"""Conversation history:
{history}

Current query to evaluate: {user_query}

Is this query clear enough for business research?"""

    result: ClarityOutput = await llm.ainvoke([
        SystemMessage(content=CLARITY_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])

    if result.clarity_status == "needs_clarification":
        question = result.clarification_question or "Which company are you asking about?"

        # Pause the graph — resumes when the user provides clarification
        clarification: str = interrupt({"question": question})

        return {
            "messages": [
                AIMessage(content=question),
                HumanMessage(content=clarification),
            ],
            "clarity_status": "clear",
            "clarified_query": clarification,
            "user_query": clarification,
        }

    return {
        "clarity_status": "clear",
        "clarified_query": user_query,
    }
