"""
Tests for listing-search filter construction.

These tests do not connect to MongoDB. They check the query the service
builds before it runs.
"""

import unittest

from ai.schemas.listing_dto import SearchFilters
from ai.services.listing_service import build_listing_query, search_listings


class ListingFilterTests(unittest.IsolatedAsyncioTestCase):
    def test_max_price_excludes_higher_prices(self):
        query = build_listing_query(SearchFilters(max_price=5000))

        self.assertEqual(query, {"price": {"$lte": 5000}})

    def test_min_price_excludes_lower_prices(self):
        query = build_listing_query(SearchFilters(min_price=1000))

        self.assertEqual(query, {"price": {"$gte": 1000}})

    def test_price_bounds_are_combined(self):
        query = build_listing_query(SearchFilters(min_price=1000, max_price=5000))

        self.assertEqual(query, {"price": {"$gte": 1000, "$lte": 5000}})

    def test_category_uses_canonical_name(self):
        query = build_listing_query(SearchFilters(category="mountains"))

        self.assertEqual(query["category"], "Mountains")

    def test_location_and_country_are_literal_substrings(self):
        query = build_listing_query(
            SearchFilters(location="South Goa", country="a.b")
        )

        self.assertEqual(query["location"], {"$regex": "South\\ Goa", "$options": "i"})
        self.assertEqual(query["country"], {"$regex": "a\\.b", "$options": "i"})

    def test_unsupported_category_is_not_an_unfiltered_query(self):
        query = build_listing_query(
            SearchFilters(category="Beach", location="Goa", max_price=5000)
        )

        self.assertIsNone(query)

    async def test_unsupported_category_returns_no_listings_without_a_search(self):
        listings = await search_listings(SearchFilters(category="Beach"))

        self.assertEqual(listings, [])


if __name__ == "__main__":
    unittest.main()
