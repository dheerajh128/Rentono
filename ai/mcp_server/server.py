"""
FastMCP server instance.
Exposes listing search tools for the LangGraph agent using FastMCP 3.x.
"""

from fastmcp import FastMCP

# Create the FastMCP server instance
mcp = FastMCP(
    name="rentono-listing-server",
    instructions="""
    This server provides property listing search and management tools for the Rentono AI agent.
    
    Available tools:
    - list_categories(): Get all available property categories
    - search_listings(): Search listings with optional filters (category, price, location)
    - get_listing_by_id(): Get detailed information for a specific listing
    """
)

# Tools are registered in tools.py using decorators
__all__ = ["mcp"]
