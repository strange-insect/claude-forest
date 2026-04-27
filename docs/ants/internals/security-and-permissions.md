# セキュリティと権限

ants の agent / skill / スクリプトが扱う権限と、信頼できない入力に対する取り扱いをまとめる。

## tools の方針

各 agent / skill の定義ファイルでは、必要最小限のツールのみを宣言する（agent は `tools` フィールド、skill は `allowed-tools` フィールド）。

### Agent 一覧

| agent | 宣言ツール | 補足 |
|-------|-----------|------|
| `codex-ask` / `codex-review` | `Bash` | パイプライン起動のみ |
| `opus-ask` / `opus-review` | `Bash` | 同上 |
| `get-pr-info` | `Bash` | `gh` コマンド呼び出し |
| `export-session` | `Bash` | `python3` 呼び出し |
| `plant-uml` | `Bash, Read` | スクリプト呼び出し + 入力ファイル読み |

### Skill 一覧

| skill | 宣言ツール | 補足 |
|-------|-----------|------|
| `create-pr` | `Bash, Read, Glob` | テンプレート探索・本文生成 |
| `create-skill` | `Read, Write, Bash, Glob, Grep, Edit` | SKILL.md 生成 |

## バックエンド側の built-in ツールセット

`*-ask` / `*-review` のバックエンド（`agents/<name>.sh`）では、`claude -p` / `codex exec` の起動方法に応じて利用可能な built-in ツールセットが異なる。Claude Code CLI の `--tools` は **利用可能な built-in ツールセット** を限定する（permission の許可リストを意味する `--allowed-tools` とは別）。

| スクリプト | 制限方式 | 備考 |
|----------|---------|------|
| `codex-ask.sh` | `codex --ask-for-approval never exec --sandbox read-only --full-auto --json` で実行。書き込み禁止は CLI 側 `--sandbox read-only` で担保する（少なくとも model-generated shell command による書き込みは拒否される。公式 help の保証範囲はそこまで） | プロンプトでのガード文は付けない |
| `codex-review.sh` | 同上。新規セッション時のみ固定プロンプトでレビュー出力ルール・10 観点・「修正禁止」の振る舞いを指示する | プロンプト側のガードは振る舞い指示のみで、書き込み制御は CLI 任せ |
| `opus-ask.sh` | `claude -p --tools "Read,Glob,Grep,Bash,WebSearch,WebFetch"` で起動。`Write`/`Edit` を built-in ツールセットから除外する | `Bash` を許可しているため、`bash -c 'cat > file'` 経由の書き込みは可能。信頼できないリポジトリでは使用しない |
| `opus-review.sh` | `claude -p --tools "Read,Glob,Grep,Bash"` で起動。`Write`/`Edit`/`WebSearch`/`WebFetch` を built-in ツールセットから除外する（手元コード集中） | 同上の `Bash` 経由の書き込みリスクあり |

## --dangerously-skip-permissions の取り扱い

`opus-ask.sh` / `opus-review.sh` / `translate-json.sh` は `claude -p --dangerously-skip-permissions` を使用する。

### 使用理由

- subagent でユーザーに権限プロンプトを出せないため
- パイプライン全体を非対話で完走させる必要があるため

### リスク

- 信頼できない入力（リポジトリ内の悪意あるファイル、外部 PR 本文など）に含まれる指示が、許可されたツール経由で副作用を持つ可能性
- 特に `Bash` を許可している `opus-review.sh` ではプロンプトインジェクションのリスクがある

### 軽減策

- built-in ツールセットを必要最小限に絞る（`Write`/`Edit` を意図的に除外）。ただし `Bash` 経由の書き込みまでは塞げない
- レビュー系では「コードの修正は行わない」固定プロンプトを冒頭に付加
- 信頼できないリポジトリでの実行は避ける（README の「既知の問題」にも明記）

## CLAUDECODE 環境変数の扱い

ネスト呼び出し（Claude Code 内から `claude -p` を呼ぶ）時の不整合を避けるため、`opus-*.sh` / `translate-json.sh` は実行前に以下を unset する：

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
- [agents/opus-review.md](../agents/opus-review.md) — `Bash` 許可によるリスク
