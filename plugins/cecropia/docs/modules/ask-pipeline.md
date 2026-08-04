# ask-pipeline

`claude-ask` / `claude-review` の共通実行パイプライン。
agent から呼ばれ、AI 実行・ログ生成・ファイル配置の一連の処理を順に実行する。

## 基本情報

| 項目 | 値 |
|---|---|
| 実装 | `bin/ask-pipeline.py` |

## 引数

| オプション | 必須 | 説明 |
|---|---|---|
| `--agent <name>` | 必須 | 実行する agent 名（`claude-ask` / `claude-review`） |
| `--message <text>` | 必須（または stdin） | 送信メッセージ |
| `--session-id <UUID>` | 省略可 | セッション継続時に指定 |
| `--lock-prefix <text>` | 省略可 | 排他ロックキーのプレフィックス。省略時は `--agent` の値を使用 |
| `--output-dir <PATH>` | 省略可 | ログの配置先ディレクトリ |
| `--inject-fixed-prompt` | 省略可 | agent 固有の固定プロンプト（役割定義・観点など、内容は agent 実装次第）を message の先頭へ明示的に付加する。`build_prompt(message, session_id, inject_fixed_prompt=...)` に伝搬される。引数を受け取らない agent ではフラグは無視される |

## パイプライン

### Step 0: プレースホルダー配置

agent 実行前に、ファイル名（`<timestamp>_<project>_<agent>`）を確定する。
`agents/<agent>.py` の `build_prompt` を動的 import して実際に送信するプロンプト（固定プロンプト含む）を取得し、answer を「処理中...」とした pending JSON を生成する。
`build_prompt` が `inject_fixed_prompt` 引数を受け付ける場合は、`--inject-fixed-prompt` の指定値がそのまま渡される（受け付けない場合は無視され、現行シグネチャ `(message, session_id)` で呼び出される）。
`save-ask-log.py` でその JSON から Markdown を生成し、出力先ディレクトリに配置する（プレースホルダー）。
プレースホルダーは Step 2 で同名ファイルに上書きされる。

### Step 1: agent 実行

`agents/<agent>.py` を `--message`、`--session-id`（指定時）、`--inject-fixed-prompt`（指定時）を渡して実行する。
agent は API 呼び出しのみを担い、結果（session_id・answer・status・exit_code・error_detail）を JSON 形式で stdout に返す。
ask-pipeline がその JSON を受け取り、Step 0 と同じパスに最終 JSON を書き込む。

### Step 2: Markdown ログ生成・上書き

`save-ask-log.py` で JSON を Markdown ログに変換し、`<tempdir>/<model>-ask/<timestamp>_<project>_<agent>.md` に保存する。
Step 0 で配置したプレースホルダーを同名の完成 Markdown で上書きする。
Markdown の上書き後、Step 1 の中間 JSON ファイルを削除する。

各ステップの失敗は個別に捕捉し、可能な限り後続を継続する。
agent が結果を返せなかった場合はプレースホルダーを削除して終了する。

## ログの配置先

`--output-dir` 省略時は git リポジトリルート（リポジトリ外ならカレントディレクトリ）配下の `.llm-ask/` に配置する。
相対パスを渡した場合も同じ基準ディレクトリからの相対パスになる。新規作成時のみ `*` を対象とした `.gitignore` を配置する。

## 中間ファイル

Step 1 で生成される JSON ファイルは、Step 2 の Markdown 生成後に削除される。

## 排他ロック

`--session-id` が指定された場合、`${CLAUDE_PLUGIN_DATA}/locks/<lock_prefix>_<session_id>.lock` を取得してから処理を開始する。`<lock_prefix>` は `--lock-prefix` で指定した値、省略時は `--agent` の値。同じロックを取得済みのプロセスが存在する場合、後発プロセスはエラーで即終了する。

`--lock-prefix` を使うと複数の agent を同一ロックキーでグループ化できる。例えば `claude-ask` と `claude-review` に `--lock-prefix claude` を指定すると、同じ session_id を持つ両者の同時実行が防止される。

※ ロックは OS レベルの file lock（POSIX: `fcntl.flock`、Windows: `LockFileEx`）で実装されており、プロセスが kill されても OS が自動解放する。
