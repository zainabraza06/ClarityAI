"""
Tavily MCP client initialisation.

Uses langchain-mcp-adapters to connect to the Tavily MCP server (via npx stdio transport).
The MCP server is spawned as a subprocess and kept alive for the duration of the FastAPI app.

Prerequisites:
  - Node.js installed (for npx)
  - TAVILY_API_KEY environment variable set
"""

import os
from langchain_mcp_adapters.client import MultiServerMCPClient


def build_mcp_client() -> MultiServerMCPClient:
    """Create a MultiServerMCPClient configured to run the Tavily MCP server."""
    tavily_api_key = os.environ.get("TAVILY_API_KEY", "")
    if not tavily_api_key:
        raise EnvironmentError(
            "TAVILY_API_KEY is not set. Add it to your .env file."
        )

    return MultiServerMCPClient(
        {
            "tavily": {
                "command": "npx",
                "args": ["-y", "tavily-mcp"],
                "transport": "stdio",
                # Pass the API key as an env var to the spawned npx process
                "env": {**os.environ, "TAVILY_API_KEY": tavily_api_key},
            }
        }
    )
