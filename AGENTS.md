# AGENTS.md — mcp-cendoj

Always-on rules for every AI agent working in this repository.
Read this file completely before writing any code.

---

## Project

**`mcp-cendoj`** is a Python MCP server for CENDOJ (Spanish legal case law database).

- **Language**: Python ≥ 3.13, strictly typed
- **Entrypoint**: `src/mcp_cendoj/__init__.py` → `main()`
- **CLI**: `mcp-cendoj` (defined in `pyproject.toml` `[project.scripts]`)
- **Packaging**: `hatchling` + `hatch-vcs` (version from git tags, no `version =` in pyproject.toml)
- **Package manager**: `uv` — use `uv add <pkg>` not `pip install`

---

## Build & Verify

```bash
make install    # first-time setup (uv sync + pre-commit hooks)
make lint       # ruff check + format --check (must pass before every commit)
make typecheck  # pyright strict (must pass before every commit)
make test       # pytest (must pass before every commit)
make all        # format → lint → typecheck → test (full quality gate)
```

**Never commit with a failing quality gate.**

---

## Code Style

- **Line length**: 120 characters (`ruff`, matches `editor.rulers`)
- **Quotes**: single `'` for inline strings, double `"` for docstrings
- **Imports**: sorted with `isort` (ruff `I`), `mcp_cendoj` is `known-first-party`
- **Complexity**: McCabe ≤ 14 per function
- **Docstrings**: Google convention (`pydocstyle D`), required on all public functions and classes — *not* on `__init__`, `__repr__`, magic methods, or test functions
- **Type hints**: required on every function signature — pyright strict mode, no `# type: ignore` without a comment explaining why

---

## Architecture Principles

1. **MCP-first**: every new capability is a proper MCP tool or resource, never a raw HTTP endpoint
2. **Thin entrypoint**: `main()` wires the server; business logic lives in dedicated modules under `src/mcp_cendoj/`
3. **No workarounds**: fix at the correct level, never patch at the call site
4. **No backwards-compat shims**: this is a new project — delete old patterns, don't layer on top of them
5. **Fail loudly**: raise typed exceptions with context; never swallow errors with bare `except`

---

## Testing

- **Framework**: `pytest` with `xfail_strict = true`
- **Coverage gate**: 80 % branch coverage (enforced by `pytest-cov`)
- **Test location**: `tests/` — mirror `src/mcp_cendoj/` structure
- **Naming**: `test_<what>_<scenario>` — describe behaviour, not implementation
- **No docstrings in test files** (`D` rules ignored for `tests/**`)
- Every new public function or MCP tool **must** have a corresponding test

---

## Dependency Rules

- Runtime dependencies go in `[project] dependencies` — keep the list minimal
- Dev/test dependencies go in `[dependency-groups] dev`
- Prefer stdlib or well-maintained PyPI packages; avoid adding dependencies for trivial tasks
- When adding a new dependency, note the reason in the commit message

---

## Git Conventions

- **Branch pattern**: `feature/<plan-name>` (created automatically by Plan Execute)
- **Commit style**: conventional commits — `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`
- **Worktrees**: Plan Execute isolates work in `.worktrees/<plan-name>` — never edit worktree files from the main branch directly
- **Never force-push** to `main`

---

## Agents-Specific Notes

- ADRs live in `docs/adr/ADR-XXXX.md` (Nygard format)
- Plans live in `docs/plans/plan-<name>.md`; completed plans move to `docs/plans/completed/`
- Hook scripts are in `.github/hooks/scripts/` — do not edit them without user confirmation (guarded by `guard-destructive.sh`)
- `AGENTS.md` itself is maintained by the `agents-updater` agent — propose changes via that agent, don't edit it directly
