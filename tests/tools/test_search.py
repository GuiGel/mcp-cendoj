"""Tests for the search_rulings tool."""

from collections.abc import Callable
from urllib.parse import parse_qs

import httpx
import pytest
import respx
from pydantic import ValidationError

from mcp_cendoj.constants import CENDOJ_SEARCH_URL, CENDOJ_SESSION_INIT_URL
from mcp_cendoj.http import CendojClient, CendojNetworkError
from mcp_cendoj.tools.search import search_rulings

_RESULT_TEMPLATE = """\
<div class="row searchresult doc" data-ref="{ref}" data-db="TS" data-fechares="20200615">
  <div class="col-xs-12 col-sm-11 content">
    <div class="title">
      <a href="#" data-roj="STS {ref}/2020" data-reference="{ref}" data-databasematch="TS" data-optimize="20200616">
        STS, a 15 de junio de 2020 - ROJ: STS {ref}/2020
      </a>
    </div>
    <div class="metadatos">
      <ul>
        <li><b>ECLI:ES:TS:2020:{ref}</b></li>
        <li>Sala de lo Civil</li>
      </ul>
    </div>
    <div class="summary">Snippet text for ruling {ref}.</div>
  </div>
</div>
"""

_TWO_RESULT_HTML = (
    f'<div class="resultswrapper">{_RESULT_TEMPLATE.format(ref="12345")}{_RESULT_TEMPLATE.format(ref="67890")}</div>'
)
_ZERO_RESULT_HTML = '<div class="resultswrapper"></div>'


async def test_successful_search_returns_results(make_cendoj_client: Callable[..., CendojClient]) -> None:
    client = make_cendoj_client(_TWO_RESULT_HTML)

    results = await search_rulings('tutela judicial', client=client)

    assert len(results) == 2
    assert results[0].ecli == 'ECLI:ES:TS:2020:12345'
    assert results[0].court == 'Sala de lo Civil'
    assert results[0].date == '2020-06-15'
    assert results[0].freshness == 'unknown'
    assert results[1].ecli == 'ECLI:ES:TS:2020:67890'


async def test_empty_results_raises_network_error(make_cendoj_client: Callable[..., CendojClient]) -> None:
    client = make_cendoj_client(_ZERO_RESULT_HTML)

    with pytest.raises(CendojNetworkError, match='No results'):
        await search_rulings('no match query', client=client)


async def test_max_results_clamped_to_cap() -> None:
    captured: dict[str, str] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured.update({k: v[0] for k, v in parse_qs(request.content.decode()).items()})
        return httpx.Response(200, text=_TWO_RESULT_HTML)

    router = respx.Router(assert_all_mocked=True)
    router.get(CENDOJ_SESSION_INIT_URL).respond(200, text='ok')
    router.post(CENDOJ_SEARCH_URL).mock(side_effect=_capture)
    client = CendojClient(transport=httpx.MockTransport(router.async_handler))

    await search_rulings('query', max_results=200, client=client)
    await client.close()

    assert captured.get('recordsPerPage') == '100'


async def test_max_results_zero_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        await search_rulings('query', max_results=0)


async def test_network_error_propagates() -> None:
    def _raise_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout('network failure', request=request)

    router = respx.Router(assert_all_mocked=True)
    router.get(CENDOJ_SESSION_INIT_URL).respond(200, text='ok')
    router.post(CENDOJ_SEARCH_URL).mock(side_effect=_raise_timeout)
    client = CendojClient(transport=httpx.MockTransport(router.async_handler))

    with pytest.raises(CendojNetworkError):
        await search_rulings('query', client=client)
    await client.close()
