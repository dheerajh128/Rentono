"""
Tests for the Phase 3 property-search workflow.

LLM and MCP dependencies are fakes or an in-memory FastMCP server.
These tests do not call Groq or MongoDB.
"""

import unittest
from types import SimpleNamespace

from fastmcp import FastMCP
from pydantic import ValidationError

from ai.agent.graph import build_search_graph
from ai.agent.prompts import intent_prompt
from ai.agent.nodes import (
    INTENT_PARSE_FAILED,
    INVALID_QUERY,
    MCP_RESPONSE_INVALID,
    MCP_SEARCH_FAILED,
    UNSUPPORTED_CATEGORY,
    ListingRank,
    McpResponseInvalid,
    McpToolError,
    RankingOutput,
    build_search_arguments,
    explain_results,
    factual_reason,
    listings_from_payload,
    parse_intent,
    payload_from_call_result,
    rank_listings,
    reason_is_grounded,
    retrieve_candidates,
)
from ai.agent.state import AgentState
from ai.schemas.intent import SearchIntent
from ai.schemas.listing_dto import LISTING_CATEGORIES, ListingDTO, RankedListingDTO


class FakeLLM:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    async def ainvoke(self, prompt, *args, **kwargs):
        self.calls.append(prompt)
        if self.error is not None:
            raise self.error
        return self.result


def listing_dict(
    listing_id="listing-1",
    title="Cedar Cabin",
    description="A quiet cabin on the ridge",
    price=4200,
    location="Manali",
    country="India",
    category="Mountains",
    rating=None,
    review_count=0,
):
    return {
        "_id": listing_id,
        "title": title,
        "description": description,
        "price": price,
        "location": location,
        "country": country,
        "category": category,
        "image": {"url": f"https://example.com/{listing_id}.jpg", "filename": "photo.jpg"},
        "rating": rating,
        "review_count": review_count,
    }


def listing_dto(**kwargs) -> ListingDTO:
    return ListingDTO.model_validate(listing_dict(**kwargs))


def tool_result(data=None, structured_content=None, is_error=False):
    return SimpleNamespace(
        data=data,
        structured_content=structured_content,
        is_error=is_error,
    )


def fixture_server(response, calls, fail=False):
    server = FastMCP(name="fixture-listings")

    @server.tool()
    async def search_listings(
        category: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        location: str | None = None,
        country: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        calls.append(
            {
                "category": category,
                "min_price": min_price,
                "max_price": max_price,
                "location": location,
                "country": country,
                "limit": limit,
            }
        )
        if fail:
            raise RuntimeError("search unavailable")
        return response

    return server


class IntentPromptTests(unittest.TestCase):
    def test_generic_terms_do_not_fill_category(self):
        prompt = intent_prompt("property in Greece")

        for term in (
            "property",
            "properties",
            "listing",
            "listings",
            "stay",
            "stays",
            "place",
        ):
            self.assertIn(term, prompt)
        self.assertIn("not property categories", prompt)
        self.assertIn("They never fill", prompt)
        self.assertIn("category must be one of those supported categories, or null", prompt)
        self.assertIn("Do not infer a category from part of a word or from shared letters", prompt)
        for name in LISTING_CATEGORIES:
            self.assertIn(name, prompt)
        self.assertIn('"property in Greece" means country Greece and category null', prompt)
        self.assertIn('"find listings in Goa" means location Goa and category null', prompt)
        self.assertIn('"any property" means category null', prompt)
        self.assertIn(
            "Still set country, location, min_price, max_price, and preferences",
            prompt,
        )
        self.assertIn("property in Greece", prompt)

    def test_example_queries_keep_place_and_price_rules(self):
        for query in ("property in Greece", "find listings in Goa", "any property"):
            prompt = intent_prompt(query)
            self.assertIn(query, prompt)
            self.assertIn("Set location or country only when the user names that place", prompt)
            self.assertIn("under 5000", prompt)
            self.assertIn("preferences is always an array of strings", prompt)

    def test_genuine_unsupported_stay_type_remains_a_category(self):
        prompt = intent_prompt("treehouse in Greece")

        self.assertIn("type of stay that is not in the list", prompt)
        self.assertIn("Do not replace them with a different supported category", prompt)
        self.assertIn("Do not turn a genuine unsupported stay type into null", prompt)
        self.assertNotIn("convert every unknown category to null", prompt)


class IntentNodeTests(unittest.IsolatedAsyncioTestCase):
    async def test_query_becomes_validated_intent(self):
        llm = FakeLLM(
            result=SearchIntent(
                category="mountains",
                max_price=5000,
                country="India",
                preferences=["peaceful", "great reviews"],
            )
        )
        state = AgentState(query="peaceful mountain stay in India under 5000")

        update = await parse_intent(state, {"configurable": {"intent_llm": llm}})

        self.assertIsInstance(update["intent"], SearchIntent)
        self.assertEqual(update["intent"].category, "Mountains")
        self.assertEqual(update["intent"].max_price, 5000)
        self.assertEqual(update["intent"].country, "India")
        self.assertIsNone(update["intent"].location)
        self.assertIsNone(update["intent"].min_price)
        self.assertEqual(update["intent"].preferences, ["peaceful", "great reviews"])
        self.assertIsNone(update["error"])
        self.assertIn("peaceful mountain stay in India under 5000", llm.calls[0])

    async def test_missing_filters_stay_absent(self):
        llm = FakeLLM(result=SearchIntent(preferences=["quiet"]))
        update = await parse_intent(
            AgentState(query="somewhere quiet"),
            {"configurable": {"intent_llm": llm}},
        )

        intent = update["intent"]
        self.assertIsNone(intent.category)
        self.assertIsNone(intent.min_price)
        self.assertIsNone(intent.max_price)
        self.assertIsNone(intent.location)
        self.assertIsNone(intent.country)
        self.assertEqual(intent.preferences, ["quiet"])

    async def test_greece_query_keeps_country_and_empty_preferences(self):
        llm = FakeLLM(
            result={
                "category": None,
                "min_price": None,
                "max_price": None,
                "location": None,
                "country": "Greece",
                "preferences": None,
            }
        )
        update = await parse_intent(
            AgentState(query="property in Greece"),
            {"configurable": {"intent_llm": llm}},
        )

        self.assertIsNone(update["error"])
        self.assertEqual(update["intent"].country, "Greece")
        self.assertEqual(update["intent"].preferences, [])
        self.assertIsNone(update["intent"].location)
        self.assertIsNone(update["intent"].category)
        self.assertIn("Use []", llm.calls[0])
        self.assertNotIn("Leave every filter null", llm.calls[0])
        self.assertIn("not property categories", llm.calls[0])

    async def test_generic_place_query_keeps_filters_and_null_category(self):
        cases = (
            (
                "find listings in Goa",
                SearchIntent(location="Goa", max_price=5000, preferences=["quiet"]),
            ),
            (
                "any property",
                SearchIntent(preferences=[]),
            ),
        )
        for query, parsed in cases:
            llm = FakeLLM(result=parsed)
            update = await parse_intent(
                AgentState(query=query),
                {"configurable": {"intent_llm": llm}},
            )

            self.assertIsNone(update["error"])
            self.assertIsNone(update["intent"].category)
            self.assertEqual(update["intent"].location, parsed.location)
            self.assertEqual(update["intent"].country, parsed.country)
            self.assertEqual(update["intent"].max_price, parsed.max_price)
            self.assertEqual(update["intent"].preferences, parsed.preferences)
            self.assertIn(query, llm.calls[0])
            self.assertIn('"find listings in Goa" means location Goa and category null', llm.calls[0])
            self.assertIn('"any property" means category null', llm.calls[0])

    async def test_groq_schema_error_does_not_invent_intent(self):
        llm = FakeLLM(
            error=RuntimeError(
                "BadRequestError 400 parameters for tool SearchIntent "
                "did not match schema: ['/preferences']: expected array, but got null"
            )
        )
        update = await parse_intent(
            AgentState(query="property in Greece"),
            {"configurable": {"intent_llm": llm}},
        )

        self.assertIsNone(update["intent"])
        self.assertEqual(update["error"], INTENT_PARSE_FAILED)
        self.assertEqual(update["raw_results"], [])
        self.assertEqual(update["ranked_results"], [])

    async def test_invalid_structured_output_does_not_invent_intent(self):
        llm = FakeLLM(result={"min_price": -20, "category": "Beach"})
        update = await parse_intent(
            AgentState(query="a beach under nothing"),
            {"configurable": {"intent_llm": llm}},
        )

        self.assertIsNone(update["intent"])
        self.assertEqual(update["error"], INTENT_PARSE_FAILED)
        self.assertEqual(update["raw_results"], [])
        self.assertEqual(update["ranked_results"], [])

    async def test_llm_exception_does_not_invent_listings(self):
        llm = FakeLLM(error=RuntimeError("groq unavailable"))
        update = await parse_intent(
            AgentState(query="mountain stay"),
            {"configurable": {"intent_llm": llm}},
        )

        self.assertIsNone(update["intent"])
        self.assertEqual(update["error"], INTENT_PARSE_FAILED)
        self.assertEqual(update["raw_results"], [])

    async def test_blank_query_skips_the_model(self):
        llm = FakeLLM(result=SearchIntent(category="Pools"))
        update = await parse_intent(
            AgentState(query="   "),
            {"configurable": {"intent_llm": llm}},
        )

        self.assertEqual(update["error"], INVALID_QUERY)
        self.assertEqual(llm.calls, [])


class RetrievalNodeTests(unittest.IsolatedAsyncioTestCase):
    def test_arguments_use_supported_filters_only(self):
        arguments = build_search_arguments(
            SearchIntent(
                category="Mountains",
                max_price=5000,
                country="India",
                preferences=["peaceful", "great reviews"],
            )
        )

        self.assertEqual(
            arguments,
            {
                "limit": 10,
                "category": "Mountains",
                "max_price": 5000,
                "country": "India",
            },
        )
        self.assertNotIn("preferences", arguments)

    def test_supported_category_and_location_are_both_passed(self):
        arguments = build_search_arguments(
            SearchIntent(category="pools", location="Goa", country="India", min_price=2000)
        )

        self.assertEqual(
            arguments,
            {
                "limit": 10,
                "category": "Pools",
                "min_price": 2000,
                "location": "Goa",
                "country": "India",
            },
        )

    def test_generic_category_word_does_not_block_place_filters(self):
        arguments = build_search_arguments(
            SearchIntent(category="property", country="Greece", preferences=["quiet"])
        )

        self.assertEqual(arguments, {"limit": 10, "country": "Greece"})
        self.assertNotIn("category", arguments)

    def test_partial_category_word_is_not_searched(self):
        with self.assertRaises(Exception) as caught:
            build_search_arguments(SearchIntent(category="pool", country="Greece"))
        self.assertEqual(caught.exception.category, "pool")

    def test_generic_place_filters_are_searched_without_a_category(self):
        arguments = build_search_arguments(
            SearchIntent(
                country="Greece",
                location="Athens",
                max_price=5000,
                preferences=["quiet"],
            )
        )

        self.assertEqual(
            arguments,
            {
                "limit": 10,
                "max_price": 5000,
                "location": "Athens",
                "country": "Greece",
            },
        )
        self.assertNotIn("category", arguments)
        self.assertNotIn("preferences", arguments)

    def test_unsupported_category_is_not_dropped(self):
        with self.assertRaises(Exception) as caught:
            build_search_arguments(
                SearchIntent(category="Beach", location="Goa", preferences=["quiet"])
            )
        self.assertEqual(caught.exception.category, "Beach")

    def test_unsupported_stay_type_with_country_is_not_cleared(self):
        with self.assertRaises(Exception) as caught:
            build_search_arguments(
                SearchIntent(category="treehouse", country="Greece", preferences=["quiet"])
            )
        self.assertEqual(caught.exception.category, "treehouse")

    def test_error_result_is_not_an_empty_search(self):
        with self.assertRaises(McpToolError):
            payload_from_call_result(tool_result(data=[], is_error=True))

    def test_empty_list_is_a_successful_empty_search(self):
        self.assertEqual(payload_from_call_result(tool_result(data=[])), [])
        self.assertEqual(listings_from_payload([]), [])

    def test_malformed_payload_is_rejected(self):
        payload = payload_from_call_result(
            tool_result(data=None, structured_content={"result": {"title": "Nope"}})
        )
        with self.assertRaises(McpResponseInvalid):
            listings_from_payload(payload)

        with self.assertRaises(ValidationError):
            listings_from_payload([{"title": "Missing id"}])

    def test_payload_keeps_source_fields(self):
        listings = listings_from_payload(
            [listing_dict(rating=4.5, review_count=3)]
        )

        self.assertEqual(listings[0].id, "listing-1")
        self.assertEqual(listings[0].price, 4200)
        self.assertEqual(listings[0].image.url, "https://example.com/listing-1.jpg")
        self.assertEqual(listings[0].rating, 4.5)
        self.assertEqual(listings[0].review_count, 3)

    async def test_mcp_call_passes_filters_and_not_preferences(self):
        calls = []
        server = fixture_server([listing_dict()], calls)
        state = AgentState(
            query="quiet mountain stay",
            intent=SearchIntent(
                category="Mountains",
                max_price=5000,
                country="India",
                preferences=["peaceful"],
            ),
        )

        update = await retrieve_candidates(
            state,
            {"configurable": {"mcp_server": server}},
        )

        self.assertIsNone(update["error"])
        self.assertEqual(len(update["raw_results"]), 1)
        self.assertIsInstance(update["raw_results"][0], ListingDTO)
        self.assertEqual(update["raw_results"][0].id, "listing-1")
        self.assertEqual(calls[0]["category"], "Mountains")
        self.assertEqual(calls[0]["max_price"], 5000)
        self.assertEqual(calls[0]["country"], "India")
        self.assertIsNone(calls[0]["location"])
        self.assertNotIn("preferences", calls[0])
        self.assertNotIn("peaceful", calls[0].values())

    async def test_empty_mcp_result(self):
        calls = []
        server = fixture_server([], calls)
        update = await retrieve_candidates(
            AgentState(query="farms", intent=SearchIntent(category="Farms")),
            {"configurable": {"mcp_server": server}},
        )

        self.assertIsNone(update["error"])
        self.assertEqual(update["raw_results"], [])
        self.assertEqual(len(calls), 1)

    async def test_mcp_tool_error_is_not_an_empty_success(self):
        calls = []
        server = fixture_server([], calls, fail=True)
        update = await retrieve_candidates(
            AgentState(query="pools", intent=SearchIntent(category="Pools")),
            {"configurable": {"mcp_server": server}},
        )

        self.assertEqual(update["error"], MCP_SEARCH_FAILED)
        self.assertEqual(update["raw_results"], [])

    async def test_malformed_mcp_item_does_not_become_a_listing(self):
        calls = []
        server = fixture_server([{"title": "Incomplete"}], calls)
        update = await retrieve_candidates(
            AgentState(query="rooms", intent=SearchIntent(category="Rooms")),
            {"configurable": {"mcp_server": server}},
        )

        self.assertEqual(update["error"], MCP_RESPONSE_INVALID)
        self.assertEqual(update["raw_results"], [])

    async def test_unsupported_category_does_not_call_search(self):
        calls = []
        server = fixture_server([listing_dict()], calls)
        update = await retrieve_candidates(
            AgentState(
                query="beach stay",
                intent=SearchIntent(category="Beach", location="Goa"),
            ),
            {"configurable": {"mcp_server": server}},
        )

        self.assertTrue(update["error"].startswith(UNSUPPORTED_CATEGORY))
        self.assertIn("Beach", update["error"])
        self.assertEqual(update["raw_results"], [])
        self.assertEqual(calls, [])


class RankingNodeTests(unittest.IsolatedAsyncioTestCase):
    async def test_ranking_keeps_source_listing_and_score(self):
        cabin = listing_dto(description="A quiet cabin on the ridge", rating=4.8, review_count=6)
        state = AgentState(
            query="quiet mountain stay with great reviews",
            intent=SearchIntent(category="Mountains", preferences=["quiet"]),
            raw_results=[cabin],
        )
        llm = FakeLLM(
            result=RankingOutput(
                rankings=[
                    ListingRank(
                        listing_id=cabin.id,
                        score=0.91,
                        reason="The description says it is a quiet cabin, and the stored rating is 4.8 from 6 reviews.",
                    )
                ]
            )
        )

        update = await rank_listings(state, {"configurable": {"rank_llm": llm}})
        ranked = update["ranked_results"]

        self.assertEqual(len(ranked), 1)
        self.assertIsInstance(ranked[0], RankedListingDTO)
        self.assertEqual(ranked[0].id, cabin.id)
        self.assertEqual(ranked[0].price, cabin.price)
        self.assertEqual(ranked[0].image.url, cabin.image.url)
        self.assertEqual(ranked[0].description, cabin.description)
        self.assertEqual(ranked[0].score, 0.91)
        self.assertIn("quiet", ranked[0].reason.lower())

    async def test_unknown_and_duplicate_ids_cannot_create_listings(self):
        first = listing_dto(listing_id="a", title="First Cabin")
        second = listing_dto(listing_id="b", title="Second Cabin", price=3000)
        state = AgentState(
            query="mountain stay",
            intent=SearchIntent(category="Mountains"),
            raw_results=[first, second],
        )
        llm = FakeLLM(
            result={
                "rankings": [
                    {"listing_id": "missing", "score": 0.99, "reason": "Invented villa"},
                    {"listing_id": "b", "score": 0.4, "reason": "Second Cabin is a Mountains listing."},
                    {"listing_id": "b", "score": 0.1, "reason": "duplicate"},
                ]
            }
        )

        update = await rank_listings(state, {"configurable": {"rank_llm": llm}})
        ranked = update["ranked_results"]

        self.assertEqual([item.id for item in ranked], ["b", "a"])
        self.assertEqual(ranked[0].score, 0.4)
        self.assertEqual(ranked[0].title, "Second Cabin")
        self.assertEqual(ranked[0].price, 3000)
        self.assertIsNone(ranked[1].score)
        self.assertNotIn("Invented villa", ranked[0].reason)

    async def test_score_outside_range_uses_fallback_for_every_candidate(self):
        first = listing_dto(listing_id="a", title="First Cabin")
        second = listing_dto(listing_id="b", title="Second Cabin")
        state = AgentState(
            query="mountain stay",
            intent=SearchIntent(),
            raw_results=[first, second],
        )
        llm = FakeLLM(
            result={
                "rankings": [
                    {"listing_id": "a", "score": 1.4, "reason": "Too high"},
                    {"listing_id": "b", "score": 0.2, "reason": "Fine"},
                ]
            }
        )

        update = await rank_listings(state, {"configurable": {"rank_llm": llm}})

        self.assertEqual([item.id for item in update["ranked_results"]], ["a", "b"])
        self.assertTrue(all(item.score is None for item in update["ranked_results"]))
        self.assertIn("INR 4200", update["ranked_results"][0].reason)

    async def test_ungrounded_reason_is_replaced(self):
        cabin = listing_dto(
            description="Stone house near the trail",
            rating=None,
            review_count=0,
        )
        self.assertFalse(
            reason_is_grounded(
                "This is peaceful and has great reviews.",
                cabin,
            )
        )
        state = AgentState(
            query="peaceful stay with great reviews",
            intent=SearchIntent(preferences=["peaceful", "great reviews"]),
            raw_results=[cabin],
        )
        llm = FakeLLM(
            result=RankingOutput(
                rankings=[
                    ListingRank(
                        listing_id=cabin.id,
                        score=0.5,
                        reason="This is peaceful and has great reviews.",
                    )
                ]
            )
        )

        update = await rank_listings(state, {"configurable": {"rank_llm": llm}})
        reason = update["ranked_results"][0].reason.lower()

        self.assertEqual(update["ranked_results"][0].score, 0.5)
        self.assertNotIn("peaceful", reason)
        self.assertNotIn("great review", reason)
        self.assertIn("no rating is stored", reason)
        self.assertIn("no description is stored", factual_reason(
            listing_dto(description=None)
        ).lower())

    async def test_empty_candidates_skip_the_model(self):
        llm = FakeLLM(result=RankingOutput(rankings=[]))
        update = await rank_listings(
            AgentState(query="anything", raw_results=[]),
            {"configurable": {"rank_llm": llm}},
        )

        self.assertEqual(update["ranked_results"], [])
        self.assertEqual(llm.calls, [])

    async def test_ranking_error_uses_factual_fallback(self):
        cabin = listing_dto(title="Cedar Cabin", description=None, rating=None)
        llm = FakeLLM(error=RuntimeError("ranker down"))
        update = await rank_listings(
            AgentState(
                query="mountain stay",
                intent=SearchIntent(category="Mountains"),
                raw_results=[cabin],
            ),
            {"configurable": {"rank_llm": llm}},
        )

        ranked = update["ranked_results"][0]
        self.assertEqual(ranked.id, cabin.id)
        self.assertEqual(ranked.price, cabin.price)
        self.assertIsNone(ranked.score)
        self.assertIn("No description is stored", ranked.reason)
        self.assertIn("No rating is stored", ranked.reason)


class ExplanationNodeTests(unittest.IsolatedAsyncioTestCase):
    async def test_summary_uses_actual_listing(self):
        cabin = RankedListingDTO(
            **listing_dto(title="Cedar Cabin", rating=4.5, review_count=4).model_dump(),
            score=0.8,
            reason="The stored rating is 4.5 from 4 reviews.",
        )
        llm = FakeLLM(
            result="Cedar Cabin in Manali matches the search at INR 4200 per night."
        )
        update = await explain_results(
            AgentState(query="mountain stay", ranked_results=[cabin], raw_results=[cabin]),
            {"configurable": {"summary_llm": llm}},
        )

        self.assertIn("Cedar Cabin", update["summary"])
        self.assertNotIn("Ocean Palace", update["summary"])

    async def test_summary_rejects_an_extra_property_name(self):
        cabin = RankedListingDTO(
            **listing_dto(title="Cedar Cabin").model_dump(),
            score=0.8,
            reason="Cedar Cabin is a Mountains listing in Manali.",
        )
        llm = FakeLLM(
            result="Ocean Palace is quieter, but Cedar Cabin is in Manali."
        )
        update = await explain_results(
            AgentState(query="mountain stay", ranked_results=[cabin], raw_results=[cabin]),
            {"configurable": {"summary_llm": llm}},
        )

        self.assertIn("Cedar Cabin", update["summary"])
        self.assertNotIn("Ocean Palace", update["summary"])
        self.assertIn("INR 4200", update["summary"])

    async def test_empty_results_do_not_call_the_model(self):
        llm = FakeLLM(result="Ocean Palace is available nearby.")
        update = await explain_results(
            AgentState(query="castle in Antarctica", raw_results=[], ranked_results=[]),
            {"configurable": {"summary_llm": llm}},
        )

        self.assertIn("No listings matched", update["summary"])
        self.assertNotIn("Ocean Palace", update["summary"])
        self.assertEqual(llm.calls, [])

    async def test_missing_rating_is_not_described_as_great_reviews(self):
        cabin = RankedListingDTO(
            **listing_dto(description=None, rating=None, review_count=0).model_dump(),
            score=0.2,
            reason=factual_reason(listing_dto(description=None, rating=None, review_count=0)),
        )
        llm = FakeLLM(result="Cedar Cabin has great reviews and a perfect score.")
        update = await explain_results(
            AgentState(query="mountain stay", ranked_results=[cabin], raw_results=[cabin]),
            {"configurable": {"summary_llm": llm}},
        )

        self.assertIn("Cedar Cabin", update["summary"])
        self.assertIn("No rating is stored", update["summary"])
        self.assertNotIn("great review", update["summary"].lower())

    async def test_summary_failure_does_not_invent_a_listing(self):
        cabin = RankedListingDTO(
            **listing_dto(title="Cedar Cabin").model_dump(),
            score=None,
            reason=factual_reason(listing_dto()),
        )
        llm = FakeLLM(error=RuntimeError("summary down"))
        update = await explain_results(
            AgentState(query="mountain stay", ranked_results=[cabin], raw_results=[cabin]),
            {"configurable": {"summary_llm": llm}},
        )

        self.assertIn("Cedar Cabin", update["summary"])
        self.assertIn("ranked ordering was not available", update["summary"])
        self.assertNotIn("Ocean Palace", update["summary"])


class GraphTests(unittest.IsolatedAsyncioTestCase):
    def test_graph_import_does_not_run_a_search(self):
        graph = build_search_graph()
        self.assertTrue(hasattr(graph, "ainvoke"))

    async def test_valid_query_uses_mcp_and_preserves_listing_fields(self):
        calls = []
        payload = listing_dict(
            listing_id="listing-9",
            title="Cedar Cabin",
            description="A quiet cabin on the ridge",
            price=4500,
            rating=4.6,
            review_count=8,
        )
        server = fixture_server([payload], calls)
        intent_llm = FakeLLM(
            result=SearchIntent(
                category="Mountains",
                max_price=5000,
                country="India",
                preferences=["peaceful"],
            )
        )
        rank_llm = FakeLLM(
            result=RankingOutput(
                rankings=[
                    ListingRank(
                        listing_id="listing-9",
                        score=0.86,
                        reason="The description says it is a quiet cabin. The stored rating is 4.6 from 8 reviews.",
                    )
                ]
            )
        )
        summary_llm = FakeLLM(
            result="Cedar Cabin in Manali is the closest match at INR 4500 per night."
        )
        graph = build_search_graph()

        result = await graph.ainvoke(
            {"query": "peaceful mountain stay in India under 5000"},
            {
                "configurable": {
                    "intent_llm": intent_llm,
                    "rank_llm": rank_llm,
                    "summary_llm": summary_llm,
                    "mcp_server": server,
                }
            },
        )

        self.assertEqual(result["query"], "peaceful mountain stay in India under 5000")
        self.assertEqual(result["intent"].category, "Mountains")
        self.assertEqual(result["intent"].preferences, ["peaceful"])
        self.assertIsNone(result["error"])
        self.assertEqual(calls[0]["category"], "Mountains")
        self.assertEqual(calls[0]["max_price"], 5000)
        self.assertNotIn("preferences", calls[0])
        ranked = result["ranked_results"][0]
        self.assertEqual(ranked.id, "listing-9")
        self.assertEqual(ranked.price, 4500)
        self.assertEqual(ranked.image.url, "https://example.com/listing-9.jpg")
        self.assertEqual(ranked.location, "Manali")
        self.assertEqual(ranked.score, 0.86)
        self.assertTrue(ranked.reason)
        self.assertIn("Cedar Cabin", result["summary"])

    async def test_empty_search_skips_ranking(self):
        calls = []
        server = fixture_server([], calls)
        rank_llm = FakeLLM(
            result=RankingOutput(
                rankings=[ListingRank(listing_id="ghost", score=1, reason="Invented")]
            )
        )
        graph = build_search_graph()

        result = await graph.ainvoke(
            {"query": "show me farms"},
            {
                "configurable": {
                    "intent_llm": FakeLLM(result=SearchIntent(category="Farms")),
                    "rank_llm": rank_llm,
                    "summary_llm": FakeLLM(result="Ocean Palace is free."),
                    "mcp_server": server,
                }
            },
        )

        self.assertEqual(result["raw_results"], [])
        self.assertEqual(result["ranked_results"], [])
        self.assertIsNone(result["error"])
        self.assertEqual(rank_llm.calls, [])
        self.assertIn("No listings matched", result["summary"])
        self.assertNotIn("Ocean Palace", result["summary"])
        self.assertEqual(len(calls), 1)

    async def test_mcp_and_llm_failures_are_controlled(self):
        calls = []
        server = fixture_server([listing_dict(title="Cedar Cabin")], calls, fail=True)
        graph = build_search_graph()

        failed_search = await graph.ainvoke(
            {"query": "pools in Goa"},
            {
                "configurable": {
                    "intent_llm": FakeLLM(result=SearchIntent(category="Pools", location="Goa")),
                    "rank_llm": FakeLLM(error=RuntimeError("should not rank")),
                    "summary_llm": FakeLLM(result="Ocean Palace"),
                    "mcp_server": server,
                }
            },
        )

        self.assertEqual(failed_search["error"], MCP_SEARCH_FAILED)
        self.assertEqual(failed_search["ranked_results"], [])
        self.assertIn("failed", failed_search["summary"].lower())
        self.assertNotIn("Ocean Palace", failed_search["summary"])
        self.assertNotIn("Cedar Cabin", failed_search["summary"])

        failed_intent = await graph.ainvoke(
            {"query": "mountain stay"},
            {
                "configurable": {
                    "intent_llm": FakeLLM(error=RuntimeError("groq down")),
                    "mcp_server": server,
                }
            },
        )

        self.assertEqual(failed_intent["error"], INTENT_PARSE_FAILED)
        self.assertIsNone(failed_intent["intent"])
        self.assertEqual(failed_intent["ranked_results"], [])
        self.assertEqual(len(calls), 1)

    async def test_unsupported_category_skips_mcp(self):
        calls = []
        server = fixture_server([listing_dict()], calls)
        graph = build_search_graph()

        result = await graph.ainvoke(
            {"query": "find a beach hut"},
            {
                "configurable": {
                    "intent_llm": FakeLLM(result=SearchIntent(category="Beach")),
                    "rank_llm": FakeLLM(error=RuntimeError("should not rank")),
                    "mcp_server": server,
                }
            },
        )

        self.assertTrue(result["error"].startswith(UNSUPPORTED_CATEGORY))
        self.assertEqual(calls, [])
        self.assertEqual(result["raw_results"], [])
        self.assertIn("Beach", result["summary"])
        self.assertIn("not a supported category", result["summary"])


if __name__ == "__main__":
    unittest.main()
