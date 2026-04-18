---
name: plant-uml
description: >-
  Krokiの画像URLとPlantUMLソースコードの相互変換、またはそれらが含まれるMarkdown文書の相互変換を行う。
  1. ユーザーがPlantUMLの画像生成を指示した場合
  2. ユーザーにPlantUML画像による説明を提示する場合
  3. Markdown文書に含まれる`puml`, `plantuml`のコードスニペットを画像に変換する場合
  4. PlantUML画像(krokiのPlantUML画像URL)が含まれるMarkdown文書をソースコードに変換して読む場合
  に使用。

  argument: "<encode|decode|md-to-url|md-to-code> [ソースコード/URL/Markdownファイルパス]"
allowed-tools: Bash, Read
context: fork
model: sonnet
---

PlantUMLのエンコード/デコード、およびMarkdown内のPlantUMLコードブロックとKroki URLの相互変換を行う。

## 引数の解釈

- `$ARGUMENTS[0]`: サブコマンド（`encode`, `decode`, `md-to-url`, `md-to-code`）
- `$ARGUMENTS[1]` 以降: 対象のソースコード、URL、またはファイルパス

## encode（ソースコード → SVG URL）

1. ユーザーからPlantUMLソースコードを受け取る（引数、会話内のコードブロック、またはファイルパス）
2. 以下のコマンドでSVG URLを生成する:

```bash
cat <<'EOF' | ${CLAUDE_SKILL_DIR}/bin/generate_puml_url.sh
@startuml
（ソースコード）
@enduml
EOF
```

3. Syntax Errorが返った場合はエラー内容を確認し、ソースコードを修正して再試行する
4. 成功したらSVG URLをユーザーに提示する

## decode（URL → ソースコード）

1. ユーザーからPlantUMLのURL（kroki.io等）またはエンコード済み文字列を受け取る
2. 以下のコマンドでソースコードを復元する:

```bash
${CLAUDE_SKILL_DIR}/bin/decode_puml_url.sh "URL_OR_ENCODED_STRING"
```

3. 復元したソースコードをユーザーに提示する

## md-to-url（Markdown内の ```puml → Kroki URL）

Markdownファイル内の ` ```puml ` / ` ```plantuml ` コードブロックを Kroki SVG画像URLに変換する。

```bash
${CLAUDE_SKILL_DIR}/bin/md-convert.sh to-url <file.md>
```

- 変換結果は標準出力に出力される（元ファイルは変更されない）
- 変換後の内容でファイルを上書きするか、別ファイルに保存するかはユーザーに確認する
- エンコードに失敗したブロックはそのまま残る（WARNINGがstderrに出力される）

## md-to-code（Markdown内の Kroki URL → ```puml）

Markdownファイル内の Kroki PlantUML画像URL（`![...](https://kroki.io/plantuml/svg/...)` または行単独のURL）を ` ```puml ` コードブロックに変換する。

```bash
${CLAUDE_SKILL_DIR}/bin/md-convert.sh to-code <file.md>
```

- 変換結果は標準出力に出力される（元ファイルは変更されない）
- 変換後の内容でファイルを上書きするか、別ファイルに保存するかはユーザーに確認する
- デコードに失敗したURLはそのまま残る（WARNINGがstderrに出力される）
