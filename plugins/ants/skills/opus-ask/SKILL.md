---
name: opus-ask
description: >-
  Claude Code CLI (claude -p) + Opus モデルを使い、1問1答形式で Opus に質問する。
  session_id を使った会話継続に対応。
  ユーザーが「opusに聞いて」「opus ask」「opus-ask」「opusで調べて」と言った場合に使用。

  argument: "[session_id=<UUID>] [output_dir=<path>] <質問>"
allowed-tools: Bash
context: fork
model: sonnet
---

## 手順

### 1. 入力解釈

`ARGUMENTS` から以下を読み取る。

- `session_id=<UUID>` / `セッション <UUID>` が含まれる → `--session-id <UUID>` を付加
- `output_dir=<path>` が含まれる → `--output-dir <path>` を付加
- 残りをメッセージとして使用

### 2. パイプライン実行

```bash
${CLAUDE_PLUGIN_ROOT}/skills/_shared-bin/ask-pipeline.sh \
  --skill opus-ask \
  [--session-id "<SESSION_ID>"] \
  [--output-dir "<OUTPUT_DIR>"] <<'EOF'
<メッセージ>
EOF
```

パイプラインを実行するとログファイルのパスが表示される

### 3. 返却

```
ログファイル: <LOG_PATH>
```

---

## 制約

- session_id を推測で補わない
- コードの修正は行わない
