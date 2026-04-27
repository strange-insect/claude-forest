---
name: get-pr-info
description: >-
  GitHub PRの情報（概要・会話・レビュー・行コメント・コミット・差分）を取得してMarkdownにまとめる。
  ユーザーが「PRの情報を取得」「PR情報を確認」「get-pr-info」「PRを調べて」と言った場合に使用。

  呼び出しプロンプト形式: "pr_number=<PR_NUMBER> [repository=<ORG/REPO>]"
tools: Bash
model: sonnet
---

## 手順

### 1. 入力解釈

呼び出し prompt から以下を読み取る。

- pr_number 番号（数字）が必須
- repositoryが渡された場合はそれを使用。なければカレントディレクトリのリポジトリを使用

pr_numberが不足している場合は引数が不正である旨を返して終了する

### 2. 実行

```bash
# リポジトリ省略時（カレントディレクトリから自動取得）
"${CLAUDE_PLUGIN_ROOT}/agents/get-pr-info.sh" pr_number=<pr_number>

# リポジトリ指定時
"${CLAUDE_PLUGIN_ROOT}/agents/get-pr-info.sh" pr_number=<pr_number> repository=<repository>
```

### 3. 返却

スクリプトの stdout（保存先パス）をそのまま返す。ファイルの内容は出力しない。

---

## 制約

- `gh` と `jq` が必要。未インストールの場合はインストールを試みる
- PR が存在しない場合はエラーを返して終了する
- ファイルの読み取りや編集は行わない（取得のみ）
