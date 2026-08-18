#!/bin/bash

# Stop フック
# バックグラウンドタスクを持たずに停止したエージェントの最後の発話を判定し、
# 「これから〜します」の宣言、選択肢を伴わない続行確認、または作業量を理由とする
# 分割・中断・別途実施の提案で止まっている場合は、停止をブロックして処理を続行させる。
#
# stdin : Claude Code が渡す Stop フックの payload JSON
# stdout: {"decision":"block","reason":"..."} (続行させる場合のみ)

exec "${CLAUDE_PLUGIN_ROOT}/bin/python-wrapper.sh" "${CLAUDE_PLUGIN_ROOT}/bin/auto-continue.py"
