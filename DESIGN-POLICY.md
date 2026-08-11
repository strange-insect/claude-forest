# DESIGN-POLICY

## クロスプラットフォーム対応

Windows（Git Bash）/ macOS / Linux（Ubuntu）の3環境で動作することを前提とする。

shell script は標準コマンドのみを使用し、`jq` や `sed` の高度な利用など環境依存になりやすい処理は Python に移譲する。Python は `python` / `conda` / `pyenv` をサポートし、環境ごとの違いを `python-wrapper.sh` が吸収する。

## subagent / skill（context: fork）内の Bash はフォアグラウンド実行のみ

subagent / skill（`context: fork`）内での Bash バックグラウンド実行は、subagent / skill の終了と同時にプロセスが kill されるため結果を取得できない。
そのため Bash 実行は必ずフォアグラウンドで行う。この制約により、1 回の Bash 実行のタイムアウト上限は 10 分となる。

## 外部 AI CLI 連携 agent の書き込み権限

外部 AI CLI を呼び出す agent は、読み取り専用の `*-ask` / `*-review` と、ワークスペースを変更する `*-task` に分離する。ユーザーが書き込みを明示的に意図した場合のみ task 系を呼び出す構成とし、ask / review 系が副作用を起こさないことを担保する。

読み取り専用を担保する手段は CLI ごとに異なり、強制力にも差がある。

| agent | CLI | 指定 | 強制力 |
| --- | --- | --- | --- |
| `codex-ask` / `codex-review` | codex | `--sandbox read-only` | CLI のサンドボックスによる強制 |
| `claude-ask` / `claude-review` | claude | `--tools` による許可リスト（`--dangerously-skip-permissions` 併用） | 許可リストに `Bash` を含むため、シェル経由の書き込みまでは防げない |
| `opencode-ask` / `opencode-review` | opencode | `--agent plan` | plan エージェントが `edit` を既定 `deny` |

task 系は書き込みを許可するため、担保手段も CLI ごとに異なる。

| agent | CLI | 指定 | 書き込み範囲 |
| --- | --- | --- | --- |
| `codex-task` | codex | `--sandbox workspace-write` | OS レベルのサンドボックスにより、ワークスペース外への書き込みは遮断される |
| `opencode-task` | opencode | `--agent build --auto` | `--auto` は明示的に `deny` されていない権限要求をすべて承認するため、ファイル編集に限らず外部コマンドの実行や作業ディレクトリ外への副作用も発生し得る |

いずれも非対話実行では権限確認プロンプトに応答できないため、承認なしに実行される挙動は意図的なものである。

## ログ保存ディレクトリの .gitignore

`claude-ask` / `claude-review` / `codex-ask` / `codex-review` / `opencode-ask` / `opencode-review` / `opencode-task` / `codex-task` のログ保存先ディレクトリ（`.llm-ask/`）を新規作成する際は、`*` を対象とした `.gitignore` を配置して git 管理対象外とする。ディレクトリが既に存在する場合は、元の git 管理ポリシーを尊重して `.gitignore` を作成・変更しない。

## 大量出力はファイルに保存してパスのみ返す

agent の出力が親セッションのコンテキストを圧迫しないよう、大量のテキストを生成する処理（AI の回答・PR 情報・セッションエクスポート等）は結果をファイルに保存し、親セッションにはパスのみを返す。必要な部分は呼び出し側が `Read` ツールで取り込む。

## コンテキスト分離には subagent を使用する

skill の `context: fork` は現時点では記憶（メッセージ履歴）を引き継がないが、将来の Claude Code アップデートで挙動が変わる可能性がある。
挙動の安定性を保つため `context: fork` は使用せず、コンテキスト分離が必要な処理は subagent（Agent ツール経由）として実装する。

## 共通モジュールはプラグイン間で同一内容とする

複数プラグインが同名で持つモジュール（`bin/python-wrapper.sh` / `bin/ask-pipeline.py` / `bin/save-ask-log.py` / `bin/_runtime_check.py` / `agents/_ask_common.py` / `hooks/session-start.sh` / `hooks/subagent-start.sh`）は、全プラグインで同一内容とする。

これらは汎用的な機能として設計し、プラグイン固有の機能や設定をこれらのモジュールに持ち込まない。
固有の変更が必要になる場合、設計が間違っているので共通部品と固有機能の分割設計を見直す。
