"""Tests for the search_rulings tool."""

from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

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


async def test_successful_search_returns_results() -> None:
    mock_client = AsyncMock(spec=CendojClient)
    mock_client.post.return_value = _TWO_RESULT_HTML

    results = await search_rulings('tutela judicial', client=mock_client)

    assert len(results) == 2
    assert results[0].ecli == 'ECLI:ES:TS:2020:12345'
    assert results[0].court == 'Sala de lo Civil'
    assert results[0].date == '2020-06-15'
    assert results[0].freshness == 'unknown'
    assert results[1].ecli == 'ECLI:ES:TS:2020:67890'


async def test_empty_results_raises_network_error() -> None:
    mock_client = AsyncMock(spec=CendojClient)
    mock_client.post.return_value = _ZERO_RESULT_HTML

    with pytest.raises(CendojNetworkError, match='No results'):
        await search_rulings('no match query', client=mock_client)


async def test_max_results_clamped_to_cap() -> None:
    mock_client = AsyncMock(spec=CendojClient)
    mock_client.post.return_value = _TWO_RESULT_HTML

    await search_rulings('query', max_results=200, client=mock_client)

    post_call_data: dict[str, str] = mock_client.post.call_args[1]['data']
    assert post_call_data['recordsPerPage'] == '100'


async def test_max_results_zero_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        await search_rulings('query', max_results=0)


async def test_network_error_propagates() -> None:
    mock_client = AsyncMock(spec=CendojClient)
    mock_client.post.side_effect = CendojNetworkError('connection failed')

    with pytest.raises(CendojNetworkError, match='connection failed'):
        await search_rulings('query', client=mock_client)
