# plant-uml スキル仕様書

PlantUML ソースコードと Kroki SVG URL の相互変換、および Markdown 文書中のコードブロックと画像 URL の相互変換を行う。

## 基本情報

| 項目 | 値 |
|-----|-----|
| スキル名 | `plant-uml` |
| 呼び出し方式 | `/ants:plant-uml <encode\|decode\|md-to-url\|md-to-code> [入力]` |
| 実行コンテキスト | `context: fork`（子セッションで実行） |
| 使用モデル | `sonnet` |
| 結果 | サブコマンドに応じて URL / ソースコード / 変換後 Markdown を返す |

## ユーザーが呼ぶタイミング

- PlantUML ソースコードから画像 URL を生成したい
- Kroki URL から元のソースコードを復元したい
- Markdown 内の `puml` / `plantuml` コードブロックを画像 URL に変換したい
- Markdown 内の Kroki URL をコードブロックに戻して読みたい

## 入力引数

| 引数 | 説明 |
|-----|------|
| `ARGUMENTS[0]` | サブコマンド：`encode` / `decode` / `md-to-url` / `md-to-code` |
| `ARGUMENTS[1]` 以降 | 対象のソースコード、URL、または Markdown ファイルパス |

## サブコマンド

### encode（ソースコード → SVG URL）

1. ユーザーから PlantUML ソースコードを受け取る（引数、会話内のコードブロック、またはファイル）
2. `${CLAUDE_SKILL_DIR}/bin/generate_puml_url.sh` で SVG URL を生成
3. Syntax Error が返ったらエラー内容を確認し、ソースを修正して再試行
4. SVG URL をユーザーに提示

### decode（URL → ソースコード）

1. ユーザーから PlantUML の Kroki URL またはエンコード済み文字列を受け取る
2. `${CLAUDE_SKILL_DIR}/bin/decode_puml_url.sh "<URL_OR_ENCODED>"` でソースコードを復元
3. ソースコードをユーザーに提示

### md-to-url（Markdown 内の `` ```puml `` → Kroki URL）

```bash
${CLAUDE_SKILL_DIR}/bin/md-convert.sh to-url <file.md>
```

- 変換結果は標準出力に出力（元ファイルは変更しない）
- 上書きするか別ファイルに保存するかはユーザーに確認する
- エンコード失敗ブロックはそのまま残り、WARNING が stderr に出る

### md-to-code（Markdown 内の Kroki URL → `` ```puml ``）

```bash
${CLAUDE_SKILL_DIR}/bin/md-convert.sh to-code <file.md>
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
| `bin/generate_puml_url.sh` | ソース → URL |
| `bin/decode_puml_url.sh` | URL → ソース |
| `bin/md-convert.sh` | Markdown ↔ URL の双方向変換 |
