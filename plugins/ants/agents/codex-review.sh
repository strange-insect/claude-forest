#!/usr/bin/env bash
# codex-review.sh
# Codex を使ってコードレビューを実行し、結果を JSON ファイルに保存してパスを返す
#
# 使い方:
#   codex-review.sh [--session-id UUID] --message "レビュー指示"
#   codex-review.sh [--session-id UUID] <<'EOF'
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
set -euo pipefail

# --- 依存チェック ---
command -v codex >/dev/null 2>&1 || { echo "ERROR: 'codex' コマンドが見つかりません。OpenAI Codex CLI をインストールしてください。" >&2; exit 1; }
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

# --- 新規 / 継続 ---
MODE=$([[ -n "$SESSION_ID" ]] && echo "continuation" || echo "new")

# --- 保存ディレクトリ ---
# JSON は /tmp/<model>-ask/ に集約する（review/ask 共通。save-ask-log.sh の
# SAVE_DIR=/tmp/${MODEL}-ask ロジックと整合させるため codex-review もここに置く）
# 共用ホストでの覗き見防止のため SAVE_DIR を 0700 で作る。
# install -d は既存ディレクトリにも chmod を適用するため、移行前に作られた 0755 のディレクトリも矯正される
SAVE_DIR="${TMPDIR:-/tmp}/codex-ask"
install -d -m 700 "$SAVE_DIR"

# --- JSON ファイルパス ---
# 並列起動時の衝突回避のためミリ秒精度のタイムスタンプを使用
TIMESTAMP=$(date '+%Y%m%d_%H%M%S_%3N')
PROJECT=$(basename "$(pwd)")
JSON_FILE="${SAVE_DIR}/${TIMESTAMP}_${PROJECT}_codex-review.json"

# --- 一時ファイル ---
TMP_JSONL=$(mktemp /tmp/codex-review-jsonl-XXXXXX)
TMP_MSG=$(mktemp  /tmp/codex-review-msg-XXXXXX)
TMP_STDERR=$(mktemp /tmp/codex-review-err-XXXXXX)

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
  local result
  result=$(jq -r 'select(.type == "thread.started") | .thread_id' "$1" 2>/dev/null | head -1 || true)
  if [[ -n "${result:-}" && "$result" != "null" ]]; then
    printf '%s' "$result"
  else
    printf 'unresolved'
  fi
}

# --- JSON ファイル保存関数 ---
save_json() {
  local session_id="$1" answer="$2" status="$3" exit_code="$4"

  # JSON 本体も他ユーザから読まれないよう umask 077 をサブシェル内で適用
  (umask 077 && jq -n \
    --arg  model      "codex" \
    --arg  type       "review" \
    --arg  mode       "$MODE" \
    --arg  session_id "$session_id" \
    --arg  timestamp  "$(date '+%Y-%m-%d %H:%M:%S')" \
    --arg  directory  "$(pwd)" \
    --arg  project    "$PROJECT" \
    --arg  message    "$PROMPT" \
    --arg  answer     "$answer" \
    --arg  status     "$status" \
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

# --- プロンプト構築 ---
# 新規レビュー時のみ固定プロンプトを先頭に付加する
if [[ -z "$SESSION_ID" ]]; then
  FIXED_PROMPT='コードレビューを実施してください。
コードの修正は一切行わず、レビューコメントの出力のみを行ってください。
ファイルの読み取りは許可されていますが、書き込みは行わないでください。

【レビュー出力ルール】
- 問題の深刻度を示すこと（Critical / Warning / Info / Suggestion）
- ファイルパスと行番号を明記すること
- 修正案がある場合は具体的なコード例を含めること（実際の修正はしない）
- 変更差分だけでなく、変更箇所の周辺コードも読み、以下を幅広く・深くレビューすること

【標準的なレビュー観点】

1. **正確性・ロジック**: バグ、エッジケース、境界値、競合状態
2. **セキュリティ**: インジェクション、認証・認可漏れ、機密情報の露出
3. **ドキュメント整合性**: README・コメント・JSDoc/docstring・CHANGELOG 等の更新漏れ
4. **周辺コードとの整合性**: 変更していない関数・クラス・設定・テストが変更後の実装と矛盾していないか
5. **類似機能との整合性**: コードベース内の類似した実装・命名規則・パターンと乖離していないか
6. **ワークフロー・連携影響**: 上流・下流の処理フロー、呼び出し元・呼び出し先との接続部分に影響が出ていないか
7. **データライフサイクル**: 同じデータを参照・更新する機能との不整合
8. **テスト網羅性**: 追加・変更したロジックに対応するテストが存在するか
9. **保守性**: 命名、重複、抽象化の適切さ
10. **パフォーマンス**: 不要な計算・I/O・メモリ使用

【ユーザからの指示文】
'
  PROMPT="${FIXED_PROMPT}${MESSAGE}"
else
  PROMPT="$MESSAGE"
fi

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
  # 取得後に失敗した場合の障害調査・リトライ導線を切らないため）
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
  ANSWER="（レビュー結果の取得に失敗しました - 出力ファイルが空です）"
fi

save_json "$EXTRACTED_SESSION_ID" "$ANSWER" "success" "0"
