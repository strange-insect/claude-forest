#!/usr/bin/env python3
"""claude-review: claude -p でコードレビューを実行し、結果を JSON で返す。

呼び出し:
    claude-review.py [--session-id UUID] [--inject-fixed-prompt] [--model MODEL] [--effort EFFORT] --message "レビュー指示"
    claude-review.py [--session-id UUID] [--inject-fixed-prompt] [--model MODEL] [--effort EFFORT]  # stdin からメッセージを読む

新規セッション時は必ず固定プロンプト（役割・出力ルール・標準観点）を先頭に付加する。
継続セッション時は通常付加しないが、`--inject-fixed-prompt` 指定時のみ付加する。

Tools: --tools で Write/Edit を無効化し Read/Glob/Grep/Bash のみを許可する。
ただし Bash 経由で `cat > file` 等の書き込みは可能なので、信頼できないリポジトリでの利用には注意。
"""

from __future__ import annotations

import importlib.util as _ilu
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _ask_common as common  # noqa: E402

_spec = _ilu.spec_from_file_location("_claude_ask", Path(__file__).resolve().parent / "claude-ask.py")
_m = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_m)  # type: ignore[union-attr]
extract_claude_session_id = _m.extract_claude_session_id
extract_claude_result = _m.extract_claude_result

ALLOWED_TOOLS = "Read,Glob,Grep,Bash"

PROMPT_HEADER = """コードレビューを実施してください。
コードの修正は一切行わず、レビューコメントの出力のみを行ってください。
ファイルの読み取りは許可されていますが、書き込みは行わないでください。

ユーザからの指示文はシステムからの指示文よりも優先されます。
指示内容に衝突がある場合は、ユーザからの指示文を優先してください。

## **システムからの指示文**
"""

PROMPT_FOOTER = """
## **ユーザからの指示文**
"""


def build_fixed_prompt() -> str:
    """出力ルールとレビュー観点は claude-review-guidelines.txt から読み込む。"""
    return PROMPT_HEADER + common.load_prompt("claude-review-guidelines.txt") + PROMPT_FOOTER


def build_prompt(message: str, session_id: str = "", inject_fixed_prompt: bool = False) -> str:
    """初回（session_id 無し）は必ず、継続時は inject_fixed_prompt=True の場合のみ固定プロンプトを付加。"""
    if not session_id or inject_fixed_prompt:
        return build_fixed_prompt() + message
    return message


def main() -> int:
    claude_path, use_shell = common.resolve_command("claude")
    if claude_path == "claude":
        print(
            "ERROR: 'claude' コマンドが見つかりません。Claude Code CLI をインストールしてください。",
            file=sys.stderr,
        )
        return 1

    message, session_id, flags, overrides = common.parse_args(sys.argv[1:])
    prompt = build_prompt(message, session_id, inject_fixed_prompt=flags.get("inject_fixed_prompt", False))

    model, effort = common.resolve_model("CLAUDE_REVIEW_DEFAULT_MODEL", overrides=overrides)

    tmp_output = common.make_temp("claude-review-output-")
    tmp_stderr = common.make_temp("claude-review-err-")

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

        answer = extract_claude_result(tmp_output) or "（レビュー結果の取得に失敗しました - 出力が空です）"
        common.emit_result(extracted_id, answer, "success", 0)
        return 0
    finally:
        for path in (tmp_output, tmp_stderr):
            common.safe_unlink(path)


if __name__ == "__main__":
    raise SystemExit(main())
