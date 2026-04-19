# ants 共通処理仕様書（internals）

ants システムで複数スキルにまたがる共通概念・機構・パターンをまとめる。

このドキュメントは個別スキルや個別シェルスクリプトの仕様には言及しない。「どの共通概念が、どの外部契約やファイル状態を守っているか」に焦点を当てる。

## 共通概念一覧

| 概念 | 説明 | 関連ファイル |
|------|------|-----------|
| ask パイプライン | `*-ask` / `*-review` の共通処理フロー（fork → run → translate → save log → copy） | `ask-pipeline.sh` |
| ログフォーマット | 中間 JSON のスキーマと、最終 Markdown のレイアウト | `run-*.sh`, `save-ask-log.sh` |
| セッション継続 | `session_id` で別セッションの会話を継続するメカニズム | `run-*.sh` |
| セキュリティ・権限 | `allowed-tools`, `--dangerously-skip-permissions` の使用範囲 | 全スキル |

## 詳細仕様

各概念の詳細仕様は以下を参照：

- [ask パイプライン全体フロー](ask-pipeline-flow.md)
- [ログフォーマット](log-format.md)
- [セッション継続](session-continuation.md)
- [セキュリティと権限](security-and-permissions.md)

## 設計原則

### 1. fork セッションでコンテキストを分離

長時間処理・大量出力を伴うスキル（`*-ask` / `*-review` / `get-pr-info` / `export-session` / `plant-uml`）は `context: fork` の子セッションで実行し、親セッションのコンテキストを汚さない。

### 2. ファイル経由の結果返却

fork セッションの結果は標準出力ではなくファイル（Markdown ログ）に書き出し、親セッションにはパスのみを返す。これにより：

- 親セッションは必要な部分だけを `Read` で取り込める
- 失敗時もログが残るため、後追い分析できる
- 出力サイズが親のコンテキスト消費に直結しない

### 3. 中間表現としての JSON

`run-<skill>.sh` は機械可読な JSON を生成し、Markdown 化は別ステップ（`save-ask-log.sh`）に委譲する。これにより：

- 翻訳・整形などの後処理を JSON 段階で挟める
- Markdown フォーマットを変えても `run-*.sh` を変更しなくて済む

### 4. 失敗時の通知ポリシー

- スキル側のエラー（引数不正など）：親セッションにエラーメッセージを返す
- バックエンド側のエラー（`codex` / `claude` 実行失敗）：エラー詳細を含む JSON / Markdown ログを生成し、`status: error` で通常通り返す。親はログを読んで判断

## 外部依存

### 標準コマンド

`bash`、`mkdir`、`rm`、`cp`、`mv`、`cat`、`date`、`tr`、`printf`、`sort`、`grep` 等

### 必須コマンド（スキルによる）

| コマンド | 用途 |
|---------|------|
| `jq` | JSON 操作 |
| `gh` | GitHub API |
| `curl` | HTTP リクエスト |
| `python3` | エンコード/デコード等 |
| `codex` | OpenAI Codex CLI |
| `claude` | Claude Code CLI |

### オプション依存

| コマンド | 用途 |
|---------|------|
| `git` | リポジトリ情報取得（未インストール時は CWD にフォールバック） |
