"""
Test script for the FastMCP server.
Verifies that all MCP tools can be called successfully using FastMCP 3.x.
"""

import asyncio
import json
from ai.mcp_server import mcp
from ai.mcp_server.tools import list_categories, search_listings, get_listing_by_id


async def test_mcp_tools():
    """Test all MCP tools to verify they work correctly."""
    
    print("=" * 60)
    print("  Testing FastMCP 3.x Server - Rentono Listing Tools")
    print("=" * 60)
    print()
    
    # Test 1: list_categories
    print("[1] Testing list_categories()...")
    try:
        categories = await list_categories()
        print(f"   [OK] Found {len(categories)} categories:")
        for cat in categories:
            print(f"     - {cat}")
        print()
    except Exception as e:
        print(f"   [ERROR] {e}")
        import traceback
        traceback.print_exc()
        print()
        return False
    
    # Test 2: search_listings (with filters)
    print("[2] Testing search_listings(category='Mountains', max_price=5000)...")
    try:
        listings = await search_listings(
            category="Mountains",
            max_price=5000,
            limit=3
        )
        print(f"   [OK] Found {len(listings)} listings:")
        for listing in listings:
            rating = listing.get('rating', 0)
            rating_str = f"{rating:.1f} stars" if rating else "No reviews"
            print(f"     - {listing['title']}")
            print(f"       Location: {listing['location']}, {listing['country']}")
            print(f"       Price: Rs.{listing['price']:,.0f}/night | Rating: {rating_str}")
        print()
    except Exception as e:
        print(f"   [ERROR] {e}")
        import traceback
        traceback.print_exc()
        print()
        return False
    
    # Test 3: search_listings (no filters - get any 2 listings)
    print("[3] Testing search_listings(no filters, limit=2)...")
    try:
        listings = await search_listings(limit=2)
        print(f"   [OK] Found {len(listings)} listings:")
        for listing in listings:
            listing_id = listing.get('_id') or listing.get('id', '')
            print(f"     - {listing['title']} (ID: {listing_id[:8]}...)")
        
        # Store first ID for next test
        test_id = (listings[0].get('_id') or listings[0].get('id')) if listings else None
        print()
    except Exception as e:
        print(f"   [ERROR] {e}")
        import traceback
        traceback.print_exc()
        print()
        return False
    
    # Test 4: get_listing_by_id
    if test_id:
        print(f"[4] Testing get_listing_by_id('{test_id[:8]}...')...")
        try:
            listing = await get_listing_by_id(test_id)
            
            if not listing:
                print(f"   [ERROR] Listing not found")
                print()
                return False
            
            print(f"   [OK] Retrieved listing:")
            print(f"     Title: {listing['title']}")
            print(f"     Category: {listing['category']}")
            print(f"     Location: {listing['location']}, {listing['country']}")
            print(f"     Price: Rs.{listing['price']:,.0f}/night")
            if listing.get('description'):
                desc = listing['description'][:100] + "..." if len(listing['description']) > 100 else listing['description']
                print(f"     Description: {desc}")
            print()
        except Exception as e:
            print(f"   [ERROR] {e}")
            import traceback
            traceback.print_exc()
            print()
            return False
    else:
        print("[4] Skipping get_listing_by_id (no listings available)")
        print()
    
    # Test 5: Verify tools are registered with FastMCP server
    print("[5] Verifying FastMCP server configuration...")
    try:
        # Check that the server has tools registered
        tool_count = len(mcp._tools) if hasattr(mcp, '_tools') else 0
        print(f"   [OK] FastMCP server has {tool_count} tools registered")
        print(f"   Server name: {mcp.name}")
        if hasattr(mcp, 'instructions') and mcp.instructions:
            instr_preview = mcp.instructions.strip()[:80] + "..."
            print(f"   Instructions: {instr_preview}")
        print()
    except Exception as e:
        print(f"   [ERROR] {e}")
        print()
        return False
    
    print("=" * 60)
    print("  [SUCCESS] All FastMCP Tools Working!")
    print("=" * 60)
    print()
    
    return True


async def main():
    """Main test runner."""
    try:
        success = await test_mcp_tools()
        if not success:
            exit(1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        exit(0)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())
