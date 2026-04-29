"""Tool: lookup a Spanish court ruling by ECLI identifier."""

import re
from datetime import UTC, datetime

from bs4 import BeautifulSoup

from mcp_cendoj.constants import (
    CENDOJ_DOCUMENT_URL_TEMPLATE,
    CENDOJ_SEARCH_URL,
    SEARCH_ACTION_QUERY,
    SEARCH_DATABASE_ALL,
    SEARCH_SORT_DEFAULT,
)
from mcp_cendoj.http import CendojClient
from mcp_cendoj.models import Ruling, RulingSections

_ECLI_RE = re.compile(r'ECLI:[A-Z]{2}:[A-Z0-9_-]+:[0-9]{4}:[A-Z0-9._-]+')


class ECLINotFoundError(Exception):
    """Raised when no result is returned for the given ECLI."""


class ECLIAmbiguousError(Exception):
    """Raised when the ECLI search returns more than one result."""


def _validate_ecli(ecli: str) -> None:
    """Validate ECLI format strictly.

    Args:
        ecli: The ECLI string to validate (already stripped/uppercased).

    Raises:
        ValueError: If the format does not match the strict ECLI pattern.
    """
    if not re.fullmatch(r'ECLI:[A-Z]{2}:[A-Z0-9_-]+:[0-9]{4}:[A-Z0-9._-]+', ecli):
        raise ValueError(f'Invalid ECLI: {ecli!r}')


def _parse_search_results(html: str) -> list[dict[str, str | None]]:
    """Parse search result items from CENDOJ HTML response.

    Args:
        html: HTML string from the CENDOJ search endpoint.

    Returns:
        List of dicts with keys: ecli, title, court, date, snippet, reference,
        databasematch, optimize, source_url.
    """
    soup = BeautifulSoup(html, 'lxml')
    items: list[dict[str, str | None]] = []
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

        items.append(
            {
                'ecli': ecli_text,
                'title': title,
                'court': court,
                'date': date,
                'snippet': snippet,
                'reference': reference,
                'databasematch': databasematch,
                'optimize': optimize,
                'source_url': source_url,
            }
        )
    return items


async def lookup_by_ecli(ecli: str, client: CendojClient | None = None) -> Ruling:
    """Look up a Spanish court ruling by its ECLI identifier.

    Args:
        ecli: The ECLI string (e.g. 'ECLI:ES:TS:2020:1234').
        client: Optional CendojClient instance; creates a fresh one if not given.

    Returns:
        A Ruling with metadata populated and raw_text from the search snippet.

    Raises:
        ValueError: If the ECLI format is invalid.
        ECLINotFoundError: If no ruling matches the ECLI.
        ECLIAmbiguousError: If more than one result is returned.
        CendojNetworkError: On HTTP failures.
    """
    ecli = ecli.strip().upper()
    _validate_ecli(ecli)

    own_client = client is None
    if own_client:
        client = CendojClient()
    try:
        html = await client.post(
            CENDOJ_SEARCH_URL,
            data={
                'action': SEARCH_ACTION_QUERY,
                'sort': SEARCH_SORT_DEFAULT,
                'recordsPerPage': '10',
                'databasematch': SEARCH_DATABASE_ALL,
                'start': '1',
                'ECLI': ecli,
            },
        )
    finally:
        if own_client:
            await client.close()

    results = _parse_search_results(html)

    if len(results) == 0:
        raise ECLINotFoundError(f'No ruling found for ECLI: {ecli!r}')
    if len(results) > 1:
        raise ECLIAmbiguousError(f'ECLI {ecli!r} matched {len(results)} results; expected exactly 1')

    item = results[0]
    sections = RulingSections(
        raw_text=item['snippet'] or '',
        parse_successful=False,
        tribunal_scope='other',
    )
    cendoj_uri = f'cendoj://{ecli}'
    return Ruling(
        ecli=item['ecli'],
        cendoj_internal_id=item['reference'] or None,
        is_ecli_resolved=True,
        title=str(item['title'] or ''),
        court=str(item['court'] or ''),
        date=str(item['date'] or ''),
        sections=sections,
        source_url=str(item['source_url'] or ''),
        cendoj_uri=cendoj_uri,
        fetched_at=datetime.now(tz=UTC),
        freshness='unknown',
    )
