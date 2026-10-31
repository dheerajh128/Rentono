"""
Listing service with read-only database operations.
Provides search, filtering, and rating aggregation for property listings.
"""

import re
from typing import List, Optional, Dict, Any
from bson import ObjectId
from ai.db.client import get_db
from ai.schemas.listing_dto import (
    ListingDTO,
    SearchFilters,
    ImageDTO,
    GeometryDTO,
    validate_category
)


def build_listing_query(filters: SearchFilters) -> Optional[Dict[str, Any]]:
    """
    Build the MongoDB filter for a listing search.

    Returns None when category is set but is not a supported category.
    Callers must treat that as no matches. Dropping the category would
    turn the search into an unfiltered query.

    Location and country are literal, case-insensitive substrings.
    """
    query: Dict[str, Any] = {}

    if filters.category:
        validated_category = validate_category(filters.category)
        if not validated_category:
            return None
        query["category"] = validated_category

    if filters.min_price is not None or filters.max_price is not None:
        price_query: Dict[str, Any] = {}
        if filters.min_price is not None:
            price_query["$gte"] = filters.min_price
        if filters.max_price is not None:
            price_query["$lte"] = filters.max_price
        query["price"] = price_query

    if filters.location:
        query["location"] = {"$regex": re.escape(filters.location), "$options": "i"}

    if filters.country:
        query["country"] = {"$regex": re.escape(filters.country), "$options": "i"}

    return query


async def search_listings(filters: SearchFilters) -> List[ListingDTO]:
    """
    Search listings based on structured filters.
    Returns a list of ListingDTO objects with basic fields (no ratings yet).
    
    Args:
        filters: SearchFilters object with category, price range, location, etc.
    
    Returns:
        List of ListingDTO objects matching the filters
    """
    query = build_listing_query(filters)
    if query is None:
        return []

    db = await get_db()
    listings_collection = db.listings
    
    # Execute query
    cursor = listings_collection.find(query).limit(filters.limit)
    
    # Convert to DTOs
    listings = []
    async for doc in cursor:
        try:
            listing = _doc_to_dto(doc)
            listings.append(listing)
        except Exception as e:
            # Skip invalid documents
            print(f"Warning: Failed to parse listing {doc.get('_id')}: {e}")
            continue
    
    return listings


async def attach_ratings(listings: List[ListingDTO]) -> List[ListingDTO]:
    """
    Attach average ratings and review counts to listings.
    Performs aggregation on the reviews collection.
    
    Args:
        listings: List of ListingDTO objects
    
    Returns:
        Same list with rating and review_count fields populated
    """
    if not listings:
        return listings
    
    db = await get_db()
    reviews_collection = db.reviews
    listings_collection = db.listings
    
    # Get all listing IDs
    listing_ids = [ObjectId(listing.id) for listing in listings]
    
    # Aggregation pipeline to compute average ratings
    # First, get all listings with their reviews populated
    pipeline = [
        {
            "$match": {
                "_id": {"$in": listing_ids}
            }
        },
        {
            "$lookup": {
                "from": "reviews",
                "localField": "reviews",
                "foreignField": "_id",
                "as": "review_docs"
            }
        },
        {
            "$project": {
                "_id": 1,
                "avg_rating": {"$avg": "$review_docs.rating"},
                "review_count": {"$size": "$review_docs"}
            }
        }
    ]
    
    # Execute aggregation
    ratings_map = {}
    async for doc in listings_collection.aggregate(pipeline):
        listing_id = str(doc["_id"])
        ratings_map[listing_id] = {
            "rating": doc.get("avg_rating"),
            "review_count": doc.get("review_count", 0)
        }
    
    # Attach ratings to listings
    for listing in listings:
        if listing.id in ratings_map:
            rating_data = ratings_map[listing.id]
            listing.rating = rating_data["rating"]
            listing.review_count = rating_data["review_count"]
    
    return listings


async def get_listing_by_id(listing_id: str) -> Optional[ListingDTO]:
    """
    Get a single listing by ID.
    
    Args:
        listing_id: MongoDB ObjectId as string
    
    Returns:
        ListingDTO if found, None otherwise
    """
    db = await get_db()
    listings_collection = db.listings
    
    try:
        doc = await listings_collection.find_one({"_id": ObjectId(listing_id)})
        if doc:
            return _doc_to_dto(doc)
        return None
    except Exception as e:
        print(f"Error fetching listing {listing_id}: {e}")
        return None


async def get_all_categories() -> List[str]:
    """
    Get all distinct categories from the database.
    
    Returns:
        List of category names
    """
    db = await get_db()
    listings_collection = db.listings
    
    categories = await listings_collection.distinct("category")
    return sorted(categories)


def _doc_to_dto(doc: Dict[str, Any]) -> ListingDTO:
    """
    Convert a MongoDB document to a ListingDTO.
    
    Args:
        doc: Raw MongoDB document
    
    Returns:
        ListingDTO object
    """
    # Handle image field
    image_data = doc.get("image", {})
    if isinstance(image_data, dict):
        image = ImageDTO(
            url=image_data.get("url", ""),
            filename=image_data.get("filename")
        )
    else:
        # Fallback for invalid image data
        image = ImageDTO(url="")
    
    # Handle geometry field
    geometry = None
    if "geometry" in doc and doc["geometry"]:
        geo_data = doc["geometry"]
        if isinstance(geo_data, dict) and "coordinates" in geo_data:
            geometry = GeometryDTO(
                type=geo_data.get("type", "Point"),
                coordinates=geo_data["coordinates"]
            )
    
    return ListingDTO(
        _id=str(doc["_id"]),
        title=doc.get("title", ""),
        description=doc.get("description"),
        price=float(doc.get("price", 0)),
        location=doc.get("location", ""),
        country=doc.get("country", ""),
        category=doc.get("category", ""),
        image=image,
        geometry=geometry
    )
