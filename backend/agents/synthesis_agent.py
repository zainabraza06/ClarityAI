from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from llm.provider import create_llm


SYNTHESIS_SYSTEM_PROMPT = """You are the Synthesis Agent for ClarityAI, a business intelligence analyst.

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
- Be specific and factual — no vague filler content
- If a section has no data, omit it
- Use professional business language
- Maintain context from the conversation history for follow-up questions"""


async def synthesis_node(state: dict) -> dict:
    llm = create_llm(temperature=0)

    query = state.get("clarified_query") or state.get("user_query", "")
    findings = state.get("research_findings", "No research findings available.")
    confidence = state.get("confidence_score", 0)
    messages = state.get("messages", [])

    history_lines = []
    for m in messages[-6:]:
        role = "User" if isinstance(m, HumanMessage) else "Assistant"
        history_lines.append(f"{role}: {m.content[:500]}")
    history = "\n".join(history_lines) if history_lines else "No prior conversation."

    prompt = f"""Conversation history:
{history}

Current query: {query}

Research findings (confidence: {confidence}/10):
{findings}

Generate a comprehensive business intelligence report based on these findings."""

    response = await llm.ainvoke([
        SystemMessage(content=SYNTHESIS_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])

    final_response = response.content

    return {
        "final_response": final_response,
        "messages": [AIMessage(content=final_response)],
    }
