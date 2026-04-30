"""Tests for the search_normas tool."""

from urllib.parse import parse_qs

import httpx
import pytest
import respx

from mcp_cendoj.constants import CENDOJ_NORMAS_URL, CENDOJ_SESSION_INIT_URL
from mcp_cendoj.http import CendojClient, CendojNetworkError
from mcp_cendoj.tools.normas import search_normas

_NORMA_ITEM_TEMPLATE = """\
<li class="normaItem level-1">
  <div class="col-xs-1 nopad">
    <label for="chk{n}" class="pull-right check-label c_off small">
      <input type="checkbox" class="normacheck" id="chk{n}"
             data-boe="{boe}" data-title="{title}">
    </label>
  </div>
  <div class="col-xs-11 nopad">
    <a href="#" data-ref="{n}" data-boe="{boe}">{title}</a>
  </div>
  <ul class="hidden" id="normaItem{n}"></ul>
</li>
"""

_TWO_NORMA_HTML = (
    '<input type="hidden" id="searchNormaForm_totalhitsNorma" value="2"><ul>'
    + _NORMA_ITEM_TEMPLATE.format(n=1, boe='2015/11430', title='Real Decreto Legislativo 2/2015, de 23 de octubre.')
    + _NORMA_ITEM_TEMPLATE.format(n=2, boe='1995/7730', title='Real Decreto Legislativo 1/1995, de 24 de marzo.')
    + '</ul>'
)
_EMPTY_NORMA_HTML = '<input type="hidden" value="0"><ul></ul>'


def _make_normas_client(html: str) -> CendojClient:
    def _respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    router = respx.Router(assert_all_mocked=True)
    router.get(CENDOJ_SESSION_INIT_URL).respond(200, text='ok')
    router.post(CENDOJ_NORMAS_URL).mock(side_effect=_respond)
    return CendojClient(transport=httpx.MockTransport(router.async_handler))


async def test_search_normas_returns_norma_results() -> None:
    client = _make_normas_client(_TWO_NORMA_HTML)

    results = await search_normas('estatuto trabajadores', client=client)
    await client.close()

    assert len(results) == 2
    assert results[0].norma_id == '2015/11430'
    assert results[0].title == 'Real Decreto Legislativo 2/2015, de 23 de octubre.'
    assert results[1].norma_id == '1995/7730'


async def test_search_normas_empty_html_returns_empty_list() -> None:
    client = _make_normas_client(_EMPTY_NORMA_HTML)

    results = await search_normas('no match', client=client)
    await client.close()

    assert results == []


async def test_search_normas_sends_correct_form_fields() -> None:
    captured: dict[str, str] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured.update({k: v[0] for k, v in parse_qs(request.content.decode()).items()})
        return httpx.Response(200, text=_TWO_NORMA_HTML)

    router = respx.Router(assert_all_mocked=True)
    router.get(CENDOJ_SESSION_INIT_URL).respond(200, text='ok')
    router.post(CENDOJ_NORMAS_URL).mock(side_effect=_capture)
    client = CendojClient(transport=httpx.MockTransport(router.async_handler))

    await search_normas('estatuto trabajadores', client=client)
    await client.close()

    assert captured['action'] == 'getNormasList'
    assert captured['databasematch'] == 'legislacion'
    assert captured['TITULO'] == 'estatuto trabajadores'


async def test_search_normas_network_error_propagates() -> None:
    def _raise(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout('network failure', request=request)

    router = respx.Router(assert_all_mocked=True)
    router.get(CENDOJ_SESSION_INIT_URL).respond(200, text='ok')
    router.post(CENDOJ_NORMAS_URL).mock(side_effect=_raise)
    client = CendojClient(transport=httpx.MockTransport(router.async_handler))

    with pytest.raises(CendojNetworkError):
        await search_normas('cualquier cosa', client=client)
    await client.close()
