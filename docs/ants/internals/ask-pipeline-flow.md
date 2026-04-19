# ask パイプライン全体フロー

`codex-ask` / `codex-review` / `opus-ask` / `opus-review` の 4 スキルが共通で使う処理フローをまとめる。

個別スクリプトの仕様は [shellscripts/ask-pipeline.md](../shellscripts/ask-pipeline.md) / [shellscripts/save-ask-log.md](../shellscripts/save-ask-log.md) / [shellscripts/translate-json.md](../shellscripts/translate-json.md) を参照。

## 全体図

```
親セッション
  │
  │ 1. /ants:<skill> 呼び出し
  ▼
fork セッション（スキル本体、SKILL.md 実行）
  │
  │ 2. ARGUMENTS 解釈
  │ 3. Bash ツールでフォアグラウンド実行（timeout は最大値）
  ▼
ask-pipeline.sh
  │
  │ 4. run-<skill>.sh 実行
  ▼
run-<skill>.sh
  │ 5. codex / claude バックエンド呼び出し
  │ 6. 中間 JSON 生成 → /tmp/<model>-ask/<basename>.json
  ▼
ask-pipeline.sh
  │ 7. translate-json.sh で answer フィールドを翻訳
  │    → /tmp/<model>-ask/<basename>.translated.json
  │ 8. save-ask-log.sh で Markdown 化
  │    → /tmp/<model>-ask/<basename>.md
  │ 9. 中間 JSON 削除（成功時）
  │10. 出力ディレクトリ（<repo>/.llm-ask）にコピー
  ▼
fork セッション
  │11. stdout 最終行から Markdown ログのパス取得
  ▼
親セッション
   12. 「ログファイル: <PATH>」を受け取る（ask 系）
       または「レビューログを読んでユーザに返す」指示を受け取る（review 系）
```

## ステップ詳細

### 1. スキル呼び出し

ユーザーが `/ants:codex-ask <message>` のようにスキルを起動。Claude Code は SKILL.md を fork セッションで実行する。

### 2. ARGUMENTS 解釈

SKILL.md に書かれた手順に従い、`session_id` / `output_dir` / メッセージ本文を抽出する。

### 3. Bash 実行（フォアグラウンド）

`ask-pipeline.sh` を Bash ツールでフォアグラウンド実行する。長時間化する可能性があるため、Bash の timeout は最大値に設定する。Skill 使用時のバックグラウンド実行には不具合らしき挙動が報告されているため、必ずフォアグラウンドで実行する。

### 4. run スクリプト解決

`ask-pipeline.sh` は `--skill <name>` から `${SHARED_BIN}/../<name>/bin/run-<name>.sh` を解決する。

### 5. バックエンド呼び出し

| skill | バックエンド | コマンド形式 |
|-------|------------|------------|
| `codex-ask` / `codex-review` | OpenAI Codex CLI | `codex exec [resume <ID>] --full-auto --json -o <out> -` |
| `opus-ask` / `opus-review` | Claude Code CLI | `claude -p --output-format json --model Opus [--resume <ID>] --dangerously-skip-permissions --tools <...>` |

### 6. 中間 JSON 生成

`run-<skill>.sh` は実行結果を JSON として保存する（スキーマは [log-format.md](log-format.md) 参照）。エラー時もエラー内容を含む JSON を生成し、stdout にパスを出力する。

### 7. 翻訳

`translate-json.sh <JSON> answer` で `answer` フィールドを Haiku 経由で日本語に翻訳。既に日本語ならそのままコピーされる。失敗時は WARN を出して原文のまま続行（パイプライン全体は止まらない）。

### 8. Markdown 化

`save-ask-log.sh <JSON>` で人間可読な Markdown ログに変換する。レイアウトは [log-format.md](log-format.md) 参照。

### 9. 中間 JSON の削除

Markdown ログが生成できた場合、元 JSON と翻訳後 JSON を削除する。Markdown ログのみが最終成果物として残る。

### 10. 出力ディレクトリへのコピー

| `--output-dir` | 出力先 |
|---------------|--------|
| 未指定 | `<repo>/.llm-ask`（git 外なら `$PWD/.llm-ask`） |
| 絶対パス | そのまま |
| 相対パス | `<repo>/<path>`（git 外なら `$PWD/<path>`） |

新規作成時のみ、`*` のみの `.gitignore` を同梱する（既存ディレクトリには触らない）。

### 11. 親への返却

fork セッションは stdout 最終行から Markdown ログのパスを取得し、親に返す。

- ask 系：`ログファイル: <LOG_PATH>` をそのまま返す
- review 系：「レビューログを読んでユーザに結果を返してください」という指示テンプレートを返す（親が Markdown を読んでユーザーに整形提示する）

## エラー伝搬

各ステップは exit code を個別に捕捉し、最終的に `PIPELINE_EXIT` として伝搬する。エラーが起きてもエラー内容を含む JSON / Markdown が極力残るようになっている。

| 失敗箇所 | 動作 |
|---------|------|
| `run-<skill>.sh` 自体の起動失敗 | パイプライン中断、exit 1 |
| バックエンド実行失敗 | エラー JSON 生成、`status: error` で続行 |
| 翻訳失敗 | WARN を出して原文 JSON のまま続行 |
| Markdown 化失敗 | パイプライン中断、exit 1 |
| コピー失敗 | パイプライン中断（`set -uo pipefail` で `cp` の失敗を捕捉） |

## 関連ドキュメント

- [shellscripts/ask-pipeline.md](../shellscripts/ask-pipeline.md)
- [shellscripts/save-ask-log.md](../shellscripts/save-ask-log.md)
- [shellscripts/translate-json.md](../shellscripts/translate-json.md)
- [log-format.md](log-format.md)
- [session-continuation.md](session-continuation.md)
