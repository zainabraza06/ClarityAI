from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from llm.provider import create_llm

# ── Template system prompts ────────────────────────────────────────────────────

_STANDARD_PROMPT = """You are the Synthesis Agent for ClarityAI, a business intelligence analyst.

Transform raw research findings into a clear, professional business intelligence report.

Format your response in clean Markdown with these sections (include only sections with meaningful content):

## Company Overview
Brief description, founding, headquarters, industry, and business model.

## Recent Developments
Latest news, product launches, partnerships, acquisitions, or strategic moves.

## Financial Insights
Revenue, growth metrics, funding rounds, or market performance (where available).

## Risks & Opportunities
Key challenges and growth opportunities based on the research.

## Key Takeaways
3-5 bullet points summarising the most important findings.

Guidelines:
- Write a thorough report — minimum 500 words total
- Each section must contain at least 3-4 sentences or bullet points
- Be specific and factual — cite actual figures, names, and dates from the research
- Only omit a section if there is genuinely zero data for it; use partial data rather than skip
- Use professional business language
- Maintain context from the conversation history for follow-up questions"""

_INVESTOR_MEMO_PROMPT = """You are the Synthesis Agent for ClarityAI, acting as a senior investment analyst.

Transform the research findings into a professional INVESTOR MEMO.

Format in clean Markdown:

## Executive Summary
One-paragraph overview of the investment opportunity.

## Company Overview
Business model, founding story, and core value proposition.

## Investment Thesis
Why this company is noteworthy from an investment perspective.

## Financial Highlights
Revenue, growth, funding rounds, valuation, and key metrics.

## Market Opportunity
Total addressable market, growth trends, and competitive dynamics.

## Key Risks
3-5 specific risks that could impair the investment case.

## Management & Strategy
Leadership quality and strategic direction.

## Conclusion
Overall assessment and key watchpoints.

Guidelines:
- Write a thorough memo — minimum 500 words total
- Each section must have at least 3-4 sentences; use partial data rather than skip a section
- Use precise financial language; cite actual numbers when available
- Maintain context from conversation history"""

_COMPETITOR_ANALYSIS_PROMPT = """You are the Synthesis Agent for ClarityAI, acting as a strategic analyst.

Transform the research findings into a COMPETITIVE ANALYSIS REPORT.

Format in clean Markdown:

## Company Overview
Brief description of the subject company.

## Competitive Landscape
Overview of the competitive environment and industry dynamics.

## Key Competitors
For each major competitor: brief profile, market position, and differentiation.

## Competitive Advantages
Sustainable moats and differentiators that set this company apart.

## Competitive Weaknesses
Gaps, vulnerabilities, and areas where competitors have an edge.

## Market Position
Current market share, trends, and positioning trajectory.

## Strategic Opportunities & Threats
Growth opportunities and competitive threats on the horizon.

## Competitive Verdict
Overall competitive standing and outlook.

Guidelines:
- Write a thorough analysis — minimum 500 words total
- Each section must have at least 3-4 sentences or bullet points
- Be specific about which competitors and why they matter
- Focus on strategic dynamics, not just basic descriptions
- Use partial data rather than skip a section"""

_SWOT_PROMPT = """You are the Synthesis Agent for ClarityAI, acting as a strategic business analyst.

Transform the research findings into a clear SWOT ANALYSIS.

Format in clean Markdown:

## Company Overview
One-paragraph context.

## Strengths
Internal advantages — what the company does exceptionally well.

## Weaknesses
Internal challenges — structural limits or underperformance areas.

## Opportunities
External factors the company can exploit to grow.

## Threats
External risks that could harm the company's position.

## Strategic Summary
2-3 sentences synthesising the most critical insight from the SWOT.

Guidelines:
- Write a thorough SWOT — minimum 450 words total
- Each section must have 3-6 concrete, well-reasoned bullet points
- Avoid generic observations — base every point on the research findings
- Use partial data rather than skip a section"""

_COMPARISON_PROMPT = """You are the Synthesis Agent for ClarityAI, acting as a comparative business analyst.

Transform the research findings into a structured COMPANY COMPARISON REPORT.
Identify the two companies being compared from the query and research findings.

Format in clean Markdown:

## Overview
Brief introduction of both companies and why the comparison is relevant.

## At a Glance

| Aspect | [Company A] | [Company B] |
|--------|-------------|-------------|
| Founded | ... | ... |
| Headquarters | ... | ... |
| Business Model | ... | ... |
| Key Products/Services | ... | ... |
| Revenue / Funding | ... | ... |

## Recent Developments
Key recent news and strategic moves for each company.

## Financial Comparison
Revenue, growth, valuation, and key financial metrics side-by-side.

## Competitive Positioning
How each company positions itself in the market.

## Strengths & Weaknesses
For each company, key advantages and disadvantages.

## Key Differences
The 3-5 most important ways these companies differ.

## Verdict
Which company appears stronger overall and why — or where each excels in different dimensions.

Guidelines:
- Write a thorough comparison — minimum 500 words total
- Each section must have at least 3-4 sentences; use partial data rather than skip a section
- Replace [Company A] and [Company B] with the actual company names from the query
- Fill table cells with actual data; use "N/A" if unknown
- Be balanced — avoid clear bias toward one company
- Base all claims on the research findings"""

_TEMPLATES: dict[str, str] = {
    "standard": _STANDARD_PROMPT,
    "investor_memo": _INVESTOR_MEMO_PROMPT,
    "competitor_analysis": _COMPETITOR_ANALYSIS_PROMPT,
    "swot": _SWOT_PROMPT,
    "comparison": _COMPARISON_PROMPT,
}


async def synthesis_node(state: dict) -> dict:
    llm = create_llm(temperature=0)

    template = state.get("template") or "standard"
    system_prompt = _TEMPLATES.get(template, _STANDARD_PROMPT)

    query = state.get("clarified_query") or state.get("user_query", "")
    findings = state.get("research_findings", "No research findings available.")
    confidence = state.get("confidence_score", 0)
    sources = state.get("sources") or []
    doc_sources = state.get("document_sources") or []
    messages = state.get("messages", [])

    history_lines = []
    for m in messages[-6:]:
        role = "User" if isinstance(m, HumanMessage) else "Assistant"
        content = m.content if isinstance(m.content, str) else " ".join(
            p.get("text", "") if isinstance(p, dict) else str(p) for p in m.content
        )
        history_lines.append(f"{role}: {content[:500]}")
    history = "\n".join(history_lines) if history_lines else "No prior conversation."

    doc_instruction = ""
    if doc_sources:
        names = ", ".join(doc_sources)
        doc_instruction = (
            f"\n\nUploaded documents used in this research: {names}\n"
            "IMPORTANT: Add a '## From Uploaded Documents' section BEFORE the Key Takeaways "
            "that explicitly quotes or summarises findings drawn from those uploaded files. "
            "Clearly distinguish document-sourced content from web-sourced content."
        )

    prompt = f"""Conversation history:
{history}

Current query: {query}

Research findings (confidence: {confidence}/10):
{findings}{doc_instruction}

Generate a report based on these findings using the specified format."""

    response = await llm.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=prompt),
    ])

    final_response = response.content

    # Build combined sources section — documents first, then web URLs
    source_parts = []
    if doc_sources:
        source_parts.append("**Uploaded Documents**")
        for name in doc_sources:
            source_parts.append(f"- {name}")
    if sources:
        if doc_sources:
            source_parts.append("\n**Web Sources**")
        for url in sources[:8]:
            source_parts.append(f"- {url}")

    if source_parts:
        final_response = f"{final_response}\n\n## Sources\n" + "\n".join(source_parts)

    return {
        "final_response": final_response,
        "messages": [AIMessage(content=final_response)],
    }
