# get-pr-info agent 仕様書

GitHub PR の情報（概要・会話・レビュー・行コメント・コミット・差分）を取得して Markdown にまとめ、`/tmp/pull-requests/` 配下に保存する。

## 基本情報

| 項目 | 値 |
|-----|-----|
| agent 名 | `get-pr-info` |
| 呼び出しプロンプト形式 | `pr_number=<PR_NUMBER> [repository=<ORG/REPO>]` |
| 実行コンテキスト | subagent として独立コンテキストで実行 |
| 使用モデル | `haiku` |
| 結果 | 保存先 Markdown ファイルのパスを親セッションに返す |

## ユーザーが呼ぶタイミング

- GitHub PR の全情報を一度に取得して読みたい
- レビューや行コメントを含む PR 履歴を確認したい
- 別リポジトリの PR を調査したい

## 入力引数

| 引数 | 説明 | デフォルト |
|-----|------|----------|
| `pr_number=<PR_NUMBER>` | PR 番号（必須） | — |
| `repository=<ORG/REPO>` | 対象リポジトリ | カレントディレクトリのリポジトリ |

`pr_number` が不足している場合はユーザーに確認する。

## 処理フロー

1. 呼び出し prompt から `pr_number` と `repository` を抽出
2. `${CLAUDE_PLUGIN_ROOT}/agents/get-pr-info.sh pr_number=<...> [repository=<...>]` を実行
3. スクリプトの stdout（保存先パス）をそのまま親セッションに返す

Markdown 本文は親セッションには展開せず、必要があれば呼び出し側が `Read` ツールでファイルを開く。

## 出力

スクリプトが返す保存先パス（`/tmp/pull-requests/` 配下）。

## 取得する情報

- PR 概要（タイトル・状態・作成者・base/head）
- 会話（コメント）
- レビュー（approval / change request / comment）
- 行コメント（diff 上のレビューコメント）
- コミット一覧
- ファイル差分

## エラー時の処理

| エラー | 動作 |
|-------|--------|
| `gh` / `jq` 未インストール | コマンド実行時にエラーとなる。利用前に事前インストールが必要 |
| PR が存在しない | エラーを返して終了 |
| 認証エラー | `gh` のエラーをそのまま返す |

## 制約

- ファイルの読み取り・編集は行わない（取得のみ）
- 取得した PR 本文に機密情報が含まれる可能性があるため、保存先（`/tmp/pull-requests/`）の取り扱いに注意する

## 依存コマンド

| コマンド | 用途 |
|---------|------|
| `gh` | GitHub API |
| `jq` | JSON 操作 |

## 関連ドキュメント

- [create-pr](../skills/create-pr.md) — PR の新規作成
