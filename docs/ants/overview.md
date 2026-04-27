# ants ドキュメント

ants は Claude Code の日常作業で繰り返し使うユーティリティを agent と skill として集約した基本プラグインです。
このドキュメントセットは、ants の仕様、設計、運用を包括的に記載しています。

## ドキュメント全体概要

### 目的

- 各 agent / skill / フック / 共通スクリプトの「何をするか」「どの順序で進むか」を明確にする
- 実装詳細ではなく外部契約（引数・出力・依存・前提）を記載する
- ドキュメント参照によって ants の保守性・拡張性を向上する

### 対象範囲

このドキュメントセットが記載する内容：

- **agent 仕様**：7 つの subagent（外部 AI 連携、PR 情報取得、その他ユーティリティ）の引数・出力・動作
- **skill 仕様**：2 つのスキル（`create-pr` / `create-skill`）の引数・出力・動作
- **Hook 仕様**：SessionStart フックの目的と動作
- **ShellScript 仕様**：複数 agent から共有される `bin/` 配下スクリプトの引数・処理フロー
- **共通処理仕様**：ask パイプライン、ログフォーマット、セッション継続、セキュリティ・権限

対象外：

- Python 関数名・クラス設計の詳細
- コード実装ガイド
- テスト仕様書

## 主要概念（読む前に理解すべき用語）

### Agent（subagent）

親セッションの LLM が Agent ツール経由で呼び出す独立コンテキストの subagent。7 種類：

- `codex-ask` / `codex-review` — OpenAI Codex CLI を使った 1問1答 / コードレビュー
- `opus-ask` / `opus-review` — Claude Opus を使った 1問1答 / コードレビュー
- `get-pr-info` — GitHub PR の情報取得
- `plant-uml` — PlantUML / Kroki URL の相互変換
- `export-session` — Claude Code セッションの Markdown エクスポート

### Skill（スキル）

ユーザーが `/ants:<name>` で呼び出すスラッシュコマンド。2 種類：

- `create-pr` — 現在のブランチから GitHub PR を作成
- `create-skill` — カスタムスキルの新規作成

### Hook（フック）

Claude Code のセッションイベントで自動実行されるシェルコマンド。

- **SessionStart フック**：`CLAUDE_SESSION_ID` を環境変数として永続化する

### ShellScript（シェルスクリプト）

ants の主要な制御はシェルスクリプトで実装する。ただし `export-session` は `agents/export-session.py` を使用し、
`plant-uml` の補助スクリプトでも `python3` を使用する。

スクリプトは 2 つに分類される：

- **plugin root の `bin/` 配下の共有スクリプト**（4 個）：複数 agent から呼び出される共通処理
- **各 agent / skill 専用スクリプト**：その agent / skill 固有の実装（`agents/<name>.sh`、`agents/<name>/...`）

このドキュメントは `bin/` 配下のみを対象とする。各専用スクリプトは対応する `agents/<name>.md` / `skills/<name>.md` を参照する。

### Internals（共通処理仕様）

複数 agent にまたがる共通概念：

- **ask パイプライン**：`*-ask` / `*-review` 系の共通処理フロー（subagent 起動 → run → translate → save log → copy）
- **ログフォーマット**：中間 JSON のスキーマと、最終 Markdown のレイアウト
- **セッション継続**：`session_id` で別セッションの会話を継続するメカニズム
- **セキュリティ・権限**：`tools`、`--dangerously-skip-permissions` の使用範囲

### subagent

親セッションとは独立したコンテキストで実行する agent。`*-ask` / `*-review` などの長時間処理・大量出力を
伴う処理は subagent として実行され、結果はファイル経由で親に返される。親セッションのメッセージ履歴は引き継がれない。

## ドキュメント読み順

### 1. はじめに（最初に読む）

このファイル（overview.md）を読んで全体像を把握。

### 2. 仕様の詳細（カテゴリ別）

各カテゴリは独立して読める：

**主要カテゴリ**：

- [agents/overview.md](agents/overview.md) — agent 一覧、各 agent の仕様書へのリンク
- [skills/overview.md](skills/overview.md) — skill 一覧、各 skill の仕様書へのリンク
- [hooks/overview.md](hooks/overview.md) — Hook 仕様、SessionStart フック
- [shellscripts/overview.md](shellscripts/overview.md) — `bin/` 配下の共有スクリプト

**内部処理（internals）**：

- [internals/overview.md](internals/overview.md) — 共通処理概念の一覧
- [internals/ask-pipeline-flow.md](internals/ask-pipeline-flow.md) — ask パイプライン全体フロー
- [internals/log-format.md](internals/log-format.md) — JSON / Markdown ログのスキーマ
- [internals/session-continuation.md](internals/session-continuation.md) — `session_id` の取り回し
- [internals/security-and-permissions.md](internals/security-and-permissions.md) — 権限と tools の指針

### 3. 特定 agent / skill の詳細

agent / skill 単位の動作・引数・出力は、対応する仕様書を参照。

## ドキュメント間の責務分離

責務混在を避けるため、以下のように責務を分離：

| 内容 | 記載場所 | 理由 |
|------|--------|------|
| agent の引数・出力・動作 | agents/*.md | agent 仕様は agent ファイルのみ |
| skill の引数・出力・動作 | skills/*.md | skill 仕様は skill ファイルのみ |
| Hook の目的・タイミング | hooks/*.md | Hook 仕様は Hook ファイルのみ |
| `bin/` スクリプトの引数・処理フロー | shellscripts/*.md | Script 仕様は Script ファイルのみ |
| 概念仕様（パイプライン・ログ・セッション継続） | internals/*.md | 概念はここ一箇所 |
| ログ JSON スキーマ・Markdown レイアウト | internals/log-format.md | フォーマット仕様はここ一箇所 |
| 権限ポリシー（tools 等） | internals/security-and-permissions.md | 権限仕様はここ一箇所 |

## 用語の統一

このドキュメントセット全体で、以下の用語を統一：

- **subagent**：親セッションとは独立したコンテキストで動く agent。Agent ツール経由で起動される
- **ask パイプライン**：`*-ask` / `*-review` の `ask-pipeline.sh` を経由する共通処理
- **JSON ログ**：`<agent>.sh` が生成する中間 JSON ファイル（`/tmp/<model>-ask/` 配下）
- **Markdown ログ**：`save-ask-log.sh` が JSON から生成する最終 Markdown ファイル
- **出力ディレクトリ**：Markdown ログのコピー先（デフォルト `<repo>/.llm-ask`）
- **セッション ID**：Codex / Claude CLI が発行する会話継続用の UUID
