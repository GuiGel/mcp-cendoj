# Plan: search-empty-results
Created: 2026-04-30 | Completed: 2026-04-30 | Branch: feature/search-empty-results | Tier: 0 | Status: COMPLETED

## Summary
`search_rulings` currently raises `CendojNetworkError` when the CENDOJ response
contains zero results. This is semantically wrong — an empty result set is a valid
server response (over-filtered query), not a network failure. The MCP framework
surfaces the exception as a tool error instead of returning an empty list. Fix
returns `[]` and updates the docstring and test accordingly.

## Decisions
- Return `[]` instead of raising — MCP tools can legitimately return empty lists;
  callers should decide what to do with no results.
- Keep `CendojNetworkError` only for actual HTTP/network failures (its original
  purpose per the class docstring in `http.py`).
- **ADR-0007 created** to supersede ADR-0002 §Required Hardening clause 7 and
  document the accepted risk (parser regression indistinguishable from genuine
  empty results — mitigated by live fixture integration tests).

## Architecture
ADR-0007 (`docs/adr/ADR-0007-empty-results-contract.md`) records this decision.
ADR-0002 status updated to "Partially superseded by ADR-0007".

## Tasks

### Layer 1
- [x] **Fix `search_rulings`** — remove `raise CendojNetworkError(...)` on empty
  results; return `results[:max_results]` (already an empty list) unconditionally.
  File: `src/mcp_cendoj/tools/search.py` lines 429-431.
  Acceptance: function returns `[]` when parser finds no results; still raises
  `CendojNetworkError` on actual HTTP errors.

- [x] **Update docstring** — remove "or empty result sets" from the `Raises` block.
  File: `src/mcp_cendoj/tools/search.py` line 376.
  Acceptance: docstring accurately reflects the new behaviour.

- [x] **Update test** — rename `test_empty_results_raises_network_error` to
  `test_empty_results_returns_empty_list` and assert `result == []` instead of
  `pytest.raises(CendojNetworkError)`.
  File: `tests/tools/test_search.py` lines 58-61.
  Acceptance: test passes, coverage gate holds.

## Test Plan
- Run `make test` — all existing tests must pass (including the renamed/updated one).
- Run `make all` — quality gate (ruff + pyright + pytest) must be green.

## Integration Verification
No HTTP calls needed — covered by existing mock-based test suite.

## Out of Scope
- `search_normas` empty-result handling (separate concern, not raised by user).
- Changing how `check_if_superseded` handles empty results (already returns a model).
