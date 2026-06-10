from typing import Annotated, List, Optional
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
from typing_extensions import TypedDict


class AgentState(TypedDict):
    # add_messages reducer appends instead of overwriting — required for multi-turn memory
    messages: Annotated[List[BaseMessage], add_messages]
    user_query: str
    clarified_query: Optional[str]
    clarity_status: Optional[str]
    research_findings: Optional[str]
    confidence_score: Optional[int]
    validation_result: Optional[str]
    attempts: int
    final_response: Optional[str]
    template: Optional[str]   # standard | investor_memo | competitor_analysis | swot | comparison
    sources: Optional[List[str]]  # source URLs collected during research
