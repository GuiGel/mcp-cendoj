# ADR-0006: Extended Parser Scope and Auto/Providencia Format Support

**Date**: 2026-04-30
**Status**: Accepted

## Context

ADR-0004 established a conservative Phase 1 scope: structured section extraction only for
Tribunal Supremo (TS) and Tribunal Constitucional (TC), with all other courts falling back
to `raw_text`. Post-MVP analysis (`docs/parser-coverage-analysis.md`) reveals this covers
only ~15–20% of the CENDOJ corpus:

- **Sentencias from AN, TSJ (×17), AP** share the same canonical structure
  (`ANTECEDENTES DE HECHO / FUNDAMENTOS DE DERECHO / FALLO`) as TS/TC sentencias. The only
  reason they fail is the ECLI-based scope gate, not an incompatible document format.
- **Autos and Providencias** (≈30% of TS output, present at all tribunal levels) use a
  different heading schema (`HECHOS / RAZONAMIENTOS JURÍDICOS / LA SALA ACUERDA:`) that
  the current regex never matches, producing a silent `parse_successful=False`.
- **Metadata header** (`Roj`, `ECLI`, `Órgano`, `Fecha`, `Ponente`, `Tipo de Resolución`)
  is present in 100% of CENDOJ PDFs and is never extracted today, losing high-value
  structured data that is trivially available.

Three options were considered:

| Option | Pros | Cons |
|--------|------|------|
| A. Keep ADR-0004 scope; add only Auto parser for TS/TC | Low risk; no model changes | Misses >50% of corpus sentences; AN/TSJ remain `raw_text` only |
| B. Extend scope to all collegial courts; add Auto parser; add metadata extraction | High corpus coverage gain; reuses existing regex unchanged | Requires `tribunal_scope` model extension; existing tests need updating |
| C. Build court-specific parsers per tribunal code | Maximum fidelity | O(20) parsers, unsustainable maintenance, insufficient fixture data |

## Decision

**Option B** — extend parser scope to three tiers and add Auto-format and metadata parsers:

### 1. `tribunal_scope` becomes a three-value literal

```python
tribunal_scope: Literal['ts_tc', 'collegial', 'other']
```

- `'ts_tc'` — Tribunal Supremo (`ECLI:ES:TS:*`) and Tribunal Constitucional (`ECLI:ES:TC:*`).
  Section splitting attempted; always has been.
- `'collegial'` — Audiencia Nacional (`ECLI:ES:AN:*`), Tribunales Superiores de Justicia
  (`ECLI:ES:TSJ*:*`), and Audiencias Provinciales (`ECLI:ES:AP*:*`). Section splitting now
  attempted when canonical or Auto-format headers are found.
- `'other'` — Juzgados, military tribunals, unknown prefixes, and `ecli=None`. Raw text
  only; `parse_successful` always `False`.

### 2. `split_sections` extended to detect both heading schemas

Both schemas map to the same three output fields (`antecedentes`, `fundamentos_derecho`,
`fallo`) because they represent the same semantic roles regardless of heading text:

| Schema | Antecedentes | Fundamentos | Fallo |
|--------|-------------|-------------|-------|
| Sentencia (Parser A) | `ANTECEDENTES DE HECHO` | `FUNDAMENTOS DE DERECHO` | `FALLO` or `PARTE DISPOSITIVA` |
| Auto/Providencia (Parser B) | `HECHOS` or `ANTECEDENTES` | `RAZONAMIENTOS JURÍDICOS` or `RAZONAMIENTOS` or `FUNDAMENTOS JURÍDICOS` | `LA SALA ACUERDA:` or `ACUERDA:` or `SE ACUERDA:` |

A unified regex with both variants is tried; the first successful 3-section parse wins.
Sentencia headings take priority (tried first) to prevent partial matches on documents that
contain both (e.g. Autos that quote a prior Sentencia in the Hechos section).

**Heading order guard**: a regex match is accepted only if the three heading positions are
strictly ordered (antecedentes < fundamentos < fallo). This prevents false-positive parses
caused by CENDOJ PDFs that include a cover-page metadata block containing text such as
`Fallo/Acuerdo: Auto no ha lugar`, which matches the `fallo` variant before the real body
sections appear. Out-of-order positions indicate a cover-page artefact, not a valid section
boundary; `_try_split_with_re` returns `(None, None, None, False)` in that case.

### 3. `DocumentMetadata` nested sub-model added to `RulingSections`

```python
class DocumentMetadata(BaseModel):
    roj: str | None
    ecli_from_pdf: str | None   # ECLI extracted from PDF header (cross-check vs ECLI arg)
    id_cendoj: str | None
    organo: str | None
    sede: str | None
    fecha_raw: str | None       # "DD/MM/YYYY" as found in PDF
    ponente: str | None
    tipo_resolucion: str | None  # "Sentencia" | "Auto" | "Providencia" | "Acuerdo"
    nro_recurso: str | None
    nro_resolucion: str | None
    seccion: str | None
```

`RulingSections.metadata: DocumentMetadata | None = None` — `None` when the PDF header
regex fails (e.g. scanned PDFs, unusual formatting, or very short documents).

### 4. No changes to `Ruling` top-level fields

`Ruling.court` and `Ruling.date` continue to come from HTML scraping and remain unchanged.
`sections.metadata` is additional enrichment, not a replacement.

## Consequences

**Positive**:
- Estimated coverage increase from ~15–20% to ~75–80% of the full CENDOJ corpus.
- Backwards-compatible at the tool API level: `antecedentes`, `fundamentos_derecho`, `fallo`,
  `raw_text`, `parse_successful` are unchanged; `tribunal_scope='other'` behavior is unchanged.
- `DocumentMetadata` allows cross-validation (`ecli_from_pdf != ecli` → `warning` on `Ruling`).
- `tipo_resolucion` from metadata lets consumers distinguish Sentencia vs Auto programmatically.

**Negative**:
- `tribunal_scope='other'` now means "Juzgados + unknown", not "anything that isn't TS/TC".
  Any downstream code pattern-matching `tribunal_scope == 'other'` to mean "not structured"
  must be updated to also handle `'collegial'` with `parse_successful=False`.
- TSJ/AN documents with atypical heading variants (missing or renamed sections) will still
  return `parse_successful=False` — same silent failure as before, now properly scoped.
- Requires collecting and maintaining 3 new minimal fixtures (`tsj_sentence.txt`,
  `an_sentence.txt`, `tsj_auto.txt`).

## Future Scope

- Parser C (Juzgados/JPI/JS/JCA): `HECHOS PROBADOS / FUNDAMENTOS JURÍDICOS / FALLO` —
  deferred until representative fixtures are available.
- Numbered item extraction (`<item numero="PRIMERO">…</item>`) within sections — deferred.
- Structured XML output format version bump (`version="2"`) — deferred; requires API
  versioning strategy.
