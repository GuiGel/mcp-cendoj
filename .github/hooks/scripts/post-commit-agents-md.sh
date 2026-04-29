#!/usr/bin/env bash
# git post-commit hook
# If a commit touched pyproject.toml or Makefile, prints a reminder to
# run agents-updater. Does not block the commit (exit 0 always).
set -euo pipefail

WATCHED_PATTERN="^(pyproject\.toml|Makefile|src/)"

changed=$(git diff-tree --no-commit-id -r --name-only HEAD 2>/dev/null || echo "")

if printf '%s\n' "$changed" | grep -qE "$WATCHED_PATTERN"; then
  echo ""
  echo "┌─────────────────────────────────────────────────────────────┐"
  echo "│  📋 AGENTS.md reminder                                      │"
  echo "│  pyproject.toml, Makefile, or src/ changed in this commit.  │"
  echo "│  Run the 'agents-updater' agent to audit AGENTS.md.         │"
  echo "└─────────────────────────────────────────────────────────────┘"
  echo ""
fi

exit 0
