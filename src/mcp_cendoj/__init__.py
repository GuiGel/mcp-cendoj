"""MCP server for the CENDOJ Spanish judicial database."""

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from mcp_cendoj.models import Ruling, SearchResult, SupersededResult
from mcp_cendoj.tools.document import get_ruling_text as _document_impl
from mcp_cendoj.tools.lookup import lookup_by_ecli as _lookup_impl
from mcp_cendoj.tools.search import search_rulings as _search_impl
from mcp_cendoj.tools.superseded import check_if_superseded as _superseded_impl

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


@app.tool()
async def check_if_superseded(ecli: str) -> SupersededResult:
    """Check heuristically whether a ruling has been reversed by a later ruling.

    Searches CENDOJ for rulings that cite *ecli* alongside reversal language.

    Args:
        ecli: The ECLI string identifying the ruling to check.

    Returns:
        A SupersededResult with a mandatory disclaimer warning.
    """
    return await _superseded_impl(ecli)


@app.resource('cendoj://{ecli}')
async def get_ruling_text(ecli: str) -> Ruling:
    """Fetch and cache the full text of a court ruling by ECLI.

    Downloads the ruling PDF from CENDOJ, extracts section text, and caches
    the result for 24 hours.

    Args:
        ecli: The ECLI string identifying the ruling.

    Returns:
        A Ruling with full PDF text extracted into RulingSections.
    """
    return await _document_impl(ecli)


def main() -> None:
    """Entry point for the mcp-cendoj MCP server."""
    app.run()
