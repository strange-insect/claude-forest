#!/usr/bin/env bash
# opus-ask.sh
# Claude Code CLI (claude -p) + Opus モデルを使って 1問1答形式の Q&A を実行し、
# 結果を JSON ファイルに保存してパスを返す
#
# 使い方:
#   opus-ask.sh [--session-id UUID] --message "質問テキスト"
#   opus-ask.sh [--session-id UUID] <<'EOF'
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
# ツール制限: --tools で Write/Edit を無効化し、Read/Glob/Grep/Bash/WebSearch/WebFetch のみを許可する。
# ただし Bash 経由で `cat > file` 等の書き込みは可能なので、信頼できないリポジトリでの利用には注意。
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

# --- 新規 / 継続 ---
MODE=$([[ -n "$SESSION_ID" ]] && echo "continuation" || echo "new")

# --- 実送信プロンプト（opus-ask は自動付与なし。ログにはこの値が記録される）---
PROMPT="$MESSAGE"

# --- 保存ディレクトリ ---
# 共用ホストでの覗き見防止のため SAVE_DIR を 0700 で作る。
# install -d は既存ディレクトリにも chmod を適用するため、移行前に作られた 0755 のディレクトリも矯正される
SAVE_DIR="${TMPDIR:-/tmp}/opus-ask"
install -d -m 700 "$SAVE_DIR"

# --- JSON ファイルパス ---
# 並列起動時の衝突回避のためミリ秒精度のタイムスタンプを使用
TIMESTAMP=$(date '+%Y%m%d_%H%M%S_%3N')
PROJECT=$(basename "$(pwd)")
JSON_FILE="${SAVE_DIR}/${TIMESTAMP}_${PROJECT}_opus-ask.json"

# --- 一時ファイル ---
TMP_OUTPUT=$(mktemp /tmp/opus-ask-output-XXXXXX)
TMP_STDERR=$(mktemp /tmp/opus-ask-err-XXXXXX)

# save_json 到達前に死んだ場合に空の JSON_FILE がゴミとして残らないよう、
# 完全な書き込みが終わった後にだけ JSON_FILE を保持するフラグ
JSON_FILE_KEEP=0
cleanup() {
  rm -f "$TMP_OUTPUT" "$TMP_STDERR"
  [[ "$JSON_FILE_KEEP" -eq 0 ]] && rm -f "$JSON_FILE"
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

  # JSON 本体も他ユーザから読まれないよう umask 077 をサブシェル内で適用
  (umask 077 && jq -n \
    --arg model      "opus" \
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

# --- 利用可能な built-in ツールセット ---
# Write/Edit は無効化するが、Bash 経由で書き込み可能な点に注意（信頼できないリポジトリでは使用しない）
ALLOWED_TOOLS="Read,Glob,Grep,Bash,WebSearch,WebFetch"

# --- Claude 実行 ---
EXIT_CODE=0
EXTRACTED_SESSION_ID="unresolved"

if [[ -n "$SESSION_ID" ]]; then
  printf '%s\n' "$PROMPT" | claude -p \
    --output-format json \
    --model Opus \
    --resume "$SESSION_ID" \
    --dangerously-skip-permissions \
    --tools "$ALLOWED_TOOLS" \
    > "$TMP_OUTPUT" 2>"$TMP_STDERR" || EXIT_CODE=$?

  if [[ $EXIT_CODE -eq 0 ]]; then
    EXTRACTED_SESSION_ID=$(extract_session_id "$TMP_OUTPUT")
    [[ "$EXTRACTED_SESSION_ID" == "unresolved" ]] && EXTRACTED_SESSION_ID="$SESSION_ID"
  fi
else
  printf '%s\n' "$PROMPT" | claude -p \
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

  # エラー時でも extract_session_id 済みの ID があれば残す（取得後に失敗した場合の障害調査・
  # リトライ導線を切らないため）
  if [[ -n "$EXTRACTED_SESSION_ID" && "$EXTRACTED_SESSION_ID" != "unresolved" ]]; then
    session_for_log="$EXTRACTED_SESSION_ID"
  else
    session_for_log="${SESSION_ID:-unresolved}"
  fi
  save_json "$session_for_log" "$ERROR_OUTPUT" "error" "$EXIT_CODE"
  exit 1
fi

# --- 正常出力 ---
ANSWER=$(extract_result "$TMP_OUTPUT")
if [[ -z "$ANSWER" ]]; then
  ANSWER="（回答の取得に失敗しました - 出力が空です）"
fi

save_json "$EXTRACTED_SESSION_ID" "$ANSWER" "success" "0"
