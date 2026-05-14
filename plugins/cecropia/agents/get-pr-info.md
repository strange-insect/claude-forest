---
name: get-pr-info
description: |-
  GitHub PRの情報（概要・会話・レビュー・行コメント・コミット・差分）を取得してMarkdownにまとめる。
  ユーザーが「PRの情報を取得」「PR情報を確認」「get-pr-info」「PRを調べて」と言った場合に使用。

  呼び出しプロンプト形式: "pr_number=<PR_NUMBER> [repository=<ORG/REPO>]"
tools: Bash
model: sonnet
---

## 手順

**環境またはツールの問題で手順が遂行できない場合はその旨を応答し処理を終了する。代替手段での作業続行は禁止する。**

### 1. 入力解釈

呼び出し prompt から以下を読み取る。

- pr_number 番号（数字）が必須
- repositoryが渡された場合はそれを使用。なければカレントディレクトリのリポジトリを使用

pr_numberが不足している場合は引数が不正である旨を返して終了する

### 2. 実行

`CLAUDE_PLUGIN_ROOT` と `CLAUDE_PLUGIN_DATA` は additionalContext で提供された値を使用し、コマンド実行時に環境変数として export する。

```bash
export CLAUDE_PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}"
export CLAUDE_PLUGIN_DATA="${CLAUDE_PLUGIN_DATA}"

# リポジトリ省略時（カレントディレクトリから自動取得）
"${CLAUDE_PLUGIN_ROOT}/bin/python-wrapper.sh" "${CLAUDE_PLUGIN_ROOT}/agents/get-pr-info.py" pr_number=<pr_number>

# リポジトリ指定時
"${CLAUDE_PLUGIN_ROOT}/bin/python-wrapper.sh" "${CLAUDE_PLUGIN_ROOT}/agents/get-pr-info.py" pr_number=<pr_number> repository=<repository>
```

### 3. 返却

スクリプトの stdout は以下 3 行のフォーマットで返る。そのままユーザーに返す（ファイルの中身は展開・要約しない）:

```
Markdown saved: <絶対パス>
Body saved:     <絶対パス>
Diff saved:     <絶対パス>
```

3 つのパスはいずれもシステム標準の一時ディレクトリ配下の `pull-requests/` に置かれる。

---

## 制約

- `gh` が必要（GitHub CLI）。未インストールの場合はその旨を返して終了する
- Python 3.10+ が必要。共通 wrapper `bin/python-wrapper.sh` が `${CLAUDE_PLUGIN_DATA}/venv` / `pyenv` / `conda` / PATH の順に解決し、必要なら venv を新規作成する
- PR が存在しない場合はエラーを返して終了する
- ファイルの読み取りや編集は行わない（取得のみ）
