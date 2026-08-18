# opencode-task

opencode CLI にファイルの変更などを含む作業を依頼し、作業報告を Markdown ログファイルに保存する。
**作業の実行中に追加の指示を渡せる**のがこの agent の特徴。

## 基本情報

| 項目 | 値 |
|---|---|
| agent 名 | `opencode-task` |
| 実装 | `bin/task-control.py` + `bin/task-supervisor.py` + `agents/_steer_opencode.py` |
| 使用モデル | `sonnet` |
| 実行コンテキスト | subagent（独立コンテキスト） |
| opencode の起動形態 | `opencode serve` |

## トリガーフレーズ

- 「opencodeに作業させて」
- 「opencodeで実装して」

## 呼び出し形式

```
[session_id=<SESSION_ID>] [reinject_guideline=<true|false>] [model=<MODEL>] [effort=<EFFORT>] instruction=<作業指示>
```

### 引数

| 引数 | 必須 | 説明 |
|---|---|---|
| `instruction=<作業指示>` | 必須 | opencode に依頼する作業内容。原文のまま渡す |
| `session_id=<SESSION_ID>` | 省略可 | 指定すると以前の作業を継続する |
| `model=<MODEL>` | 省略可 | 使用するモデル。**ユーザーが明示的に指定した場合のみ渡す** |
| `effort=<EFFORT>` | 省略可 | reasoning effort。**ユーザーが明示的に指定した場合のみ渡す** |
| `reinject_guideline=<true\|false>` | 省略可 | 固定プロンプト（開発ガイドラインの参照指示・作業報告の形式指定）を先頭に付加するか。初回は値に関わらず付加される |

実行中の指示のための引数は無い。`SendMessage` の自由文で送る（次節）。

## 実行中の指示

`opencode-task` を**バックグラウンドで起動**し、実行中に `SendMessage` でメッセージを送る。

```
Agent(opencode-task, "instruction=...", run_in_background: true)
    ↓ ユーザーから追加の指示
SendMessage(opencode-task, "refresh token は触らず、cookie の SameSite 設定を先に疑って")
    ↓
subagent が原文のまま opencode へ prompt_async で投入する
```

フォアグラウンドで起動した場合、メインエージェントは subagent の完了までブロックされるため
指示を渡せない。途中で指示を追加する可能性がある作業は必ずバックグラウンドで起動する。

投入した指示を opencode が読むのは**次のツール実行の境界**である。
長時間のコマンド（テスト実行など）が走っている最中に送っても、そのコマンドが終わるまでは反映されない。

`steer` は指示を opencode へ投入できたかどうかが確定するまで戻らない。作業が既に終わっていた場合は
投入されずに失敗を返し、subagent が呼び出し元にその旨を伝える。

## 実行モデル

```
メインエージェント
  │ Agent(opencode-task, ..., run_in_background: true)
  │      … SendMessage …
  ▼
opencode-task subagent
  │ 1. task-control.py start            → 作業を開始する
  │ 2. task-control.py wait              を反復
  │      ← スライスとスライスの間で SendMessage が届く
  │ 3. task-control.py steer            届いたメッセージを opencode へ伝達
  │ 4. wait がログパスを返したら終了
  ▼
task-supervisor.py（subagent の子プロセス）
  ▼  HTTP (127.0.0.1)
opencode serve
```

`wait` は 60 秒のスライスで刻む。subagent はフォアグラウンドの Bash に入っている間
メッセージを受け取れないため、スライスを長くすると指示を渡せない時間が延びる。

supervisor は subagent の子プロセスであり、subagent の終了に伴って一緒に終了する。
作業が終わった時点でログを書き出し、ワーカーを終了する。

## 親セッションへの応答

```
ログファイル: <絶対パス>

opencode の作業結果を出力しました。ログに記載されたエージェントからの作業報告、実際のファイル差分などを確認しユーザに報告してください。
```

opencode が作業ディレクトリを変更している可能性があるため、ログの作業報告と実際のファイル差分を確認してユーザに報告するよう呼び出し元に促す文言を添えて返す。

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
| opencode の回答 | opencode からの作業報告（固定プロンプトで指定した形式） |
| エラー情報 | エラー時のみ |

ログファイル名のパターン：`<YYYYMMDD_HHMMSS_mmm>_<プロジェクト名>_opencode-task.md`

ログに記録されるのは opencode の**報告テキスト**であり、実際のファイル変更内容ではない。変更の実体は作業ディレクトリに直接反映されるため、`git status --short --untracked-files=all` / `git diff` で確認する。

### session_id による作業継続

ログの `セッションID` 欄に記録されている ID を次回呼び出しの `session_id` に渡すと、同じ opencode スレッドで作業を続けられる。
`session_id` は `opencode-ask` / `opencode-review` とも共通で使用可能。

## opencode CLI 実行引数

`opencode serve --port 0 --hostname 127.0.0.1` を起動し、待ち受けポートを起動ログから読み取る。
`--port 0` で OS に空きポートを選ばせるのは、同時に走る別の run とポートが衝突しないようにするため。

以降は HTTP API を使う。

| リクエスト | 指定 |
|---|---|
| `POST /session` | `agent: build` / `permission`（全許可）/ `model` |
| `PATCH /session/{id}` | `permission`（全許可）。継続セッションに適用する |
| `POST /session/{id}/prompt_async` | `parts`（作業指示・実行中の指示とも同じ形式）/ `variant` |
| `GET /session/{id}/message` | 作業報告の収集と完了判定のためのポーリング |
| `GET /session/status` | 実行中の指示を投入する直前の状態確認 |

`session_id` を指定した場合はセッションを新規作成せず、その ID をそのまま使う。
ポーリング間隔は 2 秒で、これが完了検知の遅延の上限になる。

### 固定プロンプト（開発ガイドラインの参照指示・作業報告の形式指定）

opencode の作業報告は形式が定まらないと呼び出し元に作業内容が正しく伝わらないため、`opencode-review` と同様に固定プロンプトを作業指示の先頭に付加する。
本体は `agents/opencode-task-guidelines.txt` に外出ししている。

| セクション | 内容 |
|---|---|
| 指示内容 | 今回の作業のために受けた指示内容 |
| 作業結果 | 達成状況。指示外の作業を行った場合はその内容と理由 |
| 成果物・変更内容 | 成果物を特定する情報（ファイルパス等）と概要、その他の変更対象と変更内容（差分そのものは貼らない） |
| 作業中に発生した問題・課題 | 発生した問題（ファクトのみ）と、それに対する対応内容・対応理由 |
| 補足 | その他依頼元に伝達すべき情報 |

初回（`session_id` 未指定）は必ず付加される。継続時は `reinject_guideline=true` を指定した場合のみ付加される。`opencode-ask` で開始したセッションを引き継ぐ場合など、固定プロンプトを与えていないセッションでは `true` を指定する。

固定プロンプトには開発ガイドライン（`agents/development-guidelines.txt`）の絶対パスを併せて記載し、作業開始前に読んで従うよう指示する。ガイドラインの本文はプロンプトに埋め込まない。環境変数 `CLAUDEFOREST_DISABLE_DEVELOPMENT_GUIDELINES` に空文字以外を設定した場合、この参照指示は付加されない。

### 権限について

`opencode-ask` / `opencode-review` が `--agent plan`（`edit` を既定 `deny`）で書き込みを遮断しているのに対し、本 agent は `agent: build` とセッションの `permission` 全許可を使い、**作業ディレクトリへの変更を承認なしに許可する**。

`permission` を全許可にすると、明示的に `deny` されていない権限要求をすべて承認する。
そのため **ファイル編集に限らず外部コマンドの実行や作業ディレクトリ外への副作用も発生し得る**。
OS レベルのサンドボックスは無いため、書き込み範囲を仕組みで限定することはできない。

セッションに設定した `permission` は作業後も残るが、`opencode-ask` / `opencode-review` が使う
`--agent plan` は書き込みツール自体を持たないため、同じ `session_id` を引き継いでも読み取り専用は保たれる。
なお `PATCH /session/{id}` の `permission` は既存の規則へ追記されるため、規則を取り除く手段は無い。

## モデルの指定

使用するモデルと reasoning effort は、呼び出し時の `model=` / `effort=` 指定と環境変数 `OPENCODE_TASK_DEFAULT_MODEL` の 2 通りで指定できる。

| 優先順 | 指定方法 |
|---|---|
| 1 | 呼び出しプロンプトの `model=` / `effort=`（agent が `--model` / `--effort` として渡す） |
| 2 | 環境変数 `OPENCODE_TASK_DEFAULT_MODEL` |
| 3 | 未指定（既定モデル） |

`model` と `effort` は独立に上書きされる。`model` だけを明示指定した場合、effort は環境変数由来の値（無ければ未指定）のままになる。

環境変数 `OPENCODE_TASK_DEFAULT_MODEL` の書式は次のとおり。

| 書式 | 例 | 動作 |
|---|---|---|
| `<model>` | `anthropic/claude-sonnet-5` | モデルのみ指定する（`provider/model` 形式） |
| `<model>,<effort>` | `anthropic/claude-sonnet-5,high` | モデルと variant を指定する |
| 未設定 / 空文字列 | — | opencode CLI 既定のモデルを使用する |

モデルは `provider/model` 形式で指定する。この形式でない値を指定した場合はエラーになる。
値そのものの妥当性は検証しないため、存在しないモデルを指定した場合は opencode 側がエラーを返し、その内容がログの「エラー情報」に記録される。

## エラー処理

| 状況 | 動作 |
|---|---|
| `instruction` が不足 | 引数不正メッセージを出力して終了 |
| `opencode` 未インストール | `'opencode' コマンドが見つかりません` を出力して終了 |
| Python 3.10+ が見つからない | `python-wrapper.sh` が固定メッセージで終了 |
| `opencode serve` の起動失敗 | `start` が失敗を返す。詳細は `start` の出力に含まれる |
| 作業中の実行エラー | `wait` がエラー内容とログのパスを返す（exit code 1） |

opencode の実行が途中で失敗した場合、**変更が中途半端な状態で残る可能性がある**。エラー時は `git status --short --untracked-files=all` で作業ディレクトリの状態を確認する。作業ディレクトリ外への副作用が疑われる場合はログの作業内容も確認する。

## 依存

### コマンド

| ツール | 用途 |
|---|---|
| `opencode` | opencode CLI（`serve` サブコマンドを使う） |
| Python 3.10+ | 制御スクリプトの実行。`bin/python-wrapper.sh` が `${CLAUDE_PLUGIN_DATA}/venv` → `pyenv` → `conda` → `PATH` の順で解決する |

### python ライブラリ

| ライブラリ | 用途 |
|---|---|
| `filelock`（`requirements.txt`） | `ask-pipeline.py`（`opencode-ask` / `opencode-review`）が使う。起動時に `bin/python-wrapper.sh` が自動インストールする |
