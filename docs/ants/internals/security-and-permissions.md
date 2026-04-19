# セキュリティと権限

ants のスキル・スクリプトが扱う権限と、信頼できない入力に対する取り扱いをまとめる。

## allowed-tools の方針

各スキルの SKILL.md では、必要最小限のツールのみを `allowed-tools` として宣言する。

| スキル | allowed-tools | 補足 |
|-------|--------------|------|
| `codex-ask` / `codex-review` | `Bash` | パイプライン起動のみ |
| `opus-ask` / `opus-review` | `Bash` | 同上 |
| `get-pr-info` | `Bash` | `gh` コマンド呼び出し |
| `export-session` | `Bash` | `python3` 呼び出し |
| `plant-uml` | `Bash, Read` | スクリプト呼び出し + 入力ファイル読み |
| `create-pr` | `Bash, Read, Glob` | テンプレート探索・本文生成 |
| `create-skill` | `Read, Write, Bash, Glob, Grep, Edit` | SKILL.md 生成 |

## バックエンド側のツール制限

`*-ask` / `*-review` のバックエンド（`run-*.sh`）では、`claude -p` / `codex exec` の起動方法に応じて許可範囲が異なる。

| スクリプト | 制限方式 | 備考 |
|----------|---------|------|
| `run-codex-ask.sh` | Codex CLI の `--full-auto` 実行。CLI レベルの `--tools` 制限はなく、書き込み禁止はプロンプトで指示する | 信頼できないリポジトリでは注意 |
| `run-codex-review.sh` | 同上。固定プロンプトで「修正禁止」を加えて指示する | 同上 |
| `run-opus-ask.sh` | `claude -p --tools "Read, Glob, Grep, Bash, WebSearch, WebFetch"`（Write/Edit を除外） | CLI レベルで許可ツールを限定 |
| `run-opus-review.sh` | `claude -p --tools "Read, Glob, Grep, Bash"`（Write/Edit/Web を除外、手元コード集中） | 同上 |

## --dangerously-skip-permissions の取り扱い

`run-opus-ask.sh` / `run-opus-review.sh` / `translate-json.sh` は `claude -p --dangerously-skip-permissions` を使用する。

### 使用理由

- fork セッションでユーザーに権限プロンプトを出せないため
- パイプライン全体を非対話で完走させる必要があるため

### リスク

- 信頼できない入力（リポジトリ内の悪意あるファイル、外部 PR 本文など）に含まれる指示が、許可されたツール経由で副作用を持つ可能性
- 特に `Bash` を許可している `run-opus-review.sh` ではプロンプトインジェクションのリスクがある

### 軽減策

- 許可ツールを必要最小限に絞る（`Write`/`Edit` を意図的に除外）
- レビュー系では「コードの修正は行わない」固定プロンプトを冒頭に付加
- 信頼できないリポジトリでの実行は避ける（README の「既知の問題」にも明記）

## CLAUDECODE 環境変数の扱い

ネスト呼び出し（Claude Code 内から `claude -p` を呼ぶ）時の不整合を避けるため、`run-opus-*.sh` / `translate-json.sh` は実行前に以下を unset する：

```bash
unset CLAUDECODE CLAUDE_CODE_ENTRYPOINT 2>/dev/null || true
```

## ファイル出力先と機密情報

ask パイプラインの最終出力（Markdown ログ）はリポジトリ配下の `.llm-ask/` に保存される。

- 新規作成時のみ `*` のみの `.gitignore` を同梱（Git 管理対象外）
- 既存ディレクトリには触らない（ユーザーの Git 管理意図を尊重）

`export-session` の出力は `/tmp/claude-sessions/` 配下に保存される。
`get-pr-info` の出力は `/tmp/pull-requests/` 配下に保存される。
`/tmp` の取り扱いはシステム依存だが、原則として再起動で消える前提で扱う。

## 翻訳の送信内容

`translate-json.sh` は `answer` フィールドの内容を Claude API（Haiku）に送信する。バックエンドの回答に機密情報が含まれる場合、それも翻訳のために外部に送信されることに注意。

## 関連ドキュメント

- [ask-pipeline-flow.md](ask-pipeline-flow.md) — パイプライン全体
- [shellscripts/translate-json.md](../shellscripts/translate-json.md) — 翻訳の詳細
- [skills/opus-review.md](../skills/opus-review.md) — `Bash` 許可によるリスク
