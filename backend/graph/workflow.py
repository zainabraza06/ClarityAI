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


def create_workflow(tools: list):
    """
    Build and compile the LangGraph multi-agent workflow.

    Topology:
        START → clarity → research → [validator ↔ research (retry)] → synthesis → END

    The clarity node uses interrupt() to pause when a query is ambiguous.
    MemorySaver checkpointer enables both interrupt/resume and multi-turn memory.
    """
    research_node = create_research_node(tools)

    builder = StateGraph(AgentState)

    builder.add_node("clarity", clarity_node)
    builder.add_node("research", research_node)
    builder.add_node("validator", validator_node)
    builder.add_node("synthesis", synthesis_node)

    # Entry point always goes to clarity first
    builder.add_edge(START, "clarity")

    # Clarity always proceeds to research after resolving (interrupt handles the pause transparently)
    builder.add_edge("clarity", "research")

    # Research routes based on confidence score
    builder.add_conditional_edges(
        "research",
        _route_after_research,
        {"synthesis": "synthesis", "validator": "validator"},
    )

    # Validator loops back to research or advances to synthesis
    builder.add_conditional_edges(
        "validator",
        _route_after_validator,
        {"synthesis": "synthesis", "research": "research"},
    )

    builder.add_edge("synthesis", END)

    # MemorySaver checkpointer is required for interrupt() and multi-turn thread memory
    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)
