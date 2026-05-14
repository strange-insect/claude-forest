# export-session

Claude Code のセッション会話全文を Markdown ファイルにエクスポートする。list モードで過去セッションの一覧取得にも使える。

## 基本情報

| 項目 | 値 |
|---|---|
| agent 名 | `export-session` |
| 実装 | `agents/export-session.py` |
| 使用モデル | `sonnet` |
| 実行コンテキスト | subagent（独立コンテキスト） |

## トリガーフレーズ

- 「セッションをエクスポート」
- 「export-session」

## 呼び出し形式

2 つのモードがある。

| モード | プロンプト形式 |
|---|---|
| export | `session_id=<SESSION_ID>` |
| list | `list [--cwd]` |

### 引数

| 引数 | 必須 | 説明 |
|---|---|---|
| `session_id=<SESSION_ID>` | export モードで必須 | エクスポート対象のセッション ID |
| `list` | list モードで必須 | このリテラルを渡すと list モードに入る |
| `--cwd` | 省略可（list のみ） | 指定するとカレントディレクトリのセッションのみに絞る |

現在のセッションをエクスポートする場合は、`CLAUDE_SESSION_ID` 環境変数の値を `session_id` に渡す。

## 親セッションへの応答

### export モード

エクスポート完了後、以下の 2 行を返す。Markdown 本文は展開・要約しない。

```
Exported to: <絶対パス>
Size: <バイト数> bytes
```

保存先はシステム標準の一時ディレクトリ（`tempfile.gettempdir()`）配下の `claude-sessions/`。ファイル名は `session_<SessionID先頭8文字>_<タイムスタンプ>.md`。

### list モード

最新 10 件のセッションを Markdown テーブルで返す。

| 列 | 内容 |
|---|---|
| # | 新しい順の連番 |
| Session ID | ID の先頭 8 文字 |
| Project | プロジェクトディレクトリ名 |
| First Message | 最初のメッセージ（先頭 40 文字） |
| Date | セッション開始日 |
| Messages | メッセージ数 |

テーブルの下にフル Session ID の一覧も出力される。

## エクスポートされる Markdown の構成

| セクション | 内容 |
|---|---|
| ヘッダー表 | Session ID・プロジェクト・ブランチ・Claude Code バージョン・開始/終了時刻 |
| Turn N — User | ユーザーの発言 |
| Turn N — Assistant | アシスタントの発言（テキスト・ツール呼び出し・Thinking ブロック） |
| ターン所要時間 | 各ターンの処理時間 |

ツール結果と Thinking ブロックは `<details>` で折りたたまれる。ツール呼び出し自体は通常の Markdown で記録される。

## エラー処理

| 状況 | 動作 |
|---|---|
| `session_id` も `list` も不足 | 引数不正メッセージを出力して終了 |
| Python 3.10+ が見つからない | `python-wrapper.sh` が固定メッセージで終了 |
| 指定したセッション ID が見つからない | `Session '<id>' not found.` を出力して終了 |
| `CLAUDE_SESSION_ID` 未設定で `session_id=current` を渡した場合 | `CLAUDE_SESSION_ID is not set.` を出力して終了 |

## 依存

| ツール | 用途 |
|---|---|
| Python 3.10+ | JSONL 解析・Markdown 変換（stdlib のみ）。`bin/python-wrapper.sh` が `${CLAUDE_PLUGIN_DATA}/venv` → `pyenv` → `conda` → `PATH` の順で Python を解決する |
| `~/.claude/projects/` | セッション JSONL ファイルの検索先 |
| `~/.claude/history.jsonl` | list モードでのセッション一覧取得元 |
