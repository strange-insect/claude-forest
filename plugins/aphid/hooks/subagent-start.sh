#!/bin/bash

# SubagentStart フック
# サブエージェントに CLAUDE_PLUGIN_ROOT / CLAUDE_PLUGIN_DATA を
# additionalContext 経由で伝える

PAYLOAD="$(cat)"

AGENT_TYPE="$(printf '%s' "$PAYLOAD" | sed -n 's/.*"agent_type"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
PLUGIN_NAME="$(sed -n 's/.*"name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json" | head -1)"

if [[ "$AGENT_TYPE" != "${PLUGIN_NAME}:"* ]]; then
  exit 0
fi

# Windows パスの `\` だけ JSON 用に二重化する。
# ダブルクォートや制御文字などへの過剰対応はしない方針
json_escape() {
  sed 's/\\/\\\\/g' <<<"$1"
}

SET_CLAUDE_PLUGIN_ROOT="CLAUDE_PLUGIN_ROOT=$(json_escape "${CLAUDE_PLUGIN_ROOT}")"
SET_CLAUDE_PLUGIN_DATA="CLAUDE_PLUGIN_DATA=$(json_escape "${CLAUDE_PLUGIN_DATA}")"
CONTEXT_LINES="${SET_CLAUDE_PLUGIN_ROOT}\\n${SET_CLAUDE_PLUGIN_DATA}"
cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SubagentStart",
    "additionalContext": "${CONTEXT_LINES}"
  }
}
EOF
