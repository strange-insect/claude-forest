# DESIGN-POLICY

## クロスプラットフォーム対応

Windows（Git Bash）/ macOS / Linux（Ubuntu）の3環境で動作することを前提とする。

shell script は標準コマンドのみを使用し、`jq` や `sed` の高度な利用など環境依存になりやすい処理は Python に移譲する。Python は `python` / `conda` / `pyenv` をサポートし、環境ごとの違いを `python-wrapper.sh` が吸収する。

## subagent / skill（context: fork）内の Bash はフォアグラウンド実行のみ

subagent / skill（`context: fork`）内での Bash バックグラウンド実行は、subagent / skill の終了と同時にプロセスが kill されるため結果を取得できない。
そのため Bash 実行は必ずフォアグラウンドで行う。この制約により、1 回の Bash 実行のタイムアウト上限は 10 分となる。

## ログ保存ディレクトリの .gitignore

`opus-ask` / `opus-review` / `codex-ask` / `codex-review` のログ保存先ディレクトリ（`.llm-ask/`）を新規作成する際は、`*` を対象とした `.gitignore` を配置して git 管理対象外とする。ディレクトリが既に存在する場合は、元の git 管理ポリシーを尊重して `.gitignore` を作成・変更しない。

## 大量出力はファイルに保存してパスのみ返す

agent の出力が親セッションのコンテキストを圧迫しないよう、大量のテキストを生成する処理（AI の回答・PR 情報・セッションエクスポート等）は結果をファイルに保存し、親セッションにはパスのみを返す。必要な部分は呼び出し側が `Read` ツールで取り込む。

## コンテキスト分離には subagent を使用する

skill の `context: fork` は現時点では記憶（メッセージ履歴）を引き継がないが、将来の Claude Code アップデートで挙動が変わる可能性がある。
挙動の安定性を保つため `context: fork` は使用せず、コンテキスト分離が必要な処理は subagent（Agent ツール経由）として実装する。
