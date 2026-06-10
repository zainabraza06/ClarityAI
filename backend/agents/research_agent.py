import re
from typing import List
from pydantic import BaseModel
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage

from llm.provider import create_structured_llm, create_tool_llm


class ResearchOutput(BaseModel):
    research_findings: str
    confidence_score: int  # 0-10


RESEARCH_SYSTEM_PROMPT = """You are the Research Agent for ClarityAI. Gather business intelligence using the search tool.

Search Strategy:
- For a single company: run 2-3 searches covering (1) company overview and background, (2) recent news and developments (last 6 months), (3) financial highlights and market position
- For comparison queries (e.g. "Tesla vs Rivian", "Compare Apple vs Microsoft"): run a dedicated search for each company
- Maximum 3 search rounds total

After searching, write a comprehensive research summary (max 1000 words) covering all gathered information."""


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

_URL_RE = re.compile(r'https?://[^\s\'"<>\]\)]+')


def _extract_urls(text: str) -> List[str]:
    return [u.rstrip(".,;)") for u in _URL_RE.findall(text)]


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

        all_tool_results: List[str] = []
        iterations = 0
        while response.tool_calls and iterations < 3:  # max 3 search rounds
            research_messages.append(response)
            for tc in response.tool_calls:
                tool_name = tc["name"]
                if tool_name in tools_by_name:
                    try:
                        result = await tools_by_name[tool_name].ainvoke(tc["args"])
                        content = str(result)[:MAX_TOOL_RESULT_CHARS]
                        all_tool_results.append(content)
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

        # ── Collect source URLs from tool results ──────────────────────────
        seen: set = set()
        sources: List[str] = []
        for content in all_tool_results:
            for url in _extract_urls(content):
                if url not in seen and len(sources) < 10:
                    seen.add(url)
                    sources.append(url)

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
            "sources": sources,
        }

    return research_node
