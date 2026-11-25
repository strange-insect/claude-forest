#!/bin/bash

# Stop フック
# バックグラウンドタスクを持たずに停止したエージェントの最後の発話を判定し、
# 「これから〜します」の宣言、選択肢を伴わない続行確認、または作業量を理由とする
# 分割・中断・別途実施の提案で止まっている場合は、停止をブロックして処理を続行させる。
#
# stdin : Claude Code が渡す Stop フックの payload JSON
# stdout: {"decision":"block","reason":"..."} (続行させる場合のみ)
#
# 環境変数 CLAUDEFOREST_DISABLE_AUTO_CONTINUE に空文字以外を設定した場合は判定せず終了する。

if [[ -n "${CLAUDEFOREST_DISABLE_AUTO_CONTINUE:-}" ]]; then
  # stdin の hook payload を読み捨てない場合、呼び出し元が SIGPIPE により異常終了する可能性がある
  cat >/dev/null
  exit 0
fi

exec "${CLAUDE_PLUGIN_ROOT}/bin/python-wrapper.sh" "${CLAUDE_PLUGIN_ROOT}/bin/auto-continue.py"
