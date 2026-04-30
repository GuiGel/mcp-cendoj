"""PDF text extraction and section detection for CENDOJ rulings."""

import io
import re

import pdfplumber

from mcp_cendoj.constants import MAX_RESPONSE_BYTES
from mcp_cendoj.models import RulingSections

_SECTION_RE = re.compile(
    r'(ANTECEDENTES\s+DE\s+HECHO|FUNDAMENTOS\s+DE\s+DERECHO|FALLO|PARTE\s+DISPOSITIVA)',
    re.IGNORECASE,
)
"""Regex that matches the canonical section headings in Spanish court ruling PDFs.

Captures four heading variants:
    ANTECEDENTES DE HECHO: Background facts section heading (TS/TC rulings).
    FUNDAMENTOS DE DERECHO: Legal reasoning section heading (TS/TC rulings).
    FALLO: Operative part heading (most TS/TC rulings).
    PARTE DISPOSITIVA: Alternative operative part heading (some TS rulings).

The match is case-insensitive and allows any whitespace between words to handle
hyphenation and line-break artefacts introduced by pdfplumber text extraction.
"""

_TS_TC_ECLI_RE = re.compile(r'^ECLI:ES:(TS|TC):', re.IGNORECASE)
"""Regex to identify Tribunal Supremo and Tribunal Constitucional ECLI identifiers.

Matches ECLIs of the form ``ECLI:ES:TS:…`` or ``ECLI:ES:TC:…``.
Used by :func:`_detect_scope` to decide whether to attempt section splitting.
All other courts (e.g. TSJM, AN, JPI) do not reliably follow the 3-section
structure, so their PDFs are returned as raw text only.
"""


class CendojParseError(Exception):
    """Raised when a CENDOJ document cannot be parsed."""


def _detect_scope(ecli: str | None) -> str:
    """Return 'ts_tc' if *ecli* identifies a TS or TC ruling, else 'other'."""
    if ecli and _TS_TC_ECLI_RE.match(ecli):
        return 'ts_tc'
    return 'other'


def _extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract concatenated plain text from all pages of a PDF.

    Args:
        pdf_bytes: Raw PDF file content as returned by the CENDOJ document endpoint.

    Returns:
        Newline-joined text from all pages. Returns an empty string if pdfplumber
        extracts no text (e.g. scanned PDFs without an embedded text layer).
    """
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        parts: list[str] = []
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                parts.append(page_text)
    return '\n'.join(parts)


def split_sections(text: str) -> tuple[str | None, str | None, str | None, bool]:
    """Split ruling text into antecedentes, fundamentos_derecho, fallo sections.

    Locates the canonical section headings (matched by _SECTION_RE) and slices
    the text into three segments. If fewer than three headings are found, returns
    all ``None`` values with ``parse_successful=False``.

    Args:
        text: Plain text of the ruling extracted from the PDF.

    Returns:
        Tuple of ``(antecedentes, fundamentos_derecho, fallo, parse_successful)``
        where the first three elements are the extracted section strings (stripped),
        or ``None`` if parsing failed. ``parse_successful`` is ``True`` only when
        all three sections are found.
    """
    matches = list(_SECTION_RE.finditer(text))
    if not matches:
        return None, None, None, False

    label_to_pos: dict[str, int] = {}
    for m in matches:
        normalised = re.sub(r'\s+', ' ', m.group(0).upper().strip())
        if 'ANTECEDENTES' in normalised and 'ANTECEDENTES' not in label_to_pos:
            label_to_pos['ANTECEDENTES'] = m.end()
        elif 'FUNDAMENTOS' in normalised and 'FUNDAMENTOS' not in label_to_pos:
            label_to_pos['FUNDAMENTOS'] = m.end()
        elif ('FALLO' in normalised or 'PARTE DISPOSITIVA' in normalised) and 'FALLO' not in label_to_pos:
            label_to_pos['FALLO'] = m.end()

    if len(label_to_pos) < 3:
        return None, None, None, False

    ant_start = label_to_pos['ANTECEDENTES']
    fun_start = label_to_pos['FUNDAMENTOS']
    fal_start = label_to_pos['FALLO']

    # Determine end positions — each section ends where the next begins (heading inclusive)
    # We need the start of each section *heading*, not the end of the content.
    heading_starts: dict[str, int] = {}
    for m in matches:
        normalised = re.sub(r'\s+', ' ', m.group(0).upper().strip())
        if 'ANTECEDENTES' in normalised and 'ANTECEDENTES' not in heading_starts:
            heading_starts['ANTECEDENTES'] = m.start()
        elif 'FUNDAMENTOS' in normalised and 'FUNDAMENTOS' not in heading_starts:
            heading_starts['FUNDAMENTOS'] = m.start()
        elif ('FALLO' in normalised or 'PARTE DISPOSITIVA' in normalised) and 'FALLO' not in heading_starts:
            heading_starts['FALLO'] = m.start()

    antecedentes = text[ant_start : heading_starts.get('FUNDAMENTOS', fun_start)].strip()
    fundamentos = text[fun_start : heading_starts.get('FALLO', fal_start)].strip()
    fallo = text[fal_start:].strip()

    return antecedentes or None, fundamentos or None, fallo or None, True


def extract_sections(pdf_bytes: bytes, ecli: str | None = None) -> RulingSections:
    """Extract text and parse sections from a CENDOJ PDF document.

    Args:
        pdf_bytes: Raw PDF bytes returned by CENDOJ document endpoint.
        ecli: Optional ECLI identifier used to determine tribunal scope.

    Returns:
        A :class:`~mcp_cendoj.models.RulingSections` instance with extracted text
        and, for TS/TC rulings, parsed sections when section headers are found.

    Raises:
        CendojParseError: If *pdf_bytes* exceeds :data:`~mcp_cendoj.constants.MAX_RESPONSE_BYTES`.
    """
    if len(pdf_bytes) > MAX_RESPONSE_BYTES:
        raise CendojParseError(f'PDF is too large: {len(pdf_bytes)} bytes (max {MAX_RESPONSE_BYTES})')

    plain_text = _extract_text_from_pdf(pdf_bytes)
    raw_text = f'<court_document source="cendoj">\n{plain_text}\n</court_document>'

    scope = _detect_scope(ecli)

    if scope != 'ts_tc':
        return RulingSections(
            raw_text=raw_text,
            parse_successful=False,
            tribunal_scope='other',
        )

    antecedentes, fundamentos, fallo, parsed = split_sections(plain_text)

    return RulingSections(
        raw_text=raw_text,
        parse_successful=parsed,
        tribunal_scope='ts_tc',
        antecedentes=antecedentes,
        fundamentos_derecho=fundamentos,
        fallo=fallo,
    )
