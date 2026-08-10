---
name: opencode-export-session
description: |-
  opencode のセッション会話全文を Markdown ファイルにエクスポートする。
  ユーザーが「opencodeのセッションをエクスポート」「opencode-export-session」と言った場合に使用。
  対象セッション ID は `opencode-ask` / `opencode-review` / `opencode-task` が返した session_id、
  または list モードで取得したセッション ID を指定する。

  呼び出しプロンプト形式:
  - export モードの場合: "session_id=<text>"
  - list モードの場合:   "list [--cwd]"

  session_id [export モードで REQUIRED]:
  - エクスポート対象の opencode セッション ID（`ses_` で始まる文字列）

  list [list モードで REQUIRED]:
  - このリテラルを含めると list モードに入る（利用可能なセッション一覧を表示する）

  `--cwd` [list モード OPTIONAL]:
  - 指定するとカレントディレクトリのセッションのみに絞る
  - 未指定時は全ディレクトリを対象に、最新10件のセッションを返す
tools: Bash
model: sonnet
---

## 手順

**環境またはツールの問題で手順が遂行できない場合はその旨を応答し処理を終了する。代替手段での作業続行は禁止する。**

### 1. 引数の解釈

呼び出し prompt の文字列を以下の順で判定し、スクリプトに渡す第1引数（`<TARGET>`）を決定する。

1. `list` を含む → `<TARGET>` は `list`（呼び出し prompt に `--cwd` があれば `--cwd` も追加で付加）
2. `session_id=` の指定あり → `<TARGET>` はセッションID
3. いずれにも一致しない → 実行せず、引数が不正である旨を返して終了する

### 2. コマンド実行

判定結果に応じて、以下を Bash ツールで1回だけ実行する。
`CLAUDE_PLUGIN_ROOT` と `CLAUDE_PLUGIN_DATA` は additionalContext で提供された値を使用し、コマンド実行時に環境変数として export する。

```bash
export CLAUDE_PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}"
export CLAUDE_PLUGIN_DATA="${CLAUDE_PLUGIN_DATA}"
"${CLAUDE_PLUGIN_ROOT}/bin/python-wrapper.sh" "${CLAUDE_PLUGIN_ROOT}/agents/opencode-export-session.py" <TARGET> [--cwd]
```

`--cwd` は `<TARGET>` が list の場合のみ付加する。

共通 wrapper `bin/python-wrapper.sh` が確定済みの Python で `opencode-export-session.py` を起動する。

### 3. 返却

スクリプトの stdout をそのままユーザーに返す（ファイルパスとサイズ）。Markdown 本文は展開・要約しない。

---

## 制約

- ファイルの読み取りや編集は行わない
