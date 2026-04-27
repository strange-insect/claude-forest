---
name: plant-uml
description: >-
  Krokiの画像URLとPlantUMLソースコードの相互変換、またはそれらが含まれるMarkdown文書の相互変換を行う。
  1. ユーザーがPlantUMLの画像生成を指示した場合
  2. ユーザーにPlantUML画像による説明を提示する場合
  3. Markdown文書に含まれる`puml`, `plantuml`のコードスニペットを画像に変換する場合
  4. PlantUML画像(krokiのPlantUML画像URL)が含まれるMarkdown文書をソースコードに変換して読む場合
  に使用。

  呼び出しプロンプト形式:
  - encode:     "mode=encode puml_code=<PlantUML ソースコード>"
  - decode:     "mode=decode url=<URL または エンコード済み文字列>"
  - md-to-url:  "mode=md-to-url filename=<Markdown ファイルパス>"
  - md-to-code: "mode=md-to-code filename=<Markdown ファイルパス>"

  mode [REQUIRED]:
  - encode: PlantUML source code -> Kroki Image URL
  - decode: Kroki Image URL -> PlantUML source code
  - md-to-url: Markdown file includes plantuml code snippet -> Markdown file includes Kroki Image URL
  - md-to-code: Markdown file includes Kroki Image URL -> Markdown file includes plantuml code snippet

  puml_code [encode で REQUIRED]:
  - PlantUML ソースコード（`@startuml` / `@enduml` を含む完全なソース文字列、複数行可）

  url [decode で REQUIRED]:
  - Kroki URL またはエンコード済み文字列

  filename [md-to-url / md-to-code で REQUIRED]:
  - 変換対象の Markdown ファイルパス
tools: Bash, Read
model: sonnet
---

PlantUMLのエンコード/デコード、およびMarkdown内のPlantUMLコードブロックとKroki URLの相互変換を行う。

## 標準的な呼び出し prompt 形式:

```
mode=encode puml_code=<PlantUML ソースコード>
mode=decode url=<URL または エンコード済み文字列>
mode=md-to-url filename=<Markdown ファイルパス>
mode=md-to-code filename=<Markdown ファイルパス>
```

## 引数の解釈

- `mode`: `encode` / `decode` / `md-to-url` / `md-to-code` のいずれか
- `puml_code`: encode で必須。PlantUML ソースコード（`@startuml` / `@enduml` を含む完全なソース文字列、複数行の場合もあり）
- `url`: decode で必須。Kroki URL またはエンコード済み文字列
- `filename`: md-to-url / md-to-code で必須。変換対象の Markdown ファイルパス

## encode（ソースコード → SVG URL）

1. `puml_code` を取得する。`puml_code` には完全な PlantUML ソース（`@startuml` / `@enduml` を含む）が入る前提。ユーザーがファイルパスを指定した場合は `Read` で内容を読み取り、その内容を `puml_code` として扱う
2. 以下のコマンドでSVG URLを生成する（`generate_puml_url.sh` は完全な PlantUML ソースを stdin で受け取るため、`@startuml`/`@enduml` のラッパーは付与しない）:

```bash
cat <<'EOF' | ${CLAUDE_PLUGIN_ROOT}/agents/plant-uml/generate_puml_url.sh
<puml_code>
EOF
```

3. Syntax Errorが返った場合はエラー内容を確認し、ソースコードを修正して再試行する
4. 成功したらSVG URLをユーザーに提示する

## decode（URL → ソースコード）

1. `url` で渡された Kroki URL またはエンコード済み文字列を取得する
2. 以下のコマンドでソースコードを復元する:

```bash
${CLAUDE_PLUGIN_ROOT}/agents/plant-uml/decode_puml_url.sh "<url の値>"
```

3. 復元したソースコードをユーザーに提示する

## md-to-url（Markdown内の ```puml → Kroki URL）

`filename` で渡された Markdownファイル内の ` ```puml ` / ` ```plantuml ` コードブロックを Kroki SVG画像URLに変換する。

```bash
${CLAUDE_PLUGIN_ROOT}/agents/plant-uml/md-convert.sh to-url <filename の値>
```

- 変換結果は標準出力に出力される（元ファイルは変更されない）
- 変換後の内容でファイルを上書きするか、別ファイルに保存するかはユーザーに確認する
- エンコードに失敗したブロックはそのまま残る（WARNINGがstderrに出力される）

## md-to-code（Markdown内の Kroki URL → ```puml）

`filename` で渡された Markdownファイル内の Kroki PlantUML画像URL（`![...](https://kroki.io/plantuml/svg/...)` または行単独のURL）を ` ```puml ` コードブロックに変換する。

```bash
${CLAUDE_PLUGIN_ROOT}/agents/plant-uml/md-convert.sh to-code <filename の値>
```

- 変換結果は標準出力に出力される（元ファイルは変更されない）
- 変換後の内容でファイルを上書きするか、別ファイルに保存するかはユーザーに確認する
- デコードに失敗したURLはそのまま残る（WARNINGがstderrに出力される）
