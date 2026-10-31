"""
FastMCP Client for testing end-to-end MCP protocol communication.
Tests the full MCP client-server interaction through the protocol.
"""

import asyncio
import json
from fastmcp import Client
from ai.mcp_server import mcp


async def test_mcp_client():
    """
    Test FastMCP client-server communication through the MCP protocol.
    
    Uses in-memory transport for testing (client connects directly to server instance).
    LangGraph will later use this same Client pattern to interact with tools.
    """
    
    print("=" * 60)
    print("  Testing FastMCP Client-Server Communication")
    print("=" * 60)
    print()
    
    # Create client connected to our MCP server (in-memory transport)
    client = Client(mcp)
    
    # All client operations must be within async context manager
    async with client:
        
        # Test 0: Verify connection
        print("[0] Testing connection...")
        try:
            await client.ping()
            print(f"   [OK] Connected to server: {mcp.name}")
            print(f"   Connected status: {client.is_connected()}")
            print()
        except Exception as e:
            print(f"   [ERROR] Connection failed: {e}")
            return False
        
        # Test 1: Discover available tools
        print("[1] Discovering tools via MCP protocol...")
        try:
            tools = await client.list_tools()
            print(f"   [OK] Found {len(tools)} tools:")
            for tool in tools:
                print(f"     - {tool.name}: {tool.description[:60]}...")
            print()
        except Exception as e:
            print(f"   [ERROR] Tool discovery failed: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        # Test 2: Call list_categories through MCP protocol
        print("[2] Calling list_categories() through MCP protocol...")
        try:
            result = await client.call_tool("list_categories", {})
            
            # Parse MCP result: use structured_content if available
            if hasattr(result, 'structured_content') and result.structured_content:
                # FastMCP wraps results in {'result': ...}
                categories = result.structured_content.get('result', result.structured_content)
            elif hasattr(result, 'content') and result.content:
                content_text = result.content[0].text
                categories = json.loads(content_text) if isinstance(content_text, str) else content_text
            else:
                categories = result
            
            print(f"   [OK] Received {len(categories)} categories:")
            for cat in categories:
                print(f"     - {cat}")
            print()
        except Exception as e:
            print(f"   [ERROR] list_categories failed: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        # Test 3: Call search_listings with filters through MCP protocol
        print("[3] Calling search_listings(category='Mountains', max_price=5000) through MCP...")
        try:
            result = await client.call_tool("search_listings", {
                "category": "Mountains",
                "max_price": 5000,
                "limit": 3
            })
            
            # Parse MCP result: use structured_content if available
            if hasattr(result, 'structured_content') and result.structured_content:
                listings = result.structured_content.get('result', result.structured_content)
            elif hasattr(result, 'content') and result.content:
                content_text = result.content[0].text
                listings = json.loads(content_text) if isinstance(content_text, str) else content_text
            else:
                listings = result
            
            # listings should now be a list
            if not isinstance(listings, list):
                print(f"   [ERROR] Expected list, got {type(listings)}: {listings}")
                return False
            
            print(f"   [OK] Received {len(listings)} listings:")
            for listing in listings:
                rating = listing.get('rating', 0)
                rating_str = f"{rating:.1f} stars" if rating else "No reviews"
                print(f"     - {listing['title']}")
                print(f"       Location: {listing['location']}, {listing['country']}")
                print(f"       Price: Rs.{listing['price']:,.0f}/night | Rating: {rating_str}")
            print()
        except Exception as e:
            print(f"   [ERROR] search_listings failed: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        # Test 4: Call search_listings without filters
        print("[4] Calling search_listings(no filters, limit=2) through MCP...")
        try:
            result = await client.call_tool("search_listings", {"limit": 2})
            
            # Parse MCP result
            if hasattr(result, 'structured_content') and result.structured_content:
                listings = result.structured_content.get('result', result.structured_content)
            elif hasattr(result, 'content') and result.content:
                content_text = result.content[0].text
                listings = json.loads(content_text) if isinstance(content_text, str) else content_text
            else:
                listings = result
            
            if not isinstance(listings, list):
                print(f"   [ERROR] Expected list, got {type(listings)}")
                return False
            
            print(f"   [OK] Received {len(listings)} listings:")
            for listing in listings:
                listing_id = listing.get('_id') or listing.get('id', '')
                print(f"     - {listing['title']} (ID: {listing_id[:8]}...)")
            
            # Store first ID for next test
            test_id = (listings[0].get('_id') or listings[0].get('id')) if listings else None
            print()
        except Exception as e:
            print(f"   [ERROR] search_listings failed: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        # Test 5: Call get_listing_by_id through MCP protocol
        if test_id:
            print(f"[5] Calling get_listing_by_id('{test_id[:8]}...') through MCP...")
            try:
                result = await client.call_tool("get_listing_by_id", {
                    "listing_id": test_id
                })
                
                # Parse MCP result
                if hasattr(result, 'structured_content') and result.structured_content:
                    listing = result.structured_content.get('result', result.structured_content)
                elif hasattr(result, 'content') and result.content:
                    content_text = result.content[0].text
                    listing = json.loads(content_text) if isinstance(content_text, str) else content_text
                else:
                    listing = result
                
                if not listing:
                    print(f"   [ERROR] Listing not found")
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
                print(f"   [ERROR] get_listing_by_id failed: {e}")
                import traceback
                traceback.print_exc()
                return False
        else:
            print("[5] Skipping get_listing_by_id (no listings available)")
            print()
    
        print("\n[6] Testing invalid tool...")

        try:
            await client.call_tool("invalid_tool", {})
            print("[FAIL] Invalid tool unexpectedly succeeded")
        except Exception as e:
            print(f"[OK] Invalid tool rejected: {e}")


        print("\n[7] Testing invalid arguments...")

        try:
            await client.call_tool(
                "search_listings",
                {
                    "max_price": "hello"
                }
            )
            print("[FAIL] Invalid arguments unexpectedly accepted")
        except Exception as e:
            print(f"[OK] Validation worked: {e}")
            # Connection closed automatically here
            
        print(f"Connection closed. Is connected: {client.is_connected()}")
        print()
        print("=" * 60)
        print("  [SUCCESS] Full MCP Protocol Communication Working!")
        print("=" * 60)
        print()
    
    return True


async def main():
    """Main test runner."""
    print()
    print("FastMCP Client Test")
    print("=" * 60)
    print("This test uses the FastMCP Client to communicate with the")
    print("MCP server through the proper MCP protocol.")
    print()
    print("Transport: In-memory (client connects directly to server instance)")
    print("Protocol: Model Context Protocol (MCP)")
    print()
    
    try:
        success = await test_mcp_client()
        if not success:
            exit(1)
        
        print()
        print("Next Steps:")
        print("- LangGraph nodes will use this same Client pattern")
        print("- Client automatically handles MCP protocol details")
        print("- Tools are discovered and called through the protocol")
        print("- No direct function imports needed in LangGraph")
        print()
        
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
