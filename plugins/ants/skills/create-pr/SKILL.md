---
name: create-pr
description: >-
  GitHubプルリクエストを作成する。テンプレートに従いPR本文を生成し gh pr create で作成する。

  argument: "[repository=<owner/repo>] [head=<branch>] [base=<branch>] [template=<ファイルパス>] [draft=<true|false>]"
allowed-tools: Bash, Read, Glob
---

# タスク: GitHubプルリクエストの作成

指定されたリポジトリ・ブランチの変更内容を調べ、テンプレートに沿ったPR本文を生成して `gh pr create` で作成する。

---

## 1. 引数の解釈

`$ARGUMENTS` から以下を読み取る（すべて省略可）:

| 引数 | 説明 | 省略時の動作 |
|---|---|---|
| `repository=<owner/repo>` | 対象リポジトリ（`組織/リポジトリ` 形式） | カレントディレクトリの git リモートから自動取得 |
| `head=<branch>` | PRのヘッドブランチ（マージ元） | カレントブランチを使用 |
| `base=<branch>` | PRのベースブランチ（マージ先） | git log でブランチの派生元を自動検出 |
| `template=<path>` | PRテンプレートファイルパス | リポジトリの標準テンプレート → デフォルトテンプレートの順で探す |
| `draft=<true\|false>` | ドラフトPRとして作成するか | **省略時は `true`（ドラフト）として作成** |

PRタイトルは変更内容をもとにスキルが自動生成する。

---

## 2. 環境の確認

```bash
gh auth status
```

- `gh` が未認証の場合は `gh auth login` を促して終了

---

## 3. リポジトリ・ブランチの決定

### リポジトリ（`repository`）

- `repository=<owner/repo>` が指定されている場合はそれを使用
- 指定がない場合:
  ```bash
  # カレントディレクトリの git リモートから取得
  gh repo view --json nameWithOwner -q .nameWithOwner
  ```
  取得できない場合はユーザーに `repository=` の指定を促して終了

### ヘッドブランチ（`head`）

- `head=<branch>` が指定されている場合はそれを使用
- 指定がない場合:
  ```bash
  git branch --show-current
  ```
  カレントブランチが取得できない場合はユーザーに `head=` の指定を促して終了

### ベースブランチ（`base`）

- `base=<branch>` が指定されている場合はそれを使用
- 指定がない場合、`git log` でヘッドブランチの派生元ブランチを探す:
  ```bash
  # リモートの既知ブランチ一覧を取得
  git branch -r --format='%(refname:short)' | sed 's|origin/||'

  # ヘッドブランチが分岐した最も近い共通祖先を持つブランチを特定
  # 候補ブランチ（main, master, develop, release/* 等）に対して
  # git merge-base <candidate> <head> を実行し、
  # HEAD から最も近い（コミット差分が少ない）ブランチをベースとする
  git log --oneline <candidate>..<head>
  ```
  複数候補がある場合は差分コミット数が最も少ないブランチを採用する。
  自動検出できない場合はリポジトリのデフォルトブランチにフォールバック:
  ```bash
  gh repo view <owner/repo> --json defaultBranchRef -q .defaultBranchRef.name
  ```

ヘッドブランチとベースブランチが同じ場合はエラーで終了する。

---

## 4. 変更内容の調査

```bash
# ベースブランチからのコミット一覧
gh api repos/<owner/repo>/compare/<base>...<head> \
  --jq '.commits[] | "\(.sha[0:7]) \(.commit.message | split("\n")[0])"'

# 変更されたファイルの概要
gh api repos/<owner/repo>/compare/<base>...<head> \
  --jq '.files[] | "\(.status)\t\(.filename)"'
```

ローカルに該当リポジトリが clone されている場合は git コマンドも併用してよい:

```bash
git log <base>..<head> --oneline --no-merges
git diff --stat <base>..<head>
```

この情報をもとに PR 本文を生成する。

---

## 5. テンプレートの読み込み

### 5a. `template=<path>` が指定された場合

指定パスのファイルを読み込んでテンプレートとして使用する。
ファイルが存在しない場合はエラーで終了する。

### 5b. リポジトリのPRテンプレートを探す

```bash
# GitHubの標準テンプレートパスを確認
ls .github/PULL_REQUEST_TEMPLATE.md 2>/dev/null \
  || ls .github/pull_request_template.md 2>/dev/null \
  || ls docs/PULL_REQUEST_TEMPLATE.md 2>/dev/null \
  || echo "not found"
```

テンプレートが見つかった場合はそれを使用する。

### 5c. デフォルトテンプレートを使用

5a・5b のいずれも該当しない場合は以下のデフォルトテンプレートを使用:

```
<!-- GitHub Copilot コードレビューへの表示: このプルリクエストをレビューしてコメントする際には日本語でお願いします。 -->
## 概要

## 変更内容

## 今回保留にしたもの

## 影響範囲

## 動作確認の手順

## デプロイ時に必要な作業

## 補足 or 備考 or メモ
```

---

## 6. PR本文の生成

手順4で収集した変更情報をもとに、テンプレートの各セクションを埋める。

| セクション | 参照する情報 |
|---|---|
| **概要** | コミットメッセージ・変更の目的をまとめて1〜3文で記述 |
| **変更内容** | 変更ファイル・コミット一覧から具体的な変更を箇条書き |
| **今回保留にしたもの** | 明らかな場合は記述、不明な場合は「特になし」または空欄 |
| **影響範囲** | 変更ファイルの種別・機能領域を記述 |
| **動作確認の手順** | 変更内容から推測できる確認手順を記述 |
| **デプロイ時に必要な作業** | マイグレーション・設定変更等が読み取れれば記述、なければ「特になし」 |
| **補足 or 備考 or メモ** | 空欄または特記事項 |

テンプレートが独自形式（5a・5b）の場合はそのセクション構造に従って埋める。

---

## 7. PRタイトルの生成

変更内容をもとに以下の方針でスキルが自動生成する:

- コミットメッセージの1行目（複数コミットの場合は共通テーマを抽出）
- 変更ファイルの種別・機能領域も考慮する
- 70文字以内に収める

---

## 8. PRの作成

```bash
gh pr create \
  --repo <owner/repo> \
  --head <head_branch> \
  --base <base_branch> \
  --title "<タイトル>" \
  --body "$(cat <<'EOF'
<生成した本文>
EOF
)" \
  [--draft]  # draft=true または省略時（デフォルト true）の場合に付与
```

---

## 9. 作成結果の報告

```bash
# 作成されたPRのURLを取得
gh pr view --json url -q .url
```

以下の形式で報告する:

```
PR を作成しました。
URL: <PR_URL>
```

---

## 制約

- `gh` コマンドが未インストールの場合はインストールを試みる
- PR本文に機密情報（トークン・パスワード等）が含まれないよう注意する
- 変更内容から判断できない情報は推測で埋めず空欄または「要確認」とする
