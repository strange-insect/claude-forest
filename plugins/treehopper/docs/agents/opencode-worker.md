# opencode-worker

opencode CLI にファイルの変更などを含む作業を依頼し、作業報告を Markdown ログファイルに保存する。
`session_id` を使用して完了後のセッションに追加作業指示を与えたり、opencode-ask を使用して作業内容の質疑を行うことができる。

## 基本情報

| 項目 | 値 |
|---|---|
| agent 名 | `opencode-worker` |
| 実装 | `agents/opencode-worker.py` |
| 使用モデル | `sonnet` |
| 実行コンテキスト | subagent（独立コンテキスト） |

## トリガーフレーズ

- 「opencodeに作業させて」
- 「opencodeで実装して」

## 呼び出し形式

```
[session_id=<SESSION_ID>] [output_dir=<PATH>] [reinject_guideline=<true|false>] instruction=<作業指示>
```

### 引数

| 引数 | 必須 | 説明 |
|---|---|---|
| `instruction=<作業指示>` | 必須 | opencode に依頼する作業内容。原文のまま渡す |
| `session_id=<SESSION_ID>` | 省略可 | 指定すると以前の作業を継続する |
| `reinject_guideline=<true\|false>` | 省略可 | 固定プロンプト（作業報告の形式指定）を先頭に付加するか。初回は値に関わらず付加される |
| `output_dir=<PATH>` | 省略可 | ログファイルの保存先ディレクトリ。省略時はリポジトリルートの `.llm-ask/` フォルダに保存される |

## 親セッションへの応答

```
ログファイル: <絶対パス>

opencode の作業結果を出力しました。ログに記載されたエージェントからの作業報告、実際のファイル差分などを確認しユーザに報告してください。
```

opencode が作業ディレクトリを変更している可能性があるため、ログの作業報告と実際のファイル差分を確認してユーザに報告するよう呼び出し元に促す文言を添えて返す。

## ログファイル

### 保存先

`output_dir` を省略した場合、git リポジトリルート（リポジトリ外ならカレントディレクトリ）配下の `.llm-ask/` に保存される。
`output_dir` に相対パスを渡した場合も同じ基準ディレクトリからの相対パスになる。
`.llm-ask/` フォルダを新規作成するときは `*` を対象とした `.gitignore` が自動生成される。
`.llm-ask/` フォルダが既に存在する場合は `.gitignore` の作成/編集は行われない。

### 構成

| セクション | 内容 |
|---|---|
| ヘッダー | 日時・モード（new / continuation）・ディレクトリ・セッション ID |
| メッセージ | 送信した作業指示の原文 |
| opencode の回答 | opencode からの作業報告（固定プロンプトで指定した形式） |
| エラー情報 | エラー時のみ。exit code と stderr の内容 |

ログファイル名のパターン：`<YYYYMMDD_HHMMSS_mmm>_<プロジェクト名>_opencode-worker.md`

ログに記録されるのは opencode の**報告テキスト**であり、実際のファイル変更内容ではない。変更の実体は作業ディレクトリに直接反映されるため、`git status --short --untracked-files=all` / `git diff` で確認する。

### session_id による作業継続

ログの `セッションID` 欄に記録されている ID を次回呼び出しの `session_id` に渡すと、同じ opencode スレッドで作業を続けられる。
`session_id` は `opencode-ask` / `opencode-review` とも共通で使用可能。

## opencode CLI 実行引数

opencode CLI は以下の固定引数で起動される。

| オプション | 値 | 説明 |
|---|---|---|
| サブコマンド | `run` | 実行モード（非対話。メッセージは stdin から渡す） |
| `--format` | `json` | イベントを JSON 形式で出力 |
| `--agent` | `build` | opencode の既定エージェント: ファイル編集・コマンド実行が可能 |
| `--auto` | — | 明示的に拒否されていない権限を自動承認する（非対話実行のため） |

`session_id` を指定した場合は `--session <session_id>` が付加される。

回答テキストの取得方法は `opencode-ask` と同じ（`--format json` の出力から `type == "text"` イベントを messageID ごとにまとめ、最後の messageID 分を組み立てる）。

### 固定プロンプト（作業報告の形式指定）

opencode の作業報告は形式が定まらないと呼び出し元に作業内容が正しく伝わらないため、`opencode-review` と同様に固定プロンプトを作業指示の先頭に付加する。

固定プロンプトは以下のセクション構成で報告するよう指示する。

| セクション | 内容 |
|---|---|
| 指示内容 | 今回の作業のために受けた指示内容 |
| 作業結果 | 達成状況（完了 / 一部完了 / 未完了、達成した完了条件・達成できなかった完了条件）。指示外の作業を行った場合はその内容と理由 |
| 成果物・変更内容 | 成果物を特定する情報（ファイルパス等）と概要、その他の変更対象と変更内容（差分そのものは貼らない） |
| 作業中に発生した問題・課題 | 発生した問題（ファクトのみ）と、それに対する対応内容・対応理由 |
| 補足 | その他依頼元に伝達すべき情報 |

初回（`session_id` 未指定）は必ず付加される。継続時は `reinject_guideline=true` を指定した場合のみ付加される。`opencode-ask` で開始したセッションを引き継ぐ場合など、固定プロンプトを与えていないセッションでは `true` を指定する。

### 権限について

本 agent は**制限なくあらゆる作業を実行できること**を目的としている。`opencode-ask` / `opencode-review` が `--agent plan` で `edit` を既定 `deny` にしているのに対し、本 agent は `--agent build` と `--auto` を使う。

`--auto` が自動承認するのは `edit` だけではない。**明示的に `deny` されていない権限要求はすべて承認される**ため、ファイル編集に加えて外部コマンドの実行、作業ディレクトリ外への副作用なども承認なしに行われ得る。非対話実行では権限の確認プロンプトに応答できないため、この挙動は意図的なものである。

実行範囲を絞りたい場合は opencode 側の permission 設定で制御する。設定方法は opencode のドキュメントを参照（https://opencode.ai/docs/permissions/）。

## ペアリング

`opencode-pairing` によるペアリング後は、`opencode-ask` / `opencode-review` と同様に、ペアリングされたセッション ID 以外での呼び出しが PreToolUse フックによってブロックされる。

新しい opencode セッションで作業したい場合は、`opencode-pairing` を再実行してペアリング先を切り替える。

## エラー処理

| 状況 | 動作 |
|---|---|
| `instruction` が不足 | 引数不正メッセージを出力して終了 |
| `opencode` 未インストール | `'opencode' コマンドが見つかりません` を出力して終了 |
| Python 3.10+ が見つからない | `python-wrapper.sh` が固定メッセージで終了 |
| opencode の実行エラー | エラー内容をログに含めてパスを返す（exit code 1） |

opencode の実行が途中で失敗した場合、**変更が中途半端な状態で残る可能性がある**。エラー時は `git status --short --untracked-files=all` で作業ディレクトリの状態を確認する。作業ディレクトリ外への副作用が疑われる場合はログの作業内容も確認する。

## 依存

### コマンド

| ツール | 用途 |
|---|---|
| `opencode` | opencode CLI |
| Python 3.10+ | パイプライン実行。`bin/python-wrapper.sh` が `${CLAUDE_PLUGIN_DATA}/venv` → `pyenv` → `conda` → `PATH` の順で解決する |

### python ライブラリ

| ライブラリ | 用途 |
|---|---|
| `filelock`（`requirements.txt`） | 起動時に `bin/python-wrapper.sh` が自動インストールする |
