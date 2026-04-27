# create-pr スキル仕様書

GitHub プルリクエストを作成する。テンプレートに従って PR 本文を生成し、`gh pr create` で作成する。
対象ブランチの表面的な変更内容だけでなく仕様決定経緯なども含め説明文を記載する必要があり
親コンテキストの文脈をそのまま利用する必要があるため `context: fork` は外している。

※ Claude CodeのSkillは `context: fork` を指定していても親セッションのコンテキストを引き継いでいない可能性が高い。
少なくともバージョン 2.1.114 時点では親セッションの会話履歴を要約をさせる実験が成功しなかった。

## 基本情報

| 項目 | 値 |
|-----|-----|
| スキル名 | `create-pr` |
| 呼び出し方式 | `/ants:create-pr [repository=<owner/repo>] [head=<branch>] [base=<branch>] [template=<path>] [draft=<true\|false>]` |
| 実行コンテキスト | インライン（fork なし） |
| 結果 | PR 作成後、URL を返す |

## ユーザーが呼ぶタイミング

- 現在のブランチから GitHub PR を作成したい
- テンプレートに沿った PR 本文を自動生成して PR を作りたい

## 入力引数

| 引数 | 説明 | 省略時の動作 |
|-----|------|------------|
| `repository=<owner/repo>` | 対象リポジトリ | git リモートから自動取得 |
| `head=<branch>` | PR のヘッドブランチ（マージ元） | カレントブランチを使用 |
| `base=<branch>` | PR のベースブランチ（マージ先） | git log で派生元を自動検出 |
| `template=<path>` | PR テンプレートファイルパス | リポジトリ標準 → デフォルトの順で探索 |
| `draft=<true\|false>` | ドラフト PR として作成するか | `true`（ドラフト） |

PR タイトルは変更内容をもとにスキルが自動生成する。

## 処理フロー

1. **環境確認**：`gh auth status`（未認証なら `gh auth login` を促して終了）
2. **リポジトリ・ブランチ決定**：
   - `repository` 未指定 → `gh repo view --json nameWithOwner -q .nameWithOwner`
   - `head` 未指定 → `git branch --show-current`
   - `base` 未指定 → `git merge-base` でリモートブランチから派生元を推定。失敗時はリポジトリのデフォルトブランチにフォールバック
3. **変更内容調査**：`gh api repos/<owner>/<repo>/compare/<base>...<head>` でコミット一覧と変更ファイルを取得
4. **テンプレート読み込み**：
   - `template=<path>` 指定あり → そのファイル
   - 未指定 → `.github/PULL_REQUEST_TEMPLATE.md` 等を探索
   - いずれもなし → デフォルトテンプレート（概要・変更内容・今回保留にしたもの・影響範囲・動作確認の手順・デプロイ時に必要な作業・補足）
5. **PR 本文生成**：変更情報からテンプレートのセクションを埋める
6. **PR タイトル生成**：コミットメッセージ 1 行目をベースに 70 文字以内に収める
7. **PR 作成**：`gh pr create --repo --head --base --title --body [--draft]`
8. **結果報告**：`gh pr view --json url -q .url` で URL を取得して返す

## 出力

```
PR を作成しました。
URL: <PR_URL>
```

## エラー時の処理

| エラー | 動作 |
|-------|--------|
| `gh` が未認証 | `gh auth login` を促して終了 |
| `repository` 取得不可 | ユーザーに指定を促して終了 |
| `head` 取得不可 | ユーザーに指定を促して終了 |
| `head` と `base` が同じ | エラーで終了 |
| テンプレート指定パスが存在しない | エラーで終了 |

## 制約

- `gh` コマンドが未インストールの場合はインストールを試みる
- PR 本文に機密情報（トークン・パスワード等）が含まれないよう注意する
- 変更内容から判断できない情報は推測で埋めず、空欄または「要確認」とする

## 依存コマンド

| コマンド | 用途 |
|---------|------|
| `gh` | GitHub API・PR 作成 |
| `git` | ブランチ・差分情報取得 |

## 関連ドキュメント

- [get-pr-info](get-pr-info.md) — 既存 PR の情報取得
