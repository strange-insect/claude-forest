# opus-ask agent 仕様書

Claude Code CLI（`claude -p`）+ Opus モデルを使って 1問1答形式の質問を行う。`session_id` を指定することで会話を継続できる。

## 基本情報

| 項目 | 値 |
|-----|-----|
| agent 名 | `opus-ask` |
| 呼び出しプロンプト形式 | `[session_id=<UUID>] [output_dir=<path>] message_to_send=<メッセージ>` |
| 実行コンテキスト | subagent として独立コンテキストで実行 |
| 使用モデル | `sonnet`（agent 本体）／ Opus（バックエンド） |
| 結果 | Markdown ログファイルのパスを親セッションに返す |

## ユーザーが呼ぶタイミング

- Opus の意見・調査を依頼したい
- 本セッションのコンテキストを汚さずに別 AI へ質問したい
- 過去の Opus セッションに追加質問したい（`session_id` 指定）

## 入力引数

呼び出し prompt から以下を読み取る。

| 引数 | 説明 | デフォルト |
|-----|------|----------|
| `session_id=<UUID>` | 既存セッションを継続する。`セッション <UUID>` 表記も可 | 新規セッション |
| `output_dir=<path>` | Markdown ログのコピー先 | `<repo>/.llm-ask` |
| `message_to_send=<メッセージ>` | Opus への質問本文（複数行可、原文のまま渡す） | 必須 |

## 処理フロー

1. 呼び出し prompt を解釈し、`session_id` / `output_dir` / メッセージ本文を抽出
2. `${CLAUDE_PLUGIN_ROOT}/bin/ask-pipeline.sh --agent opus-ask ...` を Bash ツールでフォアグラウンド実行する。応答に時間がかかる可能性があるため Bash の timeout は最大値に設定する。サブエージェントからの Bash バックグラウンド実行は不具合があるため必ずフォアグラウンドで実行する
3. stdout の最終行から Markdown ログのパスを取得
4. 親セッションに `ログファイル: <LOG_PATH>` を返す（ログファイルを開いて内容は読まない）

## 出力

```
ログファイル: <LOG_PATH>
```

## 許可ツール（バックエンド側）

`opus-ask.sh` は `claude -p` 起動時に以下のツールのみを許可する：

```
Read, Glob, Grep, Bash, WebSearch, WebFetch
```

書き込み系ツール（`Write`、`Edit`）は意図的に除外する。

## エラー時の処理

| エラー | 動作 |
|-------|--------|
| `claude` コマンド未インストール | `opus-ask.sh` がエラーを stderr に出して exit 1 |
| `claude -p` 実行失敗 | エラー詳細を含む JSON ログが生成され、`status: error` で Markdown ログに記録される |
| `session_id` の指定誤り | `claude -p --resume` のエラーをそのまま JSON / Markdown に記録 |

## 制約

- `session_id` を推測で補わない
- コードの修正は行わない（読み取り・Web 検索のみ）
- agent はログファイルを開いて内容を読まない（パスを返すだけ）

## セキュリティ上の注意

`opus-ask.sh` は `claude -p --dangerously-skip-permissions` を使用する。信頼できないリポジトリで実行する場合は、プロンプトインジェクションのリスクを考慮すること（[internals/security-and-permissions.md](../internals/security-and-permissions.md) 参照）。

## 依存コマンド

| コマンド | 用途 |
|---------|------|
| `claude` | Claude Code CLI（`claude -p`） |
| `jq` | JSON 操作・session_id 抽出 |
| `git` | 出力ディレクトリのリポジトリルート検出（任意） |

## 関連ドキュメント

- [shellscripts/ask-pipeline.md](../shellscripts/ask-pipeline.md) — パイプライン本体
- [internals/ask-pipeline-flow.md](../internals/ask-pipeline-flow.md) — 全体フロー
- [internals/log-format.md](../internals/log-format.md) — JSON / Markdown ログ仕様
- [internals/security-and-permissions.md](../internals/security-and-permissions.md) — `--dangerously-skip-permissions` の取り扱い
