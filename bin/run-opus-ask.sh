#!/usr/bin/env bash
# run-opus-ask.sh
# Claude Code CLI (claude -p) + Opus モデルを使って 1問1答形式の Q&A を実行し、
# session_id と回答を返す
#
# 使い方:
#   run-opus-ask.sh --question "質問テキスト" [--context "背景情報"]
#   run-opus-ask.sh --session-id UUID --question "追加の質問" [--context "背景情報"]
#
# 出力形式 (stdout):
#   OPUS_SESSION_ID=<uuid or unresolved>
#   ---OPUS_ASK_OUTPUT---
#   <回答本文>
#
# session_id を指定すると既存のセッションを継続し、会話の文脈を保持したまま
# 追加の質問を送ることができる。
#
# ツール制限により書き込み系ツール（Write/Edit）は使用不可。
# 読み取り（Read/Glob/Grep/Bash）と Web 検索（WebSearch/WebFetch）のみ許可。
set -euo pipefail

# --- CLAUDECODE 環境変数の無効化 ---
# Claude Code 内からネストで claude -p を呼ぶため、ネスト検知変数を除去する
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

if [[ -z "$MESSAGE" ]]; then
  echo "ERROR: --message が指定されていません" >&2
  exit 1
fi

# --- 保存ディレクトリ ---
SAVE_DIR="${TMPDIR:-/tmp}/opus-ask"
mkdir -p "$SAVE_DIR"

# --- 一時ファイル ---
TMP_OUTPUT=$(mktemp /tmp/opus-ask-output-XXXXXX)
TMP_STDERR=$(mktemp /tmp/opus-ask-err-XXXXXX)
TMP_PROMPT=$(mktemp /tmp/opus-ask-prompt-XXXXXX)

cleanup() {
  rm -f "$TMP_OUTPUT" "$TMP_STDERR" "$TMP_PROMPT"
}
trap cleanup EXIT

# --- session_id 抽出ヘルパー ---
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

# --- 回答本文抽出ヘルパー ---
extract_result() {
  local json_file="$1"
  jq -r '.result // empty' "$json_file" 2>/dev/null || true
}

# --- プロンプト構築 ---
build_prompt() {
  printf '%s\n' "$MESSAGE"
}

# --- Claude 実行 ---
EXIT_CODE=0
EXTRACTED_SESSION_ID="unresolved"
CLAUDE_CMD_BASE=""
USER_PROMPT=""

# Write/Edit を除いた読み取り系ツール + Web 検索のみ許可
ALLOWED_TOOLS="Read,Glob,Grep,Bash,WebSearch,WebFetch"

build_prompt > "$TMP_PROMPT"
USER_PROMPT=$(cat "$TMP_PROMPT")

if [[ -n "$SESSION_ID" ]]; then
  # 継続会話
  CLAUDE_CMD_BASE="claude -p \\
  --output-format json \\
  --model Opus \\
  --resume \"${SESSION_ID}\" \\
  --dangerously-skip-permissions \\
  --tools \"${ALLOWED_TOOLS}\""

  cat "$TMP_PROMPT" | claude -p \
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
  # 新規会話
  CLAUDE_CMD_BASE="claude -p \\
  --output-format json \\
  --model Opus \\
  --dangerously-skip-permissions \\
  --tools \"${ALLOWED_TOOLS}\""

  cat "$TMP_PROMPT" | claude -p \
    --output-format json \
    --model Opus \
    --dangerously-skip-permissions \
    --tools "$ALLOWED_TOOLS" \
    > "$TMP_OUTPUT" 2>"$TMP_STDERR" || EXIT_CODE=$?

  if [[ $EXIT_CODE -eq 0 ]]; then
    EXTRACTED_SESSION_ID=$(extract_session_id "$TMP_OUTPUT")
  fi
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
  local save_file="${SAVE_DIR}/opus-ask_${project_name}_${timestamp}.md"

  {
    cat <<'INSTRUCTION'
# Claude への指示
1. このファイルのフルパスを必ずユーザに提示してください
2. 「Opus の回答」セクションの内容を必ず **原文のまま** **ユーザーに提示** してください
3. 会話を続ける場合は session_id を提示してください
INSTRUCTION
    echo ""
    echo "---"
    echo ""

    echo "# Opus Ask Log"
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
    echo -e "cat <<'USER_PROMPT' | $CLAUDE_CMD_BASE"
    echo "$USER_PROMPT"
    echo "USER_PROMPT"
    echo '```'
    echo ""

    echo "---"
    echo ""
    echo "## Opus の回答"
    echo ""
    echo "$answer"
  } > "$save_file"

  echo "OPUS_ASK_LOG=${save_file}" >&2
}

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

  save_ask_log "unresolved" "$ERROR_OUTPUT" "true"

  echo "OPUS_SESSION_ID=unresolved"
  echo "---OPUS_ASK_OUTPUT---"
  echo "$ERROR_OUTPUT"
  exit 1
fi

# --- 正常出力 ---
ANSWER=$(extract_result "$TMP_OUTPUT")
if [[ -z "$ANSWER" ]]; then
  ANSWER="（回答の取得に失敗しました - 出力が空です）"
fi

save_ask_log "$EXTRACTED_SESSION_ID" "$ANSWER"

printf 'OPUS_SESSION_ID=%s\n' "$EXTRACTED_SESSION_ID"
printf -- '---OPUS_ASK_OUTPUT---\n'
printf '%s\n' "$ANSWER"
