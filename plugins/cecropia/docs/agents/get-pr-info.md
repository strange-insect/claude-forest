# get-pr-info

GitHub PR の情報（概要・会話・レビュー・行コメント・コミット・差分）を取得し、システム標準の一時ディレクトリ配下の `pull-requests/` に Markdown としてまとめる。

## 基本情報

| 項目 | 値 |
|---|---|
| agent 名 | `get-pr-info` |
| 実装 | `agents/get-pr-info.py` |
| 使用モデル | `sonnet` |
| 実行コンテキスト | subagent（独立コンテキスト） |

## トリガーフレーズ

親セッションの LLM は次のフレーズを検知したときにこの agent を起動する。

- 「PRの情報を取得」
- 「PR情報を確認」
- 「get-pr-info」
- 「PRを調べて」

## 呼び出し形式

```
pr_number=<PR_NUMBER> [repository=<ORG/REPO>]
```

### 引数

| 引数 | 必須 | 説明 |
|---|---|---|
| `pr_number=<PR_NUMBER>` | 必須 | PR 番号（数字） |
| `repository=<ORG/REPO>` | 省略可 | 対象リポジトリ。省略時はカレントディレクトリのリポジトリを自動取得 |

`pr_number` が数字以外の場合、または省略された場合は引数不正として即終了する。

## 処理フロー

```
1. 引数解釈（pr_number / repository）
        ↓
2. python-wrapper.sh 経由で get-pr-info.py を起動
        ↓
3. gh CLI で PR 情報を取得
   ├─ gh pr view  → PR 概要 (JSON)
   ├─ gh pr diff  → diff ファイル
   ├─ gh api …/issues/{n}/comments  → 会話
   ├─ gh api …/pulls/{n}/reviews    → レビュー
   ├─ gh api …/pulls/{n}/comments   → 行コメント
   ├─ gh api …/pulls/{n}/commits    → コミット一覧
   └─ gh api …/pulls/{n}/files      → 変更ファイル一覧
        ↓
4. Markdown を組み立てて一時ディレクトリに保存
        ↓
5. stdout に保存パス 3 行を出力して終了
```

## 親セッションへの応答

スクリプトは stdout に以下の 3 行を返す。agent はこれをそのまま親セッションに返す（ファイルの中身を展開・要約しない）。

```
Markdown saved: <絶対パス>
Body saved:     <絶対パス>
Diff saved:     <絶対パス>
```

### 出力ファイル

保存先はシステム標準の一時ディレクトリ（`tempfile.gettempdir()`）配下の `pull-requests/`。Linux / macOS では `/tmp/pull-requests/`、Windows では `%TEMP%\pull-requests\` に展開される。

| ファイル | パターン | 内容 |
|---|---|---|
| Markdown | `<repo_slug>_pr_<PR_NUMBER>.md` | PR 全情報をまとめた Markdown |
| 本文 | `<repo_slug>_pr_<PR_NUMBER>_body.md` | PR 本文（description）のみ |
| Diff | `<repo_slug>_pr_<PR_NUMBER>.diff` | `gh pr diff` の生出力 |

`<repo_slug>` はリポジトリ名の `/` を `_` に置換した文字列（例：`myorg/myrepo` → `myorg_myrepo`）。

### Markdown に含まれるセクション

| セクション | 内容 |
|---|---|
| ヘッダー表 | リポジトリ・状態・作成者・ブランチ・最新コミットハッシュ |
| PR概要 | PR 本文ファイルへのリンク |
| Conversation | PR への汎用コメント一覧（linear[bot] は除外） |
| レビュー | approval / change request / comment 一覧 |
| 行コメント | diff 上のレビューコメント（スレッド構造を維持） |
| コミット一覧 | SHA・メッセージ・著者 |
| Diff | 変更ファイル一覧・diff ファイルのパスとサイズ |

※ linear botがコメントとして埋め込むIssue本文は大量のコンテキストを消費しノイズとなるため除外している

## エラー処理

| 状況 | 動作 |
|---|---|
| `pr_number` が未指定または非数値 | 引数不正メッセージを出力して終了 |
| `gh` 未インストール | `'gh' コマンドが見つかりません` を出力して終了 |
| Python 3.10+ が見つからない | `python-wrapper.sh` が固定メッセージで終了 |
| PR が存在しない | `gh pr view` のエラーをそのまま出力して終了 |
| `gh pr diff` 失敗 | 部分書き込みした diff ファイルを削除して終了 |

## 依存

| ツール | 用途 |
|---|---|
| `gh` | GitHub API クライアント（`gh pr view` / `gh pr diff` / `gh api`） |
| Python 3.10+ | JSON 解析・Markdown 組み立て（stdlib のみ）。`bin/python-wrapper.sh` が `${CLAUDE_PLUGIN_DATA}/venv` → `pyenv` → `conda` → `PATH` の順で Python を解決する |
