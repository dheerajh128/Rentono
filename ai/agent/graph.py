"""
Compiled LangGraph workflow for smart property search.

Importing this module does not connect to Groq or MongoDB and does not run a search.
Call build_search_graph() and then ainvoke when a query should be executed.
"""

from typing import Optional

from langgraph.graph import END, StateGraph

from ai.agent.nodes import (
    explain_results,
    parse_intent,
    rank_listings,
    retrieve_candidates,
    route_after_parse,
    route_after_retrieve,
)
from ai.agent.state import AgentState


def build_search_graph():
    """
    Compile parse -> retrieve -> rank -> explain.

    An intent error, an MCP error, an unsupported category, or an empty
    candidate list skips ranking and goes to the explanation node.
    """
    graph = StateGraph(AgentState)
    graph.add_node("parse_intent", parse_intent)
    graph.add_node("retrieve_candidates", retrieve_candidates)
    graph.add_node("rank_listings", rank_listings)
    graph.add_node("explain_results", explain_results)
    graph.set_entry_point("parse_intent")
    graph.add_conditional_edges(
        "parse_intent",
        route_after_parse,
        {
            "retrieve_candidates": "retrieve_candidates",
            "explain_results": "explain_results",
        },
    )
    graph.add_conditional_edges(
        "retrieve_candidates",
        route_after_retrieve,
        {
            "rank_listings": "rank_listings",
            "explain_results": "explain_results",
        },
    )
    graph.add_edge("rank_listings", "explain_results")
    graph.add_edge("explain_results", END)
    return graph.compile()


async def run_search(query: str, config: Optional[dict] = None) -> dict:
    """Run one natural-language search. Used by callers and the smoke script."""
    graph = build_search_graph()
    return await graph.ainvoke({"query": query}, config)
