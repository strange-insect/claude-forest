---
name: export-session
description: >-
  Claude Code のセッション会話全文を Markdown ファイルにエクスポートする。
  ユーザーが「セッションをエクスポート」「export-session」と言った場合に使用。
  現在のセッションIDは`CLAUDE_SESSION_ID`環境変数から取得しsession_idに指定すること。

  argument: "session_id=<UUID> | list [--cwd]"
allowed-tools: Bash
context: fork
model: haiku
---

## 手順

### 1. 引数の解釈

`ARGUMENTS` の文字列を以下の順で判定し、スクリプトに渡す第1引数（`<TARGET>`）を決定する。

1. `list` を含む → `<TARGET>` は `list`（`ARGUMENTS` に `--cwd` があれば `--cwd` も追加で付加）
2. `session_id=` の後ろに UUID らしき文字列を含む → `<TARGET>` は抽出した UUID
3. いずれにも一致しない → 実行せず、引数が不正である旨を返して終了

### 2. コマンド実行

判定結果に応じて、以下を Bash ツールで1回だけ実行する。

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/export_session.py" <TARGET> [--cwd]
```

`--cwd` はルール 1 の場合のみ付加する。

### 3. 返却

スクリプトの stdout をそのままユーザーに返す（ファイルパスとサイズ）。Markdown 本文は展開・要約しない。

---

## 制約

- ファイルの読み取りや編集は行わない
