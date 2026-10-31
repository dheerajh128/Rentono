"""
LangGraph nodes for smart property search.

Retrieval goes through the FastMCP client. Listing fields written into the
state always come from the tool payload, never from model prose.
"""

import logging
import re
import traceback
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator

from ai.agent.prompts import intent_prompt, ranking_prompt, summary_prompt
from ai.agent.state import AgentState
from ai.schemas.intent import SearchIntent
from ai.schemas.listing_dto import LISTING_CATEGORIES, ListingDTO, RankedListingDTO
from ai.services.llm_service import get_structured_llm

logger = logging.getLogger(__name__)

SEARCH_LIMIT = 10
SEARCH_ARGUMENT_KEYS = {
    "category",
    "min_price",
    "max_price",
    "location",
    "country",
    "limit",
}

INVALID_QUERY = "invalid_query"
INTENT_PARSE_FAILED = "intent_parse_failed"
UNSUPPORTED_CATEGORY = "unsupported_category"
MCP_SEARCH_FAILED = "mcp_search_failed"
MCP_RESPONSE_INVALID = "mcp_response_invalid"

_UNGROUNDED_QUALITIES = (
    ("peaceful", ("peaceful", "peace", "quiet", "calm", "serene", "tranquil")),
    ("quiet", ("quiet", "calm", "peaceful", "serene", "tranquil")),
    ("calm", ("calm", "quiet", "peaceful", "serene")),
    ("luxurious", ("luxurious", "luxury", "premium")),
    ("luxury", ("luxury", "luxurious", "premium")),
    ("safe", ("safe", "safety", "secure")),
)
_REVIEW_CLAIMS = (
    "great review",
    "great reviews",
    "excellent review",
    "excellent reviews",
    "highly rated",
    "top rated",
    "top-rated",
)


class McpToolError(Exception):
    """The MCP client reported a failed tool call."""


class McpResponseInvalid(Exception):
    """The tool returned a payload that is not a list of listings."""


class ListingRank(BaseModel):
    """One model ranking decision. Source listing fields are not accepted here."""

    listing_id: str = Field(min_length=1)
    score: float = Field(ge=0, le=1)
    reason: str = ""


class RankingOutput(BaseModel):
    rankings: list[ListingRank] = Field(default_factory=list)

    @field_validator("rankings")
    @classmethod
    def scores_are_unit_interval(cls, rankings: list[ListingRank]) -> list[ListingRank]:
        for item in rankings:
            if item.score < 0 or item.score > 1:
                raise ValueError("score must be between 0 and 1")
        return rankings


class SearchSummary(BaseModel):
    summary: str = Field(min_length=1)


class UnsupportedCategoryError(Exception):
    def __init__(self, category: str):
        self.category = category
        super().__init__(category)


def _configurable(config: Optional[dict]) -> dict:
    if not config:
        return {}
    values = config.get("configurable") or {}
    return values if isinstance(values, dict) else {}


def _default_server():
    from ai.mcp_server import mcp

    return mcp


def build_search_arguments(intent: SearchIntent) -> dict[str, Any]:
    """
    Arguments for the search_listings MCP tool.

    Preferences are omitted. An unsupported category raises instead of being
    dropped, because the listing service would otherwise search without it.
    """
    if intent.category and intent.supported_category() is None:
        raise UnsupportedCategoryError(intent.category)

    arguments: dict[str, Any] = {"limit": SEARCH_LIMIT}
    category = intent.supported_category()
    if category:
        arguments["category"] = category
    if intent.min_price is not None:
        arguments["min_price"] = intent.min_price
    if intent.max_price is not None:
        arguments["max_price"] = intent.max_price
    if intent.location:
        arguments["location"] = intent.location
    if intent.country:
        arguments["country"] = intent.country

    unexpected = set(arguments) - SEARCH_ARGUMENT_KEYS
    if unexpected:
        raise ValueError(f"unsupported search arguments: {sorted(unexpected)}")
    return arguments


def payload_from_call_result(result: Any) -> Any:
    """Read the tool payload. An error result is not treated as an empty list."""
    if getattr(result, "is_error", False):
        raise McpToolError("search_listings returned an error")

    data = getattr(result, "data", None)
    if isinstance(data, list):
        return data

    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict) and "result" in structured:
        return structured["result"]
    if isinstance(structured, list):
        return structured
    if data is not None:
        return data
    raise McpResponseInvalid("search_listings returned no payload")


def listings_from_payload(payload: Any) -> list[ListingDTO]:
    if not isinstance(payload, list):
        raise McpResponseInvalid("search_listings payload was not a list")

    listings: list[ListingDTO] = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            raise McpResponseInvalid("search_listings item was not an object")
        listing = ListingDTO.model_validate(item)
        if listing.id in seen:
            continue
        seen.add(listing.id)
        listings.append(listing)
    return listings


def listing_evidence(listing: ListingDTO) -> str:
    return f"{listing.title}\n{listing.description or ''}".lower()


def reason_is_grounded(reason: str, listing: ListingDTO) -> bool:
    """Reject reasons that assert qualities or reviews the listing does not store."""
    text = reason.lower()
    evidence = listing_evidence(listing)
    for phrase, supported_by in _UNGROUNDED_QUALITIES:
        if phrase in text and not any(token in evidence for token in supported_by):
            return False
    if any(phrase in text for phrase in _REVIEW_CLAIMS):
        if listing.rating is None or not listing.review_count:
            return False
    return True


def factual_reason(listing: ListingDTO) -> str:
    """A reason built only from stored listing fields."""
    description = (
        "A description is stored."
        if listing.description
        else "No description is stored."
    )
    if listing.rating is not None and listing.review_count:
        rating = (
            f"The stored average rating is {listing.rating:.1f} "
            f"from {listing.review_count} reviews."
        )
    else:
        rating = "No rating is stored for this listing."
    return (
        f"{listing.title} is listed as {listing.category} in {listing.location}, "
        f"{listing.country}, at INR {listing.price:.0f} per night. "
        f"{description} {rating}"
    )


def to_ranked(
    listing: ListingDTO,
    score: Optional[float],
    reason: str,
) -> RankedListingDTO:
    grounded = reason.strip()
    if not grounded or not reason_is_grounded(grounded, listing):
        grounded = factual_reason(listing)
    return RankedListingDTO(**listing.model_dump(), score=score, reason=grounded)


def fallback_rankings(listings: list[ListingDTO]) -> list[RankedListingDTO]:
    """
    Used when model ranking cannot be trusted.

    Order stays the MCP order. Scores are left unset rather than invented.
    """
    return [to_ranked(listing, None, factual_reason(listing)) for listing in listings]


def reconcile_rankings(
    listings: list[ListingDTO],
    output: RankingOutput,
) -> list[RankedListingDTO]:
    """
    Keep model order for known ids, then append any candidate the model omitted.

    Unknown ids and duplicate ids are discarded. A score outside 0-1 cannot
    appear here because RankingOutput rejects it; callers fall back instead.
    """
    if not output.rankings:
        return fallback_rankings(listings)

    by_id = {listing.id: listing for listing in listings}
    used: set[str] = set()
    ranked: list[RankedListingDTO] = []
    for decision in output.rankings:
        if decision.listing_id not in by_id or decision.listing_id in used:
            continue
        used.add(decision.listing_id)
        ranked.append(
            to_ranked(by_id[decision.listing_id], decision.score, decision.reason)
        )

    if not ranked:
        return fallback_rankings(listings)

    for listing in listings:
        if listing.id not in used:
            ranked.append(to_ranked(listing, None, factual_reason(listing)))
    return ranked


def _coerce_ranking(result: Any) -> RankingOutput:
    if isinstance(result, RankingOutput):
        return result
    if isinstance(result, dict):
        return RankingOutput.model_validate(result)
    raise TypeError("ranking output was not a ranking object")


_SUMMARY_TOKEN_ALLOWLIST = {"inr", "rs"}


def _known_summary_text(listings: list[RankedListingDTO]) -> str:
    parts: list[str] = []
    for listing in listings:
        parts.extend(
            [
                listing.title,
                listing.location,
                listing.country,
                listing.category,
                listing.description or "",
                listing.reason or "",
            ]
        )
    return " ".join(parts).lower()


def summary_is_acceptable(summary: str, listings: list[RankedListingDTO]) -> bool:
    """
    Accept a model summary only when it names a retrieved listing, does not
    invent review claims, and does not introduce a capitalized name that is
    absent from the retrieved listing fields.
    """
    text = summary.strip()
    if not text:
        return False
    if listings and not any(listing.title in text for listing in listings):
        return False
    has_rating = any(
        listing.rating is not None and listing.review_count for listing in listings
    )
    lowered = text.lower()
    if not has_rating and any(phrase in lowered for phrase in _REVIEW_CLAIMS):
        return False

    known = _known_summary_text(listings)
    for token in re.findall(r"[A-Za-z][A-Za-z']*", text):
        if token[0].islower():
            continue
        word = token.lower()
        if word in _SUMMARY_TOKEN_ALLOWLIST or word in known:
            continue
        return False
    return True


def compose_summary(state: AgentState) -> str:
    """Deterministic summary used for empty results, errors, and model failure."""
    error = state.error or ""
    if error.startswith(INVALID_QUERY):
        return "No search was run because the query was empty."
    if error.startswith(INTENT_PARSE_FAILED):
        return (
            "The request could not be turned into a property search, "
            "so no listings are shown."
        )
    if error.startswith(UNSUPPORTED_CATEGORY):
        category = state.intent.category if state.intent and state.intent.category else "That category"
        names = ", ".join(LISTING_CATEGORIES)
        return (
            f"{category} is not a supported category, so listings were not searched. "
            f"Supported categories are: {names}."
        )
    if error.startswith(MCP_SEARCH_FAILED):
        return "The listing search failed, so no properties are shown."
    if error.startswith(MCP_RESPONSE_INVALID):
        return (
            "The listing search returned data that could not be read, "
            "so no properties are shown."
        )

    listings = list(state.ranked_results)
    if not listings:
        return "No listings matched this search. No other properties were added."

    sentences = []
    if all(listing.score is None for listing in listings):
        sentences.append(
            "These listings matched the search filters and are shown in search "
            "order because a ranked ordering was not available."
        )
    else:
        sentences.append(f"{len(listings)} listings matched the search.")

    for listing in listings[:3]:
        if listing.rating is not None and listing.review_count:
            rating = (
                f" Stored rating {listing.rating:.1f} from "
                f"{listing.review_count} reviews."
            )
        else:
            rating = " No rating is stored."
        sentences.append(
            f"{listing.title} in {listing.location}, {listing.country} is "
            f"{listing.category} at INR {listing.price:.0f} per night.{rating}"
        )
    return " ".join(sentences)


def _read_summary(result: Any) -> Optional[str]:
    if isinstance(result, SearchSummary):
        return result.summary
    if isinstance(result, str):
        return result
    if isinstance(result, dict) and isinstance(result.get("summary"), str):
        return result["summary"]
    return None


async def _invoke_structured(llm: Any, prompt: str) -> Any:
    if hasattr(llm, "ainvoke"):
        return await llm.ainvoke(prompt)
    return llm.invoke(prompt)


def _log_intent_failure(exc: BaseException) -> None:
    """Log the parse failure and its traceback. API keys are redacted."""
    rendered = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    key = ""
    try:
        from ai.config import get_settings

        key = get_settings().GROQ_API_KEY or ""
    except Exception:
        key = ""
    if key:
        rendered = rendered.replace(key, "[REDACTED]")
    rendered = re.sub(r"gsk_[A-Za-z0-9_\-]+", "[REDACTED]", rendered)
    logger.error("Intent parsing failed\n%s", rendered)


async def parse_intent(state: AgentState, config: Optional[dict] = None) -> dict:
    """Turn the user query into a SearchIntent. Does not read listings."""
    query = state.query.strip()
    if not query:
        return {
            "intent": None,
            "error": INVALID_QUERY,
            "raw_results": [],
            "ranked_results": [],
        }

    try:
        llm = _configurable(config).get("intent_llm")
        if llm is None:
            llm = get_structured_llm(SearchIntent)
        result = await _invoke_structured(llm, intent_prompt(query))
        if isinstance(result, SearchIntent):
            intent = result
        else:
            intent = SearchIntent.model_validate(result)
    except Exception as exc:
        _log_intent_failure(exc)
        return {
            "intent": None,
            "error": INTENT_PARSE_FAILED,
            "raw_results": [],
            "ranked_results": [],
        }

    return {"intent": intent, "error": None}


async def _call_search_tool(server: Any, arguments: dict[str, Any]) -> Any:
    from fastmcp import Client

    async with Client(server) as client:
        return await client.call_tool("search_listings", arguments)


async def retrieve_candidates(state: AgentState, config: Optional[dict] = None) -> dict:
    """Load candidate listings through the MCP client."""
    if state.intent is None:
        return {
            "error": INTENT_PARSE_FAILED,
            "raw_results": [],
            "ranked_results": [],
        }

    try:
        arguments = build_search_arguments(state.intent)
    except UnsupportedCategoryError as exc:
        return {
            "error": f"{UNSUPPORTED_CATEGORY}: {exc.category}",
            "raw_results": [],
            "ranked_results": [],
        }

    server = _configurable(config).get("mcp_server") or _default_server()
    try:
        result = await _call_search_tool(server, arguments)
        payload = payload_from_call_result(result)
        listings = listings_from_payload(payload)
    except McpResponseInvalid:
        return {
            "error": MCP_RESPONSE_INVALID,
            "raw_results": [],
            "ranked_results": [],
        }
    except ValidationError:
        return {
            "error": MCP_RESPONSE_INVALID,
            "raw_results": [],
            "ranked_results": [],
        }
    except Exception:
        return {
            "error": MCP_SEARCH_FAILED,
            "raw_results": [],
            "ranked_results": [],
        }

    return {"raw_results": listings, "ranked_results": [], "error": None}


async def rank_listings(state: AgentState, config: Optional[dict] = None) -> dict:
    """
    Score the retrieved listings.

    If the model output is missing, invalid, or contains a score outside 0-1,
    every candidate is kept in MCP order with score left unset.
    """
    if not state.raw_results:
        return {"ranked_results": []}

    try:
        llm = _configurable(config).get("rank_llm")
        if llm is None:
            llm = get_structured_llm(RankingOutput)
        prompt = ranking_prompt(
            state.query,
            state.intent or SearchIntent(),
            list(state.raw_results),
        )
        result = await _invoke_structured(llm, prompt)
        output = _coerce_ranking(result)
        ranked = reconcile_rankings(list(state.raw_results), output)
    except Exception:
        ranked = fallback_rankings(list(state.raw_results))

    return {"ranked_results": ranked}


async def explain_results(state: AgentState, config: Optional[dict] = None) -> dict:
    """
    Write the overall summary.

    Empty results and errors use a fixed explanation. A model summary is kept
    only when it names a retrieved listing and does not invent review claims.
    """
    fallback = compose_summary(state)
    listings = list(state.ranked_results)
    summary = fallback

    if listings and not state.error:
        try:
            llm = _configurable(config).get("summary_llm")
            if llm is None:
                llm = get_structured_llm(SearchSummary)
            result = await _invoke_structured(llm, summary_prompt(state.query, listings))
            drafted = _read_summary(result)
            if drafted and summary_is_acceptable(drafted, listings):
                summary = drafted.strip()
        except Exception:
            summary = fallback

    return {
        "summary": summary,
        "raw_results": list(state.raw_results),
        "ranked_results": listings,
    }


def route_after_parse(state: AgentState) -> str:
    if state.error:
        return "explain_results"
    return "retrieve_candidates"


def route_after_retrieve(state: AgentState) -> str:
    if state.error or not state.raw_results:
        return "explain_results"
    return "rank_listings"
