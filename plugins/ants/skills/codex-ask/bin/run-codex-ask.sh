#!/usr/bin/env bash
# run-codex-ask.sh
# Codex を使って 1問1答形式の Q&A を実行し、結果を JSON ファイルに保存してパスを返す
#
# 使い方:
#   run-codex-ask.sh [--session-id UUID] --message "質問テキスト"
#   run-codex-ask.sh [--session-id UUID] <<'EOF'
#   質問テキスト（複数行可）
#   EOF
#
# 出力形式 (stdout):
#   <JSON ファイルの絶対パス>
#
# 終了コード:
#   0: 成功
#   1: エラー（エラー内容を含む JSON ファイルのパスは stdout に出力済み）
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

[[ -z "$MESSAGE" ]] && MESSAGE=$(cat)
[[ -z "$MESSAGE" ]] && { echo "ERROR: --message または stdin でメッセージを指定してください" >&2; exit 1; }

# --- 保存ディレクトリ ---
SAVE_DIR="${TMPDIR:-/tmp}/codex-ask"
mkdir -p "$SAVE_DIR"

# --- JSON ファイルパス ---
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
PROJECT=$(basename "$(pwd)")
JSON_FILE="${SAVE_DIR}/codex-ask_${PROJECT}_${TIMESTAMP}.json"

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

# --- JSON ファイル保存関数 ---
save_json() {
  local session_id="$1"
  local answer="$2"
  local status="$3"
  local exit_code="$4"

  jq -n \
    --arg model      "codex" \
    --arg type       "ask" \
    --arg mode       "$MODE" \
    --arg session_id "$session_id" \
    --arg timestamp  "$(date '+%Y-%m-%d %H:%M:%S')" \
    --arg directory  "$(pwd)" \
    --arg project    "$PROJECT" \
    --arg message    "$MESSAGE" \
    --arg answer     "$answer" \
    --arg status     "$status" \
    --argjson exit_code "$exit_code" \
    '{
      model:      $model,
      type:       $type,
      mode:       $mode,
      session_id: $session_id,
      timestamp:  $timestamp,
      directory:  $directory,
      project:    $project,
      message:    $message,
      answer:     $answer,
      status:     $status,
      exit_code:  $exit_code
    }' > "$JSON_FILE"

  printf '%s\n' "$JSON_FILE"
}

# --- プロンプト構築 ---
PROMPT=$(printf 'ファイルの読み取りと Web 検索は許可する。ファイルの書き込み・作成は行わないこと。\n\n%s\n' "$MESSAGE")

# --- 新規 / 継続 ---
MODE=$([[ -n "$SESSION_ID" ]] && echo "continuation" || echo "new")

# --- Codex 実行 ---
EXIT_CODE=0

if [[ -n "$SESSION_ID" ]]; then
  echo "$PROMPT" | codex exec resume "$SESSION_ID" --full-auto --json -o "$TMP_MSG" - \
    >"$TMP_JSONL" 2>"$TMP_STDERR" || EXIT_CODE=$?

  NEW_ID=$(extract_session_id "$TMP_JSONL")
  EXTRACTED_SESSION_ID="${NEW_ID:-unresolved}"
  [[ "$EXTRACTED_SESSION_ID" == "unresolved" ]] && EXTRACTED_SESSION_ID="$SESSION_ID"
else
  echo "$PROMPT" | codex exec --full-auto --json -o "$TMP_MSG" - \
    >"$TMP_JSONL" 2>"$TMP_STDERR" || EXIT_CODE=$?

  EXTRACTED_SESSION_ID=$(extract_session_id "$TMP_JSONL")
fi

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

  save_json "${SESSION_ID:-unresolved}" "$ERROR_OUTPUT" "error" "$EXIT_CODE"
  exit 1
fi

# --- 正常出力 ---
ANSWER=""
if [[ -s "$TMP_MSG" ]]; then
  ANSWER=$(cat "$TMP_MSG")
else
  ANSWER="（回答の取得に失敗しました - 出力ファイルが空です）"
fi

save_json "$EXTRACTED_SESSION_ID" "$ANSWER" "success" "0"
