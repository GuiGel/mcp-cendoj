# Plan: integration-test-foundation
Created: 2026-04-30 | Branch: feature/integration-test-foundation | Tier: 0 (Solo)

## Summary

Establish a proper integration-test foundation for `mcp-cendoj` by making two minimal
structural changes that unlock transport-level HTTP mocking and MCP-layer testing, then
building the test infrastructure on top. The result: all 69 existing unit tests become
faster (no real sleeps), the full call chain from `@app.tool()` wrapper → impl →
HTTP client → HTML parser is exercised for the first time, and the MCP serialisation
envelope is verified end-to-end — all without a real network call.

---

## Decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| D1 | Transport injection API | `httpx.MockTransport(router.async_handler)` wrapping `respx.Router` | `respx.Router` is NOT `httpx.AsyncBaseTransport`; `httpx.MockTransport` IS (verified in venv). `assert_all_mocked=True` enforcement works through `async_handler`: `aresolve` → `resolver` context manager checks `_assert_all_mocked` and raises `AllMockedAssertionError` on unregistered URLs (verified in respx/router.py:241-264) |
| D2 | MCP in-process test client | `mcp.shared.memory.create_connected_server_and_client_session` (mcp SDK v1.27.0) | `fastmcp` not installed; avoid adding a runtime dep for test-only ergonomics. Import verified: `python -c "from mcp.shared.memory import create_connected_server_and_client_session; print('OK')"` ✅ |
| D3 | MCP tool injection bridge | Module-level `_client: CendojClient \| None = None` in `__init__.py` | LLM never sees it (outside tool signature); controls all 4 tools with one `monkeypatch`. Set via `monkeypatch.setattr(mcp_cendoj, '_client', client)` — correct pytest API (3-arg form: obj, name, value) |
| D4 | Result assertion attribute | `result.isError` (camelCase) | Verified: `mcp.types.CallToolResult` field name is `isError`, not `is_error` |
| D5 | `_no_sleep` patch target | `monkeypatch.setattr('asyncio.sleep', AsyncMock())` | `http.py` calls `asyncio.sleep(...)` via module attr lookup — patch hits correctly. Validated by `test_no_sleep_fixture_actually_patches` smoke test |
| D6 | Snapshot testing | Deferred to Layer 5 (optional) | Core value is in Layers 1–4; `syrupy` adds a new dep and snapshot maintenance burden |
| D7 | Live canary | Deferred to Layer 5 (optional) | Structural-only assertions required to avoid false regressions from CENDOJ metadata updates |
| D8 | `respx.Router` kwarg | `assert_all_mocked=True` | Verified in `.venv/lib/python3.13/site-packages/respx/router.py:44` — correct kwarg for `Router.__init__` (default value is already `True`) |

---

## Architecture

### The Injection Gap (Root Cause)

Currently `__init__.py` discards the `client=` injection point:
```python
@app.tool()
async def search_rulings(query, max_results=10) -> list[SearchResult]:
    return await _search_impl(query, max_results)  # client= never passed
```

Every MCP-level call creates a fresh `CendojClient()` with no way to intercept HTTP.
The fix adds a module-level bridge variable:
```python
_client: CendojClient | None = None  # test-injectable; None = each impl uses its own default

@app.tool()
async def search_rulings(query, max_results=10) -> list[SearchResult]:
    return await _search_impl(query, max_results, client=_client)  # bridge forwarded
```

### The Transport Pattern

```
respx.Router  ──async_handler──►  httpx.MockTransport  ──transport=──►  CendojClient._client
                                  (httpx.AsyncBaseTransport)
```

In tests:
```python
router = respx.Router()
router.get(SESSION_URL).respond(200, text='ok')
router.post(SEARCH_URL).respond(200, text=html)
transport = httpx.MockTransport(router.async_handler)
client = CendojClient(transport=transport)
```

### Test Fixture Pyramid

```
Layer 4: tests/test_mcp_integration.py
    └─ mcp_session (create_connected_server_and_client_session)
       └─ monkeypatch(mcp_cendoj, '_client', injected_client)
          └─ make_cendoj_client(html) → CendojClient(transport=MockTransport)
             └─ respx.Router routes
Layer 3: tests/tools/test_*.py (upgraded)
    └─ make_cendoj_client directly (no MCP overhead)
Layer 2: tests/conftest.py
    └─ _no_sleep (autouse) + make_cendoj_client + disk_cache + mcp_session
Layer 1: src/ structural changes (CendojClient transport= + __init__._client)
```

---

## Tasks

### Layer 1 — Structural changes (foundation for everything)

- [ ] **Task A — `CendojClient(*, transport=)`**
  - File: `src/mcp_cendoj/http.py`
  - Change: Add keyword-only param `transport: httpx.AsyncBaseTransport | None = None` to
    `CendojClient.__init__`; pass it to `httpx.AsyncClient(transport=transport)`
  - Acceptance: `make typecheck` passes; `httpx.AsyncClient(transport=None)` is identical to
    no transport arg (httpx default-branches internally); all 11 existing `CendojClient()` call
    sites unchanged (keyword-only ensures no positional conflict)

- [ ] **Task B — `mcp_cendoj._client` injection bridge**
  - File: `src/mcp_cendoj/__init__.py`
  - Change: Add **both** of the following at module level (pyright strict requires the import
    before the type annotation):
    ```python
    from mcp_cendoj.http import CendojClient

    _client: CendojClient | None = None  # set in tests via monkeypatch; None = prod default
    ```
    Forward `client=_client` through all four `@app.tool()` / `@app.resource()` wrappers:
    `lookup_by_ecli`, `search_rulings`, `check_if_superseded`, `get_ruling_text`.
    Also forward `cache=_disk_cache` through the `get_ruling_text` resource wrapper
    (imports `_disk_cache` from `mcp_cendoj.tools.document`) so the integration test can
    override the cache without touching `document.py`.
  - Note: `_client` is function-scoped via `monkeypatch` → automatically reset after each
    test. Do NOT use class/module-scoped fixtures to set `_client` — violates isolation.
    Not pytest-xdist safe (parallel workers share the same module global), but xdist is
    not in use for this project.
  - Acceptance: `make typecheck` passes; `make test` still passes (production path unchanged
    since `_client` defaults to `None` → impls create their own client as before)

### Layer 2 — Test infrastructure

- [ ] **Task C — `tests/conftest.py`**
  - Create `tests/conftest.py` with four fixtures:

  **`_no_sleep` (autouse=True)**
  ```python
  @pytest.fixture(autouse=True)
  def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
      """Patch asyncio.sleep globally to eliminate delays in CendojClient retry logic.

      Uses monkeypatch (not unittest.mock.patch) for pytest-idiomatic teardown.
      Patch target 'asyncio.sleep' is correct because http.py uses `asyncio.sleep(...)`
      via the module attribute, not a local import.
      """
      monkeypatch.setattr('asyncio.sleep', AsyncMock())
  ```
  Effect: eliminates all `asyncio.sleep` calls in `CendojClient` retry logic.
  Expected suite speed improvement: ~11s → **≤3s** (3s accounts for HTML parsing,
  pytest fixture setup, and in-process MCP session overhead; ~1s would require zero
  non-sleep overhead which is unrealistic).

  **`make_cendoj_client` (function-scoped async generator factory)**
  ```python
  @pytest.fixture
  async def make_cendoj_client() -> AsyncGenerator[Callable[..., CendojClient], None]:
      clients: list[CendojClient] = []
      def factory(
          html: str,
          *,
          session_url: str = CENDOJ_SESSION_INIT_URL,
          post_url: str = CENDOJ_SEARCH_URL,
          document_url: str | None = None,
          document_bytes: bytes | None = None,
      ) -> CendojClient:
          router = respx.Router(assert_all_mocked=True)
          router.get(session_url).respond(200, text='ok')
          router.post(post_url).respond(200, text=html)
          if document_url is not None:
              router.get(document_url).respond(
                  200,
                  content=document_bytes or b'',
                  headers={'Content-Type': 'application/pdf'},
              )
          transport = httpx.MockTransport(router.async_handler)
          client = CendojClient(transport=transport)
          clients.append(client)
          return client
      yield factory
      for client in clients:
          await client.close()
  ```
  `assert_all_mocked=True`: kwarg verified in `.venv/lib/python3.13/site-packages/respx/router.py:44`.
  Enforcement works via `async_handler` → `aresolve` → `resolver` context manager →
  raises `AllMockedAssertionError` on unregistered URLs (verified in router.py:249).
  Use `document_url=` + `document_bytes=` for the `get_ruling_text` resource test.

  **`disk_cache` (function-scoped)**
  ```python
  @pytest.fixture
  def disk_cache(tmp_path: Path) -> DiskCache:
      return DiskCache(db_path=str(tmp_path / 'cache.db'))
  ```
  Eliminates SQLite writes to `platformdirs.user_cache_path('mcp-cendoj')` in CI.

  **`mcp_session` (function-scoped async generator)**
  ```python
  @pytest.fixture
  async def mcp_session(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[ClientSession, None]:
      """Yield an in-process MCP ClientSession.

      Safety: sets `mcp_cendoj._client` to a sentinel object that raises AttributeError
      on any attribute access. Tests MUST override it with a real CendojClient via
      monkeypatch BEFORE calling `call_tool` — otherwise the sentinel causes an immediate
      loud failure instead of a silent real-network call to CENDOJ.
      """
      monkeypatch.setattr('mcp_cendoj._client', object())  # fail-loud sentinel
      async with create_connected_server_and_client_session(app) as session:
          yield session
  ```
  Yields a `mcp.client.session.ClientSession` connected in-process. Used only in Layer 4.
  Every test that uses `mcp_session` **must** call
  `monkeypatch.setattr(mcp_cendoj, '_client', make_cendoj_client(html))` to replace the
  sentinel before invoking any tool — otherwise the `object()` sentinel will cause a
  `TypeError` or `AttributeError` on the first `client.post(...)` call, clearly indicating
  the forgotten injection.

  - Acceptance: `make test` still passes; suite runtime drops to **≤3s**;
    `test_no_sleep_fixture_actually_patches` smoke test confirms the patch is active:
    ```python
    async def test_no_sleep_fixture_actually_patches() -> None:
        import time
        start = time.perf_counter()
        await asyncio.sleep(10.0)  # must be instant
        elapsed = time.perf_counter() - start
        assert elapsed < 0.1, f'_no_sleep not working: sleep(10) took {elapsed:.3f}s'
    ```

### Layer 3 — Unit test upgrade

> **⚠️ ATOMICITY REQUIREMENT**: Tasks C and D **must be committed together as a single
> commit**. Merging Task C alone introduces `_no_sleep` autouse while `test_http.py` still
> has 10 explicit `patch('asyncio.sleep', ...)` context managers — the autouse fixture and
> the `unittest.mock.patch` context managers stack (the explicit patch overwrites the
> monkeypatch inside its `with` block), creating confusing double-patching. Commit them as:
> ```
> feat(test): add conftest _no_sleep autouse and remove explicit asyncio.sleep patches
> ```

- [ ] **Task D — Upgrade `tests/test_http.py`**
  - Replace `@respx.mock` decorator + `patch('asyncio.sleep', ...)` with
    `CendojClient(transport=httpx.MockTransport(router.async_handler))` pattern throughout
  - Add one new test: `test_session_cookie_forwarded_to_post` — a `respx.Router` whose
    GET returns `Set-Cookie: JSESSIONID=test-abc` and whose POST handler asserts the
    request contains `Cookie: JSESSIONID=test-abc`, verifying the cookie-jar wiring
  - Remove **all 10** explicit `with patch('asyncio.sleep', new_callable=AsyncMock):` blocks
    from `test_http.py` (now handled by `_no_sleep` autouse fixture added in Task C)
  - Files affected: `tests/test_http.py`
  - Acceptance: all `test_http.py` tests pass; no `asyncio.sleep` patches remain in file;
    **must be committed in the same commit as Task C** (see atomicity requirement above)

- [ ] **Task E — Upgrade `tests/tools/test_*.py`**
  - Replace `AsyncMock(spec=CendojClient)` with `make_cendoj_client(html)` in:
    - `tests/tools/test_search.py`
    - `tests/tools/test_lookup.py`
    - `tests/tools/test_superseded.py`
    - `tests/tools/test_document.py`
  - For `test_document.py` specifically:
    - **Remove** the local `mem_cache` async fixture (defined inside the file)
    - **Use** the conftest `disk_cache` fixture instead: `async def test_...(disk_cache: DiskCache)`
    - Inject `cache=disk_cache` via the `cache=` parameter on `get_ruling_text` directly
      (not via `_disk_cache` module global — the module-level bridge is only needed for
      the MCP resource wrapper path exercised in Task F)
  - Effect: `_parse_search_results`, `_parse_search_results` (lookup), and `split_sections`
    are on the hot path for the first time — real HTML is parsed rather than mocked away
  - Existing inline `_ONE_RESULT_HTML`, `_TWO_RESULT_HTML` constants in test files:
    keep as-is (they are valid HTML snippets the real parser already handles)
  - Files affected: all four `tests/tools/test_*.py`
  - Acceptance: all 69 existing tests continue to pass; branch coverage gate (80%) met;
    expect ~200–400 ms increase in tools test runtime due to real BeautifulSoup HTML parsing
    (trade-off is intentional — we gain real parser coverage)

### Layer 4 — Integration tests

- [ ] **Task F — `tests/test_mcp_integration.py`**
  - New file exercising the full chain: `@app.tool()` wrapper → `_client` bridge → impl →
    `CendojClient(transport=)` → `_parse_search_results` → Pydantic model → MCP serialisation
  - Use `mcp_session` + `monkeypatch.setattr(mcp_cendoj, '_client', make_cendoj_client(html))`
  - Cover all three tools + the resource:

  | Test | HTML fixture | Assertion |
  |------|-------------|-----------|
  | `test_search_rulings_returns_list` | `search_results.html` | `not result.isError`; `content[0].text` parses as JSON list |
  | `test_search_rulings_field_values` | inline HTML | ECLI, court, date, freshness fields |
  | `test_search_rulings_validation_error_on_bad_max` | — | `result.isError` when `max_results=0` |
  | `test_search_rulings_network_error_is_mcp_error` | 500 response | `result.isError` |
  | `test_lookup_by_ecli_returns_ruling` | `ecli_lookup.html` | `is_ecli_resolved=True` |
  | `test_lookup_by_ecli_invalid_ecli` | — | `result.isError` (no network call) |
  | `test_lookup_by_ecli_not_found` | empty HTML | `result.isError` |
  | `test_check_if_superseded_not_superseded` | `search_results.html` | `is_likely_superseded=False`; warning present |
  | `test_check_if_superseded_no_results` | empty HTML | `citations_found=0` |

  - For `get_ruling_text` (resource): use `mcp_session.read_resource('cendoj://ECLI:ES:TS:2020:1234')`.
    The factory must handle two routes — pass `document_url=` to `make_cendoj_client`:
    ```python
    client = make_cendoj_client(
        html=fixtures.ecli_lookup_html,   # POST route → lookup HTML
        document_url='https://example.com/doc.pdf',  # GET route
        document_bytes=(FIXTURES / 'ts_ruling.pdf').read_bytes(),  # PDF fixture
    )
    ```
    Inject `disk_cache` via `monkeypatch.setattr('mcp_cendoj.tools.document._disk_cache', disk_cache)`
    (this requires that Task B adds the corresponding module-level `_disk_cache` bridge to
    the `get_ruling_text` resource wrapper, forwarding it from `mcp_cendoj.tools.document`).
    Assert `result.contents[0].text` (from `ReadResourceResult.contents[0].text`).
    Note: the document bytes fixture is `ts_ruling.pdf` (not `ts_ruling.txt`); the PDF
    fixture exists at `tests/fixtures/ts_ruling.pdf`.

  - Acceptance: all integration tests pass; `make test` passes with ≥80% branch coverage

### Layer 5 — Optional enhancements (not in this plan scope)

- [ ] **Task G — `syrupy` snapshot tests**
  - Add `syrupy>=4.0` to dev deps; custom `StableSnapshotSerializer` stripping `fetched_at`;
    snapshot `split_sections()` output for all 3 `.txt` fixtures
  - Trigger: do after Layer 1–4 are stable

- [ ] **Task H — `@pytest.mark.live` weekly canary**
  - `pytest_addoption` + `pytest_collection_modifyitems` in `conftest.py`; structural-only
    assertions (`len(results) >= 1`, `all(r.ecli is not None for r in results)`)
  - GitHub Actions `schedule: cron: '0 6 * * 1'`; `pytest-retry` for flakiness tolerance

- [ ] **Task I — `MAX_RESPONSE_BYTES` boundary transport test**
  - Custom `TruncatingTransport(httpx.AsyncBaseTransport)` streaming exactly
    `MAX_RESPONSE_BYTES + 1` bytes; assert `CendojNetworkError` is raised

---

## Test Plan

| Layer | Verification |
|-------|-------------|
| Layer 1 | `make typecheck && make test` — 69 tests still pass, no new type errors |
| Layer 2 | `make test` — suite time drops from ~11s to ≤3s; `test_no_sleep_fixture_actually_patches` passes |
| Layer 3 | `make test` — 69 tests pass; `make test --cov` shows parser branches now covered |
| Layer 4 | `make test` — new integration tests pass; `--cov` report at ≥80% branch |
| All | `make all` (format → lint → typecheck → test) passes clean |

---

## Integration Verification

```bash
# After each layer:
make typecheck   # pyright strict — no type: ignore without explanation
make test        # pytest -q with coverage
make lint        # ruff check + format --check

# After Layer 4:
make all         # full quality gate
```

---

## Out of Scope

- Migration from `mcp.server.fastmcp.FastMCP` to standalone `fastmcp` package (risk:
  pyright strict may fail; reward is `result.data` ergonomics — revisit after Layer 1–4)
- `run_server_async` HTTP transport tests (DiskCache SQLite side effect requires
  additional `_disk_cache` module-level variable in `document.py` — not in this plan)
- VCR cassettes / `pytest-recording` (cassettes go stale; no refresh mechanism planned)
- Mutation testing with `mutmut` (separate effort; gated on stable test suite first)
