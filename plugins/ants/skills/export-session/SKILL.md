---
name: export-session
description: >-
  Claude Code のセッション会話全文を Markdown ファイルにエクスポートする。
  ユーザーが「セッションをエクスポート」「export-session」と言った場合に使用。

  argument: "session_id=<UUID|current> | list [--cwd]"
allowed-tools: Bash
context: fork
model: haiku
---

## 手順

### 1. 入力解釈

`$ARGUMENTS` から以下を読み取る。

- `list` が含まれる → セッション一覧を表示
- `session_id=<UUID>` が含まれる → 指定セッションをエクスポート
- `session_id=current` が含まれる → 現在のセッションをエクスポート
- `--cwd` が含まれる（list 時）→ 現在のディレクトリのセッションに限定
- `session_id` の指定がない場合 → エラーを返す（必須）

### 2. 実行

**セッション一覧表示**:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/export_session.py" list [--cwd]
```

**エクスポート**:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/export_session.py" <session_id|current>
```

### 3. 返却

スクリプトの出力（ファイルパスとサイズ）をそのまま返す。Markdown 本文は出力しない。

---

## 制約

- `CLAUDE_SESSION_ID` 環境変数が未設定の場合、`current` は使用できない（session-start フックが必要）
- ファイルの読み取りや編集は行わない
