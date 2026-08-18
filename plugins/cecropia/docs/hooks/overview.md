# hooks

6 つのフックを提供する。agent や skill が正しく動作するための基盤と、Bash 実行環境の整備、エージェントの停止判定を行う。

## 一覧

| フック | タイミング | 目的 |
|---|---|---|
| `SessionStart` | セッション開始時 | `CLAUDE_SESSION_ID` を環境変数として後続プロセスに継承させる |
| `SessionStart`（direnv） | セッション開始時 | `.envrc` を direnv で評価し、得られた環境変数を後続の Bash 実行に継承させる |
| `SessionStart`（development-guidelines） | セッション開始時 | 開発ガイドラインを `additionalContext` としてセッションに注入する |
| `SubagentStart` | subagent 起動時 | `CLAUDE_PLUGIN_ROOT` / `CLAUDE_PLUGIN_DATA` を additionalContext 経由で subagent に伝える |
| `PreToolUse` | Agent ツール呼び出し前 | ペアリング済みの場合、指定外のセッション ID での `claude-ask` / `claude-review` 呼び出しをブロックする |
| `Stop` | エージェントの応答終了時 | 作業宣言・続行確認だけで停止した場合に、停止をブロックして処理を続行させる |

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

## SessionStart（development-guidelines）

セッション開始時に `agents/development-guidelines.txt` を `additionalContext` としてセッションに注入する。実装・修正時に開発ガイドラインを適用するための機能である。

開発ガイドラインはソースコード、ソースコード上のコメント、ドキュメント、全体構成、AIエージェントによる不正行為の各区分を持ち、遵守事項を示す形式で記述する。

### 無効化

環境変数 `CLAUDEFOREST_DISABLE_DEVELOPMENT_GUIDELINES` に空文字以外を設定すると、何も出力せず終了する。

### 適用範囲

このフックは cecropia が提供する。

## SubagentStart

subagent 起動時に発火し、`CLAUDE_PLUGIN_ROOT` と `CLAUDE_PLUGIN_DATA` を `additionalContext` として subagent に渡す。
これらの値は入力コンテキストの一部としてsubagentに伝えられるもので、環境変数として設定されるわけではない。

※ Windows パスの `\` は JSON 出力時に `\\` にエスケープされる。

## PreToolUse（claude-pairing）

`claude-pairing` agent によるペアリング実行後に有効になる。

`claude-ask` / `claude-review` の Agent 呼び出し時に発火し、プロンプトにペアリング済みの Claude セッション ID が含まれているかを検証する。含まれていない場合は呼び出しをブロックし、正しい Session ID を通知する。

ペアリングファイル（`$CLAUDE_PLUGIN_DATA/claude-pairing.txt`）が存在しない、または現在の `CLAUDE_SESSION_ID` に対応するエントリがない場合はブロックしない。

## Stop（auto-continue）

エージェントが応答を終えてユーザの入力待ちに戻るときに発火する。最後の発話が次のいずれかで終わっている場合、停止をブロックして処理を続行させる。

- 「これから〇〇します」という作業宣言だけで、実行せずに停止している
- 選択肢を伴わない、単なる続行確認で停止している
- 作業量が多いことを理由に、続行を確認している、または分割・中断・別途実施を推奨して停止している

判定は `bin/auto-continue.py` が行い、次の順に処理する。

| ステップ | 内容 |
|---|---|
| 1 | `stop_hook_active` が真なら何もしない（block による再停止でループしないようにする） |
| 2 | 実行中のバックグラウンドタスクがあれば何もしない |
| 3 | 実行中の subagent があれば何もしない |
| 4 | Haiku に `continue` / `stop` を判定させる |
| 5 | `continue` を含み、かつ `stop` を含まない場合のみ block を返す |

block 時の出力は次の固定内容である。

```json
{"decision": "block", "reason": "ユーザからの停止指示はありません。処理を続行するか、停止する **必要がある** 場合はその理由を説明してください。"}
```

判定対象の発話は payload の `last_assistant_message` から取得する。

### バックグラウンドタスクの検出

payload の `background_tasks` が空かどうかで判定する。この配列には実行中のタスクだけが列挙される。

```json
[{"id": "bs3ojygq9", "type": "shell", "status": "running",
  "description": "sleep 120", "command": "sleep 120"}]
```

### subagent の検出

subagent は `background_tasks` に現れないため、transcript から判定する。対象は、非同期に起動して実行中のものと、`SendMessage` によって再開されて実行中のものである。

| 事象 | transcript 上の記録 |
|---|---|
| 起動 | `Agent` の `tool_use` に対し、`toolUseResult.status` が `async_launched` の `tool_result` が返る |
| 完了 | `<tool-use-id>` を含む task-notification が届く |
| 再開 | `SendMessage` の結果に `toolUseResult.resumedAgentId` が返る。以降の完了通知は、その `SendMessage` の tool-use-id で届く |

`toolUseResult` は `tool_result` ブロックではなく、それを含む transcript レコードのトップレベルに位置する。

task-notification は `user` メッセージの本文文字列、または attachment として記録される。通知は `completed` / `failed` / `stopped` / `killed` のいずれの結果でも届くため、`status` は判定に用いない。

停止した subagent は `SendMessage` によって再開されるため、起動・再開・完了は時系列の状態遷移として処理する。

### 判定の委譲

判定は `claude -p --safe-mode --model haiku --max-turns 1` を別プロセスとして起動して行う。`--safe-mode` は子プロセス側のプラグインとフックを無効化するため、このフック自身が再帰的に起動することはない。

`claude` が PATH に無い場合、および判定結果が `continue` を含まない、または `continue` と `stop` の両方を含む場合は何も出力せず、エージェントはそのまま停止する。

### 制約

`stop_hook_active` によるループ防止のため、連続した自動継続は 1 回までとなる。継続後の応答が再び作業宣言で終わった場合、2 回目は発火しない。
