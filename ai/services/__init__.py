"""
Business logic layer for the AI service.
Shared services used by MCP tools, LangGraph nodes, and FastAPI endpoints.
"""

from ai.services.listing_service import (
    search_listings,
    attach_ratings,
    get_listing_by_id,
    get_all_categories
)

from ai.services.llm_service import (
    get_llm,
    get_structured_llm,
    list_models,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE
)

__all__ = [
    # Listing services
    "search_listings",
    "attach_ratings",
    "get_listing_by_id",
    "get_all_categories",
    # LLM services
    "get_llm",
    "get_structured_llm",
    "list_models",
    "DEFAULT_MODEL",
    "DEFAULT_TEMPERATURE"
]
