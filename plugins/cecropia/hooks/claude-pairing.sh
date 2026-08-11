#!/bin/bash

# PreToolUse フック: claude-ask / claude-review 呼び出し時に session_id を検証する。
#
# ペアリングファイルパスは CLAUDE_PLUGIN_DATA から組み立てる。
#
# stdin : Claude Code が渡すツール呼び出し情報 JSON
# stdout: {"decision":"block","reason":"..."} (ブロック時のみ)
# exit  : 0=許可, 2=ブロック

FLAT="$(cat | tr -d '\n')"

# claude-ask / claude-review のみ対象（claude-pairing 自身は除外）
SUBAGENT_TYPE="$(printf '%s' "$FLAT" \
  | grep -o '"subagent_type"[[:space:]]*:[[:space:]]*"[^"]*"' \
  | sed 's/.*"\([^"]*\)"$/\1/')"
case "$SUBAGENT_TYPE" in
  *claude-ask|*claude-review) ;;
  *) exit 0 ;;
esac

PAIRING_FILE=""
if [[ -z "$PAIRING_FILE" && -n "${CLAUDE_PLUGIN_DATA:-}" ]]; then
  PAIRING_FILE="${CLAUDE_PLUGIN_DATA}/claude-pairing.txt"
fi
[[ -z "$PAIRING_FILE" || ! -f "$PAIRING_FILE" ]] && exit 0

CLAUDE_SESSION_ID="$(printf '%s' "$FLAT" \
  | grep -o '"session_id"[[:space:]]*:[[:space:]]*"[^"]*"' \
  | sed 's/.*"\([^"]*\)"$/\1/')"
[[ -z "$CLAUDE_SESSION_ID" ]] && exit 0

# ペアリングファイルから期待するペアリング先 Session ID を取得
# 形式: CLAUDE: <id>, PAIRED: <id>
EXPECTED_PAIRED_ID="$(grep "^CLAUDE: ${CLAUDE_SESSION_ID}," "$PAIRING_FILE" | sed 's/.*PAIRED: //')"
[[ -z "$EXPECTED_PAIRED_ID" ]] && exit 0

# プロンプトにペアリング先 Session ID が含まれているか確認
printf '%s' "$FLAT" | grep -qF "$EXPECTED_PAIRED_ID" && exit 0

printf '{"decision":"block","reason":"Session ID %s を指定してください（このセッションにペアリングされた Claude セッション ID です）"}' \
  "$EXPECTED_PAIRED_ID"
exit 2
