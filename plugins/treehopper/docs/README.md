# treehopper

opencode CLI との連携機能を提供する Claude Code プラグイン。

opencode との 1問1答・コードレビュー・ファイル書き込みを含む作業・セッションペアリング・セッションエクスポートを agent として提供する。

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
| `opencode` | opencode CLI |

※ 使用可能な python/conda/pyenv が存在する場合、自動的にplugin専用の venv/conda env を作成する

## インストール

```bash
claude plugin install treehopper@claude-forest
```

## 環境変数

| 環境変数 | 対象 agent | 説明 |
|---------|-----------|------|
| `OPENCODE_ASK_DEFAULT_MODEL` | `opencode-ask` | 使用するモデル。`<provider/model>` または `<provider/model>,<effort>` 形式（区切りはカンマ）。未設定または空文字列の場合は既定モデルを使用する |
| `OPENCODE_REVIEW_DEFAULT_MODEL` | `opencode-review` | 同上 |
| `OPENCODE_TASK_DEFAULT_MODEL` | `opencode-task` | 同上 |
| `CLAUDEFOREST_DISABLE_DEVELOPMENT_GUIDELINES` | `opencode-task` | 空文字以外を設定すると開発ガイドラインの参照指示を付加しない |

※ 各 agent の呼び出し時に `model=` / `effort=` を指定した場合はそちらが優先される（ユーザーが明示的に指定した場合のみ使用される）

## agent 一覧

| agent 名 | 説明 |
|---------|------|
| `opencode-ask` | opencode CLI で opencode と会話する |
| `opencode-review` | opencode CLI で opencode にコードレビューを依頼する |
| `opencode-task` | opencode CLI で opencode にファイル書き込みを含む作業を依頼する。実行中に軌道修正の指示を差し込める |
| `opencode-pairing` | 現在の Claude セッションを opencode セッションに 1:1 でペアリングする |
| `opencode-export-session` | opencode のセッション会話全文を Markdown ファイルにエクスポートする |
