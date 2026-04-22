"""Graph state definitions and data structures for the Deep Research agent."""

import operator
from typing import Annotated, Optional

from langchain_core.messages import MessageLikeRepresentation
from langgraph.graph import MessagesState
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


###################
# Structured Outputs
###################
class ConductResearch(BaseModel):
    """Call this tool to conduct research on a specific topic."""
    research_topic: str = Field(
        description="The topic to research. Should be a single topic, and should be described in high detail (at least a paragraph).",
    )

class ResearchComplete(BaseModel):
    """Call this tool to indicate that the research is complete."""

class Summary(BaseModel):
    """Research summary with key findings."""
    
    summary: str
    key_excerpts: str

class ClarifyWithUser(BaseModel):
    """Model for user clarification requests."""
    
    need_clarification: bool = Field(
        description="Whether the user needs to be asked a clarifying question.",
    )
    question: str = Field(
        description="A question to ask the user to clarify the report scope",
    )
    verification: str = Field(
        description="Verify message that we will start research after the user has provided the necessary information.",
    )

class ResearchQuestion(BaseModel):
    """Research question and brief for guiding research."""
    
    research_brief: str = Field(
        description="A research question that will be used to guide the research.",
    )


class ResearchDimensions(BaseModel):
    """Required research dimensions extracted from the research brief."""

    dimensions: list[str] = Field(
        description="List of required research dimensions that must be covered before completion.",
    )


class EvidenceItem(BaseModel):
    """Structured evidence record extracted from researcher findings."""

    claim: str = Field(description="A concrete factual claim supported by a source")
    entity: str = Field(description="Named entity associated with the claim")
    date: str = Field(description="Date or date range for the claim, if available")
    metric: str = Field(description="Numeric figure/value for the claim, if available")
    source_url: str = Field(description="Primary source URL for this claim")
    dimension: str = Field(description="Research dimension this claim supports")


###################
# State Definitions
###################

def override_reducer(current_value, new_value):
    """Reducer function that allows overriding values in state."""
    if isinstance(new_value, dict) and new_value.get("type") == "override":
        return new_value.get("value", new_value)
    else:
        return operator.add(current_value, new_value)
    
class AgentInputState(MessagesState):
    """InputState is only 'messages'."""

class AgentState(MessagesState):
    """Main agent state containing messages and research data."""
    
    supervisor_messages: Annotated[list[MessageLikeRepresentation], override_reducer]
    research_brief: Optional[str]
    required_dimensions: Annotated[list[str], override_reducer] = []
    covered_dimensions: Annotated[list[str], override_reducer] = []
    raw_notes: Annotated[list[str], override_reducer] = []
    notes: Annotated[list[str], override_reducer] = []
    evidence_ledger: Annotated[list[dict], operator.add] = []
    final_report: str

class SupervisorState(TypedDict):
    """State for the supervisor that manages research tasks."""
    
    supervisor_messages: Annotated[list[MessageLikeRepresentation], override_reducer]
    research_brief: str
    required_dimensions: list[str] = []
    covered_dimensions: list[str] = []
    notes: Annotated[list[str], override_reducer] = []
    research_iterations: int = 0
    conduct_research_iterations: int = 0
    raw_notes: Annotated[list[str], override_reducer] = []
    evidence_ledger: Annotated[list[dict], operator.add] = []

class ResearcherState(TypedDict):
    """State for individual researchers conducting research."""
    
    researcher_messages: Annotated[list[MessageLikeRepresentation], operator.add]
    tool_call_iterations: int = 0
    search_tool_call_count: int = 0
    research_topic: str
    compressed_research: str
    raw_notes: Annotated[list[str], override_reducer] = []
    evidence_ledger: Annotated[list[dict], operator.add] = []

class ResearcherOutputState(BaseModel):
    """Output state from individual researchers."""
    
    compressed_research: str
    raw_notes: Annotated[list[str], override_reducer] = []
    evidence_ledger: list[EvidenceItem] = Field(default_factory=list)
