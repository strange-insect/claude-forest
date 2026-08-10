#!/usr/bin/env python3
"""opencode セッション会話エクスポーター

opencode の SQLite ストレージ（`opencode.db`）からセッションの会話を読み出し、
Markdown に変換して一時ディレクトリへ保存する。

使い方:
    opencode-export-session.py list [--cwd] [--project PATH] [--limit N]
    opencode-export-session.py <session-id> [--output DIR]
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

OUTPUT_DIR = Path(tempfile.gettempdir()) / "opencode-sessions"

# ツール結果・ファイル内容の折り返し行数
MAX_OUTPUT_LINES = 50

# 会話としての内容を持たない内部 part（出力しない）
INTERNAL_PART_TYPES = {"step-start", "step-finish", "snapshot"}


# ---------------------------------------------------------------------------
# DB の解決とオープン
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


def data_dir() -> Path:
    """opencode のデータディレクトリ（`Path.data`）を返す。

    opencode は OS による分岐を持たず、`XDG_DATA_HOME` か `~/.local/share` の
    どちらかを使う（Windows でも `%USERPROFILE%\\.local\\share\\opencode`）。
    """
    data_home = env_path("XDG_DATA_HOME")
    base = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    return base / "opencode"


def db_candidates() -> list[Path]:
    """opencode.db の探索候補を優先順に返す。"""
    candidates: list[Path] = []
    base = data_dir()

    # OPENCODE_DB は opencode 本体と同じ解釈（絶対パスならそのまま / 相対ならデータディレクトリ基準）
    override = env_path("OPENCODE_DB")
    if override and override != ":memory:":
        override_path = Path(override).expanduser()
        candidates.append(override_path if override_path.is_absolute() else base / override_path)

    candidates.append(base / "opencode.db")

    # latest / beta / prod 以外のチャンネルでは opencode-<channel>.db になる
    try:
        channel_dbs = sorted(base.glob("opencode-*.db"),
                             key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        channel_dbs = []
    candidates.extend(channel_dbs)

    # 重複除去（順序維持）
    seen: set[str] = set()
    uniq: list[Path] = []
    for path in candidates:
        key = str(path)
        if key not in seen:
            seen.add(key)
            uniq.append(path)
    return uniq


def existing_dbs() -> list[Path]:
    """存在する DB を優先順に返す。

    チャンネルを切り替えた環境では `opencode.db` と `opencode-<channel>.db` が
    共存し得るため、単一の DB で打ち切らず全件を対象にする。
    """
    return [path for path in db_candidates() if path.is_file()]


def open_db(db_path: Path) -> tuple[sqlite3.Connection, Path | None]:
    """DB を読み取り専用で開く。

    opencode 実行中は WAL が有効で読み取り専用オープンに失敗することがあるため、
    その場合は db / -wal / -shm を一時ディレクトリへコピーしてから開く。
    戻り値は (接続, コピー先一時ディレクトリ or None)。
    """
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.execute("select count(*) from session").fetchone()
        return conn, None
    except sqlite3.Error:
        pass

    tmp_dir = Path(tempfile.mkdtemp(prefix="opencode-export-"))
    conn = None
    try:
        copied = tmp_dir / db_path.name
        shutil.copy2(db_path, copied)
        for suffix in ("-wal", "-shm"):
            sidecar = db_path.with_name(db_path.name + suffix)
            if sidecar.exists():
                try:
                    shutil.copy2(sidecar, tmp_dir / sidecar.name)
                except OSError:
                    pass
        conn = sqlite3.connect(f"file:{copied}?mode=ro", uri=True)
        # コピー中に opencode が書き込んでいた場合、コピーが壊れていることがある
        integrity = conn.execute("PRAGMA quick_check(1)").fetchone()
        if integrity and integrity[0] != "ok":
            raise sqlite3.DatabaseError(
                f"コピーしたデータベースの整合性チェックに失敗しました: {integrity[0]}"
            )
        return conn, tmp_dir
    except BaseException:
        # mkdtemp 後の失敗で一時ディレクトリが残らないようにする。
        # Windows は開いたままのファイルを削除できないため、必ず先に接続を閉じる。
        # close() 自体が例外を投げても削除は実行する。
        try:
            if conn is not None:
                conn.close()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def close_db(conn: sqlite3.Connection, tmp_dir: Path | None) -> None:
    try:
        conn.close()
    finally:
        if tmp_dir is not None:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 整形ユーティリティ
# ---------------------------------------------------------------------------

def format_epoch_ms(ts_ms) -> str:
    """エポックミリ秒を読みやすい形式に変換"""
    try:
        dt = datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except (TypeError, ValueError, OSError):
        return str(ts_ms) if ts_ms else ""


def load_json(raw: str) -> dict:
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


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


def model_label(model) -> str:
    """message.data / session.model のモデル情報を文字列化する"""
    if isinstance(model, str):
        return model
    if not isinstance(model, dict):
        return ""
    provider = model.get("providerID") or model.get("provider") or ""
    model_id = model.get("modelID") or model.get("id") or ""
    variant = model.get("variant") or ""
    label = "/".join(part for part in (provider, model_id) if part)
    if variant and variant != "default":
        label = f"{label} ({variant})" if label else variant
    return label


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


# ---------------------------------------------------------------------------
# part の Markdown 化
# ---------------------------------------------------------------------------

def format_tool_part(part: dict) -> str:
    tool_name = part.get("tool", "unknown")
    state = part.get("state") or {}
    status = state.get("status", "")
    title = state.get("title", "")
    tool_input = state.get("input")
    output = state.get("output", "")
    error = state.get("error", "")

    lines = [f"**Tool: {tool_name}**" + (f" — {status}" if status else "")]
    if title:
        lines.append(f"  {escape_table_cell(title)}")

    if isinstance(tool_input, dict) and tool_input:
        if tool_name == "bash" and "command" in tool_input:
            lines.append(fenced(str(tool_input.get("command", "")), "bash"))
            extra = {k: v for k, v in tool_input.items() if k != "command"}
            if extra:
                lines.append(fenced(json.dumps(extra, indent=2, ensure_ascii=False), "json"))
        else:
            input_str = json.dumps(tool_input, indent=2, ensure_ascii=False)
            lines.append(fenced(truncate_lines(input_str), "json"))
    elif tool_input:
        lines.append(fenced(truncate_lines(str(tool_input))))

    if error:
        body = truncate_lines(str(error))
        lines.append(f"<details><summary>Error</summary>\n\n{fenced(body)}\n\n</details>")
    elif output:
        body = truncate_lines(str(output))
        lines.append(f"<details><summary>Result</summary>\n\n{fenced(body)}\n\n</details>")

    # 画像取得や MCP resource の戻り値に付く添付（`data:` URL 等）は本文に展開せず、存在だけ残す
    attachments = state.get("attachments") or []
    if isinstance(attachments, list) and attachments:
        # 直前が </details> の場合、空行を挟まないと HTML block が続いて Markdown として解釈されない
        lines.append("")
        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            name = attachment.get("filename") or attachment.get("uri") or attachment.get("type") or "file"
            mime = attachment.get("mime", "")
            lines.append(f"**Attachment:** `{name}`" + (f" ({mime})" if mime else ""))

    return "\n".join(lines)


def format_part(part: dict) -> str | None:
    """part を Markdown 断片に変換する。出力不要な場合は None を返す。"""
    part_type = part.get("type")

    if part_type == "text":
        text = str(part.get("text", "")).strip()
        return text or None

    if part_type == "reasoning":
        text = str(part.get("text", "")).strip()
        if not text:
            return None
        return f"<details><summary>Thinking</summary>\n\n{text}\n\n</details>"

    if part_type == "tool":
        return format_tool_part(part)

    if part_type == "file":
        filename = part.get("filename") or part.get("url") or ""
        mime = part.get("mime", "")
        return f"**File:** `{filename}`" + (f" ({mime})" if mime else "")

    if part_type == "agent":
        name = part.get("name", "")
        return f"**Agent:** `{name}`" if name else None

    if part_type == "patch":
        files = part.get("files") or []
        if isinstance(files, list) and files:
            listed = "\n".join(f"- `{f}`" for f in files)
            return f"**Patch:**\n{listed}"
        return "**Patch**"

    if part_type == "compaction":
        reason = part.get("reason") or ""
        return "**Compaction checkpoint**" + (f" — {escape_table_cell(reason)}" if reason else "")

    if part_type in INTERNAL_PART_TYPES:
        return None

    # 未知の type は黙って落とさず、欠落したことが分かるようにする
    return f"**Unsupported part type:** `{part_type}`"


# ---------------------------------------------------------------------------
# セッション一覧 / エクスポート
# ---------------------------------------------------------------------------

def list_sessions(conn: sqlite3.Connection, project_filter: str | None, limit: int,
                  cwd_only: bool) -> list[dict]:
    rows = conn.execute(
        "select id, parent_id, slug, directory, title, agent, model,"
        " time_created, time_updated from session order by time_updated desc"
    ).fetchall()

    target_dir = None
    if cwd_only:
        target_dir = str(Path.cwd().resolve())
    elif project_filter:
        target_dir = str(Path(project_filter).expanduser().resolve())

    sessions = []
    for row in rows:
        (sid, parent_id, slug, directory, title, agent, model,
         time_created, time_updated) = row
        if target_dir:
            try:
                resolved = str(Path(directory).resolve())
            except OSError:
                resolved = directory
            if resolved != target_dir:
                continue
        sessions.append({
            "id": sid,
            "parentId": parent_id,
            "slug": slug,
            "directory": directory,
            "title": title,
            "agent": agent,
            "model": model_label(load_json(model) if model else ""),
            "timeCreated": time_created,
            "timeUpdated": time_updated,
        })
        if len(sessions) >= limit:
            break
    return sessions


def fetch_session(conn: sqlite3.Connection, session_id: str) -> dict | None:
    row = conn.execute(
        "select id, parent_id, slug, directory, title, version, agent, model,"
        " cost, tokens_input, tokens_output, tokens_reasoning,"
        " time_created, time_updated from session where id = ?",
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    keys = ("id", "parentId", "slug", "directory", "title", "version", "agent", "model",
            "cost", "tokensInput", "tokensOutput", "tokensReasoning",
            "timeCreated", "timeUpdated")
    return dict(zip(keys, row))


def convert_session_to_markdown(conn: sqlite3.Connection, session: dict) -> str:
    session_id = session["id"]

    messages = conn.execute(
        "select id, time_created, data from message where session_id = ?"
        " order by time_created, id",
        (session_id,),
    ).fetchall()

    parts_by_message: dict[str, list[dict]] = {}
    for message_id, part_data in conn.execute(
        "select message_id, data from part where session_id = ? order by time_created, id",
        (session_id,),
    ):
        parts_by_message.setdefault(message_id, []).append(load_json(part_data))

    children = conn.execute(
        "select id, title from session where parent_id = ? order by time_created",
        (session_id,),
    ).fetchall()

    md: list[str] = []
    md.append("# opencode Session Export")
    md.append("")
    md.append("| Key | Value |")
    md.append("|-----|-------|")
    md.append(f"| Session ID | `{session_id}` |")
    if session.get("title"):
        md.append(f"| Title | {escape_table_cell(session['title'])} |")
    if session.get("slug"):
        md.append(f"| Slug | `{session['slug']}` |")
    md.append(f"| Directory | `{session.get('directory', '')}` |")
    if session.get("agent"):
        md.append(f"| Agent | `{session['agent']}` |")
    model = model_label(load_json(session["model"]) if session.get("model") else "")
    if model:
        md.append(f"| Model | `{model}` |")
    if session.get("version"):
        md.append(f"| opencode Version | `{session['version']}` |")
    if session.get("parentId"):
        md.append(f"| Parent Session | `{session['parentId']}` |")
    md.append(f"| Start | {format_epoch_ms(session.get('timeCreated'))} |")
    md.append(f"| End | {format_epoch_ms(session.get('timeUpdated'))} |")
    tokens_in = session.get("tokensInput") or 0
    tokens_out = session.get("tokensOutput") or 0
    md.append(f"| Tokens | input {tokens_in:,} / output {tokens_out:,} |")
    md.append(f"| Cost | {session.get('cost') or 0} |")
    md.append("")

    if children:
        md.append("## Child Sessions")
        md.append("")
        for child_id, child_title in children:
            md.append(f"- `{child_id}` {escape_table_cell(child_title or '')}")
        md.append("")

    md.append("---")
    md.append("")

    turn_number = 0
    for message_id, time_created, data in messages:
        message = load_json(data)
        role = message.get("role", "")
        ts = (message.get("time") or {}).get("created", time_created)
        parts = parts_by_message.get(message_id, [])

        rendered = [text for text in (format_part(part) for part in parts) if text]

        # 可視 part が無くてもエラーだけは残す（失敗メッセージが丸ごと消えるのを防ぐ）
        error = message.get("error")
        if error:
            detail = error if isinstance(error, str) else json.dumps(error, ensure_ascii=False)
            # fence は行頭から始める必要があるため、ラベルとは行を分ける
            rendered.append(f"**Message error:**\n\n{fenced(truncate_lines(detail))}")

        if not rendered:
            continue

        if role == "user":
            turn_number += 1
            md.append(f"## Turn {turn_number}")
            md.append("")
            md.append("### User")
        else:
            model = model_label(message.get("model") or {})
            if not model:
                provider = message.get("providerID", "")
                model_id = message.get("modelID", "")
                model = "/".join(part for part in (provider, model_id) if part)
            heading = "Assistant" if role == "assistant" else (role or "Message")
            md.append(f"### {heading}" + (f" ({model})" if model else ""))

        if ts:
            md.append(f"*{format_epoch_ms(ts)}*")
        md.append("")

        for block in rendered:
            md.append(block)
            md.append("")

        if role != "user":
            completed = (message.get("time") or {}).get("completed")
            created = (message.get("time") or {}).get("created")
            if completed and created:
                md.append(f"*Turn duration: {(completed - created) / 1000:.1f}s*")
                md.append("")
            md.append("---")
            md.append("")

    if turn_number == 0 and not messages:
        md.append("_No messages found in this session._")
        md.append("")

    return "\n".join(md)


def cmd_list(db_paths: list[Path], args: list[str]) -> None:
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

    # チャンネル DB が共存する場合に備え、全 DB の結果をマージして新しい順に並べる
    merged: dict[str, dict] = {}
    schema_errors: list[tuple[Path, sqlite3.OperationalError]] = []
    readable = 0
    for db_path in db_paths:
        conn, tmp_dir = open_db(db_path)
        try:
            for session in list_sessions(conn, project_filter, limit, cwd_only):
                current = merged.get(session["id"])
                # 同一セッションが複数 DB にある場合は更新が新しい方を採用する
                if current is None or (session["timeUpdated"] or 0) > (current["timeUpdated"] or 0):
                    merged[session["id"]] = session
            readable += 1
        except sqlite3.OperationalError as exc:
            # 旧スキーマの DB は飛ばし、残りの候補を試す
            schema_errors.append((db_path, exc))
        finally:
            close_db(conn, tmp_dir)

    if readable == 0 and schema_errors:
        raise schema_errors[0][1]

    for db_path, exc in schema_errors:
        print(f"Warning: {db_path} は読み取れないためスキップしました: {exc}", file=sys.stderr)

    sessions = sorted(merged.values(), key=lambda s: s["timeUpdated"] or 0, reverse=True)[:limit]
    if not sessions:
        print("セッションが見つかりませんでした。")
        return

    print(f"## opencode セッション一覧 (最新{len(sessions)}件)")
    print()
    print("| # | Session ID | Directory | Title | Agent | Updated |")
    print("|---|-----------|-----------|-------|-------|---------|")
    for i, s in enumerate(sessions, 1):
        short_id = s["id"][:12] + "..."
        directory = os.path.basename(s["directory"].rstrip("/\\")) if s["directory"] else "-"
        title = escape_table_cell(s["title"] or "")[:40]
        agent = s["agent"] or "-"
        updated = format_epoch_ms(s["timeUpdated"])[:16]
        print(f"| {i} | `{short_id}` | {directory} | {title} | {agent} | {updated} |")

    print()
    print("Full Session IDs:")
    for i, s in enumerate(sessions, 1):
        directory = os.path.basename(s["directory"].rstrip("/\\")) if s["directory"] else "-"
        date = format_epoch_ms(s["timeUpdated"])[:10]
        title = (s["title"] or "").replace("\n", " ")[:50]
        print(f"  {i}. `{s['id']}` ({directory}, {date}) {title}")


def cmd_export(db_paths: list[Path], session_id: str, args: list[str]) -> None:
    output_dir_arg = None
    for i, arg in enumerate(args):
        if arg in ("--output", "-o") and i + 1 < len(args):
            output_dir_arg = args[i + 1]

    # 見つかるまで候補 DB を順に試す（チャンネル DB が共存する環境への対応）。
    # 同一セッションが複数 DB にある場合は候補順で先勝ちとする。
    markdown = None
    schema_errors: list[tuple[Path, sqlite3.OperationalError]] = []
    # 対象セッションは見つかったが変換に失敗した DB（not found と区別するため別に持つ）
    matching_errors: list[tuple[Path, sqlite3.OperationalError]] = []
    readable = 0
    for db_path in db_paths:
        conn, tmp_dir = open_db(db_path)
        session = None
        try:
            # 1 回の read transaction にまとめ、session / message / part を同一スナップショットから読む
            conn.execute("BEGIN")
            session = fetch_session(conn, session_id)
            readable += 1
            if session is not None:
                markdown = convert_session_to_markdown(conn, session)
                break
        except sqlite3.OperationalError as exc:
            # 旧スキーマの DB は飛ばし、残りの候補を試す
            schema_errors.append((db_path, exc))
            if session is not None:
                matching_errors.append((db_path, exc))
        finally:
            # rollback が例外を投げても接続クローズと一時ディレクトリ削除は実行する
            try:
                conn.rollback()
            finally:
                close_db(conn, tmp_dir)

    if markdown is None:
        # 対象セッションを持つ DB の変換失敗は、not found ではなくスキーマエラーとして報告する
        if matching_errors:
            raise matching_errors[0][1]
        if readable == 0 and schema_errors:
            raise schema_errors[0][1]

    for db_path, exc in schema_errors:
        print(f"Warning: {db_path} は読み取れないためスキップしました: {exc}", file=sys.stderr)

    if markdown is None:
        print(f"Error: Session '{session_id}' not found.")
        print("Use 'list' subcommand to see available sessions.")
        sys.exit(1)

    output_dir = Path(output_dir_arg).expanduser() if output_dir_arg else OUTPUT_DIR
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in session_id)[:16]
    output_path = output_dir / f"session_{safe_id}_{timestamp}.md"
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
        size = output_path.stat().st_size
    except OSError as exc:
        # DB 側のエラーと混同しないよう、書き込み失敗はここで報告する
        print(f"Error: エクスポート先へ書き込めません: {exc}")
        sys.exit(1)

    print(f"Exported to: {output_path}")
    print(f"Size: {size:,} bytes")


def print_usage() -> None:
    print("Usage:")
    print("  opencode-export-session.py list [--cwd] [--project PATH] [--limit N]")
    print("  opencode-export-session.py <session-id> [--output DIR]")
    print()
    print("Options:")
    print("  list                   List recent opencode sessions")
    print("  <session-id>           Export session to markdown (reasoning blocks included)")
    print("  --cwd, -c              Filter by current working directory")
    print("  --project, -p PATH     Filter by session directory")
    print("  --limit, -n N          Limit number of sessions (default: 10)")
    print("  --output, -o DIR       Output directory (filename is auto-generated)")


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] in ("--help", "-h"):
        print_usage()
        return 0

    db_paths = existing_dbs()
    if not db_paths:
        print("Error: opencode のデータベース (opencode.db) が見つかりません。")
        print("探索した場所:")
        for candidate in db_candidates():
            print(f"  - {candidate}")
        print("OPENCODE_DB 環境変数でパスを直接指定できます。")
        return 1

    try:
        if args[0] == "list":
            cmd_list(db_paths, args[1:])
        else:
            cmd_export(db_paths, args[0], args[1:])
    except sqlite3.OperationalError as exc:
        # 列やテーブルの欠落 = 対応していない opencode のスキーマ
        print(f"Error: opencode のデータベースを読み取れません: {exc}")
        print("この agent が対応していない opencode のスキーマの可能性があります。")
        return 1
    except (sqlite3.Error, OSError) as exc:
        print(f"Error: opencode のデータベースを開けません: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
