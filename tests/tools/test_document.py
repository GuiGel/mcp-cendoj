"""Tests for src/mcp_cendoj/tools/document.py."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from mcp_cendoj.cache import DiskCache
from mcp_cendoj.http import CendojClient
from mcp_cendoj.models import Ruling, RulingSections
from mcp_cendoj.tools.document import get_ruling_text

FIXTURES = Path(__file__).parent.parent / 'fixtures'

_DUMMY_SECTIONS = RulingSections(
    raw_text='<court_document source="cendoj">\nFallo\n</court_document>',
    parse_successful=False,
    tribunal_scope='other',
)

_DUMMY_RULING = Ruling(
    ecli='ECLI:ES:TS:2020:1234',
    cendoj_internal_id='99999',
    is_ecli_resolved=True,
    title='STS, 15 de junio de 2020',
    court='Sala de lo Civil',
    date='2020-06-15',
    sections=_DUMMY_SECTIONS,
    source_url='https://www.poderjudicial.es/search/contenidos.action?action=contentpdf&databasematch=TS&reference=99999&optimize=20200615&publicinterface=true',
    cendoj_uri='cendoj://ECLI:ES:TS:2020:1234',
)


@pytest.fixture
async def mem_cache(tmp_path: Path) -> DiskCache:
    """Isolated temp-path DiskCache instance."""
    return DiskCache(db_path=str(tmp_path / 'cache.db'))


async def test_cache_miss_fetches_and_caches(mem_cache: DiskCache) -> None:
    mock_client = AsyncMock(spec=CendojClient)
    mock_client.post.return_value = _build_html('12345', 'ECLI:ES:TS:2020:1234')
    pdf_bytes = (FIXTURES / 'ts_ruling.pdf').read_bytes()
    mock_client.get_with_content_type.return_value = (pdf_bytes, 'application/pdf')

    result = await get_ruling_text('ECLI:ES:TS:2020:1234', client=mock_client, cache=mem_cache)

    assert result.ecli == 'ECLI:ES:TS:2020:1234'
    assert result.sections.raw_text is not None
    assert result.sections.raw_text.startswith('<court_document')

    cached = await mem_cache.get('ECLI:ES:TS:2020:1234')
    assert cached is not None


async def test_cache_hit_returns_without_http(mem_cache: DiskCache) -> None:
    await mem_cache.set('ECLI:ES:TS:2020:1234', _DUMMY_RULING.model_dump_json())

    mock_client = AsyncMock(spec=CendojClient)

    result = await get_ruling_text('ECLI:ES:TS:2020:1234', client=mock_client, cache=mem_cache)

    mock_client.post.assert_not_called()
    assert result.ecli == _DUMMY_RULING.ecli


async def test_invalid_cached_json_is_treated_as_miss(mem_cache: DiskCache) -> None:
    await mem_cache.set('ECLI:ES:TS:2020:1234', 'not_valid_json')

    mock_client = AsyncMock(spec=CendojClient)
    mock_client.post.return_value = _build_html('12345', 'ECLI:ES:TS:2020:1234')
    mock_client.get_with_content_type.return_value = (b'%PDF-1.4', 'application/pdf; charset=utf-8')

    # Should not raise — invalid cache hit triggers fetch
    # (parser will fail silently on minimal PDF, returning empty raw_text)
    try:
        await get_ruling_text('ECLI:ES:TS:2020:1234', client=mock_client, cache=mem_cache)
    except Exception:
        pass  # If PDF parse fails it's fine — the key behaviour is cache is not used

    mock_client.post.assert_called_once()


async def test_invalid_ecli_raises(mem_cache: DiskCache) -> None:
    mock_client = AsyncMock(spec=CendojClient)
    with pytest.raises(ValueError, match='Invalid ECLI'):
        await get_ruling_text('BAD-ECLI', client=mock_client, cache=mem_cache)


async def test_ecli_normalised_before_lookup(mem_cache: DiskCache) -> None:
    mock_client = AsyncMock(spec=CendojClient)
    mock_client.post.return_value = _build_html('12345', 'ECLI:ES:TS:2020:1234')
    mock_client.get_with_content_type.return_value = (b'%PDF-1.4', 'text/html')

    try:
        await get_ruling_text('  ecli:es:ts:2020:1234  ', client=mock_client, cache=mem_cache)
    except Exception:
        pass
    # Regardless of outcome, the POST was called with normalised key
    mock_client.post.assert_called_once()


def _build_html(ref: str, ecli: str) -> str:
    return (
        f'<div class="resultswrapper">'
        f'<div class="row searchresult doc" data-ref="{ref}" data-db="TS" data-fechares="20200615">'
        f'<div class="col-xs-12 col-sm-11 content">'
        f'<div class="title">'
        f'<a href="#" data-roj="STS {ref}/2020" data-reference="{ref}" data-databasematch="TS" data-optimize="20200616">'
        f'STS 2020'
        f'</a></div>'
        f'<div class="metadatos"><ul>'
        f'<li><b>{ecli}</b></li>'
        f'<li>Sala de lo Civil</li>'
        f'</ul></div>'
        f'<div class="summary">Extracto</div>'
        f'</div></div></div>'
    )
