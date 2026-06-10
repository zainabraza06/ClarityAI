from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from .state import AgentState
from agents.clarity_agent import clarity_node
from agents.research_agent import create_research_node
from agents.validator_agent import validator_node
from agents.synthesis_agent import synthesis_node


def _route_after_research(state: AgentState) -> str:
    score = state.get("confidence_score") or 0
    return "synthesis" if score >= 6 else "validator"


def _route_after_validator(state: AgentState) -> str:
    result = state.get("validation_result", "insufficient")
    attempts = state.get("attempts") or 0
    if result == "sufficient" or attempts >= 3:
        return "synthesis"
    return "research"


def create_workflow(tools: list, checkpointer=None):
    """
    Build and compile the LangGraph multi-agent workflow.

    Topology:
        START → clarity → research → [validator ↔ research (retry)] → synthesis → END

    The clarity node uses interrupt() to pause when a query is ambiguous.
    A checkpointer (MemorySaver or AsyncSqliteSaver) enables interrupt/resume
    and multi-turn memory. Pass an external checkpointer for persistent storage;
    defaults to in-memory MemorySaver if none is provided.
    """
    research_node = create_research_node(tools)

    builder = StateGraph(AgentState)

    builder.add_node("clarity", clarity_node)
    builder.add_node("research", research_node)
    builder.add_node("validator", validator_node)
    builder.add_node("synthesis", synthesis_node)

    builder.add_edge(START, "clarity")
    builder.add_edge("clarity", "research")

    builder.add_conditional_edges(
        "research",
        _route_after_research,
        {"synthesis": "synthesis", "validator": "validator"},
    )

    builder.add_conditional_edges(
        "validator",
        _route_after_validator,
        {"synthesis": "synthesis", "research": "research"},
    )

    builder.add_edge("synthesis", END)

    if checkpointer is None:
        checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)
