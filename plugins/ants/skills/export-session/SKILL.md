---
name: export-session
description: Claude Code のセッション会話全文を Markdown ファイルにエクスポートする。ユーザーが「セッションをエクスポート」「export-session」と言った場合に使用。
argument-hint: "[session_id|current|list] [--cwd]"
allowed-tools: Bash
---

## 手順

### 1. 入力解釈

`$ARGUMENTS` から以下を読み取る。

- `list` が含まれる → セッション一覧を表示
- UUID 形式の文字列が含まれる → 指定セッションをエクスポート
- `--cwd` が含まれる（list 時）→ 現在のディレクトリのセッションに限定
- 何も指定なし → `current` として現在のセッションをエクスポート

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
