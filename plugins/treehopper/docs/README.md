# treehopper

opencode CLI との連携機能を提供する Claude Code プラグイン。

opencode との 1問1答・コードレビュー・ファイル書き込みを含む作業・セッションペアリングを agent として提供する。

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

## agent 一覧

| agent 名 | 説明 |
|---------|------|
| `opencode-ask` | opencode CLI で opencode と会話する |
| `opencode-review` | opencode CLI で opencode にコードレビューを依頼する |
| `opencode-worker` | opencode CLI で opencode にファイル書き込みを含む作業を依頼する |
| `opencode-pairing` | 現在の Claude セッションを opencode セッションに 1:1 でペアリングする |
