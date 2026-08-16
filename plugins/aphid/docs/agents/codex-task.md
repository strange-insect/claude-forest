# codex-task

OpenAI Codex CLI にファイルの変更などを含む作業を依頼し、作業報告を Markdown ログファイルに保存する。
**作業の実行中に追加の指示を渡せる**のがこの agent の特徴。

## 基本情報

| 項目 | 値 |
|---|---|
| agent 名 | `codex-task` |
| 実装 | `bin/task-control.py` + `bin/task-supervisor.py` + `agents/_steer_codex.py` |
| 使用モデル | `sonnet` |
| 実行コンテキスト | subagent（独立コンテキスト） |
| Codex の起動形態 | `codex app-server` |

## トリガーフレーズ

- 「codexに作業させて」
- 「codexで実装して」

## 呼び出し形式

```
[session_id=<SESSION_ID>] [reinject_guideline=<true|false>] [model=<MODEL>] [effort=<EFFORT>] instruction=<作業指示>
```

### 引数

| 引数 | 必須 | 説明 |
|---|---|---|
| `instruction=<作業指示>` | 必須 | Codex に依頼する作業内容。原文のまま渡す |
| `session_id=<SESSION_ID>` | 省略可 | 指定すると以前の作業を継続する |
| `model=<MODEL>` | 省略可 | 使用するモデル。**ユーザーが明示的に指定した場合のみ渡す** |
| `effort=<EFFORT>` | 省略可 | reasoning effort。**ユーザーが明示的に指定した場合のみ渡す** |
| `reinject_guideline=<true\|false>` | 省略可 | 固定プロンプト（作業報告の形式指定）を先頭に付加するか。初回は値に関わらず付加される |

実行中の指示のための引数は無い。`SendMessage` の自由文で送る（次節）。

## 実行中の指示

`codex-task` を**バックグラウンドで起動**し、実行中に `SendMessage` でメッセージを送る。

```
Agent(codex-task, "instruction=...", run_in_background: true)
    ↓ ユーザーから追加の指示
SendMessage(codex-task, "refresh token は触らず、cookie の SameSite 設定を先に疑って")
    ↓
subagent が原文のまま Codex へ turn/steer で投入する
```

フォアグラウンドで起動した場合、メインエージェントは subagent の完了までブロックされるため
指示を渡せない。途中で指示を追加する可能性がある作業は必ずバックグラウンドで起動する。

投入した指示を Codex が読むのは**次のツール実行の境界**である。
長時間のコマンド（テスト実行など）が走っている最中に送っても、そのコマンドが終わるまでは反映されない。

`steer` は指示を Codex へ投入できたかどうかが確定するまで戻らない。作業が既に終わっていた場合は
投入されずに失敗を返し、subagent が呼び出し元にその旨を伝える。

## 実行モデル

```
メインエージェント
  │ Agent(codex-task, ..., run_in_background: true)
  │      … SendMessage …
  ▼
codex-task subagent
  │ 1. task-control.py start            → 作業を開始する
  │ 2. task-control.py wait              を反復
  │      ← スライスとスライスの間で SendMessage が届く
  │ 3. task-control.py steer            届いたメッセージを Codex へ伝達
  │ 4. wait がログパスを返したら終了
  ▼
task-supervisor.py（subagent の子プロセス）
  ▼  JSON-RPC (stdio)
codex app-server
```

`wait` は 60 秒のスライスで刻む。subagent はフォアグラウンドの Bash に入っている間
メッセージを受け取れないため、スライスを長くすると指示を渡せない時間が延びる。

supervisor は subagent の子プロセスであり、subagent の終了に伴って一緒に終了する。
作業が終わった時点でログを書き出し、ワーカーを終了する。

## 親セッションへの応答

```
ログファイル: <絶対パス>

Codex の作業結果を出力しました。ログに記載されたエージェントからの作業報告、実際のファイル差分などを確認しユーザに報告してください。
```

Codex が作業ディレクトリを変更している可能性があるため、ログの作業報告と実際のファイル差分を確認してユーザに報告するよう呼び出し元に促す文言を添えて返す。

## ログファイル

### 保存先

ログは git リポジトリルート（リポジトリ外ならカレントディレクトリ）配下の `.llm-ask/` に保存される。保存先は変更できない。
`.llm-ask/` フォルダを新規作成するときは `*` を対象とした `.gitignore` が自動生成される。
`.llm-ask/` フォルダが既に存在する場合は `.gitignore` の作成/編集は行われない。

### 構成

| セクション | 内容 |
|---|---|
| ヘッダー | 日時・モード（new / continuation）・ディレクトリ・セッション ID |
| メッセージ | 送信した作業指示の原文 |
| Codex の回答 | Codex からの作業報告（固定プロンプトで指定した形式） |
| エラー情報 | エラー時のみ |

ログファイル名のパターン：`<YYYYMMDD_HHMMSS_mmm>_<プロジェクト名>_codex-task.md`

ログに記録されるのは Codex の**報告テキスト**であり、実際のファイル変更内容ではない。変更の実体は作業ディレクトリに直接反映されるため、`git status --short --untracked-files=all` / `git diff` で確認する。

### session_id による作業継続

ログの `セッションID` 欄に記録されている ID を次回呼び出しの `session_id` に渡すと、同じ Codex スレッドで作業を続けられる。
`session_id` は `codex-ask` / `codex-review` とも共通で使用可能。

## OpenAI Codex CLI 実行引数

`codex app-server` を起動し、JSON-RPC で以下を送る。

| リクエスト | 指定 |
|---|---|
| `thread/start` | `cwd`（作業ディレクトリ）/ `sandbox: workspace-write` / `approvalPolicy: never` / `model` |
| `turn/start` | `input`（作業指示）/ `effort` |
| `turn/steer` | `threadId` / `expectedTurnId` / `input`（実行中の指示） |

`session_id` を指定した場合は `thread/start` の代わりに `thread/resume` を使う。

`codex app-server` は Codex CLI 側で `[experimental]` と位置づけられている。
プロトコルが変更された場合は `agents/_steer_codex.py` の追従が必要になる。

### 固定プロンプト（作業報告の形式指定）

Codex の作業報告は形式が定まらないと呼び出し元に作業内容が正しく伝わらないため、`codex-review` と同様に固定プロンプトを作業指示の先頭に付加する。
本体は `agents/codex-task-guidelines.txt` に外出ししている。

| セクション | 内容 |
|---|---|
| 指示内容 | 今回の作業のために受けた指示内容 |
| 作業結果 | 達成状況。指示外の作業を行った場合はその内容と理由 |
| 成果物・変更内容 | 成果物を特定する情報（ファイルパス等）と概要、その他の変更対象と変更内容（差分そのものは貼らない） |
| 作業中に発生した問題・課題 | 発生した問題（ファクトのみ）と、それに対する対応内容・対応理由 |
| 補足 | その他依頼元に伝達すべき情報 |

初回（`session_id` 未指定）は必ず付加される。継続時は `reinject_guideline=true` を指定した場合のみ付加される。`codex-ask` で開始したセッションを引き継ぐ場合など、固定プロンプトを与えていないセッションでは `true` を指定する。

### 権限について

`codex-ask` / `codex-review` が `--sandbox read-only` で書き込みを遮断しているのに対し、本 agent は `sandbox: workspace-write` を使い、**ワークスペースへの書き込みを承認なしに許可する**。

codex のサンドボックスは OS レベルで強制されるため、`workspace-write` ではワークスペース外への書き込みは遮断される。
`approvalPolicy: never` により承認は求められない。

## モデルの指定

使用するモデルと reasoning effort は、呼び出し時の `model=` / `effort=` 指定と環境変数 `CODEX_TASK_DEFAULT_MODEL` の 2 通りで指定できる。

| 優先順 | 指定方法 |
|---|---|
| 1 | 呼び出しプロンプトの `model=` / `effort=`（agent が `--model` / `--effort` として渡す） |
| 2 | 環境変数 `CODEX_TASK_DEFAULT_MODEL` |
| 3 | 未指定（既定モデル） |

`model` と `effort` は独立に上書きされる。`model` だけを明示指定した場合、effort は環境変数由来の値（無ければ未指定）のままになる。

環境変数 `CODEX_TASK_DEFAULT_MODEL` の書式は次のとおり。

| 書式 | 例 | 動作 |
|---|---|---|
| `<model>` | `gpt-5` | モデルのみ指定する |
| `<model>,<effort>` | `gpt-5,high` | モデルと reasoning effort を指定する |
| 未設定 / 空文字列 | — | codex CLI 既定のモデルを使用する |

プラグイン側で値の妥当性は検証しないため、不正な値を指定した場合は codex 側がエラーを返し、その内容がログの「エラー情報」に記録される。

## エラー処理

| 状況 | 動作 |
|---|---|
| `instruction` が不足 | 引数不正メッセージを出力して終了 |
| `codex` 未インストール | `'codex' コマンドが見つかりません` を出力して終了 |
| Python 3.10+ が見つからない | `python-wrapper.sh` が固定メッセージで終了 |
| app-server の起動失敗 | `start` が失敗を返す。詳細は `start` の出力に含まれる |
| 作業中の実行エラー | `wait` がエラー内容とログのパスを返す（exit code 1） |

Codex の実行が途中で失敗した場合、**変更が中途半端な状態で残る可能性がある**。エラー時は `git status --short --untracked-files=all` で作業ディレクトリの状態を確認する。作業ディレクトリ外への副作用が疑われる場合はログの作業内容も確認する。

## 依存

### コマンド

| ツール | 用途 |
|---|---|
| `codex` | OpenAI Codex CLI（`app-server` サブコマンドを使う） |
| Python 3.10+ | 制御スクリプトの実行。`bin/python-wrapper.sh` が `${CLAUDE_PLUGIN_DATA}/venv` → `pyenv` → `conda` → `PATH` の順で解決する |

### python ライブラリ

| ライブラリ | 用途 |
|---|---|
| `filelock`（`requirements.txt`） | `ask-pipeline.py`（`codex-ask` / `codex-review`）が使う。起動時に `bin/python-wrapper.sh` が自動インストールする |
