#!/usr/bin/env bash
# run-codex-ask.sh
# Codex を使って 1問1答形式の Q&A を実行し、session_id と回答を返す
#
# 使い方:
#   run-codex-ask.sh --question "質問テキスト" [--context "背景情報"]
#   run-codex-ask.sh --session-id UUID --question "追加の質問" [--context "背景情報"]
#
# 出力形式 (stdout):
#   CODEX_SESSION_ID=<uuid or unresolved>
#   ---CODEX_ASK_OUTPUT---
#   <回答本文>
#
# session_id を指定すると既存のセッションを継続し、会話の文脈を保持したまま
# 追加の質問を送ることができる。
set -euo pipefail

# --- 依存チェック ---
command -v codex >/dev/null 2>&1 || { echo "ERROR: 'codex' コマンドが見つかりません。OpenAI Codex CLI をインストールしてください。" >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "ERROR: 'jq' コマンドが見つかりません。" >&2; exit 1; }

# --- 引数パース ---
MESSAGE=""
SESSION_ID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --message)     MESSAGE="$2";     shift 2 ;;
    --session-id)  SESSION_ID="$2";  shift 2 ;;
    *) echo "ERROR: 不明なオプション: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$MESSAGE" ]]; then
  echo "ERROR: --message が指定されていません" >&2
  exit 1
fi

# --- 保存ディレクトリ ---
SAVE_DIR="${TMPDIR:-/tmp}/codex-ask"
mkdir -p "$SAVE_DIR"

# --- 一時ファイル ---
TMP_JSONL=$(mktemp /tmp/codex-ask-jsonl-XXXXXX)
TMP_MSG=$(mktemp /tmp/codex-ask-msg-XXXXXX)
TMP_STDERR=$(mktemp /tmp/codex-ask-err-XXXXXX)

cleanup() {
  rm -f "$TMP_JSONL" "$TMP_MSG" "$TMP_STDERR"
}
trap cleanup EXIT

# --- session_id 抽出ヘルパー ---
extract_session_id() {
  local jsonl_file="$1"
  local result
  result=$(jq -r 'select(.type == "thread.started") | .thread_id' "$jsonl_file" 2>/dev/null | head -1 || true)
  if [[ -n "${result:-}" && "$result" != "null" ]]; then
    printf '%s' "$result"
  else
    printf 'unresolved'
  fi
}

# --- プロンプト構築 ---
build_prompt() {
  printf 'ファイルの読み取りと Web 検索は許可する。ファイルの書き込み・作成は行わないこと。\n\n%s\n' "$MESSAGE"
}

# --- Codex 実行 ---
EXIT_CODE=0
EXTRACTED_SESSION_ID="unresolved"
PROMPT=$(build_prompt)
CODEX_CMD_BASE=""

if [[ -n "$SESSION_ID" ]]; then
  # 継続会話
  CODEX_CMD_BASE="codex exec resume \"${SESSION_ID}\" \\
  --full-auto \\
  --json"
  echo "$PROMPT" | codex exec resume "$SESSION_ID" --full-auto --json -o "$TMP_MSG" - \
    >"$TMP_JSONL" 2>"$TMP_STDERR" || EXIT_CODE=$?

  NEW_ID=$(extract_session_id "$TMP_JSONL")
  EXTRACTED_SESSION_ID="${NEW_ID:-unresolved}"
  [[ "$EXTRACTED_SESSION_ID" == "unresolved" ]] && EXTRACTED_SESSION_ID="$SESSION_ID"
else
  # 新規会話
  CODEX_CMD_BASE="codex exec \\
  --full-auto \\
  --json"
  echo "$PROMPT" | codex exec --full-auto --json -o "$TMP_MSG" - \
    >"$TMP_JSONL" 2>"$TMP_STDERR" || EXIT_CODE=$?

  EXTRACTED_SESSION_ID=$(extract_session_id "$TMP_JSONL")
fi

# --- ログ保存 ---
save_ask_log() {
  local session_id="$1"
  local answer="$2"
  local is_error="${3:-false}"

  local timestamp
  timestamp=$(date '+%Y%m%d_%H%M%S')
  local project_name
  project_name=$(basename "$(pwd)")
  local save_file="${SAVE_DIR}/codex-ask_${project_name}_${timestamp}.md"

  {
    cat <<'INSTRUCTION'
# Claude への指示
1. このファイルのフルパスを必ずユーザに提示してください
2. 「Codex の回答」セクションの内容を必ず **原文のまま** **ユーザーに提示** してください
3. 会話を続ける場合は session_id を提示してください
INSTRUCTION
    echo ""
    echo "---"
    echo ""

    echo "# Codex Ask Log"
    echo ""
    echo "- **日時**: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "- **ディレクトリ**: $(pwd)"
    echo "- **セッションID**: ${session_id}"
    [[ "$is_error" == "true" ]] && echo "- **ステータス**: エラー (exit code: ${EXIT_CODE})"
    echo ""

    echo "---"
    echo ""
    echo "## メッセージ"
    echo ""
    echo "${MESSAGE}"
    echo ""

    echo "---"
    echo ""
    echo "## 実行したコマンド"
    echo ""
    echo '```bash'
    echo -e "$CODEX_CMD_BASE"
    echo "  \"\$(cat <<'PROMPT'"
    echo "$PROMPT"
    echo "PROMPT"
    echo ")\""
    echo '```'
    echo ""

    echo "---"
    echo ""
    echo "## Codex の回答"
    echo ""
    echo "$answer"
  } > "$save_file"

  echo "CODEX_ASK_LOG=${save_file}" >&2
}

# --- エラーハンドリング ---
if [[ $EXIT_CODE -ne 0 ]]; then
  ERROR_OUTPUT="【エラー】Codex の実行に失敗しました（exit code: $EXIT_CODE）"
  if [[ -s "$TMP_STDERR" ]]; then
    ERROR_OUTPUT="${ERROR_OUTPUT}

エラー詳細:
$(cat "$TMP_STDERR")"
  fi
  if [[ -s "$TMP_MSG" ]]; then
    ERROR_OUTPUT="${ERROR_OUTPUT}

部分的な出力:
$(cat "$TMP_MSG")"
  fi

  save_ask_log "unresolved" "$ERROR_OUTPUT" "true"

  echo "CODEX_SESSION_ID=unresolved"
  echo "---CODEX_ASK_OUTPUT---"
  echo "$ERROR_OUTPUT"
  exit 1
fi

# --- 正常出力 ---
ANSWER=""
if [[ -s "$TMP_MSG" ]]; then
  ANSWER=$(cat "$TMP_MSG")
else
  ANSWER="（回答の取得に失敗しました - 出力ファイルが空です）"
fi

save_ask_log "$EXTRACTED_SESSION_ID" "$ANSWER"

printf 'CODEX_SESSION_ID=%s\n' "$EXTRACTED_SESSION_ID"
printf -- '---CODEX_ASK_OUTPUT---\n'
echo "$ANSWER"
