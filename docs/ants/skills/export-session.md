# export-session スキル仕様書

Claude Code のセッション会話全文を Markdown ファイルにエクスポートする。

## 基本情報

| 項目 | 値 |
|-----|-----|
| スキル名 | `export-session` |
| 呼び出し方式 | `/ants:export-session session_id=<UUID>` または `/ants:export-session list [--cwd]` |
| 実行コンテキスト | `context: fork`（子セッションで実行） |
| 使用モデル | `haiku` |
| 結果 | スクリプトの stdout（ファイルパスとサイズ）をそのままユーザーに返す |

## ユーザーが呼ぶタイミング

- 現在のセッションの全会話を Markdown として保存したい
- 過去のセッション一覧を確認したい
- 特定のセッション ID から会話を Markdown 化したい

現在のセッション ID は `CLAUDE_SESSION_ID` 環境変数（[hooks/overview.md](../hooks/overview.md) 参照）から取得して `session_id=` に渡す。

## 入力引数

`ARGUMENTS` の文字列を以下の順で判定する。

1. `list` を含む → セッション一覧を表示。`--cwd` があればカレントディレクトリのセッションのみに絞る
2. `session_id=<UUID>` の形式で UUID らしき文字列を含む → その UUID のセッションを Markdown 化
3. いずれにも一致しない → 引数不正として終了

## 処理フロー

1. `ARGUMENTS` を判定し、第 1 引数（`<TARGET>`）を決定
2. 以下のコマンドを 1 回だけ実行：
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/export_session.py" <TARGET> [--cwd]
   ```
3. スクリプトの stdout をそのまま返す（Markdown 本文の展開・要約はしない）

## 出力

エクスポート時：保存先ファイルパスとサイズ。
リスト時：セッション一覧。

### エクスポート Markdown のフォーマット

Assistant ターンの見出しには、そのターンで応答したモデル名（JSONL の `message.model`）が括弧で付加される。

```markdown
### Assistant (claude-opus-4-7)
*2026-04-19 12:34:56 UTC*

本文...
```

モデル情報が無いレコードでは `### Assistant` にフォールバックする。

## エラー時の処理

| エラー | 動作 |
|-------|--------|
| 引数不正 | 不正である旨を返して終了 |
| 該当セッションなし | スクリプトのエラーをそのまま返す |

## 制約

- ファイルの読み取り・編集は行わない
- 出力の Markdown 本文をスキル側で解釈・要約しない（フォーマットを壊さないため）

## 依存コマンド

| コマンド | 用途 |
|---------|------|
| `python3` | エクスポート処理本体 |

## 関連ドキュメント

- [hooks/overview.md](../hooks/overview.md) — `CLAUDE_SESSION_ID` の永続化
