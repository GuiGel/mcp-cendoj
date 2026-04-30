# ADR-0004: Section Extraction Scope and Fallback Strategy

**Date**: 2026-04-29
**Status**: Partially superseded by [ADR-0006](ADR-0006-extended-parser-scope-and-auto-format.md) (`tribunal_scope` definition and parser scope extended)

## Context

CENDOJ indexes rulings from ~30 tribunals built over 20+ years with heterogeneous court IT systems. Section headers (`ANTECEDENTES DE HECHO`, `FUNDAMENTOS DE DERECHO`, `FALLO`) appear in different HTML structures depending on the tribunal:

- **Tribunal Supremo (TS)** and **Tribunal Constitucional (TC)**: most uniform, highest volume, consistent `<h3>` or bold `<p>` structure.
- **Audiencia Nacional (AN)**: reasonably consistent.
- **Tribunales Superiores de Justicia (TSJ)**: highly variable, 17 regional variants.
- **Juzgados de Primera Instancia**: minimal structure, often plain paragraphs.

A single regex parser trained on TS output silently mis-parses TSJ documents — extracting `fundamentos` into `antecedentes` with no error signal.

## Decision

### Phase 1 scope (MVP)

Build the structured section extractor **only for TS and TC** (the two most uniform, highest-authority courts). For all other tribunals, fall back to `raw_text` extraction.

The `RulingSections` model includes:
- `antecedentes: str | None`
- `fundamentos_derecho: str | None`
- `fallo: str | None`
- `raw_text: str` — always populated, regardless of parse success.
- `parse_successful: bool` — `True` only when all three sections were extracted cleanly.
- `tribunal_scope: Literal["ts_tc", "other"]` — indicates which parsing path was used.

### Failure mode

When a section boundary is not found for TS/TC documents, the parser logs a warning and sets `parse_successful = False` rather than returning a mis-labelled partial parse.

### Future scope

An AN extractor can be added in a follow-up. TSJ parsers require court-specific fixture collection and are explicitly out of scope until sample data is gathered per tribunal.

## Consequences

**Positive**:
- Prevents silent mis-labelling of legal sections across courts.
- `raw_text` always available as fallback — tool is never "broken", just less structured.
- LLM can check `parse_successful` and `tribunal_scope` to decide how to use the result.

**Negative**:
- Full structured extraction unavailable for TSJ and lower courts in MVP.
- Requires collecting 10–15 real HTML fixtures from TS/TC/AN/TSJ before finalising regexes — adds ~1 hour of pre-work.
