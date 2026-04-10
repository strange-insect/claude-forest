#!/bin/bash
# フックスクリプトの雛形
#
# 利用可能な環境変数:
#   $CLAUDE_PROJECT_DIR  — プロジェクトのルートディレクトリ
#   $CLAUDE_PLUGIN_ROOT  — プラグインディレクトリ
#   $CLAUDE_PLUGIN_DATA  — プラグインの永続データディレクトリ
#   $CLAUDE_ENV_FILE     — 環境変数を永続化するファイル（SessionStart/CwdChanged/FileChanged時）
#
# stdin から受け取るJSONの例（PreToolUse/PostToolUse時）:
#   {
#     "session_id": "abc123",
#     "cwd": "/path/to/project",
#     "hook_event_name": "PreToolUse",
#     "permission_mode": "default",
#     "tool_name": "Bash",
#     "tool_input": { "command": "..." }
#   }
#
# exit code:
#   0 — 成功（処理を続行）
#   2 — ブロック（stderrの内容をClaudeにフィードバック）
#   その他 — エラー（処理は続行されるがエラーが表示される）

set -euo pipefail

INPUT=$(cat)

# 必要なフィールドを取得
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
# TOOL_INPUT=$(echo "$INPUT" | jq -r '.tool_input // empty')
# SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
# CWD=$(echo "$INPUT" | jq -r '.cwd // empty')

# ---- ここにロジックを記述 ----

# 例: 特定のツール呼び出しをブロックする場合
# if [[ "$TOOL_NAME" == "SomeTool" ]]; then
#   echo "このツールは使用できません" >&2
#   exit 2
# fi

# 例: JSON で追加コンテキストを返す場合（exit 0 時のみ有効）
# echo '{"hookSpecificOutput": {"additionalContext": "Claudeへの追加情報"}}'

exit 0
