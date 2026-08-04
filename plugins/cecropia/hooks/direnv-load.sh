#!/bin/bash

# SessionStart フック
# カレントディレクトリの .envrc を direnv で評価し、得られた環境変数を
# CLAUDE_ENV_FILE 経由で後続の Bash 実行に継承させる。
#
# CLAUDE_ENV_FILE はシェルとして source されるため、`direnv export bash` が出力する
# `export FOO=$'...';` 形式をそのまま追記できる。
#
# 前提と安全性:
#   - direnv が PATH に無ければ何もしない
#   - .envrc が未 allow の場合、direnv は stdout に内部変数（DIRENV_DIR 等）しか出さず
#     ユーザー定義の変数は出力しない。許可していない .envrc が読み込まれることはない
#   - どの経路でも exit 0 で抜ける（fail-fast せず、後続処理を止めない）
#
# 制約:
#   セッション開始時の 1 回だけ評価する。セッション中に .envrc を変更した場合や、
#   別の .envrc を持つディレクトリへ移動した場合は反映されない（セッション再開始が必要）。

# stdin の hook payload は使わないが、読み捨てないと呼び出し元が SIGPIPE で落ちうる
cat >/dev/null

[[ -n "${CLAUDE_ENV_FILE:-}" ]] || exit 0

DIRENV_BIN="$(command -v direnv 2>/dev/null)"
[[ -n "$DIRENV_BIN" ]] || exit 0

# stdout（export 文）のみを env ファイルへ追記する。stderr は表示しない。
# 未 allow の .envrc がある場合、direnv は非 0 で終了する（明示的に deny 済みの場合は 0）。
DIRENV_OUTPUT="$("$DIRENV_BIN" export bash 2>/dev/null)"
DIRENV_EXIT=$?

if [[ $DIRENV_EXIT -ne 0 ]]; then
  # .envrc の読み込みに失敗。hook が知り得るのは direnv が非 0 で終了したことだけで、
  # 原因は特定できない（未 allow のほか、strict_env 下の未定義変数参照や .envrc 内の
  # 非 0 終了でも発生する）。環境変数は読み込まないまま、対処方法をセッションに伝える。
  cat <<'JSON'
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "direnv: このディレクトリの .envrc を読み込めませんでした。未許可の場合は `direnv allow` を実行し、解消しない場合は `direnv export bash` のエラー内容を確認したうえで、セッションを開始し直す必要がある旨をユーザに通知してください。"
  }
}
JSON
  exit 0
fi

[[ -n "$DIRENV_OUTPUT" ]] || exit 0

printf '%s\n' "$DIRENV_OUTPUT" >> "$CLAUDE_ENV_FILE"

exit 0
