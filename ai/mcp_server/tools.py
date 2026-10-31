"""
MCP tools implementation using FastMCP 3.x decorators.
Thin wrappers over the services layer - no business logic duplication.
"""

from typing import List, Optional
from ai.mcp_server.server import mcp
from ai.services.listing_service import (
    search_listings as service_search_listings,
    get_listing_by_id as service_get_listing_by_id,
    get_all_categories as service_get_all_categories,
    attach_ratings as service_attach_ratings,
)
from ai.schemas.listing_dto import SearchFilters, ListingDTO


@mcp.tool()
async def list_categories() -> List[str]:
    """
    Get all available property categories.
    
    Returns a list of category names that can be used for filtering listings.
    Categories include: Rooms, Iconic Cities, Mountains, Castles, Pools, Camping, Farms, Arctic.
    
    Returns:
        List[str]: Available category names sorted alphabetically
    
    Example:
        >>> categories = await list_categories()
        >>> print(categories)
        ['Arctic', 'Camping', 'Castles', ...]
    """
    return await service_get_all_categories()


@mcp.tool()
async def search_listings(
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    location: Optional[str] = None,
    country: Optional[str] = None,
    limit: int = 10
) -> List[dict]:
    """
    Search property listings based on filters.
    
    Searches the database for property listings matching the specified criteria.
    All filters are optional - if no filters are provided, returns the first `limit` listings.
    
    Args:
        category: Filter by category (e.g., "Mountains", "Pools"). Case-insensitive.
        min_price: Minimum price per night in ₹ (Indian Rupees)
        max_price: Maximum price per night in ₹
        location: Search in location field (case-insensitive partial match)
        country: Search in country field (case-insensitive partial match)
        limit: Maximum number of results to return (default: 10, max: 50)
    
    Returns:
        List[dict]: List of matching listings with complete fields:
            - _id: Listing MongoDB ObjectId
            - title: Property title
            - description: Property description
            - price: Price per night (₹)
            - location: Location name
            - country: Country name
            - category: Property category
            - image: {url, filename}
            - rating: Average rating (if available)
            - review_count: Number of reviews
    
    Example:
        >>> # Search for mountain properties under ₹5000
        >>> results = await search_listings(category="Mountains", max_price=5000, limit=5)
        >>> for listing in results:
        >>>     print(f"{listing['title']} - ₹{listing['price']}/night")
    """
    # Create filters object
    filters = SearchFilters(
        category=category,
        min_price=min_price,
        max_price=max_price,
        location=location,
        country=country,
        limit=min(limit, 50)  # Cap at 50 for safety
    )
    
    # Call service layer. Ratings stay in the service so the tool does not
    # reimplement the review aggregation.
    listings = await service_search_listings(filters)
    listings = await service_attach_ratings(listings)

    # Convert DTOs to dicts for JSON serialization
    return [listing.model_dump(by_alias=True) for listing in listings]


@mcp.tool()
async def get_listing_by_id(listing_id: str) -> Optional[dict]:
    """
    Get detailed information for a specific listing by ID.
    
    Retrieves complete details for a single property listing by its MongoDB ObjectId.
    
    Args:
        listing_id: MongoDB ObjectId of the listing (24-character hex string)
    
    Returns:
        dict: Listing details with all fields, or None if not found
            - _id: Listing ID
            - title: Property title
            - description: Full property description
            - price: Price per night (₹)
            - location: Location name
            - country: Country name
            - category: Property category
            - image: {url, filename}
            - geometry: {type, coordinates} for map display
            - rating: Average rating
            - review_count: Number of reviews
    
    Example:
        >>> listing = await get_listing_by_id("507f1f77bcf86cd799439011")
        >>> if listing:
        >>>     print(f"{listing['title']} - {listing['location']}")
    """
    # Call service layer
    listing = await service_get_listing_by_id(listing_id)
    
    # Convert DTO to dict, or return None
    if listing:
        return listing.model_dump(by_alias=True)
    return None


__all__ = ["list_categories", "search_listings", "get_listing_by_id"]
