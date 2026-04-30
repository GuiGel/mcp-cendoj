"""Tool: search CENDOJ legislation index for norm references."""

from bs4 import BeautifulSoup
from pydantic import ConfigDict, validate_call

from mcp_cendoj.constants import CENDOJ_NORMAS_URL
from mcp_cendoj.http import CendojClient
from mcp_cendoj.models import NormaResult

_NORMAS_BASE: dict[str, str] = {
    'action': 'getNormasList',
    'start': '1',
    'recordsPerPage': '20',
    'maxresults': '0',
    'page': '1',
    'databasematch': 'legislacion',
}
"""Base POST payload for legislation (normas) search requests.

Posted to CENDOJ_NORMAS_URL (``/search/jurisprudencia.action``).
Add the ``TITULO`` field on top with the user's search text::

    data = {**_NORMAS_BASE, 'TITULO': titulo}

Field notes:
    action: Always ``'getNormasList'`` to trigger the legislation endpoint.
    databasematch: Always ``'legislacion'`` (different from jurisprudencia's ``'AN'``).
    TITULO: Field name is ``TITULO`` (the HTML input has ``name="TITULO"`` even
        though its ``id`` is ``searchNormaForm_TEXTNorma``). Verified 2026-04-30
        by inspecting the ``doSearchNorma()`` JS function via Playwright.
"""


def _parse_normas(html: str) -> list[NormaResult]:
    """Parse the getNormasList HTML fragment into NormaResult objects.

    The HTML fragment returned by CENDOJ_NORMAS_URL has this structure::

        <input type="hidden" id="searchNormaForm_totalhitsNorma"
               name="totalhitsNorma" value="20">
        <ul>
          <li class="normaItem level-1">
            <div class="col-xs-1 nopad">
              <label>
                <input type="checkbox" class="normacheck"
                       data-boe="2015/11430"
                       data-title="Real Decreto Legislativo 2/2015...">
              </label>
            </div>
            <div class="col-xs-11 nopad">
              <a href="#" data-boe="2015/11430">Real Decreto Legislativo 2/2015...</a>
            </div>
          </li>
          ...
        </ul>

    The ``data-boe`` attribute is the BOE reference ID used as ``norma_id``
    in :func:`~mcp_cendoj.tools.search.search_rulings`.
    The ``data-title`` attribute is preferred for the title; the anchor text
    is used as a fallback if ``data-title`` is absent.

    Args:
        html: HTML fragment returned by the CENDOJ getNormasList endpoint.

    Returns:
        List of :class:`~mcp_cendoj.models.NormaResult` objects in document
        order. Items without a ``data-boe`` attribute are silently skipped.
    """
    soup = BeautifulSoup(html, 'lxml')
    results: list[NormaResult] = []
    for item in soup.select('li.normaItem.level-1'):
        chk = item.select_one('input.normacheck')
        if chk is None:
            continue
        boe = str(chk.get('data-boe', '') or '')
        title = str(chk.get('data-title', '') or '')
        # Fallback: link text (HTML entities already decoded by BeautifulSoup)
        if not title:
            link = item.select_one('a[data-boe]')
            title = link.get_text(strip=True) if link else ''
        if boe:
            results.append(NormaResult(norma_id=boe, title=title))
    return results


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
async def search_normas(
    titulo: str,
    client: CendojClient | None = None,
) -> list[NormaResult]:
    """Search the CENDOJ legislation index to look up a norm's BOE reference ID.

    Use this tool to discover the norma_id value (BOE reference such as
    '2015/11430') needed for the norma_id parameter of search_rulings.

    Example workflow:
        norms = await search_normas('estatuto trabajadores')
        # norms[0].norma_id -> '2015/11430'
        # norms[0].title   -> 'Real Decreto Legislativo 2/2015 ...'
        results = await search_rulings('despido', norma_id=norms[0].norma_id)

    Args:
        titulo: Free-text search for the legislation title (e.g. 'estatuto
            trabajadores', 'ley enjuiciamiento civil').
        client: Optional CendojClient instance; creates a fresh one if not given.

    Returns:
        List of NormaResult objects, each with norma_id (BOE reference) and title.

    Raises:
        CendojNetworkError: On HTTP failures.
    """
    own_client = client is None
    if own_client:
        client = CendojClient()
    try:
        html = await client.post(
            CENDOJ_NORMAS_URL,
            data={**_NORMAS_BASE, 'TITULO': titulo},
        )
    finally:
        if own_client:
            await client.close()
    return _parse_normas(html)
