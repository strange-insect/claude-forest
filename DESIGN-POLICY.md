# DESIGN-POLICY

## オーバーエンジニアリングの禁止

必要かどうか判断できない処理は作らない。必要になった時点で、そのとき判明した要求とともに足す。

### 要求から導けない処理を実装しない

実装する処理は、すべて要求のどこから導かれるかを説明できること。説明できない処理は実装しない。

### 発生ルートを辿れない事象へ備えない

その事象が起こる経路をコード上で示せない場合、対応は不要である。
「念のため」「万一に備えて」の防御的な処理を作らない。

経路を示せる事象は、まだ観測していなくても対応の対象である。

### 発生確率、発生時の実害が低いエラーに対する過剰防御をしない

その事象が発生してもリトライすれば済む、エラー応答をしなくてもエラーの発生が呼び出し元に伝わるなど
実害が低いエラーに対する過剰な防御による複雑化を避ける。

### 他が責務を持つ機能を再実装しない

- 上位のフレームワークやハーネスが担保する排他制御・プロセス管理・再試行
- 呼び出し元が守る前提の契約を、呼び出し先で二重に検証する処理
- 規定されていない操作順序への対応

### 同じ問題に対する対策を二重に持たない

### 実需要の無い拡張性のための抽象化を行わない

## クロスプラットフォーム対応

Windows（Git Bash）/ macOS / Linux（Ubuntu）の3環境で動作することを前提とする。

shell script は標準コマンドのみを使用し、`jq` や `sed` の高度な利用など環境依存になりやすい処理は Python に移譲する。Python は `python` / `conda` / `pyenv` をサポートし、環境ごとの違いを `python-wrapper.sh` が吸収する。

## subagent / skill（context: fork）内の Bash はフォアグラウンド実行のみ

subagent / skill（`context: fork`）内での Bash バックグラウンド実行は、subagent / skill の終了と同時にプロセスが kill されるため結果を取得できない。
そのため Bash 実行は必ずフォアグラウンドで行う。この制約により、1 回の Bash 実行のタイムアウト上限は 10 分となる。

一方でこれは、**subagent が生きている間は子プロセスも生き続ける**ことの裏返しでもある。
そのため、1 回の Bash 実行の中で完結させる必要があるのは「結果の取得」だけであり、
subagent が生存する限りプロセス自体は Bash 実行をまたいで保持できる。
`*-task` の常駐ワーカーはこの性質を利用している（後述）。プロセスをデタッチしてはならない。
デタッチすると subagent の終了に巻き込まれなくなり、ワーカーが孤児として残る。

## 外部 AI CLI 連携 agent の書き込み権限

外部 AI CLI を呼び出す agent は、読み取り専用の `*-ask` / `*-review` と、ワークスペースを変更する `*-task` に分離する。ユーザーが書き込みを明示的に意図した場合のみ task 系を呼び出す構成とし、ask / review 系が副作用を起こさないことを担保する。

読み取り専用を担保する手段は CLI ごとに異なり、強制力にも差がある。

| agent | CLI | 指定 | 強制力 |
| --- | --- | --- | --- |
| `codex-ask` / `codex-review` | codex | `--sandbox read-only` | CLI のサンドボックスによる強制 |
| `claude-ask` / `claude-review` | claude | `--tools` による許可リスト（`--dangerously-skip-permissions` 併用） | 許可リストに `Bash` を含むため、シェル経由の書き込みまでは防げない |
| `opencode-ask` / `opencode-review` | opencode | `--agent plan` | plan エージェントが `edit` を既定 `deny` |

task 系は書き込みを許可するため、担保手段も CLI ごとに異なる。

task 系は steering に対応するため常駐形態で起動する。書き込み許可の指定もその形態に合わせている。

| agent | CLI の起動形態 | 指定 | 書き込み範囲 |
| --- | --- | --- | --- |
| `codex-task` | `codex app-server` | `thread/start` の `sandbox: workspace-write` | OS レベルのサンドボックスにより、ワークスペース外への書き込みは遮断される |
| `claude-task` | `claude -p --input-format stream-json` | `--tools` に `Write` / `Edit` を追加（`--dangerously-skip-permissions` 併用） | 許可リストに `Bash` を含むため、ファイル編集に限らず外部コマンドの実行や作業ディレクトリ外への副作用も発生し得る |
| `opencode-task` | `opencode serve` | セッション作成時の `permission` を全許可、`agent: build` | 明示的に `deny` されていない権限要求をすべて承認するため、ファイル編集に限らず外部コマンドの実行や作業ディレクトリ外への副作用も発生し得る |

いずれも非対話実行では権限確認プロンプトに応答できないため、承認なしに実行される挙動は意図的なものである。
codex は承認要求そのものを `approvalPolicy: never` で無効化している。

## ログ保存ディレクトリの .gitignore

`claude-ask` / `claude-review` / `claude-task` / `codex-ask` / `codex-review` / `codex-task` / `opencode-ask` / `opencode-review` / `opencode-task` のログ保存先ディレクトリ（`.llm-ask/`）を新規作成する際は、`*` を対象とした `.gitignore` を配置して git 管理対象外とする。ディレクトリが既に存在する場合は、元の git 管理ポリシーを尊重して `.gitignore` を作成・変更しない。

## `CLAUDE_PLUGIN_DATA` は永続データ専用とし、作業領域には使わない

`CLAUDE_PLUGIN_DATA` に置いてよいのは、**実行をまたいで保持する必要があるデータだけ**とする。

| 用途 | 置き場 | 例 |
| --- | --- | --- |
| 実行をまたいで保持する | `${CLAUDE_PLUGIN_DATA}` | Python venv、インストール済み requirements のスナップショット |
| 単一の実行の間だけ必要 | `<tempdir>`（`tempfile.gettempdir()`） | run の状態、中間 JSON、ログの下書き |

実行ごとに生成される作業データは OS の一時領域に置き、**役目を終えた時点で削除する**。
永続領域に作業データを置くと、掃除する主体がいないまま実行のたびに残り、際限なく肥大化する。
削除する前に、残す価値のある情報は `.llm-ask/` のログなど恒久的な出力へ転記する。

## 大量出力はファイルに保存してパスのみ返す

agent の出力が親セッションのコンテキストを圧迫しないよう、大量のテキストを生成する処理（AI の回答・PR 情報・セッションエクスポート等）は結果をファイルに保存し、親セッションにはパスのみを返す。必要な部分は呼び出し側が `Read` ツールで取り込む。

## コンテキスト分離には subagent を使用する

skill の `context: fork` は現時点では記憶（メッセージ履歴）を引き継がないが、将来の Claude Code アップデートで挙動が変わる可能性がある。
挙動の安定性を保つため `context: fork` は使用せず、コンテキスト分離が必要な処理は subagent（Agent ツール経由）として実装する。

## `*-task` は実行中のワーカーへ追加指示を伝達する

メインエージェントから `*-task` subagent に届いた追加指示を、実行中のワーカーへ原文のまま伝達する。
伝達には各 CLI のネイティブ API を使用する。

| CLI | 伝達手段 |
| --- | --- |
| codex | `app-server` の `turn/steer` |
| claude | Streaming Input への user message 追加投入 |
| opencode | `serve` の `prompt_async` |

この伝達を成立させるために、次の 2 点が技術的な制約から導かれる。

- ワーカーは Bash 呼び出しをまたいで生かし続ける必要がある。codex と claude は stdio で
  会話し続けるため接続そのものを、opencode は HTTP サーバのプロセスを保持する。
  いずれも subagent の子プロセスとして常駐させる。
- subagent は完了待ちを短く刻む。刻まないと、その間 指示を受け取れない。

保持の対象と完了検知の方法は CLI ごとに異なるが、
`bin/` の共通モジュールと backend の契約は全プラグインで統一する。

## 共通モジュールはプラグイン間で同一内容とする

複数プラグインが同名で持つモジュール（`bin/python-wrapper.sh` / `bin/ask-pipeline.py` / `bin/save-ask-log.py` / `bin/_ask_log.py` / `bin/_runtime_check.py` / `bin/task-control.py` / `bin/task-supervisor.py` / `bin/_task_run_store.py` / `agents/_ask_common.py` / `agents/development-guidelines.txt` / `hooks/session-start.sh` / `hooks/subagent-start.sh`）と、CLI ごとに名前が異なるレビュー観点定義（`agents/*-review-guidelines.txt`）・作業報告形式の定義（`agents/*-task-guidelines.txt`）は、全プラグインで同一内容とする。

CLI 固有の差異は steering backend（`agents/_steer_<cli>.py`）に閉じ込める。

これらは汎用的な機能として設計し、プラグイン固有の機能や設定をこれらのモジュールに持ち込まない。
固有の変更が必要になる場合、設計が間違っているので共通部品と固有機能の分割設計を見直す。

## レビュー観点と開発ガイドラインは同じ指針を示す

レビュー観点定義（`agents/*-review-guidelines.txt`）と開発ガイドライン（`agents/development-guidelines.txt`）は、同じ指針をレビュー時と実装時のそれぞれに適用するための文書である。一方を変更した場合はもう一方にも反映し、示す指針が食い違わないよう同期する。
