# opus-review スキル仕様書

Claude Code CLI（`claude -p`）+ Opus モデルを使ってコードレビューを行う。新規レビューと `session_id` を使った継続レビューに対応する。

## 基本情報

| 項目 | 値 |
|-----|-----|
| スキル名 | `opus-review` |
| 呼び出し方式 | `/ants:opus-review [session_id=<UUID>] [base=<branch>] [targets=<...>] [aspects=<...>] [context=<...>] [output_dir=<path>]` |
| 実行コンテキスト | `context: fork`（子セッションで実行） |
| 使用モデル | `sonnet`（スキル本体）／ Opus（バックエンド） |
| 結果 | Markdown ログファイルのパスを親セッションに返す |

## ユーザーが呼ぶタイミング

- Opus によるコードレビューを実施したい
- 過去の Opus レビューを継続して追質問したい（`session_id` 指定）

スキル名を指定せず単に「レビューして」と言われた場合はこのスキルではなく、ユーザー意図に応じて選択する。

## 入力引数

`ARGUMENTS` から以下を読み取る。

| 引数 | 説明 | デフォルト |
|-----|------|----------|
| `session_id=<UUID>` | 既存セッションを継続する | 新規セッション |
| `base=<branch>` | ベースブランチとの差分をレビュー対象にする。`PR差分` / `ブランチ差分` 表記も解釈 | なし |
| `targets=<...>` | レビュー対象ファイル・ディレクトリ | なし |
| `aspects=<...>` | レビュー観点を絞る（例：「セキュリティ観点で」） | デフォルト 10 観点 |
| `context=<...>` | 修正意図・背景・設計書への言及 | なし |
| `output_dir=<path>` | Markdown ログのコピー先 | `<repo>/.llm-ask` |

判断に迷った場合は「含めない」より「含める」側に倒す。

## レビュー対象の確定

1. `session_id` 指定あり
   - 過去レビューの継続：会話セッションに範囲が記憶されているため、対象指定は不要
   - 新規レビュー：「`session_id` 指定なし」と同じルール
2. `session_id` 指定なし（新規レビュー）
   - `targets` 指定あり：そのまま使用
   - `targets` 指定なし：`get-working-set.sh` でワーキングツリー変更を取得
     - 変更あり：「未コミットの変更」をプロンプトに使用
     - 変更なし：「レビュー範囲を指定してください」を返して終了

## 処理フロー

1. 引数解釈 → レビュー対象確定
2. メッセージを以下のテンプレートで組み立てる：
   - 未コミット変更：`ワーキングツリーの未コミット変更をレビューしてください。git diff、git diff --cached、git ls-files --others --exclude-standard で差分を確認してください。`
   - ブランチ差分：`現在のブランチと <branch> との差分をレビューしてください。git diff $(git merge-base HEAD <branch>) HEAD で差分を確認してください。`
   - 対象ファイル：`以下のファイルを中心に確認してください:\n- <file>`
   - 観点指定：`以下の観点のみに絞ってレビューしてください:\n<観点>`
   - 背景：`【背景・修正意図・注意点】\n<内容>`
   - 継続指示：そのままメッセージに含める
3. `${CLAUDE_PLUGIN_ROOT}/skills/_shared-bin/ask-pipeline.sh --skill opus-review ...` を Bash ツールでフォアグラウンド実行する。長時間化する可能性があるため、Bash の timeout は最大値に設定する（Skill 使用時のバックグラウンド実行には不具合らしき挙動が報告されているため、必ずフォアグラウンドで実行する）
4. stdout 最終行から Markdown ログのパスを取得
5. 親セッションに「レビューログを読んでユーザに結果を返す」指示を送信

## バックエンドの固定プロンプト

`run-opus-review.sh` は新規セッション時のみ、以下を冒頭に付加する（継続セッションでは付加しない）：

- レビュー出力ルール（深刻度区分、ファイルパス・行番号、修正案コード例）
- デフォルト 10 観点（正確性 / セキュリティ / ドキュメント整合性 / 周辺コード / 類似機能 / ワークフロー / データライフサイクル / テスト網羅性 / 保守性 / パフォーマンス）
- 「コードの修正は行わない」制約

## 許可ツール（バックエンド側）

`run-opus-review.sh` は `claude -p` 起動時に以下のツールのみを許可する：

```
Read, Glob, Grep, Bash
```

`opus-ask` と異なり、`WebSearch` / `WebFetch` は許可しない（レビューは手元コードに集中させる方針）。

## 出力

親セッションへの返却フォーマット（外側のみ実パスに置換、内側テンプレートは置換せずそのまま渡す）：

````
レビューログ: <LOG_PATH>

レビューログを読んで以下の形式でユーザに結果を返してください。

```
レビューログ: <LOG_PATH>
セッションID: <SESSION_ID>

## レビュー結果
（ログの「Opus の回答」を原文・全文で）

## 必須対応の指摘
（typo・指摘漏れ・トレードオフのない明確な改善点）

## 要検討の指摘
（トレードオフがある指摘）

### 推奨対応

## 所感

---
次のアクション: 修正指示 / 深掘り
```
````

## 制約

- `session_id` を推測で補わない
- ユーザーから明示的な指示があるまでコードを修正しない
- 継続レビューで新規指摘が出た場合、前回の修正指示を新規指摘に拡大解釈しない

## セキュリティ上の注意

`run-opus-review.sh` は `claude -p --dangerously-skip-permissions` と `Bash` を許可する。信頼できないリポジトリのレビューにはプロンプトインジェクションのリスクがある。詳細は [internals/security-and-permissions.md](../internals/security-and-permissions.md) を参照。

## 依存コマンド

| コマンド | 用途 |
|---------|------|
| `claude` | Claude Code CLI（`claude -p`） |
| `jq` | JSON 操作 |
| `git` | 差分取得・ワーキングセット取得 |

## 関連ドキュメント

- [shellscripts/ask-pipeline.md](../shellscripts/ask-pipeline.md) — パイプライン本体
- [shellscripts/get-working-set.md](../shellscripts/get-working-set.md) — ワーキングセット取得
- [internals/ask-pipeline-flow.md](../internals/ask-pipeline-flow.md) — 全体フロー
- [internals/log-format.md](../internals/log-format.md) — JSON / Markdown ログ仕様
- [internals/security-and-permissions.md](../internals/security-and-permissions.md) — `--dangerously-skip-permissions` の取り扱い
