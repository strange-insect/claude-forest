# plant-uml agent 仕様書

PlantUML ソースコードと Kroki SVG URL の相互変換、および Markdown 文書中のコードブロックと画像 URL の相互変換を行う。

## 基本情報

| 項目 | 値 |
|-----|-----|
| agent 名 | `plant-uml` |
| 呼び出しプロンプト形式 | mode 別: `mode=encode puml_code=<...>` / `mode=decode url=<...>` / `mode=md-to-url filename=<...>` / `mode=md-to-code filename=<...>` |
| 実行コンテキスト | subagent として独立コンテキストで実行 |
| 使用モデル | `sonnet` |
| 結果 | サブコマンドに応じて URL / ソースコード / 変換後 Markdown を返す |

## ユーザーが呼ぶタイミング

- PlantUML ソースコードから画像 URL を生成したい
- Kroki URL から元のソースコードを復元したい
- Markdown 内の `puml` / `plantuml` コードブロックを画像 URL に変換したい
- Markdown 内の Kroki URL をコードブロックに戻して読みたい

## 入力引数

| 引数 | 必須となる mode | 説明 |
|-----|------|------|
| `mode=<mode>` | 常に必須 | サブコマンド：`encode` / `decode` / `md-to-url` / `md-to-code` |
| `puml_code=<...>` | encode | PlantUML ソースコード（`@startuml` / `@enduml` を含む完全なソース、複数行可） |
| `url=<...>` | decode | Kroki URL またはエンコード済み文字列 |
| `filename=<...>` | md-to-url / md-to-code | 変換対象の Markdown ファイルパス |

### mode 別の呼び出し形式

| mode | 形式 | 出力 |
|------|------|------|
| `encode` | `mode=encode puml_code=<...>` | Kroki SVG URL |
| `decode` | `mode=decode url=<...>` | PlantUML ソースコード |
| `md-to-url` | `mode=md-to-url filename=<...>` | コードブロックを画像 URL に変換した Markdown |
| `md-to-code` | `mode=md-to-code filename=<...>` | 画像 URL をコードブロックに戻した Markdown |

## サブコマンド

### encode（ソースコード → SVG URL）

1. `puml_code` で完全な PlantUML ソース（`@startuml` / `@enduml` を含む）を受け取る。ユーザーがファイルパスで指定してきた場合は呼び出し側 LLM が `Read` で内容を読んで `puml_code` として渡す
2. `${CLAUDE_PLUGIN_ROOT}/agents/plant-uml/generate_puml_url.sh` に `puml_code` をそのまま stdin で渡し、SVG URL を生成（`@startuml`/`@enduml` のラッパー付与は不要）
3. Syntax Error が返ったらエラー内容を確認し、ソースを修正して再試行
4. SVG URL をユーザーに提示

### decode（URL → ソースコード）

1. ユーザーから PlantUML の Kroki URL またはエンコード済み文字列を受け取る
2. `${CLAUDE_PLUGIN_ROOT}/agents/plant-uml/decode_puml_url.sh "<URL_OR_ENCODED>"` でソースコードを復元
3. ソースコードをユーザーに提示

### md-to-url（Markdown 内の `` ```puml `` → Kroki URL）

```bash
${CLAUDE_PLUGIN_ROOT}/agents/plant-uml/md-convert.sh to-url <file.md>
```

- 変換結果は標準出力に出力（元ファイルは変更しない）
- 上書きするか別ファイルに保存するかはユーザーに確認する
- エンコード失敗ブロックはそのまま残り、WARNING が stderr に出る

### md-to-code（Markdown 内の Kroki URL → `` ```puml ``）

```bash
${CLAUDE_PLUGIN_ROOT}/agents/plant-uml/md-convert.sh to-code <file.md>
```

- 変換結果は標準出力に出力（元ファイルは変更しない）
- デコード失敗 URL はそのまま残り、WARNING が stderr に出る

## エラー時の処理

| エラー | 動作 |
|-------|--------|
| Syntax Error（encode） | エラー内容をもとに修正して再試行 |
| URL デコード失敗（decode） | エラーを返して終了 |
| 一部ブロック変換失敗（md-to-url / md-to-code） | 失敗箇所はそのまま残し、WARNING を stderr に出力 |

## セキュリティ上の注意

`encode` / `md-to-url` は外部の Kroki サーバー（デフォルト：kroki.io）にソースコードを送信する。機微な情報を含む図表に使う場合は、自前の Kroki サーバーを参照するように設定する。

## 依存コマンド

| コマンド | 用途 |
|---------|------|
| `curl` | Kroki サーバーへのリクエスト |
| `python3` | エンコード/デコード処理 |

## 関連スクリプト

| スクリプト | 用途 |
|----------|------|
| `agents/plant-uml/generate_puml_url.sh` | ソース → URL |
| `agents/plant-uml/decode_puml_url.sh` | URL → ソース |
| `agents/plant-uml/md-convert.sh` | Markdown ↔ URL の双方向変換 |
