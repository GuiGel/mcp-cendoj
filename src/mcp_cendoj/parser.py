"""PDF text extraction and section detection for CENDOJ rulings."""

import io
import re
from collections.abc import Callable
from typing import Literal

import pdfplumber

from mcp_cendoj.constants import MAX_RESPONSE_BYTES
from mcp_cendoj.models import DocumentMetadata, RulingSections

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

_AUTO_SECTION_RE = re.compile(
    r'(HECHOS|ANTECEDENTES)'
    r'|(RAZONAMIENTOS\s+JUR[IÍ]DICOS|RAZONAMIENTOS|FUNDAMENTOS\s+JUR[IÍ]DICOS)'
    r'|(LA\s+SALA\s+ACUERDA\s*:|ACUERDA\s*:|SE\s+ACUERDA\s*:|PARTE\s+DISPOSITIVA)',
    re.IGNORECASE,
)
"""Regex for the Auto/Providencia heading schema used by collegial courts.

Group 1: antecedentes equivalent (HECHOS or ANTECEDENTES).
Group 2: fundamentos equivalent (RAZONAMIENTOS JURÍDICOS / RAZONAMIENTOS / FUNDAMENTOS JURÍDICOS).
Group 3: fallo equivalent (LA SALA ACUERDA: / ACUERDA: / SE ACUERDA: / PARTE DISPOSITIVA).
"""

_TS_TC_ECLI_RE = re.compile(r'^ECLI:ES:(TS|TC):', re.IGNORECASE)
"""Regex to identify Tribunal Supremo and Tribunal Constitucional ECLI identifiers."""

_COLLEGIAL_ECLI_RE = re.compile(
    r'^ECLI:ES:(AN|TSJ[A-Z]+|AP[A-Z]+):',
    re.IGNORECASE,
)
"""Regex to identify Audiencia Nacional, TSJ, and Audiencia Provincial ECLI identifiers."""

_HEADER_RE = re.compile(
    r'Roj:\s*(?P<roj>[^\-\n]+?)\s*-\s*ECLI:(?P<ecli>[^\n]+)\n'
    r'Id\s+Cendoj:\s*(?P<id_cendoj>\d+)\n'
    r'Órgano:\s*(?P<organo>[^\n]+)\n'
    r'(?:Sede:\s*(?P<sede>[^\n]+)\n)?'
    r'(?:Sección:\s*(?P<seccion>[^\n]+)\n)?'
    r'Fecha:\s*(?P<fecha>\d{2}/\d{2}/\d{4})\n'
    r'(?:.*?Nº\s+de\s+Recurso:\s*(?P<nro_recurso>[^\n]+)\n)?'
    r'(?:.*?Nº\s+de\s+Resolución:\s*(?P<nro_resolucion>[^\n]*)\n)?'
    r'(?:.*?Ponente:\s*(?P<ponente>[^\n]+)\n)?'
    r'.*?Tipo\s+de\s+Resolución:\s*(?P<tipo>[^\n]+)',
    re.DOTALL | re.IGNORECASE,
)
"""Regex that extracts structured fields from the CENDOJ PDF header block.

The CENDOJ header is present in 100% of digitally-generated PDFs and contains:
Roj, ECLI, Id Cendoj, Órgano, Sede, Sección, Fecha, Nº de Recurso,
Nº de Resolución, Ponente, and Tipo de Resolución.
"""


class CendojParseError(Exception):
    """Raised when a CENDOJ document cannot be parsed."""


def extract_header_metadata(text: str) -> DocumentMetadata | None:
    """Extract structured fields from the CENDOJ PDF header block.

    Args:
        text: Plain text extracted from a CENDOJ PDF.

    Returns:
        A :class:`~mcp_cendoj.models.DocumentMetadata` instance when the header
        block is detected, or ``None`` when the header is absent or malformed.
    """
    m = _HEADER_RE.search(text)
    if not m:
        return None
    return DocumentMetadata(
        roj=m.group('roj').strip() or None,
        ecli_from_pdf=m.group('ecli').strip() or None,
        id_cendoj=m.group('id_cendoj').strip() or None,
        organo=m.group('organo').strip() or None,
        sede=(m.group('sede') or '').strip() or None,
        seccion=(m.group('seccion') or '').strip() or None,
        fecha_raw=(m.group('fecha') or '').strip() or None,
        ponente=(m.group('ponente') or '').strip() or None,
        tipo_resolucion=(m.group('tipo') or '').strip() or None,
        nro_recurso=(m.group('nro_recurso') or '').strip() or None,
        nro_resolucion=(m.group('nro_resolucion') or '').strip() or None,
    )


def _detect_scope(ecli: str | None) -> Literal['ts_tc', 'collegial', 'other']:
    """Return the tribunal scope tier for the given ECLI identifier.

    Args:
        ecli: ECLI identifier string, or ``None``.

    Returns:
        ``'ts_tc'`` for Tribunal Supremo / Tribunal Constitucional,
        ``'collegial'`` for Audiencia Nacional, TSJ, and Audiencias Provinciales,
        ``'other'`` for Juzgados, unknown prefixes, or when *ecli* is ``None``.
    """
    if ecli and _TS_TC_ECLI_RE.match(ecli):
        return 'ts_tc'
    if ecli and _COLLEGIAL_ECLI_RE.match(ecli):
        return 'collegial'
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

    Tries the canonical Sentencia headings first (``_SECTION_RE``). If fewer than
    three headings are found, falls back to the Auto/Providencia heading schema
    (``_AUTO_SECTION_RE``). Returns the first successful 3-section parse.

    Args:
        text: Plain text of the ruling extracted from the PDF.

    Returns:
        Tuple of ``(antecedentes, fundamentos_derecho, fallo, parse_successful)``
        where the first three elements are the extracted section strings (stripped),
        or ``None`` if parsing failed. ``parse_successful`` is ``True`` only when
        all three sections are found.
    """
    result = _try_split_with_re(text, _SECTION_RE, _map_sentencia_label)
    if result[3]:
        return result
    return _try_split_with_re(text, _AUTO_SECTION_RE, _map_auto_label)


def _map_sentencia_label(match: re.Match[str]) -> str | None:
    """Map a canonical Sentencia heading match to its canonical label."""
    normalised = re.sub(r'\s+', ' ', match.group(0).upper().strip())
    if 'ANTECEDENTES' in normalised:
        return 'ANTECEDENTES'
    if 'FUNDAMENTOS' in normalised:
        return 'FUNDAMENTOS'
    if 'FALLO' in normalised or 'PARTE DISPOSITIVA' in normalised:
        return 'FALLO'
    return None


def _map_auto_label(match: re.Match[str]) -> str | None:
    """Map an Auto/Providencia heading match to the canonical three-section label."""
    if match.group(1):
        return 'ANTECEDENTES'
    if match.group(2):
        return 'FUNDAMENTOS'
    if match.group(3):
        return 'FALLO'
    return None


def _try_split_with_re(
    text: str,
    pattern: re.Pattern[str],
    label_fn: 'Callable[[re.Match[str]], str | None]',
) -> tuple[str | None, str | None, str | None, bool]:
    """Generic section splitter — shared by both Sentencia and Auto variants.

    Args:
        text: Plain text to split.
        pattern: Compiled regex with heading matches.
        label_fn: Maps each regex match to one of ``'ANTECEDENTES'``,
            ``'FUNDAMENTOS'``, ``'FALLO'``, or ``None`` (skip).

    Returns:
        ``(antecedentes, fundamentos, fallo, parse_successful)`` tuple.
    """
    matches = list(pattern.finditer(text))
    if not matches:
        return None, None, None, False

    label_to_content_start: dict[str, int] = {}
    label_to_heading_start: dict[str, int] = {}

    for m in matches:
        label = label_fn(m)
        if label and label not in label_to_content_start:
            label_to_content_start[label] = m.end()
            label_to_heading_start[label] = m.start()

    if len(label_to_content_start) < 3:
        return None, None, None, False

    ant_heading = label_to_heading_start['ANTECEDENTES']
    fun_heading = label_to_heading_start['FUNDAMENTOS']
    fal_heading = label_to_heading_start['FALLO']

    # Reject splits where headings appear out of order in the text.
    # This guards against false-positive matches such as "Fallo/Acuerdo:" in
    # the CENDOJ cover-page metadata block, which precedes ANTECEDENTES DE HECHO.
    if not (ant_heading < fun_heading < fal_heading):
        return None, None, None, False

    ant_start = label_to_content_start['ANTECEDENTES']
    fun_start = label_to_content_start['FUNDAMENTOS']
    fal_start = label_to_content_start['FALLO']

    antecedentes = text[ant_start:fun_heading].strip()
    fundamentos = text[fun_start:fal_heading].strip()
    fallo = text[fal_start:].strip()

    return antecedentes or None, fundamentos or None, fallo or None, True


def extract_sections(pdf_bytes: bytes, ecli: str | None = None) -> RulingSections:
    """Extract text and parse sections from a CENDOJ PDF document.

    Args:
        pdf_bytes: Raw PDF bytes returned by CENDOJ document endpoint.
        ecli: Optional ECLI identifier used to determine tribunal scope.

    Returns:
        A :class:`~mcp_cendoj.models.RulingSections` instance with extracted text
        and, for TS/TC and collegial rulings, parsed sections when section headers
        are found.

    Raises:
        CendojParseError: If *pdf_bytes* exceeds :data:`~mcp_cendoj.constants.MAX_RESPONSE_BYTES`.
    """
    if len(pdf_bytes) > MAX_RESPONSE_BYTES:
        raise CendojParseError(f'PDF is too large: {len(pdf_bytes)} bytes (max {MAX_RESPONSE_BYTES})')

    plain_text = _extract_text_from_pdf(pdf_bytes)
    raw_text = f'<court_document source="cendoj">\n{plain_text}\n</court_document>'

    scope = _detect_scope(ecli)
    metadata = extract_header_metadata(plain_text)

    if scope == 'other':
        return RulingSections(
            raw_text=raw_text,
            parse_successful=False,
            tribunal_scope='other',
            metadata=metadata,
        )

    # scope is 'ts_tc' or 'collegial' — attempt section splitting
    antecedentes, fundamentos, fallo, parsed = split_sections(plain_text)
    return RulingSections(
        raw_text=raw_text,
        parse_successful=parsed,
        tribunal_scope=scope,
        antecedentes=antecedentes,
        fundamentos_derecho=fundamentos,
        fallo=fallo,
        metadata=metadata,
    )
