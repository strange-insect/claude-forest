# ask-pipeline.sh 仕様書

`*-ask` / `*-review` の 4 agent が共通で使う処理パイプラインの入口。各 agent の `agents/<name>.sh` を呼び出し、
翻訳・Markdown 化・出力ディレクトリへのコピーまでを一貫して実行する。

## 配置

```
plugins/ants/bin/ask-pipeline.sh
```

## 呼び出し方

```bash
ask-pipeline.sh --agent <name> [--session-id UUID] [--output-dir PATH] --message "テキスト"

# stdin で渡す場合
ask-pipeline.sh --agent <name> [--session-id UUID] [--output-dir PATH] <<'EOF'
質問テキスト（複数行可）
EOF
```

## 入力

| 引数 | 説明 | 必須 |
|-----|------|-----|
| `--agent <name>` | 対応する agent 名（`codex-ask` / `codex-review` / `opus-ask` / `opus-review`） | 必須 |
| `--session-id <UUID>` | セッション継続用 UUID | 任意 |
| `--output-dir <path>` | Markdown ログのコピー先 | 任意（デフォルト：`<repo>/.llm-ask`） |
| `--message <text>` | メッセージ本文 | `--message` または stdin のいずれか必須 |
| stdin | メッセージ本文 | 同上 |

## 出力

stdout の最終行に、コピー先 Markdown ログの絶対パスを出力する。

## 終了コード

| コード | 意味 |
|-------|------|
| 0 | 成功 |
| 1 | エラー（不明オプション、メッセージ未指定、`agents/<name>.sh` の不在、各ステップの致命的失敗） |

`agents/<name>.sh` 自体が異常終了した場合、エラー内容を含む JSON / Markdown ログは生成された上で、最終的な exit code に伝搬する。

## 処理フロー

1. **引数パース**：`--agent` / `--message` / `--session-id` / `--output-dir` を解釈
2. **メッセージ取得**：`--message` 未指定なら stdin から読む。空ならエラー
3. **run スクリプト解決**：`${PLUGIN_ROOT}/agents/<name>.sh` の存在・実行可能性を確認
4. **run スクリプト実行**：`agents/<name>.sh --message <...> [--session-id <...>]` を実行し、JSON ファイルパスを取得
5. **翻訳**：`translate-json.sh <JSON> answer` で `answer` フィールドを翻訳。失敗時は WARN を出して原文のまま続行
6. **Markdown 化**：`save-ask-log.sh <JSON>` で Markdown ログに変換し、パスを取得
7. **中間 JSON の削除**：Markdown が生成できた場合、元 JSON と翻訳後 JSON を削除
8. **出力先ディレクトリの決定**：
   - `--output-dir` 未指定 → `<repo>/.llm-ask`（git リポジトリ外なら CWD）
   - `--output-dir` 指定（絶対パス） → そのまま
   - `--output-dir` 指定（相対パス） → `<repo>/<path>`（git リポジトリ外なら CWD 起点）
9. **出力先の初期化**：ディレクトリが存在しなければ作成し、`*` のみの `.gitignore` を同梱（既存ディレクトリには触らない）
10. **Markdown のコピー**：保存先の `/tmp/<model>-ask/` から、出力先ディレクトリにコピー
11. **コピー先パスを stdout に出力**

## 出力先の挙動

| 状態 | 動作 |
|-----|------|
| ディレクトリ未作成 | 作成 + `.gitignore`（`*`）を生成 |
| ディレクトリ既存 | 既存物には触らない（ユーザーの Git 管理意図を尊重） |

## エラー時の伝搬

`agents/<name>.sh` の exit code は `PIPELINE_EXIT` に保持され、最終的に exit に使われる。
途中ステップが失敗してもエラー内容を含む JSON / Markdown が極力残るよう、各ステップの exit code は個別に捕捉する。

## 依存スクリプト

| スクリプト | 用途 |
|----------|------|
| `agents/<name>.sh` | agent 本体実行 |
| `bin/translate-json.sh` | 翻訳 |
| `bin/save-ask-log.sh` | Markdown 化 |

## 依存コマンド

| コマンド | 用途 |
|---------|------|
| `git` | リポジトリルート取得（任意） |

`agents/<name>.sh` / `translate-json.sh` / `save-ask-log.sh` の依存はそれぞれの仕様書を参照。

## 関連ドキュメント

- [internals/ask-pipeline-flow.md](../internals/ask-pipeline-flow.md) — 全体フロー図
- [save-ask-log.md](save-ask-log.md)
- [translate-json.md](translate-json.md)
