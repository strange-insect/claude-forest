---
name: opus-ask
description: >-
  Claude Code CLI (claude -p) + Opus モデルを使い、1問1答形式で別セッションの Opus と会話する。
  session_id を使った会話継続に対応するため、複数ターンの会話/議論や追加指示も可能。
  ユーザーが「opusに聞いて」「opus ask」「opus-ask」「opusで調べて」と言った場合に使用。

  argument: "[session_id=<UUID>] [output_dir=<path>] <メッセージ>"
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

依頼した作業の規模によっては応答に数分以上の時間がかかるため、タイムアウト値を最大にしてフォアグラウンド実行する。
Skill使用時のバックグラウンド実行には不具合らしき挙動が報告されているため必ずフォアグラウンドで実行すること。

```bash
${CLAUDE_PLUGIN_ROOT}/skills/_shared-bin/ask-pipeline.sh \
  --skill opus-ask \
  [--session-id "<SESSION_ID>"] \
  [--output-dir "<OUTPUT_DIR>"] <<'EOF'
<メッセージ>
EOF
```

### 3. 返却

```
ログファイル: <LOG_PATH>
```

---

## 制約

- session_id を推測で補わない
- コードの修正は行わない
