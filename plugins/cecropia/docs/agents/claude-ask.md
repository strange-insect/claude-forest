# claude-ask

別セッションの Claude に質問を送り、回答を Markdown ログファイルに保存する。`session_id` を使って複数ターンの会話を継続できる。

## 基本情報

| 項目 | 値 |
|---|---|
| agent 名 | `claude-ask` |
| 実装 | `agents/claude-ask.py` |
| 使用モデル | `sonnet` |
| 実行コンテキスト | subagent（独立コンテキスト） |

## トリガーフレーズ

- 「claude-ask」

## 呼び出し形式

```
[session_id=<SESSION_ID>] [model=<MODEL>] [effort=<EFFORT>] message_to_send=<メッセージ>
```

### 引数

| 引数 | 必須 | 説明 |
|---|---|---|
| `message_to_send=<メッセージ>` | 必須 | 別セッションの Claude に送るメッセージ。原文のまま渡す |
| `session_id=<SESSION_ID>` | 省略可 | 指定すると以前の会話を継続する |
| `model=<MODEL>` | 省略可 | 使用するモデル。**ユーザーが明示的に指定した場合のみ渡す** |
| `effort=<EFFORT>` | 省略可 | reasoning effort。**ユーザーが明示的に指定した場合のみ渡す** |

## 親セッションへの応答

```
ログファイル: <絶対パス>
```

ログファイルの中身は親セッションに展開しない。必要な部分は呼び出し側が `Read` ツールで取り込む。

## 別セッションで使えるツール

別セッションには以下のツールのみ許可される。

| ツール | 用途 |
|---|---|
| Read / Glob / Grep | ファイル読み取り・検索 |
| Bash | コマンド実行 |
| WebSearch / WebFetch | Web 検索・ページ取得 |

※ `Write` / `Edit` は許可されない。ただし `Bash` 経由のリダイレクトやスクリプト実行でファイルを書き換える抜け道は残っている。

## ログファイル

### 保存先

ログは git リポジトリルート（リポジトリ外ならカレントディレクトリ）配下の `.llm-ask/` に保存される。保存先は変更できない。
`.llm-ask/` フォルダを新規作成するときは `*` を対象とした `.gitignore` が自動生成される。
`.llm-ask/` フォルダが既に存在する場合は `.gitignore` の作成/編集は行われない。

### 構成

| セクション | 内容 |
|---|---|
| ヘッダー | 日時・モード（new / continuation）・ディレクトリ・セッション ID |
| メッセージ | 送信したメッセージ原文 |
| Claude の回答 | 別セッションの Claude からの回答 |
| エラー情報 | エラー時のみ。exit code と stderr の内容 |

ログファイル名のパターン：`<YYYYMMDD_HHMMSS_mmm>_<プロジェクト名>_claude-ask.md`

### session_id による会話継続

ログの `セッションID` 欄に記録されている ID を次回呼び出しの `session_id` に渡すと、同じセッションで会話を続けられる。
`session_id` は claude-review でも使用可能。

## Claude CLI 実行引数

`claude` CLI は以下の固定引数で起動される。

| オプション | 値 | 説明 |
|---|---|---|
| `-p` | — | 非インタラクティブモード（print mode） |
| `--output-format` | `json` | JSON 形式で出力 |
| `--model` | — | モデルを指定した場合のみ付与 |
| `--effort` | — | effort を指定した場合のみ付与 |
| `--dangerously-skip-permissions` | — | 権限確認をスキップ |
| `--tools` | `Read,Glob,Grep,Bash,WebSearch,WebFetch` | 許可するツール |

`session_id` を指定した場合は `--resume <session_id>` が付加される。

## モデルの指定

使用するモデルと reasoning effort は、呼び出し時の `model=` / `effort=` 指定と環境変数 `CLAUDE_ASK_DEFAULT_MODEL` の 2 通りで指定できる。

| 優先順 | 指定方法 |
|---|---|
| 1 | 呼び出しプロンプトの `model=` / `effort=`（agent が `--model` / `--effort` として渡す） |
| 2 | 環境変数 `CLAUDE_ASK_DEFAULT_MODEL` |
| 3 | 未指定（既定モデル） |

`model` と `effort` は独立に上書きされる。`model` だけを明示指定した場合、effort は環境変数由来の値（無ければ未指定）のままになる。

agent は**ユーザーが明示的にモデルや effort を指定した場合のみ** `--model` / `--effort` を付与する。指定が無い場合は付与せず、環境変数または `claude` CLI の既定モデルが使われる。

環境変数 `CLAUDE_ASK_DEFAULT_MODEL` の書式は次のとおり。

| 書式 | 例 | 動作 |
|---|---|---|
| `<model>` | `opus` | モデルのみ指定する |
| `<model>,<effort>` | `opus,high` | モデルと reasoning effort を指定する |
| 未設定 / 空文字列 | — | `claude` CLI 既定のモデルを使用する |

呼び出し時の指定・環境変数のいずれで指定した値も、`claude` の `--model`（model）と `--effort`（effort）にそのまま渡される。プラグイン側で値の妥当性は検証しないため、不正な値を指定した場合は claude 側がエラーを返し、その内容がログの「エラー情報」に記録される。

## エラー処理

| 状況 | 動作 |
|---|---|
| `message_to_send` が不足 | 引数不正メッセージを出力して終了 |
| `claude` 未インストール | `'claude' コマンドが見つかりません` を出力して終了 |
| Python 3.10+ が見つからない | `python-wrapper.sh` が固定メッセージで終了 |
| `claude` の実行エラー | エラー内容をログに含めてパスを返す（exit code 1） |

## 依存

### コマンド

| ツール | 用途 |
|---|---|
| `claude` | Claude Code CLI |
| Python 3.10+ | パイプライン実行。`bin/python-wrapper.sh` が `${CLAUDE_PLUGIN_DATA}/venv` → `pyenv` → `conda` → `PATH` の順で解決する |

### python ライブラリ

| ライブラリ | 用途 |
| `filelock`（`requirements.txt`） | 起動時に `bin/python-wrapper.sh` が自動インストールする |
