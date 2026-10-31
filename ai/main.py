"""
FastAPI entry point for the Rentono property-search agent.

Importing this module does not call Groq or MongoDB. Search requests delegate
to the existing LangGraph workflow.
"""

import logging
import re
import traceback
from typing import Any, Mapping, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from ai.agent.graph import run_search
from ai.schemas.intent import SearchIntent
from ai.schemas.listing_dto import RankedListingDTO

logger = logging.getLogger(__name__)

MAX_QUERY_LENGTH = 500

app = FastAPI(title="Rentono AI")


class SearchRequest(BaseModel):
    """Natural-language search submitted by the client."""

    query: str = Field(min_length=1, max_length=MAX_QUERY_LENGTH)

    @field_validator("query")
    @classmethod
    def query_must_contain_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("query must not be blank")
        if len(text) > MAX_QUERY_LENGTH:
            raise ValueError("query is too long")
        return text


class SearchResponse(BaseModel):
    """Structured search result. Listing ids use the MongoDB _id alias."""

    query: str
    intent: Optional[SearchIntent] = None
    results: list[RankedListingDTO] = Field(default_factory=list)
    summary: Optional[str] = None
    error: Optional[str] = None


def _redact(text: str) -> str:
    text = re.sub(r"gsk_[A-Za-z0-9_\-]+", "[REDACTED]", text)
    text = re.sub(r"mongodb(\+srv)?://\S+", "mongodb://[REDACTED]", text)
    return text


def _log_unexpected(exc: BaseException) -> None:
    rendered = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    logger.error("Unhandled search failure\n%s", _redact(rendered))


def _as_intent(value: Any) -> Optional[SearchIntent]:
    if value is None:
        return None
    if isinstance(value, SearchIntent):
        return value
    return SearchIntent.model_validate(value)


def _as_results(value: Any) -> list[RankedListingDTO]:
    if not value:
        return []
    results = []
    for item in value:
        if isinstance(item, RankedListingDTO):
            results.append(item)
        else:
            results.append(RankedListingDTO.model_validate(item))
    return results


def search_response_from_state(result: Mapping[str, Any], query: str) -> SearchResponse:
    error = result.get("error")
    summary = result.get("summary")
    return SearchResponse(
        query=result.get("query") or query,
        intent=_as_intent(result.get("intent")),
        results=_as_results(result.get("ranked_results")),
        summary=summary if isinstance(summary, str) else None,
        error=error if isinstance(error, str) else None,
    )


@app.get("/health")
async def health() -> dict[str, str]:
    """Process liveness only. External services are not checked."""
    return {"status": "ok"}


@app.post("/ai/search", response_model=SearchResponse, response_model_by_alias=True)
async def search(body: SearchRequest) -> SearchResponse:
    try:
        result = await run_search(body.query)
    except Exception as exc:
        _log_unexpected(exc)
        raise HTTPException(
            status_code=500,
            detail="The search could not be completed.",
        ) from None
    return search_response_from_state(result, body.query)


def serve() -> None:
    """Start the API using AI_PORT from the shared root .env."""
    import uvicorn

    from ai.config import get_settings

    settings = get_settings()
    uvicorn.run(app, host="127.0.0.1", port=settings.AI_PORT)


if __name__ == "__main__":
    serve()
