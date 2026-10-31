"""
Optional live smoke test for the property-search graph.

This calls Groq and the shared MongoDB through the real MCP server.
It is not part of the offline unit tests.

From the project root, with GROQ_API_KEY and ATLAS_URL set in the root .env:

    python -m ai.smoke_agent
"""

import asyncio
import sys

from ai.agent.graph import run_search


async def main() -> int:
    query = " ".join(sys.argv[1:]).strip() or (
        "Find me a peaceful mountain stay in India under 5000 with great reviews."
    )
    result = await run_search(query)

    print(f"query: {result.get('query')}")
    intent = result.get("intent")
    print(f"intent: {intent}")
    print(f"error: {result.get('error')}")
    print(f"summary: {result.get('summary')}")
    print()

    ranked = result.get("ranked_results") or []
    if not ranked:
        print("No ranked listings.")
        return 0 if result.get("error") is None else 1

    for listing in ranked:
        score = "unscored" if listing.score is None else f"{listing.score:.2f}"
        print(f"- {listing.title} | {listing.id} | INR {listing.price:.0f} | score {score}")
        print(f"  {listing.location}, {listing.country} | {listing.category}")
        print(f"  {listing.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
