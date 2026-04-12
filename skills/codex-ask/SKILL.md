---
name: codex-ask
description: OpenAI Codex CLI をバックエンドとして使い、1問1答形式で Codex に質問する。session_id を使った会話継続に対応。ユーザーが「codexに聞いて」「codex ask」「codex-ask」「codexで調べて」と言った場合に使用。
argument-hint: "<質問> [session_id=<UUID>]"
allowed-tools: Bash
---

## 手順

### 1. 入力解釈

`$ARGUMENTS` から以下を読み取る。

- `session_id=<UUID>` / `セッション <UUID>` が含まれる → `--session-id <UUID>` を付加
- 残りをメッセージとして使用

### 2. パイプライン実行

```bash
LOG_PATH=$(${CLAUDE_PLUGIN_ROOT}/skills/_shared-bin/ask-pipeline.sh \
  --skill codex-ask \
  [--session-id "<SESSION_ID>"] <<'EOF'
<メッセージ>
EOF
)
```

### 3. 返却

```
ログ: <LOG_PATH>
```

---

## 制約

- `~/.codex/auth.json` などの内容を表示しない
- session_id を推測で補わない
- コードの修正は行わない
