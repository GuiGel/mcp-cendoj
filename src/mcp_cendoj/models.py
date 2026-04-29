"""Pydantic data models for mcp-cendoj."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class RulingSections(BaseModel):
    """Extracted sections of a court ruling."""

    antecedentes: str | None = None
    fundamentos_derecho: str | None = None
    fallo: str | None = None
    raw_text: str
    parse_successful: bool = False
    tribunal_scope: Literal['ts_tc', 'other'] = 'other'


class Ruling(BaseModel):
    """A resolved court ruling with provenance envelope."""

    ecli: str | None
    cendoj_internal_id: str | None
    is_ecli_resolved: bool
    title: str
    court: str
    date: str
    sections: RulingSections
    source_url: str
    cendoj_uri: str
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    freshness: Literal['unknown'] = 'unknown'
    warning: str | None = None


class SearchResult(BaseModel):
    """A search result item from CENDOJ."""

    ecli: str | None
    title: str
    court: str
    date: str
    snippet: str
    url: str
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    freshness: Literal['unknown'] = 'unknown'


_SUPERSEDED_WARNING = (
    'Citation coverage is incomplete — CENDOJ has no citation graph. '
    'Absence of results does NOT confirm validity. '
    'Spanish courts also cite by ROJ identifier and popular case name. '
    'A positive result indicates the checked ECLI co-occurs with reversal language '
    'in a later ruling snippet — NOT that the checked ruling is the direct subject '
    'of reversal. Manual verification by a qualified lawyer is required.'
)


class SupersededResult(BaseModel):
    """Result of a supersession check for a court ruling."""

    checked_ecli: str
    later_rulings: list[SearchResult]
    citations_found: int
    is_likely_superseded: bool
    search_method: Literal['ecli_fulltext']
    confidence: Literal['medium'] = 'medium'
    warning: str = _SUPERSEDED_WARNING
