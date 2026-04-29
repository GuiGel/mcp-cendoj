#!/usr/bin/env bash
# Hook: SessionStart
# Detects if AGENTS.md is stale relative to key config files.
# If stale, injects a warning into the session context so agents are reminded
# to run the agents-updater before doing any non-trivial work.
set -euo pipefail

input=$(cat)
cwd=$(printf '%s' "$input" | python3 -c "
import sys, json; d = json.load(sys.stdin); print(d.get('cwd', '.'))
" 2>/dev/null || echo ".")

cd "$cwd" 2>/dev/null || exit 0

AGENTS_MD="AGENTS.md"

# If AGENTS.md doesn't exist yet, suggest creating it — don't block
if [[ ! -f "$AGENTS_MD" ]]; then
  msg="⚠️ No AGENTS.md found in project root. Run the \`agents-updater\` agent to create one."
  json_msg=$(python3 -c "import sys,json; print(json.dumps(sys.argv[1]))" "$msg" 2>/dev/null) || exit 0
  printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":%s}}' "$json_msg"
  exit 0
fi

# Use python3 for portable mtime comparison (avoids stat flag differences between macOS/Linux)
stale_files_json=$(python3 - "$AGENTS_MD" <<'PYEOF'
import sys, os, json

agents_md = sys.argv[1]
watched = ["pyproject.toml", "Makefile", "src/mcp_cendoj/__init__.py"]

agents_mtime = os.path.getmtime(agents_md)
stale = [f for f in watched if os.path.exists(f) and os.path.getmtime(f) > agents_mtime]
print(json.dumps(stale))
PYEOF
) || exit 0

# Parse the JSON list back into a bash array
mapfile -t stale_files < <(python3 -c "import sys,json; [print(f) for f in json.loads(sys.argv[1])]" "$stale_files_json" 2>/dev/null) || {
  stale_files=()
}

if [[ ${#stale_files[@]} -gt 0 ]]; then
  files_list=$(printf '%s\n' "${stale_files[@]}" | sed 's/^/  - /')
  msg="📋 AGENTS.md may be stale — the following files were modified after it was last updated:
${files_list}
Consider switching to the \`agents-updater\` agent to audit and patch AGENTS.md before proceeding."

  json_msg=$(python3 -c "import sys,json; print(json.dumps(sys.argv[1]))" "$msg" 2>/dev/null) || exit 0
  printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":%s}}' "$json_msg"
fi
