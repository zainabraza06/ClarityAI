import re
from typing import List
from pydantic import BaseModel
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage

from llm.provider import create_structured_llm, create_tool_llm


class ResearchOutput(BaseModel):
    research_findings: str
    confidence_score: int  # 0-10


RESEARCH_SYSTEM_PROMPT = """You are the Research Agent for ClarityAI. Gather business intelligence using the search tool.

IMPORTANT: You MUST call the search tool at least once. Never answer from memory alone — always search first.

Search Strategy:
- For a single company: run 2-3 searches covering (1) company overview and background, (2) recent news and developments (last 6 months), (3) market position and competitors
- For comparison queries (e.g. "Tesla vs Rivian"): run a dedicated search for each company
- Maximum 3 search rounds total

After searching, write a comprehensive research summary (max 1000 words) covering all gathered information.
If real-time financial data or document context is provided above, incorporate it into your summary.
When content is labeled [Uploaded: filename], explicitly reference it as 'Per the uploaded document [filename]:' in your summary."""


ANALYSIS_SYSTEM_PROMPT = """You are a business intelligence analyst. Evaluate the research gathered and produce a structured summary.

Assign an honest confidence score (0-10):
- 9-10: Rich, comprehensive data with recent news, financials, and strategic context
- 7-8: Good coverage across most dimensions, minor gaps
- 5-6: Adequate for basic research, some key areas missing
- 3-4: Sparse -- only general or partial information found
- 0-2: Very little useful data; mostly generic or no company-specific info

The confidence score determines whether the research proceeds to synthesis or triggers validation.
Be accurate -- a false high score skips quality checks."""

MAX_TOOL_RESULT_CHARS = 3000

_URL_RE = re.compile(r'https?://[^\s\'"<>\]\)]+')
_VALID_TIME_RANGES = {"day", "week", "month", "year"}


def _extract_urls(text: str) -> List[str]:
    # Normalize literal \n / \t escape sequences to real whitespace so the
    # URL regex stops at them rather than including them in the URL
    normalized = text.replace("\\n", "\n").replace("\\t", "\t")
    urls = []
    seen: set = set()
    for raw in _URL_RE.findall(normalized):
        url = raw.rstrip(".,;)")
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _content_str(content) -> str:
    """Normalize LLM response content — langchain-core 1.x can return a list of parts."""
    if isinstance(content, list):
        return " ".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content) if content else ""


def _sanitize_tool_args(tool_name: str, args: dict) -> dict:
    """Strip invalid time_range values -- Groq/Gemini reject anything outside the enum."""
    if "time_range" in args and args["time_range"] not in _VALID_TIME_RANGES:
        return {k: v for k, v in args.items() if k != "time_range"}
    return args


# Module-level import attempt for document store -- fails gracefully if unavailable
try:
    from documents.store import search_chunks as _search_chunks
    _DOCS_AVAILABLE = True
except ImportError:
    _DOCS_AVAILABLE = False


def create_research_node(tools: list):
    """Factory that captures MCP tools and financial tool in a closure."""
    tools_by_name = {tool.name: tool for tool in tools}
    # The LLM tool loop uses only search tools; financial data is fetched proactively
    search_tools = [t for t in tools if t.name != "get_financial_data"]

    async def research_node(state: dict) -> dict:
        query = state.get("clarified_query") or state.get("user_query", "")
        messages_history = state.get("messages", [])

        history_lines = []
        for m in messages_history[-4:]:
            role = "User" if isinstance(m, HumanMessage) else "Assistant"
            history_lines.append(f"{role}: {_content_str(m.content)[:150]}")
        history = "\n".join(history_lines) if history_lines else "No prior conversation."

        # 1. Proactively fetch real-time financial data
        financial_context = ""
        fin_tool = tools_by_name.get("get_financial_data")
        if fin_tool:
            try:
                fin_result = await fin_tool.ainvoke({"company_or_ticker": query})
                if (
                    fin_result
                    and "not installed" not in fin_result
                    and "No public financial" not in fin_result
                    and "temporarily unavailable" not in fin_result
                    and len(fin_result.strip()) > 40
                ):
                    financial_context = f"\n\n## Real-Time Financial Data\n{fin_result}"
            except Exception:
                pass

        # 2. Search uploaded documents — only when the query explicitly asks for them
        _DOC_TRIGGERS = {"document", "documents", "uploaded", "upload", "file", "files", "pdf", "attachment"}
        query_asks_for_docs = any(t in query.lower() for t in _DOC_TRIGGERS)

        doc_context = ""
        doc_filenames: List[str] = []
        if _DOCS_AVAILABLE and query_asks_for_docs:
            try:
                chunks = await _search_chunks(query)
                if chunks:
                    # Trust the search results directly — _search_chunks already
                    # ranks by relevance to the query via FTS/vector similarity.
                    relevant = chunks
                    if relevant:
                        doc_context = (
                            "\n\n## Context from Uploaded Documents\n"
                            "IMPORTANT: Content below is from the user's uploaded files. "
                            "When referencing it, explicitly say 'Per the uploaded document [filename]:'\n"
                        )
                        for c in relevant:
                            doc_context += f"\n[Uploaded: {c['filename']}]:\n{c['content'][:600]}\n"
                            if c["filename"] not in doc_filenames:
                                doc_filenames.append(c["filename"])
            except Exception:
                pass

        # 3. Web search tool-calling loop (ReAct pattern)
        research_messages = [
            SystemMessage(content=RESEARCH_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Research query: {query}\n\n"
                    f"Conversation context:\n{history}"
                    f"{financial_context}"
                    f"{doc_context}"
                )
            ),
        ]

        llm_with_tools = create_tool_llm(search_tools, temperature=0.1)
        response = await llm_with_tools.ainvoke(research_messages)

        all_tool_results: List[str] = []
        iterations = 0
        while response.tool_calls and iterations < 3:
            research_messages.append(response)
            for tc in response.tool_calls:
                tool_name = tc["name"]
                if tool_name in tools_by_name:
                    try:
                        safe_args = _sanitize_tool_args(tool_name, tc["args"])
                        result = await tools_by_name[tool_name].ainvoke(safe_args)
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

        raw_findings = (_content_str(response.content) or "No research data retrieved.")[:4000]

        # 4. Collect source URLs
        seen: set = set()
        sources: List[str] = []
        for content in all_tool_results:
            for url in _extract_urls(content):
                if url not in seen and len(sources) < 10:
                    seen.add(url)
                    sources.append(url)

        # Prepend document and financial context so the analysis LLM always sees them
        if doc_context:
            raw_findings = doc_context.strip() + "\n\n" + raw_findings
        if financial_context:
            raw_findings = financial_context.strip() + "\n\n" + raw_findings

        # 5. Structured analysis + confidence scoring
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
            "document_sources": doc_filenames if doc_filenames else None,
            "document_query": query_asks_for_docs,
        }

    return research_node
