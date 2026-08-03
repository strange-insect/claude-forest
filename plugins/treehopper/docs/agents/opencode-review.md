# opencode-review

opencode CLI にコードレビューを依頼し、結果を Markdown ログファイルに保存する。`session_id` を使って指摘対応の追加レビューを同一スレッドで継続できる。

## 基本情報

| 項目 | 値 |
|---|---|
| agent 名 | `opencode-review` |
| 実装 | `agents/opencode-review.py` |
| 使用モデル | `sonnet` |
| 実行コンテキスト | subagent（独立コンテキスト） |

## トリガーフレーズ

- 「opencodeでレビュー」
- 「opencodeレビュー」
- 「opencode-review」

※ agent 名を指定せず単に「レビューして」と言った場合は使用しない。

## 呼び出し形式

```
[session_id=<SESSION_ID>] [output_dir=<PATH>] [reinject_guideline=<true|false>] review_instruction=<レビュー指示>
```

### 引数

| 引数 | 必須 | 説明 |
|---|---|---|
| `review_instruction=<レビュー指示>` | 必須 | レビュー指示。原文のまま渡す |
| `session_id=<SESSION_ID>` | 省略可 | 指摘対応後に継続レビューする場合に前回の session_id を指定する |
| `output_dir=<PATH>` | 省略可 | ログファイルの保存先ディレクトリ。省略時はリポジトリルートの `.llm-ask/` フォルダに保存される |
| `reinject_guideline=<true\|false>` | 省略可 | 役割定義・出力ルール・標準レビュー観点などの固定プロンプトを review_instruction の先頭に付加するかどうか。初回レビュー時はこの値に関わらず必ず付加される。継続レビュー時は `true` を指定した場合のみ付加される。`opencode-ask` からの継続セッションで初回プロンプトを opencode に与えていない場合に指定する |

`review_instruction` の最もシンプルな例：「未コミットの変更をレビューしてください」。必要に応じて背景情報・対象範囲・比較元ブランチ名・レビュー観点を追加する。

## 親セッションへの応答

ログファイルのパスと、親セッションがユーザーに結果を提示するためのテンプレートを返す。

```
レビューログ: <絶対パス>

レビューログを読んで以下のテンプレートに従いユーザに結果を応答してください。
ユーザから明示的な指示がない限り指摘対応や修正を開始しないでください。

（応答テンプレート）
```

※ 親セッションはこのテンプレートに従ってユーザーに結果を提示する。

### 親セッションの応答テンプレート構成

親セッションがユーザーに返す応答の構成：

| セクション | 内容 |
|---|---|
| レビューログ / セッション ID | ログファイルパスと session_id |
| レビュー結果 | opencode の回答原文（全文） |
| 誤検知と思われる指摘 | 文脈不足・事実誤認・周辺確認不足による誤検知の分類 |
| 必須対応の指摘 | typo・バグ・検討の余地がない明確な改善点 |
| 要検討の指摘 | トレードオフがある・意思決定が必要な指摘 |
| 推奨対応 | 要検討の指摘に対する推奨対応 |
| 所感 | レビュー結果に対する所感 |

## レビュー観点

新規セッション（`session_id` なし）の場合、以下の観点が opencode への指示に自動付加される。継続セッション（`session_id` あり）の場合は既定で付加されないが、`reinject_guideline=true` を指定すれば改めて付加できる。

| # | 観点 |
|---|---|
| 1 | 正確性・ロジック（バグ、エッジケース、境界値、競合状態） |
| 2 | セキュリティ（インジェクション、認証・認可漏れ、機密情報の露出） |
| 3 | ドキュメント整合性（README・コメント・docstring・CHANGELOG の更新漏れ） |
| 4 | 周辺コードとの整合性（変更していない関数・設定・テストとの矛盾） |
| 5 | 類似機能との整合性（コードベース内の命名規則・パターンとの乖離） |
| 6 | ワークフロー・連携影響（上流・下流の処理フローへの影響） |
| 7 | データライフサイクル（同じデータを参照・更新する機能との不整合） |
| 8 | テスト網羅性（追加・変更ロジックに対応するテストの有無） |
| 9 | 保守性（命名、重複、抽象化の適切さ） |
| 10 | パフォーマンス（不要な計算・I/O・メモリ使用） |

また opencode には「コードの修正は行わず読み取りのみ」「深刻度・ファイルパス・行番号を明記」「具体的なコード例を含める」という制約が自動付加される。

## ログファイル

### 保存先

`output_dir` を省略した場合、git リポジトリルート（リポジトリ外ならカレントディレクトリ）配下の `.llm-ask/` に保存される。
`output_dir` に相対パスを渡した場合も同じ基準ディレクトリからの相対パスになる。
`.llm-ask/` フォルダを新規作成するときは `*` を対象とした `.gitignore` が自動生成される。
`.llm-ask/` フォルダが既に存在する場合は `.gitignore` の作成/編集は行われない。

### 構成

| セクション | 内容 |
|---|---|
| ヘッダー | 日時・モード（new / continuation）・ディレクトリ・セッション ID |
| メッセージ | 送信したレビュー指示原文 |
| opencode の回答 | opencode からのレビュー結果 |
| エラー情報 | エラー時のみ。exit code と stderr の内容 |

ログファイル名のパターン：`<YYYYMMDD_HHMMSS_mmm>_<プロジェクト名>_opencode-review.md`

### session_id による継続レビュー

ログの `セッションID` 欄の ID を次回呼び出しの `session_id` に渡すと、同じ opencode スレッドで追加レビューを依頼できる。opencode-ask の session_id も指定可能。

## opencode CLI 実行引数

opencode CLI は以下の固定引数で起動される。

| オプション | 値 | 説明 |
|---|---|---|
| サブコマンド | `run` | 実行モード（非対話。メッセージは stdin から渡す） |
| `--format` | `json` | イベントを JSON 形式で出力 |
| `--agent` | `plan` | opencode の plan エージェント: `edit` 権限が既定で `deny` |

`session_id` を指定した場合は `--session <session_id>` が付加される。

### read-only の担保について

codex CLI の `--sandbox read-only` は OS レベルで書き込みを遮断するが、opencode の `--agent plan` は権限設定にすぎず、同等の強制力は無い。

- `edit` 権限は既定で `deny` だが、`bash` 権限は `allow` のため **bash 経由のファイル書き込みは通る**
- plan エージェントは `.opencode/plans/*.md` と `~/.local/share/opencode/plans/*.md` に対しては `edit` が明示的に `allow`
- これらの権限はユーザー/プロジェクトの `opencode.json` で上書きできる

`bash` を一律 `deny` にすると `git diff` 等が実行できずレビュー用途が成立しないため、本プラグインでは権限を制限していない。書き込みを防ぎたい場合は opencode 側の permission 設定で絞る。設定方法は opencode のドキュメントを参照（https://opencode.ai/docs/permissions/）。

opencode には codex CLI の `--output-last-message` に相当するオプションが無いため、回答は `--format json` の出力から `type == "text"` イベントを messageID ごとにまとめ、最後の messageID 分を組み立てて取得する。セッション ID も同出力の `sessionID` から取得する。

## エラー処理

| 状況 | 動作 |
|---|---|
| `review_instruction` が不足 | 引数不正メッセージを出力して終了 |
| `opencode` 未インストール | `'opencode' コマンドが見つかりません` を出力して終了 |
| Python 3.10+ が見つからない | `python-wrapper.sh` が固定メッセージで終了 |
| opencode の実行エラー | エラー内容をログに含めてパスを返す（exit code 1） |

## 依存

### コマンド

| ツール | 用途 |
|---|---|
| `opencode` | opencode CLI |
| Python 3.10+ | パイプライン実行。`bin/python-wrapper.sh` が `${CLAUDE_PLUGIN_DATA}/venv` → `pyenv` → `conda` → `PATH` の順で解決する |

### python ライブラリ

| ライブラリ | 用途 |
|---|---|
| `filelock`（`requirements.txt`） | 起動時に `bin/python-wrapper.sh` が自動インストールする |
