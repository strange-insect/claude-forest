#!/usr/bin/env python3
"""Claude Code セッション会話エクスポーター

セッションのJSONLデータをMarkdownに変換する。
"""

from __future__ import annotations

import json
import sys
import os
import re
from datetime import datetime, timezone
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"
HISTORY_FILE = CLAUDE_DIR / "history.jsonl"
OUTPUT_DIR = Path("/tmp/claude-sessions")


def format_timestamp(ts_str: str) -> str:
    """ISO 8601タイムスタンプを読みやすい形式に変換"""
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except (ValueError, AttributeError):
        return str(ts_str) if ts_str else ""


def format_epoch_ms(ts_ms: int) -> str:
    """エポックミリ秒を読みやすい形式に変換"""
    try:
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except (ValueError, OSError):
        return str(ts_ms)


def find_session_file(session_id: str) -> Path | None:
    """セッションIDからJSONLファイルを検索"""
    if not PROJECTS_DIR.exists():
        return None
    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        jsonl_file = project_dir / f"{session_id}.jsonl"
        if jsonl_file.exists():
            return jsonl_file
    return None


def list_sessions(project_filter: str = None, limit: int = 10, cwd_only: bool = False) -> list[dict]:
    """セッション一覧を取得"""
    sessions = {}

    # history.jsonlからセッション情報を集約
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                sid = rec.get("sessionId", "")
                project = rec.get("project", "")
                ts = rec.get("timestamp", 0)
                display = rec.get("display", "")

                if cwd_only and project != os.getcwd():
                    continue
                if project_filter and project != project_filter:
                    continue

                if sid not in sessions:
                    sessions[sid] = {
                        "sessionId": sid,
                        "project": project,
                        "firstMessage": display,
                        "firstTimestamp": ts,
                        "lastTimestamp": ts,
                        "messageCount": 1,
                    }
                else:
                    sessions[sid]["messageCount"] += 1
                    sessions[sid]["lastTimestamp"] = max(sessions[sid]["lastTimestamp"], ts)
                    if ts < sessions[sid]["firstTimestamp"]:
                        sessions[sid]["firstTimestamp"] = ts
                        sessions[sid]["firstMessage"] = display

    # タイムスタンプの降順でソート
    sorted_sessions = sorted(sessions.values(), key=lambda s: s["lastTimestamp"], reverse=True)
    return sorted_sessions[:limit]


def truncate_text(text: str, max_len: int = 200) -> str:
    """テキストを指定文字数で切り詰め"""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def format_tool_use(content_block: dict) -> str:
    """tool_useブロックをMarkdown化"""
    tool_name = content_block.get("name", "Unknown")
    tool_input = content_block.get("input", {})

    lines = [f"**Tool: {tool_name}**"]

    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        desc = tool_input.get("description", "")
        if desc:
            lines.append(f"  {desc}")
        lines.append(f"```bash\n{cmd}\n```")
    elif tool_name == "Read":
        fp = tool_input.get("file_path", "")
        lines.append(f"  `{fp}`")
    elif tool_name == "Write":
        fp = tool_input.get("file_path", "")
        content = tool_input.get("content", "")
        lines.append(f"  `{fp}`")
        if content:
            # 長い場合は先頭と末尾だけ表示
            content_lines = content.split("\n")
            if len(content_lines) > 30:
                shown = "\n".join(content_lines[:15]) + f"\n\n... ({len(content_lines) - 30} lines omitted) ...\n\n" + "\n".join(content_lines[-15:])
            else:
                shown = content
            lines.append(f"```\n{shown}\n```")
    elif tool_name == "Edit":
        fp = tool_input.get("file_path", "")
        old = tool_input.get("old_string", "")
        new = tool_input.get("new_string", "")
        lines.append(f"  `{fp}`")
        lines.append(f"```diff\n- {old}\n+ {new}\n```")
    elif tool_name == "Glob":
        pattern = tool_input.get("pattern", "")
        path = tool_input.get("path", "")
        lines.append(f"  Pattern: `{pattern}`" + (f" in `{path}`" if path else ""))
    elif tool_name == "Grep":
        pattern = tool_input.get("pattern", "")
        path = tool_input.get("path", "")
        lines.append(f"  Pattern: `{pattern}`" + (f" in `{path}`" if path else ""))
    elif tool_name == "Task":
        desc = tool_input.get("description", "")
        lines.append(f"  {desc}")
    elif tool_name == "WebSearch":
        query = tool_input.get("query", "")
        lines.append(f"  Query: `{query}`")
    elif tool_name == "WebFetch":
        url = tool_input.get("url", "")
        lines.append(f"  URL: `{url}`")
    else:
        # その他のツール
        input_str = json.dumps(tool_input, indent=2, ensure_ascii=False)
        if len(input_str) > 500:
            input_str = input_str[:500] + "\n..."
        lines.append(f"```json\n{input_str}\n```")

    return "\n".join(lines)


def format_tool_result(content_block: dict, tool_use_result: dict = None) -> str:
    """tool_resultブロックをMarkdown化"""
    content = content_block.get("content", "")
    is_error = content_block.get("is_error", False)

    if isinstance(content, list):
        # 画像等のリッチコンテンツ
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(item.get("text", ""))
            elif isinstance(item, dict) and item.get("type") == "image":
                text_parts.append("[Image]")
        content = "\n".join(text_parts)

    prefix = "Error" if is_error else "Result"

    # 長い結果は切り詰め
    content_str = str(content)
    content_lines = content_str.split("\n")
    if len(content_lines) > 50:
        content_str = "\n".join(content_lines[:25]) + f"\n\n... ({len(content_lines) - 50} lines omitted) ...\n\n" + "\n".join(content_lines[-25:])

    return f"<details><summary>{prefix}</summary>\n\n```\n{content_str}\n```\n\n</details>"


def convert_session_to_markdown(jsonl_path: Path, include_thinking: bool = False, include_progress: bool = False) -> str:
    """セッションJSONLをMarkdownに変換"""
    records = []
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not records:
        return "# Empty Session\n\nNo records found."

    # セッション情報を抽出
    session_id = ""
    project = ""
    git_branch = ""
    version = ""
    first_ts = ""
    last_ts = ""

    for rec in records:
        if rec.get("type") in ("user", "assistant"):
            if not session_id:
                session_id = rec.get("sessionId", "")
            if not project:
                project = rec.get("cwd", "")
            if not git_branch:
                git_branch = rec.get("gitBranch", "")
            if not version:
                version = rec.get("version", "")
            ts = rec.get("timestamp", "")
            if ts:
                if not first_ts:
                    first_ts = ts
                last_ts = ts

    # Markdown生成
    md_lines = []
    md_lines.append(f"# Session Export")
    md_lines.append("")
    md_lines.append("| Key | Value |")
    md_lines.append("|-----|-------|")
    md_lines.append(f"| Session ID | `{session_id}` |")
    md_lines.append(f"| Project | `{project}` |")
    if git_branch:
        md_lines.append(f"| Branch | `{git_branch}` |")
    if version:
        md_lines.append(f"| Claude Code Version | `{version}` |")
    md_lines.append(f"| Start | {format_timestamp(first_ts)} |")
    md_lines.append(f"| End | {format_timestamp(last_ts)} |")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")

    turn_number = 0

    for rec in records:
        rec_type = rec.get("type")

        if rec_type == "user":
            message = rec.get("message", {})
            content = message.get("content", "")
            ts = rec.get("timestamp", "")

            if isinstance(content, str) and content:
                # ユーザーのテキストメッセージ
                turn_number += 1
                md_lines.append(f"## Turn {turn_number}")
                md_lines.append("")
                md_lines.append(f"### User")
                if ts:
                    md_lines.append(f"*{format_timestamp(ts)}*")
                md_lines.append("")
                md_lines.append(content)
                md_lines.append("")

            elif isinstance(content, list):
                # tool_result（ツール実行結果）
                tool_use_result = rec.get("toolUseResult")
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        md_lines.append(format_tool_result(block, tool_use_result))
                        md_lines.append("")

        elif rec_type == "assistant":
            message = rec.get("message", {})
            content = message.get("content", [])
            ts = rec.get("timestamp", "")
            model = message.get("model", "")
            heading = f"### Assistant ({model})" if model else "### Assistant"

            if not isinstance(content, list):
                continue

            has_visible_content = False
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")

                if block_type == "thinking" and include_thinking:
                    thinking_text = block.get("thinking", "")
                    if thinking_text:
                        if not has_visible_content:
                            md_lines.append(heading)
                            if ts:
                                md_lines.append(f"*{format_timestamp(ts)}*")
                            md_lines.append("")
                            has_visible_content = True
                        md_lines.append(f"<details><summary>Thinking</summary>\n\n{thinking_text}\n\n</details>")
                        md_lines.append("")

                elif block_type == "text":
                    text = block.get("text", "")
                    if text:
                        if not has_visible_content:
                            md_lines.append(heading)
                            if ts:
                                md_lines.append(f"*{format_timestamp(ts)}*")
                            md_lines.append("")
                            has_visible_content = True
                        md_lines.append(text)
                        md_lines.append("")

                elif block_type == "tool_use":
                    if not has_visible_content:
                        md_lines.append(heading)
                        if ts:
                            md_lines.append(f"*{format_timestamp(ts)}*")
                        md_lines.append("")
                        has_visible_content = True
                    md_lines.append(format_tool_use(block))
                    md_lines.append("")

        elif rec_type == "system":
            subtype = rec.get("subtype", "")
            if subtype == "turn_duration":
                duration_ms = rec.get("durationMs", 0)
                if duration_ms:
                    md_lines.append(f"*Turn duration: {duration_ms / 1000:.1f}s*")
                    md_lines.append("")
                    md_lines.append("---")
                    md_lines.append("")

        elif rec_type == "progress" and include_progress:
            pass  # 通常はスキップ

    return "\n".join(md_lines)


def cmd_list(args: list[str]) -> None:
    """セッション一覧表示"""
    project_filter = None
    limit = 10
    cwd_only = False

    i = 0
    while i < len(args):
        if args[i] in ("--project", "-p") and i + 1 < len(args):
            project_filter = str(Path(args[i + 1]).expanduser().resolve())
            i += 2
        elif args[i] in ("--limit", "-n") and i + 1 < len(args):
            limit = int(args[i + 1])
            i += 2
        elif args[i] in ("--cwd", "-c"):
            cwd_only = True
            i += 1
        else:
            # 位置引数をプロジェクトパスとして扱う
            project_filter = str(Path(args[i]).expanduser().resolve())
            i += 1

    sessions = list_sessions(project_filter=project_filter, limit=limit, cwd_only=cwd_only)
    current_session_id = os.environ.get("CLAUDE_SESSION_ID", "")

    if not sessions:
        print("セッションが見つかりませんでした。")
        return

    print(f"## セッション一覧 (最新{len(sessions)}件)")
    print()
    print("| # | Session ID | Project | First Message | Date | Messages |")
    print("|---|-----------|---------|---------------|------|----------|")
    for i, s in enumerate(sessions, 1):
        sid = s["sessionId"][:8] + "..."
        proj = os.path.basename(s["project"]) if s["project"] else "-"
        msg = s["firstMessage"][:40].replace("|", "\\|").replace("\n", " ")
        date = format_epoch_ms(s["firstTimestamp"])[:10]
        count = s["messageCount"]
        marker = " *(current)*" if current_session_id and s["sessionId"] == current_session_id else ""
        print(f"| {i} | `{sid}` | {proj} | {msg} | {date} | {count}{marker} |")

    print()
    print("Full Session IDs:")
    for i, s in enumerate(sessions, 1):
        proj = os.path.basename(s["project"]) if s["project"] else "-"
        date = format_epoch_ms(s["firstTimestamp"])[:10]
        msg = s["firstMessage"][:50].replace("\n", " ")
        marker = " ← current" if current_session_id and s["sessionId"] == current_session_id else ""
        print(f"  {i}. `{s['sessionId']}` ({proj}, {date}) {msg}{marker}")


def cmd_export(session_id: str, args: list[str]) -> None:
    """セッションをMarkdownにエクスポート"""
    include_thinking = True
    output_path_arg = None

    for i, arg in enumerate(args):
        if arg in ("--output", "-o") and i + 1 < len(args):
            output_path_arg = args[i + 1]

    # "current" をカレントセッションIDに解決
    if session_id == "current":
        session_id = os.environ.get("CLAUDE_SESSION_ID", "")
        if not session_id:
            print("Error: CLAUDE_SESSION_ID is not set.")
            sys.exit(1)

    # セッションファイルを検索
    jsonl_path = find_session_file(session_id)
    if not jsonl_path:
        print(f"Error: Session '{session_id}' not found.")
        print("Use 'list' subcommand to see available sessions.")
        sys.exit(1)

    # Markdown変換
    markdown = convert_session_to_markdown(jsonl_path, include_thinking=include_thinking)

    # 出力先決定
    if output_path_arg:
        output_path = Path(output_path_arg)
        if output_path.is_dir():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = output_path / f"session_{session_id[:8]}_{timestamp}.md"
    else:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = OUTPUT_DIR / f"session_{session_id[:8]}_{timestamp}.md"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    print(f"Exported to: {output_path}")
    print(f"Size: {output_path.stat().st_size:,} bytes")


def main():
    args = sys.argv[1:]

    if not args or args[0] in ("--help", "-h"):
        print("Usage:")
        print("  export_session.py list [--cwd] [--project PATH] [--limit N]")
        print("  export_session.py current [--output DIR]")
        print("  export_session.py <session-id> [--output DIR]")
        print()
        print("Options:")
        print("  list                   List recent sessions")
        print("  <session-id>           Export session to markdown (thinking blocks always included)")
        print("  --cwd, -c              Filter by current working directory")
        print("  --output, -o DIR       Output directory (filename is auto-generated)")
        print("  --project, -p PATH     Filter by project path (e.g. ~/projects/foo)")
        print("  --limit, -n N          Limit number of sessions (default: 10)")
        sys.exit(0)

    subcmd = args[0]

    if subcmd == "list":
        cmd_list(args[1:])
    else:
        # セッションIDとして扱う
        cmd_export(subcmd, args[1:])


if __name__ == "__main__":
    main()
