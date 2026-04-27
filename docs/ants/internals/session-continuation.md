# セッション継続

ants の `*-ask` / `*-review` agent が、別セッションの AI（Codex / Opus）と複数ターンの会話を続けるためのメカニズム。

## 基本方針

- ユーザーまたは親エージェントが明示的に `session_id=<UUID>` を指定したときのみ、継続セッションとして扱う

## 取得元

各 agent の初回（`session_id` 指定なし）実行時、バックエンドから生成された UUID を中間 JSON の `session_id` フィールドに記録する。
最終 Markdown ログには「セッションID」として表示される。

## 受け渡し

```
1. 初回呼び出し
   親セッションの LLM が Agent ツール経由で codex-ask を起動（prompt: "質問テキスト"）
   → Markdown ログに セッションID: 12345... が記録される

2. ユーザーがログを確認

3. 継続呼び出し
   親セッションの LLM が Agent ツール経由で codex-ask を起動（prompt: "session_id=12345... 追加の質問"）
   → 同じセッションの続きとして実行される
```

## バックエンド別の取り回し

### Codex

```bash
# 初回
codex --ask-for-approval never exec --skip-git-repo-check --sandbox read-only --full-auto --json -o <out> -

# 継続（exec オプションは resume サブコマンドの前に置く）
codex --ask-for-approval never exec --skip-git-repo-check --sandbox read-only --full-auto --json resume <SESSION_ID> -o <out> -
```

セッション ID は JSONL 出力から以下で抽出する：

```bash
jq -r 'select(.type == "thread.started") | .thread_id' <jsonl>
```

### Opus（Claude Code CLI）

```bash
# 初回
claude -p --output-format json --model Opus ...

# 継続
claude -p --output-format json --model Opus --resume <SESSION_ID> ...
```

セッション ID は JSON 出力から `.session_id` で抽出する。

## 抽出失敗時の挙動

| 状況 | 値 |
|-----|-----|
| 初回実行で抽出失敗 | `session_id: "unresolved"` |
| 継続実行で抽出失敗 | 元の `--session-id` 引数値にフォールバック |

`unresolved` がログに記録された場合、その後継続セッションを開けないため、新規セッションとして再実行する必要がある。

## モード判定

中間 JSON の `mode` フィールドは `--session-id` 引数の有無で決まる：

| `--session-id` | `mode` |
|---------------|--------|
| なし | `new` |
| あり | `continuation` |

## レビュー系の固定プロンプト

`*-review` agent では、新規セッション時のみ固定プロンプト（出力ルール・デフォルト 10 観点・修正禁止）を冒頭に付加する。継続セッションでは付加しない（バックエンド側に既に文脈が残っているため）。

これにより、継続レビューでは既存の会話脈を維持したまま追質問できる。

## 関連ドキュメント

- [ask-pipeline-flow.md](ask-pipeline-flow.md) — パイプライン全体
- [log-format.md](log-format.md) — `session_id` を含むログスキーマ
