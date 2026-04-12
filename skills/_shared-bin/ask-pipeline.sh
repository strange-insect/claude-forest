#!/usr/bin/env bash
# ask-pipeline.sh
# ask 系の処理パイプラインを実行し、Markdown ログファイルパスを返す
#
# 使い方:
#   ask-pipeline.sh --skill <name> [--session-id UUID] --message "質問テキスト"
#   ask-pipeline.sh --skill <name> [--session-id UUID] <<'EOF'
#   質問テキスト（複数行可）
#   EOF
#
# 出力 (stdout):
#   <Markdown ログファイルの絶対パス>
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

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skill)      SKILL="$2";      shift 2 ;;
    --message)    MESSAGE="$2";    shift 2 ;;
    --session-id) SESSION_ID="$2"; shift 2 ;;
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

printf '%s\n' "$LOG_PATH"
exit "$PIPELINE_EXIT"
