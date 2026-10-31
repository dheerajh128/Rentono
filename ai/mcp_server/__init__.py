"""
FastMCP tool server.
Exposes listing search tools for the LangGraph agent using FastMCP 3.x.
"""

from ai.mcp_server.server import mcp
from ai.mcp_server import tools  # Import to register tools

__all__ = ["mcp"]
