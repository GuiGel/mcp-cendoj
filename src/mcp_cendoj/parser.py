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

_TS_TC_ECLI_RE = re.compile(r'^ECLI:ES:(TS|TC):', re.IGNORECASE)


class CendojParseError(Exception):
    """Raised when a CENDOJ document cannot be parsed."""


def _detect_scope(ecli: str | None) -> str:
    """Return 'ts_tc' if *ecli* identifies a TS or TC ruling, else 'other'."""
    if ecli and _TS_TC_ECLI_RE.match(ecli):
        return 'ts_tc'
    return 'other'


def _extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract plain text from PDF bytes using pdfplumber."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        parts: list[str] = []
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                parts.append(page_text)
    return '\n'.join(parts)


def _split_sections(text: str) -> tuple[str | None, str | None, str | None, bool]:
    """Split text into antecedentes / fundamentos_derecho / fallo sections.

    Returns a tuple of (antecedentes, fundamentos_derecho, fallo, parse_successful).
    parse_successful is True only when all three sections are found.
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

    antecedentes, fundamentos, fallo, parsed = _split_sections(plain_text)

    return RulingSections(
        raw_text=raw_text,
        parse_successful=parsed,
        tribunal_scope='ts_tc',
        antecedentes=antecedentes,
        fundamentos_derecho=fundamentos,
        fallo=fallo,
    )
