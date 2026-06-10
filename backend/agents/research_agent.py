from typing import List
from pydantic import BaseModel
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage

from llm.provider import create_structured_llm, create_tool_llm


class ResearchOutput(BaseModel):
    research_findings: str
    confidence_score: int  # 0-10


RESEARCH_SYSTEM_PROMPT = """You are the Research Agent for ClarityAI. Gather business intelligence using the search tool.

Search for: company overview, recent news, financial highlights, key products, and strategic developments.
Run 1-2 targeted searches. After searching, write a concise research summary (max 800 words)."""

ANALYSIS_SYSTEM_PROMPT = """You are a business intelligence analyst. Evaluate the research gathered and produce a structured summary.

Assign an honest confidence score (0-10):
- 9-10: Rich, comprehensive data with recent news, financials, and strategic context
- 7-8: Good coverage across most dimensions, minor gaps
- 5-6: Adequate for basic research, some key areas missing
- 3-4: Sparse — only general or partial information found
- 0-2: Very little useful data; mostly generic or no company-specific info

The confidence score determines whether the research proceeds to synthesis or triggers validation.
Be accurate — a false high score skips quality checks."""

# Groq free tier: ~12,000 TPM. Cap tool results to stay within budget.
MAX_TOOL_RESULT_CHARS = 3000


def create_research_node(tools: list):
    """Factory that captures MCP tools in a closure and returns an async LangGraph node."""
    tools_by_name = {tool.name: tool for tool in tools}

    async def research_node(state: dict) -> dict:
        query = state.get("clarified_query") or state.get("user_query", "")
        messages_history = state.get("messages", [])

        # Last 2 turns only — keeps context short and avoids TPM limits
        history_lines = []
        for m in messages_history[-4:]:
            role = "User" if isinstance(m, HumanMessage) else "Assistant"
            history_lines.append(f"{role}: {m.content[:150]}")
        history = "\n".join(history_lines) if history_lines else "No prior conversation."

        # ── Tool-calling loop (ReAct pattern) ─────────────────────────────
        research_messages = [
            SystemMessage(content=RESEARCH_SYSTEM_PROMPT),
            HumanMessage(
                content=f"Research query: {query}\n\nConversation context:\n{history}"
            ),
        ]

        llm_with_tools = create_tool_llm(tools, temperature=0.1)
        response = await llm_with_tools.ainvoke(research_messages)

        iterations = 0
        while response.tool_calls and iterations < 2:  # max 2 search rounds
            research_messages.append(response)
            for tc in response.tool_calls:
                tool_name = tc["name"]
                if tool_name in tools_by_name:
                    try:
                        result = await tools_by_name[tool_name].ainvoke(tc["args"])
                        # Truncate to stay within provider TPM limits
                        content = str(result)[:MAX_TOOL_RESULT_CHARS]
                        research_messages.append(
                            ToolMessage(content=content, tool_call_id=tc["id"])
                        )
                    except Exception as exc:
                        research_messages.append(
                            ToolMessage(
                                content=f"Search error: {exc}",
                                tool_call_id=tc["id"],
                            )
                        )
            response = await llm_with_tools.ainvoke(research_messages)
            iterations += 1

        raw_findings = (response.content or "No research data retrieved.")[:4000]

        # ── Structured analysis + confidence scoring ───────────────────────
        analysis_llm = create_structured_llm(ResearchOutput, temperature=0)
        analysis: ResearchOutput = await analysis_llm.ainvoke([
            SystemMessage(content=ANALYSIS_SYSTEM_PROMPT),
            HumanMessage(
                content=f"Query: {query}\n\nGathered research:\n{raw_findings}"
            ),
        ])

        return {
            "research_findings": analysis.research_findings,
            "confidence_score": max(0, min(10, analysis.confidence_score)),
            "attempts": state.get("attempts", 0) + 1,
        }

    return research_node
