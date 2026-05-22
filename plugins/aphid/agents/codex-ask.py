#!/usr/bin/env python3
"""codex-ask: OpenAI Codex CLI で 1問1答形式の Q&A を実行し、結果を JSON で返す。

呼び出し:
    codex-ask.py [--session-id UUID] --message "質問テキスト"
    codex-ask.py [--session-id UUID]  # stdin からメッセージを読む

stdout には結果 JSON を返す（ask-pipeline.py が受け取る）。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _ask_common as common  # noqa: E402


def extract_codex_session_id(jsonl_file: Path) -> str:
    """Codex JSONL から `select(.type == "thread.started") | .thread_id` 相当を抽出。"""
    if not jsonl_file.exists():
        return "unresolved"
    try:
        with jsonl_file.open("r", encoding="utf-8", errors="replace") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") == "thread.started":
                    tid = rec.get("thread_id")
                    if tid:
                        return str(tid)
    except OSError:
        return "unresolved"
    return "unresolved"


def build_prompt(message: str, session_id: str = "") -> str:
    return message


def main() -> int:
    codex_path, use_shell = common.resolve_command("codex")
    if codex_path == "codex":
        print(
            "ERROR: 'codex' コマンドが見つかりません。OpenAI Codex CLI をインストールしてください。",
            file=sys.stderr,
        )
        return 1

    message, session_id, _flags = common.parse_args(sys.argv[1:])
    prompt = build_prompt(message, session_id)

    tmp_jsonl = common.make_temp("codex-ask-jsonl-")
    tmp_msg = common.make_temp("codex-ask-msg-")
    tmp_stderr = common.make_temp("codex-ask-err-")

    try:
        codex_options = [
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--full-auto",
            "--json",
        ]
        cmd = [codex_path, "--ask-for-approval", "never", "exec", *codex_options]
        if session_id:
            cmd += ["resume", session_id]
        cmd += ["-o", str(tmp_msg), "-"]

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

        extracted_id = extract_codex_session_id(tmp_jsonl)
        if extracted_id == "unresolved" and session_id:
            extracted_id = session_id

        if exit_code != 0:
            answer = common.read_text(tmp_msg).strip() or "（回答の取得に失敗しました）"
            error_detail = common.format_error_detail(exit_code, tmp_stderr, tmp_jsonl)
            sid = extracted_id if extracted_id != "unresolved" else (session_id or "unresolved")
            common.emit_result(sid, answer, "error", exit_code, error_detail)
            return 1

        answer = common.read_text(tmp_msg) or "（回答の取得に失敗しました - 出力ファイルが空です）"
        common.emit_result(extracted_id, answer, "success", 0)
        return 0
    finally:
        for path in (tmp_jsonl, tmp_msg, tmp_stderr):
            common.safe_unlink(path)


if __name__ == "__main__":
    raise SystemExit(main())
