# cecropia

よく使う機能をまとめた Claude Code の基本プラグイン。

外部 AI（Opus）との 1問1答・コードレビュー、GitHub PR の作成・取得、PlantUML 変換、セッションエクスポートなど、日常的に使うユーティリティを agent と skill として提供する。

## 動作環境

| 項目 | 要件 |
|------|------|
| OS | Linux / macOS / Windows（Git Bash MINGW64） |
| シェル | Bash 3.2 以上（macOS system bash / Git Bash でも動作） |
| Python | 3.10 以上（JSON 解析・パス処理・HTTP リクエスト等を Python stdlib で実行） |
| Git | `create-pr` / `get-pr-info` などリポジトリ操作系を使う場合に必要 |

## 依存コマンド

agent / skill ごとに使用する外部コマンドが異なる。利用するものに対応するコマンドを事前にインストールしておく。

| コマンド | 用途 |
|---------|------|
| Python 3.10+ | JSON 解析・パス処理・HTTP リクエスト等の cross-platform 実装 |
| `gh` | GitHub API・PR 操作 |
| `claude` | Claude Code CLI（`claude -p`） |
| `direnv` | `.envrc` の環境変数を Bash 実行に読み込む場合に必要（任意。未インストールでも他機能は動作する） |

※ 使用可能な python/conda/pyenv が存在する場合、自動的にplugin専用の venv/conda env を作成する

## インストール

```bash
claude plugin install cecropia@claude-forest
```

## 環境変数

| 環境変数 | 対象 agent | 説明 |
|---------|-----------|------|
| `CLAUDE_ASK_DEFAULT_MODEL` | `claude-ask` | 使用するモデル。`<model>` または `<model>/<effort>` 形式。未設定または空文字列の場合は既定モデルを使用する |
| `CLAUDE_REVIEW_DEFAULT_MODEL` | `claude-review` | 同上 |

## agent 一覧

| agent 名 | 説明 |
|---------|------|
| `claude-ask` | 別セッションのOpusモデルと会話する |
| `claude-review` | 別セッションの Claude Opus モデルでコードレビューを行う |
| `claude-pairing` | 現在の Claude セッションを Opus セッションに 1:1 でペアリングする |
| `get-pr-info` | GitHub PR の情報を取得する |
| `plant-uml` | PlantUML ソースコードと 画像(Kroki URL) の相互変換、ソースコードテキスト・Markdownのコードスニペットに対応 |
| `export-session` | Claude Code のセッション会話全文を Markdown ファイルにエクスポートする |

## スキル一覧

| スキル名 | 説明 |
|---------|------|
| `create-pr` | 現在のブランチから GitHub PR を作成する。テンプレート指定に対応 |
