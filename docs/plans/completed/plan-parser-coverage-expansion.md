# Plan: parser-coverage-expansion

Created: 2026-04-30 | Branch: feature/parser-coverage-expansion | Tier: 1 (Focused) | **Status: COMPLETED 2026-04-30**

## Summary

Implement three parser improvements identified in `docs/parser-coverage-analysis.md` to
increase CENDOJ PDF parsing coverage from ~15–20% to ~75–80% of the full corpus:

1. **Parser 0** — extract structured metadata (`Roj`, `Órgano`, `Fecha`, `Ponente`,
   `Tipo de Resolución`, etc.) from the PDF header block present in 100% of CENDOJ PDFs.
2. **Parser A extended** — lift the `_detect_scope` gate so Sentencias from Audiencia
   Nacional (`AN`), Tribunales Superiores de Justicia (`TSJ*`), and Audiencias Provinciales
   (`AP*`) are parsed when canonical headings are detected.
3. **Parser B** — handle the Auto/Providencia heading schema (`HECHOS /
   RAZONAMIENTOS JURÍDICOS / LA SALA ACUERDA:`) for all collegial courts including TS/TC.

Governed by ADR-0006. Extends ADR-0004 (Phase 1 scope).

---

## Decisions

| ID | Decision | Rationale |
|----|----------|----------|
| D-1 | `tribunal_scope` three-tier Literal: `'ts_tc'` / `'collegial'` / `'other'` | 3 tiers match structural reality; `'ts_tc'` kept for backwards compat |
| D-2 | Parser B output fields reuse `antecedentes`, `fundamentos_derecho`, `fallo` | Same semantic role regardless of heading text |
| D-3 | `DocumentMetadata` as nested sub-model on `RulingSections` | Additive; no breaking changes to `Ruling` top-level |
| D-4 | Sentencia headers tried first in dual-schema `split_sections` | Prevents false Auto matches in embedded quotes |
| D-5 | Juzgados (Parser C) out of scope | Insufficient fixtures; `'other'` scope behaviour unchanged |

> **ADR-0006 status**: Currently "Proposed". Must be updated to **Accepted** at the start of plan execution (before the first commit).

> **Downstream impact**: Any code pattern-matching `tribunal_scope == 'other'` to mean "not structured" must also handle `'collegial'` with `parse_successful=False` after this change. Task 5.1 covers the only known call site in the test suite.

---

## Architecture

### ADR created
- `docs/adr/ADR-0006-extended-parser-scope-and-auto-format.md` — three-tier
  `tribunal_scope`, dual-schema `split_sections`, nested `DocumentMetadata`.

### ADR-0004 status
ADR-0004 Phase 1 scope is superseded by ADR-0006 for the parser layer. The fallback
strategy (raw_text always available) is preserved unchanged.

### Key design decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| `tribunal_scope` values | `'ts_tc'` / `'collegial'` / `'other'` | 3 tiers match structural reality; `'ts_tc'` kept for backwards compat |
| Parser B output fields | Reuse `antecedentes`, `fundamentos_derecho`, `fallo` | Same semantic role regardless of heading text |
| `DocumentMetadata` placement | Nested sub-model on `RulingSections` | Additive; no breaking changes to `Ruling` top-level |
| Parser priority | Sentencia headers tried first | Prevents false Auto matches in embedded quotes |
| Juzgados (Parser C) | Out of scope | Insufficient fixtures; `'other'` scope unchanged |

---

## Tasks

### Layer 1 — Models (foundation, no dependencies)

- [ ] **Task 1.1** — Add `DocumentMetadata` Pydantic model to `src/mcp_cendoj/models.py`

  **Files affected**: `src/mcp_cendoj/models.py`

  Add before `RulingSections`:
  ```python
  class DocumentMetadata(BaseModel):
      """Structured metadata extracted from the CENDOJ PDF header block."""
      roj: str | None = None
      ecli_from_pdf: str | None = None
      id_cendoj: str | None = None
      organo: str | None = None
      sede: str | None = None
      fecha_raw: str | None = None        # "DD/MM/YYYY"
      ponente: str | None = None
      tipo_resolucion: str | None = None  # "Sentencia" | "Auto" | "Providencia"
      nro_recurso: str | None = None
      nro_resolucion: str | None = None
      seccion: str | None = None
  ```

  **Acceptance criteria**:
  - `DocumentMetadata` can be instantiated with all fields `None` (graceful fallback)
  - `pyright --strict` passes with zero errors on `models.py`

- [ ] **Task 1.2** — Extend `RulingSections` in `src/mcp_cendoj/models.py`

  **Files affected**: `src/mcp_cendoj/models.py`

  Changes:
  - `tribunal_scope: Literal['ts_tc', 'collegial', 'other']` — add `'collegial'` variant
  - `metadata: DocumentMetadata | None = Field(default=None, description='...')`

  Update docstring on `tribunal_scope` field.

  **Acceptance criteria**:
  - `RulingSections(raw_text='x')` still constructs without error (all new fields default)
  - `tribunal_scope='collegial'` accepted by Pydantic validator
  - `pyright --strict` passes

### Layer 2 — Parser core (depends on Layer 1)

- [ ] **Task 2.1** — Add `_HEADER_RE` regex and `extract_header_metadata()` to `src/mcp_cendoj/parser.py` (Parser 0)

  **Files affected**: `src/mcp_cendoj/parser.py`

  Add module-level regex:
  ```python
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
  ```

  Add function:
  ```python
  def extract_header_metadata(text: str) -> DocumentMetadata | None:
      """Extract structured fields from the CENDOJ PDF header block.

      Returns None when the header block is not found or is malformed.
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
  ```

  **Acceptance criteria**:
  - Given the text of `ts_ruling.txt`, returns `DocumentMetadata` with:
    - `roj == 'ATS 3898/2026'`
    - `ponente` containing `'CORDOBA'` (case-insensitive)
    - `tipo_resolucion == 'Auto'`
    - `fecha_raw == '20/04/2026'`
  - Given the text of `ts_sentence.txt`, returns `DocumentMetadata` with:
    - `roj == 'STS 1234/2020'`
    - `tipo_resolucion == 'Sentencia'`
  - Given empty string or unrelated text, returns `None`

- [ ] **Task 2.2** — Add `_AUTO_SECTION_RE` regex and extend `split_sections()` for Auto format (Parser B)

  **Files affected**: `src/mcp_cendoj/parser.py`

  Add module-level regex:
  ```python
  _AUTO_SECTION_RE = re.compile(
      r'(HECHOS|ANTECEDENTES)'
      r'|(RAZONAMIENTOS\s+JUR[IÍ]DICOS|RAZONAMIENTOS|FUNDAMENTOS\s+JUR[IÍ]DICOS)'
      r'|(LA\s+SALA\s+ACUERDA\s*:|ACUERDA\s*:|SE\s+ACUERDA\s*:)',
      re.IGNORECASE,
  )
  ```

  Refactor `split_sections()`:
  - Try Sentencia regex (`_SECTION_RE`) first
  - If < 3 headings found, try Auto regex (`_AUTO_SECTION_RE`) mapping group 1→antecedentes,
    group 2→fundamentos, group 3→fallo
  - Return `(antecedentes, fundamentos, fallo, True)` on first successful 3-section match

  The function signature is unchanged: `split_sections(text: str) -> tuple[str | None, str | None, str | None, bool]`.

  **Acceptance criteria**:
  - `split_sections` on `ts_ruling.txt` text returns `parse_successful=True` with all three sections non-`None`
  - `split_sections` on `ts_sentence.txt` text still returns `parse_successful=True` (regression)
  - `split_sections('HECHOS\nA.\nRAZONAMIENTOS JURÍDICOS\nB.\nLA SALA ACUERDA:\nC.')` → `ok=True`
  - `split_sections('HECHOS\nA.\nRAZONAMIENTOS JURÍDICOS\nB.\nACUERDA:\nC.')` → `ok=True`
  - `split_sections('no headers')` → `ok=False` (regression)

- [ ] **Task 2.3** — Extend `_detect_scope()` and `extract_sections()` for collegial courts

  **Files affected**: `src/mcp_cendoj/parser.py`

  Add module-level regex:
  ```python
  _COLLEGIAL_ECLI_RE = re.compile(
      r'^ECLI:ES:(AN|TSJ[A-Z]+|AP[A-Z]+):',
      re.IGNORECASE,
  )
  ```

  Update `_detect_scope`:
  ```python
  def _detect_scope(ecli: str | None) -> str:
      if ecli and _TS_TC_ECLI_RE.match(ecli):
          return 'ts_tc'
      if ecli and _COLLEGIAL_ECLI_RE.match(ecli):
          return 'collegial'
      return 'other'
  ```

  Update `extract_sections`: when `scope in ('ts_tc', 'collegial')`, attempt `split_sections()`.
  Extract `metadata` via `extract_header_metadata(plain_text)` for ALL documents (all scopes).

  **Critical**: Use the detected `scope` variable in the return statement — do NOT hardcode
  `'other'` or `'ts_tc'`. The complete return logic must be:

  ```python
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
      tribunal_scope=scope,   # USE detected scope, not hardcoded value
      antecedentes=antecedentes,
      fundamentos_derecho=fundamentos,
      fallo=fallo,
      metadata=metadata,
  )
  ```

  **Acceptance criteria**:
  - `_detect_scope('ECLI:ES:AN:2024:1234')` → `'collegial'`
  - `_detect_scope('ECLI:ES:TSJM:2024:1234')` → `'collegial'`
  - `_detect_scope('ECLI:ES:TSJCAT:2024:1234')` → `'collegial'`
  - `_detect_scope('ECLI:ES:APBA:2024:1234')` → `'collegial'`
  - `_detect_scope('ECLI:ES:TS:2024:1234')` → `'ts_tc'` (regression)
  - `_detect_scope('ECLI:ES:JPI:2024:1234')` → `'other'`
  - `_detect_scope(None)` → `'other'` (regression)
  - `extract_sections(pdf_bytes, ecli='ECLI:ES:TSJM:2020:1234')` → `tribunal_scope == 'collegial'`
  - `metadata` field populated when PDF text contains the CENDOJ header block

### Layer 3 — Test fixtures (independent — no code dependencies)

- [ ] **Task 3.1** — Create `tests/fixtures/tsj_sentence.txt`

  Minimal TSJ Sentencia with full metadata header and canonical (`ANTECEDENTES / FUNDAMENTOS / FALLO`) sections.

  ```
  JURISPRUDENCIA
  Roj: STSJ M 9999/2024 - ECLI:ES:TSJM:2024:9999
  Id Cendoj:28079310012024100001
  Órgano:Tribunal Superior de Justicia de Madrid. Sala de lo Contencioso
  Sede:Madrid
  Sección:1
  Fecha:10/01/2024
  Nº de Recurso:999/2022
  Nº de Resolución:
  Ponente:MAGISTRADO PONENTE NOMBRE
  Tipo de Resolución:Sentencia

  ANTECEDENTES DE HECHO

  PRIMERO.- El recurrente interpuso recurso contencioso-administrativo.

  FUNDAMENTOS DE DERECHO

  PRIMERO.- Conforme al artículo 106 CE la jurisdicción contencioso-administrativa controla la actividad administrativa.

  FALLO

  Se estima el recurso. Se anula el acto impugnado.
  ```

  **Acceptance criteria**: File exists, `utf-8` encoded, contains the three section headers.

- [ ] **Task 3.2** — Create `tests/fixtures/an_sentence.txt`

  Minimal Audiencia Nacional Sentencia with full metadata header and canonical sections.

  ```
  JURISPRUDENCIA
  Roj: SAN 9999/2024 - ECLI:ES:AN:2024:9999
  Id Cendoj:28079220012024100001
  Órgano:Audiencia Nacional. Sala de lo Contencioso
  Sede:Madrid
  Sección:1
  Fecha:15/03/2024
  Nº de Recurso:888/2022
  Nº de Resolución:
  Ponente:MAGISTRADO PONENTE AN
  Tipo de Resolución:Sentencia

  ANTECEDENTES DE HECHO

  PRIMERO.- La parte actora impugna la resolución del Ministerio del Interior.

  FUNDAMENTOS DE DERECHO

  PRIMERO.- La Sala analiza la legalidad de la resolución impugnada.

  FALLO

  Se desestima el recurso. Se confirma el acto impugnado. Sin costas.
  ```

  **Acceptance criteria**: File exists, `utf-8` encoded, contains the three section headers, ECLI prefix `AN`.

- [ ] **Task 3.3** — Create `tests/fixtures/tsj_auto.txt`

  Minimal TSJ Auto with full metadata header and Auto-format sections.

  ```
  JURISPRUDENCIA
  Roj: ATSJ M 9999/2024 - ECLI:ES:TSJM:2024:9999A
  Id Cendoj:28079310012024200001
  Órgano:Tribunal Superior de Justicia de Madrid. Sala de lo Civil
  Sede:Madrid
  Sección:1
  Fecha:10/01/2024
  Nº de Recurso:999/2023
  Nº de Resolución:
  Ponente:MAGISTRADO PONENTE NOMBRE
  Tipo de Resolución:Auto

  HECHOS

  PRIMERO.- La parte solicitó la adopción de medidas cautelares.

  RAZONAMIENTOS JURÍDICOS

  PRIMERO.- Conforme al artículo 130 LJCA, para acordar la medida cautelar deben concurrir los requisitos legales.

  LA SALA ACUERDA:

  Inadmitir la solicitud de medida cautelar.
  ```

  **Acceptance criteria**: File exists, `utf-8` encoded, contains `HECHOS`, `RAZONAMIENTOS JURÍDICOS`, `LA SALA ACUERDA:`.

### Layer 4 — Unit and integration tests (depends on Layer 2 + 3)

- [ ] **Task 4.1** — Add `TestSplitSectionsAutoFormat` class to `tests/tools/test_parser.py`

  **Files affected**: `tests/tools/test_parser.py`

  New class after `TestSplitSectionsDirect`:
  ```python
  class TestSplitSectionsAutoFormat:
      """Unit tests for the Auto/Providencia heading variant of split_sections."""
  ```

  Test methods (all call `split_sections()` directly — no PDF, fully deterministic):

  | Method | Input | Expected |
  |--------|-------|---------|
  | `test_hechos_razonamientos_la_sala_acuerda` | `HECHOS\nA.\nRAZONAMIENTOS JURÍDICOS\nB.\nLA SALA ACUERDA:\nC.` | `ok=True`, all three non-`None` |
  | `test_acuerda_variant` | `HECHOS\nA.\nRAZONAMIENTOS JURÍDICOS\nB.\nACUERDA:\nC.` | `ok=True` |
  | `test_se_acuerda_variant` | `HECHOS\nA.\nRAZONAMIENTOS\nB.\nSE ACUERDA:\nC.` | `ok=True` |
  | `test_fundamentos_juridicos_variant` | `HECHOS\nA.\nFUNDAMENTOS JURÍDICOS\nB.\nACUERDA:\nC.` | `ok=True` |
  | `test_only_hechos_not_parsed` | `HECHOS\nFacts only.` | `ok=False` |
  | `test_case_insensitive_auto_headers` | Mixed-case `hechos`/`razonamientos jurídicos` | `ok=True` |
  | `test_sentencia_headers_still_work` | Canonical `ts_sentence.txt` full text | `ok=True` (regression) |
  | `test_real_auto_fixture_parsed` | Content of `tests/fixtures/ts_ruling.txt` | `ok=True`, `fallo` contains `'ACUERDA'` |

  **Acceptance criteria**: 8 tests pass, no regressions in existing `TestSplitSectionsDirect`.

- [ ] **Task 4.2** — Add `TestDetectScope` class to `tests/tools/test_parser.py`

  **Files affected**: `tests/tools/test_parser.py`

  New class testing `_detect_scope` directly (import it: `from mcp_cendoj.parser import _detect_scope`).

  | Method | ECLI input | Expected |
  |--------|-----------|---------|
  | `test_ts_returns_ts_tc` | `ECLI:ES:TS:2024:1234` | `'ts_tc'` |
  | `test_tc_returns_ts_tc` | `ECLI:ES:TC:2024:1234` | `'ts_tc'` |
  | `test_an_returns_collegial` | `ECLI:ES:AN:2024:1234` | `'collegial'` |
  | `test_tsjm_returns_collegial` | `ECLI:ES:TSJM:2024:1234` | `'collegial'` |
  | `test_tsjcat_returns_collegial` | `ECLI:ES:TSJCAT:2024:1234` | `'collegial'` |
  | `test_apba_returns_collegial` | `ECLI:ES:APBA:2024:1234` | `'collegial'` |
  | `test_jpi_returns_other` | `ECLI:ES:JPI28:2024:1234` | `'other'` |
  | `test_none_returns_other` | `None` | `'other'` |
  | `test_invalid_prefix_returns_other` | `'NOT-AN-ECLI'` | `'other'` |

  **Acceptance criteria**: 9 tests pass.

- [ ] **Task 4.3** — Add `TestExtractHeaderMetadata` class to `tests/tools/test_parser.py`

  **Files affected**: `tests/tools/test_parser.py`

  New class testing `extract_header_metadata(text)` directly.

  | Method | Description |
  |--------|-------------|
  | `test_ts_ruling_fixture_metadata` | Text of `ts_ruling.txt` → `roj='ATS 3898/2026'`, `ponente` contains `CORDOBA`, `tipo_resolucion='Auto'` |
  | `test_ts_sentence_fixture_metadata` | Text of `ts_sentence.txt` → `roj='STS 1234/2020'`, `tipo_resolucion='Sentencia'` |
  | `test_tsj_sentence_fixture_metadata` | Text of `tsj_sentence.txt` → `organo` contains `Madrid`, `tipo_resolucion='Sentencia'` |
  | `test_returns_none_for_empty_text` | `''` → `None` |
  | `test_returns_none_for_prose_only` | `'Some legal text without headers.'` → `None` |
  | `test_fecha_raw_preserved_as_string` | Any fixture → `fecha_raw` in `DD/MM/YYYY` format |
  | `test_id_cendoj_extracted` | Any fixture with Id Cendoj line → `id_cendoj` is non-`None` and digits-only |

  **Acceptance criteria**: 7 tests pass.

- [ ] **Task 4.4** — Add `TestExtractSectionsCollegialScope` class to `tests/tools/test_parser.py`

  **Files affected**: `tests/tools/test_parser.py`

  New class after `TestExtractSectionsWithSyntheticText` (follows its lenient `if result.parse_successful` pattern):

  | Method | ECLI | Fixture | Expected |
  |--------|------|---------|---------|
  | `test_tsjm_ecli_sets_collegial_scope` | `ECLI:ES:TSJM:2020:1234` | `tsj_sentence.txt` | `tribunal_scope == 'collegial'` |
  | `test_an_ecli_sets_collegial_scope` | `ECLI:ES:AN:2020:1234` | `an_sentence.txt` | `tribunal_scope == 'collegial'` |
  | `test_tsj_ecli_with_canonical_headers_can_parse` | `ECLI:ES:TSJM:2024:9999` | `tsj_sentence.txt` | If `parse_successful`: `antecedentes` non-`None` |
  | `test_tsj_auto_can_parse` | `ECLI:ES:TSJM:2024:9999A` | `tsj_auto.txt` | If `parse_successful`: `fallo` non-`None` |
  | `test_tsj_prose_only_not_parsed` | `ECLI:ES:TSJM:2020:1234` | `tsj_ruling.txt` (no headers) | `parse_successful=False` (regression with new scope) |
  | `test_jpi_ecli_returns_other_scope` | `ECLI:ES:JPI28:2024:1234` | `tsj_ruling.txt` | `tribunal_scope == 'other'`, `parse_successful=False` |

  **Note on regression**: The existing test `test_tsj_ecli_sets_other_scope` in `TestExtractSectionsWithSyntheticText` must be updated to expect `tribunal_scope == 'collegial'` (TSJ is now collegial). This is a breaking change in the test assertion — see Task 5.1.

  **Acceptance criteria**: 6 tests pass, covers all new scope paths.

- [ ] **Task 4.5** — Add parser integration tests to `tests/test_mcp_integration.py`

  **Files affected**: `tests/test_mcp_integration.py`

  Add a `# --- parser scope integration tests ---` section with 3 async test functions that go through the full MCP stack (mock HTTP, real `extract_sections`, real `split_sections`):

  | Function | Setup | Assertions |
  |----------|-------|-----------|
  | `test_get_ruling_text_ts_auto_parses_hechos` | `document_bytes=ts_ruling.pdf bytes`, ECLI `ECLI:ES:TS:2026:3898A` | JSON result has `sections.parse_successful=True`, `sections.tribunal_scope='ts_tc'`, `sections.antecedentes` non-empty |
  | `test_get_ruling_text_tsj_sentencia_parses_sections` | synthetic PDF from `tsj_sentence.txt`, ECLI `ECLI:ES:TSJM:2024:9999` | `sections.tribunal_scope='collegial'`; if `parse_successful`: `antecedentes` present |
  | `test_get_ruling_text_metadata_populated` | `document_bytes=ts_ruling.pdf bytes`, ECLI `ECLI:ES:TS:2026:3898A` | `sections.metadata` is non-`None`, `sections.metadata.tipo_resolucion == 'Auto'`, `sections.metadata.ponente` contains `'Córdoba'` or `'CORDOBA'` |

  All three tests use the same `_mcp_session` inline pattern already established in the file.
  These are **tool-level tests** (calling `get_ruling_text` directly via `session.call_tool`). They
  do **NOT** fix or remove `test_get_ruling_text_resource` — that xfail is explicitly Out of Scope.

  **Mock HTTP setup**:
  - For TS tests: `make_cendoj_client((FIXTURES / 'ecli_lookup.html').read_text(), document_url=_ECLI_LOOKUP_DOC_URL, document_bytes=pdf_bytes)` — same pattern as the existing xfail test.
  - For TSJ tests: reuse `ecli_lookup.html` as the mock POST response (HTML content mismatch is fine — mock doesn't validate ECLI). Generate the synthetic PDF inline: `_make_minimal_pdf((FIXTURES / 'tsj_sentence.txt').read_text())`. Use the same `_ECLI_LOOKUP_DOC_URL` for `document_url`.

  **Acceptance criteria**: All 3 tests pass without `xfail`. Coverage of the document tool +
  parser integration path reaches 100%.

### Layer 5 — Update existing tests (depends on Layer 1–4)

- [ ] **Task 5.1** — Update `TestExtractSectionsWithSyntheticText` in `tests/tools/test_parser.py`

  **Files affected**: `tests/tools/test_parser.py`

  Required change: `test_tsj_ecli_sets_other_scope` must be renamed and updated:

  ```python
  # Before:
  def test_tsj_ecli_sets_other_scope(self) -> None:
      ...
      assert result.tribunal_scope == 'other'

  # After:
  def test_tsj_ecli_sets_collegial_scope(self) -> None:
      ...
      assert result.tribunal_scope == 'collegial'
  ```

  `test_other_tribunal_no_sections` in `TestExtractSectionsSectionParsing` also uses
  TSJM ECLI. The `parse_successful=False` assertion still holds (no section headers in
  `tsj_ruling.txt`) but `tribunal_scope` assertion should NOT be present in that test
  (it already isn't — only `parse_successful` and section fields are checked there).

  **Acceptance criteria**: All existing tests that were green remain green.

---

## Test Plan

| Layer | Verification method |
|-------|-------------------|
| Layer 1 (Models) | `pyright --strict`; `pytest tests/test_models.py` |
| Task 2.1 (Parser 0) | `TestExtractHeaderMetadata` — 7 deterministic unit tests on raw text (no PDF) |
| Task 2.2 (Parser B) | `TestSplitSectionsAutoFormat` — 8 deterministic unit tests on raw text (no PDF) |
| Task 2.3 (scope extension) | `TestDetectScope` — 9 deterministic unit tests; `TestExtractSectionsCollegialScope` — 6 synthetic-PDF tests |
| Layer 3 (Fixtures) | Checked in tests via `FIXTURES / 'tsj_sentence.txt'` etc.; CI fails if missing |
| Layer 4 (Integration) | 3 MCP integration tests with real PDF bytes + mocked HTTP |
| Layer 5 (Regression) | Full `pytest` run — all pre-existing tests must pass |

**TDD order within each task**: write failing test → implement → green.

**TDD ordering note**: Tasks 4.1 (`TestSplitSectionsAutoFormat`), 4.2 (`TestDetectScope`), and
4.3 (`TestExtractHeaderMetadata`) call parser functions directly on raw text with no PDF or
model dependencies. They SHOULD be written **before** the corresponding Layer 2 implementation
tasks (2.2, 2.3, 2.1 respectively) to enforce TDD at the unit level. Layer 3 fixtures can be
created in parallel with Layer 2 (they have no code dependencies).

**Coverage gate**: 80% branch coverage enforced by `pytest-cov`. New code paths must be
covered. Target: parser.py at ≥90% branch after this change.

**reportlab leniency**: Tests that build synthetic PDFs via `_make_minimal_pdf()` must use
the `if result.parse_successful:` guard to remain green in environments without `reportlab`.
Tests that call `split_sections()` or `extract_header_metadata()` directly on raw text
have no such constraint and must assert unconditionally.

---

## Integration Verification

After all layers are complete, run the full quality gate:

```bash
make all          # format → lint → typecheck → test
```

Smoke checks (require network access — run manually, not in CI):

```bash
# Verify Parser B on a real TS Auto
uv run python -c "
from mcp_cendoj.parser import extract_sections
from pathlib import Path
pdf = Path('tests/fixtures/ts_ruling.pdf').read_bytes()
r = extract_sections(pdf, ecli='ECLI:ES:TS:2026:3898A')
print('parse_successful:', r.parse_successful)
print('tribunal_scope:', r.tribunal_scope)
print('metadata.tipo_resolucion:', r.metadata.tipo_resolucion if r.metadata else None)
print('antecedentes[:80]:', (r.antecedentes or '')[:80])
"
```

Expected output:
```
parse_successful: True
tribunal_scope: ts_tc
metadata.tipo_resolucion: Auto
antecedentes[:80]: PRIMERO.La Procuradora Doña Ana María Capilla Montes...
```

---

## Out of Scope

- **Parser C (Juzgados)** — `HECHOS PROBADOS / FUNDAMENTOS JURÍDICOS / FALLO` variant for
  `JPI`, `JS`, `JCA`, `JM`, `JVM`. Deferred: no representative fixtures, `'other'` scope
  behavior unchanged.
- **Numbered item extraction** — `<item numero="PRIMERO">` wrapping within sections. Deferred:
  requires XML output format version bump strategy.
- **XML format version 2** — `<court_document source="cendoj" version="2">` with nested
  `<metadata>` and typed sections. Deferred: API versioning strategy not decided.
- **`tsj_ruling.txt` enrichment** — kept as-is; it serves as a regression anchor for the
  "headers absent → `parse_successful=False`" path.
- **`test_get_ruling_text_resource` xfail fix** — the MCP `AnyUrl` ECLI URI parsing bug is
  a separate issue. Not addressed here.
