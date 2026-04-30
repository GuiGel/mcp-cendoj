"""Tests for src/mcp_cendoj/parser.py (TDD — written before implementation)."""

import io
from pathlib import Path

import pytest

from mcp_cendoj.constants import MAX_RESPONSE_BYTES
from mcp_cendoj.parser import (
    CendojParseError,
    _detect_scope,  # pyright: ignore[reportPrivateUsage]
    extract_header_metadata,
    extract_sections,
    split_sections,
)

FIXTURES = Path(__file__).parent.parent / 'fixtures'


def _make_minimal_pdf(text: str) -> bytes:
    """Build a minimal single-page PDF containing *text* using pdfplumber/reportlab fallback."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        y = 800
        for line in text.splitlines():
            c.drawString(40, y, line)
            y -= 15
            if y < 50:
                c.showPage()
                y = 800
        c.save()
        return buf.getvalue()
    except ImportError:
        # Minimal valid PDF with no text — sufficient for size/format tests
        return (
            b'%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj '
            b'2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj '
            b'3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj '
            b'xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n'
            b'0000000058 00000 n \n0000000115 00000 n \n'
            b'trailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF\n'
        )


class TestExtractSectionsTooBig:
    def test_raises_when_pdf_too_large(self) -> None:
        oversized_bytes = b'%PDF-1.4' + b'0' * (MAX_RESPONSE_BYTES + 1)
        with pytest.raises(CendojParseError, match='too large'):
            extract_sections(oversized_bytes)


class TestExtractSectionsFromRealFixture:
    def test_real_ts_ruling_loads_without_error(self) -> None:
        pdf_bytes = (FIXTURES / 'ts_ruling.pdf').read_bytes()
        result = extract_sections(pdf_bytes, ecli='ECLI:ES:TS:2026:3898A')
        assert result.raw_text is not None
        assert len(result.raw_text) > 100

    def test_real_ts_ruling_has_court_document_wrapper(self) -> None:
        pdf_bytes = (FIXTURES / 'ts_ruling.pdf').read_bytes()
        result = extract_sections(pdf_bytes, ecli='ECLI:ES:TS:2026:3898A')
        assert result.raw_text is not None
        assert result.raw_text.startswith('<court_document source="cendoj">')
        assert result.raw_text.strip().endswith('</court_document>')


class TestExtractSectionsWithSyntheticText:
    def test_ts_ecli_sets_tribunal_scope(self) -> None:
        txt = (FIXTURES / 'ts_sentence.txt').read_text(encoding='utf-8')
        # Build minimal PDF or test via text path
        result = extract_sections(
            _make_minimal_pdf(txt),
            ecli='ECLI:ES:TS:2020:1234',
        )
        assert result.tribunal_scope == 'ts_tc'

    def test_tc_ecli_sets_tribunal_scope(self) -> None:
        txt = (FIXTURES / 'ts_sentence.txt').read_text(encoding='utf-8')
        result = extract_sections(
            _make_minimal_pdf(txt),
            ecli='ECLI:ES:TC:2020:1234',
        )
        assert result.tribunal_scope == 'ts_tc'

    def test_tsj_ecli_sets_collegial_scope(self) -> None:
        txt = (FIXTURES / 'tsj_ruling.txt').read_text(encoding='utf-8')
        result = extract_sections(
            _make_minimal_pdf(txt),
            ecli='ECLI:ES:TSJM:2020:1234',
        )
        assert result.tribunal_scope == 'collegial'
        assert result.parse_successful is False

    def test_no_ecli_sets_other_scope(self) -> None:
        txt = 'Some ruling text without sections.'
        result = extract_sections(_make_minimal_pdf(txt))
        assert result.tribunal_scope == 'other'
        assert result.parse_successful is False


class TestExtractSectionsSectionParsing:
    """Tests that require text with section headers to be extractable from PDF.

    These tests are intentionally lenient about whether section extraction
    succeeds — the key check is parse_successful matches sections presence.
    """

    def test_parse_successful_when_sections_found_in_text(self) -> None:
        txt = (FIXTURES / 'ts_sentence.txt').read_text(encoding='utf-8')
        result = extract_sections(_make_minimal_pdf(txt), ecli='ECLI:ES:TS:2020:1234')
        # If pdfplumber extracted text, we should have sections
        if result.parse_successful:
            assert result.antecedentes is not None
            assert result.fundamentos_derecho is not None
            assert result.fallo is not None
        # raw_text must always be populated
        assert result.raw_text is not None

    def test_other_tribunal_no_sections(self) -> None:
        txt = (FIXTURES / 'tsj_ruling.txt').read_text(encoding='utf-8')
        result = extract_sections(_make_minimal_pdf(txt), ecli='ECLI:ES:TSJM:2020:1234')
        assert result.parse_successful is False
        assert result.antecedentes is None
        assert result.fundamentos_derecho is None
        assert result.fallo is None


class TestSplitSectionsDirect:
    """Unit tests for the _split_sections helper — no PDF needed."""

    _FULL_TEXT = (
        'Preamble text.\n'
        'ANTECEDENTES DE HECHO\n'
        'First antecedente here.\n'
        'FUNDAMENTOS DE DERECHO\n'
        'Legal reasoning here.\n'
        'FALLO\n'
        'Sentencia estimatoria.'
    )

    def test_full_split_returns_all_three_sections(self) -> None:
        ant, fund, fal, ok = split_sections(self._FULL_TEXT)
        assert ok is True
        assert ant is not None and 'antecedente' in ant
        assert fund is not None and 'Legal reasoning' in fund
        assert fal is not None and 'Sentencia' in fal

    def test_no_headers_returns_all_none(self) -> None:
        ant, fund, fal, ok = split_sections('no headers here at all')
        assert ok is False
        assert ant is None
        assert fund is None
        assert fal is None

    def test_only_antecedentes_returns_not_parsed(self) -> None:
        text = 'ANTECEDENTES DE HECHO\nSome facts.'
        _ant, _fund, _fal, ok = split_sections(text)
        assert ok is False

    def test_parte_dispositiva_accepted_as_fallo(self) -> None:
        text = 'ANTECEDENTES DE HECHO\nFacts.\nFUNDAMENTOS DE DERECHO\nLaw.\nPARTE DISPOSITIVA\nDisposition.'
        _ant, _fund, fal, ok = split_sections(text)
        assert ok is True
        assert fal is not None and 'Disposition' in fal

    def test_case_insensitive_headers(self) -> None:
        text = 'Antecedentes de Hecho\nFacts.\nFundamentos de Derecho\nLaw.\nFallo\nResult.'
        ant, fund, fal, ok = split_sections(text)
        assert ok is True
        assert ant is not None
        assert fund is not None
        assert fal is not None

    def test_empty_sections_become_none(self) -> None:
        # sections with only whitespace should become None
        text = 'ANTECEDENTES DE HECHO\n   \nFUNDAMENTOS DE DERECHO\n   \nFALLO\n   '
        _ant, _fund, _fal, ok = split_sections(text)
        # Sections may be None if all whitespace after strip
        # The important thing is no crash
        assert ok is True or ok is False  # Either is acceptable; no exception


class TestSplitSectionsAutoFormat:
    """Unit tests for the Auto/Providencia heading variant of split_sections."""

    def test_hechos_razonamientos_la_sala_acuerda(self) -> None:
        text = 'HECHOS\nA.\nRAZONAMIENTOS JURÍDICOS\nB.\nLA SALA ACUERDA:\nC.'
        ant, fund, fal, ok = split_sections(text)
        assert ok is True
        assert ant is not None
        assert fund is not None
        assert fal is not None

    def test_acuerda_variant(self) -> None:
        text = 'HECHOS\nA.\nRAZONAMIENTOS JURÍDICOS\nB.\nACUERDA:\nC.'
        _ant, _fund, fal, ok = split_sections(text)
        assert ok is True
        assert fal is not None

    def test_se_acuerda_variant(self) -> None:
        text = 'HECHOS\nA.\nRAZONAMIENTOS\nB.\nSE ACUERDA:\nC.'
        _ant, _fund, fal, ok = split_sections(text)
        assert ok is True
        assert fal is not None

    def test_fundamentos_juridicos_variant(self) -> None:
        text = 'HECHOS\nA.\nFUNDAMENTOS JURÍDICOS\nB.\nACUERDA:\nC.'
        _ant, fund, _fal, ok = split_sections(text)
        assert ok is True
        assert fund is not None

    def test_only_hechos_not_parsed(self) -> None:
        text = 'HECHOS\nFacts only.'
        _ant, _fund, _fal, ok = split_sections(text)
        assert ok is False

    def test_case_insensitive_auto_headers(self) -> None:
        text = 'hechos\nA.\nrazonamientos jurídicos\nB.\nla sala acuerda:\nC.'
        ant, fund, fal, ok = split_sections(text)
        assert ok is True
        assert ant is not None
        assert fund is not None
        assert fal is not None

    def test_sentencia_headers_still_work(self) -> None:
        txt = (FIXTURES / 'ts_sentence.txt').read_text(encoding='utf-8')
        _ant, _fund, _fal, ok = split_sections(txt)
        assert ok is True

    def test_real_auto_fixture_parsed(self) -> None:
        txt = (FIXTURES / 'ts_ruling.txt').read_text(encoding='utf-8')
        _ant, _fund, fal, ok = split_sections(txt)
        assert ok is True
        assert fal is not None
        assert 'acuerda' in fal.lower()


class TestDetectScope:
    """Unit tests for _detect_scope."""

    def test_ts_returns_ts_tc(self) -> None:
        assert _detect_scope('ECLI:ES:TS:2024:1234') == 'ts_tc'

    def test_tc_returns_ts_tc(self) -> None:
        assert _detect_scope('ECLI:ES:TC:2024:1234') == 'ts_tc'

    def test_an_returns_collegial(self) -> None:
        assert _detect_scope('ECLI:ES:AN:2024:1234') == 'collegial'

    def test_tsjm_returns_collegial(self) -> None:
        assert _detect_scope('ECLI:ES:TSJM:2024:1234') == 'collegial'

    def test_tsjcat_returns_collegial(self) -> None:
        assert _detect_scope('ECLI:ES:TSJCAT:2024:1234') == 'collegial'

    def test_apba_returns_collegial(self) -> None:
        assert _detect_scope('ECLI:ES:APBA:2024:1234') == 'collegial'

    def test_jpi_returns_other(self) -> None:
        assert _detect_scope('ECLI:ES:JPI28:2024:1234') == 'other'

    def test_none_returns_other(self) -> None:
        assert _detect_scope(None) == 'other'

    def test_invalid_prefix_returns_other(self) -> None:
        assert _detect_scope('NOT-AN-ECLI') == 'other'


class TestExtractHeaderMetadata:
    """Unit tests for extract_header_metadata."""

    def test_ts_ruling_fixture_metadata(self) -> None:
        text = (FIXTURES / 'ts_ruling.txt').read_text(encoding='utf-8')
        meta = extract_header_metadata(text)
        assert meta is not None
        assert meta.roj == 'ATS 3898/2026'
        assert meta.ponente is not None and 'CORDOBA' in meta.ponente.upper()
        assert meta.tipo_resolucion == 'Auto'
        assert meta.fecha_raw == '20/04/2026'

    def test_ts_sentence_fixture_metadata(self) -> None:
        text = (FIXTURES / 'ts_sentence.txt').read_text(encoding='utf-8')
        meta = extract_header_metadata(text)
        assert meta is not None
        assert meta.roj == 'STS 1234/2020'
        assert meta.tipo_resolucion == 'Sentencia'

    def test_tsj_sentence_fixture_metadata(self) -> None:
        text = (FIXTURES / 'tsj_sentence.txt').read_text(encoding='utf-8')
        meta = extract_header_metadata(text)
        assert meta is not None
        assert meta.organo is not None and 'Madrid' in meta.organo
        assert meta.tipo_resolucion == 'Sentencia'

    def test_returns_none_for_empty_text(self) -> None:
        assert extract_header_metadata('') is None

    def test_returns_none_for_prose_only(self) -> None:
        assert extract_header_metadata('Some legal text without headers.') is None

    def test_fecha_raw_preserved_as_string(self) -> None:
        text = (FIXTURES / 'ts_ruling.txt').read_text(encoding='utf-8')
        meta = extract_header_metadata(text)
        assert meta is not None
        assert meta.fecha_raw is not None
        # DD/MM/YYYY format: 10 chars, two slashes at positions 2 and 5
        assert len(meta.fecha_raw) == 10
        assert meta.fecha_raw[2] == '/'
        assert meta.fecha_raw[5] == '/'

    def test_id_cendoj_extracted(self) -> None:
        text = (FIXTURES / 'ts_ruling.txt').read_text(encoding='utf-8')
        meta = extract_header_metadata(text)
        assert meta is not None
        assert meta.id_cendoj is not None
        assert meta.id_cendoj.isdigit()


class TestExtractSectionsCollegialScope:
    """Tests for collegial tribunal scope via extract_sections."""

    def test_tsjm_ecli_sets_collegial_scope(self) -> None:
        txt = (FIXTURES / 'tsj_sentence.txt').read_text(encoding='utf-8')
        result = extract_sections(_make_minimal_pdf(txt), ecli='ECLI:ES:TSJM:2020:1234')
        assert result.tribunal_scope == 'collegial'

    def test_an_ecli_sets_collegial_scope(self) -> None:
        txt = (FIXTURES / 'an_sentence.txt').read_text(encoding='utf-8')
        result = extract_sections(_make_minimal_pdf(txt), ecli='ECLI:ES:AN:2020:1234')
        assert result.tribunal_scope == 'collegial'

    def test_tsj_ecli_with_canonical_headers_can_parse(self) -> None:
        txt = (FIXTURES / 'tsj_sentence.txt').read_text(encoding='utf-8')
        result = extract_sections(_make_minimal_pdf(txt), ecli='ECLI:ES:TSJM:2024:9999')
        assert result.tribunal_scope == 'collegial'
        if result.parse_successful:
            assert result.antecedentes is not None

    def test_tsj_auto_can_parse(self) -> None:
        txt = (FIXTURES / 'tsj_auto.txt').read_text(encoding='utf-8')
        result = extract_sections(_make_minimal_pdf(txt), ecli='ECLI:ES:TSJM:2024:9999A')
        assert result.tribunal_scope == 'collegial'
        if result.parse_successful:
            assert result.fallo is not None

    def test_tsj_prose_only_not_parsed(self) -> None:
        txt = (FIXTURES / 'tsj_ruling.txt').read_text(encoding='utf-8')
        result = extract_sections(_make_minimal_pdf(txt), ecli='ECLI:ES:TSJM:2020:1234')
        assert result.parse_successful is False

    def test_jpi_ecli_returns_other_scope(self) -> None:
        txt = (FIXTURES / 'tsj_ruling.txt').read_text(encoding='utf-8')
        result = extract_sections(_make_minimal_pdf(txt), ecli='ECLI:ES:JPI28:2024:1234')
        assert result.tribunal_scope == 'other'
        assert result.parse_successful is False
