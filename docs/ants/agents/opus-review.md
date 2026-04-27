# opus-review agent 仕様書

Claude Code CLI（`claude -p`）+ Opus モデルを使ってコードレビューを行う。新規レビューと `session_id` を使った継続レビューに対応する。

## 基本情報

| 項目 | 値 |
|-----|-----|
| agent 名 | `opus-review` |
| 呼び出しプロンプト形式 | `[session_id=<UUID>] [output_dir=<path>] review_instruction=<レビュー指示>` |
| 実行コンテキスト | subagent として独立コンテキストで実行 |
| 使用モデル | `sonnet`（agent 本体）／ Opus（バックエンド） |
| 結果 | Markdown ログファイルのパスを親セッションに返す |

## ユーザーが呼ぶタイミング

- Opus によるコードレビューを実施したい
- 過去の Opus レビューを継続して追質問したい（`session_id` 指定）

agent 名を指定せず単に「レビューして」と言われた場合はこの agent ではなく、ユーザー意図に応じて選択する。

## 入力引数

呼び出し prompt から以下を読み取る。

| 引数 | 説明 | デフォルト |
|-----|------|----------|
| `session_id=<UUID>` | 既存セッションを継続する | 新規セッション |
| `output_dir=<path>` | Markdown ログのコピー先 | `<repo>/.llm-ask` |
| `review_instruction=<レビュー指示>` | レビュー指示の自由文。対象範囲・観点・背景などを呼び出し側で組み立てて記述する。原文のまま渡す | 必須 |

agent 自身は `session_id` / `output_dir` のキーだけを抽出し、残りはレビュー指示として `ask-pipeline.sh` にそのまま渡す。レビュー対象の確定や観点の絞り込みは**呼び出し側 LLM の責務**。

## レビュー指示の組み立て（呼び出し側 LLM 向けの参考）

agent 側では解釈しないが、呼び出し側 LLM がレビュー指示を組み立てる際の代表的なパターンは以下：

- 未コミット変更：`ワーキングツリーの未コミット変更をレビューしてください。git diff、git diff --cached、git ls-files --others --exclude-standard で差分を確認してください。`
- ブランチ差分：`現在のブランチと <branch> との差分をレビューしてください。git diff $(git merge-base HEAD <branch>) HEAD で差分を確認してください。`
- 対象ファイル指定：`以下のファイルを中心に確認してください:\n- <file>`
- 観点指定：`以下の観点のみに絞ってレビューしてください:\n<観点>`
- 背景の追加：`【背景・修正意図・注意点】\n<内容>`
- 継続レビューの追加指示：そのままメッセージに含める

判断に迷った場合は「含めない」より「含める」側に倒す。

## 処理フロー

1. 呼び出し prompt から `session_id` / `output_dir` / `review_instruction` を抽出する
2. `${CLAUDE_PLUGIN_ROOT}/bin/ask-pipeline.sh --agent opus-review ...` を Bash ツールでフォアグラウンド実行する。応答に数分以上の時間がかかる可能性があるため Bash の timeout は最大値に設定する。サブエージェントからの Bash バックグラウンド実行は不具合があるため必ずフォアグラウンドで実行する
3. stdout 最終行から Markdown ログのパスを取得
4. 親セッションに「レビューログを読んでユーザに結果を返す」指示を送信（agent 自身はログファイルを開いて内容を読まない）

## バックエンドの固定プロンプト

`opus-review.sh` は新規セッション時のみ、以下を冒頭に付加する（継続セッションでは付加しない）：

- レビュー出力ルール（深刻度区分、ファイルパス・行番号、修正案コード例）
- デフォルト 10 観点（正確性 / セキュリティ / ドキュメント整合性 / 周辺コード / 類似機能 / ワークフロー / データライフサイクル / テスト網羅性 / 保守性 / パフォーマンス）
- 「コードの修正は行わない」制約

## 許可ツール（バックエンド側）

`opus-review.sh` は `claude -p` 起動時に以下のツールのみを許可する：

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

## 誤検知と思われる指摘
（文脈共有不足・事実誤認・周辺確認不足などによる誤検知と思われる指摘）

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
- agent はログファイルを開いて内容を読まない（パスとテンプレートを返すだけ）

## セキュリティ上の注意

`opus-review.sh` は `claude -p --dangerously-skip-permissions` と `Bash` を許可する。信頼できないリポジトリのレビューにはプロンプトインジェクションのリスクがある。詳細は [internals/security-and-permissions.md](../internals/security-and-permissions.md) を参照。

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
