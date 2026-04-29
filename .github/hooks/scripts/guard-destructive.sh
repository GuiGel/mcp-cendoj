#!/usr/bin/env bash
# Hook: PreToolUse
# Intercepts shell execute tools and asks for user confirmation when a
# destructive command pattern is detected. Prevents accidental data loss.
set -euo pipefail

input=$(cat)

# Extract command from tool_input (VS Code uses camelCase)
command=$(printf '%s' "$input" | python3 -c "
import sys, json
d = json.load(sys.stdin)
ti = d.get('tool_input', {})
# runInTerminal / execute aliases expose 'command' or 'cmd'
print(ti.get('command', ti.get('cmd', ti.get('input', ''))))
" 2>/dev/null || echo "")

if [[ -z "$command" ]]; then
  exit 0
fi

# Patterns that require explicit user confirmation before execution
PATTERNS=(
  "rm -rf"
  "git push --force"
  "git push -f "
  "git push -f$"
  "git reset --hard"
  "git clean -fd"
  "git clean -f "
  "DROP TABLE"
  "DROP DATABASE"
  "DROP SCHEMA"
  "DELETE FROM"
  "TRUNCATE TABLE"
  "TRUNCATE "
  "git worktree remove"
)

for pattern in "${PATTERNS[@]}"; do
  if printf '%s' "$command" | grep -qiE -- "$pattern"; then
    # Sanitize the pattern for JSON output
    safe_pattern=$(python3 -c "import sys,json; print(json.dumps(sys.argv[1]))" "$pattern" 2>/dev/null || echo "\"$pattern\"")
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"Destructive command detected (%s) — confirm before executing"}}\n' "${pattern}"
    exit 0
  fi
done
