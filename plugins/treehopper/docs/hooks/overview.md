# hooks

3 つのフックを提供する。いずれも agent が正しく動作するための基盤となる。

## 一覧

| フック | タイミング | 目的 |
|---|---|---|
| `SessionStart` | セッション開始時 | `CLAUDE_SESSION_ID` を環境変数として後続プロセスに継承させる |
| `SubagentStart` | subagent 起動時 | `CLAUDE_PLUGIN_ROOT` / `CLAUDE_PLUGIN_DATA` を additionalContext 経由で subagent に伝える |
| `PreToolUse` | Agent ツール呼び出し前 | ペアリング済みの場合、指定外のセッション ID での `opencode-ask` / `opencode-review` / `opencode-worker` 呼び出しをブロックする |

## SessionStart

セッション開始時に発火し、`CLAUDE_SESSION_ID` を `CLAUDE_ENV_FILE` 経由で後続の subprocess に継承させる。

## SubagentStart

subagent 起動時に発火し、`CLAUDE_PLUGIN_ROOT` と `CLAUDE_PLUGIN_DATA` を `additionalContext` として subagent に渡す。
これらの値は入力コンテキストの一部としてsubagentに伝えられるもので、環境変数として設定されるわけではない。

※ Windows パスの `\` は JSON 出力時に `\\` にエスケープされる。

## PreToolUse（opencode-pairing）

`opencode-pairing` agent によるペアリング実行後に有効になる。

`opencode-ask` / `opencode-review` / `opencode-worker` の Agent 呼び出し時に発火し、プロンプトにペアリング済みの opencode セッション ID が含まれているかを検証する。含まれていない場合は呼び出しをブロックし、正しい Session ID を通知する。

ペアリングファイル（`$CLAUDE_PLUGIN_DATA/opencode-pairing.txt`）が存在しない、または現在の `CLAUDE_SESSION_ID` に対応するエントリがない場合はブロックしない。
