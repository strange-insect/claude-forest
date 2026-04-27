# save-ask-log.sh 仕様書

`agents/<name>.sh` が生成する中間 JSON を、人間可読な Markdown ログに変換する。

## 配置

```
plugins/ants/bin/save-ask-log.sh
```

## 呼び出し方

```bash
save-ask-log.sh <json-file-path>
```

## 入力

JSON ファイルパス。スキーマは [internals/log-format.md](../internals/log-format.md) を参照。

| フィールド | 用途 |
|----------|------|
| `model` / `type` / `mode` / `session_id` | メタ情報 |
| `timestamp` / `directory` / `project` | 実行コンテキスト |
| `message` / `answer` | 質問・回答本文 |
| `status` / `exit_code` | 実行結果 |

## 出力

stdout に、生成した Markdown ファイルの絶対パスを出力する。

## 保存先

| `model` | 保存ディレクトリ |
|---------|----------------|
| `codex` | `${TMPDIR:-/tmp}/codex-ask` |
| `opus` | `${TMPDIR:-/tmp}/opus-ask` |
| その他 | `${TMPDIR:-/tmp}/<model>-ask` |

## ファイル名

入力 JSON のベース名から `.json` および `.translated` サフィックスを除いたものに `.md` を付ける。

例：`codex-ask_proj_20260412_123456.translated.json` → `codex-ask_proj_20260412_123456.md`

## 生成される Markdown のレイアウト

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

| フィールド | ラベル変換 |
|----------|----------|
| `model: codex` | `Codex` |
| `model: opus` | `Opus` |
| `type: ask` | `Ask` |
| `type: review` | `Review` |

## 終了コード

| コード | 意味 |
|-------|------|
| 0 | 成功 |
| 1 | エラー（`jq` 未インストール、引数不正、JSON ファイル不在） |

## 依存コマンド

| コマンド | 用途 |
|---------|------|
| `jq` | JSON フィールド抽出 |

## 関連ドキュメント

- [internals/log-format.md](../internals/log-format.md) — JSON / Markdown のスキーマ詳細
- [ask-pipeline.md](ask-pipeline.md) — 上位パイプライン
