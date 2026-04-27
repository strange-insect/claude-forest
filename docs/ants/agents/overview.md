# ants agent 仕様書

ants の subagent（Agent ツール経由で呼ばれる独立コンテキストの agent）の仕様をまとめる。

各 agent は親セッションのコンテキストを引き継がずに独立した subagent として走り、結果はファイル経由で親セッションに返す。fork セッションのように親コンテキスト全体をコピーすることはない。

## agent 一覧

### 外部 AI 連携

別セッションの AI を呼び出して、本セッションのコンテキストを汚さずに質問・レビューを行う。`session_id` を渡すことで会話を継続できる。

| agent 名 | 説明 | 用途 |
|---------|------|-----|
| `codex-ask` | OpenAI Codex CLI で 1問1答 | Codex に質問・調査 |
| `codex-review` | OpenAI Codex CLI でコードレビュー | Codex によるレビュー |
| `opus-ask` | Claude Opus で 1問1答 | Opus に質問・調査 |
| `opus-review` | Claude Opus でコードレビュー | Opus によるレビュー |

### GitHub PR

| agent 名 | 説明 | 用途 |
|---------|------|-----|
| `get-pr-info` | GitHub PR の情報を取得して `/tmp/pull-requests/` に保存 | PR 情報取得 |

### その他ユーティリティ

| agent 名 | 説明 | 用途 |
|---------|------|-----|
| `plant-uml` | PlantUML / Kroki URL の相互変換 | 図表生成・解読 |
| `export-session` | Claude Code セッションを Markdown にエクスポート | セッション記録 |

## 共通特徴

- **呼び出し方式**：親セッションの LLM が Agent ツール経由で起動。スラッシュコマンド起動はサポートしない
- **実行コンテキスト**：subagent として独立コンテキストで実行。親セッションのメッセージ履歴は引き継がれない
- **結果の返却**：結果を Markdown ログファイルに保存し、親セッションにはパスのみ返す
- **副作用**：いずれも読み取り系（`get-pr-info`、`plant-uml` の decode/md-to-code、`export-session`、`*-ask`、`*-review`）。`plant-uml` の md-to-url のみ書き込み確認あり

## 共有処理

`*-ask` / `*-review` の 4 agent は、`bin/ask-pipeline.sh` を共通の入口として使う。詳細は [shellscripts/overview.md](../shellscripts/overview.md) と [internals/ask-pipeline-flow.md](../internals/ask-pipeline-flow.md) を参照。

`bin/get-working-set.sh` は呼び出し側 LLM がレビュー指示を組み立てるときの補助ユーティリティ（ワーキングツリー変更の一覧取得）として使える。agent 自身は呼ばない。

## 詳細仕様

各 agent の詳細仕様は以下を参照：

**外部 AI 連携**：

- [codex-ask](codex-ask.md)
- [codex-review](codex-review.md)
- [opus-ask](opus-ask.md)
- [opus-review](opus-review.md)

**GitHub PR**：

- [get-pr-info](get-pr-info.md)

**その他**：

- [plant-uml](plant-uml.md)
- [export-session](export-session.md)
