---
name: get-pr-info
description: GitHub PRの情報（概要・会話・レビュー・行コメント・コミット・差分）を取得してMarkdownにまとめる。ユーザーが「PRの情報を取得」「PR情報を確認」「get-pr-info」「PRを調べて」と言った場合に使用。
argument-hint: "<PR_NUMBER> | <ORG/REPO> <PR_NUMBER>"
allowed-tools: Bash
---

## 手順

### 1. 入力解釈

`$ARGUMENTS` から以下を読み取る。

- PR 番号（数字）が必須
- `ORG/REPO` 形式のリポジトリ名が含まれる場合はそれを使用。なければカレントディレクトリのリポジトリを使用

PR 番号が不足している場合はユーザーに確認する。

### 2. 実行

```bash
# リポジトリ省略時（カレントディレクトリから自動取得）
"${CLAUDE_PLUGIN_ROOT}/skills/get-pr-info/bin/run-get-pr-info.sh" <PR_NUMBER>

# リポジトリ指定時
"${CLAUDE_PLUGIN_ROOT}/skills/get-pr-info/bin/run-get-pr-info.sh" <ORG/REPO> <PR_NUMBER>
```

### 3. 返却

スクリプトの stdout（保存先パス）をそのまま返す。Markdown 本文は出力しない。

---

## 制約

- `gh` と `jq` が必要。未インストールの場合はインストールを試みる
- PR が存在しない場合はエラーを返して終了する
- ファイルの読み取りや編集は行わない（取得のみ）
