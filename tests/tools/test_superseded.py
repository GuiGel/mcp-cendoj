"""Tests for src/mcp_cendoj/tools/superseded.py."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from mcp_cendoj.http import CendojClient, CendojNetworkError
from mcp_cendoj.models import SearchResult
from mcp_cendoj.tools.superseded import check_if_superseded


def _make_result(ecli: str | None, snippet: str) -> SearchResult:
    return SearchResult(
        ecli=ecli,
        title='Test ruling',
        court='TS',
        date='2024-01-01',
        snippet=snippet,
        url='https://example.com',
        fetched_at=datetime.now(tz=UTC),
    )


async def test_no_results_returns_not_superseded() -> None:
    mock_client = AsyncMock(spec=CendojClient)
    mock_client.post.return_value = '<div class="resultswrapper"></div>'

    result = await check_if_superseded('ECLI:ES:TS:2020:1234', client=mock_client)

    assert result.is_likely_superseded is False
    assert result.citations_found == 0
    assert result.later_rulings == []
    assert result.search_method == 'ecli_fulltext'
    assert result.confidence == 'medium'
    assert result.warning != ''


async def test_reversal_language_triggers_superseded() -> None:
    from unittest.mock import patch

    hit = _make_result('ECLI:ES:TS:2024:9999', 'La Sala revoca la sentencia de instancia.')

    with patch('mcp_cendoj.tools.superseded.search_rulings', return_value=[hit]):
        result = await check_if_superseded('ECLI:ES:TS:2020:1234')

    assert result.is_likely_superseded is True
    assert result.citations_found == 1


async def test_self_reference_excluded() -> None:
    from unittest.mock import patch

    self_ref = _make_result('ECLI:ES:TS:2020:1234', 'Se refiere a sí misma.')
    other = _make_result('ECLI:ES:TS:2024:9999', 'No hay revocación.')

    with patch('mcp_cendoj.tools.superseded.search_rulings', return_value=[self_ref, other]):
        result = await check_if_superseded('ECLI:ES:TS:2020:1234')

    assert result.citations_found == 1
    assert result.later_rulings[0].ecli == 'ECLI:ES:TS:2024:9999'


async def test_no_reversal_language_not_superseded() -> None:
    from unittest.mock import patch

    neutral = _make_result('ECLI:ES:TS:2024:9999', 'Se cita la jurisprudencia anterior.')

    with patch('mcp_cendoj.tools.superseded.search_rulings', return_value=[neutral]):
        result = await check_if_superseded('ECLI:ES:TS:2020:1234')

    assert result.is_likely_superseded is False


async def test_invalid_ecli_raises() -> None:
    with pytest.raises(ValueError, match='Invalid ECLI'):
        await check_if_superseded('NOT-AN-ECLI')


async def test_network_error_propagates() -> None:
    mock_client = AsyncMock(spec=CendojClient)
    mock_client.post.side_effect = CendojNetworkError('timeout')

    with pytest.raises(CendojNetworkError):
        await check_if_superseded('ECLI:ES:TS:2020:1234', client=mock_client)
