"""ask 系 agent の共通ヘルパ。

shell 側依存 (jq / mktemp / install -d / date '+%3N' / basename) を Python stdlib に
寄せるための薄いユーティリティ。複数の Python スクリプトから直接 import する。
"""

from __future__ import annotations

import errno
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path


def resolve_command(name: str) -> tuple[str, bool]:
    """コマンド名を解決し (実行パス, shell必要フラグ) を返す。

    Windows の npm shim (.cmd) は CreateProcess で直接起動できないため
    shell=True が必要。shutil.which() の結果で判定する。
    見つからない場合は (name, False) を返し、呼び出し元で存在チェックさせる。
    """
    resolved = shutil.which(name)
    if resolved is None:
        return name, False
    if os.name == "nt" and resolved.lower().endswith((".cmd", ".bat")):
        return resolved, True
    return resolved, False


def parse_args(argv: list[str]) -> tuple[str, str, dict[str, bool]]:
    """--message / --session-id / --inject-fixed-prompt / stdin から (message, session_id, flags) を取り出す。

    flags は agent 別の振る舞いを切り替えるブーリアン辞書。現状のキー:
    - inject_fixed_prompt: agent が定義する固定プロンプト（役割・出力ルール・観点等、agent によって内容は異なる）の
      挿入を明示的に要求するフラグ
    """
    message = ""
    session_id = ""
    flags: dict[str, bool] = {"inject_fixed_prompt": False}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--message" and i + 1 < len(argv):
            message = argv[i + 1]
            i += 2
        elif arg == "--session-id" and i + 1 < len(argv):
            session_id = argv[i + 1]
            i += 2
        elif arg == "--inject-fixed-prompt":
            flags["inject_fixed_prompt"] = True
            i += 1
        else:
            print(f"ERROR: 不明なオプション: {arg}", file=sys.stderr)
            sys.exit(1)
    if not message:
        message = sys.stdin.buffer.read().decode("utf-8")
    if not message:
        print("ERROR: --message または stdin でメッセージを指定してください", file=sys.stderr)
        sys.exit(1)
    return message, session_id, flags


def make_temp(prefix: str) -> Path:
    """同一の cleanup 経路で扱える Path を返す（fd は閉じる）。"""
    fd, path = tempfile.mkstemp(prefix=prefix)
    os.close(fd)
    return Path(path)


def format_error_detail(exit_code: int, stderr_path: Path, stdout_path: Path | None = None) -> str:
    """エラー時の詳細情報を組み立てる。answer とは別セクションに出力される前提。"""
    parts = [f"exit code: {exit_code}"]
    if (e := read_text(stderr_path)).strip():
        parts += ["", "stderr:", e]
    if stdout_path and (s := read_text(stdout_path)).strip():
        parts += ["", "stdout (raw):", s]
    return "\n".join(parts)


def safe_unlink(path: Path) -> None:
    """一時ファイルを削除する。Windows のファイルロック (WinError 32/33) のみ握りつぶす。

    握りつぶした場合 path は %TEMP% に残存する。OS の一時領域 cleanup に委ねる。
    """
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        if os.name == "nt" and (
            getattr(exc, "winerror", None) in (32, 33) or exc.errno in {errno.EACCES, errno.EBUSY}
        ):
            return
        raise


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def emit_result(session_id: str, answer: str, status: str, exit_code: int, error_detail: str = "") -> None:
    """agent の処理結果を JSON 形式で stdout に返す。ask-pipeline.py が受け取る。"""
    payload: dict[str, object] = {
        "session_id": session_id,
        "answer": answer,
        "status": status,
        "exit_code": exit_code,
    }
    if error_detail:
        payload["error_detail"] = error_detail
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()
