# claude-task

別セッションの Claude にファイルの変更などを含む作業を依頼し、作業報告を Markdown ログファイルに保存する。
`session_id` を使用して完了後のセッションに追加作業指示を与えたり、`claude-ask` を使用して作業内容の質疑を行うことができる。

## 基本情報

| 項目 | 値 |
|---|---|
| agent 名 | `claude-task` |
| 実装 | `agents/claude-task.py` |
| 使用モデル | `sonnet` |
| 実行コンテキスト | subagent（独立コンテキスト） |

## トリガーフレーズ

- 「claude-task」
- claude-task の使用を明示的に指定した場合

## 呼び出し形式

```
[session_id=<SESSION_ID>] [reinject_guideline=<true|false>] [model=<MODEL>] [effort=<EFFORT>] instruction=<作業指示>
```

### 引数

| 引数 | 必須 | 説明 |
|---|---|---|
| `instruction=<作業指示>` | 必須 | 別セッションの Claude に依頼する作業内容。原文のまま渡す |
| `session_id=<SESSION_ID>` | 省略可 | 指定すると以前の作業を継続する |
| `model=<MODEL>` | 省略可 | 使用するモデル。**ユーザーが明示的に指定した場合のみ渡す** |
| `effort=<EFFORT>` | 省略可 | reasoning effort。**ユーザーが明示的に指定した場合のみ渡す** |
| `reinject_guideline=<true\|false>` | 省略可 | 固定プロンプト（作業報告の形式指定）を先頭に付加するか。初回は値に関わらず付加される |

## 親セッションへの応答

```
ログファイル: <絶対パス>

作業結果を出力しました。ログに記載されたエージェントからの作業報告、実際のファイル差分などを確認しユーザに報告してください。
```

作業ディレクトリが変更されている可能性があるため、ログの作業報告と実際のファイル差分を確認してユーザに報告するよう呼び出し元に促す文言を添えて返す。

## ログファイル

### 保存先

ログは git リポジトリルート（リポジトリ外ならカレントディレクトリ）配下の `.llm-ask/` に保存される。保存先は変更できない。
`.llm-ask/` フォルダを新規作成するときは `*` を対象とした `.gitignore` が自動生成される。
`.llm-ask/` フォルダが既に存在する場合は `.gitignore` の作成/編集は行われない。

### 構成

| セクション | 内容 |
|---|---|
| ヘッダー | 日時・モード（new / continuation）・ディレクトリ・セッション ID |
| メッセージ | 実際に送信したプロンプト。初回および `reinject_guideline=true` 指定時は固定プロンプトを含む |
| Claude の回答 | 別セッションの Claude からの作業報告（固定プロンプトで指定した形式） |
| エラー情報 | エラー時のみ。exit code と stderr の内容 |

ログファイル名のパターン：`<YYYYMMDD_HHMMSS_mmm>_<プロジェクト名>_claude-task.md`

ログに記録されるのは**報告テキスト**であり、実際のファイル変更内容ではない。変更の実体は作業ディレクトリに直接反映されるため、`git status --short --untracked-files=all` / `git diff` で確認する。

### session_id による作業継続

ログの `セッションID` 欄に記録されている ID を次回呼び出しの `session_id` に渡すと、同じセッションで作業を続けられる。
`session_id` は `claude-ask` / `claude-review` とも共通で使用可能。

## Claude Code CLI 実行引数

`claude` CLI は以下の固定引数で起動される。

| オプション | 値 | 説明 |
|---|---|---|
| `-p` | — | 非インタラクティブモード（print mode） |
| `--output-format` | `json` | JSON 形式で出力 |
| `--model` | — | モデルを指定した場合のみ付与 |
| `--effort` | — | effort を指定した場合のみ付与 |
| `--dangerously-skip-permissions` | — | 権限確認をスキップ |
| `--tools` | `Read,Glob,Grep,Bash,Write,Edit,WebSearch,WebFetch` | 許可するツール（`claude-ask` / `claude-review` と異なり `Write` / `Edit` を含む） |

`session_id` を指定した場合は `--resume <session_id>` が付加される。

### 固定プロンプト（作業報告の形式指定）

作業報告は形式が定まらないと呼び出し元に作業内容が正しく伝わらないため、`claude-review` と同様に固定プロンプトを作業指示の先頭に付加する。

固定プロンプトは以下のセクション構成で報告するよう指示する。

| セクション | 内容 |
|---|---|
| 指示内容 | 今回の作業のために受けた指示内容 |
| 作業結果 | 達成状況（完了 / 一部完了 / 未完了、達成した完了条件・達成できなかった完了条件）。指示外の作業を行った場合はその内容と理由 |
| 成果物・変更内容 | 成果物を特定する情報（ファイルパス等）と概要、その他の変更対象と変更内容（差分そのものは貼らない） |
| 作業中に発生した問題・課題 | 発生した問題（ファクトのみ）と、それに対する対応内容・対応理由 |
| 補足 | その他依頼元に伝達すべき情報 |

初回（`session_id` 未指定）は必ず付加される。継続時は `reinject_guideline=true` を指定した場合のみ付加される。`claude-ask` で開始したセッションを引き継ぐ場合など、固定プロンプトを与えていないセッションでは `true` を指定する。

### 権限について

`claude-ask` / `claude-review` が `--tools` から `Write` / `Edit` を外しているのに対し、本 agent はこれらを許可し、**ファイルの変更を承認なしに実行する**。

`claude` CLI には codex のような OS レベルのサンドボックスが無く、書き込み範囲は `--tools` の許可リストでしか制御できない。許可リストには `Bash` も含まれるため、書き込み範囲はワークスペース内に限定されず、外部コマンドの実行や作業ディレクトリ外への副作用も発生し得る。

非対話実行（`-p`）では権限確認プロンプトに応答できないため、`--dangerously-skip-permissions` で承認をスキップしている。承認なしに実行される挙動は意図的なものである。

## モデルの指定

使用するモデルと reasoning effort は、呼び出し時の `model=` / `effort=` 指定と環境変数 `CLAUDE_TASK_DEFAULT_MODEL` の 2 通りで指定できる。

| 優先順 | 指定方法 |
|---|---|
| 1 | 呼び出しプロンプトの `model=` / `effort=`（agent が `--model` / `--effort` として渡す） |
| 2 | 環境変数 `CLAUDE_TASK_DEFAULT_MODEL` |
| 3 | 未指定（既定モデル） |

`model` と `effort` は独立に上書きされる。`model` だけを明示指定した場合、effort は環境変数由来の値（無ければ未指定）のままになる。

agent は**ユーザーが明示的に指示した場合のみ** `model=` / `effort=` を渡す。`--model` / `--effort` は、呼び出し時の指定または環境変数からモデル・effort が決まった場合に付与され、どちらも決まらない場合は付与せず `claude` CLI の既定モデルが使われる。

環境変数 `CLAUDE_TASK_DEFAULT_MODEL` の書式は次のとおり。

| 書式 | 例 | 動作 |
|---|---|---|
| `<model>` | `opus` | モデルのみ指定する |
| `<model>/<effort>` | `opus/high` | モデルと reasoning effort を指定する |
| 未設定 / 空文字列 | — | `claude` CLI 既定のモデルを使用する |

呼び出し時の指定・環境変数のいずれで指定した値も、`claude` の `--model`（model）と `--effort`（effort）にそのまま渡される。プラグイン側で値の妥当性は検証しないため、不正な値を指定した場合は claude 側がエラーを返し、その内容がログの「エラー情報」に記録される。

## エラー処理

| 状況 | 動作 |
|---|---|
| `instruction` が不足 | 引数不正メッセージを出力して終了 |
| `claude` 未インストール | `'claude' コマンドが見つかりません` を出力して終了 |
| Python 3.10+ が見つからない | `python-wrapper.sh` が固定メッセージで終了 |
| `claude` の実行エラー | エラー内容をログに含めてパスを返す（exit code 1） |

実行が途中で失敗した場合、**変更が中途半端な状態で残る可能性がある**。エラー時は `git status --short --untracked-files=all` で作業ディレクトリの状態を確認する。作業ディレクトリ外への副作用が疑われる場合はログの作業内容も確認する。

## 依存

### コマンド

| ツール | 用途 |
|---|---|
| `claude` | Claude Code CLI |
| Python 3.10+ | パイプライン実行。`bin/python-wrapper.sh` が `${CLAUDE_PLUGIN_DATA}/venv` → `pyenv` → `conda` → `PATH` の順で解決する |

### python ライブラリ

| ライブラリ | 用途 |
|---|---|
| `filelock`（`requirements.txt`） | 起動時に `bin/python-wrapper.sh` が自動インストールする |
