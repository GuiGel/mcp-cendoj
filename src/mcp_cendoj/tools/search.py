"""Tool: search CENDOJ for Spanish court rulings."""

from datetime import UTC, datetime
from typing import Annotated

from bs4 import BeautifulSoup
from pydantic import ConfigDict, Field, validate_call

from mcp_cendoj.constants import (
    CENDOJ_DOCUMENT_URL_TEMPLATE,
    CENDOJ_SEARCH_URL,
    MAX_RESULTS_CAP,
    SEARCH_ACTION_QUERY,
    SEARCH_DATABASE_ALL,
    SEARCH_SORT_DEFAULT,
)
from mcp_cendoj.http import CendojClient, CendojNetworkError
from mcp_cendoj.models import SearchResult


def _parse_search_results(html: str) -> list[SearchResult]:
    """Parse search results from CENDOJ HTML response into SearchResult objects.

    Args:
        html: HTML fragment returned by the CENDOJ search endpoint.

    Returns:
        List of SearchResult objects.
    """
    soup = BeautifulSoup(html, 'lxml')
    results: list[SearchResult] = []
    for result_div in soup.select('div.searchresult.doc'):
        title_link = result_div.select_one('a[data-roj]')
        if not title_link:
            continue

        reference = str(title_link.get('data-reference', '') or '')
        databasematch = str(title_link.get('data-databasematch', '') or '')
        optimize = str(title_link.get('data-optimize', '') or '')
        title = title_link.get_text(strip=True)

        ecli_elem = result_div.select_one('.metadatos ul li b')
        ecli_text: str | None = ecli_elem.get_text(strip=True) if ecli_elem else None

        court_li = result_div.select('.metadatos ul li')
        court = court_li[1].get_text(strip=True) if len(court_li) > 1 else ''

        date_raw = str(result_div.get('data-fechares', '') or '')
        date = f'{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:]}' if len(date_raw) == 8 else date_raw

        snippet_elem = result_div.select_one('.summary')
        snippet = snippet_elem.get_text(strip=True) if snippet_elem else ''

        source_url = CENDOJ_DOCUMENT_URL_TEMPLATE.format(
            databasematch=databasematch,
            reference=reference,
            optimize=optimize,
        )

        results.append(
            SearchResult(
                ecli=ecli_text,
                title=title,
                court=court,
                date=date,
                snippet=snippet,
                url=source_url,
                fetched_at=datetime.now(tz=UTC),
                freshness='unknown',
            )
        )
    return results


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
async def search_rulings(
    query: str,
    max_results: Annotated[int, Field(ge=1)] = 10,
    client: CendojClient | None = None,
) -> list[SearchResult]:
    """Search CENDOJ for Spanish court rulings matching a free-text query.

    Rate limiting: 1 request/second per process. Concurrent Claude Desktop
    sessions (separate processes) are not serialised — each has its own
    rate limiter. Avoid querying this tool at high frequency.

    Terms of Service: Use only for legal research on publicly available rulings.
    This tool does not circumvent authentication or access controls.

    Freshness: Results include a provenance envelope with fetched_at timestamp
    and freshness='unknown'. CENDOJ does not expose document modification dates.

    Args:
        query: Free-text search query for the CENDOJ database.
        max_results: Maximum number of results to return. Values above 100 are
            silently clamped to 100.
        client: Optional CendojClient instance; creates a fresh one if not given.

    Returns:
        List of SearchResult objects, ordered by ruling date descending.

    Raises:
        CendojNetworkError: On HTTP failures or empty result sets.
    """
    max_results = min(max_results, MAX_RESULTS_CAP)

    own_client = client is None
    if own_client:
        client = CendojClient()
    try:
        html = await client.post(
            CENDOJ_SEARCH_URL,
            data={
                'action': SEARCH_ACTION_QUERY,
                'sort': SEARCH_SORT_DEFAULT,
                'recordsPerPage': str(max_results),
                'databasematch': SEARCH_DATABASE_ALL,
                'start': '1',
                'TEXT': query,
            },
        )
    finally:
        if own_client:
            await client.close()

    results = _parse_search_results(html)
    if not results:
        raise CendojNetworkError(f'No results returned for query: {query!r}')
    return results
