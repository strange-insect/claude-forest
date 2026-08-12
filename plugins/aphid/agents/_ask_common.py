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


def split_model_spec(raw: str) -> tuple[str, str]:
    """`<model>[,<effort>]` 形式の文字列を (model, effort) に分解する。"""
    raw = raw.strip()
    if not raw:
        return "", ""
    model, _, effort = raw.partition(",")
    return model.strip(), effort.strip()


def resolve_model(
    env_var: str,
    overrides: dict[str, str] | None = None,
) -> tuple[str, str]:
    """使用する (model, effort) を決定する。

    優先順位は「呼び出し時の明示指定 (overrides) > 環境変数 > 未指定」。
    model と effort は独立に上書きされるため、`--model` だけを指定した場合の
    effort は環境変数由来の値（無ければ未指定）のままになる。

    どちらも決まらない場合は ("", "") を返す。呼び出し側はその場合に
    CLI 既定または agent 固有の既定モデルを使う。値の妥当性は検証せず、
    そのまま CLI に渡してエラー報告を CLI 側に委ねる。
    """
    overrides = overrides or {}
    model = str(overrides.get("model", "")).strip()
    effort = str(overrides.get("effort", "")).strip()
    if model and effort:
        return model, effort
    env_model, env_effort = split_model_spec(os.environ.get(env_var, ""))
    return model or env_model, effort or env_effort


def parse_args(argv: list[str]) -> tuple[str, str, dict[str, bool], dict[str, str]]:
    """コマンドライン引数と stdin から (message, session_id, flags, overrides) を取り出す。

    受け付けるオプション:
    - --message / stdin: 送信するメッセージ
    - --session-id: 継続対象のセッション ID
    - --inject-fixed-prompt: 固定プロンプトの挿入を要求するフラグ
    - --model / --effort: 使用するモデルと reasoning effort の明示指定

    flags は agent 別の振る舞いを切り替えるブーリアン辞書。現状のキー:
    - inject_fixed_prompt: agent が定義する固定プロンプト（役割・出力ルール・観点等、agent によって内容は異なる）の
      挿入を明示的に要求するフラグ

    overrides は既定値（環境変数）より優先されるモデル指定。未指定のキーは
    空文字列で、その場合は既定値が使われる。
    """
    message = ""
    session_id = ""
    flags: dict[str, bool] = {"inject_fixed_prompt": False}
    overrides: dict[str, str] = {"model": "", "effort": ""}
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
        elif arg == "--model" and i + 1 < len(argv):
            overrides["model"] = argv[i + 1]
            i += 2
        elif arg == "--effort" and i + 1 < len(argv):
            overrides["effort"] = argv[i + 1]
            i += 2
        else:
            print(f"ERROR: 不明なオプション: {arg}", file=sys.stderr)
            sys.exit(1)
    if not message:
        message = sys.stdin.buffer.read().decode("utf-8")
    if not message:
        print("ERROR: --message または stdin でメッセージを指定してください", file=sys.stderr)
        sys.exit(1)
    return message, session_id, flags, overrides


def load_prompt(name: str) -> str:
    """同じ agents ディレクトリに外出しした固定プロンプト断片を読み込む。

    プロンプト本文はレビュー結果を左右するため、欠落・破損は握りつぶさず例外にする。
    """
    path = Path(__file__).resolve().parent / name
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"プロンプトファイルの読み込みに失敗しました: {path}") from exc


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
