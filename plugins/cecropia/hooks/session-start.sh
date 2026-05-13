#!/bin/bash

# SessionStart フック
# セッション開始時に CLAUDE_SESSION_ID を
# CLAUDE_ENV_FILE 経由で後続 subprocess に継承させる

# session_id を永続化 (best-effort)
# session_id は UUID 形式なのでエスケープ文字を含まず、sed (POSIX) の素朴パースで十分。
SESSION_ID="$(tr -d '\n' | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"

if [[ -n "${CLAUDE_ENV_FILE:-}" ]] && grep -q "^CLAUDE_SESSION_ID=" "$CLAUDE_ENV_FILE" 2>/dev/null; then
  exit 0
fi

if [[ -n "$SESSION_ID" && -n "${CLAUDE_ENV_FILE:-}" ]]; then
  printf 'CLAUDE_SESSION_ID=%q\n' "$SESSION_ID" >> "$CLAUDE_ENV_FILE"
fi

exit 0
