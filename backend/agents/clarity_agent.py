import re
from typing import Literal, Optional
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, SystemMessage

from llm.provider import create_structured_llm
from documents.store import (
    asks_for_all_documents,
    is_document_query,
    list_documents,
    names_a_document,
)


class ClarityOutput(BaseModel):
    clarity_status: Literal["clear", "needs_clarification"]
    clarification_question: Optional[str] = None


CLARITY_SYSTEM_PROMPT = """You are the Clarity Agent for ClarityAI, a business research assistant.

Evaluate whether the user's query is specific enough for business research.

A query is CLEAR when:
- A specific company name is provided (e.g., "Tesla", "OpenAI", "Apple Inc.", "NVIDIA")
- The research intent is understandable
- Enough context exists to proceed with research
- The user is asking about an uploaded document, file, PDF, or attachment
  (the document itself is the context — do not ask for Apple, Tesla, or another public company)
- Several files are uploaded but the user names one of them, or asks about all of them

A query NEEDS_CLARIFICATION when:
- No company name is provided AND the query is not about uploaded documents
- The company name is genuinely ambiguous (e.g., "Apple" without context could mean Apple Inc. or Apple Corps)
- The query is too vague to research meaningfully (e.g., "tell me about tech companies")
- Two or more documents are uploaded and the user asks about "the document" without saying which file
  (ask which filename — never ask for Apple or Tesla)

IMPORTANT: Check the conversation history first. If a company was mentioned earlier in the conversation,
a follow-up like "What about their competitors?" is CLEAR — the company is already established.

If clarification is needed, write a concise, specific question to ask the user.

Reserve NEEDS_CLARIFICATION for genuinely ambiguous cases only — NOT when the user
names a well-known company with a clear research intent (e.g. "Research Apple Inc",
"SWOT analysis of Microsoft", "Compare Amazon vs Microsoft")."""


_RESEARCH_INTENT = re.compile(
    r"\b(research|analyze|analysis|compare|swot|investor\s+memo|competitor\s+analysis|financials?|overview)\b",
    re.I,
)
_LEGAL_ENTITY = re.compile(r"\b(inc\.?|corp\.?|corporation|llc|ltd\.?|technologies)\b", re.I)
_COMPARISON = re.compile(r"\bvs\.?\b|\bversus\b", re.I)


_DOC_TRIGGERS = re.compile(
    r"\b(document|documents|uploaded|upload|file|files|pdf|attachment|briefing)\b",
    re.I,
)


def _is_explicit_research_query(query: str) -> bool:
    """Fast-path: skip LLM when the query already names a company and intent."""
    q = query.strip()
    if not q:
        return False
    ql = q.lower()

    if _DOC_TRIGGERS.search(ql):
        return True

    if _LEGAL_ENTITY.search(ql) or _COMPARISON.search(ql):
        return True

    if _RESEARCH_INTENT.search(ql) and len(q.split()) >= 2:
        return True

    if re.search(r"\bwhat\s+has\b.+\b(?:doing|recently|latest)\b", ql):
        return True

    return False


def _last_human_text(messages: list) -> str:
    for m in reversed(messages or []):
        if isinstance(m, HumanMessage):
            content = m.content if isinstance(m.content, str) else " ".join(
                p.get("text", "") if isinstance(p, dict) else str(p) for p in m.content
            )
            if content.strip():
                return content
    return ""


async def clarity_node(state: dict) -> dict:
    user_query = state.get("user_query", "")
    messages = state.get("messages", [])

    filenames: list[str] = []
    try:
        filenames = [d["filename"] for d in await list_documents()]
    except Exception:
        filenames = []

    named_file = names_a_document(user_query, filenames)
    wants_all = asks_for_all_documents(user_query)
    prior = _last_human_text(messages[:-1] if messages else [])

    # Short replies like "harborline" / "the harborline one" after a file picker
    if len(filenames) >= 2 and (named_file or wants_all):
        combined = user_query
        if prior and prior.strip().lower() != user_query.strip().lower():
            combined = f"{prior}\nUser selected document: {user_query}"
        return {
            "clarity_status": "clear",
            "clarified_query": combined,
            "clarification_question": None,
        }

    if is_document_query(user_query) and len(filenames) >= 2:
        listed = ", ".join(f"'{n}'" for n in filenames[:8])
        extra = " (and more)" if len(filenames) > 8 else ""
        return {
            "clarity_status": "needs_clarification",
            "clarification_question": (
                f"You have {len(filenames)} uploaded documents: {listed}{extra}. "
                "Which file should I use (e.g. Harborline), or should I use all of them?"
            ),
            "clarified_query": None,
        }

    if _is_explicit_research_query(user_query):
        return {
            "clarity_status": "clear",
            "clarified_query": user_query,
            "clarification_question": None,
        }

    llm = create_structured_llm(ClarityOutput)

    messages = state.get("messages", [])
    user_query = state.get("user_query", "")

    history_lines = []
    for m in messages[:-1]:
        role = "User" if isinstance(m, HumanMessage) else "Assistant"
        content = m.content if isinstance(m.content, str) else " ".join(
            p.get("text", "") if isinstance(p, dict) else str(p) for p in m.content
        )
        history_lines.append(f"{role}: {content}")
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
        return {
            "clarity_status": "needs_clarification",
            "clarification_question": question,
            "clarified_query": None,
        }

    return {
        "clarity_status": "clear",
        "clarified_query": user_query,
        "clarification_question": None,
    }
