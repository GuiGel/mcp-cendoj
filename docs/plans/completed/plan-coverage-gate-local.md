# Plan: coverage-gate-local
Created: 2026-04-29 | Status: **COMPLETED 2026-04-30** | Branch: feature/coverage-gate-local | Tier: 0

## Summary

The `fail_under = 80` coverage gate is only enforced when pytest is invoked with
`--cov`, which currently happens only in `make testcov` and in CI. The default
`make test` and `make all` targets skip coverage entirely, so developers learn
about coverage regressions only after a push triggers CI. This plan closes that
feedback loop by (1) embedding `--cov` in `addopts` so every `pytest` invocation
enforces the gate locally, and (2) adding a `pre-push` hook that blocks pushes
when coverage falls below the threshold — without penalising every commit.

## Decisions

No open decisions. The two approaches are additive and complementary:

- **Option 1 — always-on coverage in `addopts`**: immediate feedback during
  `make test` / `make all` / any direct `pytest` call. ~2–3 s overhead per run;
  acceptable for this project size.
- **Option 2 — pre-push hook**: hard stop before any push reaches CI, without
  slowing down every commit.

Both are implemented.

## Architecture

No ADR required — this is a pure tooling/quality-gate change. No product
architecture is affected.

Patterns applied:
- Shift-left quality gates: enforce constraints at the earliest feasible point
  (local test run > pre-push > CI), each layer catching failures that the
  previous may have missed.

## Tasks

### Layer 1 — Always-on coverage in `addopts`

- [ ] **Task A — Update `addopts` in `pyproject.toml`**
  - File: `pyproject.toml`
  - Change `addopts = "--tb=short"` →
    `addopts = "--tb=short --cov=mcp_cendoj --cov-report=term-missing"`
  - Acceptance: `make test` exits non-zero when branch coverage < 80 %

- [ ] **Task B — Simplify `make testcov`**
  - File: `Makefile`
  - `testcov` currently passes `--cov=mcp_cendoj --cov-report=html
    --cov-report=term-missing`; with addopts providing `--cov=mcp_cendoj
    --cov-report=term-missing`, trim to `--cov-report=html` only.
  - Acceptance: `make testcov` still produces both term-missing (stdout) and
    HTML report; no duplicate flags warnings.

### Layer 2 — Pre-push hook

- [ ] **Task C — Add `coverage-gate` pre-push hook**
  - File: `.pre-commit-config.yaml`
  - Add a `local` hook under `stages: [pre-push]` that runs
    `uv run pytest --cov=mcp_cendoj --cov-report=term-missing -q`.
  - Acceptance: `git push` is blocked when coverage < 80 %; passes when
    coverage ≥ 80 %.
  - Note: the hook re-specifies `--cov` explicitly so it remains correct even if
    `addopts` is later changed independently.

- [ ] **Task D — Update `make install` and re-install pre-commit hooks**
  - File: `Makefile`
  - Add `pre-commit install --hook-type pre-push` as a second line in the `install`
    target (after the existing `pre-commit install --install-hooks` call) so that
    every developer doing `make install` on a fresh clone automatically gets the
    pre-push hook registered.
  - Also run `pre-commit install --hook-type pre-push` manually once in the current
    checkout to activate the hook immediately.
  - Acceptance: `.git/hooks/pre-push` exists after `make install`; new clones that
    run `make install` also get the hook without any manual step.

## Test Plan

| Task | Verification |
|------|-------------|
| A | Run `make test` — confirm coverage output appears and exit code is 0 (current coverage ≥ 80 %) |
| B | Run `make testcov` — confirm HTML report is generated in `htmlcov/`, term-missing output on stdout |
| C | Manually lower coverage (comment out a line without `pragma: no cover`) and run `git push --dry-run` — confirm hook fires and exits non-zero |
| D | Run `make install` in a fresh clone (or re-run in the current tree) — confirm `.git/hooks/pre-push` exists without any manual extra step |

## Integration Verification

```bash
make all          # format → lint → typecheck → test+cov; must exit 0
make testcov      # must produce htmlcov/ and term-missing report
git push --dry-run  # pre-push hook must execute (check git output)
```

## Out of Scope

- Changing the 80 % threshold itself.
- Adding coverage badges or upload to Codecov/Coveralls.
- Per-file coverage exclusions beyond what's already in `[tool.coverage.report]`.
- Speeding up the test suite itself.
