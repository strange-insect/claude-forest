# codex-export-session

codex のセッション会話全文を Markdown ファイルにエクスポートする。list モードで過去セッションの一覧取得にも使える。

## 基本情報

| 項目 | 値 |
|---|---|
| agent 名 | `codex-export-session` |
| 実装 | `agents/codex-export-session.py` |
| 使用モデル | `sonnet` |
| 実行コンテキスト | subagent（独立コンテキスト） |

## トリガーフレーズ

- 「codex のセッションをエクスポート」
- 「codex-export-session」

## 呼び出し形式

2 つのモードがある。

| モード | プロンプト形式 |
|---|---|
| export | `session_id=<SESSION_ID>` |
| list | `list [--cwd]` |

### 引数

| 引数 | 必須 | 説明 |
|---|---|---|
| `session_id=<SESSION_ID>` | export モードで必須 | エクスポート対象の codex セッション ID（UUID 形式） |
| `list` | list モードで必須 | このリテラルを渡すと list モードに入る |
| `--cwd` | 省略可（list のみ） | 指定するとカレントディレクトリのセッションのみに絞る |

セッション ID は `codex-ask` / `codex-review` / `codex-task` が返した session_id、
ペアリング済みの場合は `${CLAUDE_PLUGIN_DATA}/codex-pairing.txt` に記録された codex 側の ID、
または list モードの出力から取得する。

## 親セッションへの応答

### export モード

エクスポート完了後、以下の 2 行を返す。Markdown 本文は展開・要約しない。

```
Exported to: <絶対パス>
Size: <バイト数> bytes
```

保存先はシステム標準の一時ディレクトリ（`tempfile.gettempdir()`）配下の `codex-sessions/`。ファイル名は `session_<SessionID先頭16文字>_<タイムスタンプ>.md`。

### list モード

最新 10 件のセッションを Markdown テーブルで返す。

| 列 | 内容 |
|---|---|
| # | 更新が新しい順の連番 |
| Session ID | ID の先頭 8 文字 |
| Directory | セッションの作業ディレクトリ名 |
| First Message | 最初のユーザーメッセージ（先頭 40 文字） |
| Date | セッション開始日 |

テーブルの下にフル Session ID の一覧も出力される。

## エクスポートされる Markdown の構成

| セクション | 内容 |
|---|---|
| ヘッダー表 | Session ID・ディレクトリ・モデル・effort・codex バージョン・originator・開始/終了時刻・トークン |
| Turn N — User | ユーザーの発言（`event_msg.user_message`） |
| ### Assistant | アシスタントの発言（`event_msg.agent_message`） |
| ツール呼び出し | `function_call` / `custom_tool_call` / `tool_search_call` の名前と引数 |
| ツール結果 | `function_call_output` / `custom_tool_call_output` / `tool_search_output`（`<details>` で折りたたみ） |
| エラー | `event_msg.error` のメッセージと `codex_error_info` |

- ツール引数に `cmd` があればシェルコマンドとして、それ以外は JSON として表示する
- ツール結果の見出しは `Result: <ツール名> (<call_id>)` とする。並列にツールを呼ぶセッションでは出力順が呼び出し順と一致しないため、どの呼び出しに対する結果かを示す
- 50 行を超えるツール入出力は先頭・末尾を残して中間を省略する
- コードブロックの fence は内容に含まれる最長のバッククォート連続より 1 つ長くする（ツール入出力自体が ` ``` ` を含む場合にブロックが途中で閉じるのを防ぐ）
- Web 操作は action の種類ごとに記録する（`search` はクエリ、`open_page` は URL、`find_in_page` は検索パターンと URL）
- `web_search_call` と `web_search_end` は同じ操作の両端なので、対応する action を 1 件ずつ消費して重複排除する。call が出力済みなら end 側は見出しを出さず結果リンク（上位 5 件）のみ、call が無ければ end 側が見出しも出す。end 側の action は call 側より情報が少ないため（`open_page` は URL を持たない）、対応付けは `search` はクエリ、`find_in_page` は URL とパターン、それ以外は種類のみで行う
- コンテキスト圧縮（`context_compacted`）、ターン中断（`turn_aborted`）、レビューモードの出入りも記録する
- 未知の type は `**Unsupported item type:** <type>` / `**Unsupported event type:** <type>` / `**Unsupported record type:** <type>` / `**Unsupported web action:** <type>` として記録し、黙って欠落させない

**reasoning は出力されない。** codex の `response_item.reasoning` は `encrypted_content` のみを持ち平文の要約が無いため、エクスポートできない。

以下は会話の内容を持たない内部レコードなので出力しない。

| 種別 | 理由 |
|---|---|
| `session_meta` / `turn_context` | ヘッダー表の生成に使用 |
| `world_state` / `compacted` | codex 内部の状態で、会話としての内容を持たない |
| `response_item.message` | 本文は `event_msg` 側で出力するため（重複回避）。role が developer / user のものはハーネスが注入した指示 |
| `event_msg.token_count` / `task_started` / `task_complete` / `thread_settings_applied` / `item_completed` | 進捗・統計情報。最終応答は `agent_message` として出力済み |
| `event_msg.exec_command_end` / `patch_apply_end` | ツール結果と重複する |

## データソース

codex はセッションを JSONL のロールアウトファイルとして保存している。

| 項目 | 値 |
|---|---|
| ディレクトリ | `${CODEX_HOME}/sessions`、未設定なら `~/.codex/sessions` |
| ファイル | `<YYYY>/<MM>/<DD>/rollout-<ISO8601>-<session_id>.jsonl` |

実行中のセッションもエクスポートできるが、その場合の内容は best-effort となる。書き込み途中の行は読み飛ばされ、`event_msg.agent_message` がまだ書かれていない時点ではアシスタントの発言が欠けることがある。完全な内容が必要な場合はセッション終了後にエクスポートする。

export モードはファイル名末尾のセッション ID で検索し、見つからない場合は各ファイルの `session_meta` を読んで探す。list モードはファイルの更新時刻が新しい順に、先頭 200 行から `session_meta` と最初のユーザーメッセージを読み取る。

Windows（Git Bash）では、`CODEX_HOME` に POSIX 形式（`/c/...`）のパスが設定されていると Windows ネイティブ Python が相対パスとして扱ってしまうため、Windows 実行時のみ `C:\...` 形式へ変換する。

## エラー処理

| 状況 | 動作 |
|---|---|
| `session_id` も `list` も不足 | 引数不正メッセージを出力して終了 |
| Python 3.10+ が見つからない | `python-wrapper.sh` が固定メッセージで終了 |
| セッションディレクトリが無い | 探索したパスと `CODEX_HOME` の案内を出力して終了（exit 1） |
| 指定したセッション ID が見つからない | `Session '<id>' not found.` を出力して終了（exit 1） |
| エクスポート先へ書き込めない（権限・容量など） | `エクスポート先へ書き込めません: <理由>` を出力して終了（exit 1） |
| 壊れた JSONL 行 | その行のみ読み飛ばす |
| セッション内で codex がエラーを返していた | `**Codex error:**` としてメッセージと `codex_error_info` を本文に記録する（エクスポート自体は成功） |

## 依存

| ツール | 用途 |
|---|---|
| Python 3.10+ | JSONL 解析・Markdown 変換（stdlib のみ）。`bin/python-wrapper.sh` が `${CLAUDE_PLUGIN_DATA}/venv` → `pyenv` → `conda` → `PATH` の順で Python を解決する |
| `${CODEX_HOME}/sessions` | codex のセッションログ（読み取りのみ） |

codex CLI 自体の実行は行わないため、`codex` コマンドが PATH に無くてもセッションログがあれば動作する。
