"""
Unit tests for SearchIntent and AgentState.

These tests cover schema validation, defaults, and model compatibility only.
They do not execute a graph, call Groq, or connect to MongoDB.
"""

import unittest

from pydantic import ValidationError

from ai.agent.state import AgentState
from ai.schemas import (
    LISTING_CATEGORIES,
    ListingDTO,
    RankedListingDTO,
    SearchFilters,
    validate_category,
)
from ai.schemas.intent import GENERIC_SEARCH_TERMS, SearchIntent
from ai.schemas.listing_dto import ListingDTO as ListingDTODirect


def sample_listing() -> ListingDTO:
    return ListingDTO(
        _id="507f1f77bcf86cd799439011",
        title="Mountainy House",
        description="Quiet stay",
        price=12000,
        location="Goa",
        country="India",
        category="Pools",
        image={"url": "https://example.com/house.jpg", "filename": "house.jpg"},
    )


class SearchIntentTests(unittest.TestCase):
    def test_all_optional_filters_can_be_omitted(self):
        intent = SearchIntent()

        self.assertIsNone(intent.category)
        self.assertIsNone(intent.min_price)
        self.assertIsNone(intent.max_price)
        self.assertIsNone(intent.location)
        self.assertIsNone(intent.country)
        self.assertEqual(intent.preferences, [])

    def test_valid_price_range_is_accepted(self):
        intent = SearchIntent(min_price=1000, max_price=5000)

        self.assertEqual(intent.min_price, 1000)
        self.assertEqual(intent.max_price, 5000)

        exact = SearchIntent(min_price=2500, max_price=2500)
        self.assertEqual(exact.min_price, exact.max_price)

    def test_negative_prices_are_rejected(self):
        with self.assertRaises(ValidationError):
            SearchIntent(min_price=-1)

        with self.assertRaises(ValidationError):
            SearchIntent(max_price=-0.01)

    def test_min_price_above_max_price_is_rejected(self):
        with self.assertRaises(ValidationError):
            SearchIntent(min_price=5000, max_price=1000)

    def test_preferences_work_without_category_or_location(self):
        intent = SearchIntent(
            preferences=["quiet surroundings", "  great reviews  "]
        )

        self.assertIsNone(intent.category)
        self.assertIsNone(intent.location)
        self.assertEqual(
            intent.preferences,
            ["quiet surroundings", "great reviews"],
        )

    def test_blank_optional_strings_become_none(self):
        intent = SearchIntent(
            category="   ",
            location="",
            country=" \n ",
            preferences=["  ", "honeymoon"],
        )

        self.assertIsNone(intent.category)
        self.assertIsNone(intent.location)
        self.assertIsNone(intent.country)
        self.assertEqual(intent.preferences, ["honeymoon"])

    def test_known_category_uses_canonical_spelling(self):
        intent = SearchIntent(category=" mountains ")

        self.assertEqual(intent.category, "Mountains")
        self.assertIn(intent.category, LISTING_CATEGORIES)
        self.assertEqual(intent.supported_category(), "Mountains")

    def test_every_supported_category_normalizes_by_case(self):
        self.assertEqual(
            LISTING_CATEGORIES,
            [
                "Rooms",
                "Iconic Cities",
                "Mountains",
                "Castles",
                "Pools",
                "Camping",
                "Farms",
                "Arctic",
            ],
        )
        for name in LISTING_CATEGORIES:
            intent = SearchIntent(
                category=f"  {name.lower()}  ",
                location="Goa",
                country="India",
                max_price=5000,
                preferences=["quiet"],
            )
            self.assertEqual(intent.category, name)
            self.assertEqual(intent.supported_category(), name)
            self.assertEqual(intent.location, "Goa")
            self.assertEqual(intent.country, "India")
            self.assertEqual(intent.max_price, 5000)
            self.assertEqual(intent.preferences, ["quiet"])

    def test_generic_terms_do_not_become_categories(self):
        for term in (
            "property",
            "Properties",
            "listing",
            "listings",
            "stay",
            "stays",
            " place ",
        ):
            intent = SearchIntent(
                category=term,
                location="Goa",
                country="Greece",
                min_price=1000,
                max_price=5000,
                preferences=["quiet"],
            )
            self.assertIsNone(intent.category, term)
            self.assertIsNone(intent.supported_category())
            self.assertEqual(intent.location, "Goa")
            self.assertEqual(intent.country, "Greece")
            self.assertEqual(intent.min_price, 1000)
            self.assertEqual(intent.max_price, 5000)
            self.assertEqual(intent.preferences, ["quiet"])
        self.assertEqual(
            GENERIC_SEARCH_TERMS,
            frozenset(
                {
                    "property",
                    "properties",
                    "listing",
                    "listings",
                    "stay",
                    "stays",
                    "place",
                }
            ),
        )

    def test_partial_words_are_not_inferred_as_categories(self):
        for text in ("pool", "room", "mountain", "mountain stay", "camp", "city"):
            intent = SearchIntent(category=text, country="Greece")
            self.assertEqual(intent.category, text)
            self.assertIsNone(intent.supported_category())
            self.assertEqual(intent.country, "Greece")

    def test_unknown_category_is_preserved(self):
        intent = SearchIntent(category=" Beach ", location="Goa", country="Greece")

        self.assertEqual(intent.category, "Beach")
        self.assertNotIn(intent.category, LISTING_CATEGORIES)
        self.assertIsNone(intent.supported_category())
        self.assertIsNone(validate_category(intent.category))
        self.assertEqual(intent.location, "Goa")
        self.assertEqual(intent.country, "Greece")

    def test_category_schema_lists_supported_categories(self):
        schema = SearchIntent.model_json_schema()["properties"]["category"]
        description = schema["description"]
        for name in LISTING_CATEGORIES:
            self.assertIn(name, description)
        variants = schema.get("anyOf", [schema])
        types = {item.get("type") for item in variants}
        self.assertIn("string", types)
        self.assertIn("null", types)

    def test_non_string_preference_is_rejected(self):
        with self.assertRaises(ValidationError):
            SearchIntent(preferences=["quiet", 3])

    def test_empty_preference_list_is_kept(self):
        intent = SearchIntent(preferences=[])

        self.assertEqual(intent.preferences, [])

    def test_omitted_preferences_default_to_empty_list(self):
        intent = SearchIntent.model_validate({"country": "Greece"})

        self.assertEqual(intent.country, "Greece")
        self.assertEqual(intent.preferences, [])

    def test_null_preferences_become_empty_list(self):
        intent = SearchIntent.model_validate(
            {
                "country": "Greece",
                "location": None,
                "category": None,
                "min_price": None,
                "max_price": None,
                "preferences": None,
            }
        )

        self.assertEqual(intent.country, "Greece")
        self.assertIsNone(intent.location)
        self.assertIsNone(intent.category)
        self.assertIsNone(intent.min_price)
        self.assertIsNone(intent.max_price)
        self.assertEqual(intent.preferences, [])

    def test_preferences_schema_accepts_array_or_null(self):
        schema = SearchIntent.model_json_schema()["properties"]["preferences"]
        variants = schema.get("anyOf", [schema])
        types = {item.get("type") for item in variants}

        self.assertIn("array", types)
        self.assertIn("null", types)
        self.assertEqual(schema.get("default"), [])
        array_schema = next(item for item in variants if item.get("type") == "array")
        self.assertEqual(array_schema["items"]["type"], "string")

    def test_json_schema_exposes_supported_filters_only(self):
        schema = SearchIntent.model_json_schema()
        properties = set(schema["properties"])

        self.assertEqual(
            properties,
            {
                "category",
                "min_price",
                "max_price",
                "location",
                "country",
                "preferences",
            },
        )
        self.assertNotIn("category", schema.get("required", []))


class AgentStateTests(unittest.TestCase):
    def test_query_only_state_has_no_intent(self):
        state = AgentState(query="peaceful mountain stay under 5000")

        self.assertEqual(state.query, "peaceful mountain stay under 5000")
        self.assertIsNone(state.intent)
        self.assertIsNone(state.summary)
        self.assertIsNone(state.error)

    def test_result_lists_default_to_empty(self):
        state = AgentState(query="any stay")

        self.assertEqual(state.raw_results, [])
        self.assertEqual(state.ranked_results, [])

    def test_state_holds_listing_and_ranked_listing(self):
        listing = sample_listing()
        ranked = RankedListingDTO(
            **listing.model_dump(),
            score=0.82,
            reason="Quiet surroundings and strong reviews",
        )
        intent = SearchIntent(
            category="Pools",
            max_price=15000,
            preferences=["quiet surroundings"],
        )

        state = AgentState(
            query="quiet pool stay",
            intent=intent,
            raw_results=[listing],
            ranked_results=[ranked],
            summary="One pool stay matches the budget.",
        )

        self.assertIsInstance(state.raw_results[0], ListingDTO)
        self.assertIsInstance(state.ranked_results[0], RankedListingDTO)
        self.assertEqual(state.raw_results[0].id, "507f1f77bcf86cd799439011")
        self.assertEqual(state.ranked_results[0].score, 0.82)
        self.assertEqual(state.intent.category, "Pools")

    def test_empty_results_are_representable(self):
        state = AgentState(
            query="castle in Antarctica",
            intent=SearchIntent(category="Castles", country="Antarctica"),
            raw_results=[],
            ranked_results=[],
            summary="No listings matched.",
            error=None,
        )

        self.assertEqual(state.raw_results, [])
        self.assertEqual(state.ranked_results, [])
        self.assertEqual(state.summary, "No listings matched.")
        self.assertIsNone(state.error)

    def test_summary_and_error_can_be_absent(self):
        state = AgentState(query="show farms")

        self.assertIsNone(state.summary)
        self.assertIsNone(state.error)

    def test_separate_states_do_not_share_result_lists(self):
        first = AgentState(query="one")
        second = AgentState(query="two")
        first.raw_results.append(sample_listing())

        self.assertEqual(second.raw_results, [])


class ExistingDtoImportTests(unittest.TestCase):
    def test_existing_dto_imports_still_construct(self):
        self.assertIs(ListingDTO, ListingDTODirect)

        listing = sample_listing()
        self.assertEqual(listing.title, "Mountainy House")

        filters = SearchFilters(category="Mountains", max_price=5000, limit=10)
        self.assertEqual(filters.category, "Mountains")
        self.assertEqual(filters.limit, 10)

        self.assertEqual(validate_category("pools"), "Pools")
        self.assertTrue(LISTING_CATEGORIES)


if __name__ == "__main__":
    unittest.main()
