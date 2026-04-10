---
name: my-skill
description: スキルの説明（250文字以内）。Claudeがいつこのスキルを使うべきかを記述する
# disable-model-invocation: true  # true にするとユーザーの /my-skill 呼び出しのみ有効（自動呼び出し禁止）
# user-invocable: false           # false にするとClaude内部からのみ呼び出し可能
# allowed-tools: Bash Read Write  # 許可なしで使用できるツール（スペース区切り）
# argument-hint: "[引数1] [引数2]" # オートコンプリート時に表示されるヒント
# model: sonnet                   # 使用するモデル（省略時は現在のモデルを使用）
# context: fork                   # fork でサブエージェントとして実行
# agent: Explore                  # context: fork 時に使用するエージェントタイプ
---

# スキル名

スキルの概要説明をここに書く。

## 引数

- `$ARGUMENTS` — ユーザーが渡した引数全体
- `$0`, `$1`, `$2` — 引数を空白で分割した各要素

## 手順

1. 最初のステップ
2. 次のステップ
3. ...

## 注意事項

- 注意点があれば記述する
