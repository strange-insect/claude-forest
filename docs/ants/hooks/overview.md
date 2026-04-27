# Hook 仕様書

ants は Claude Code の hook メカニズムを使用してセッション開始時に環境変数を設定する。

## 目的

ants の一部 agent（`export-session` など）は現在のセッション ID を必要とする。Claude Code の `SessionStart` フックで `session_id` を環境変数化することで、後続の呼び出しから参照できるようにする。

## Hook の種類と実行タイミング

### SessionStart フック

| 項目 | 値 |
|-----|-----|
| 実行タイミング | Claude Code セッション開始直後（一度のみ） |
| タイムアウト | 10 秒 |
| 失敗時動作 | `exit 0` で終了（セッション実行は継続、非ブロッキング） |
| 実装ファイル | `hooks/session-start.sh` |
| 設定ファイル | `hooks/hooks.json` |

## SessionStart フックの処理

### 1. session_id の取得

Claude Code から渡される JSON（stdin）から `session_id` を抽出する。

```bash
INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
```

### 2. 環境変数の永続化

`session_id` が取得できて `CLAUDE_ENV_FILE` が設定されている場合、`CLAUDE_SESSION_ID` をその環境ファイルに書き込む。

```bash
if [[ -n "$SESSION_ID" && -n "${CLAUDE_ENV_FILE:-}" ]]; then
  echo "CLAUDE_SESSION_ID=$SESSION_ID" >> "$CLAUDE_ENV_FILE"
fi
```

`CLAUDE_ENV_FILE` は Claude Code が用意する環境変数の永続化先。書き込まれた値は以後の agent / skill 実行で `${CLAUDE_SESSION_ID}` として参照できる。

## Hook 失敗時の動作

`set -euo pipefail` で実行されるが、最終的には `exit 0` で終了する。検証失敗・JSON パース失敗などがあってもセッションは止まらない。

| 状態 | 動作 |
|-----|------|
| `session_id` が空 | 何もせず exit 0 |
| `CLAUDE_ENV_FILE` が未設定 | 何もせず exit 0 |
| `jq` 未インストール | スクリプトが中断、exit 0 で終わらず非ゼロ終了の可能性あり |

`jq` の有無は SessionStart で検証していないため、未インストール環境では他の依存先が呼び出された時点でエラーになる。

## `CLAUDE_SESSION_ID` のライフサイクル

`CLAUDE_SESSION_ID` の値は Claude Code セッションのライフサイクルに連動する。SessionStart は「Claude Code が新しいセッションを開始した時点」で発火するため、以下のような挙動になる。

| イベント | `CLAUDE_SESSION_ID` の値 |
|---------|--------------------------|
| Claude Code 起動（新規セッション） | 新しい session_id が設定される |
| Claude Code 再起動 | 再起動時に SessionStart が再発火し、新しい session_id が設定される |
| `/compact` 実行 | 値は引き継がれる（compact が発生してもセッション ID は変わらない） |
| subagent の独立コンテキスト | 値は引き継がれない（subagent は別 session_id で動くため、`CLAUDE_SESSION_ID` を参照しても親セッションの ID は得られない） |

### subagent での取り扱い

subagent として動く agent（`export-session` など）から親セッションの ID を扱いたい場合は、親セッションが `CLAUDE_SESSION_ID` を読み取って prompt 引数として明示的に渡す必要がある。subagent 側で `$CLAUDE_SESSION_ID` を参照しても、それは subagent 自体の ID（または未定義）になる。

例：`export-session` の agents/export-session.md は親セッションに対して「現在のセッションIDは `CLAUDE_SESSION_ID` 環境変数から取得し `session_id=` に指定すること」と指示している。これは、親セッションが値を解決してから subagent へ prompt 引数で渡す前提による。

## 利用先

`CLAUDE_SESSION_ID` を参照する agent の代表：

- [export-session](../agents/export-session.md) — `session_id=$CLAUDE_SESSION_ID` で現在セッションをエクスポート

## Hook の設計理由

### 非ブロッキング設計

検証失敗時にセッションを止めない理由：

- ants はオプション機能（コア Claude Code とは独立）
- 他プラグインの操作を妨げない
- ユーザーが選択的に対応可能

### 環境変数による受け渡し

セッション ID を毎回引数で渡す代わりに環境変数化する理由：

- 全 agent / skill で共通に必要になる可能性がある情報を、呼び出し側の負担なく参照できる
- ユーザーが `$CLAUDE_SESSION_ID` を手動入力する手間を省く

## 関連ドキュメント

- [agents/export-session.md](../agents/export-session.md) — `CLAUDE_SESSION_ID` を利用する agent
