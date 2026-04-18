#!/usr/bin/env bash
# translate-json.sh
# JSON ファイルの指定フィールドを翻訳（英語→日本語）して .translated.json を生成する
#
# 使い方:
#   translate-json.sh <json-file-path> <field-name>
#
# 例:
#   translate-json.sh /tmp/codex-ask/codex-ask_proj_20260412_123456.json answer
#
# 動作:
#   1. JSON から指定フィールドを抽出し翻訳元ファイルに保存
#   2. 翻訳元・翻訳先ファイルパスを機械的に生成
#   3. Haiku に翻訳元・翻訳先パスを渡して翻訳を依頼
#      （既に日本語の場合はそのままコピーするよう指示）
#   4. 翻訳先ファイルの内容で JSON の指定フィールドを更新し .translated.json を生成
#
# 出力 (stdout):
#   <翻訳済み JSON ファイルのパス>  例: /tmp/codex-ask/codex-ask_proj_20260412_123456.translated.json
#
# 終了コード:
#   0: 成功
#   1: エラー
set -euo pipefail

# --- CLAUDECODE 環境変数の無効化（ネスト呼び出し対応）---
unset CLAUDECODE CLAUDE_CODE_ENTRYPOINT 2>/dev/null || true

# --- 依存チェック ---
command -v claude >/dev/null 2>&1 || { echo "ERROR: 'claude' コマンドが見つかりません。" >&2; exit 1; }
command -v jq    >/dev/null 2>&1 || { echo "ERROR: 'jq' コマンドが見つかりません。"    >&2; exit 1; }

# --- 引数チェック ---
if [[ $# -ne 2 ]]; then
  echo "ERROR: 使い方: translate-json.sh <json-file-path> <field-name>" >&2
  exit 1
fi

JSON_FILE="$1"
FIELD="$2"

if [[ ! -f "$JSON_FILE" ]]; then
  echo "ERROR: JSON ファイルが見つかりません: $JSON_FILE" >&2
  exit 1
fi

# --- ファイルパスを機械的に生成 ---
JSON_DIR=$(dirname  "$JSON_FILE")
JSON_BASE=$(basename "$JSON_FILE" .json)

SRC_FILE="${JSON_DIR}/${JSON_BASE}-${FIELD}-src.txt"
DST_FILE="${JSON_DIR}/${JSON_BASE}-${FIELD}-translated.txt"
TRANSLATED_JSON="${JSON_DIR}/${JSON_BASE}.translated.json"

# --- 翻訳用中間テキストは終了時に削除 ---
cleanup() { rm -f "$SRC_FILE" "$DST_FILE"; }
trap cleanup EXIT

# --- 指定フィールドを抽出 → 翻訳元ファイル ---
jq -r --arg f "$FIELD" '.[$f]' "$JSON_FILE" > "$SRC_FILE"

# --- Haiku に翻訳を依頼 ---
PROMPT="次の手順を実行してください。

翻訳元ファイル: ${SRC_FILE}
翻訳先ファイル: ${DST_FILE}

1. 翻訳元ファイルを読む
2. 内容が英語なら日本語に翻訳する。既に日本語ならそのままコピーする
3. 結果を翻訳先ファイルに書き込む"

printf '%s\n' "$PROMPT" | claude -p \
  --model haiku \
  --output-format text \
  --dangerously-skip-permissions \
  --tools "Read,Write" \
  > /dev/null 2>&1

# --- 翻訳先ファイルの存在確認 ---
if [[ ! -f "$DST_FILE" ]]; then
  echo "ERROR: 翻訳先ファイルが生成されませんでした: $DST_FILE" >&2
  exit 1
fi

# --- 翻訳済み JSON を .translated.json として保存 ---
TRANSLATED=$(cat "$DST_FILE")
jq --arg f "$FIELD" --arg t "$TRANSLATED" '.[$f] = $t' "$JSON_FILE" > "$TRANSLATED_JSON"

printf '%s\n' "$TRANSLATED_JSON"
