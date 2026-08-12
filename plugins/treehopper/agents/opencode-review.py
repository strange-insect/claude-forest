#!/usr/bin/env python3
"""opencode-review: opencode CLI でコードレビューを実行し、結果を JSON で返す。

呼び出し:
    opencode-review.py [--session-id ID] [--inject-fixed-prompt] [--model MODEL] [--effort EFFORT] --message "レビュー指示"
    opencode-review.py [--session-id ID] [--inject-fixed-prompt] [--model MODEL] [--effort EFFORT]  # stdin からメッセージを読む

新規セッション時は必ず固定プロンプト（役割・出力ルール・標準観点）を先頭に付加する。
継続セッション時は通常付加しないが、`--inject-fixed-prompt` 指定時のみ付加する。
"""

from __future__ import annotations

import importlib.util as _ilu
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _ask_common as common  # noqa: E402

_spec = _ilu.spec_from_file_location("_opencode_ask", Path(__file__).resolve().parent / "opencode-ask.py")
_m = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_m)  # type: ignore[union-attr]
extract_opencode_session_id = _m.extract_opencode_session_id
extract_last_message = _m.extract_last_message

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
    """出力ルールとレビュー観点は opencode-review-guidelines.txt から読み込む。"""
    return PROMPT_HEADER + common.load_prompt("opencode-review-guidelines.txt") + PROMPT_FOOTER


def build_prompt(message: str, session_id: str = "", inject_fixed_prompt: bool = False) -> str:
    """初回（session_id 無し）は必ず、継続時は inject_fixed_prompt=True の場合のみ固定プロンプトを付加。"""
    if not session_id or inject_fixed_prompt:
        return build_fixed_prompt() + message
    return message


def main() -> int:
    opencode_path, use_shell = common.resolve_command("opencode")
    if opencode_path == "opencode":
        print(
            "ERROR: 'opencode' コマンドが見つかりません。opencode CLI をインストールしてください。",
            file=sys.stderr,
        )
        return 1

    message, session_id, flags, overrides = common.parse_args(sys.argv[1:])
    prompt = build_prompt(message, session_id, inject_fixed_prompt=flags.get("inject_fixed_prompt", False))

    model, effort = common.resolve_model("OPENCODE_REVIEW_DEFAULT_MODEL", overrides=overrides)

    tmp_jsonl = common.make_temp("opencode-review-jsonl-")
    tmp_stderr = common.make_temp("opencode-review-err-")

    try:
        opencode_options = [
            "--format",
            "json",
            "--agent",
            "plan",
        ]
        if model:
            opencode_options += ["-m", model]
        if effort:
            opencode_options += ["--variant", effort]
        cmd = [opencode_path, "run", *opencode_options]
        if session_id:
            cmd += ["--session", session_id]

        with tmp_jsonl.open("wb") as out_fp, tmp_stderr.open("wb") as err_fp:
            proc = subprocess.run(
                cmd,
                input=(prompt + "\n").encode("utf-8"),
                stdout=out_fp,
                stderr=err_fp,
                check=False,
                shell=use_shell,
            )
        exit_code = proc.returncode

        extracted_id = extract_opencode_session_id(tmp_jsonl)
        if extracted_id == "unresolved" and session_id:
            extracted_id = session_id

        answer = extract_last_message(tmp_jsonl)

        if exit_code != 0:
            error_detail = common.format_error_detail(exit_code, tmp_stderr, tmp_jsonl)
            sid = extracted_id if extracted_id != "unresolved" else (session_id or "unresolved")
            common.emit_result(sid, answer.strip() or "（回答の取得に失敗しました）",
                               "error", exit_code, error_detail)
            return 1

        answer = answer or "（レビュー結果の取得に失敗しました - 応答にテキストが含まれていません）"
        common.emit_result(extracted_id, answer, "success", 0)
        return 0
    finally:
        for path in (tmp_jsonl, tmp_stderr):
            common.safe_unlink(path)


if __name__ == "__main__":
    raise SystemExit(main())
