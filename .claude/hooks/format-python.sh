#!/usr/bin/env bash
# PostToolUse on Edit|Write: auto-format touched server/**/*.py files with ruff,
# since no CI enforces backend formatting.
set -euo pipefail

file=$(jq -r '.tool_input.file_path // .tool_response.filePath // empty')
[[ -z "$file" ]] && exit 0

case "$file" in
  */server/*.py|server/*.py) ;;
  *) exit 0 ;;
esac
[[ -f "$file" ]] || exit 0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

(cd "$REPO_ROOT/server" && uv run ruff format "$file") 2>/dev/null || true
exit 0
