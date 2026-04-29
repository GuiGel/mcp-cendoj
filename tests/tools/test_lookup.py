"""Tests for the lookup_by_ecli tool."""

from unittest.mock import AsyncMock

import pytest

from mcp_cendoj.http import CendojClient, CendojNetworkError
from mcp_cendoj.tools.lookup import ECLIAmbiguousError, ECLINotFoundError, lookup_by_ecli

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
    <div class="summary">Tutela judicial efectiva. Derecho a obtener resolución motivada.</div>
  </div>
</div>
"""

_ONE_RESULT_HTML = f'<div class="resultswrapper">{_RESULT_TEMPLATE.format(ref="12345")}</div>'
_TWO_RESULT_HTML = (
    f'<div class="resultswrapper">{_RESULT_TEMPLATE.format(ref="12345")}{_RESULT_TEMPLATE.format(ref="67890")}</div>'
)
_ZERO_RESULT_HTML = '<div class="resultswrapper"></div>'


async def test_successful_lookup_returns_ruling() -> None:
    mock_client = AsyncMock(spec=CendojClient)
    mock_client.post.return_value = _ONE_RESULT_HTML

    result = await lookup_by_ecli('ECLI:ES:TS:2020:1234', client=mock_client)

    assert result.ecli == 'ECLI:ES:TS:2020:12345'
    assert result.cendoj_internal_id == '12345'
    assert result.is_ecli_resolved is True
    assert 'STS' in result.title
    assert result.court == 'Sala de lo Civil'
    assert result.date == '2020-06-15'
    assert result.sections.raw_text == 'Tutela judicial efectiva. Derecho a obtener resolución motivada.'
    assert result.cendoj_uri == 'cendoj://ECLI:ES:TS:2020:1234'
    assert result.freshness == 'unknown'


async def test_not_found_raises_ecli_not_found_error() -> None:
    mock_client = AsyncMock(spec=CendojClient)
    mock_client.post.return_value = _ZERO_RESULT_HTML

    with pytest.raises(ECLINotFoundError, match='ECLI:ES:TS:2020:1234'):
        await lookup_by_ecli('ECLI:ES:TS:2020:1234', client=mock_client)


async def test_ambiguous_raises_ecli_ambiguous_error() -> None:
    mock_client = AsyncMock(spec=CendojClient)
    mock_client.post.return_value = _TWO_RESULT_HTML

    with pytest.raises(ECLIAmbiguousError, match='2 results'):
        await lookup_by_ecli('ECLI:ES:TS:2020:1234', client=mock_client)


async def test_invalid_ecli_format_raises_value_error() -> None:
    with pytest.raises(ValueError, match='Invalid ECLI'):
        await lookup_by_ecli('NOT-AN-ECLI')


async def test_injection_ecli_raises_value_error() -> None:
    with pytest.raises(ValueError, match='Invalid ECLI'):
        await lookup_by_ecli('ECLI:ES:TS:2020:1@evil.com')


async def test_network_error_propagates() -> None:
    mock_client = AsyncMock(spec=CendojClient)
    mock_client.post.side_effect = CendojNetworkError('connection failed')

    with pytest.raises(CendojNetworkError, match='connection failed'):
        await lookup_by_ecli('ECLI:ES:TS:2020:1234', client=mock_client)
