"""
CLI entry point for the Smart Property Search Agent.
Used for development and testing of the LangGraph workflow.

Usage:
    python -m ai.run_agent
    python -m ai.run_agent "peaceful mountain stay under ₹5000 for a honeymoon"
"""

import sys
import asyncio
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai.config import get_settings, validate_config


def print_banner():
    """Print a welcome banner."""
    print("=" * 60)
    print("  Rentono AI - Smart Property Search Agent")
    print("=" * 60)
    print()


def verify_configuration():
    """Verify that configuration is loaded correctly."""
    print("🔧 Verifying configuration...")
    print()
    
    try:
        validate_config()
        settings = get_settings()
        
        print("✓ Configuration loaded successfully!")
        print(f"  • MongoDB: {settings.ATLAS_URL[:30]}...")
        print(f"  • Groq API Key: {'*' * 20} (present)")
        print(f"  • AI Service Port: {settings.AI_PORT}")
        print(f"  • Environment: {settings.NODE_ENV}")
        print()
        
        return True
    except Exception as e:
        print(f"✗ Configuration verification failed!")
        print(f"  Error: {e}")
        print()
        print("Please ensure the following are set in the root .env file:")
        print("  - ATLAS_URL (MongoDB connection string)")
        print("  - GROQ_API_KEY (Groq API key)")
        print()
        return False


async def test_phase1():
    """Test Phase 1: Database connection and services."""
    from ai.db.client import test_connection, MongoClient
    from ai.services.listing_service import search_listings, attach_ratings
    from ai.schemas.listing_dto import SearchFilters
    
    print("📦 Phase 1: Testing database and services...")
    print()
    
    try:
        # Test connection
        print("  → Testing MongoDB connection...")
        await test_connection()
        print("  ✓ Connected to MongoDB successfully")
        print()
        
        # Search for some listings
        print("  → Searching for listings (limit: 3)...")
        filters = SearchFilters(limit=3)
        listings = await search_listings(filters)
        print(f"  ✓ Found {len(listings)} listings")
        print()
        
        # Attach ratings
        print("  → Attaching ratings...")
        listings = await attach_ratings(listings)
        print("  ✓ Ratings attached")
        print()
        
        # Print listings
        print("=" * 60)
        print("  Sample Listings")
        print("=" * 60)
        print()
        
        for i, listing in enumerate(listings, 1):
            print(f"{i}. {listing.title}")
            print(f"   Category: {listing.category}")
            print(f"   Location: {listing.location}, {listing.country}")
            print(f"   Price: ₹{listing.price:,.0f}/night")
            
            if listing.rating:
                print(f"   Rating: {listing.rating:.1f}/5 ({listing.review_count} reviews)")
            else:
                print(f"   Rating: No reviews yet")
            
            print(f"   Image: {listing.image.url[:50]}...")
            print()
        
        # Close connection
        await MongoClient.close()
        
        return True
        
    except Exception as e:
        print(f"  ✗ Phase 1 test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main entry point for the agent runner."""
    print_banner()
    
    # Phase 0: Verify configuration
    if not verify_configuration():
        sys.exit(1)
    
    print("✓ Phase 0 complete: Configuration verified")
    print()
    
    # Phase 1: Test database and services
    try:
        success = asyncio.run(test_phase1())
        if success:
            print("✓ Phase 1 complete: Database and services working")
            print()
        else:
            print("✗ Phase 1 failed")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Error running Phase 1 test: {e}")
        sys.exit(1)
    
    print("Next phases:")
    print("  Phase 2: FastMCP tool server")
    print("  Phase 3: LangGraph agent workflow")
    print("  Phase 4: FastAPI HTTP endpoint")
    print("  Phase 5: Node.js integration")
    print()
    
    # Check if a query was provided (for future phases)
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        print(f"📝 Query received: \"{query}\"")
        print("   (Agent workflow not yet implemented)")
        print()


if __name__ == "__main__":
    main()
