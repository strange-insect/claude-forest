# ants

よく使う機能をまとめた Claude Code の基本プラグイン。

## インストール

```bash
claude plugin install ants@claude-forest
```

## スキル一覧

`/ants:<name>` で呼び出せるスラッシュコマンド。

| スキル名 | 説明 |
|---------|------|
| `codex-ask` | OpenAI Codex CLI で 1問1答形式の質問。会話継続に対応 |
| `codex-review` | OpenAI Codex CLI でコードレビュー。新規・継続レビューに対応 |
| `create-pr` | 現在のブランチから GitHub PR を作成する |
| `create-skill` | 対話的にカスタムスキル（SKILL.md）を新規作成する |
| `export-session` | セッション会話全文を Markdown ファイルにエクスポートする |
| `get-pr-info` | GitHub PR の情報（概要・会話・レビュー・行コメント・コミット・差分）を取得して `/tmp/pull-requests/` に保存する |
| `opus-ask` | Opus モデルで 1問1答形式の質問。会話継続に対応 |
| `opus-review` | Opus モデルでコードレビュー。新規・継続レビューに対応 |
| `plant-uml` | PlantUML のエンコード/デコードおよび Markdown と Kroki URL の相互変換 |

## フック一覧

| フック名 | イベント | 説明 |
|---------|--------|------|
| `session-start` | `SessionStart` | セッション開始時に `CLAUDE_SESSION_ID` を環境変数として永続化する |

## 依存コマンド

| コマンド | 用途 | 対象スキル |
|---------|------|-----------|
| `jq` | JSON 解析 | `codex-ask`, `codex-review`, `opus-ask`, `opus-review`, `get-pr-info`, `session-start` |
| `gh` | GitHub API・PR 操作 | `get-pr-info`, `create-pr` |
| `curl` | PlantUML サーバーへのリクエスト | `plant-uml` |
| `python3` | エンコード/デコード・セッションエクスポート | `plant-uml`, `export-session` |
| `codex` | OpenAI Codex CLI | `codex-ask`, `codex-review` |
| `claude` | Claude Code CLI（claude -p） | `opus-ask`, `opus-review` |

## 既知の問題

| スキル | 内容 |
|--------|------|
| `opus-review` | 内部で `--dangerously-skip-permissions` と `Bash` を許可しているため、信頼できないリポジトリのレビューにはプロンプトインジェクションのリスクがある |
