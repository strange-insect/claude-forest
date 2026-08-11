#!/usr/bin/env python3
"""opencode-ask: opencode CLI で 1問1答形式の Q&A を実行し、結果を JSON で返す。

呼び出し:
    opencode-ask.py [--session-id ID] [--model MODEL] [--effort EFFORT] --message "質問テキスト"
    opencode-ask.py [--session-id ID] [--model MODEL] [--effort EFFORT]  # stdin からメッセージを読む

stdout には結果 JSON を返す（ask-pipeline.py が受け取る）。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _ask_common as common  # noqa: E402


def _iter_events(jsonl_file: Path):
    """opencode の `--format json` 出力（1 行 1 イベントの JSON）を順に読む。"""
    if not jsonl_file.exists():
        return
    try:
        with jsonl_file.open("r", encoding="utf-8", errors="replace") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return


def extract_opencode_session_id(jsonl_file: Path) -> str:
    """イベントの `sessionID` を抽出する（全イベントに同じ値が入る）。"""
    for rec in _iter_events(jsonl_file):
        sid = rec.get("sessionID")
        if sid:
            return str(sid)
    return "unresolved"


def extract_last_message(jsonl_file: Path) -> str:
    """最後のアシスタントメッセージのテキストを組み立てる。

    codex CLI の `--output-last-message` に相当するものが opencode には無いため、
    `type == "text"` イベントを messageID ごとにまとめ、最後の messageID 分を返す。
    """
    by_message: dict[str, list[str]] = {}
    for rec in _iter_events(jsonl_file):
        if rec.get("type") != "text":
            continue
        part = rec.get("part") or {}
        text = part.get("text")
        if not text:
            continue
        by_message.setdefault(str(part.get("messageID", "")), []).append(str(text))
    if not by_message:
        return ""
    last_id = list(by_message)[-1]
    return "".join(by_message[last_id])


def build_prompt(message: str, session_id: str = "") -> str:
    return message


def main() -> int:
    opencode_path, use_shell = common.resolve_command("opencode")
    if opencode_path == "opencode":
        print(
            "ERROR: 'opencode' コマンドが見つかりません。opencode CLI をインストールしてください。",
            file=sys.stderr,
        )
        return 1

    message, session_id, _flags, overrides = common.parse_args(sys.argv[1:])
    prompt = build_prompt(message, session_id)

    model, effort = common.resolve_model(
        "OPENCODE_ASK_DEFAULT_MODEL", model_contains_slash=True, overrides=overrides
    )

    tmp_jsonl = common.make_temp("opencode-ask-jsonl-")
    tmp_stderr = common.make_temp("opencode-ask-err-")

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

        answer = answer or "（回答の取得に失敗しました - 応答にテキストが含まれていません）"
        common.emit_result(extracted_id, answer, "success", 0)
        return 0
    finally:
        for path in (tmp_jsonl, tmp_stderr):
            common.safe_unlink(path)


if __name__ == "__main__":
    raise SystemExit(main())
