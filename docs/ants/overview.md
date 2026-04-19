# ants ドキュメント

ants は Claude Code の日常作業で繰り返し使うユーティリティをスキルとして集約した基本プラグインです。
このドキュメントセットは、ants の仕様、設計、運用を包括的に記載しています。

## ドキュメント全体概要

### 目的

- 各スキル・フック・共通スクリプトの「何をするか」「どの順序で進むか」を明確にする
- 実装詳細ではなく外部契約（引数・出力・依存・前提）を記載する
- ドキュメント参照によってスキルの保守性・拡張性を向上する

### 対象範囲

このドキュメントセットが記載する内容：

- **SKILL 仕様**：9 つのスキル（外部 AI 連携、GitHub PR、その他ユーティリティ）の引数・出力・動作
- **Hook 仕様**：SessionStart フックの目的と動作
- **ShellScript 仕様**：複数スキルから共有される `_shared-bin/` 配下スクリプトの引数・処理フロー
- **共通処理仕様**：ask パイプライン、ログフォーマット、セッション継続、セキュリティ・権限

対象外：

- Python 関数名・クラス設計の詳細
- コード実装ガイド
- テスト仕様書

## 主要概念（読む前に理解すべき用語）

### SKILL（スキル）

ユーザーが `/ants:<name>` で呼び出すスラッシュコマンド。9 種類：

- `codex-ask` / `codex-review` — OpenAI Codex CLI を使った 1問1答 / コードレビュー
- `opus-ask` / `opus-review` — Claude Opus を使った 1問1答 / コードレビュー
- `create-pr` / `get-pr-info` — GitHub PR の作成 / 情報取得
- `plant-uml` — PlantUML / Kroki URL の相互変換
- `export-session` — Claude Code セッションの Markdown エクスポート
- `create-skill` — カスタムスキルの新規作成

### Hook（フック）

Claude Code のセッションイベントで自動実行されるシェルコマンド。

- **SessionStart フック**：`CLAUDE_SESSION_ID` を環境変数として永続化する

### ShellScript（シェルスクリプト）

ants の主要な制御はシェルスクリプトで実装する。ただし `export-session` は `scripts/export_session.py` を使用し、
`plant-uml` の補助スクリプトでも `python3` を使用する。

スクリプトは 2 つに分類される：

- **`_shared-bin/` 配下の共有スクリプト**（4 個）：複数スキルから呼び出される共通処理
- **各スキルの `bin/` 配下スクリプト**：そのスキル専用の実装

このドキュメントは `_shared-bin/` のみを対象とする。各スキル専用スクリプトは対応する `skills/<name>.md` を参照する。

### Internals（共通処理仕様）

複数スキルにまたがる共通概念：

- **ask パイプライン**：`*-ask` / `*-review` 系の共通処理フロー（fork → run → translate → save log → copy）
- **ログフォーマット**：中間 JSON のスキーマと、最終 Markdown のレイアウト
- **セッション継続**：`session_id` で別セッションの会話を継続するメカニズム
- **セキュリティ・権限**：`allowed-tools`、`--dangerously-skip-permissions` の使用範囲

### fork セッション

スキルを呼び出した親セッションとは独立した子セッションで実行する仕組み。`*-ask` / `*-review` などの長時間処理・大量出力を
伴うスキルは fork 実行され、結果はファイル経由で親に返される。

## ドキュメント読み順

### 1. はじめに（最初に読む）

このファイル（overview.md）を読んで全体像を把握。

### 2. 仕様の詳細（カテゴリ別）

各カテゴリは独立して読める：

**主要カテゴリ**：

- [skills/overview.md](skills/overview.md) — SKILL 一覧、各 SKILL の仕様書へのリンク
- [hooks/overview.md](hooks/overview.md) — Hook 仕様、SessionStart フック
- [shellscripts/overview.md](shellscripts/overview.md) — `_shared-bin/` 配下の共有スクリプト

**内部処理（internals）**：

- [internals/overview.md](internals/overview.md) — 共通処理概念の一覧
- [internals/ask-pipeline-flow.md](internals/ask-pipeline-flow.md) — ask パイプライン全体フロー
- [internals/log-format.md](internals/log-format.md) — JSON / Markdown ログのスキーマ
- [internals/session-continuation.md](internals/session-continuation.md) — `session_id` の取り回し
- [internals/security-and-permissions.md](internals/security-and-permissions.md) — 権限と allowed-tools の指針

### 3. 特定スキルの詳細

スキル単位の動作・引数・出力は、各 SKILL 仕様書を参照。

## ドキュメント間の責務分離

責務混在を避けるため、以下のように責務を分離：

| 内容 | 記載場所 | 理由 |
|------|--------|------|
| SKILL の引数・出力・動作 | skills/*.md | SKILL 仕様は SKILL ファイルのみ |
| Hook の目的・タイミング | hooks/*.md | Hook 仕様は Hook ファイルのみ |
| `_shared-bin/` スクリプトの引数・処理フロー | shellscripts/*.md | Script 仕様は Script ファイルのみ |
| 概念仕様（パイプライン・ログ・セッション継続） | internals/*.md | 概念はここ一箇所 |
| ログ JSON スキーマ・Markdown レイアウト | internals/log-format.md | フォーマット仕様はここ一箇所 |
| 権限ポリシー（allowed-tools 等） | internals/security-and-permissions.md | 権限仕様はここ一箇所 |

## 用語の統一

このドキュメントセット全体で、以下の用語を統一：

- **fork セッション**：スキルが Claude CLI を分岐実行する権限制限されたセッション
- **ask パイプライン**：`*-ask` / `*-review` の `ask-pipeline.sh` を経由する共通処理
- **JSON ログ**：`run-*.sh` が生成する中間 JSON ファイル（`/tmp/<model>-ask/` 配下）
- **Markdown ログ**：`save-ask-log.sh` が JSON から生成する最終 Markdown ファイル
- **出力ディレクトリ**：Markdown ログのコピー先（デフォルト `<repo>/.llm-ask`）
- **セッション ID**：Codex / Claude CLI が発行する会話継続用の UUID
