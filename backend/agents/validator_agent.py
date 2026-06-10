from typing import List, Literal
from pydantic import BaseModel
from langchain_core.messages import SystemMessage, HumanMessage

from llm.provider import create_structured_llm


class ValidationOutput(BaseModel):
    validation_result: Literal["sufficient", "insufficient"]
    reasoning: str
    missing_aspects: List[str] = []


VALIDATOR_SYSTEM_PROMPT = """You are the Validator Agent for ClarityAI. Assess research quality.

Evaluate the provided research findings against the user's query.

Research is SUFFICIENT when:
- The main query is meaningfully addressed
- Key company information is present (at minimum: overview + one of: news, financials, or strategic context)
- The response would provide genuine value to the user

Research is INSUFFICIENT when:
- The query is completely unanswered
- The findings are placeholder text or clearly fabricated
- Critical company-specific information is entirely absent

Be lenient — prefer "sufficient" when findings have reasonable content, even if imperfect.
Only mark "insufficient" when the research is genuinely too sparse to be useful.
This avoids unnecessary retry loops."""


async def validator_node(state: dict) -> dict:
    llm = create_structured_llm(ValidationOutput)

    query = state.get("clarified_query") or state.get("user_query", "")
    findings = state.get("research_findings", "")
    confidence = state.get("confidence_score", 0)
    attempts = state.get("attempts", 0)

    prompt = f"""User query: {query}

Research findings (confidence score: {confidence}/10):
{findings}

Research attempt number: {attempts}

Evaluate whether this research is sufficient to generate a useful response."""

    result: ValidationOutput = await llm.ainvoke([
        SystemMessage(content=VALIDATOR_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])

    return {
        "validation_result": result.validation_result,
    }
