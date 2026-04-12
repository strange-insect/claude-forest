#!/usr/bin/env bash
# run-opus-ask.sh
# Claude Code CLI (claude -p) + Opus モデルを使って 1問1答形式の Q&A を実行し、
# 結果を JSON ファイルに保存してパスを返す
#
# 使い方:
#   run-opus-ask.sh [--session-id UUID] --message "質問テキスト"
#   run-opus-ask.sh [--session-id UUID] <<'EOF'
#   質問テキスト（複数行可）
#   EOF
#
# 出力形式 (stdout):
#   <JSON ファイルの絶対パス>
#
# 終了コード:
#   0: 成功
#   1: エラー（エラー内容を含む JSON ファイルのパスは stdout に出力済み）
#
# ツール制限により書き込み系ツール（Write/Edit）は使用不可。
# 読み取り（Read/Glob/Grep/Bash）と Web 検索（WebSearch/WebFetch）のみ許可。
set -euo pipefail

# --- CLAUDECODE 環境変数の無効化 ---
unset CLAUDECODE CLAUDE_CODE_ENTRYPOINT 2>/dev/null || true

# --- 依存チェック ---
command -v claude >/dev/null 2>&1 || { echo "ERROR: 'claude' コマンドが見つかりません。Claude Code CLI をインストールしてください。" >&2; exit 1; }
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
SAVE_DIR="${TMPDIR:-/tmp}/opus-ask"
mkdir -p "$SAVE_DIR"

# --- JSON ファイルパス ---
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
PROJECT=$(basename "$(pwd)")
JSON_FILE="${SAVE_DIR}/opus-ask_${PROJECT}_${TIMESTAMP}.json"

# --- 一時ファイル ---
TMP_OUTPUT=$(mktemp /tmp/opus-ask-output-XXXXXX)
TMP_STDERR=$(mktemp /tmp/opus-ask-err-XXXXXX)

cleanup() {
  rm -f "$TMP_OUTPUT" "$TMP_STDERR"
}
trap cleanup EXIT

# --- session_id / 回答 抽出ヘルパー ---
extract_session_id() {
  local json_file="$1"
  local result
  result=$(jq -r '.session_id // empty' "$json_file" 2>/dev/null || true)
  if [[ -n "${result:-}" && "$result" != "null" ]]; then
    printf '%s' "$result"
  else
    printf 'unresolved'
  fi
}

extract_result() {
  local json_file="$1"
  jq -r '.result // empty' "$json_file" 2>/dev/null || true
}

# --- JSON ファイル保存関数 ---
save_json() {
  local session_id="$1"
  local answer="$2"
  local status="$3"
  local exit_code="$4"

  jq -n \
    --arg type       "opus" \
    --arg session_id "$session_id" \
    --arg timestamp  "$(date '+%Y-%m-%d %H:%M:%S')" \
    --arg directory  "$(pwd)" \
    --arg project    "$PROJECT" \
    --arg message    "$MESSAGE" \
    --arg answer     "$answer" \
    --arg status     "$status" \
    --argjson exit_code "$exit_code" \
    '{
      type:       $type,
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

# --- Write/Edit を除いた読み取り系ツール + Web 検索のみ許可 ---
ALLOWED_TOOLS="Read,Glob,Grep,Bash,WebSearch,WebFetch"

# --- Claude 実行 ---
EXIT_CODE=0
EXTRACTED_SESSION_ID="unresolved"

if [[ -n "$SESSION_ID" ]]; then
  printf '%s\n' "$MESSAGE" | claude -p \
    --output-format json \
    --model Opus \
    --resume "$SESSION_ID" \
    --dangerously-skip-permissions \
    --tools "$ALLOWED_TOOLS" \
    > "$TMP_OUTPUT" 2>"$TMP_STDERR" || EXIT_CODE=$?

  if [[ $EXIT_CODE -eq 0 ]]; then
    NEW_ID=$(extract_session_id "$TMP_OUTPUT")
    EXTRACTED_SESSION_ID="${NEW_ID:-unresolved}"
    [[ "$EXTRACTED_SESSION_ID" == "unresolved" ]] && EXTRACTED_SESSION_ID="$SESSION_ID"
  fi
else
  printf '%s\n' "$MESSAGE" | claude -p \
    --output-format json \
    --model Opus \
    --dangerously-skip-permissions \
    --tools "$ALLOWED_TOOLS" \
    > "$TMP_OUTPUT" 2>"$TMP_STDERR" || EXIT_CODE=$?

  if [[ $EXIT_CODE -eq 0 ]]; then
    EXTRACTED_SESSION_ID=$(extract_session_id "$TMP_OUTPUT")
  fi
fi

# --- エラーハンドリング ---
if [[ $EXIT_CODE -ne 0 ]]; then
  ERROR_OUTPUT="【エラー】claude -p の実行に失敗しました（exit code: $EXIT_CODE）"
  if [[ -s "$TMP_OUTPUT" ]]; then
    ERR_RESULT=$(extract_result "$TMP_OUTPUT")
    if [[ -n "$ERR_RESULT" ]]; then
      ERROR_OUTPUT="${ERROR_OUTPUT}

エラー詳細:
${ERR_RESULT}"
    fi
  fi
  if [[ -s "$TMP_STDERR" ]]; then
    ERROR_OUTPUT="${ERROR_OUTPUT}

stderr:
$(cat "$TMP_STDERR")"
  fi

  save_json "unresolved" "$ERROR_OUTPUT" "error" "$EXIT_CODE"
  exit 1
fi

# --- 正常出力 ---
ANSWER=$(extract_result "$TMP_OUTPUT")
if [[ -z "$ANSWER" ]]; then
  ANSWER="（回答の取得に失敗しました - 出力が空です）"
fi

save_json "$EXTRACTED_SESSION_ID" "$ANSWER" "success" "0"
