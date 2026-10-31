"""
Prompts for the property-search workflow.

These prompts only ask the model to structure a query, order retrieved
listings, or summarize those listings. They do not provide property facts.
"""

from ai.schemas.intent import SearchIntent
from ai.schemas.listing_dto import LISTING_CATEGORIES, ListingDTO, RankedListingDTO


def intent_prompt(query: str) -> str:
    categories = ", ".join(LISTING_CATEGORIES)
    return f"""Extract a property-search intent from the user query.

Supported categories, exact spelling only:
{categories}

Rules:
- category must be one of those supported categories, or null. Return a
  supported category only when the user expresses that category, using its
  exact spelling from the list. Otherwise return null.
  "mountain" or "mountains" means Mountains. "pool" or "pools" means Pools.
  Apply the same direct reading to the other names in the list.
  Do not infer a category from part of a word or from shared letters.
- These words are generic search terms, not property categories: property,
  properties, listing, listings, stay, stays, and place. They never fill
  category by themselves. Leave category null when the query uses only those
  words and does not name a supported category.
  "property in Greece" means country Greece and category null.
  "find listings in Goa" means location Goa and category null.
  "any property" means category null.
  Still set country, location, min_price, max_price, and preferences when
  the user states them, whether or not category is null.
- If the user names a type of stay that is not in the list, put their words in
  category. Do not replace them with a different supported category.
  Do not turn a genuine unsupported stay type into null.
- Set min_price or max_price only when the user states a number.
  "under 5000" means max_price 5000. "over 2000" means min_price 2000.
  Prices are nightly amounts in INR. Omit currency symbols.
- Set location or country only when the user names that place.
- Put qualities such as peaceful, quiet, romantic, or great reviews in
  preferences. preferences is always an array of strings. Use [] when the
  user states no qualities. Do not use null for preferences.
  Do not turn those qualities into category, location, or country.
- Leave category, min_price, max_price, location, and country null when the
  user does not state them.
- Do not invent listings, prices, places, or categories.

User query:
{query}
"""


def ranking_prompt(
    query: str,
    intent: SearchIntent,
    listings: list[ListingDTO],
) -> str:
    preference_text = ", ".join(intent.preferences) if intent.preferences else "none"
    blocks = []
    for listing in listings:
        rating = "not stored" if listing.rating is None else f"{listing.rating}"
        reviews = listing.review_count if listing.review_count is not None else 0
        description = listing.description if listing.description else "not stored"
        blocks.append(
            "\n".join(
                [
                    f"id: {listing.id}",
                    f"title: {listing.title}",
                    f"category: {listing.category}",
                    f"price: {listing.price}",
                    f"location: {listing.location}",
                    f"country: {listing.country}",
                    f"rating: {rating}",
                    f"review_count: {reviews}",
                    f"description: {description}",
                ]
            )
        )
    catalog = "\n\n".join(blocks)
    return f"""Rank only the listings below for this search.

User query:
{query}

Preferences, used only as ranking signals:
{preference_text}

Listings:
{catalog}

Rules:
- Return one ranking entry per listing you want to order.
- listing_id must be copied from the id field above.
- Do not add, rename, or alter a listing.
- score must be from 0 to 1. It is a relevance rank, not a probability.
- The reason must use only the title, description, category, price, location,
  country, rating, and review_count shown above.
- Do not call a stay peaceful, quiet, luxurious, or safe unless those words
  are supported by its title or description.
- Do not mention reviews or a high rating unless rating and review_count are present.
- If a description or rating is "not stored", say that it is not stored rather
  than guessing.
"""


def summary_prompt(
    query: str,
    ranked: list[RankedListingDTO],
) -> str:
    blocks = []
    for listing in ranked:
        rating = "not stored" if listing.rating is None else str(listing.rating)
        reviews = listing.review_count if listing.review_count is not None else 0
        blocks.append(
            "\n".join(
                [
                    f"id: {listing.id}",
                    f"title: {listing.title}",
                    f"category: {listing.category}",
                    f"price: {listing.price}",
                    f"location: {listing.location}",
                    f"country: {listing.country}",
                    f"rating: {rating}",
                    f"review_count: {reviews}",
                    f"score: {listing.score if listing.score is not None else 'not scored'}",
                    f"reason: {listing.reason or 'not available'}",
                ]
            )
        )
    catalog = "\n\n".join(blocks)
    return f"""Write a short property-search summary in two or three sentences.

User query:
{query}

Ranked listings:
{catalog}

Rules:
- Mention only titles, places, prices, categories, ratings, and reasons shown above.
- Use the title text exactly when you name a property.
- Do not add properties that are not in the list.
- Do not claim a stay is peaceful, luxurious, safe, or highly reviewed unless
  that listing's reason or stored fields support the claim.
- If a rating is "not stored", do not invent one.
"""
