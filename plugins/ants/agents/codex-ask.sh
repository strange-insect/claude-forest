#!/usr/bin/env bash
# codex-ask.sh
# Codex を使って 1問1答形式の Q&A を実行し、結果を JSON ファイルに保存してパスを返す
#
# 使い方:
#   codex-ask.sh [--session-id UUID] --message "質問テキスト"
#   codex-ask.sh [--session-id UUID] <<'EOF'
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

# --- 新規 / 継続 ---
MODE=$([[ -n "$SESSION_ID" ]] && echo "continuation" || echo "new")

# --- 実送信プロンプト（codex-ask は自動付与なし。ログにはこの値が記録される）---
PROMPT="$MESSAGE"

# --- 保存ディレクトリ ---
# 共用ホストでの覗き見防止のため SAVE_DIR を 0700 で作る。
# install -d は既存ディレクトリにも chmod を適用するため、移行前に作られた 0755 のディレクトリも矯正される
SAVE_DIR="${TMPDIR:-/tmp}/codex-ask"
install -d -m 700 "$SAVE_DIR"

# --- JSON ファイルパス ---
# 並列起動時の衝突回避のためミリ秒精度のタイムスタンプを使用
TIMESTAMP=$(date '+%Y%m%d_%H%M%S_%3N')
PROJECT=$(basename "$(pwd)")
JSON_FILE="${SAVE_DIR}/${TIMESTAMP}_${PROJECT}_codex-ask.json"

# --- 一時ファイル ---
TMP_JSONL=$(mktemp /tmp/codex-ask-jsonl-XXXXXX)
TMP_MSG=$(mktemp /tmp/codex-ask-msg-XXXXXX)
TMP_STDERR=$(mktemp /tmp/codex-ask-err-XXXXXX)

# save_json 到達前に死んだ場合に空の JSON_FILE がゴミとして残らないよう、
# 完全な書き込みが終わった後にだけ JSON_FILE を保持するフラグ
JSON_FILE_KEEP=0
cleanup() {
  rm -f "$TMP_JSONL" "$TMP_MSG" "$TMP_STDERR"
  [[ "$JSON_FILE_KEEP" -eq 0 ]] && rm -f "$JSON_FILE"
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

  # JSON 本体も他ユーザから読まれないよう umask 077 をサブシェル内で適用
  (umask 077 && jq -n \
    --arg model      "codex" \
    --arg type       "ask" \
    --arg mode       "$MODE" \
    --arg session_id "$session_id" \
    --arg timestamp  "$(date '+%Y-%m-%d %H:%M:%S')" \
    --arg directory  "$(pwd)" \
    --arg project    "$PROJECT" \
    --arg message    "$PROMPT" \
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
    }' > "$JSON_FILE")

  JSON_FILE_KEEP=1
  printf '%s\n' "$JSON_FILE"
}

# --- Codex 実行 ---
EXIT_CODE=0
CODEX_OPTIONS=(--skip-git-repo-check --sandbox read-only --full-auto --json)

if [[ -n "$SESSION_ID" ]]; then
  printf '%s\n' "$PROMPT" | codex --ask-for-approval never exec "${CODEX_OPTIONS[@]}" resume "$SESSION_ID" -o "$TMP_MSG" - \
    >"$TMP_JSONL" 2>"$TMP_STDERR" || EXIT_CODE=$?

  EXTRACTED_SESSION_ID=$(extract_session_id "$TMP_JSONL")
  [[ "$EXTRACTED_SESSION_ID" == "unresolved" ]] && EXTRACTED_SESSION_ID="$SESSION_ID"
else
  printf '%s\n' "$PROMPT" | codex --ask-for-approval never exec "${CODEX_OPTIONS[@]}" -o "$TMP_MSG" - \
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

  # エラー時でも extract_session_id 済みの ID があれば残す（新規セッションで thread.started
  # 取得後に失敗した場合の障害調査・リトライ導線を切らないため）。取れていなければ継続元の
  # SESSION_ID にフォールバック、それも無ければ "unresolved"
  if [[ -n "$EXTRACTED_SESSION_ID" && "$EXTRACTED_SESSION_ID" != "unresolved" ]]; then
    session_for_log="$EXTRACTED_SESSION_ID"
  else
    session_for_log="${SESSION_ID:-unresolved}"
  fi
  save_json "$session_for_log" "$ERROR_OUTPUT" "error" "$EXIT_CODE"
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
