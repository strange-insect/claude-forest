---
name: export-session
description: >-
  Claude Code のセッション会話全文を Markdown ファイルにエクスポートする。
  ユーザーが「セッションをエクスポート」「export-session」と言った場合に使用。
  現在のセッションIDは`CLAUDE_SESSION_ID`環境変数から取得しsession_idに指定すること。

  呼び出しプロンプト形式:
  - export モードの場合: "session_id=<text>"
  - list モードの場合:   "list [--cwd]"

  session_id [export モードで REQUIRED]:
  - エクスポート対象のセッション ID
  - 現在のセッションをエクスポートする場合は `CLAUDE_SESSION_ID` 環境変数の値を指定する

  list [list モードで REQUIRED]:
  - このリテラルを含めると list モードに入る（利用可能なセッション一覧を表示する）

  `--cwd` [list モード OPTIONAL]:
  - 指定するとカレントディレクトリのセッションのみに絞る
  - 未指定時は全プロジェクトを対象に、最新10件のセッションを返す
tools: Bash
model: sonnet
---

## 手順

### 1. 引数の解釈

呼び出し prompt の文字列を以下の順で判定し、スクリプトに渡す第1引数（`<TARGET>`）を決定する。

1. `list` を含む → `<TARGET>` は `list`（呼び出し prompt に `--cwd` があれば `--cwd` も追加で付加）
2. `session_id=` の指定あり → `<TARGET>` はセッションID
3. いずれにも一致しない → 実行せず、引数が不正である旨を返して終了する

### 2. コマンド実行

判定結果に応じて、以下を Bash ツールで1回だけ実行する。

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/agents/export-session.py" <TARGET> [--cwd]
```

`--cwd` は `<TARGET>` が list の場合のみ付加する。

### 3. 返却

スクリプトの stdout をそのままユーザーに返す（ファイルパスとサイズ）。Markdown 本文は展開・要約しない。

---

## 制約

- ファイルの読み取りや編集は行わない
