#!/usr/bin/env bash
# Hook: SessionStart
# Injects git context (branch, worktrees, status) into every new agent session
# so all agents know the exact repo state from the first message.
set -euo pipefail

input=$(cat)
cwd=$(printf '%s' "$input" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('cwd','.'))" 2>/dev/null || echo ".")

cd "$cwd" 2>/dev/null || exit 0

# Git context — safe: read-only operations
branch=$(git branch --show-current 2>/dev/null || echo "detached HEAD")
worktrees=$(git worktree list 2>/dev/null | head -10 || echo "n/a")
status=$(git status --short 2>/dev/null | head -20 || echo "(clean)")
last_commit=$(git log --oneline -1 2>/dev/null || echo "n/a")
python_ver=$(uv run python --version 2>/dev/null || python3 --version 2>/dev/null || echo "unknown")

context="## Session Context (auto-injected)
- **Branch**: ${branch}
- **Last commit**: ${last_commit}
- **Working tree status** (first 20 lines):
\`\`\`
${status}
\`\`\`
- **Worktrees**:
\`\`\`
${worktrees}
\`\`\`
- **Python**: ${python_ver}
- **Project root**: ${cwd}"

json_context=$(python3 -c "import sys,json; print(json.dumps(sys.argv[1]))" "$context" 2>/dev/null) || {
  # Fallback: minimal context if python3 not available
  json_context="\"Git branch: ${branch}\""
}

printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":%s}}' "$json_context"
