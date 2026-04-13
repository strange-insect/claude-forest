#!/usr/bin/env bash
# save-ask-log.sh
# ask 系 JSON ファイルを Markdown ログファイルに変換して保存し、パスを返す
#
# 使い方:
#   save-ask-log.sh <json-file-path>
#
# 出力形式 (stdout):
#   <Markdown ログファイルの絶対パス>
#
# JSON スキーマ:
#   {
#     "model":      "codex" | "opus",
#     "type":       "ask" | "review",
#     "mode":       "new" | "continuation",
#     "session_id": "...",
#     "timestamp":  "YYYY-MM-DD HH:MM:SS",
#     "directory":  "...",
#     "project":    "...",
#     "message":    "...",
#     "answer":     "...",
#     "status":     "success" | "error",
#     "exit_code":  0
#   }
set -euo pipefail

command -v jq >/dev/null 2>&1 || { echo "ERROR: 'jq' コマンドが見つかりません。" >&2; exit 1; }

# --- 引数チェック ---
if [[ $# -ne 1 ]]; then
  echo "ERROR: 使い方: save-ask-log.sh <json-file-path>" >&2
  exit 1
fi

JSON_FILE="$1"

if [[ ! -f "$JSON_FILE" ]]; then
  echo "ERROR: JSON ファイルが見つかりません: $JSON_FILE" >&2
  exit 1
fi

# --- JSON パース ---
MODEL=$(jq -r '.model // .type' "$JSON_FILE")
TYPE=$(jq -r '.type' "$JSON_FILE")
MODE=$(jq -r '.mode // "new"' "$JSON_FILE")
SESSION_ID=$(jq -r '.session_id' "$JSON_FILE")
TIMESTAMP=$(jq -r '.timestamp' "$JSON_FILE")
DIRECTORY=$(jq -r '.directory' "$JSON_FILE")
PROJECT=$(jq -r '.project' "$JSON_FILE")
MESSAGE=$(jq -r '.message' "$JSON_FILE")
ANSWER=$(jq -r '.answer' "$JSON_FILE")
STATUS=$(jq -r '.status' "$JSON_FILE")
EXIT_CODE=$(jq -r '.exit_code' "$JSON_FILE")

# --- ラベルと保存先 ---
case "$MODEL" in
  codex) LABEL="Codex" ; SAVE_DIR="${TMPDIR:-/tmp}/codex-ask" ;;
  opus)  LABEL="Opus"  ; SAVE_DIR="${TMPDIR:-/tmp}/opus-ask" ;;
  *)     LABEL="$MODEL"; SAVE_DIR="${TMPDIR:-/tmp}/${MODEL}-ask" ;;
esac

case "$TYPE" in
  ask)    SKILL_LABEL="Ask" ;;
  review) SKILL_LABEL="Review" ;;
  *)      SKILL_LABEL="$(echo "${TYPE:0:1}" | tr '[:lower:]' '[:upper:]')${TYPE:1}" ;;
esac
mkdir -p "$SAVE_DIR"

# --- Markdown ファイルパス（.translated サフィックスを除いた名前を使用）---
JSON_BASENAME=$(basename "$JSON_FILE" .json)
MD_FILE="${SAVE_DIR}/${JSON_BASENAME%.translated}.md"

# --- Markdown 生成 ---
{
  echo "# ${LABEL} ${SKILL_LABEL} Log"
  echo ""
  echo "- **日時**: ${TIMESTAMP}"
  echo "- **モード**: ${MODE}"
  echo "- **ディレクトリ**: ${DIRECTORY}"
  echo "- **セッションID**: ${SESSION_ID}"
  [[ "$STATUS" == "error" ]] && echo "- **ステータス**: エラー (exit code: ${EXIT_CODE})"
  echo ""
  echo "---"
  echo ""
  echo "## メッセージ"
  echo ""
  echo "${MESSAGE}"
  echo ""
  echo "---"
  echo ""
  echo "## ${LABEL} の回答"
  echo ""
  echo "${ANSWER}"
} > "$MD_FILE"

printf '%s\n' "$MD_FILE"
