#!/usr/bin/env bash
# Hook: PostToolUse
# Runs `make lint` after any Python file is edited and injects lint errors as
# context so the agent fixes them immediately rather than accumulating debt.
set -euo pipefail

input=$(cat)

# Extract tool name and affected file path (VS Code uses camelCase tool_input)
tool_name=$(printf '%s' "$input" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('tool_name', ''))
" 2>/dev/null || echo "")

file_path=$(printf '%s' "$input" | python3 -c "
import sys, json
d = json.load(sys.stdin)
ti = d.get('tool_input', {})
# editFiles passes a list; createFile / replaceStringInFile pass a single path
files = ti.get('files', [])
if isinstance(files, list) and files:
    print(files[0].get('filePath', files[0]) if isinstance(files[0], dict) else files[0])
else:
    print(ti.get('filePath', ti.get('file_path', '')))
" 2>/dev/null || echo "")

cwd=$(printf '%s' "$input" | python3 -c "
import sys, json; d = json.load(sys.stdin); print(d.get('cwd', '.'))
" 2>/dev/null || echo ".")

# Only act on file-mutation tools
case "$tool_name" in
  editFiles|edit_file|createFile|create_file|replaceStringInFile|replace_string_in_file|insertIntoFile) ;;
  *) exit 0 ;;
esac

# Only act on Python files
case "$file_path" in
  *.py) ;;
  *) exit 0 ;;
esac

cd "$cwd" 2>/dev/null || exit 0

# Only run if the project has a Makefile with a lint target
if ! grep -q "^lint:" Makefile 2>/dev/null; then
  exit 0
fi

lint_output=$(make lint 2>&1) || lint_failed=true

if [[ "${lint_failed:-false}" == "true" ]]; then
  context="⚠️ Lint errors after editing \`${file_path}\`. Fix before continuing:
\`\`\`
${lint_output}
\`\`\`"
  json_ctx=$(python3 -c "import sys,json; print(json.dumps(sys.argv[1]))" "$context" 2>/dev/null) || {
    json_ctx="\"Lint errors detected after file edit — run make lint to see details\""
  }
  printf '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":%s}}' "$json_ctx"
fi
