---
name: create-skill
description: >-
  対話的にClaude Codeのカスタムスキル（SKILL.md）を新規作成する。
  スキル名・用途・引数・ツール・実行コンテキスト等をヒアリングし、SKILL.md と補助スクリプトを生成する。

  argument: "[スキル名] [用途の説明]"
allowed-tools: Read, Write, Bash, Glob, Grep, Edit
disable-model-invocation: true
---

# タスク: カスタムスキルの新規作成

ユーザーの要件をヒアリングし、`.claude/skills/<name>/SKILL.md`（および必要なら補助スクリプト）を生成する。

---

## 1. 要件のヒアリング

`ARGUMENTS` からスキル名や用途が読み取れる場合はそれを初期値とする。
不足している情報があればユーザーに質問する。

### 必須ヒアリング項目

| 項目 | 質問例 | 備考 |
|---|---|---|
| **スキル名** | `create-skill foo` の `foo` 部分 | 小文字英数字+ハイフン、最大64文字 |
| **用途・説明** | 「このスキルは何をするもの？」 | description フィールドに使用（250文字以内） |
| **やりたいこと** | 「具体的にどんな手順を実行する？」 | SKILL.md 本文の手順になる |

### 任意ヒアリング項目（デフォルト値あり）

| 項目 | デフォルト | 質問するタイミング |
|---|---|---|
| **引数** | なし | 用途から引数が必要そうな場合 |
| **使用ツール** | 制限なし | 特定ツールに限定したい場合 |
| **実行コンテキスト** | インライン | 重い処理・親会話を汚したくない場合は `context: fork` |
| **サブエージェント型** | general-purpose | `context: fork` の場合のみ |
| **自動呼び出し** | 有効 | 手動のみにしたい場合は `disable-model-invocation: true` |
| **補助スクリプト** | なし | 外部コマンド実行が必要な場合 |

---

## 2. 既存スキルの確認

同名スキルが存在しないか確認する:

```bash
mkdir -p .claude/skills
ls .claude/skills/
```

同名が存在する場合はユーザーに上書き確認を取る。

---

## 3. SKILL.md の生成

以下のテンプレートに沿って SKILL.md を生成する。

### フロントマッター

```yaml
---
name: <スキル名>
description: <250文字以内の説明。下記「descriptionの書き方」参照>
argument-hint: "<引数ヒント>"          # 引数がある場合のみ
allowed-tools: <ツール名カンマ区切り>    # 制限する場合のみ
context: fork                          # フォーク実行する場合のみ
agent: <サブエージェント型>              # context: fork の場合のみ
disable-model-invocation: true         # 手動のみの場合
---
```

### フロントマッターフィールド一覧（参考）

| フィールド | 説明 | 有効な値 |
|---|---|---|
| `name` | スキル名（ディレクトリ名と一致） | 小文字英数字+ハイフン、最大64文字 |
| `description` | 用途の説明（下記「descriptionの書き方」参照） | 文字列（250文字以内推奨） |
| `argument-hint` | 引数ヒント | `[arg1] [arg2]` 形式 |
| `allowed-tools` | 許可ツール | `Read, Write, Bash, Glob, Grep, Edit, Agent, WebFetch, WebSearch` 等。`Bash(python *)` のようにワイルドカードも可 |
| `context` | 実行コンテキスト | `fork`（省略時はインライン） |
| `agent` | サブエージェント型 | `Explore`, `Plan`, `general-purpose` |
| `model` | モデル指定 | `sonnet`, `opus`, `haiku` |
| `effort` | 労力レベル | `low`, `medium`, `high`, `max` |
| `disable-model-invocation` | 自動呼び出し無効化 | `true` / `false` |
| `user-invocable` | ユーザー呼び出し可否 | `true` / `false` |
| `paths` | 自動呼び出しのパス制限 | グロブパターン |

### description の書き方

`description` は Claude が自動呼び出しを判定する最重要フィールド。以下のルールで生成する:

1. **三人称で、ユーザーがどんな発話をしたときに呼び出されるべきかを明記する**
   - 良い例: `PRの差分をCodexでレビューする。ユーザーが「レビューして」「コードレビュー」「codexでチェック」と言った場合に使用。`
   - 悪い例: `コードレビューを実施する。`
2. **ユーザーが実際に使いそうなトリガーフレーズ（日本語・英語）を含める**
3. **250文字以内に収める**
4. `disable-model-invocation: true` の場合はトリガーフレーズは不要（手動呼び出しのみのため）

自動呼び出しを有効にするスキルの場合は、ヒアリング時に「ユーザーがどう言ったらこのスキルを呼び出したい？」と確認し、その回答を description に反映する。
`disable-model-invocation: true` の場合はこのヒアリングをスキップし、用途の説明のみで構成する。

### 本文の構成

1. タスクの概要（1行）
2. 手順（番号付き）
   - 各手順は明確で具体的に
   - コマンドがあればコードブロックで記載
3. 出力フォーマット（ある場合）
4. 制約事項（ある場合）

### `ARGUMENTS` とは

ユーザーがスキル呼び出し時に渡した引数文字列を表す。ランタイムによって SKILL.md 本文に展開される。

| 記法 | 意味 |
|---|---|
| <code>&#36;ARGUMENTS</code> | 全引数に置換される |
| <code>&#36;ARGUMENTS[N]</code> / <code>&#36;N</code> | N番目の引数に置換される（0始まり） |

本文中に <code>&#36;ARGUMENTS</code> が**含まれない**場合、ランタイムはプロンプト末尾に `ARGUMENTS: <値>` を自動付与する。

### `ARGUMENTS` の参照方法（本文での書き方）

手順文中で引数を参照するときは、**先頭の `$` を外した `ARGUMENTS` と記述する**。理由は以下。

- `ARGUMENTSを取得する`というようなプロンプトのARGUMENTSが展開されてしまうと`3を取得する`のような意味不明なプロンプトになってしまう
- 本文に <code>&#36;ARGUMENTS</code> が無ければランタイムが末尾に `ARGUMENTS: <値>` を付与するため、`ARGUMENTS` という語だけで引数を指し示せる。
- <code>&#36;ARGUMENTS</code> を本文に書くと、手順説明やドキュメント部分など引数値にしたくない箇所まで文字列置換されてしまい、モデルに指示の意図が伝わらない。

### その他の置換トークン

| 記法 | 説明 |
|---|---|
| <code>&#36;{CLAUDE_SKILL_DIR}</code> | SKILL.md のあるディレクトリの絶対パス |
| <code>!&#96;command&#96;</code> | 事前実行されるシェルコマンド（出力が本文に展開される） |

いずれもランタイムによってプロンプト送信前に置換される。ドキュメントとして記述する場合は HTML エンティティ等でエスケープする必要がある（このテーブル自体が <code>&#36;</code> や <code>&#96;</code> を使って置換を回避している）。

---

## 4. 補助スクリプトの生成（必要な場合）

外部コマンドの実行が必要な場合は `bin/` ディレクトリにスクリプトを作成する。

- パス: `.claude/skills/<name>/bin/<script-name>.sh`
- 先頭に `#!/usr/bin/env bash` と `set -euo pipefail`
- SKILL.md からは <code>&#36;{CLAUDE_SKILL_DIR}/bin/&lt;script-name&gt;.sh</code> で参照

```bash
mkdir -p .claude/skills/<name>/bin
chmod +x .claude/skills/<name>/bin/<script-name>.sh
```

---

## 5. 検証

生成後、以下を確認する:

1. SKILL.md のフロントマッターが有効な YAML か
2. スキル名がディレクトリ名と一致しているか
3. 補助スクリプトがある場合、実行権限が付与されているか
4. SKILL.md の手順が論理的に整合しているか

---

## 6. ユーザーへの報告

生成したファイルの一覧と、スキルの呼び出し方を提示する:

```
作成したスキル: <name>
  .claude/skills/<name>/SKILL.md
  .claude/skills/<name>/bin/xxx.sh  (あれば)

呼び出し方:
  /<name> で呼び出せます
  引数がある場合: /<name> <args>
```

---

## 制約

- 既存スキルを上書きする場合は必ずユーザーの確認を取る
- フロントマッターの description は具体的なキーワードを含め、Claude が自動呼び出しを判断できるようにする
- 生成する SKILL.md は 500 行以下に収める
- 副作用のあるスキル（デプロイ、コミット等）には `disable-model-invocation: true` を推奨する
