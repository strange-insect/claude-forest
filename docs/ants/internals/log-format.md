# ログフォーマット

ask パイプラインの中間 JSON と最終 Markdown ログのスキーマをまとめる。

## 中間 JSON

`agents/<name>.sh` が生成し、`save-ask-log.sh` が読み込む共通スキーマ。

### スキーマ

```json
{
  "model":      "codex" | "opus",
  "type":       "ask" | "review",
  "mode":       "new" | "continuation",
  "session_id": "<UUID>" | "unresolved",
  "timestamp":  "YYYY-MM-DD HH:MM:SS",
  "directory":  "<実行時の CWD>",
  "project":    "<basename of CWD>",
  "message":    "<ユーザー指示テキスト>",
  "answer":     "<バックエンドの回答>",
  "status":     "success" | "error",
  "exit_code":  0
}
```

### フィールド詳細

| フィールド | 型 | 説明 |
|----------|---|------|
| `model` | string | `codex` または `opus`。バックエンドを表す |
| `type` | string | `ask` または `review`。agent 種別を表す |
| `mode` | string | `new` または `continuation`。`session_id` 指定の有無で決まる |
| `session_id` | string | バックエンドから抽出したセッション ID。失敗時は `unresolved` |
| `timestamp` | string | JSON 生成時刻 |
| `directory` | string | agent 実行時の絶対パス |
| `project` | string | `directory` の basename |
| `message` | string | バックエンドに実際に送信したプロンプト全体。review 系で新規セッション時には固定プロンプト（役割指示・出力ルール・10 観点）+ ユーザー指示文の連結が記録される（継続セッションではユーザー指示文のみ）。意図しない応答が返ってきた際の検証用に「システムが自動付与した部分」も含めて全文を保持する |
| `answer` | string | バックエンドの回答。エラー時はエラー詳細を含むテキスト |
| `status` | string | `success` または `error` |
| `exit_code` | number | バックエンドの exit code |

### session_id の抽出

| バックエンド | 抽出方法 |
|------------|---------|
| Codex | JSONL 出力から `select(.type == "thread.started") \| .thread_id` |
| Opus | `claude -p --output-format json` の出力から `.session_id` |

抽出に失敗した場合は `unresolved`。継続セッション時は元の `--session-id` 引数値にフォールバックする。

### 翻訳後 JSON

`translate-json.sh <JSON> answer` を通すと、`answer` フィールドが日本語化された `<basename>.translated.json` が生成される。スキーマは元と同じ。

## Markdown ログ

`save-ask-log.sh` が中間 JSON から生成する人間可読な Markdown。

### ファイル名

入力 JSON のベース名から `.json` および `.translated` サフィックスを除いたものに `.md` を付ける。

例：`opus-review_proj_20260412_123456.translated.json` → `opus-review_proj_20260412_123456.md`

### 保存先

| `model` | 保存ディレクトリ |
|---------|----------------|
| `codex` | `${TMPDIR:-/tmp}/codex-ask` |
| `opus` | `${TMPDIR:-/tmp}/opus-ask` |

`ask-pipeline.sh` はこれを更に出力ディレクトリ（`<repo>/.llm-ask`）にコピーする。

### レイアウト

```markdown
# <Label> <Type> Log

- **日時**: <timestamp>
- **モード**: <mode>
- **ディレクトリ**: <directory>
- **セッションID**: <session_id>
- **ステータス**: エラー (exit code: <code>)   ← status=error の場合のみ

---

## メッセージ

<message>

---

## <Label> の回答

<answer>
```

### ラベル変換

| 元の値 | 表示 |
|-------|------|
| `model: codex` | `Codex` |
| `model: opus` | `Opus` |
| `type: ask` | `Ask` |
| `type: review` | `Review` |

## 出力ディレクトリ構成

`ask-pipeline.sh` がコピーする最終出力先：

```
<repo>/.llm-ask/
  ├── .gitignore                        # 内容は "*"（新規作成時のみ自動生成）
  ├── codex-ask_proj_20260412_120000.md
  ├── codex-review_proj_20260412_130000.md
  ├── opus-ask_proj_20260412_140000.md
  └── opus-review_proj_20260412_150000.md
```

`.gitignore` は新規作成時のみ同梱され、既存ディレクトリには追加されない。

## 関連ドキュメント

- [ask-pipeline-flow.md](ask-pipeline-flow.md) — パイプライン全体
- [shellscripts/save-ask-log.md](../shellscripts/save-ask-log.md)
- [shellscripts/translate-json.md](../shellscripts/translate-json.md)
- [session-continuation.md](session-continuation.md) — `session_id` の取り回し
