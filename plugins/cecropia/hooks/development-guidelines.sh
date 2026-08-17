#!/bin/bash

# SessionStart フック
# 開発ガイドラインを additionalContext としてセッションに注入する。
#
# 環境変数 CECROPIA_DISABLE_DEVELOPMENT_GUIDELINES に空文字以外を設定した場合は注入しない。

# stdin の hook payload を読み捨てない場合、呼び出し元が SIGPIPE により異常終了する可能性がある
cat >/dev/null

[[ -z "${CECROPIA_DISABLE_DEVELOPMENT_GUIDELINES:-}" ]] || exit 0

GUIDELINES="$(cat "${CLAUDE_PLUGIN_ROOT}/agents/development-guidelines.txt" 2>/dev/null)"

# 本文を取得できない場合、前置きだけを注入しても意味を成さないため何も出力しない
[[ -n "$GUIDELINES" ]] || exit 0

json_escape() {
  local text="$1"
  text="${text//\\/\\\\}"
  text="${text//\"/\\\"}"
  text="${text//$'\r'/}"
  text="${text//$'\t'/\\t}"
  text="${text//$'\n'/\\n}"
  printf '%s' "$text"
}

HEADER='以下は開発ガイドラインです。実装・修正時に抵触していないか確認してください。'

cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "$(json_escape "${HEADER}"$'\n\n'"${GUIDELINES}")"
  }
}
EOF
