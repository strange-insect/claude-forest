# codex-ask

OpenAI Codex CLI に質問を送り、回答を Markdown ログファイルに保存する。`session_id` を使って複数ターンの会話を継続できる。

## 基本情報

| 項目 | 値 |
|---|---|
| agent 名 | `codex-ask` |
| 実装 | `agents/codex-ask.py` |
| 使用モデル | `sonnet` |
| 実行コンテキスト | subagent（独立コンテキスト） |

## トリガーフレーズ

- 「codexに聞いて」
- 「codex ask」
- 「codex-ask」
- 「codexで調べて」

## 呼び出し形式

```
[session_id=<SESSION_ID>] message_to_send=<メッセージ>
```

### 引数

| 引数 | 必須 | 説明 |
|---|---|---|
| `message_to_send=<メッセージ>` | 必須 | Codex に送るメッセージ。原文のまま渡す |
| `session_id=<SESSION_ID>` | 省略可 | 指定すると以前の会話を継続する |

## 親セッションへの応答

```
ログファイル: <絶対パス>
```

ログファイルの中身は親セッションに展開しない。必要な部分は呼び出し側が `Read` ツールで取り込む。

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
| Codex の回答 | Codex からの回答 |
| エラー情報 | エラー時のみ。exit code と stderr の内容 |

ログファイル名のパターン：`<YYYYMMDD_HHMMSS_mmm>_<プロジェクト名>_codex-ask.md`

### session_id による会話継続

ログの `セッションID` 欄に記録されている ID を次回呼び出しの `session_id` に渡すと、同じ Codex スレッドで会話を続けられる。
`session_id` はcodex-reviewでも使用可能。

## Codex CLI 実行引数

Codex CLI は以下の固定引数で起動される。

| オプション | 値 | 説明 |
|---|---|---|
| サブコマンド | `exec` | 実行モード（非対話。承認は求められない） |
| `--skip-git-repo-check` | — | git リポジトリ外でも実行を許可 |
| `--sandbox` | `read-only` | サンドボックス: ファイル読み取りのみ許可 |
| `--json` | — | JSON 形式で出力 |
| `-m` / `-c model_reasoning_effort=` | — | `CODEX_ASK_DEFAULT_MODEL` を指定した場合のみ付与 |

`session_id` を指定した場合は `exec` の後に `resume <session_id>` が付加される。

## モデルの指定

環境変数 `CODEX_ASK_DEFAULT_MODEL` で使用するモデルを指定できる。

| 書式 | 例 | 動作 |
|---|---|---|
| `<model>` | `gpt-5` | モデルのみ指定する |
| `<model>/<effort>` | `gpt-5/high` | モデルと reasoning effort を指定する |
| 未設定 / 空文字列 | — | codex CLI 既定のモデルを使用する |

指定した値は `codex` の `-m`（model）と `-c model_reasoning_effort=`（effort）にそのまま渡される。プラグイン側で値の妥当性は検証しないため、不正な値を指定した場合は codex 側がエラーを返し、その内容がログの「エラー情報」に記録される。

## エラー処理

| 状況 | 動作 |
|---|---|
| `message_to_send` が不足 | 引数不正メッセージを出力して終了 |
| `codex` 未インストール | `'codex' コマンドが見つかりません` を出力して終了 |
| Python 3.10+ が見つからない | `python-wrapper.sh` が固定メッセージで終了 |
| Codex の実行エラー | エラー内容をログに含めてパスを返す（exit code 1） |

## 依存

### コマンド

| ツール | 用途 |
|---|---|
| `codex` | OpenAI Codex CLI |
| Python 3.10+ | パイプライン実行。`bin/python-wrapper.sh` が `${CLAUDE_PLUGIN_DATA}/venv` → `pyenv` → `conda` → `PATH` の順で解決する |

### python ライブラリ

| ライブラリ | 用途 |
|---|---|
| `filelock`（`requirements.txt`） | 起動時に `bin/python-wrapper.sh` が自動インストールする |
