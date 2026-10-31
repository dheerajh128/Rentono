"""
HTTP tests for the property-search API.

The agent is replaced with a fake. These tests do not call Groq or MongoDB.
"""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai.main import app
from ai.schemas.intent import SearchIntent
from ai.schemas.listing_dto import RankedListingDTO


def sample_listing() -> RankedListingDTO:
    return RankedListingDTO(
        _id="69485099aaaaaaaaaaaaaaaa",
        title="Cedar Cabin",
        description="A quiet cabin",
        price=4200,
        location="Manali",
        country="India",
        category="Mountains",
        image={"url": "https://example.com/cabin.jpg", "filename": "cabin.jpg"},
        geometry={"type": "Point", "coordinates": [77.1, 32.2]},
        rating=4.6,
        review_count=8,
        score=0.86,
        reason="The description says it is a quiet cabin.",
    )


class HealthTests(unittest.TestCase):
    def test_health_does_not_call_the_agent(self):
        def forbidden(*args, **kwargs):
            raise AssertionError("health check invoked the agent")

        with patch("ai.main.run_search", forbidden):
            with TestClient(app) as client:
                response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


class SearchApiTests(unittest.TestCase):
    def test_valid_search_calls_run_search_and_serializes_listing(self):
        listing = sample_listing()
        seen = {}

        async def fake_run_search(query, config=None):
            seen["query"] = query
            seen["config"] = config
            return {
                "query": query,
                "intent": SearchIntent(
                    category="Mountains",
                    max_price=5000,
                    country="India",
                    preferences=["peaceful", "great reviews"],
                ),
                "ranked_results": [listing],
                "summary": "Cedar Cabin in Manali is listed at INR 4200 per night.",
                "error": None,
            }

        with patch("ai.main.run_search", fake_run_search):
            with TestClient(app) as client:
                response = client.post(
                    "/ai/search",
                    json={"query": "  peaceful mountain stay in India under 5000  "},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(seen["query"], "peaceful mountain stay in India under 5000")
        self.assertIsNone(seen["config"])
        body = response.json()
        self.assertEqual(body["query"], "peaceful mountain stay in India under 5000")
        self.assertEqual(body["intent"]["category"], "Mountains")
        self.assertEqual(body["intent"]["max_price"], 5000)
        self.assertEqual(body["intent"]["country"], "India")
        self.assertEqual(body["intent"]["preferences"], ["peaceful", "great reviews"])
        self.assertIsNone(body["intent"]["min_price"])
        self.assertIsNone(body["intent"]["location"])
        self.assertIsNone(body["error"])
        result = body["results"][0]
        self.assertEqual(result["_id"], "69485099aaaaaaaaaaaaaaaa")
        self.assertEqual(result["title"], "Cedar Cabin")
        self.assertEqual(result["description"], "A quiet cabin")
        self.assertEqual(result["price"], 4200)
        self.assertEqual(result["location"], "Manali")
        self.assertEqual(result["country"], "India")
        self.assertEqual(result["category"], "Mountains")
        self.assertEqual(result["image"]["url"], "https://example.com/cabin.jpg")
        self.assertEqual(result["image"]["filename"], "cabin.jpg")
        self.assertEqual(result["geometry"]["type"], "Point")
        self.assertEqual(result["geometry"]["coordinates"], [77.1, 32.2])
        self.assertEqual(result["rating"], 4.6)
        self.assertEqual(result["review_count"], 8)
        self.assertEqual(result["score"], 0.86)
        self.assertIn("quiet cabin", result["reason"])

    def test_optional_listing_fields_can_be_null(self):
        listing = RankedListingDTO(
            _id="listing-2",
            title="Plain Room",
            description=None,
            price=1500,
            location="Jaipur",
            country="India",
            category="Rooms",
            image={"url": "https://example.com/room.jpg"},
            geometry=None,
            rating=None,
            review_count=0,
            score=None,
            reason=None,
        )

        async def fake_run_search(query, config=None):
            return {
                "query": query,
                "intent": None,
                "ranked_results": [listing],
                "summary": "Plain Room is listed in Jaipur.",
                "error": None,
            }

        with patch("ai.main.run_search", fake_run_search):
            with TestClient(app) as client:
                response = client.post("/ai/search", json={"query": "any property"})

        result = response.json()["results"][0]
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(result["description"])
        self.assertIsNone(result["geometry"])
        self.assertIsNone(result["rating"])
        self.assertIsNone(result["score"])
        self.assertIsNone(result["reason"])
        self.assertEqual(result["review_count"], 0)
        self.assertIsNone(result["image"]["filename"])

    def test_empty_search_returns_an_empty_list(self):
        async def fake_run_search(query, config=None):
            return {
                "query": query,
                "intent": SearchIntent(category="Mountains", max_price=5000, country="India"),
                "ranked_results": [],
                "summary": "No listings matched this search. No other properties were added.",
                "error": None,
            }

        with patch("ai.main.run_search", fake_run_search):
            with TestClient(app) as client:
                response = client.post(
                    "/ai/search",
                    json={"query": "mountain stay in India under 5000"},
                )

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["results"], [])
        self.assertIn("No listings matched", body["summary"])
        self.assertIsNone(body["error"])
        self.assertEqual(body["intent"]["category"], "Mountains")

    def test_expected_agent_error_is_returned_without_a_traceback(self):
        async def fake_run_search(query, config=None):
            return {
                "query": query,
                "intent": SearchIntent(category="Beach"),
                "ranked_results": [],
                "summary": "Beach is not a supported category, so listings were not searched.",
                "error": "unsupported_category: Beach",
            }

        with patch("ai.main.run_search", fake_run_search):
            with TestClient(app) as client:
                response = client.post("/ai/search", json={"query": "find a beach hut"})

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["error"], "unsupported_category: Beach")
        self.assertEqual(body["results"], [])
        self.assertNotIn("Traceback", response.text)
        self.assertNotIn("gsk_", response.text)

    def test_blank_and_missing_queries_are_rejected(self):
        async def fake_run_search(query, config=None):
            raise AssertionError("invalid query invoked the agent")

        with patch("ai.main.run_search", fake_run_search):
            with TestClient(app) as client:
                blank = client.post("/ai/search", json={"query": "   "})
                missing = client.post("/ai/search", json={})
                too_long = client.post("/ai/search", json={"query": "a" * 501})

        self.assertEqual(blank.status_code, 422)
        self.assertEqual(missing.status_code, 422)
        self.assertEqual(too_long.status_code, 422)
        self.assertNotIn("gsk_", blank.text)

    def test_unexpected_exception_does_not_leak_secrets(self):
        async def fake_run_search(query, config=None):
            raise RuntimeError(
                "boom gsk_testsecretvalue mongodb+srv://user:password@cluster.example"
            )

        with patch("ai.main.run_search", fake_run_search):
            with TestClient(app) as client:
                response = client.post("/ai/search", json={"query": "any property"})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"detail": "The search could not be completed."})
        self.assertNotIn("gsk_testsecretvalue", response.text)
        self.assertNotIn("mongodb", response.text.lower())
        self.assertNotIn("password", response.text)
        self.assertNotIn("Traceback", response.text)
        self.assertNotIn("boom", response.text)


if __name__ == "__main__":
    unittest.main()
