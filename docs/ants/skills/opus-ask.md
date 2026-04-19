# opus-ask スキル仕様書

Claude Code CLI（`claude -p`）+ Opus モデルを使って 1問1答形式の質問を行う。`session_id` を指定することで会話を継続できる。

## 基本情報

| 項目 | 値 |
|-----|-----|
| スキル名 | `opus-ask` |
| 呼び出し方式 | `/ants:opus-ask [session_id=<UUID>] [output_dir=<path>] <メッセージ>` |
| 実行コンテキスト | `context: fork`（子セッションで実行） |
| 使用モデル | `sonnet`（スキル本体）／ Opus（バックエンド） |
| 結果 | Markdown ログファイルのパスを親セッションに返す |

## ユーザーが呼ぶタイミング

- Opus の意見・調査を依頼したい
- 本セッションのコンテキストを汚さずに別 AI へ質問したい
- 過去の Opus セッションに追加質問したい（`session_id` 指定）

## 入力引数

`ARGUMENTS` から以下を読み取る。

| 引数 | 説明 | デフォルト |
|-----|------|----------|
| `session_id=<UUID>` | 既存セッションを継続する。`セッション <UUID>` 表記も可 | 新規セッション |
| `output_dir=<path>` | Markdown ログのコピー先 | `<repo>/.llm-ask` |
| `<メッセージ>` | Opus への質問本文（複数行可、上記キー以外の残り全部） | 必須 |

## 処理フロー

1. `ARGUMENTS` を解釈し、`session_id` / `output_dir` / メッセージ本文を抽出
2. `${CLAUDE_PLUGIN_ROOT}/skills/_shared-bin/ask-pipeline.sh --skill opus-ask ...` を Bash ツールでフォアグラウンド実行する。長時間化する可能性があるため、Bash の timeout は最大値に設定する（Skill 使用時のバックグラウンド実行には不具合らしき挙動が報告されているため、必ずフォアグラウンドで実行する）
3. stdout の最終行から Markdown ログのパスを取得
4. 親セッションに `ログファイル: <LOG_PATH>` を返す

## 出力

```
ログファイル: <LOG_PATH>
```

## 許可ツール（バックエンド側）

`run-opus-ask.sh` は `claude -p` 起動時に以下のツールのみを許可する：

```
Read, Glob, Grep, Bash, WebSearch, WebFetch
```

書き込み系ツール（`Write`、`Edit`）は意図的に除外する。

## エラー時の処理

| エラー | 動作 |
|-------|--------|
| `claude` コマンド未インストール | `run-opus-ask.sh` がエラーを stderr に出して exit 1 |
| `claude -p` 実行失敗 | エラー詳細を含む JSON ログが生成され、`status: error` で Markdown ログに記録される |
| `session_id` の指定誤り | `claude -p --resume` のエラーをそのまま JSON / Markdown に記録 |

## 制約

- `session_id` を推測で補わない
- コードの修正は行わない（読み取り・Web 検索のみ）

## セキュリティ上の注意

`run-opus-ask.sh` は `claude -p --dangerously-skip-permissions` を使用する。信頼できないリポジトリで実行する場合は、プロンプトインジェクションのリスクを考慮すること（[internals/security-and-permissions.md](../internals/security-and-permissions.md) 参照）。

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
