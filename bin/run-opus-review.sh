#!/usr/bin/env bash
# run-opus-review.sh
# Claude Code CLI (claude -p) + Opus モデルを使ってコードレビューを実行し、
# session_id とレビュー結果を返す
#
# 使い方:
#   run-opus-review.sh --mode new-uncommitted [--targets "file1" --targets "file2"] [--aspects "観点"] [--review-context "背景"]
#   run-opus-review.sh --mode new-base --base main [--aspects "観点"]
#   run-opus-review.sh --mode resume --session-id UUID [--continuation "追加指示"]
#
# 出力形式 (stdout):
#   OPUS_SESSION_ID=<uuid or unresolved>
#   ---OPUS_REVIEW_OUTPUT---
#   <レビュー本文>
set -euo pipefail

# --- CLAUDECODE 環境変数の無効化 ---
# Claude Code 内からネストで claude -p を呼ぶため、ネスト検知変数を除去する
unset CLAUDECODE CLAUDE_CODE_ENTRYPOINT 2>/dev/null || true

# --- 依存チェック ---
command -v claude >/dev/null 2>&1 || { echo "ERROR: 'claude' コマンドが見つかりません。Claude Code CLI をインストールしてください。" >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "ERROR: 'jq' コマンドが見つかりません。" >&2; exit 1; }

# --- 引数パース ---
MODE="new-uncommitted"
BASE_BRANCH="main"
ASPECTS=""
SESSION_ID=""
CONTINUATION=""
TARGETS=()
REVIEW_CONTEXT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)           MODE="$2";           shift 2 ;;
    --base)           BASE_BRANCH="$2";    shift 2 ;;
    --aspects)        ASPECTS="$2";        shift 2 ;;
    --session-id)     SESSION_ID="$2";     shift 2 ;;
    --continuation)   CONTINUATION="$2";   shift 2 ;;
    --targets)        TARGETS+=("$2");     shift 2 ;;
    --review-context) REVIEW_CONTEXT="$2"; shift 2 ;;
    *) echo "ERROR: 不明なオプション: $1" >&2; exit 1 ;;
  esac
done

# --- 保存ディレクトリ ---
SAVE_DIR="${TMPDIR:-/tmp}/reviews"
mkdir -p "$SAVE_DIR"

# --- 一時ファイル ---
TMP_OUTPUT=$(mktemp /tmp/opus-review-output-XXXXXX)
TMP_STDERR=$(mktemp /tmp/opus-review-err-XXXXXX)
TMP_PROMPT=$(mktemp /tmp/opus-review-prompt-XXXXXX)

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

# --- レビュー本文抽出ヘルパー ---
extract_result() {
  local json_file="$1"
  jq -r '.result // empty' "$json_file" 2>/dev/null || true
}

# --- 新規レビュー用プロンプト構築 ---
build_review_prompt() {
  local parts=()

  parts+=("あなたはコードレビューを担当するシニアエンジニアです。
コードの修正は一切行わず、レビューコメントの出力のみを行ってください。
ファイルの読み取りは許可されていますが、書き込みは行わないでください。

【レビュー出力ルール】
- 問題の深刻度を示すこと（Critical / Warning / Info / Suggestion）
- ファイルパスと行番号を明記すること
- 修正案がある場合は具体的なコード例を含めること（実際の修正はしない）")

  if [[ "$MODE" == "new-uncommitted" ]]; then
    parts+=("ワーキングツリーの未コミット変更（staged + unstaged + untracked）をレビューしてください。
git diff や git diff --cached、git ls-files --others --exclude-standard を使って差分を確認してください。")
  elif [[ "$MODE" == "new-base" ]]; then
    # ${BASE_BRANCH} はここで展開してブランチ名をプロンプトに埋め込む
    # \$(...) はリテラル文字列として AI プロンプトに渡す（bash 展開させない）
    parts+=("現在のブランチと ${BASE_BRANCH} ブランチとの差分をレビューしてください。
git diff \$(git merge-base HEAD ${BASE_BRANCH} 2>/dev/null || echo ${BASE_BRANCH}) HEAD を使って差分を確認してください。")
  fi

  if [[ -n "$REVIEW_CONTEXT" ]]; then
    parts+=("【背景・修正意図・注意点】
${REVIEW_CONTEXT}

上記を踏まえてレビューしてください。")
  fi

  if [[ ${#TARGETS[@]} -gt 0 ]]; then
    local target_list=""
    for target in "${TARGETS[@]}"; do
      target_list="${target_list}- ${target}
"
    done
    parts+=("【レビュー対象】
以下のファイルを中心に確認してください:

${target_list}")
  fi

  if [[ -n "$ASPECTS" ]]; then
    parts+=("【レビュー観点】
以下の観点のみに絞ってレビューしてください。この観点以外（コード品質・バグ・セキュリティ等）の指摘は不要です:

${ASPECTS}")
  fi

  local result=""
  for part in "${parts[@]}"; do
    [[ -n "$result" ]] && result+=$'\n\n'
    result+="$part"
  done
  printf '%s\n' "$result"
}

# --- 継続レビュー用プロンプト構築 ---
build_resume_prompt() {
  local continuation_text="${CONTINUATION:-前回の指摘が解消されているか確認してください。}"

  local context_section=""
  if [[ -n "$REVIEW_CONTEXT" ]]; then
    context_section="
【背景・修正意図・注意点】
${REVIEW_CONTEXT}
"
  fi

  cat <<EOF
前回レビューの続きです。
${context_section}
【今回の指示】
${continuation_text}

【確認してほしいこと】
- 前回指摘した問題が解消されているか
- 未解消の指摘（変更なし・対応不十分なもの）
- 新たに見つかった問題
- 今回確認した範囲
EOF
}

# --- Claude 実行 ---
EXIT_CODE=0
EXTRACTED_SESSION_ID="unresolved"
CLAUDE_CMD_BASE=""
USER_PROMPT=""

case "$MODE" in
  new-uncommitted|new-base)
    build_review_prompt > "$TMP_PROMPT"
    USER_PROMPT=$(cat "$TMP_PROMPT")

    CLAUDE_CMD_BASE="claude -p \\
  --output-format json \\
  --model Opus \\
  --dangerously-skip-permissions \\
  --tools \"Read,Glob,Grep,Bash\""

    cat "$TMP_PROMPT" | claude -p \
      --output-format json \
      --model Opus \
      --dangerously-skip-permissions \
      --tools "Read,Glob,Grep,Bash" \
      > "$TMP_OUTPUT" 2>"$TMP_STDERR" || EXIT_CODE=$?

    if [[ $EXIT_CODE -eq 0 ]]; then
      EXTRACTED_SESSION_ID=$(extract_session_id "$TMP_OUTPUT")
    fi
    ;;

  resume)
    if [[ -z "$SESSION_ID" ]]; then
      echo "ERROR: --session-id が指定されていません" >&2
      exit 1
    fi

    build_resume_prompt > "$TMP_PROMPT"
    USER_PROMPT=$(cat "$TMP_PROMPT")

    CLAUDE_CMD_BASE="claude -p \\
  --output-format json \\
  --model Opus \\
  --resume \"${SESSION_ID}\" \\
  --dangerously-skip-permissions \\
  --tools \"Read,Glob,Grep,Bash\""

    cat "$TMP_PROMPT" | claude -p \
      --output-format json \
      --model Opus \
      --resume "$SESSION_ID" \
      --dangerously-skip-permissions \
      --tools "Read,Glob,Grep,Bash" \
      > "$TMP_OUTPUT" 2>"$TMP_STDERR" || EXIT_CODE=$?

    if [[ $EXIT_CODE -eq 0 ]]; then
      NEW_ID=$(extract_session_id "$TMP_OUTPUT")
      EXTRACTED_SESSION_ID="${NEW_ID:-unresolved}"
      [[ "$EXTRACTED_SESSION_ID" == "unresolved" ]] && EXTRACTED_SESSION_ID="$SESSION_ID"
    fi
    ;;

  *)
    echo "ERROR: 不明なモード: $MODE" >&2
    exit 1
    ;;
esac

# --- レビュー記録の保存 ---
save_review_log() {
  local session_id="$1"
  local review_output="$2"
  local is_error="${3:-false}"

  local timestamp
  timestamp=$(date '+%Y%m%d_%H%M%S')
  local project_name
  project_name=$(basename "$(pwd)")
  local save_file="${SAVE_DIR}/opus-review_${project_name}_${timestamp}.md"

  {
    # --- 親セッションの Claude への指示 ---
    if [[ "$MODE" == "resume" ]]; then
      cat <<'INSTRUCTION'
# Claude への指示
1. このファイルのフルパスを必ずユーザに提示してください
2. 「Opus レビュー結果」セクションの内容を必ず **原文のまま** **ユーザーに提示** してください
3. プロジェクトのコンテキストを踏まえた所感を述べてください
4. **今回のレビューで新たに出た指摘がある場合: 前回ユーザーから受けた修正指示のスコープは前回のレビュー指摘に対してのみ有効です。新規指摘については改めてユーザーに対応要否を確認してください。前回の「修正して」等の指示を新規指摘にまで拡大解釈しないでください。**
5. ユーザーに次のアクションを問いかけてください（修正指示・深掘り・session_id での継続 など）
6. **ユーザーから明示的な指示があるまでコードを修正しないでください**
INSTRUCTION
    else
      cat <<'INSTRUCTION'
# Claude への指示
1. このファイルのフルパスを必ずユーザに提示してください
2. 「Opus レビュー結果」セクションの内容を必ず **原文のまま** **ユーザーに提示** してください
3. プロジェクトのコンテキストを踏まえた所感を述べてください
4. ユーザーに次のアクションを問いかけてください（修正指示・深掘り・session_id での継続 など）
5. **ユーザーから明示的な指示があるまでコードを修正しないでください**
INSTRUCTION
    fi
    echo ""
    echo "---"
    echo ""

    # --- ログ本体 ---
    echo "# Opus Review Log"
    echo ""
    echo "- **日時**: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "- **ディレクトリ**: $(pwd)"
    echo "- **モード**: ${MODE}"
    echo "- **セッションID**: ${session_id}"
    [[ "$MODE" == "new-base" ]] && echo "- **ベースブランチ**: ${BASE_BRANCH}"
    [[ ${#TARGETS[@]} -gt 0 ]] && echo "- **対象ファイル**: ${TARGETS[*]}"
    [[ "$MODE" == "resume" && -n "$SESSION_ID" ]] && echo "- **継続元セッションID**: ${SESSION_ID}"
    [[ "$is_error" == "true" ]] && echo "- **ステータス**: エラー (exit code: ${EXIT_CODE})"
    echo ""

    # 実行コマンドとプロンプトを記録
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
    echo "## Opus レビュー結果"
    echo ""
    echo "$review_output"
  } > "$save_file"

  # 保存パスを stderr に出力（stdout は呼び出し元のパース対象なので混ぜない）
  echo "OPUS_REVIEW_LOG=${save_file}" >&2
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

  save_review_log "unresolved" "$ERROR_OUTPUT" "true"

  echo "OPUS_SESSION_ID=unresolved"
  echo "---OPUS_REVIEW_OUTPUT---"
  echo "$ERROR_OUTPUT"
  exit 1
fi

# --- 正常出力 ---
REVIEW_BODY=$(extract_result "$TMP_OUTPUT")
if [[ -z "$REVIEW_BODY" ]]; then
  REVIEW_BODY="（レビュー結果の取得に失敗しました - 出力が空です）"
fi

save_review_log "$EXTRACTED_SESSION_ID" "$REVIEW_BODY"

printf 'OPUS_SESSION_ID=%s\n' "$EXTRACTED_SESSION_ID"
printf -- '---OPUS_REVIEW_OUTPUT---\n'
printf '%s\n' "$REVIEW_BODY"
