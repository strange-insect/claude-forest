# translate-json.sh 仕様書

JSON ファイルの指定フィールドを Haiku モデルに翻訳させ、`.translated.json` を生成する。

## 配置

```
plugins/ants/bin/translate-json.sh
```

## 呼び出し方

```bash
translate-json.sh <json-file-path> <field-name>
```

例：

```bash
translate-json.sh /tmp/codex-ask/codex-ask_proj_20260412_123456.json answer
```

## 入力

| 引数 | 説明 |
|-----|------|
| `<json-file-path>` | 入力 JSON ファイル |
| `<field-name>` | 翻訳対象のフィールド名（例：`answer`） |

## 出力

stdout に、翻訳済み JSON ファイルのパスを出力する。

例：`/tmp/codex-ask/codex-ask_proj_20260412_123456.translated.json`

## 処理フロー

1. **依存チェック**：`claude` / `jq` の存在を確認
2. **CLAUDECODE 環境変数の無効化**：ネスト呼び出しを避けるため `CLAUDECODE` / `CLAUDE_CODE_ENTRYPOINT` を unset
3. **中間ファイル名の生成**：
   - 翻訳元：`<basename>-<field>-src.txt`
   - 翻訳先：`<basename>-<field>-translated.txt`
   - 出力 JSON：`<basename>.translated.json`
4. **対象フィールドの抽出**：`jq -r '.<field>'` で翻訳元ファイルに保存
5. **Haiku に翻訳依頼**：以下のプロンプトを `claude -p --model haiku --tools "Read,Write" --dangerously-skip-permissions` に渡す
   - 翻訳元ファイルを読む
   - 内容が英語なら日本語に翻訳、既に日本語ならそのままコピー
   - 結果を翻訳先ファイルに書き込む
6. **翻訳先ファイルの存在確認**：未生成ならエラーで終了
7. **翻訳済み JSON の生成**：`jq --arg t '.<field> = $t'` で翻訳結果をフィールドに入れた `.translated.json` を出力
8. **trap で中間テキストを削除**

## 終了コード

| コード | 意味 |
|-------|------|
| 0 | 成功 |
| 1 | エラー（依存コマンド未インストール、引数不正、JSON 不在、翻訳先ファイル未生成） |

## 中間ファイルの扱い

`SRC_FILE` / `DST_FILE` は `trap cleanup EXIT` で必ず削除される。`.translated.json` は呼び出し側（`ask-pipeline.sh`）が削除する。

## セキュリティ上の注意

- `claude -p --dangerously-skip-permissions` を使用する。許可ツールは `Read,Write` に限定するが、翻訳元ファイル内容が外部に送信される（Claude API 経由）ことに注意
- 機微な情報を含む可能性があるフィールドの翻訳には使用しない設計（現在は `answer` フィールドのみ）

## 依存コマンド

| コマンド | 用途 |
|---------|------|
| `claude` | Haiku モデルへの翻訳依頼 |
| `jq` | JSON フィールド抽出・更新 |

## 関連ドキュメント

- [ask-pipeline.md](ask-pipeline.md) — 上位パイプライン
- [internals/log-format.md](../internals/log-format.md) — JSON スキーマ
- [internals/security-and-permissions.md](../internals/security-and-permissions.md) — `--dangerously-skip-permissions` の取り扱い
