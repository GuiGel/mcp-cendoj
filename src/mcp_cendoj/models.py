"""Pydantic data models for mcp-cendoj."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class DocumentMetadata(BaseModel):
    """Structured metadata extracted from the CENDOJ PDF header block."""

    roj: str | None = None
    ecli_from_pdf: str | None = None
    id_cendoj: str | None = None
    organo: str | None = None
    sede: str | None = None
    fecha_raw: str | None = None
    ponente: str | None = None
    tipo_resolucion: str | None = None
    nro_recurso: str | None = None
    nro_resolucion: str | None = None
    seccion: str | None = None


class RulingSections(BaseModel):
    """Extracted text sections of a court ruling document.

    For Tribunal Supremo (TS) and Tribunal Constitucional (TC) rulings
    (``tribunal_scope='ts_tc'``), or for collegial courts (Audiencia Nacional,
    Tribunales Superiores de Justicia, Audiencias Provinciales,
    ``tribunal_scope='collegial'``), the PDF is split into three named sections
    when the appropriate headings are detected.
    For all other courts, only ``raw_text`` is populated and ``parse_successful``
    is ``False``.
    """

    antecedentes: str | None = Field(
        default=None,
        description=(
            'Background facts section ("Antecedentes de hecho" / "Hechos"). Present only when parse_successful is True.'
        ),
    )
    fundamentos_derecho: str | None = Field(
        default=None,
        description=(
            'Legal reasoning section ("Fundamentos de derecho" / "Razonamientos jurídicos"). '
            'Present only when parse_successful is True.'
        ),
    )
    fallo: str | None = Field(
        default=None,
        description=(
            'Operative part / dispositif ("Fallo" / "La Sala Acuerda"). Present only when parse_successful is True.'
        ),
    )
    raw_text: str = Field(
        description=(
            'Full document text wrapped in <court_document>…</court_document> XML tags. '
            'Always present regardless of tribunal_scope or parse_successful.'
        ),
    )
    parse_successful: bool = Field(
        default=False,
        description=(
            'True when the three-section (antecedentes / fundamentos / fallo) '
            'split succeeded. Possible for ts_tc and collegial scopes. '
            'False for other courts or when the PDF format is unexpected.'
        ),
    )
    tribunal_scope: Literal['ts_tc', 'collegial', 'other'] = Field(
        default='other',
        description=(
            '"ts_tc" for Tribunal Supremo and Tribunal Constitucional rulings; '
            '"collegial" for Audiencia Nacional, Tribunales Superiores de Justicia, '
            'and Audiencias Provinciales (section splitting attempted); '
            '"other" for Juzgados and all remaining courts (raw text only).'
        ),
    )
    metadata: DocumentMetadata | None = Field(
        default=None,
        description='Structured metadata from the CENDOJ PDF header block, when detected.',
    )


class Ruling(BaseModel):
    """A resolved court ruling with full text and provenance metadata."""

    ecli: str | None = Field(description='ECLI identifier (e.g. "ECLI:ES:TS:2024:1234"), or None if unresolved.')
    cendoj_internal_id: str | None = Field(
        description='CENDOJ internal numeric document reference (the "reference" field from search results).',
    )
    is_ecli_resolved: bool = Field(
        description='True when the ECLI was successfully looked up in CENDOJ before fetching the document.',
    )
    title: str = Field(description='Full document title as returned by CENDOJ (e.g. "SENTENCIA de 2024-01-15...").')
    court: str = Field(description='Court name as returned by CENDOJ (e.g. "Tribunal Supremo. Sala de lo Civil").')
    date: str = Field(description='Resolution date in YYYY-MM-DD format, or the raw string if parsing failed.')
    sections: RulingSections = Field(description='Extracted document sections including full text.')
    source_url: str = Field(description='URL used to download the PDF from CENDOJ.')
    cendoj_uri: str = Field(
        description=(
            'cendoj:// URI encoding all document identifiers, e.g. '
            '"cendoj://AN/11699040/20240115?ecli=ECLI:ES:TS:2024:1234". '
            'Stable reference for re-fetching without an ECLI lookup.'
        ),
    )
    fetched_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC),
        description='UTC timestamp of when this document was retrieved from CENDOJ.',
    )
    freshness: Literal['unknown'] = Field(
        default='unknown',
        description=(
            'Always "unknown". CENDOJ does not expose document modification dates, '
            'so staleness cannot be determined without re-fetching.'
        ),
    )
    warning: str | None = Field(
        default=None,
        description='Optional advisory message (e.g. failed PDF parse, partial content).',
    )


class SearchResult(BaseModel):
    """A single result item from a CENDOJ full-text search."""

    ecli: str | None = Field(description='ECLI identifier extracted from the result metadata, or None if absent.')
    title: str = Field(description='Document title from the search result anchor text.')
    court: str = Field(description='Court name from the result metadata list.')
    date: str = Field(description='Resolution date in YYYY-MM-DD format, or raw string if parsing failed.')
    snippet: str = Field(description='Short text excerpt from the result summary div.')
    url: str = Field(description='Direct URL to this document on the CENDOJ portal.')
    fetched_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC),
        description='UTC timestamp of when this search was executed.',
    )
    freshness: Literal['unknown'] = Field(
        default='unknown',
        description='Always "unknown" — CENDOJ does not expose last-modified timestamps.',
    )


class NormaResult(BaseModel):
    """A legislation item returned by the CENDOJ getNormasList endpoint."""

    norma_id: str = Field(
        description=(
            'BOE reference ID for this legislation item (e.g. "2015/11430" for the '
            "Workers' Statute). Pass as the ``norma_id`` argument to search_rulings "
            'to restrict results to rulings citing this norm.'
        ),
    )
    title: str = Field(description='Display title of the legislation (e.g. "Real Decreto Legislativo 2/2015…").')


_SUPERSEDED_WARNING = (
    'Citation coverage is incomplete — CENDOJ has no citation graph. '
    'Absence of results does NOT confirm validity. '
    'Spanish courts also cite by ROJ identifier and popular case name. '
    'A positive result indicates the checked ECLI co-occurs with reversal language '
    'in a later ruling snippet — NOT that the checked ruling is the direct subject '
    'of reversal. Manual verification by a qualified lawyer is required.'
)


class SupersededResult(BaseModel):
    """Result of a heuristic supersession check for a court ruling."""

    checked_ecli: str = Field(description='The ECLI that was checked for supersession.')
    later_rulings: list[SearchResult] = Field(
        description='Search results that cite the checked ECLI alongside reversal language.',
    )
    citations_found: int = Field(
        description='Number of later rulings found that contain the ECLI and reversal keywords.',
    )
    is_likely_superseded: bool = Field(
        description=(
            'True if at least one later ruling was found that cites the checked ECLI '
            'alongside reversal language (revoca, casa, anula, deja sin efecto). '
            'See ``warning`` for important caveats.'
        ),
    )
    search_method: Literal['ecli_fulltext'] = Field(
        description='Always "ecli_fulltext" — the ECLI string is used as a TEXT query.',
    )
    confidence: Literal['medium'] = Field(
        default='medium',
        description=(
            'Always "medium". The check is heuristic: snippet co-occurrence, not a '
            'verified citation graph. A positive result requires manual legal review.'
        ),
    )
    warning: str = Field(
        default=_SUPERSEDED_WARNING,
        description='Mandatory disclaimer about the heuristic nature of this check.',
    )
