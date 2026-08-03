# opencode-ask

opencode CLI に質問を送り、回答を Markdown ログファイルに保存する。`session_id` を使って複数ターンの会話を継続できる。

## 基本情報

| 項目 | 値 |
|---|---|
| agent 名 | `opencode-ask` |
| 実装 | `agents/opencode-ask.py` |
| 使用モデル | `sonnet` |
| 実行コンテキスト | subagent（独立コンテキスト） |

## トリガーフレーズ

- 「opencodeに聞いて」
- 「opencode ask」
- 「opencode-ask」
- 「opencodeで調べて」

## 呼び出し形式

```
[session_id=<SESSION_ID>] [output_dir=<PATH>] message_to_send=<メッセージ>
```

### 引数

| 引数 | 必須 | 説明 |
|---|---|---|
| `message_to_send=<メッセージ>` | 必須 | opencode に送るメッセージ。原文のまま渡す |
| `session_id=<SESSION_ID>` | 省略可 | 指定すると以前の会話を継続する |
| `output_dir=<PATH>` | 省略可 | ログファイルの保存先ディレクトリ。省略時はリポジトリルートの `.llm-ask/` フォルダに保存される |

## 親セッションへの応答

```
ログファイル: <絶対パス>
```

ログファイルの中身は親セッションに展開しない。必要な部分は呼び出し側が `Read` ツールで取り込む。

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
| メッセージ | 送信したメッセージ原文 |
| opencode の回答 | opencode からの回答 |
| エラー情報 | エラー時のみ。exit code と stderr の内容 |

ログファイル名のパターン：`<YYYYMMDD_HHMMSS_mmm>_<プロジェクト名>_opencode-ask.md`

### session_id による会話継続

ログの `セッションID` 欄に記録されている ID を次回呼び出しの `session_id` に渡すと、同じ opencode スレッドで会話を続けられる。
`session_id` はopencode-reviewでも使用可能。

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
| `message_to_send` が不足 | 引数不正メッセージを出力して終了 |
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
