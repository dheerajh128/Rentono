"""
Data Transfer Objects for listings.
Defines the structure of listing data returned by the AI service.
"""

from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime


class ImageDTO(BaseModel):
    """Image information for a listing."""
    url: str
    filename: Optional[str] = None


class GeometryDTO(BaseModel):
    """GeoJSON geometry for location data."""
    type: str = "Point"
    coordinates: List[float]  # [longitude, latitude]


class ListingDTO(BaseModel):
    """
    Lightweight listing object with essential fields.
    Maps to the MongoDB Listing document structure.
    """
    # MongoDB ID (string representation)
    id: str = Field(alias="_id")
    
    # Core listing fields
    title: str
    description: Optional[str] = None
    price: float
    location: str
    country: str
    category: str
    
    # Image
    image: ImageDTO
    
    # Location data (optional, for geo queries)
    geometry: Optional[GeometryDTO] = None
    
    # Computed fields (added by services)
    rating: Optional[float] = None  # Average rating from reviews
    review_count: Optional[int] = 0  # Number of reviews
    
    class Config:
        populate_by_name = True  # Allow both 'id' and '_id'
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class RankedListingDTO(ListingDTO):
    """
    Extended listing with AI ranking information.
    Used after the rank and explain nodes in the agent workflow.
    """
    score: Optional[float] = None  # Ranking score (0-1)
    reason: Optional[str] = None  # Explanation for why this listing was chosen
    
    class Config:
        populate_by_name = True


class SearchFilters(BaseModel):
    """
    Structured filters for listing search.
    Maps to MongoDB query parameters.
    """
    category: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    location: Optional[str] = None  # Regex search
    country: Optional[str] = None  # Regex search
    limit: int = 50  # Max results to return
    
    class Config:
        # Validate category against the enum
        use_enum_values = True


# Category enum matching the Node.js Listing model
LISTING_CATEGORIES = [
    "Rooms",
    "Iconic Cities",
    "Mountains",
    "Castles",
    "Pools",
    "Camping",
    "Farms",
    "Arctic"
]


def validate_category(category: Optional[str]) -> Optional[str]:
    """
    Validate that a category matches the allowed values.
    Returns the category if valid, None if invalid or None.
    """
    if category is None:
        return None
    
    # Case-insensitive match
    for valid_cat in LISTING_CATEGORIES:
        if category.lower() == valid_cat.lower():
            return valid_cat
    
    return None
