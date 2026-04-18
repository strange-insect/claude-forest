#!/usr/bin/env bash
# ask-pipeline.sh
# ask 系の処理パイプラインを実行し、Markdown ログファイルパスを返す
#
# 使い方:
#   ask-pipeline.sh --skill <name> [--session-id UUID] [--output-dir PATH] --message "質問テキスト"
#   ask-pipeline.sh --skill <name> [--session-id UUID] [--output-dir PATH] <<'EOF'
#   質問テキスト（複数行可）
#   EOF
#
# 出力 (stdout):
#   <出力先にコピーされた Markdown ログファイルの絶対パス>
#
# 終了コード:
#   0: 成功
#   1: エラー
set -uo pipefail

SHARED_BIN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- 引数パース ---
SKILL=""
MESSAGE=""
SESSION_ID=""
OUTPUT_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skill)      SKILL="$2";      shift 2 ;;
    --message)    MESSAGE="$2";    shift 2 ;;
    --session-id) SESSION_ID="$2"; shift 2 ;;
    --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    *) echo "ERROR: 不明なオプション: $1" >&2; exit 1 ;;
  esac
done

[[ -z "$SKILL" ]] && { echo "ERROR: --skill が指定されていません" >&2; exit 1; }
[[ -z "$MESSAGE" ]] && MESSAGE=$(cat)
[[ -z "$MESSAGE" ]] && { echo "ERROR: --message または stdin でメッセージを指定してください" >&2; exit 1; }

# --- スキル名からスクリプトパスを解決 ---
# 規則: skills/<skill>/bin/run-<skill>.sh
RUN_SCRIPT="${SHARED_BIN}/../${SKILL}/bin/run-${SKILL}.sh"
[[ ! -x "$RUN_SCRIPT" ]] && { echo "ERROR: 実行できません: $RUN_SCRIPT" >&2; exit 1; }

# --- パイプライン実行 ---
# 各ステップが失敗してもエラー内容を含む JSON/ログが生成されるよう
# exit code を個別に捕捉して最後にまとめて返す

PIPELINE_EXIT=0
RUN_ARGS=(--message "$MESSAGE")
[[ -n "$SESSION_ID" ]] && RUN_ARGS+=(--session-id "$SESSION_ID")

JSON_PATH=$("$RUN_SCRIPT" "${RUN_ARGS[@]}") || PIPELINE_EXIT=$?
[[ -z "${JSON_PATH:-}" ]] && { echo "ERROR: run スクリプトがパスを返しませんでした" >&2; exit 1; }

ORIGINAL_JSON_PATH="$JSON_PATH"
if TRANSLATED_JSON_PATH=$("${SHARED_BIN}/translate-json.sh" "$JSON_PATH" answer); then
  JSON_PATH="$TRANSLATED_JSON_PATH"
else
  echo "WARN: 翻訳に失敗しました。原文のまま続行します" >&2
  JSON_PATH="$ORIGINAL_JSON_PATH"
fi

LOG_PATH=$("${SHARED_BIN}/save-ask-log.sh" "$JSON_PATH") || PIPELINE_EXIT=$?
[[ -z "${LOG_PATH:-}" ]] && { echo "ERROR: save-ask-log.sh がパスを返しませんでした" >&2; exit 1; }

# --- 中間 JSON ファイルは Markdown 生成後に削除 ---
if [[ -f "$LOG_PATH" ]]; then
  rm -f "$ORIGINAL_JSON_PATH"
  [[ "$JSON_PATH" != "$ORIGINAL_JSON_PATH" ]] && rm -f "$JSON_PATH"
fi

# --- 出力先ディレクトリの決定 ---
# 基準ディレクトリ: git リポジトリ内ならリポジトリルート、そうでなければカレントディレクトリ
BASE_DIR=$(git rev-parse --show-toplevel 2>/dev/null || pwd)

if [[ -z "$OUTPUT_DIR" ]]; then
  TARGET_DIR="${BASE_DIR}/.llm-ask"
elif [[ "$OUTPUT_DIR" = /* ]]; then
  TARGET_DIR="$OUTPUT_DIR"
else
  TARGET_DIR="${BASE_DIR}/${OUTPUT_DIR}"
fi

# --- 出力先ディレクトリの初期化 ---
# 新規作成時のみ .gitignore(*) を同梱。既存ディレクトリには触らない（ユーザーの Git 管理意図を尊重）
if [[ ! -d "$TARGET_DIR" ]]; then
  mkdir -p "$TARGET_DIR"
  printf '*\n' > "${TARGET_DIR}/.gitignore"
fi

# --- 最終 Markdown を出力先にコピー ---
TARGET_DIR=$(cd "$TARGET_DIR" && pwd)
COPIED_PATH="${TARGET_DIR}/$(basename "$LOG_PATH")"
cp "$LOG_PATH" "$COPIED_PATH"

printf '%s\n' "$COPIED_PATH"
exit "$PIPELINE_EXIT"
