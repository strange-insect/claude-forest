# plant-uml

PlantUML ソースコードと 画像 (Kroki URL) の相互変換、および Markdown ファイル内のコードブロックと画像の相互変換を行う。

## 基本情報

| 項目 | 値 |
|---|---|
| agent 名 | `plant-uml` |
| 実装 | `agents/plant-uml/` |
| 使用モデル | `sonnet` |
| 実行コンテキスト | subagent（独立コンテキスト） |

## 呼び出し形式

4 つのモードがある。

| モード | プロンプト形式 |
|---|---|
| `encode` | `mode=encode puml_code=<PlantUML ソースコード>` |
| `decode` | `mode=decode url=<URL またはエンコード済み文字列>` |
| `md-to-url` | `mode=md-to-url filename=<Markdown ファイルパス>` |
| `md-to-code` | `mode=md-to-code filename=<Markdown ファイルパス>` |

### 引数

| 引数 | 必須 | 説明 |
|---|---|---|
| `mode` | 必須 | 上表の 4 値のいずれか |
| `puml_code` | `encode` のみ | `@startuml` / `@enduml` を含む完全なソース文字列。複数行可。ユーザーがファイルパスを指定した場合は `Read` で読み取る |
| `url` | `decode` のみ | Kroki URL またはエンコード済み文字列 |
| `filename` | `md-to-url` / `md-to-code` のみ | 変換対象の Markdown ファイルパス |

## 動作モード

### encode — PlantUML ソース → Kroki SVG URL

Plant UMLのソースコードを入力し画像URL (Kroki) を応答する

### decode — Kroki URL → PlantUML ソース

Kroki 画像 URL またはエンコード済み文字列を渡し、PlantUML ソースを復元し応答する。

### md-to-url — Markdown 内の `puml` ブロック → Kroki URL

Markdown ファイル内の ` ```puml ` / ` ```plantuml ` コードブロックを Markdown 画像記法 `![PlantUML](https://...)` に変換する。
変換後の内容でファイルを上書きするか別ファイルに保存するかをユーザーに確認してファイルに保存する。

### md-to-code — Markdown 内の Kroki URL → `puml` ブロック

Markdown ファイル内の行単独の Markdown 画像記法または行単独の URL を ` ```puml ` コードブロックに変換する。
変換後の内容でファイルを上書きするか別ファイルに保存するかをユーザーに確認してファイルに保存する。

## 設定変更

`PLANTUML_SERVER` 環境変数で画像URLを変更できる（未設定時は `https://kroki.io/plantuml`）。

## エラー処理

| 状況 | 動作 |
|---|---|
| `mode` が不正 | 引数不正メッセージを出力して終了 |
| `puml_code` / `url` / `filename` が不足 | 引数不正メッセージを出力して終了 |
| Python 3.10+ が見つからない | `python-wrapper.sh` が固定メッセージで終了 |
| Kroki サーバーに接続できない | `Failed to contact PlantUML server: <URL>` を出力して終了 |
| PlantUML 構文エラー | サーバーのエラーメッセージを表示して終了（encode 時は修正後に再試行する） |
| md-to-url / md-to-code でブロック単位の変換失敗 | 失敗したブロックをそのまま残し WARNING を stderr に出力。他のブロックは処理を継続 |

## 依存

| ツール | 用途 |
|---|---|
| Python 3.10+ | エンコード・デコード・Markdown 変換（stdlib のみ）。`bin/python-wrapper.sh` が `${CLAUDE_PLUGIN_DATA}/venv` → `pyenv` → `conda` → `PATH` の順で Python を解決する |
| Kroki サーバー（外部） | encode 時に構文チェック用で参照（`PLANTUML_SERVER` で変更可） |
