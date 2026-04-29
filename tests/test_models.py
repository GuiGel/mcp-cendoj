from datetime import UTC

import pytest

from mcp_cendoj.models import Ruling, RulingSections, SearchResult, SupersededResult

# ---------------------------------------------------------------------------
# RulingSections
# ---------------------------------------------------------------------------


def test_ruling_sections_defaults() -> None:
    sections = RulingSections(raw_text='texto')
    assert sections.antecedentes is None
    assert sections.fundamentos_derecho is None
    assert sections.fallo is None
    assert sections.parse_successful is False
    assert sections.tribunal_scope == 'other'


def test_ruling_sections_tribunal_scope_values() -> None:
    s1 = RulingSections(raw_text='x', tribunal_scope='ts_tc')
    assert s1.tribunal_scope == 'ts_tc'
    s2 = RulingSections(raw_text='x', tribunal_scope='other')
    assert s2.tribunal_scope == 'other'


def test_ruling_sections_tribunal_scope_invalid() -> None:
    with pytest.raises(Exception):
        RulingSections(raw_text='x', tribunal_scope='invalid')  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Ruling
# ---------------------------------------------------------------------------


def test_ruling_freshness_always_unknown() -> None:
    sections = RulingSections(raw_text='texto')
    ruling = Ruling(
        ecli='ECLI:ES:TS:2020:1234',
        cendoj_internal_id='12345',
        is_ecli_resolved=True,
        title='STS 1234/2020',
        court='Tribunal Supremo',
        date='2020-06-15',
        sections=sections,
        source_url='https://example.com/ruling',
        cendoj_uri='cendoj://TS/2020/1234',
    )
    assert ruling.freshness == 'unknown'


def test_ruling_fetched_at_is_utc() -> None:
    sections = RulingSections(raw_text='texto')
    ruling = Ruling(
        ecli=None,
        cendoj_internal_id=None,
        is_ecli_resolved=False,
        title='Auto',
        court='TSJ Madrid',
        date='2021-01-01',
        sections=sections,
        source_url='https://example.com',
        cendoj_uri='cendoj://TSJ/2021/1',
    )
    assert ruling.fetched_at.tzinfo is not None
    assert ruling.fetched_at.tzinfo == UTC


def test_ruling_cendoj_uri_field_exists() -> None:
    sections = RulingSections(raw_text='x')
    ruling = Ruling(
        ecli=None,
        cendoj_internal_id=None,
        is_ecli_resolved=False,
        title='T',
        court='C',
        date='2022-01-01',
        sections=sections,
        source_url='https://example.com',
        cendoj_uri='cendoj://X/2022/1',
    )
    assert ruling.cendoj_uri == 'cendoj://X/2022/1'


# ---------------------------------------------------------------------------
# SearchResult
# ---------------------------------------------------------------------------


def test_search_result_freshness_always_unknown() -> None:
    sr = SearchResult(
        ecli='ECLI:ES:TS:2021:5678',
        title='STS 5678/2021',
        court='Tribunal Supremo',
        date='2021-03-10',
        snippet='texto recortado',
        url='https://example.com/sr',
    )
    assert sr.freshness == 'unknown'


def test_search_result_fetched_at_is_utc() -> None:
    sr = SearchResult(
        ecli=None,
        title='T',
        court='C',
        date='2021-01-01',
        snippet='s',
        url='https://example.com',
    )
    assert sr.fetched_at.tzinfo is not None
    assert sr.fetched_at.tzinfo == UTC


# ---------------------------------------------------------------------------
# SupersededResult
# ---------------------------------------------------------------------------


def test_superseded_result_confidence_always_medium() -> None:
    result = SupersededResult(
        checked_ecli='ECLI:ES:TS:2020:1234',
        later_rulings=[],
        citations_found=0,
        is_likely_superseded=False,
        search_method='ecli_fulltext',
    )
    assert result.confidence == 'medium'


def test_superseded_result_warning_non_empty() -> None:
    result = SupersededResult(
        checked_ecli='ECLI:ES:TS:2020:1234',
        later_rulings=[],
        citations_found=0,
        is_likely_superseded=False,
        search_method='ecli_fulltext',
    )
    assert isinstance(result.warning, str)
    assert len(result.warning) > 0


def test_superseded_result_is_likely_superseded_is_bool() -> None:
    r_true = SupersededResult(
        checked_ecli='ECLI:ES:TS:2020:1234',
        later_rulings=[],
        citations_found=1,
        is_likely_superseded=True,
        search_method='ecli_fulltext',
    )
    r_false = SupersededResult(
        checked_ecli='ECLI:ES:TS:2020:1234',
        later_rulings=[],
        citations_found=0,
        is_likely_superseded=False,
        search_method='ecli_fulltext',
    )
    assert isinstance(r_true.is_likely_superseded, bool)
    assert isinstance(r_false.is_likely_superseded, bool)
    assert r_true.is_likely_superseded is True
    assert r_false.is_likely_superseded is False
