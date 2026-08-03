# opus-ask

別セッションの Claude Opus に質問を送り、回答を Markdown ログファイルに保存する。`session_id` を使って複数ターンの会話を継続できる。

## 基本情報

| 項目 | 値 |
|---|---|
| agent 名 | `opus-ask` |
| 実装 | `agents/opus-ask.py` |
| 使用モデル | `sonnet` |
| 実行コンテキスト | subagent（独立コンテキスト） |

## トリガーフレーズ

- 「opusに聞いて」
- 「opus ask」
- 「opus-ask」
- 「opusで調べて」

## 呼び出し形式

```
[session_id=<SESSION_ID>] message_to_send=<メッセージ>
```

### 引数

| 引数 | 必須 | 説明 |
|---|---|---|
| `message_to_send=<メッセージ>` | 必須 | Opus に送るメッセージ。原文のまま渡す |
| `session_id=<SESSION_ID>` | 省略可 | 指定すると以前の会話を継続する |

## 親セッションへの応答

```
ログファイル: <絶対パス>
```

ログファイルの中身は親セッションに展開しない。必要な部分は呼び出し側が `Read` ツールで取り込む。

## Opus セッションで使えるツール

Opus セッションには以下のツールのみ許可される。

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
| Opus の回答 | Opus からの回答 |
| エラー情報 | エラー時のみ。exit code と stderr の内容 |

ログファイル名のパターン：`<YYYYMMDD_HHMMSS_mmm>_<プロジェクト名>_opus-ask.md`

### session_id による会話継続

ログの `セッションID` 欄に記録されている ID を次回呼び出しの `session_id` に渡すと、同じ Opus セッションで会話を続けられる。
`session_id` は opus-review でも使用可能。

## Claude CLI 実行引数

`claude` CLI は以下の固定引数で起動される。

| オプション | 値 | 説明 |
|---|---|---|
| `-p` | — | 非インタラクティブモード（print mode） |
| `--output-format` | `json` | JSON 形式で出力 |
| `--model` | `Opus` | Opus モデルを使用 |
| `--dangerously-skip-permissions` | — | 権限確認をスキップ |
| `--tools` | `Read,Glob,Grep,Bash,WebSearch,WebFetch` | 許可するツール |

`session_id` を指定した場合は `--resume <session_id>` が付加される。

## エラー処理

| 状況 | 動作 |
|---|---|
| `message_to_send` が不足 | 引数不正メッセージを出力して終了 |
| `claude` 未インストール | `'claude' コマンドが見つかりません` を出力して終了 |
| Python 3.10+ が見つからない | `python-wrapper.sh` が固定メッセージで終了 |
| Opus の実行エラー | エラー内容をログに含めてパスを返す（exit code 1） |

## 依存

### コマンド

| ツール | 用途 |
|---|---|
| `claude` | Claude Code CLI |
| Python 3.10+ | パイプライン実行。`bin/python-wrapper.sh` が `${CLAUDE_PLUGIN_DATA}/venv` → `pyenv` → `conda` → `PATH` の順で解決する |

### python ライブラリ

| ライブラリ | 用途 |
| `filelock`（`requirements.txt`） | 起動時に `bin/python-wrapper.sh` が自動インストールする |
