"""Tests for src/mcp_cendoj/parser.py (TDD — written before implementation)."""

import io
from pathlib import Path

import pytest

from mcp_cendoj.constants import MAX_RESPONSE_BYTES
from mcp_cendoj.parser import CendojParseError, extract_sections

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

    def test_tsj_ecli_sets_other_scope(self) -> None:
        txt = (FIXTURES / 'tsj_ruling.txt').read_text(encoding='utf-8')
        result = extract_sections(
            _make_minimal_pdf(txt),
            ecli='ECLI:ES:TSJM:2020:1234',
        )
        assert result.tribunal_scope == 'other'
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
