"""
Search intent extracted from a natural-language property query.

Preferences are ranking signals. They are not database or MCP filters.
The only filters this model carries are the ones search_listings already accepts:
category, min_price, max_price, location, and country.
"""

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from ai.schemas.listing_dto import LISTING_CATEGORIES, validate_category

# Whole search words that are not listing categories. Matching is exact after
# trimming and case folding. A longer phrase is not cleared just because it
# contains one of these words.
GENERIC_SEARCH_TERMS = frozenset(
    {
        "property",
        "properties",
        "listing",
        "listings",
        "stay",
        "stays",
        "place",
    }
)


class SearchIntent(BaseModel):
    """
    Structured property-search intent.

    category is a supported listing category or null. A known value is stored
    with the canonical spelling from LISTING_CATEGORIES. A generic search word
    is cleared to null and does not remove country, location, price, or
    preferences. Any other category text is kept as entered so the search step
    can reject it instead of running without that filter.
    """

    category: Optional[str] = Field(
        default=None,
        description=(
            "A supported listing category copied with its exact spelling, or "
            "null when the query does not express one. Supported categories: "
            + ", ".join(LISTING_CATEGORIES)
            + ". Do not invent a category, and do not use a generic word such "
            "as property, listing, stay, or place."
        ),
    )
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    location: Optional[str] = None
    country: Optional[str] = None
    # Null is accepted because Groq validates the tool call against this schema
    # before Pydantic runs. The validator below stores that as an empty list.
    preferences: Optional[list[str]] = Field(
        default_factory=list,
        json_schema_extra={"default": []},
    )

    @field_validator("category", "location", "country", mode="before")
    @classmethod
    def blank_text_to_none(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            return text or None
        return value

    @field_validator("category")
    @classmethod
    def canonicalize_known_category(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        canonical = validate_category(value)
        if canonical is not None:
            return canonical
        if value.casefold() in GENERIC_SEARCH_TERMS:
            return None
        return value

    @field_validator("min_price", "max_price")
    @classmethod
    def reject_negative_price(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and value < 0:
            raise ValueError("price must be greater than or equal to 0")
        return value

    @field_validator("preferences", mode="before")
    @classmethod
    def normalize_preferences(cls, value: Any) -> Any:
        if value is None:
            return []
        if not isinstance(value, list):
            return value
        cleaned: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("preferences must be a list of strings")
            text = " ".join(item.split())
            if text:
                cleaned.append(text)
        return cleaned

    @model_validator(mode="after")
    def check_price_range(self) -> "SearchIntent":
        if (
            self.min_price is not None
            and self.max_price is not None
            and self.min_price > self.max_price
        ):
            raise ValueError("min_price must not exceed max_price")
        return self

    def supported_category(self) -> Optional[str]:
        """
        Category safe to pass to search_listings, or None if this intent has
        no category or the category is not one the database accepts.
        """
        return validate_category(self.category)
