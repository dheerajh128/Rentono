# FastMCP Client Usage Guide

## Overview

This guide explains how to use the FastMCP client to interact with the Rentono listing server. The client provides a protocol-compliant way to discover and call MCP tools.

## Basic Usage

### 1. Import and Setup

```python
import asyncio
from fastmcp import Client
from ai.mcp_server import mcp

# Create client with in-memory transport
client = Client(mcp)
```

### 2. Connect and Use Tools

```python
async def example():
    # Must use async context manager
    async with client:
        # Verify connection
        await client.ping()
        print(f"Connected: {client.is_connected()}")
        
        # Discover available tools
        tools = await client.list_tools()
        for tool in tools:
            print(f"Tool: {tool.name}")
        
        # Call a tool
        result = await client.call_tool("list_categories", {})
        categories = result.structured_content.get('result', [])
        print(categories)
    
    # Connection closed automatically
    print(f"Connected: {client.is_connected()}")  # False

asyncio.run(example())
```

## Result Parsing

FastMCP returns `CallToolResult` objects. The actual data is in `structured_content['result']`:

```python
result = await client.call_tool("search_listings", {"limit": 5})

# Extract data
if hasattr(result, 'structured_content') and result.structured_content:
    listings = result.structured_content.get('result', [])
else:
    # Fallback for older versions
    listings = result.content[0].text if result.content else []

for listing in listings:
    print(f"{listing['title']} - Rs.{listing['price']}/night")
```

## Available Tools

### 1. list_categories()

Get all available property categories.

```python
result = await client.call_tool("list_categories", {})
categories = result.structured_content['result']
# ['Arctic', 'Camping', 'Castles', 'Farms', ...]
```

**Parameters:** None  
**Returns:** `List[str]` - Alphabetically sorted category names

### 2. search_listings(...)

Search property listings with optional filters.

```python
result = await client.call_tool("search_listings", {
    "category": "Mountains",
    "min_price": 1000,
    "max_price": 5000,
    "location": "Goa",
    "country": "India",
    "limit": 10
})
listings = result.structured_content['result']
```

**Parameters:**
- `category` (optional): Filter by category (case-insensitive)
- `min_price` (optional): Minimum price per night (₹)
- `max_price` (optional): Maximum price per night (₹)
- `location` (optional): Location search (partial match)
- `country` (optional): Country search (partial match)
- `limit` (default: 10, max: 50): Maximum results

**Returns:** `List[dict]` - List of listings with these fields:
```python
{
    '_id': '507f1f77bcf86cd799439011',
    'title': 'Beach Villa',
    'description': 'Beautiful beachfront property...',
    'price': 3500,
    'location': 'Goa',
    'country': 'India',
    'category': 'Pools',
    'image': {'url': '...', 'filename': '...'},
    'rating': 4.5,
    'review_count': 12
}
```

### 3. get_listing_by_id(listing_id)

Get detailed information for a specific listing.

```python
result = await client.call_tool("get_listing_by_id", {
    "listing_id": "507f1f77bcf86cd799439011"
})
listing = result.structured_content['result']
```

**Parameters:**
- `listing_id`: MongoDB ObjectId (24-character hex string)

**Returns:** `dict` with full listing details, or `None` if not found

## Transport Options

### In-Memory (Current)

Best for testing and single-process apps. Server runs in the same process.

```python
from ai.mcp_server import mcp
client = Client(mcp)
```

**Pros:**
- Fast (no network overhead)
- Simple setup
- Shared memory space
- Perfect for LangGraph integration

**Cons:**
- Server must be in same Python process
- Cannot scale horizontally

### STDIO (Subprocess)

Run server as a separate subprocess. Client communicates via stdin/stdout.

```python
client = Client("ai/mcp_server/server.py")
```

**Pros:**
- Process isolation
- Server can be in different Python environment
- Language-agnostic (any MCP-compliant server)

**Cons:**
- Subprocess management overhead
- Slightly slower than in-memory

### HTTP (Remote)

Connect to a remote MCP server over HTTP.

```python
client = Client("https://api.example.com/mcp")
```

**Pros:**
- True client-server architecture
- Horizontal scaling
- Network-accessible
- Load balancing support

**Cons:**
- Network latency
- Requires HTTP server setup
- Authentication complexity

## Error Handling

```python
async with client:
    try:
        result = await client.call_tool("search_listings", {
            "category": "InvalidCategory",
            "limit": 5
        })
        
        # Check for errors
        if hasattr(result, 'is_error') and result.is_error:
            print(f"Tool error: {result.content}")
        else:
            listings = result.structured_content.get('result', [])
            print(f"Found {len(listings)} listings")
            
    except Exception as e:
        print(f"Client error: {e}")
```

## Connection Lifecycle

```python
# ✅ CORRECT: Use async context manager
async with client:
    await client.ping()
    # All operations here
# Connection auto-closed

# ❌ WRONG: Operations outside context
client = Client(mcp)
await client.ping()  # Will fail - not connected
```

The `async with` statement:
1. Establishes connection
2. Performs protocol handshake
3. Exchanges capabilities
4. Makes client ready for operations
5. Automatically closes on exit

## Complete Example

```python
import asyncio
from fastmcp import Client
from ai.mcp_server import mcp


async def search_mountain_properties():
    """Search for affordable mountain properties."""
    
    client = Client(mcp)
    
    async with client:
        # Check connection
        await client.ping()
        print("Connected to Rentono listing server")
        
        # Search for properties
        result = await client.call_tool("search_listings", {
            "category": "Mountains",
            "max_price": 5000,
            "country": "India",
            "limit": 5
        })
        
        listings = result.structured_content.get('result', [])
        
        if not listings:
            print("No properties found matching criteria")
            return
        
        print(f"\nFound {len(listings)} mountain properties under ₹5000:\n")
        
        for i, listing in enumerate(listings, 1):
            rating = listing.get('rating', 0)
            rating_str = f"{rating:.1f}★" if rating else "No reviews"
            
            print(f"{i}. {listing['title']}")
            print(f"   Location: {listing['location']}, {listing['country']}")
            print(f"   Price: ₹{listing['price']:,.0f}/night")
            print(f"   Rating: {rating_str} ({listing.get('review_count', 0)} reviews)")
            print()
        
        # Get details for first listing
        if listings:
            first_id = listings[0]['_id']
            result = await client.call_tool("get_listing_by_id", {
                "listing_id": first_id
            })
            
            details = result.structured_content.get('result')
            if details:
                print(f"\nDetails for '{details['title']}':")
                print(f"Description: {details['description'][:100]}...")
                print(f"Category: {details['category']}")


if __name__ == "__main__":
    asyncio.run(search_mountain_properties())
```

## Testing

Run the included test suite:

```bash
cd "d:\Web Dev\Major Project"
python -m ai.test_mcp_client
```

This tests all tools and validates the MCP protocol communication.

## For LangGraph Integration

When building LangGraph nodes, use the client like this:

```python
from langgraph.graph import StateGraph
from fastmcp import Client
from ai.mcp_server import mcp

async def search_node(state):
    """LangGraph node that searches listings via MCP."""
    
    client = Client(mcp)
    
    async with client:
        result = await client.call_tool("search_listings", {
            "category": state["intent"].category,
            "max_price": state["intent"].max_price,
            "limit": 10
        })
        
        listings = result.structured_content.get('result', [])
        
        return {
            **state,
            "raw_results": listings
        }
```

## Troubleshooting

### "Client not connected" error

**Problem:** Trying to use client outside `async with` block.

**Solution:** Always use the async context manager:
```python
async with client:
    # All operations here
```

### Empty results from tools

**Problem:** `result.structured_content` is empty or missing.

**Solution:** Check for errors and use fallback parsing:
```python
if hasattr(result, 'structured_content'):
    data = result.structured_content.get('result', [])
elif hasattr(result, 'content') and result.content:
    data = json.loads(result.content[0].text)
else:
    data = []
```

### Tool not found

**Problem:** `call_tool` raises "tool not found" error.

**Solution:** List available tools first:
```python
tools = await client.list_tools()
print([t.name for t in tools])
```

## Next Steps

- See `test_mcp_client.py` for complete examples
- Read `PHASE2_COMPLETE.md` for architectural overview
- Check `FASTMCP_MIGRATION.md` for migration details
