# ADR-0003: Provenance Envelope Design

**Date**: 2026-04-29
**Status**: Accepted

## Context

Every tool response from `mcp_cendoj` will be cited by LLMs in legal contexts. Two failure modes were identified in brainstorming:

1. **False freshness**: a timestamp named `retrieved_at` implies document currency. CENDOJ does not expose `Last-Modified` headers. The timestamp only records when the HTTP GET was made.
2. **False certainty**: returning `superseded: bool` on the supersession check would allow LLMs to produce confident legal statements about a check that is based on incomplete full-text ECLI string matching (Spanish courts routinely cite rulings by popular name or `ROJ` ID, not ECLI).

The `Ruling` model must make uncertainty explicit and un-dismissible at the schema level.

## Decision

### Naming

Use `fetched_at: datetime` (not `retrieved_at`) to signal that this is an HTTP fetch timestamp, not document last-modified.

### Freshness field

Add `freshness: Literal["unknown"] = "unknown"` as a non-optional literal field. It is structurally impossible to return any other value — consumers cannot treat the timestamp as a freshness guarantee.

### Supersession confidence

`SupersededResult` uses `confidence: Literal["medium"] = "medium"` — hardcoded, non-optional. The field cannot be set to `"high"` anywhere in the codebase. The docstring explains that CENDOJ has no citation graph and coverage is limited to ECLI full-text matches.

### Boolean ban

`SupersededResult` does NOT include a `superseded: bool` field. It exposes `citations_found: int` and `is_likely_superseded: bool` (with explicit "likely" qualifier) accompanied by a mandatory `search_method: Literal["ecli_fulltext"]` and `warning: str` field.

### ECLI ambiguity

`lookup_by_ecli` raises `ECLIAmbiguousError` when `len(results) != 1`. The `Ruling` model includes `cendoj_internal_id: str | None` for deduplication when ECLI is not a stable unique key.

## Consequences

**Positive**:
- LLMs cannot silently misuse tool outputs as authoritative legal facts.
- Compliance-ready: audit logs contain explicit uncertainty markers.
- Pyright enforces the literal types — impossible to accidentally set `freshness="fresh"`.

**Negative**:
- More verbose response models than strictly necessary for a demo.
- `is_likely_superseded: bool` still conveys a boolean signal — mitigated by the `confidence: "medium"` and `warning` fields being co-present.
