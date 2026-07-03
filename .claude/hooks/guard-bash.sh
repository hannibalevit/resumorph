#!/usr/bin/env bash
# PreToolUse guard on Bash: block secrets from being staged/committed,
# and block destructive commands that wipe the docker data volume
# (SQLite DB + Fernet encryption key).
set -euo pipefail

cmd=$(jq -r '.tool_input.command // empty')
[[ -z "$cmd" ]] && exit 0

deny() {
  jq -n --arg reason "$1" \
    '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$reason}}'
  exit 0
}

if echo "$cmd" | grep -qE '(^|[;&|]|[[:space:]])git[[:space:]]+(add|commit)\b'; then
  if echo "$cmd" | grep -qE '(^|[/[:space:]])(server/)?\.env([[:space:]]|$)|encryption\.key'; then
    deny "Blocked: this command references server/.env or an encryption.key file. These hold the real MASTER_ENCRYPTION_KEY / LLM API keys and must never be committed. Stage other files explicitly by name instead."
  fi
fi

if echo "$cmd" | grep -qE '(^|[;&|]|[[:space:]])make[[:space:]]+clean([[:space:]]|$)' \
  || echo "$cmd" | grep -qE '(docker[-[:space:]]compose|docker[[:space:]]+compose)[[:space:]]+down[[:space:]]+.*(-v\b|--volumes\b)'; then
  deny "Blocked: this command deletes the docker data volume, which holds the SQLite DB and the encryption key. This can't be undone from here. If you really want to wipe local data, run 'make clean' or 'docker compose down -v' yourself in a terminal."
fi

exit 0
