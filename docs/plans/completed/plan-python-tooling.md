# Plan: python-tooling
Created: 2026-04-29 | Completed: 2026-04-29 | Status: MERGED | Branch: main | Tier: 0 (Solo)

## Summary

Establish a production-grade Python project toolchain for `mcp-cendoj`. Covers
formatting, linting, static type checking, testing, coverage, git hooks, CI, and
dynamic versioning — modelled on pydantic/logfire conventions.

## Decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Versioning | `hatch-vcs` (dynamic, from git tags) | Automates version from `git tag vX.Y.Z`; standard for published packages |
| 2 | Ruff rule set | Comprehensive (Q, UP, I, D, C90, DTZ005, FA) | Enforces best practices; D rules relaxed for tests |
| 3 | Type checker | `pyright --strict` | Faster than mypy, first-class Python 3.13 support, used by pydantic/logfire |
| 4 | CI scope | Local (Makefile + pre-commit) + GitHub Actions | Minimal matrix CI (lint / typecheck / test jobs) |

## Architecture

No ADR required — pure tooling configuration, no architectural layers changed.

**Patterns applied:**
- `uv` as package manager and task runner (consistent with Python 3.13 ecosystem)
- All tool config co-located in `pyproject.toml` (single source of truth)
- Makefile as the developer interface (`make install`, `make all`)
- Pre-commit hooks mirror CI checks (no surprises on push)

## Tasks

### Layer 1 — Completed ✓

- [x] `pyproject.toml` — added `hatch-vcs` dynamic versioning, `[dependency-groups] dev`,
  `[tool.ruff]`, `[tool.pyright]`, `[tool.pytest.ini_options]`, `[tool.coverage.*]`
- [x] `Makefile` — targets: `install`, `format`, `lint`, `typecheck`, `test`, `testcov`, `all`
- [x] `.pre-commit-config.yaml` — hooks: `pre-commit-hooks`, `ruff-lint`, `ruff-format`, `pyright`
- [x] `.github/workflows/ci.yml` — jobs: `lint`, `typecheck`, `test` (with coverage artifact)
- [x] `tests/__init__.py` — created tests package
- [x] `tests/test_main.py` — placeholder smoke test
- [x] `uv.lock` — committed for reproducible CI `--frozen` installs
- [x] `src/mcp_cendoj/__init__.py` — updated to comply with ruff rules (docstring, single quotes)

## Test Plan

| Check | Command | Status |
|-------|---------|--------|
| Lint | `make lint` | ✓ |
| Format | `ruff format --check` (inside `make lint`) | ✓ |
| Type check | `make typecheck` | ✓ (0 errors) |
| Tests | `make test` | ✓ (1 passed) |

## Integration Verification

```bash
# Full local quality gate
make all

# Coverage report
make testcov
open htmlcov/index.html
```

## Onboarding

```bash
# One-time setup
make install

# Daily workflow
make all        # format + lint + typecheck + test
make format     # auto-fix formatting
make testcov    # tests with HTML coverage report
```

**Versioning:** bump via `git tag v0.2.0 && git push --tags`.
The package version is derived automatically from the latest tag.

## Out of Scope

- Documentation site (MkDocs)
- Publishing to PyPI
- Multi-Python-version test matrix
- Integration / snapshot tests
