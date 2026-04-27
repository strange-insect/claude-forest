# get-working-set.sh 仕様書

ワーキングセット（staged + unstaged + untracked）のファイル一覧を出力する。

## 配置

```
plugins/ants/bin/get-working-set.sh
```

## 呼び出し方

```bash
get-working-set.sh
```

引数なし。カレントディレクトリを git リポジトリとして扱う。

## 出力

stdout に、ワーキングセットに含まれるファイルパス（リポジトリルート相対）を 1 行ずつ出力する。重複は除去済み。

```
src/foo.ts
src/bar.ts
docs/new.md
```

## 処理フロー

1. `git diff --name-only`（unstaged）
2. `git diff --name-only --cached`（staged）
3. `git ls-files --others --exclude-standard`（untracked、`.gitignore` 対象は除外）
4. 上記 3 つを連結し、`sort -u` で重複除去、空行を除外

## 終了コード

`set -euo pipefail` で実行されるが、各 git コマンドは `2>/dev/null` でエラーを抑制し、最後に `|| true` で常に成功扱いになる。

| コード | 意味 |
|-------|------|
| 0 | 常に成功（git リポジトリでない場合は空出力） |

## 利用元

review agent (`codex-review` / `opus-review`) を呼ぶ側の LLM が、レビュー指示を組み立てるときの補助ユーティリティとして使える。ワーキングツリーに変更があるかの判定や、変更ファイル一覧をレビュー指示文に含める用途。agent 自身は呼ばない（agent は `<レビュー指示>` を解釈せずそのまま `ask-pipeline.sh` に渡す）。

## 依存コマンド

| コマンド | 用途 |
|---------|------|
| `git` | ワーキングセット情報取得 |
| `sort` / `grep` | 重複除去・空行除外 |
