# ants スキル仕様書

ants の手動スキル（`/ants:<name>` で呼び出せるコマンド）の仕様をまとめる。

スキルはユーザーの明示的な指示で起動される。多くは `context: fork` の子セッションで実行され、結果はファイル経由で親セッションに返される。

## スキル一覧

### 外部 AI 連携

別セッションの AI を呼び出して、本セッションのコンテキストを汚さずに質問・レビューを行う。`session_id` を渡すことで会話を継続できる。

| スキル名 | 説明 | 用途 |
|---------|------|-----|
| `codex-ask` | OpenAI Codex CLI で 1問1答 | Codex に質問・調査 |
| `codex-review` | OpenAI Codex CLI でコードレビュー | Codex によるレビュー |
| `opus-ask` | Claude Opus で 1問1答 | Opus に質問・調査 |
| `opus-review` | Claude Opus でコードレビュー | Opus によるレビュー |

### GitHub PR

| スキル名 | 説明 | 用途 |
|---------|------|-----|
| `create-pr` | 現在のブランチから GitHub PR を作成 | PR 作成 |
| `get-pr-info` | GitHub PR の情報を取得して `/tmp/pull-requests/` に保存 | PR 情報取得 |

### その他ユーティリティ

| スキル名 | 説明 | 用途 |
|---------|------|-----|
| `plant-uml` | PlantUML / Kroki URL の相互変換 | 図表生成・解読 |
| `export-session` | Claude Code セッションを Markdown にエクスポート | セッション記録 |
| `create-skill` | カスタムスキルの新規作成 | スキル雛形生成 |

## 共通特徴

- **呼び出し方式**：`/ants:<スキル名> [引数]`
- **実行コンテキスト**：多くは `context: fork`（子セッション実行）。`create-pr` / `create-skill` はインライン実行
- **結果の返却**：
  - fork 実行のスキルは結果を Markdown ログファイルに保存し、本セッションにはパスのみ返す
  - インライン実行のスキルは結果を本セッションに直接返す
- **副作用**：
  - 読み取り専用：`get-pr-info`、`plant-uml`（decode/md-to-code）、`export-session`、`*-ask`、`*-review`
  - 書き込みあり：`create-pr`（PR 作成）、`create-skill`（SKILL.md 生成）、`plant-uml`（md-to-url で書き込み確認あり）

## 共有処理

`*-ask` / `*-review` の 4 スキルは、`_shared-bin/ask-pipeline.sh` を共通の入口として使う。詳細は [shellscripts/overview.md](../shellscripts/overview.md) と [internals/ask-pipeline-flow.md](../internals/ask-pipeline-flow.md) を参照。

`*-review` は `_shared-bin/get-working-set.sh` でレビュー対象のワーキングセットを取得する。

## 詳細仕様

各スキルの詳細仕様は以下を参照：

**外部 AI 連携**：

- [codex-ask](codex-ask.md)
- [codex-review](codex-review.md)
- [opus-ask](opus-ask.md)
- [opus-review](opus-review.md)

**GitHub PR**：

- [create-pr](create-pr.md)
- [get-pr-info](get-pr-info.md)

**その他**：

- [plant-uml](plant-uml.md)
- [export-session](export-session.md)
- [create-skill](create-skill.md)
