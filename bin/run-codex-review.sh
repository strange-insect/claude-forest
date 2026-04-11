#!/usr/bin/env bash
# run-codex-review.sh
# Codex を使ってコードレビューを実行し、session_id とレビュー結果を返す
#
# 使い方:
#   run-codex-review.sh --mode new-uncommitted [--targets "file1" --targets "file2"] [--aspects "観点"]
#   run-codex-review.sh --mode new-base --base main [--aspects "観点"]
#   run-codex-review.sh --mode resume --session-id UUID [--continuation "追加指示"]
#
# 出力形式 (stdout):
#   CODEX_SESSION_ID=<uuid or unresolved>
#   ---CODEX_REVIEW_OUTPUT---
#   <レビュー本文>
#
# ロール指示・レビュー出力ルール・モード別指示を含むプロンプトを組み立てて
# codex exec の位置引数として渡す。
set -euo pipefail

# --- 依存チェック ---
command -v codex >/dev/null 2>&1 || { echo "ERROR: 'codex' コマンドが見つかりません。OpenAI Codex CLI をインストールしてください。" >&2; exit 1; }
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
TMP_JSONL=$(mktemp /tmp/codex-review-jsonl-XXXXXX)
TMP_MSG=$(mktemp /tmp/codex-review-msg-XXXXXX)
TMP_STDERR=$(mktemp /tmp/codex-review-err-XXXXXX)

cleanup() {
  rm -f "$TMP_JSONL" "$TMP_MSG" "$TMP_STDERR"
}
trap cleanup EXIT

# --- session_id 抽出ヘルパー ---
# codex exec --json の出力形式: {"type":"thread.started","thread_id":"<UUID>"}
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

# --- 新規レビュー用プロンプト ---
build_review_prompt() {
  local parts=()

  parts+=("あなたはコードレビューを担当するシニアエンジニアです。
コードの修正は一切行わず、レビューコメントの出力のみを行ってください。
ファイルの読み取りは許可されていますが、書き込みは行わないでください。

【レビュー出力ルール】
- 問題の深刻度を示すこと（Critical / Warning / Info / Suggestion）
- ファイルパスと行番号を明記すること
- 修正案がある場合は具体的なコード例を含めること（実際の修正はしない）")

  if [[ -z "$ASPECTS" ]]; then
    parts+=("【レビュー観点（デフォルト）】
変更差分だけでなく、変更箇所の周辺コードも読み、以下を幅広く・深くレビューすること:

1. **正確性・ロジック**: バグ、エッジケース、境界値、競合状態
2. **セキュリティ**: インジェクション、認証・認可漏れ、機密情報の露出
3. **ドキュメント整合性**: README・コメント・JSDoc/docstring・CHANGELOG 等の更新漏れ、変更後の実装と一致しない記述
4. **周辺コードとの整合性**: 変更していない関数・クラス・設定・テストが変更後の実装と矛盾していないか
5. **類似機能との整合性**: コードベース内の類似した実装・命名規則・エラーハンドリング・ログ出力等のパターンと乖離していないか
6. **ワークフロー・連携影響**: 変更した機能が担う上流・下流の処理フロー、呼び出し元・呼び出し先、イベント・キュー・ジョブ等との接続部分に影響が出ていないか
7. **データライフサイクル**: 変更がデータ構造や内容に影響する場合、そのデータを扱うライフサイクル上の他の部分（生成・変換・永続化・読み取り・表示・削除・有効期限管理）と不整合を起こしていないか。直接の呼び出し関係がなくても同じデータを参照・更新する機能（例: バッチ処理でステータスが変わった場合の画面表示やレポート出力、非同期ジョブの結果を参照するAPIやUI、帳票・CSV出力など）まで広く確認すること
8. **テスト網羅性**: 追加・変更したロジックに対応するテストが存在するか、既存テストが陳腐化していないか
9. **保守性**: 命名、重複、抽象化の適切さ、将来の変更への影響
10. **パフォーマンス**: 不要な計算・I/O・メモリ使用")
  fi

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

# --- 継続レビュー用プロンプト ---
build_resume_prompt() {
  local continuation_text="${CONTINUATION:-前回の指摘が解消されているか確認してください。}"

  if [[ -n "$REVIEW_CONTEXT" ]]; then
    printf '【背景・修正意図・注意点】\n%s\n\n' "$REVIEW_CONTEXT"
  fi

  printf '%s\n' "$continuation_text"
}

# --- Codex 実行 ---
EXIT_CODE=0
EXTRACTED_SESSION_ID="unresolved"

CODEX_CMD_BASE=""

case "$MODE" in
  new-uncommitted)
    PROMPT=$(build_review_prompt)
    CODEX_CMD_BASE="codex exec \\
  --full-auto \\
  --json"
    echo "$PROMPT" | codex exec --full-auto --json -o "$TMP_MSG" - \
      >"$TMP_JSONL" 2>"$TMP_STDERR" || EXIT_CODE=$?

    EXTRACTED_SESSION_ID=$(extract_session_id "$TMP_JSONL")
    ;;

  new-base)
    PROMPT=$(build_review_prompt)
    CODEX_CMD_BASE="codex exec \\
  --full-auto \\
  --json"
    echo "$PROMPT" | codex exec --full-auto --json -o "$TMP_MSG" - \
      >"$TMP_JSONL" 2>"$TMP_STDERR" || EXIT_CODE=$?

    EXTRACTED_SESSION_ID=$(extract_session_id "$TMP_JSONL")
    ;;

  resume)
    if [[ -z "$SESSION_ID" ]]; then
      echo "ERROR: --session-id が指定されていません" >&2
      exit 1
    fi
    PROMPT=$(build_resume_prompt)
    CODEX_CMD_BASE="codex exec resume \"${SESSION_ID}\" \\
  --full-auto \\
  --json"
    echo "$PROMPT" | codex exec resume "$SESSION_ID" --full-auto --json -o "$TMP_MSG" - \
      >"$TMP_JSONL" 2>"$TMP_STDERR" || EXIT_CODE=$?
    # resume 応答に thread.started がない場合は入力 SESSION_ID を保持する
    NEW_ID=$(extract_session_id "$TMP_JSONL")
    EXTRACTED_SESSION_ID="${NEW_ID:-unresolved}"
    [[ "$EXTRACTED_SESSION_ID" == "unresolved" ]] && EXTRACTED_SESSION_ID="$SESSION_ID"
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
  local save_file="${SAVE_DIR}/codex-review_${project_name}_${timestamp}.md"

  {
    # --- 親セッションの Claude への指示 ---
    if [[ "$MODE" == "resume" ]]; then
      cat <<'INSTRUCTION'
# Claude への指示
1. このファイルのフルパスを必ずユーザに提示してください
2. 「Codex レビュー結果」セクションの内容を必ず **原文のまま** **ユーザーに提示** してください
3. プロジェクトのコンテキストを踏まえた所感を述べてください
4. **今回のレビューで新たに出た指摘がある場合: 前回ユーザーから受けた修正指示のスコープは前回のレビュー指摘に対してのみ有効です。新規指摘については改めてユーザーに対応要否を確認してください。前回の「修正して」等の指示を新規指摘にまで拡大解釈しないでください。**
5. ユーザーに次のアクションを問いかけてください（修正指示・深掘り・session_id での継続 など）
6. **ユーザーから明示的な指示があるまでコードを修正しないでください**
INSTRUCTION
    else
      cat <<'INSTRUCTION'
# Claude への指示
1. このファイルのフルパスを必ずユーザに提示してください
2. 「Codex レビュー結果」セクションの内容を必ず **原文のまま** **ユーザーに提示** してください
3. プロジェクトのコンテキストを踏まえた所感を述べてください
4. ユーザーに次のアクションを問いかけてください（修正指示・深掘り・session_id での継続 など）
5. **ユーザーから明示的な指示があるまでコードを修正しないでください**
INSTRUCTION
    fi
    echo ""
    echo "---"
    echo ""

    # --- ログ本体 ---
    echo "# Codex Review Log"
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
    echo -e "$CODEX_CMD_BASE"
    echo "  \"\$(cat <<'REVIEW_PROMPT'"
    echo "$PROMPT"
    echo "REVIEW_PROMPT"
    echo ")\""
    echo '```'
    echo ""

    echo "---"
    echo ""
    echo "## Codex レビュー結果"
    echo ""
    echo "$review_output"
  } > "$save_file"

  # 保存パスを stderr に出力（stdout は呼び出し元のパース対象なので混ぜない）
  echo "CODEX_REVIEW_LOG=${save_file}" >&2
}

# --- エラーハンドリング ---
if [[ $EXIT_CODE -ne 0 ]]; then
  # エラー時の出力を組み立て
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

  save_review_log "unresolved" "$ERROR_OUTPUT" "true"

  echo "CODEX_SESSION_ID=unresolved"
  echo "---CODEX_REVIEW_OUTPUT---"
  echo "$ERROR_OUTPUT"
  exit 1
fi

# --- 正常出力 ---
REVIEW_OUTPUT=""
if [[ -s "$TMP_MSG" ]]; then
  REVIEW_OUTPUT=$(cat "$TMP_MSG")
else
  REVIEW_OUTPUT="（レビュー結果の取得に失敗しました - 出力ファイルが空です）"
fi

save_review_log "$EXTRACTED_SESSION_ID" "$REVIEW_OUTPUT"

printf 'CODEX_SESSION_ID=%s\n' "$EXTRACTED_SESSION_ID"
printf -- '---CODEX_REVIEW_OUTPUT---\n'
echo "$REVIEW_OUTPUT"
