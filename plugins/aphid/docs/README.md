# aphid

OpenAI Codex CLI との連携機能を提供する Claude Code プラグイン。

Codex との 1問1答・コードレビュー・ファイル書き込みを含む作業・セッションペアリング・セッションエクスポートを agent として提供する。

## 動作環境

| 項目 | 要件 |
|------|------|
| OS | Linux / macOS / Windows（Git Bash MINGW64） |
| シェル | Bash 3.2 以上（macOS system bash / Git Bash でも動作） |
| Python | 3.10 以上（JSON 解析・パス処理・HTTP リクエスト等を Python stdlib で実行） |

## 依存コマンド

| コマンド | 用途 |
|---------|------|
| Python 3.10+ | JSON 解析・パス処理・HTTP リクエスト等の cross-platform 実装 |
| `codex` | OpenAI Codex CLI |

※ 使用可能な python/conda/pyenv が存在する場合、自動的にplugin専用の venv/conda env を作成する

## インストール

```bash
claude plugin install aphid@claude-forest
```

## 環境変数

| 環境変数 | 対象 agent | 説明 |
|---------|-----------|------|
| `CODEX_ASK_DEFAULT_MODEL` | `codex-ask` | 使用するモデル。`<model>` または `<model>,<effort>` 形式（区切りはカンマ）。未設定または空文字列の場合は既定モデルを使用する |
| `CODEX_REVIEW_DEFAULT_MODEL` | `codex-review` | 同上 |
| `CODEX_TASK_DEFAULT_MODEL` | `codex-task` | 同上 |
| `CLAUDEFOREST_DISABLE_DEVELOPMENT_GUIDELINES` | `codex-task` | 空文字以外を設定すると開発ガイドラインの参照指示を付加しない |

※ 各 agent の呼び出し時に `model=` / `effort=` を指定した場合はそちらが優先される（ユーザーが明示的に指定した場合のみ使用される）

## agent 一覧

| agent 名 | 説明 |
|---------|------|
| `codex-ask` | OpenAI Codex CLI で Codex と会話する |
| `codex-review` | OpenAI Codex CLI で Codex でコードレビューを行う |
| `codex-task` | OpenAI Codex CLI で Codex にファイル書き込みを含む作業を依頼する。実行中に軌道修正の指示を差し込める |
| `codex-pairing` | 現在の Claude セッションを Codex セッションに 1:1 でペアリングする |
| `codex-export-session` | codex のセッション会話全文を Markdown ファイルにエクスポートする |
