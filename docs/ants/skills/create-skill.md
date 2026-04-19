# create-skill スキル仕様書

対話的に Claude Code のカスタムスキル（SKILL.md）を新規作成する。スキル名・用途・引数・ツール・実行コンテキスト等をヒアリングし、SKILL.md と必要に応じて補助スクリプトを生成する。

## 基本情報

| 項目 | 値 |
|-----|-----|
| スキル名 | `create-skill` |
| 呼び出し方式 | `/ants:create-skill [スキル名] [用途の説明]` |
| 実行コンテキスト | インライン（fork なし） |
| `disable-model-invocation` | `true`（手動呼び出しのみ） |
| 結果 | 生成したファイル一覧と呼び出し方を表示 |

## ユーザーが呼ぶタイミング

- 新しいカスタムスキルを作りたい
- SKILL.md のフロントマッターやテンプレートを思い出せない

## 入力引数

| 引数 | 説明 | デフォルト |
|-----|------|----------|
| `スキル名` | 作成するスキル名 | ヒアリング |
| `用途の説明` | スキルの目的 | ヒアリング |

不足項目はユーザーに対話で確認する。

## 処理フロー

1. **要件のヒアリング**：必須項目（スキル名・用途・手順）と任意項目（引数・使用ツール・実行コンテキスト・サブエージェント型・自動呼び出し可否・補助スクリプトの有無）を確認
2. **既存スキルの確認**：`.claude/skills/<name>/` の存在を確認。既存なら上書き確認
3. **SKILL.md の生成**：フロントマッター（name / description / argument-hint / allowed-tools / context / agent / model / effort / disable-model-invocation / user-invocable / paths）と本文（手順・出力フォーマット・制約）を生成
4. **補助スクリプトの生成（必要な場合）**：`.claude/skills/<name>/bin/` 配下に `#!/usr/bin/env bash` + `set -euo pipefail` の雛形を作成、実行権限を付与
5. **検証**：YAML フロントマッターの妥当性、ディレクトリ名と `name` の一致、補助スクリプトの実行権限、本文の論理整合
6. **報告**：生成ファイル一覧と呼び出し方をユーザーに表示

## description 生成のルール

`description` は Claude が自動呼び出しを判定する最重要フィールド。生成時は以下を満たす：

1. 三人称で、ユーザーの発話例を明記する
2. ユーザーが使いそうな日本語・英語のトリガーフレーズを含める
3. 250 文字以内
4. `disable-model-invocation: true` の場合はトリガーフレーズ不要

## 出力

```
作成したスキル: <name>
  .claude/skills/<name>/SKILL.md
  .claude/skills/<name>/bin/xxx.sh  (あれば)

呼び出し方:
  /<name> で呼び出せます
  引数がある場合: /<name> <args>
```

## 制約

- 既存スキルを上書きする場合は必ずユーザーの確認を取る
- 生成する SKILL.md は 500 行以下に収める
- 副作用のあるスキル（デプロイ、コミット等）には `disable-model-invocation: true` を推奨

## 依存コマンド

なし（標準的な Read / Write / Bash / Glob / Grep / Edit ツールのみ使用）。
