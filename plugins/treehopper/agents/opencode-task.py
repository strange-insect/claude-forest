#!/usr/bin/env python3
"""opencode-task: opencode CLI で ファイル書き込みを含む作業を実行し、結果を JSON で返す。

呼び出し:
    opencode-task.py [--session-id ID] [--inject-fixed-prompt] --message "作業指示"
    opencode-task.py [--session-id ID] [--inject-fixed-prompt]  # stdin からメッセージを読む

stdout には結果 JSON を返す（ask-pipeline.py が受け取る）。

新規セッション時は必ず固定プロンプト（作業報告の形式指定）を先頭に付加する。
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

FIXED_PROMPT = """依頼された作業を実施してください。

作業完了後、以下の形式で作業報告を出力してください。
この報告は呼び出し元が作業内容を把握する唯一の情報源になるため、報告を省略・簡略化しないこと。

【作業報告の形式】

## 指示内容

今回の作業のために受けた指示内容を詳細に記載する。

## 作業結果

### 達成状況
- 完了 / 一部完了 / 未完了 のいずれか
- 達成した完了条件
- 達成できなかった完了条件

指示内容以外の作業を行った場合は以下２点を追加で記載する
- 追加で実施した作業内容
- その作業を実施した理由

## 成果物・変更内容

作成した成果物を記載する
- 成果物を特定する情報（ファイルパス、キーなど）
- 成果物の概要

その他の変更
- 変更対象物
- 変更内容

変更が無い場合は「なし」と記載する。差分そのものは貼らない。

## 作業中に発生した問題・課題

### 発生した問題
作業中に問題や課題が発生した場合は、その内容を記載する。
ファクトのみを記載し、推測や判断は記載しない。

### 対応内容
問題や課題に対して対応した場合は、その内容とその対応を行った理由を詳細に記載する。

## 補足

その他依頼元に伝達すべき情報がある場合は記載する。

【依頼内容】
"""


def build_prompt(message: str, session_id: str = "", inject_fixed_prompt: bool = False) -> str:
    """初回（session_id 無し）は必ず、継続時は inject_fixed_prompt=True の場合のみ固定プロンプトを付加。"""
    if not session_id or inject_fixed_prompt:
        return FIXED_PROMPT + message
    return message


def main() -> int:
    opencode_path, use_shell = common.resolve_command("opencode")
    if opencode_path == "opencode":
        print(
            "ERROR: 'opencode' コマンドが見つかりません。opencode CLI をインストールしてください。",
            file=sys.stderr,
        )
        return 1

    message, session_id, flags = common.parse_args(sys.argv[1:])
    prompt = build_prompt(message, session_id, inject_fixed_prompt=flags.get("inject_fixed_prompt", False))

    tmp_jsonl = common.make_temp("opencode-task-jsonl-")
    tmp_stderr = common.make_temp("opencode-task-err-")

    try:
        opencode_options = [
            "--format",
            "json",
            "--agent",
            "build",
            "--auto",
        ]
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

        answer = answer or "（作業結果の取得に失敗しました - 応答にテキストが含まれていません）"
        common.emit_result(extracted_id, answer, "success", 0)
        return 0
    finally:
        for path in (tmp_jsonl, tmp_stderr):
            common.safe_unlink(path)


if __name__ == "__main__":
    raise SystemExit(main())
