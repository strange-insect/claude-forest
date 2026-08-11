#!/usr/bin/env python3
"""Codex セッション会話エクスポーター

codex CLI のセッションログ（`${CODEX_HOME}/sessions/**/rollout-*.jsonl`）を
Markdown に変換して一時ディレクトリへ保存する。

使い方:
    codex-export-session.py list [--cwd] [--project PATH] [--limit N]
    codex-export-session.py <session-id> [--output DIR]
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

OUTPUT_DIR = Path(tempfile.gettempdir()) / "codex-sessions"

# ツール入出力の折り返し行数
MAX_OUTPUT_LINES = 50

# list モードで各セッションのメタ情報を探すために読む最大行数
HEAD_SCAN_LINES = 200

# 会話としての内容を持たない内部イベント（出力しない）
INTERNAL_EVENT_TYPES = {
    "task_started",
    "task_complete",          # 最終応答は agent_message として出力済み
    "token_count",
    "thread_settings_applied",
    "item_completed",
    "exec_command_end",       # function_call_output と重複する
    "patch_apply_end",
}
INTERNAL_ITEM_TYPES = {
    "message",                # user / assistant の本文は event_msg 側で出力する
    "reasoning",              # encrypted_content のみで平文を持たない
}
# 出力しないトップレベルのレコード種別
#   session_meta / turn_context : ヘッダー表の生成に使う
#   world_state / compacted     : codex 内部の状態（会話としての内容を持たない）
INTERNAL_RECORD_TYPES = {"session_meta", "turn_context", "world_state", "compacted"}


# ---------------------------------------------------------------------------
# セッションファイルの探索
# ---------------------------------------------------------------------------

def env_path(name: str) -> str:
    """環境変数からパスを取得する。

    Git Bash / MSYS2 から Windows ネイティブ Python を起動した場合、`/c/Users/...`
    形式の値が渡されることがある。pathlib はこれを相対パスとして扱うため、
    Windows 上でのみ `C:\\Users\\...` に変換する。
    """
    value = os.environ.get(name, "").strip()
    if not value or os.name != "nt":
        return value
    match = re.fullmatch(r"/([A-Za-z])(/.*)?", value)
    if match:
        drive, rest = match.group(1), match.group(2) or "/"
        return f"{drive.upper()}:{rest}".replace("/", "\\")
    return value


def sessions_dir() -> Path:
    """codex のセッションディレクトリを返す（codex 本体と同じ解決順）。"""
    codex_home = env_path("CODEX_HOME")
    base = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
    return base / "sessions"


def iter_session_files(base: Path) -> list[Path]:
    """rollout ファイルを更新が新しい順に返す。"""
    if not base.is_dir():
        return []
    files = [p for p in base.rglob("rollout-*.jsonl") if p.is_file()]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def find_session_file(session_id: str) -> Path | None:
    """セッション ID からファイルを検索する（ファイル名末尾が ID）。"""
    base = sessions_dir()
    if not base.is_dir():
        return None
    matches = sorted(base.rglob(f"rollout-*-{session_id}.jsonl"),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    if matches:
        return matches[0]
    # ファイル名から特定できない場合は session_meta を見て探す
    for path in iter_session_files(base):
        meta = read_session_meta(path)
        if meta.get("session_id") == session_id:
            return path
    return None


def iter_records(path: Path, limit: int | None = None):
    """JSONL を 1 行ずつ読む。壊れた行は読み飛ばす。"""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fp:
            for i, line in enumerate(fp):
                if limit is not None and i >= limit:
                    return
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict):
                    yield record
    except OSError:
        return


def read_session_meta(path: Path) -> dict:
    """先頭付近から session_meta / 最初の user_message を拾う。"""
    info: dict = {"path": path}
    for record in iter_records(path, limit=HEAD_SCAN_LINES):
        payload = record.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        if record.get("type") == "session_meta" and "session_id" not in info:
            info["session_id"] = payload.get("session_id") or payload.get("id") or ""
            info["cwd"] = payload.get("cwd", "")
            info["cliVersion"] = payload.get("cli_version", "")
            info["originator"] = payload.get("originator", "")
            info["timestamp"] = payload.get("timestamp") or record.get("timestamp", "")
        elif record.get("type") == "turn_context" and "model" not in info:
            info["model"] = payload.get("model", "")
            info["effort"] = payload.get("effort", "")
        elif payload.get("type") == "user_message" and "firstMessage" not in info:
            info["firstMessage"] = str(payload.get("message", ""))
            break
    if not info.get("session_id"):
        # session_meta が読めない場合はファイル名 rollout-<ISO>-<session_id>.jsonl から拾う
        match = re.search(r"-([0-9a-fA-F-]{36})$", path.stem)
        info["session_id"] = match.group(1) if match else path.stem
    return info


# ---------------------------------------------------------------------------
# 整形ユーティリティ
# ---------------------------------------------------------------------------

def format_timestamp(value: str) -> str:
    """ISO 8601 タイムスタンプを読みやすい形式に変換"""
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S %Z").strip()
    except (TypeError, ValueError):
        return str(value)


def truncate_lines(text: str, max_lines: int = MAX_OUTPUT_LINES) -> str:
    """長いテキストを先頭・末尾のみ残して切り詰める"""
    lines = text.split("\n")
    if len(lines) <= max_lines:
        return text
    head = max_lines // 2
    tail = max_lines - head
    omitted = len(lines) - max_lines
    return (
        "\n".join(lines[:head])
        + f"\n\n... ({omitted} lines omitted) ...\n\n"
        + "\n".join(lines[-tail:])
    )


def escape_table_cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def fenced(text: str, language: str = "") -> str:
    """コードブロックで囲む。

    ツールの入出力自体が ``` を含むことがある（差分・Markdown 編集など）。
    本文中の最長のバッククォート連続より 1 つ長い fence を使い、
    ブロックが途中で閉じてしまわないようにする。
    """
    longest = 0
    run = 0
    for char in text:
        if char == "`":
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    fence = "`" * max(3, longest + 1)
    return f"{fence}{language}\n{text}\n{fence}"


def content_text(content) -> str:
    """content_item のリスト（input_text / output_text）を文字列にまとめる。"""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return "" if content is None else str(content)
    parts = []
    for item in content:
        if isinstance(item, dict):
            parts.append(str(item.get("text", "")))
        else:
            parts.append(str(item))
    return "".join(parts)


# ---------------------------------------------------------------------------
# レコードの Markdown 化
# ---------------------------------------------------------------------------

def format_tool_call(name: str, arguments: str) -> str:
    lines = [f"**Tool: {name or 'unknown'}**"]
    text = str(arguments or "")
    if not text:
        return "\n".join(lines)
    # exec 系は JavaScript / シェルコマンド、それ以外は JSON 引数
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        lines.append(fenced(truncate_lines(text)))
        return "\n".join(lines)
    if isinstance(parsed, dict) and "cmd" in parsed and isinstance(parsed["cmd"], str):
        lines.append(fenced(parsed["cmd"], "bash"))
        extra = {k: v for k, v in parsed.items() if k != "cmd"}
        if extra:
            lines.append(fenced(json.dumps(extra, indent=2, ensure_ascii=False), "json"))
        return "\n".join(lines)
    lines.append(fenced(truncate_lines(json.dumps(parsed, indent=2, ensure_ascii=False)), "json"))
    return "\n".join(lines)


def format_tool_output(output, call_id: str = "", tool_name: str = "") -> str:
    """ツール結果を折りたたみで整形する。

    並列にツールを呼ぶセッションでは出力順が呼び出し順と一致しないため、
    どの呼び出しに対する結果かを summary に出す。
    """
    summary = "Result"
    if tool_name:
        summary += f": {tool_name}"
    if call_id:
        summary += f" ({call_id})"
    body = truncate_lines(content_text(output))
    if not body.strip():
        return f"<details><summary>{summary}</summary>\n\n（出力なし）\n\n</details>"
    return f"<details><summary>{summary}</summary>\n\n{fenced(body)}\n\n</details>"


def collect_call_names(records: list[dict]) -> dict[str, str]:
    """call_id → ツール名の対応を作る。"""
    names: dict[str, str] = {}
    for record in records:
        payload = record.get("payload")
        if record.get("type") != "response_item" or not isinstance(payload, dict):
            continue
        if payload.get("type") in ("function_call", "custom_tool_call", "tool_search_call"):
            call_id = payload.get("call_id")
            if call_id:
                names[str(call_id)] = str(payload.get("name") or payload.get("type", ""))
    return names


def web_action_key(action, fallback_query: str = "") -> tuple:
    """web_search_call と web_search_end を対応付けるキー。

    end 側の action は call 側より情報が少ないことがある（`open_page` は URL を持たない）。
    種類ごとに、両方が持つフィールドだけでキーを作る。
    """
    action = action if isinstance(action, dict) else {}
    kind = action.get("type", "")
    if kind == "search":
        return (kind, action.get("query") or fallback_query)
    if kind == "find_in_page":
        return (kind, action.get("url", ""), action.get("pattern", ""))
    # open_page など、end 側に識別できる情報が無いものは種類だけで対応付ける
    return (kind,)


def format_web_action(action) -> str:
    """web_search_call の action を種類ごとに整形する。"""
    if not isinstance(action, dict):
        return "**Web search**"
    kind = action.get("type", "")
    if kind == "search":
        query = action.get("query", "")
        return f"**Web search:** `{escape_table_cell(query)}`" if query else "**Web search**"
    if kind == "open_page":
        url = action.get("url", "")
        return f"**Web open:** `{escape_table_cell(url)}`" if url else "**Web open**"
    if kind == "find_in_page":
        return (f"**Web find:** `{escape_table_cell(action.get('pattern', ''))}`"
                f" in `{escape_table_cell(action.get('url', ''))}`")
    if not kind:
        return "**Web search**"
    return f"**Unsupported web action:** `{kind}`"


def format_record(record: dict, state: dict | None = None) -> str | None:
    """レコードを Markdown 断片に変換する。出力不要な場合は None を返す。"""
    rec_type = record.get("type")
    if rec_type not in ("response_item", "event_msg"):
        if rec_type in INTERNAL_RECORD_TYPES:
            return None
        return f"**Unsupported record type:** `{rec_type}`"

    payload = record.get("payload") or {}
    if not isinstance(payload, dict):
        return None
    item_type = payload.get("type")

    if rec_type == "response_item":
        if item_type in INTERNAL_ITEM_TYPES:
            return None
        if item_type == "function_call":
            return format_tool_call(payload.get("name", ""), payload.get("arguments", ""))
        if item_type == "custom_tool_call":
            return format_tool_call(payload.get("name", ""), payload.get("input", ""))
        if item_type in ("function_call_output", "custom_tool_call_output"):
            call_id = str(payload.get("call_id", ""))
            names = (state or {}).get("call_names", {})
            return format_tool_output(payload.get("output"), call_id, names.get(call_id, ""))
        if item_type == "web_search_call":
            action = payload.get("action") or {}
            if state is not None:
                # 対応する web_search_end が後続するため、end 側では見出しを繰り返さない
                actions = state.setdefault("web_actions", Counter())
                actions[web_action_key(action)] += 1
            return format_web_action(action)
        if item_type == "tool_search_call":
            arguments = payload.get("arguments") or {}
            query = arguments.get("query", "") if isinstance(arguments, dict) else str(arguments)
            return f"**Tool search:** `{escape_table_cell(query)}`"
        if item_type == "tool_search_output":
            call_id = str(payload.get("call_id", ""))
            tools = payload.get("tools")
            body = (payload.get("output") if tools is None
                    else json.dumps(tools, indent=2, ensure_ascii=False))
            return format_tool_output(body, call_id, "tool_search")
        return f"**Unsupported item type:** `{item_type}`"

    if rec_type == "event_msg":
        if item_type in INTERNAL_EVENT_TYPES:
            return None
        if item_type in ("user_message", "agent_message"):
            if item_type == "user_message" and state is not None:
                # ターンをまたいで未消費の call が残ると、別ターンの end を誤って抑制する
                state.setdefault("web_actions", Counter()).clear()
            return str(payload.get("message", "")).strip() or None
        if item_type == "web_search_end":
            query = str(payload.get("query", ""))
            action = payload.get("action") or {}
            results = payload.get("results") or []
            # 対応する web_search_call が出力済みなら見出しを繰り返さない（1 件ずつ消費する）
            already = False
            if state is not None:
                pending = state.setdefault("web_actions", Counter())
                key = web_action_key(action, query)
                already = pending[key] > 0
                if already:
                    pending[key] -= 1
            lines = [] if already else [format_web_action(action) if action
                                        else f"**Web search:** `{escape_table_cell(query)}`"]
            for result in results[:5]:
                if not isinstance(result, dict):
                    continue
                title = escape_table_cell(result.get("title", ""))
                url = result.get("url", "")
                lines.append(f"- [{title}]({url})" if url else f"- {title}")
            return "\n".join(lines) if lines else None
        if item_type == "error":
            detail = str(payload.get("message", ""))
            error_info = payload.get("codex_error_info")
            if error_info:
                detail += f"\n\ncodex_error_info: {error_info}"
            return f"**Codex error:**\n\n{fenced(truncate_lines(detail))}"
        if item_type == "context_compacted":
            return "**Context compacted**"
        if item_type == "turn_aborted":
            return f"**Turn aborted:** {escape_table_cell(payload.get('reason', ''))}"
        if item_type == "entered_review_mode":
            hint = payload.get("user_facing_hint", "")
            return f"**Review mode:** {escape_table_cell(hint)}" if hint else "**Review mode**"
        if item_type == "exited_review_mode":
            return "**Review mode exited**"
        return f"**Unsupported event type:** `{item_type}`"



def convert_session_to_markdown(path: Path) -> str:
    records = list(iter_records(path))
    if not records:
        return "# Empty Session\n\nNo records found."

    meta: dict = {}
    context: dict = {}
    tokens: dict = {}
    first_ts = ""
    last_ts = ""
    for record in records:
        payload = record.get("payload") or {}
        if record.get("timestamp"):
            first_ts = first_ts or record["timestamp"]
            last_ts = record["timestamp"]
        if not isinstance(payload, dict):
            continue
        if record.get("type") == "session_meta" and not meta:
            meta = payload
        elif record.get("type") == "turn_context":
            context = payload
        elif payload.get("type") == "token_count":
            tokens = (payload.get("info") or {}).get("total_token_usage") or tokens

    session_id = meta.get("session_id") or meta.get("id") or ""
    md: list[str] = []
    md.append("# Codex Session Export")
    md.append("")
    md.append("| Key | Value |")
    md.append("|-----|-------|")
    md.append(f"| Session ID | `{session_id}` |")
    md.append(f"| Directory | `{meta.get('cwd', '')}` |")
    if context.get("model"):
        md.append(f"| Model | `{context['model']}` |")
    if context.get("effort"):
        md.append(f"| Effort | `{context['effort']}` |")
    if meta.get("cli_version"):
        md.append(f"| codex Version | `{meta['cli_version']}` |")
    if meta.get("originator"):
        md.append(f"| Originator | `{meta['originator']}` |")
    md.append(f"| Start | {format_timestamp(meta.get('timestamp') or first_ts)} |")
    md.append(f"| End | {format_timestamp(last_ts)} |")
    if tokens:
        md.append(f"| Tokens | input {tokens.get('input_tokens', 0):,}"
                  f" / output {tokens.get('output_tokens', 0):,} |")
    md.append("")
    md.append("---")
    md.append("")

    turn_number = 0
    state: dict = {"call_names": collect_call_names(records), "web_actions": Counter()}
    for record in records:
        payload = record.get("payload") or {}
        item_type = payload.get("type") if isinstance(payload, dict) else None
        block = format_record(record, state)
        if not block:
            continue

        if item_type == "user_message":
            turn_number += 1
            md.append(f"## Turn {turn_number}")
            md.append("")
            md.append("### User")
            md.append(f"*{format_timestamp(record.get('timestamp', ''))}*")
            md.append("")
        elif item_type == "agent_message":
            md.append("### Assistant")
            md.append(f"*{format_timestamp(record.get('timestamp', ''))}*")
            md.append("")

        md.append(block)
        md.append("")

    if turn_number == 0:
        md.append("_No conversation found in this session._")
        md.append("")

    return "\n".join(md)


# ---------------------------------------------------------------------------
# セッション一覧 / エクスポート
# ---------------------------------------------------------------------------

def cmd_list(args: list[str]) -> None:
    project_filter = None
    limit = 10
    cwd_only = False

    i = 0
    while i < len(args):
        if args[i] in ("--project", "-p") and i + 1 < len(args):
            project_filter = args[i + 1]
            i += 2
        elif args[i] in ("--limit", "-n") and i + 1 < len(args):
            try:
                limit = int(args[i + 1])
            except ValueError:
                print(f"Error: --limit の値が不正です: {args[i + 1]}")
                sys.exit(1)
            i += 2
        elif args[i] in ("--cwd", "-c"):
            cwd_only = True
            i += 1
        else:
            project_filter = args[i]
            i += 1

    target_dir = None
    if cwd_only:
        target_dir = str(Path.cwd().resolve())
    elif project_filter:
        target_dir = str(Path(project_filter).expanduser().resolve())

    sessions = []
    for path in iter_session_files(sessions_dir()):
        info = read_session_meta(path)
        if target_dir:
            try:
                resolved = str(Path(info.get("cwd", "")).resolve())
            except OSError:
                resolved = info.get("cwd", "")
            if resolved != target_dir:
                continue
        sessions.append(info)
        if len(sessions) >= limit:
            break

    if not sessions:
        print("セッションが見つかりませんでした。")
        return

    print(f"## codex セッション一覧 (最新{len(sessions)}件)")
    print()
    print("| # | Session ID | Directory | First Message | Date |")
    print("|---|-----------|-----------|---------------|------|")
    for i, s in enumerate(sessions, 1):
        short_id = str(s.get("session_id", ""))[:8] + "..."
        directory = os.path.basename(str(s.get("cwd", "")).rstrip("/\\")) or "-"
        message = escape_table_cell(s.get("firstMessage", ""))[:40]
        date = format_timestamp(s.get("timestamp", ""))[:10]
        print(f"| {i} | `{short_id}` | {directory} | {message} | {date} |")

    print()
    print("Full Session IDs:")
    for i, s in enumerate(sessions, 1):
        directory = os.path.basename(str(s.get("cwd", "")).rstrip("/\\")) or "-"
        date = format_timestamp(s.get("timestamp", ""))[:10]
        message = str(s.get("firstMessage", "")).replace("\n", " ")[:50]
        print(f"  {i}. `{s.get('session_id', '')}` ({directory}, {date}) {message}")


def cmd_export(session_id: str, args: list[str]) -> None:
    output_dir_arg = None
    for i, arg in enumerate(args):
        if arg in ("--output", "-o") and i + 1 < len(args):
            output_dir_arg = args[i + 1]

    path = find_session_file(session_id)
    if path is None:
        print(f"Error: Session '{session_id}' not found.")
        print("Use 'list' subcommand to see available sessions.")
        sys.exit(1)

    markdown = convert_session_to_markdown(path)

    output_dir = Path(output_dir_arg).expanduser() if output_dir_arg else OUTPUT_DIR
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in session_id)[:16]
    output_path = output_dir / f"session_{safe_id}_{timestamp}.md"
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
        size = output_path.stat().st_size
    except OSError as exc:
        print(f"Error: エクスポート先へ書き込めません: {exc}")
        sys.exit(1)

    print(f"Exported to: {output_path}")
    print(f"Size: {size:,} bytes")


def print_usage() -> None:
    print("Usage:")
    print("  codex-export-session.py list [--cwd] [--project PATH] [--limit N]")
    print("  codex-export-session.py <session-id> [--output DIR]")
    print()
    print("Options:")
    print("  list                   List recent codex sessions")
    print("  <session-id>           Export session to markdown")
    print("  --cwd, -c              Filter by current working directory")
    print("  --project, -p PATH     Filter by session directory")
    print("  --limit, -n N          Limit number of sessions (default: 10)")
    print("  --output, -o DIR       Output directory (filename is auto-generated)")


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] in ("--help", "-h"):
        print_usage()
        return 0

    base = sessions_dir()
    if not base.is_dir():
        print(f"Error: codex のセッションディレクトリが見つかりません: {base}")
        print("CODEX_HOME 環境変数でパスを指定できます。")
        return 1

    if args[0] == "list":
        cmd_list(args[1:])
    else:
        cmd_export(args[0], args[1:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
