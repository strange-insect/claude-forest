---
name: opus-review
description: Claude Code CLI (claude -p) をバックエンドとして使い、Opusモデルでコードレビューを実施する。新規レビューと session_id を使った継続レビューに対応。コードの修正は行わない。ユーザーが「opusでレビュー」「opusレビュー」「opus-review」と言った場合に使用。
argument-hint: "[session_id=<UUID>] [base=<branch>] [targets=<file>] [aspects=<観点>] [context=<背景>]"
allowed-tools: Bash
---

コードレビュー専門スキル。事前確認なしに即実行する。コードの修正は一切行わない。

## 手順

### 1. 入力解釈

`$ARGUMENTS` から以下を読み取る:

- `session_id=<UUID>` / `セッション <UUID>` → `--session-id <UUID>` を付加
- `base=<branch>` / `PR差分` / `ブランチ差分` → ベースブランチとの差分をレビューする指示をメッセージに含める
- ファイル・ディレクトリ名 → レビュー対象の指示をメッセージに含める
- `〜の観点で` / `〜についてレビュー` → その観点に絞る指示をメッセージに含める
- 修正意図・背景・設計書への言及 → 背景の指示をメッセージに含める
- 継続レビューへの追加指示 → メッセージに含める
- 判断に迷った場合は「含めない」より「含める」側に倒すこと

### 2. レビュー対象の確定（新規レビューのみ）

`session_id` も以下のいずれも指定されていない場合:
- `base=<branch>`
- ファイル・ディレクトリ名

```bash
WORKING_SET=$(${CLAUDE_PLUGIN_ROOT}/skills/_shared-bin/get-working-set.sh)
```

- 出力あり → 未コミット変更（staged + unstaged + untracked）をレビューする指示をメッセージに含める
- 出力なし → 「レビュー対象がありません。レビュー範囲を指定してください」と返して終了

### 3. パイプライン実行

以下の形式でメッセージを組み立てて渡す:

- 未コミット変更: `ワーキングツリーの未コミット変更をレビューしてください。git diff、git diff --cached、git ls-files --others --exclude-standard で差分を確認してください。`
- ブランチ差分: `現在のブランチと <branch> との差分をレビューしてください。git diff $(git merge-base HEAD <branch> 2>/dev/null || echo <branch>) HEAD で差分を確認してください。`
- 対象ファイル: `以下のファイルを中心に確認してください:\n- <file>`
- 観点指定: `以下の観点のみに絞ってレビューしてください:\n<観点>`
- 背景: `【背景・修正意図・注意点】\n<内容>`
- 継続指示: そのままメッセージに含める

```bash
LOG_PATH=$(${CLAUDE_PLUGIN_ROOT}/skills/_shared-bin/ask-pipeline.sh \
  --skill opus-review \
  [--session-id "<SESSION_ID>"] <<'EOF'
<組み立てたメッセージ>
EOF
)
```

### 4. 結果の提示

`$LOG_PATH` を読み、以下の形式で返す:

```
レビューログ: <LOG_PATH>

## レビュー結果

<ログの「Opus の回答」セクションの内容>

---
次のアクション: 修正指示 / 深掘り / セッション継続（session_id: <SESSION_ID>）
```

- **ユーザーから明示的な指示があるまでコードを修正しないこと**
- 継続レビューで新規指摘が出た場合、前回の修正指示を新規指摘に拡大解釈しないこと

---

## 制約

- session_id を推測で補わない
- コードの修正は行わない（読み取り専用レビュー）
