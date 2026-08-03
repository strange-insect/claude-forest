# opencode-pairing

現在の Claude セッションと opencode セッションを 1:1 でペアリングする。ペアリング後は、このセッションからの `opencode-ask` / `opencode-review` / `opencode-task` 呼び出しに、ペアリング済みの opencode セッション ID が必須になる。

## 基本情報

| 項目 | 値 |
|---|---|
| agent 名 | `opencode-pairing` |
| 実装 | `agents/opencode-pairing.md` |
| 使用モデル | `sonnet` |
| 実行コンテキスト | subagent（独立コンテキスト） |

## トリガーフレーズ

- 「opencodeとペアリング」
- 「opencode-pairing」

## 呼び出し形式

引数なし。

## 動作概要

1. `opencode-ask` パイプラインを使って opencode に挨拶を送り、新しい opencode セッションを開始する
2. 発行された opencode セッション ID と現在の `CLAUDE_SESSION_ID` の対応を `$CLAUDE_PLUGIN_DATA/opencode-pairing.txt` に記録する
3. 以降、`PreToolUse` フックが `opencode-ask` / `opencode-review` / `opencode-task` 呼び出し時にセッション ID を検証する

## ペアリングファイル

| 項目 | 値 |
|---|---|
| パス | `$CLAUDE_PLUGIN_DATA/opencode-pairing.txt` |
| 形式 | `CLAUDE: <session_id>, OPENCODE: <session_id>` （1行1エントリ） |

複数の Claude セッションが同一ファイルにエントリを持てる。同一 `CLAUDE_SESSION_ID` で再ペアリングした場合は既存エントリが上書きされる。

## 親セッションへの応答

ペアリング成功時：

```
ペアリングを実施しました。
以下の Session ID 以外での opencode-ask, opencode-review, opencode-task は禁止されます。
opencode Session ID: <OPENCODE_SESSION_ID>
```

ペアリング失敗時：

```
ペアリングに失敗しました。opencode-pairing をもう一度実行してください。
```

## ペアリング後の制約

`PreToolUse` フック（`opencode-pairing.sh`）が有効になり、`opencode-ask` / `opencode-review` / `opencode-task` の呼び出しプロンプトにペアリング済みの opencode セッション ID が含まれていない場合はブロックされる。

詳細は [hooks/overview.md](../hooks/overview.md) を参照。

## 依存

### コマンド

| ツール | 用途 |
|---|---|
| Python 3.10+ | `ask-pipeline.py` の実行 |
| `opencode` | opencode CLI |
