#!/usr/bin/env python3
"""claude-ask: claude -p で 1問1答形式の Q&A を実行し、結果を JSON で返す。

呼び出し:
    claude-ask.py [--session-id UUID] [--model MODEL] [--effort EFFORT] --message "質問テキスト"
    claude-ask.py [--session-id UUID] [--model MODEL] [--effort EFFORT]  # stdin からメッセージを読む

Tools: --tools で Write/Edit を無効化し Read/Glob/Grep/Bash/WebSearch/WebFetch のみを許可する。
ただし Bash 経由で `cat > file` 等の書き込みは可能なので、信頼できないリポジトリでの利用には注意。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _ask_common as common  # noqa: E402

ALLOWED_TOOLS = "Read,Glob,Grep,Bash,WebSearch,WebFetch"


def extract_claude_session_id(json_file: Path) -> str:
    """`claude -p --output-format json` 出力から .session_id を抽出。"""
    if not json_file.exists():
        return "unresolved"
    try:
        text = json_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "unresolved"
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return "unresolved"
    sid = data.get("session_id") or ""
    return sid if sid else "unresolved"


def extract_claude_result(json_file: Path) -> str:
    """`claude -p --output-format json` 出力から .result を抽出。"""
    if not json_file.exists():
        return ""
    try:
        text = json_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return ""
    return data.get("result") or ""


def build_prompt(message: str, session_id: str = "") -> str:
    return message


def main() -> int:
    claude_path, use_shell = common.resolve_command("claude")
    if claude_path == "claude":
        print(
            "ERROR: 'claude' コマンドが見つかりません。Claude Code CLI をインストールしてください。",
            file=sys.stderr,
        )
        return 1

    message, session_id, _flags, overrides = common.parse_args(sys.argv[1:])
    prompt = build_prompt(message, session_id)

    model, effort = common.resolve_model("CLAUDE_ASK_DEFAULT_MODEL", overrides=overrides)

    tmp_output = common.make_temp("claude-ask-output-")
    tmp_stderr = common.make_temp("claude-ask-err-")

    try:
        cmd = [
            claude_path,
            "-p",
            "--output-format",
            "json",
        ]
        if model:
            cmd += ["--model", model]
        if effort:
            cmd += ["--effort", effort]
        if session_id:
            cmd += ["--resume", session_id]
        cmd += [
            "--dangerously-skip-permissions",
            "--tools",
            ALLOWED_TOOLS,
        ]

        with tmp_output.open("wb") as out_fp, tmp_stderr.open("wb") as err_fp:
            proc = subprocess.run(
                cmd,
                input=(prompt + "\n").encode("utf-8"),
                stdout=out_fp,
                stderr=err_fp,
                check=False,
                shell=use_shell,
            )
        exit_code = proc.returncode

        extracted_id = extract_claude_session_id(tmp_output)
        if extracted_id == "unresolved" and session_id:
            extracted_id = session_id

        if exit_code != 0:
            answer = extract_claude_result(tmp_output).strip() or "（回答の取得に失敗しました）"
            error_detail = common.format_error_detail(exit_code, tmp_stderr, tmp_output)
            sid = extracted_id if extracted_id != "unresolved" else (session_id or "unresolved")
            common.emit_result(sid, answer, "error", exit_code, error_detail)
            return 1

        answer = extract_claude_result(tmp_output) or "（回答の取得に失敗しました - 出力が空です）"
        common.emit_result(extracted_id, answer, "success", 0)
        return 0
    finally:
        for path in (tmp_output, tmp_stderr):
            common.safe_unlink(path)


if __name__ == "__main__":
    raise SystemExit(main())
