#!/usr/bin/env bash
# Hook: Stop (agent-scoped to Plan Execute)
# Blocks the agent from finishing if there are uncommitted changes in the
# current worktree. Prevents "done" reports with a dirty state.
#
# Uses stop_hook_active guard to prevent infinite loops.
set -euo pipefail

input=$(cat)

# Prevent infinite loop: if already running from a Stop hook, let it finish
stop_hook_active=$(printf '%s' "$input" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('true' if d.get('stop_hook_active', False) else 'false')
" 2>/dev/null || echo "false")

if [[ "$stop_hook_active" == "true" ]]; then
  exit 0
fi

cwd=$(printf '%s' "$input" | python3 -c "
import sys, json; d = json.load(sys.stdin); print(d.get('cwd', '.'))
" 2>/dev/null || echo ".")

cd "$cwd" 2>/dev/null || exit 0

# Remove .mr-body.md if it exists (artifact from Create MR agent)
if [[ -f ".mr-body.md" ]]; then
  rm -f ".mr-body.md"
fi

# Check for uncommitted changes
dirty=$(git status --porcelain 2>/dev/null | head -5 || echo "")

if [[ -n "$dirty" ]]; then
  reason="Uncommitted changes detected — commit or stash before finishing Plan Execute:
${dirty}"
  json_reason=$(python3 -c "import sys,json; print(json.dumps(sys.argv[1]))" "$reason" 2>/dev/null) || {
    json_reason="\"Uncommitted changes detected — commit or stash before finishing\""
  }
  printf '{"hookSpecificOutput":{"hookEventName":"Stop","decision":"block","reason":%s}}' "$json_reason"
  exit 0
fi
