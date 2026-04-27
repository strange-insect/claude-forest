# ants

よく使う機能をまとめた Claude Code の基本プラグイン。

外部 AI（Codex / Opus）との 1問1答・コードレビュー、GitHub PR の作成・取得、PlantUML 変換、セッションエクスポートなど、日常的に使うユーティリティを agent と skill として提供する。

設計思想は [DESIGN.md](./DESIGN.md) を参照。

## 動作環境

| 項目 | 要件 |
|------|------|
| OS | Linux / macOS |
| シェル | Bash 4.x 以上 |
| Git | `create-pr` / `get-pr-info` などリポジトリ操作系を使う場合に必要 |

## 依存プラグイン

なし。ants は他のプラグインに依存しない基本セットとして単独で動作する。

## 依存コマンド

agent / skill ごとに使用する外部コマンドが異なる。利用するものに対応するコマンドを事前にインストールしておく。

| コマンド | 用途 | 対象 agent / skill / フック |
|---------|------|-----------|
| `jq` | JSON 解析 | `codex-ask`, `codex-review`, `opus-ask`, `opus-review`, `get-pr-info`, `session-start` |
| `gh` | GitHub API・PR 操作 | `create-pr`, `get-pr-info` |
| `curl` | PlantUML / Kroki サーバーへのリクエスト | `plant-uml` |
| `python3` | エンコード/デコード・セッションエクスポート | `plant-uml`, `export-session` |
| `codex` | OpenAI Codex CLI | `codex-ask`, `codex-review` |
| `claude` | Claude Code CLI（`claude -p`） | `opus-ask`, `opus-review` |

## インストール

```bash
claude plugin install ants@claude-forest
```

## フック一覧

| フック名 | イベント | 説明 |
|---------|--------|------|
| `session-start` | `SessionStart` | セッション開始時に `CLAUDE_SESSION_ID` を環境変数として永続化する。`export-session` などセッション ID を必要とする agent から参照される |

## agent 一覧

親セッションの LLM が Agent ツール経由で起動する subagent。独立コンテキストで実行され、結果はファイル経由で親に返される。

### 外部 AI 連携

別セッションの AI を呼び出して、本セッションのコンテキストを汚さずに質問・レビューを行うための agent。`session_id` を渡すことで会話を継続できる。

| agent 名 | 説明 |
|---------|------|
| `codex-ask` | OpenAI Codex CLI で 1問1答形式の質問を行う |
| `codex-review` | OpenAI Codex CLI でコードレビューを行う |
| `opus-ask` | Claude Opus モデルで 1問1答形式の質問を行う |
| `opus-review` | Claude Opus モデルでコードレビューを行う |

### GitHub PR

| agent 名 | 説明 |
|---------|------|
| `get-pr-info` | GitHub PR の情報（概要・会話・レビュー・行コメント・コミット・差分）を取得して `/tmp/pull-requests/` に保存する |

### その他ユーティリティ

| agent 名 | 説明 |
|---------|------|
| `plant-uml` | PlantUML のエンコード/デコードおよび Markdown と Kroki URL の相互変換 |
| `export-session` | Claude Code のセッション会話全文を Markdown ファイルにエクスポートする |

## スキル一覧

`/ants:<name>` で呼び出せるスラッシュコマンド。本セッション内のインライン処理として実行される。

| スキル名 | 説明 |
|---------|------|
| `create-pr` | 現在のブランチから GitHub PR を作成する。テンプレート指定に対応 |
| `create-skill` | 対話的にカスタムスキル（SKILL.md）を新規作成する |

## 既知の問題

| 対象 | 内容 |
|------|------|
| `opus-ask` / `opus-review` (agent) | 内部で `--dangerously-skip-permissions` と `Bash` を許可しているため、信頼できないリポジトリでの利用にはプロンプトインジェクションのリスクがある（`bash -c 'cat > file'` 等で `--tools` から除外した `Write`/`Edit` を回避した書き込みも可能） |
