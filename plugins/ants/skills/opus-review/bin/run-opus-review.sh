#!/usr/bin/env bash
# run-opus-review.sh
# Claude Code CLI (claude -p) + Opus モデルを使ってコードレビューを実行し、
# 結果を JSON ファイルに保存してパスを返す
#
# 使い方:
#   run-opus-review.sh [--session-id UUID] --message "レビュー指示"
#   run-opus-review.sh [--session-id UUID] <<'EOF'
#   レビュー指示（複数行可）
#   EOF
#
# レビュー用の固定プロンプト（役割・出力ルール・デフォルト観点）を先頭に付加する。
# レビュー対象・観点・背景は message に含めること。
# セッション継続時（--session-id 指定時）は固定プロンプトを付加しない。
#
# 出力形式 (stdout):
#   <JSON ファイルの絶対パス>
#
# 終了コード:
#   0: 成功
#   1: エラー（エラー内容を含む JSON ファイルのパスは stdout に出力済み）
#
# ツール制限: Read/Glob/Grep/Bash のみ許可（書き込み系は使用不可）。
set -euo pipefail

# --- CLAUDECODE 環境変数の無効化 ---
unset CLAUDECODE CLAUDE_CODE_ENTRYPOINT 2>/dev/null || true

# --- 依存チェック ---
command -v claude >/dev/null 2>&1 || { echo "ERROR: 'claude' コマンドが見つかりません。Claude Code CLI をインストールしてください。" >&2; exit 1; }
command -v jq    >/dev/null 2>&1 || { echo "ERROR: 'jq' コマンドが見つかりません。" >&2; exit 1; }

# --- 引数パース ---
MESSAGE=""
SESSION_ID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --message)    MESSAGE="$2";    shift 2 ;;
    --session-id) SESSION_ID="$2"; shift 2 ;;
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
JSON_FILE="${SAVE_DIR}/opus-review_${PROJECT}_${TIMESTAMP}.json"

# --- 一時ファイル ---
TMP_OUTPUT=$(mktemp /tmp/opus-review-output-XXXXXX)
TMP_STDERR=$(mktemp /tmp/opus-review-err-XXXXXX)

cleanup() { rm -f "$TMP_OUTPUT" "$TMP_STDERR"; }
trap cleanup EXIT

# --- session_id / 回答 抽出ヘルパー ---
extract_session_id() {
  local result
  result=$(jq -r '.session_id // empty' "$1" 2>/dev/null || true)
  if [[ -n "${result:-}" && "$result" != "null" ]]; then
    printf '%s' "$result"
  else
    printf 'unresolved'
  fi
}

extract_result() {
  jq -r '.result // empty' "$1" 2>/dev/null || true
}

# --- JSON ファイル保存関数 ---
save_json() {
  local session_id="$1" answer="$2" status="$3" exit_code="$4"

  jq -n \
    --arg  type       "opus" \
    --arg  session_id "$session_id" \
    --arg  timestamp  "$(date '+%Y-%m-%d %H:%M:%S')" \
    --arg  directory  "$(pwd)" \
    --arg  project    "$PROJECT" \
    --arg  message    "$MESSAGE" \
    --arg  answer     "$answer" \
    --arg  status     "$status" \
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

# --- プロンプト構築 ---
# 新規レビュー時のみ固定プロンプトを先頭に付加する
if [[ -z "$SESSION_ID" ]]; then
  FIXED_PROMPT='あなたはコードレビューを担当するシニアエンジニアです。
コードの修正は一切行わず、レビューコメントの出力のみを行ってください。
ファイルの読み取りは許可されていますが、書き込みは行わないでください。

【レビュー出力ルール】
- 問題の深刻度を示すこと（Critical / Warning / Info / Suggestion）
- ファイルパスと行番号を明記すること
- 修正案がある場合は具体的なコード例を含めること（実際の修正はしない）

【レビュー観点（デフォルト）】
変更差分だけでなく、変更箇所の周辺コードも読み、以下を幅広く・深くレビューすること:

1. **正確性・ロジック**: バグ、エッジケース、境界値、競合状態
2. **セキュリティ**: インジェクション、認証・認可漏れ、機密情報の露出
3. **ドキュメント整合性**: README・コメント・JSDoc/docstring・CHANGELOG 等の更新漏れ
4. **周辺コードとの整合性**: 変更していない関数・クラス・設定・テストが変更後の実装と矛盾していないか
5. **類似機能との整合性**: コードベース内の類似した実装・命名規則・パターンと乖離していないか
6. **ワークフロー・連携影響**: 上流・下流の処理フロー、呼び出し元・呼び出し先との接続部分に影響が出ていないか
7. **データライフサイクル**: 同じデータを参照・更新する機能との不整合
8. **テスト網羅性**: 追加・変更したロジックに対応するテストが存在するか
9. **保守性**: 命名、重複、抽象化の適切さ
10. **パフォーマンス**: 不要な計算・I/O・メモリ使用'
  PROMPT="${FIXED_PROMPT}

${MESSAGE}"
else
  PROMPT="$MESSAGE"
fi

# --- Write/Edit を除いた読み取り系ツールのみ許可 ---
ALLOWED_TOOLS="Read,Glob,Grep,Bash"

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
    NEW_ID=$(extract_session_id "$TMP_OUTPUT")
    EXTRACTED_SESSION_ID="${NEW_ID:-unresolved}"
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
if [[ $EXIT_CODE -ne 0 ]] ; then
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
  ANSWER="（レビュー結果の取得に失敗しました - 出力が空です）"
fi

save_json "$EXTRACTED_SESSION_ID" "$ANSWER" "success" "0"
