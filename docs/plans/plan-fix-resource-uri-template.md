# Plan: fix-resource-uri-template
Created: 2026-04-30 | Branch: fix/resource-uri-template | Tier: 0

## Summary

The MCP resource registered as `cendoj://{ecli}` is permanently broken in
production. Pydantic's `AnyUrl` (used in `mcp/types.py`'s
`ReadResourceRequestParams`) fails to parse `cendoj://ECLI:ES:TS:2026:3898A`
because the colons inside the ECLI identifier are interpreted as host:port
separators. The fix changes the template to `cendoj://ruling/{ecli}`, places the
ECLI in the URI **path** (where colons are valid per RFC 3986), and promotes the
previously `xfail` integration test to a fully passing test.

## Decisions

- **URI form chosen**: `cendoj://ruling/{ecli}` — semantically clear, validates
  cleanly as `AnyUrl`, `str()` round-trip is lossless (colons preserved, no
  percent-encoding). See ADR-0005.
- **No encoding helper**: the ECLI path segment contains no forward-slashes, so the
  `[^/]+` regex in `ResourceTemplate.matches()` captures it verbatim. No
  `urllib.parse.quote/unquote` is needed.
- **Cache unaffected**: `DiskCache` keys on the raw ECLI string, not the MCP URI.
  No cache invalidation or migration needed.
- **`xfail` removed entirely**: the test comment explained a now-resolved limitation.
  The `strict=False` xfail marker and its `# pyright: ignore` cast are both removed.

## Architecture

- ADR created: `docs/adr/ADR-0005-resource-uri-template-scheme.md`
- No new ADR patterns (single-file change, no architectural layers added).

## Tasks

### Layer 1

- [ ] **Update resource template** — change `@app.resource('cendoj://{ecli}')` to
  `@app.resource('cendoj://ruling/{ecli}')` in `src/mcp_cendoj/__init__.py`.
  - Files affected: `src/mcp_cendoj/__init__.py`
  - Acceptance criteria: `make lint && make typecheck` pass. The resource is
    advertised with URI template `cendoj://ruling/{ecli}` in the MCP server manifest.

- [ ] **Promote xfail test** — in `tests/test_mcp_integration.py`:
  1. Remove `@pytest.mark.xfail(...)` decorator and its comment block.
  2. Change `session.read_resource('cendoj://ECLI:ES:TS:2026:3898A')` to
     `session.read_resource('cendoj://ruling/ECLI:ES:TS:2026:3898A')`.
  3. Remove the `# pyright: ignore[reportArgumentType]` and `# URI xfail: ...`
     inline comments.
  4. Add the missing `ts_ruling.pdf` fixture (the test references it but the file
     does not exist — supply a minimal PDF bytes fixture or adjust the test to use
     the existing `ts_ruling.txt` fixture appropriately).
  - Files affected: `tests/test_mcp_integration.py`
  - Acceptance criteria: `pytest tests/test_mcp_integration.py::test_get_ruling_text_resource`
    passes without xfail.

- [ ] **Update docstring** — update the `get_ruling_text` resource docstring in
  `src/mcp_cendoj/__init__.py` to reflect the new URI form
  (`cendoj://ruling/{ecli}`).
  - Files affected: `src/mcp_cendoj/__init__.py`
  - Acceptance criteria: docstring example matches new URI.

### Layer 2 (depends on Layer 1)

- [ ] **Full quality gate** — run `make all` and confirm all checks pass.
  - Acceptance criteria: exit code 0 for lint, typecheck, test, coverage ≥ 80 %.

## Test Plan

| Task | Verification |
|------|-------------|
| Template update | `pytest tests/test_mcp_integration.py` — all resource tests pass |
| xfail promotion | `pytest -v tests/test_mcp_integration.py::test_get_ruling_text_resource` — PASSED (not XFAIL) |
| No regressions | `make test` — full suite green |
| Coverage gate | `make test` — branch coverage ≥ 80 % |
| Lint & types | `make lint && make typecheck` — no errors |

**TDD note**: the existing xfail test IS the test. Promote it; do not add a parallel test.

## Integration Verification

```bash
# Smoke-test the registered resource template via the MCP inspector
uv run mcp dev src/mcp_cendoj/__init__.py
# In the inspector, Resources tab should show:
#   URI template: cendoj://ruling/{ecli}
```

## Out of Scope

- Adding `urllib.parse.unquote` to `get_ruling_text` (not needed — colons are
  preserved verbatim by `AnyUrl.__str__`).
- Migrating cached JSON entries (cache keys are raw ECLIs, not MCP URIs).
- Adding sibling resource templates (`cendoj://search/{query}`, etc.).
- Updating `README.md` or external documentation (no docs yet describe the URI).
- Changing the `Ruling.cendoj_uri` field (stores CENDOJ's own HTTP URL, unrelated).
