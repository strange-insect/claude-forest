# claude-plugins

個人的によく使う機能をまとめた Claude Code プラグイン集。

## 導入方法

### マーケットプレイスとして追加

```bash
claude plugin marketplace add strange-insect/claude-plugins
```

### プラグインをインストール

```bash
claude plugin install usual-plugin
```

### ローカルで試す（セッション限定）

```bash
claude --plugin-dir /path/to/claude-plugins
```

### プラグインを更新する

GitHub 上で更新があった場合、以下の2段階で取り込む。

```bash
# 1. マーケットプレイスのカタログを最新化
claude plugin marketplace update strange-plugins

# 2. プラグインを更新（更新後は Claude Code の再起動が必要）
claude plugin update usual-plugin
```

`/plugin` → Marketplaces タブで **auto-update** を有効にすると、起動時に自動更新される。

## 構成

```
claude-plugins/
├── .claude-plugin/
│   ├── plugin.json        # プラグインマニフェスト
│   └── marketplace.json   # マーケットプレイスカタログ
├── agents/                # サブエージェント定義
│   ├── codex-review.md
│   ├── export-session.md
│   ├── get-pr-info.md
│   └── opus-review.md
├── skills/                # スキル（/usual-plugin:<name> で呼び出せる）
│   ├── create-pr/
│   │   └── SKILL.md
│   ├── create-skill/
│   │   └── SKILL.md
│   └── puml/
│       ├── SKILL.md
│       └── bin/
├── bin/                   # 実行スクリプト（エージェントから参照）
│   ├── get-pr-info.sh
│   ├── get-working-set.sh
│   ├── run-codex-review.sh
│   └── run-opus-review.sh
├── scripts/               # ユーティリティスクリプト
│   └── export_session.py
└── hooks/                 # フック設定・スクリプト
    ├── hooks.json
    └── session-start.sh
```

## エージェント一覧

Claude が自動的に委譲するサブエージェント。`usual-plugin:<name>` としても参照できる。

| エージェント名 | 説明 |
|--------------|------|
| `codex-review` | OpenAI Codex CLI をバックエンドとして使ってコードレビューを実施する。新規・継続レビューに対応 |
| `export-session` | Claude Code のセッション会話全文を Markdown ファイルにエクスポートする |
| `get-pr-info` | GitHub PR の情報（概要・会話・レビュー・行コメント・コミット・差分）を取得して Markdown にまとめる |
| `opus-review` | Claude CLI（claude -p）を使い Opus モデルでコードレビューを実施する。新規・継続レビューに対応 |

## スキル一覧

`/usual-plugin:<name>` で呼び出せるスラッシュコマンド。

| スキル名 | 説明 |
|---------|------|
| `create-pr` | 現在のブランチからGitHubプルリクエストを作成する。デフォルトテンプレートまたは指定テンプレートに従いPR本文を自動生成する |
| `create-skill` | 対話的に Claude Code のカスタムスキル（SKILL.md）を新規作成する |
| `puml` | PlantUML のエンコード/デコードおよび Markdown 内のコードブロックと Kroki URL の相互変換を行う |

## フック一覧

| フック名 | イベント | 説明 |
|---------|--------|------|
| `session-start` | `SessionStart` | セッション開始時に `CLAUDE_SESSION_ID` を環境変数として永続化する |

## 依存コマンド・ライブラリ

プラグインを使用するには、以下のコマンドが必要です。スキルごとに必要なものが異なります。

### 必要コマンド一覧

| コマンド | 用途 | 対象機能 |
|---------|------|--------------------------------|
| `jq` | JSON 解析 | `codex-review`, `opus-review`, `get-pr-info`, `session-start` |
| `gh` | GitHub API・PR操作 | `get-pr-info`, `create-pr` |
| `curl` | PlantUML サーバーへのリクエスト | `puml` |
| `python3` | エンコード/デコード処理・セッションエクスポート | `puml`, `export-session` |
| `codex` | OpenAI Codex CLI | `codex-review` |

### インストール方法

**Ubuntu / Debian**

```bash
sudo apt install jq curl python3
```

**macOS**

```bash
brew install jq curl python3
```

**OpenAI Codex CLI**

Node.js が必要です。未インストールの場合は [nodejs.org](https://nodejs.org/) からインストールしてください。

```bash
npm install -g @openai/codex
```

## 既知の問題・TODO

| 機能 | 内容 |
|-------------|------|
| `opus-review` | 内部で `--dangerously-skip-permissions` と無制限の `Bash` を使用しているため、信頼できないリポジトリのレビューにはプロンプトインジェクションのリスクがある。ツールを読み取り専用（`Read,Glob,Grep`）に制限することで対処可能だが、現状は現行の動作を維持している |
