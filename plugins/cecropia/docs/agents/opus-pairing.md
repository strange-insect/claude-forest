# opus-pairing

現在の Claude セッションと Opus セッションを 1:1 でペアリングする。ペアリング後は、このセッションからの `opus-ask` / `opus-review` 呼び出しに、ペアリング済みの Opus セッション ID が必須になる。

## 基本情報

| 項目 | 値 |
|---|---|
| agent 名 | `opus-pairing` |
| 実装 | `agents/opus-pairing.md` |
| 使用モデル | `sonnet` |
| 実行コンテキスト | subagent（独立コンテキスト） |

## トリガーフレーズ

- 「opusとペアリング」
- 「opus-pairing」

## 呼び出し形式

引数なし。

## 動作概要

1. `opus-ask` パイプラインを使って Opus に挨拶を送り、新しい Opus セッションを開始する
2. 発行された Opus セッション ID と現在の `CLAUDE_SESSION_ID` の対応を `$CLAUDE_PLUGIN_DATA/opus-pairing.txt` に記録する
3. 以降、`PreToolUse` フックが `opus-ask` / `opus-review` 呼び出し時にセッション ID を検証する

## ペアリングファイル

| 項目 | 値 |
|---|---|
| パス | `$CLAUDE_PLUGIN_DATA/opus-pairing.txt` |
| 形式 | `CLAUDE: <session_id>, OPUS: <session_id>` （1行1エントリ） |

複数の Claude セッションが同一ファイルにエントリを持てる。同一 `CLAUDE_SESSION_ID` で再ペアリングした場合は既存エントリが上書きされる。

## 親セッションへの応答

ペアリング成功時：

```
ペアリングを実施しました。
以下の Session ID 以外での opus-ask, opus-review は禁止されます。
Opus Session ID: <OPUS_SESSION_ID>
```

ペアリング失敗時：

```
ペアリングに失敗しました。opus-pairing をもう一度実行してください。
```

## ペアリング後の制約

`PreToolUse` フック（`opus-pairing.sh`）が有効になり、`opus-ask` / `opus-review` の呼び出しプロンプトにペアリング済みの Opus セッション ID が含まれていない場合はブロックされる。

詳細は [hooks/overview.md](../hooks/overview.md) を参照。

## 依存

### コマンド

| ツール | 用途 |
|---|---|
| Python 3.10+ | `ask-pipeline.py` の実行 |
| `claude` | Claude CLI |
