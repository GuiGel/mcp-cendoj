# Plan: cendoj-mcp-server

Created: 2026-04-29 | Branch: `feat/cendoj-mcp-server` | Tier: 0 (Solo — inline research)

## Summary

Build `mcp_cendoj`: a Python MCP server that exposes Spain's CENDOJ judicial database
to AI assistants via four tools and one resource. The server enables LLMs to search
for court rulings, resolve documents by ECLI identifier, fetch full structured text,
and check whether a ruling has been superseded by later case law — all with an
explicit provenance envelope that prevents confident misuse of uncertain legal data.

Source of requirements: two rounds of multi-perspective brainstorming (2026-04-29)
covering architecture, failure modes, and implementation sequencing.

---

## Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Use `mcp.server.fastmcp.FastMCP`, not low-level `mcp.Server` | Schema auto-generation from type annotations; existing entrypoint wired. See ADR-0001. |
| D2 | Direct `httpx` POST scraping, not headless browser | Zero extra heavyweight deps for MVP; session persistence via `AsyncClient`. See ADR-0002. |
| D3 | Provenance envelope: `fetched_at` + `freshness: Literal["unknown"]` | CENDOJ exposes no document modification date. See ADR-0003. |
| D4 | `SupersededResult` has no `superseded: bool` field | Citation coverage is incomplete (no citation graph); legal conclusions belong to the LLM. See ADR-0003. |
| D5 | Section extraction scoped to TS/TC; `raw_text` fallback for all others | Prevents silent mis-labelling across 30 heterogeneous tribunal IT systems. See ADR-0004. |
| D6 | `sqlite3` (stdlib) for disk caching, 24h TTL, stored in `~/.cache/mcp-cendoj/` | Zero extra dependency; court rulings are immutable once published. |
| D7 | Build sequence: models → constants → lookup_by_ecli → search_rulings → document resource → check_if_superseded | Models unblock all tools; ECLI URL archaeology unblocks both lookup and search; parsing and supersession depend on both. |
| D8 | `get_ruling_text` registered as `@app.resource("cendoj://{ecli}")`, NOT `@app.tool()`. Add `cendoj_uri: str` field to `Ruling` so every tool response hands the LLM the URI to use. | Resources are the semantically correct MCP primitive for document content. The `cendoj_uri` field in `Ruling` ensures the LLM always has a concrete URI to request, without needing to independently construct the `cendoj://` scheme. |

---

## Architecture

### ADRs Created

- [ADR-0001](../adr/ADR-0001-fastmcp-over-low-level-server.md) — Use `FastMCP` high-level API
- [ADR-0002](../adr/ADR-0002-cendoj-http-integration-strategy.md) — CENDOJ HTTP integration strategy
- [ADR-0003](../adr/ADR-0003-provenance-envelope-design.md) — Provenance envelope design
- [ADR-0004](../adr/ADR-0004-section-extraction-scope.md) — Section extraction scope and fallback

### Module Layout

```
src/mcp_cendoj/
    __init__.py          # FastMCP app instance, main(), all tool/resource registrations
    models.py            # Pydantic models: Ruling, RulingSections, SearchResult, SupersededResult
    constants.py         # CENDOJ URLs, browser-mimicking headers (locked after live capture)
    http.py              # Async httpx client: retry, rate limiting (1 req/s), circuit breaker
    cache.py             # sqlite3 cache: get/set/clear, 24h TTL, ~/.cache/mcp-cendoj/
    parser.py            # Section extraction: TS/TC structured + raw_text fallback
    tools/
        __init__.py
        lookup.py        # lookup_by_ecli()
        search.py        # search_rulings()
        document.py      # get_ruling_text() resource
        superseded.py    # check_if_superseded()

tests/
    __init__.py
    test_main.py              # existing smoke test (update after Layer 1)
    fixtures/
        ts_ruling.html        # saved TS HTML for parser tests
        an_ruling.html        # saved AN HTML for parser tests
        tsj_ruling.html       # saved TSJ HTML (raw_text path)
        search_results.html   # saved CENDOJ search response
    test_models.py
    test_parser.py
    test_cache.py
    tools/
        test_lookup.py
        test_search.py
        test_document.py
        test_superseded.py
```

### Key Types

```python
# models.py (condensed)
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field

class RulingSections(BaseModel):
    antecedentes: str | None = None
    fundamentos_derecho: str | None = None
    fallo: str | None = None
    raw_text: str                              # always populated
    parse_successful: bool
    tribunal_scope: Literal['ts_tc', 'other']

class Ruling(BaseModel):
    ecli: str | None
    cendoj_internal_id: str | None             # stable dedup key
    is_ecli_resolved: bool
    title: str
    court: str
    date: str
    sections: RulingSections
    source_url: str
    cendoj_uri: str                            # e.g. "cendoj://ECLI:ES:TS:2020:1234" — hand to LLM so it can call the resource
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    freshness: Literal['unknown'] = 'unknown'
    warning: str | None = None

class SearchResult(BaseModel):
    ecli: str | None
    title: str
    court: str
    date: str
    snippet: str
    url: str
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    freshness: Literal['unknown'] = 'unknown'

class SupersededResult(BaseModel):
    checked_ecli: str
    later_rulings: list[SearchResult]
    citations_found: int
    is_likely_superseded: bool                 # "likely" qualifier is intentional
    search_method: Literal['ecli_fulltext']
    confidence: Literal['medium'] = 'medium'   # structurally impossible to set to "high"
    warning: str = (
        'Citation coverage is incomplete — CENDOJ has no citation graph. '
        'Absence of results does NOT confirm validity. '
        'Spanish courts also cite by ROJ identifier and popular case name.'
    )
```

---

## Tasks

### Layer 1 — Foundation (~2 h)

*No network calls. Pure Python. Unblocks everything.*

- [ ] **1.1 — Update `pyproject.toml` dependencies**
  Files: `pyproject.toml`
  Add to `dependencies`:
  ```toml
  "mcp[cli]>=1.0,<2",
  "httpx>=0.27",
  "beautifulsoup4>=4.12",
  "lxml>=4.9",
  "pydantic>=2.7",
  "platformdirs>=4.0",
  ```
  Add to `[dependency-groups] dev`:
  ```toml
  "respx>=0.21",
  "pytest-asyncio>=0.23",
  ```
  Add to `[tool.pytest.ini_options]`:
  ```toml
  [tool.pytest.ini_options]
  asyncio_mode = "auto"
  ```
  Run `uv sync` to lock. Acceptance: `make lint` passes, `uv run python -c "from mcp.server.fastmcp import FastMCP"` exits 0.

- [ ] **1.2 — Create `src/mcp_cendoj/models.py`**
  Files: `src/mcp_cendoj/models.py`, `tests/test_models.py`
  Implement `RulingSections`, `Ruling`, `SearchResult`, `SupersededResult` as per Key Types above.
  Acceptance: `uv run pyright src/mcp_cendoj/models.py` clean; tests cover: field defaults, `freshness` literal constraint, `confidence` literal constraint, `fetched_at` is UTC.

- [ ] **1.3 — Create `src/mcp_cendoj/constants.py`** *(requires live browser capture first)*
  Files: `src/mcp_cendoj/constants.py`
  Pre-work:
  1. Open https://www.poderjudicial.es/search/indexAN.jsp in browser, run a search, inspect XHR in DevTools, capture exact POST URL + form field names + required headers.
  2. **Go/no-go gate**: run a throwaway `httpx` script asserting the response contains at least one ruling. If the endpoint returns 403, a CSRF-error body, or an empty result set after 3 retries with session cookies → **stop and escalate to the Playwright branch** (open a follow-up issue; do not continue with Layer 2 tasks until resolved).
  3. Run a second assertion: POST with `query='"ECLI:ES:TS:XXXX:YYYY"'` (a known published ECLI), assert the response contains that ECLI in a result. If colons break the query, test URL-encoding the colon (`%3A`) inside the quoted string and record the working encoding in `constants.py` comments.
  4. Determine whether `CENDOJ_ECLI_URL_TEMPLATE` resolves to (A) the full document page or (B) a metadata/redirect page — document the conclusion as a comment in `constants.py`, as it determines the Task 3.3 fetch architecture.
  Contents:
  ```python
  CENDOJ_SEARCH_URL: str             # exact POST endpoint URL from DevTools
  CENDOJ_ECLI_URL_TEMPLATE: str      # URL with {ecli} placeholder
  DEFAULT_HEADERS: dict[str, str]    # ONLY: User-Agent, Referer, Accept-Language
                                     # MUST NOT include Cookie, Authorization, or any session header
  MAX_RESULTS_DEFAULT: int = 10
  MAX_RESULTS_CAP: int = 100         # enforced upper bound in search_rulings
  RATE_LIMIT_RPS: int = 1
  CONNECT_TIMEOUT_S: float = 5.0
  READ_TIMEOUT_S: float = 30.0
  MAX_RESPONSE_BYTES: int = 10_485_760   # 10 MB hard cap on HTTP response bodies
  MAX_HTML_BYTES: int = 2_000_000        # 2 MB hard cap before BeautifulSoup parsing
  ```
  Acceptance: constants importable; go/no-go live POST passes; `DEFAULT_HEADERS` keys must not match `(?i)^(cookie|authorization|x-csrf|x-auth|session)`.

- [ ] **1.4 — Wire FastMCP entry point**
  Files: `src/mcp_cendoj/__init__.py`
  Replace stub `main()`:
  ```python
  from mcp.server.fastmcp import FastMCP
  app = FastMCP('mcp-cendoj')

  def main() -> None:
      """Entry point for the mcp-cendoj MCP server."""
      app.run()
  ```
  Acceptance: `uv run mcp-cendoj --help` exits without traceback; `test_main_runs` smoke test still passes (update to not call `app.run()` directly — mock it).

### Layer 2 — HTTP client + core tools (~4 h, depends on Layer 1)

*ECLI lookup first (forces URL archaeology); search second (reuses same client).*

- [ ] **2.1 — Create `src/mcp_cendoj/http.py`**
  Files: `src/mcp_cendoj/http.py`
  Implement `CendojClient` with:
  - `asyncio.Semaphore(1)` + `asyncio.sleep` for 1 req/s rate limiting. Note: rate limit is per-process; concurrent Claude Desktop sessions each have their own semaphore — document this limitation in the class docstring.
  - **Module-level singleton** `AsyncClient` (not per-call): instantiate once in `CendojClient.__init__()` or via FastMCP lifespan hooks (`@app.on_startup` / `@app.on_shutdown`) for proper lifecycle. Avoids TLS handshake overhead on every tool call.
  - `httpx.AsyncClient` with explicit timeout: `httpx.Timeout(connect=CONNECT_TIMEOUT_S, read=READ_TIMEOUT_S, write=10.0, pool=5.0)` — **required**, no default timeout is not acceptable.
  - Response size guard: check `Content-Length` header; if body exceeds `MAX_RESPONSE_BYTES`, raise `CendojNetworkError('Response too large')`.
  - Retry decorator: up to 3 attempts, exponential backoff (1s, 2s, 4s) + jitter on 429/503.
  - `CendojNetworkError(Exception)` wrapping `httpx.HTTPError` (including `httpx.TimeoutException`) and empty-result silences.
  Acceptance: unit tests with `respx` covering: success, 429 retry, 503 retry, timeout (`side_effect=httpx.ReadTimeout`), empty-result error, response-too-large error.

- [ ] **2.2 — Implement `lookup_by_ecli` tool**
  Files: `src/mcp_cendoj/tools/lookup.py`, `tests/tools/test_lookup.py`, `tests/tools/__init__.py`
  Signature: `async def lookup_by_ecli(ecli: str) -> Ruling`
  Logic:
  1. Normalize: `ecli = ecli.strip().upper()`.
  2. Validate with strict regex: `re.fullmatch(r"ECLI:[A-Z]{2}:[A-Z0-9_-]+:[0-9]{4}:[A-Z0-9._-]+", ecli)` — raise `ValueError(f"Invalid ECLI: {ecli!r}")` if no match.
  3. URL-encode: `safe_ecli = urllib.parse.quote(ecli, safe='')` before substitution into `CENDOJ_ECLI_URL_TEMPLATE`.
  4. GET URL via `CendojClient`.
  5. Parse response HTML → `Ruling` (populate `raw_text` via `BeautifulSoup(html, "lxml").get_text(separator="\n")` at minimum; `sections.parse_successful = False` — structured section extraction is Layer 3).
  6. Assert exactly one result; raise `ECLIAmbiguousError` if `len != 1`, `ECLINotFoundError` if `len == 0`.
  Register: `@app.tool()` in `__init__.py`.
  Create `tests/tools/__init__.py` (empty file — needed for pytest sub-package discovery).
  Acceptance: unit tests cover success, ambiguous ECLI, not-found ECLI, non-ES ECLI rejection, injection-attempt ECLI (`'ECLI:ES:TS:2020:1@evil.com'`) raises `ValueError`; mock uses saved HTML fixture.

- [ ] **2.3 — Implement `search_rulings` tool**
  Files: `src/mcp_cendoj/tools/search.py`, `tests/tools/test_search.py`
  Signature: `async def search_rulings(query: str, max_results: Annotated[int, Field(ge=1, le=100)] = 10) -> list[SearchResult]`
  Logic:
  - Clamp: `max_results = min(max_results, MAX_RESULTS_CAP)` (defense-in-depth even with Pydantic constraint).
  - POST to `CENDOJ_SEARCH_URL` with form data, parse result list, return `SearchResult` list.
  Docstring must include: rate limiting caveat (1 req/s per process — concurrent sessions are not serialised), ToS note, freshness warning.
  Register: `@app.tool()` in `__init__.py`.
  Acceptance: unit tests cover: results returned, empty results → `CendojNetworkError`, max_results clamped at 100, `respx` mock returns saved HTML fixture.

### Layer 3 — Full-text resource + parsing + cache (~4 h, depends on Layer 2)

- [ ] **3.1 — Create `src/mcp_cendoj/parser.py`**
  Files: `src/mcp_cendoj/parser.py`, `tests/fixtures/ts_ruling.html`, `tests/fixtures/an_ruling.html`, `tests/fixtures/tsj_ruling.html`, `tests/test_parser.py`
  **TDD gate**: fixtures MUST be committed in a separate commit before any parser code is written. This ensures tests validate real CENDOJ HTML, not the developer's assumption of its structure.
  Pre-work:
  1. Save 3–5 real CENDOJ HTML pages per court type (TS, AN, TSJ) as test fixtures.
  2. Run `BeautifulSoup(fixture_html, "lxml").get_text(separator="\n")` on `ts_ruling.html` and assert the output contains the exact header string the section regex will match. Adjust `separator` argument if needed and document the choice.
  Implement `extract_sections(html: str, ecli: str | None = None) -> RulingSections`:
  - Guard: if `len(html) > MAX_HTML_BYTES`, raise `CendojParseError('HTML too large')`.
  - Parse: **always** use `BeautifulSoup(html, "lxml")` (not default `html.parser` — lxml is 3-5× faster for large documents).
  - `raw_text` always populated from `soup.get_text(separator="\n")`.
  - Wrap `raw_text` in content boundary for LLM safety: `raw_text = f'<court_document source="cendoj">\n{plain_text}\n</court_document>'`.
  - Detect tribunal from ECLI prefix or HTML metadata → set `tribunal_scope`.
  - TS/TC path: regex split on `ANTECEDENTES DE HECHO`, `FUNDAMENTOS DE DERECHO`, `FALLO`.
  - Other path: set all section fields `None`, `parse_successful = False`.
  Acceptance: tests cover TS ruling (all sections extracted), TSJ ruling (raw_text only, `parse_successful=False`), unknown HTML (raw_text fallback, no exception), HTML > `MAX_HTML_BYTES` raises `CendojParseError`.

- [ ] **3.2 — Create `src/mcp_cendoj/cache.py`**
  Files: `src/mcp_cendoj/cache.py`, `tests/test_cache.py`
  Implement `DiskCache` with:
  - `sqlite3` backend, schema:
    ```sql
    CREATE TABLE IF NOT EXISTS cache (
        key TEXT PRIMARY KEY,
        value TEXT,
        expires_at REAL
    );
    CREATE INDEX IF NOT EXISTS idx_expires_at ON cache(expires_at);
    ```
  - DB path: `platformdirs.user_cache_path("mcp-cendoj") / "cache.db"` — **use `user_cache_path`** (returns `pathlib.Path`), NOT `user_cache_dir` (returns `str`).
  - Create parent directory before connecting: `db_path.parent.mkdir(parents=True, exist_ok=True)`.
  - Key normalization: all keys normalized via `key.strip().upper()` before any read or write.
  - **All sqlite3 statements MUST use `?` placeholder form** — no string interpolation. Example: `cursor.execute("SELECT value, expires_at FROM cache WHERE key = ?", (key,))`.
  - Wrap all sqlite3 I/O in `asyncio.to_thread()` to avoid blocking the asyncio event loop. Example: `value = await asyncio.to_thread(self._sync_get, key)`.
  - `get(key) -> str | None` (returns None if expired or missing).
  - `set(key, value, ttl_seconds=86400)`.
  - `clear()` — delete all rows.
  Acceptance: tests use `sqlite3.connect(":memory:")` via dependency injection; cover: get-miss, get-hit, get-expired, set, clear, key-with-single-quote (SQL injection attempt must not raise or corrupt).

- [ ] **3.3 — Implement `get_ruling_text` resource**
  Files: `src/mcp_cendoj/tools/document.py`, `tests/tools/test_document.py`
  Signature: `async def get_ruling_text(ecli: str) -> Ruling`
  Logic:
  1. Normalize: `ecli = ecli.strip().upper()`. Apply same strict regex as Task 2.2.
  2. Check `DiskCache` for `ecli`:
     - Cache hit: deserialize with `try: Ruling.model_validate_json(cached) except ValidationError: treat as miss` (guards against schema evolution breaking cached entries).
     - Return cached `Ruling` if deserialization succeeds.
  3. Cache miss path — wrap in `asyncio.wait_for(..., timeout=20.0)` for aggregate deadline:
     - Determine fetch strategy from `CENDOJ_ECLI_URL_TEMPLATE` type (established in Task 1.3 pre-work):
       - **Option A (ECLI URL = direct document page)**: call `lookup_by_ecli(ecli)` which returns a `Ruling` with `raw_text` populated. Then call `extract_sections(html, ecli)` to add structured sections. Cache the enriched `Ruling`.
       - **Option B (ECLI URL = metadata/redirect page)**: call `lookup_by_ecli(ecli)` to get `Ruling.source_url`. Then fetch full document HTML from `source_url` via `CendojClient`. Call `extract_sections(html, ecli)`. Cache the fully populated `Ruling`.
     - PDF detection: if URL ends in `.pdf` or `Content-Type: application/pdf`, set `parse_successful=False` and skip `extract_sections`.
  4. Cache enriched result with 24h TTL.
  Register: `@app.resource("cendoj://{ecli}")` in `__init__.py` (Decision D8). The `Ruling.cendoj_uri` field populated in Task 2.2 ensures the LLM receives the URI it needs without having to construct the `cendoj://` scheme independently.
  Acceptance: tests cover cache-hit path, cache-miss + fetch path, ValidationError on stale cache → re-fetch, PDF URLs handled, aggregate 20s timeout fires correctly.

### Layer 4 — Supersession check (~2 h, depends on Layer 2)

- [ ] **4.1 — Implement `check_if_superseded` tool**
  Files: `src/mcp_cendoj/tools/superseded.py`, `tests/tools/test_superseded.py`
  Signature: `async def check_if_superseded(ecli: str) -> SupersededResult`
  Logic:
  1. Normalize: `ecli = ecli.strip().upper()`. Apply same strict regex as Task 2.2.
  2. Construct ECLI query string (use encoding confirmed in Task 1.3 pre-work — colons may need `%3A` encoding in the quoted phrase).
  3. Call `search_rulings(query=f'"{ecli}"', max_results=20)`.
  4. Filter out results whose `ecli == checked_ecli` (self-references).
  5. Scan `snippet` for reversal keywords: `re.compile(r"\b(revoca|casa\b|anula|deja\s+sin\s+efecto)", re.I)`.
  6. Return `SupersededResult` with `confidence="medium"` hardcoded, `search_method="ecli_fulltext"`, and the extended `warning` string:
     ```python
     WARNING = (
         'Citation coverage is incomplete — CENDOJ has no citation graph. '
         'Absence of results does NOT confirm validity. '
         'Spanish courts also cite by ROJ identifier and popular case name. '
         'A positive result indicates the checked ECLI co-occurs with reversal language '
         'in a later ruling snippet — NOT that the checked ruling is the direct subject '
         'of reversal. Manual verification by a qualified lawyer is required.'
     )
     ```
  Register: `@app.tool()` in `__init__.py`.
  Acceptance: tests cover: later rulings found with reversal keyword (`is_likely_superseded=True`), later rulings found without keyword (`is_likely_superseded=False`), no later rulings found (`citations_found=0`); `confidence` is always `"medium"`.

---

## Test Plan

| Task | Test strategy | Test file |
|------|--------------|-----------|
| 1.1 deps | `uv run python -c "from mcp.server.fastmcp import FastMCP"` | CI |
| 1.2 models | Pydantic validation, literal constraints, UTC default | `tests/test_models.py` |
| 1.4 entrypoint | Mock `app.run()`, assert `main()` calls it | `tests/test_main.py` |
| 2.1 http client | `respx` mocks: success, 429 retry, 503 retry, `httpx.ReadTimeout`, response-too-large | `tests/test_http.py` |
| 2.2 lookup | `respx` + HTML fixture; ambiguous/not-found/injection-attempt ECLI errors | `tests/tools/test_lookup.py` |
| 2.3 search | `respx` + HTML fixture; empty result error; max_results clamped at 100 | `tests/tools/test_search.py` |
| 3.1 parser | Real HTML fixtures for TS/TSJ (committed first); section extraction + fallback; HTML-too-large | `tests/test_parser.py` |
| 3.2 cache | In-memory sqlite3 via DI; TTL expiry; SQL injection key; key normalization | `tests/test_cache.py` |
| 3.3 document | Cache hit/miss paths; stale-cache ValidationError → re-fetch; 20s timeout | `tests/tools/test_document.py` |
| 4.1 superseded | Reversal keyword match + no-match + no-results | `tests/tools/test_superseded.py` |

Additional file: `tests/tools/__init__.py` — create empty (required for pytest sub-package discovery).

**TDD tasks**: 1.2 (models — write tests first), 3.1 (parser — fixtures first), 3.2 (cache — pure logic).

**No live network in CI**: all HTTP calls mocked with `respx`. Live integration tests
are gated behind `CENDOJ_LIVE_TEST=1` env var and excluded from `make test`.

---

## Integration Verification

After Layer 2 is complete, run a manual smoke test (requires network):

```bash
# 0. Install all dependencies first (required for src/ layout)
uv sync

# 1. Verify the MCP inspector sees the registered tools
#    (uv run ensures the src/ package is on sys.path)
uv run mcp dev mcp_cendoj:app

# 2. Direct invocation via valid JSON-RPC 2.0 (stdio)
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | uv run mcp-cendoj

# 3. Live ECLI lookup (manual, not in CI)
CENDOJ_LIVE_TEST=1 uv run pytest tests/integration/ -v -k "test_lookup_live"
```

---

## Out of Scope

The following ideas from brainstorming are explicitly deferred:

- **Streaming/cursor-based pagination** for `search_rulings` — future enhancement.
- **`FundamentoJuridico` typed objects with `cites_ecli`** — requires NLP citation parsing; deferred.
- **Full appellate history tree / citation graph** — requires data CENDOJ does not expose; deferred.
- **Multi-database resolver** (BOE, Aranzadi, regional) — deferred until CENDOJ MVP is stable.
- **Reliability confidence score** (`confidence: float`) — deferred; requires binding authority data.
- **AN section extractor** — deferred; requires AN-specific HTML fixtures.
- **TSJ section extractors** — deferred; requires per-tribunal fixture collection (17 variants).
- **Headless browser fallback** (Playwright) — deferred; introduce only if CENDOJ enforces JS-rendered CSRF.
