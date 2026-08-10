# opencode-export-session

opencode のセッション会話全文を Markdown ファイルにエクスポートする。list モードで過去セッションの一覧取得にも使える。

## 基本情報

| 項目 | 値 |
|---|---|
| agent 名 | `opencode-export-session` |
| 実装 | `agents/opencode-export-session.py` |
| 使用モデル | `sonnet` |
| 実行コンテキスト | subagent（独立コンテキスト） |

## トリガーフレーズ

- 「opencode のセッションをエクスポート」
- 「opencode-export-session」

## 呼び出し形式

2 つのモードがある。

| モード | プロンプト形式 |
|---|---|
| export | `session_id=<SESSION_ID>` |
| list | `list [--cwd]` |

### 引数

| 引数 | 必須 | 説明 |
|---|---|---|
| `session_id=<SESSION_ID>` | export モードで必須 | エクスポート対象の opencode セッション ID（`ses_` で始まる） |
| `list` | list モードで必須 | このリテラルを渡すと list モードに入る |
| `--cwd` | 省略可（list のみ） | 指定するとカレントディレクトリのセッションのみに絞る |

セッション ID は `opencode-ask` / `opencode-review` / `opencode-task` が返した session_id、
ペアリング済みの場合は `${CLAUDE_PLUGIN_DATA}/opencode-pairing.txt` に記録された opencode 側の ID、
または list モードの出力から取得する。

## 親セッションへの応答

### export モード

エクスポート完了後、以下の 2 行を返す。Markdown 本文は展開・要約しない。

```
Exported to: <絶対パス>
Size: <バイト数> bytes
```

保存先はシステム標準の一時ディレクトリ（`tempfile.gettempdir()`）配下の `opencode-sessions/`。ファイル名は `session_<SessionID先頭16文字>_<タイムスタンプ>.md`。

### list モード

最新 10 件のセッションを Markdown テーブルで返す。

| 列 | 内容 |
|---|---|
| # | 更新が新しい順の連番 |
| Session ID | ID の先頭 12 文字 |
| Directory | セッションの作業ディレクトリ名 |
| Title | opencode が付けたセッションタイトル（先頭 40 文字） |
| Agent | セッションを実行した opencode agent（`plan` / `build` など） |
| Updated | 最終更新日時 |

テーブルの下にフル Session ID の一覧も出力される。

## エクスポートされる Markdown の構成

| セクション | 内容 |
|---|---|
| ヘッダー表 | Session ID・タイトル・slug・ディレクトリ・agent・モデル・opencode バージョン・親セッション・開始/終了時刻・トークン・コスト |
| Child Sessions | 子セッション（opencode の subagent セッション）の ID とタイトル一覧 |
| Turn N — User | ユーザーの発言 |
| ### Assistant | アシスタントの発言（テキスト・reasoning・ツール呼び出し） |
| ターン所要時間 | assistant メッセージの `time.created` → `time.completed` の差分 |

- reasoning（Thinking）ブロックとツール結果は `<details>` で折りたたまれる
- ツール呼び出し自体は通常の Markdown で記録される（`bash` の場合はコマンドを bash コードブロックで表示）
- 50 行を超えるツール入出力は先頭・末尾を残して中間を省略する
- コードブロックの fence は内容に含まれる最長のバッククォート連続より 1 つ長くする（差分や Markdown 編集など、ツール入出力自体が ` ``` ` を含む場合にブロックが途中で閉じるのを防ぐ）
- `step-start` / `step-finish` / `snapshot` の内部 part は出力しない
- 未知の part type は `**Unsupported part type:** <type>` として記録し、黙って欠落させない
- ツール結果に添付（画像取得や MCP resource の `attachments`）がある場合は、本文を展開せずファイル名と MIME タイプのみ記録する
- 可視 part を持たないメッセージでも、メッセージレベルの `error` があれば出力する

子セッションの会話は含まれない。必要な場合は Child Sessions に記載された ID を指定して個別にエクスポートする。

## データソース

opencode は会話を SQLite データベース（`opencode.db`）に保存している。本 agent は次の優先順でデータベースを探索する。

データディレクトリは opencode 本体と同じく `${XDG_DATA_HOME}/opencode`、未設定なら `~/.local/share/opencode`。opencode は OS による分岐を持たないため、Windows でも `%USERPROFILE%\.local\share\opencode` を使う。

| 優先順 | パス |
|---|---|
| 1 | `${OPENCODE_DB}`（opencode 本体と同じ解釈。絶対パスならそのまま、相対パスならデータディレクトリ基準） |
| 2 | `<データディレクトリ>/opencode.db` |
| 3 | `<データディレクトリ>/opencode-<channel>.db`（latest / beta / prod 以外のチャンネル。複数ある場合は更新が新しい順） |

チャンネルを切り替えた環境では複数の DB が共存し得るため、単一の DB では打ち切らない。list モードは全 DB の結果をセッション ID でマージして更新が新しい順に並べ（同一 ID が複数 DB にある場合は `time_updated` が新しい方を採用）、export モードは対象セッションが見つかるまで候補 DB を順に試す（同一 ID が複数 DB にある場合は候補順で先勝ち）。

候補 DB の一部が読めない場合（旧スキーマなど）はその DB のみスキップし、警告を stderr に出して残りの候補を処理する。すべての候補が読めなかった場合のみエラー終了する。

参照するテーブルは `session` / `message` / `part` の 3 つで、いずれも読み取り専用（`mode=ro`）で開く。export モードの読み取りは 1 つの read transaction（`BEGIN` → `rollback`）にまとめ、opencode が実行中でも session / message / part を同一スナップショットから読む。
opencode 実行中で WAL の都合により読み取り専用オープンに失敗する場合は、`opencode.db` と `-wal` / `-shm` を一時ディレクトリへコピーしてから読み取り、処理後に削除する（元のデータベースは変更しない）。コピーは `PRAGMA quick_check` で検証し、コピー中の書き込みで壊れていた場合はエラーにする。コピー途中で失敗した場合も、接続を閉じたうえで一時ディレクトリを削除する。

このコピーは **best-effort のスナップショット**であり、一貫性は保証しない。DB 本体と `-wal` を別々の時点でコピーするため、コピー中に opencode が書き込んでいると最新のメッセージが欠けることがある。`quick_check` が検出するのは構造的な破損のみで、「整合しているが最新コミットが欠落した状態」は検出できない。確実な全文が必要な場合は opencode を終了させてからエクスポートする。

Windows（Git Bash）では、`XDG_DATA_HOME` と `OPENCODE_DB` に POSIX 形式（`/c/...`）のパスが設定されていると Windows ネイティブ Python が相対パスとして扱ってしまうため Windows 実行時のみ `C:\...` 形式へ変換する。

## エラー処理

| 状況 | 動作 |
|---|---|
| `session_id` も `list` も不足 | 引数不正メッセージを出力して終了 |
| Python 3.10+ が見つからない | `python-wrapper.sh` が固定メッセージで終了 |
| `opencode.db` が見つからない | 探索したパス一覧と `OPENCODE_DB` の案内を出力して終了（exit 1） |
| 指定したセッション ID がどの候補 DB にも無い | `Session '<id>' not found.` を出力して終了（exit 1） |
| 一部の候補 DB で参照する列・テーブルが存在しない | その DB をスキップした旨を stderr に出力し、残りの候補で続行 |
| すべての候補 DB で参照する列・テーブルが存在しない（opencode のスキーマ変更） | 対応していないスキーマである旨を出力して終了（exit 1）。traceback は出さない |
| 対象セッションは見つかったが変換時にスキーマエラー | セッション未検出（not found）ではなく、スキーマエラーとして報告して終了（exit 1） |
| エクスポート先へ書き込めない（権限・容量など） | `エクスポート先へ書き込めません: <理由>` を出力して終了（exit 1） |
| WAL コピーの整合性チェック失敗 | データベースを開けない旨を出力して終了（exit 1） |

## 依存

| ツール | 用途 |
|---|---|
| Python 3.10+ | SQLite 読み取り・Markdown 変換（stdlib のみ）。`bin/python-wrapper.sh` が `${CLAUDE_PLUGIN_DATA}/venv` → `pyenv` → `conda` → `PATH` の順で Python を解決する |
| `opencode.db` | opencode のセッションストレージ（読み取りのみ） |

opencode CLI 自体の実行は行わないため、`opencode` コマンドが PATH に無くてもデータベースがあれば動作する。
