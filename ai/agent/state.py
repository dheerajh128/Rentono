"""
State for the LangGraph property-search workflow.

LangGraph 0.4.8 accepts a Pydantic model as a state schema and constructs it
with schema(**input) before a run. Defaults here let a run start from a query
alone. The compiled graph lives in ai.agent.graph and is not built on import.
"""

from typing import Optional

from pydantic import BaseModel, Field

from ai.schemas.intent import SearchIntent
from ai.schemas.listing_dto import ListingDTO, RankedListingDTO


class AgentState(BaseModel):
    """
    Shared state for intent extraction, MCP retrieval, ranking, and explanation.

    raw_results holds candidate listings after they have been parsed into
    ListingDTO. ranked_results holds the same listings after scoring.
    summary and error stay unset until a later node writes them.
    """

    query: str
    intent: Optional[SearchIntent] = None
    raw_results: list[ListingDTO] = Field(default_factory=list)
    ranked_results: list[RankedListingDTO] = Field(default_factory=list)
    summary: Optional[str] = None
    error: Optional[str] = None
