#!/bin/bash

# PreToolUse フック: codex-ask / codex-review 呼び出し時に session_id を検証する。
#
# ペアリングファイルパスは CLAUDE_PLUGIN_DATA から組み立てる。
#
# stdin : Claude Code が渡すツール呼び出し情報 JSON
# stdout: {"decision":"block","reason":"..."} (ブロック時のみ)
# exit  : 0=許可, 2=ブロック

FLAT="$(cat | tr -d '\n')"

# codex-ask / codex-review のみ対象（codex-pairing 自身は除外）
SUBAGENT_TYPE="$(printf '%s' "$FLAT" \
  | grep -o '"subagent_type"[[:space:]]*:[[:space:]]*"[^"]*"' \
  | sed 's/.*"\([^"]*\)"$/\1/')"
case "$SUBAGENT_TYPE" in
  *codex-ask|*codex-review) ;;
  *) exit 0 ;;
esac

PAIRING_FILE=""
if [[ -z "$PAIRING_FILE" && -n "${CLAUDE_PLUGIN_DATA:-}" ]]; then
  PAIRING_FILE="${CLAUDE_PLUGIN_DATA}/codex-pairing.txt"
fi
[[ -z "$PAIRING_FILE" || ! -f "$PAIRING_FILE" ]] && exit 0

CLAUDE_SESSION_ID="$(printf '%s' "$FLAT" \
  | grep -o '"session_id"[[:space:]]*:[[:space:]]*"[^"]*"' \
  | sed 's/.*"\([^"]*\)"$/\1/')"
[[ -z "$CLAUDE_SESSION_ID" ]] && exit 0

# ペアリングファイルから期待する Codex Session ID を取得
# 形式: CLAUDE: <id>, CODEX: <id>
EXPECTED_CODEX_ID="$(grep "^CLAUDE: ${CLAUDE_SESSION_ID}," "$PAIRING_FILE" | sed 's/.*CODEX: //')"
[[ -z "$EXPECTED_CODEX_ID" ]] && exit 0

# プロンプトに Codex Session ID が含まれているか確認
printf '%s' "$FLAT" | grep -qF "$EXPECTED_CODEX_ID" && exit 0

printf '{"decision":"block","reason":"Session ID %s を指定してください（このセッションにペアリングされた Codex セッション ID です）"}' \
  "$EXPECTED_CODEX_ID"
exit 2
