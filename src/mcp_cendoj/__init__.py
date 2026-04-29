"""MCP server for the CENDOJ Spanish judicial database."""

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from mcp_cendoj.models import Ruling, SearchResult
from mcp_cendoj.tools.lookup import lookup_by_ecli as _lookup_impl
from mcp_cendoj.tools.search import search_rulings as _search_impl

app = FastMCP('mcp-cendoj')


@app.tool()
async def lookup_by_ecli(ecli: str) -> Ruling:
    """Look up a Spanish court ruling by its ECLI identifier.

    Args:
        ecli: The ECLI string (e.g. 'ECLI:ES:TS:2020:1234').

    Returns:
        A Ruling with metadata and snippet text.
    """
    return await _lookup_impl(ecli)


@app.tool()
async def search_rulings(
    query: str,
    max_results: Annotated[int, Field(ge=1, le=100)] = 10,
) -> list[SearchResult]:
    """Search CENDOJ for Spanish court rulings matching a free-text query.

    Args:
        query: Free-text search query.
        max_results: Maximum number of results (1–100).

    Returns:
        List of SearchResult objects ordered by ruling date descending.
    """
    return await _search_impl(query, max_results)


def main() -> None:
    """Entry point for the mcp-cendoj MCP server."""
    app.run()
