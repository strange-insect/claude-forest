# hooks

4 つのフックを提供する。agent や skill が正しく動作するための基盤と、Bash 実行環境の整備を行う。

## 一覧

| フック | タイミング | 目的 |
|---|---|---|
| `SessionStart` | セッション開始時 | `CLAUDE_SESSION_ID` を環境変数として後続プロセスに継承させる |
| `SessionStart`（direnv） | セッション開始時 | `.envrc` を direnv で評価し、得られた環境変数を後続の Bash 実行に継承させる |
| `SubagentStart` | subagent 起動時 | `CLAUDE_PLUGIN_ROOT` / `CLAUDE_PLUGIN_DATA` を additionalContext 経由で subagent に伝える |
| `PreToolUse` | Agent ツール呼び出し前 | ペアリング済みの場合、指定外のセッション ID での `claude-ask` / `claude-review` 呼び出しをブロックする |

## SessionStart

セッション開始時に発火し、`CLAUDE_SESSION_ID` を `CLAUDE_ENV_FILE` 経由で後続の subprocess に継承させる。

これにより `export-session` agent が「現在のセッション」を参照できるようになる。

## SessionStart（direnv-load）

セッション開始時に `direnv export bash` を実行し、その出力を `CLAUDE_ENV_FILE` に追記する。これにより `.envrc` で定義した環境変数が Bash ツールの実行時に読み込まれる。

`CLAUDE_ENV_FILE` はシェルとして source されるため、`direnv export bash` が出力する `export FOO=$'...';` 形式をそのまま追記できる。

### 安全性

| 状況 | 動作 |
|---|---|
| direnv が PATH に無い | 何もせず終了する |
| `.envrc` が未 allow | direnv はユーザー定義の変数を出力しないため、環境変数は設定されない。`direnv allow` が必要 |
| `.envrc` の読み込みに失敗 | 環境変数は設定されない。`additionalContext` で対処方法をセッションに伝える |
| `.envrc` が存在しない | 追記される内容が無く、環境は変わらない |

いずれの場合も `exit 0` で終了し、後続処理を止めない。

`direnv export bash` が非 0 で終了した場合を「読み込み失敗」として扱う。hook が知り得るのは終了コードだけで原因は特定できないため、通知は `direnv allow` の案内に限定せず、direnv 側のエラー確認も促す内容にしている。

非 0 になるのは未 allow のほか、`.envrc` 内で `strict_env` を有効にしたうえで未定義変数を参照した場合や、`.envrc` が非 0 で終了した場合である。なお `.envrc` 内のコマンドが失敗した場合や構文エラーがある場合、direnv は 0 で終了し、成功した分の変数だけを出力する（この場合 hook は通知しない）。明示的に `direnv deny` した場合も 0 で終了するため、通知の対象外となる。

### 制約

セッション開始時に 1 回だけ評価する。セッション中に `.envrc` を変更した場合や、別の `.envrc` を持つディレクトリへ移動した場合は反映されない。反映するにはセッションを開始し直す。

direnv 連携は Linux / macOS での利用を想定している。Windows（Git Bash）では未検証である。direnv が PATH に無い環境では何もせず終了するため、未インストールでもセッションの動作に影響はない。

## SubagentStart

subagent 起動時に発火し、`CLAUDE_PLUGIN_ROOT` と `CLAUDE_PLUGIN_DATA` を `additionalContext` として subagent に渡す。
これらの値は入力コンテキストの一部としてsubagentに伝えられるもので、環境変数として設定されるわけではない。

※ Windows パスの `\` は JSON 出力時に `\\` にエスケープされる。

## PreToolUse（claude-pairing）

`claude-pairing` agent によるペアリング実行後に有効になる。

`claude-ask` / `claude-review` の Agent 呼び出し時に発火し、プロンプトにペアリング済みの Claude セッション ID が含まれているかを検証する。含まれていない場合は呼び出しをブロックし、正しい Session ID を通知する。

ペアリングファイル（`$CLAUDE_PLUGIN_DATA/claude-pairing.txt`）が存在しない、または現在の `CLAUDE_SESSION_ID` に対応するエントリがない場合はブロックしない。
