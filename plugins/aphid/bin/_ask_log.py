"""`.llm-ask/` へ Markdown ログを書き出す共通処理。

`ask-pipeline.py`（ask / review）と `task-supervisor.py`（task）が、ログのフォーマット・
ファイル名規約・出力先の決定を共有するためのモジュール。

ログ生成の流れは 3 段:
    1. 中間 JSON を <tempdir>/<prefix>-ask/<stem>.json に書く      (write_json)
    2. save-ask-log.py が JSON を読んで Markdown を生成する        (run_step)
    3. 生成物を .llm-ask/<stem>.md へ原子的に配置する              (atomic_copy)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path


class AskLogError(RuntimeError):
    """ログ生成に失敗した。呼び出し側がユーザー向けメッセージに変換する。"""


def git_toplevel() -> str | None:
    """git リポジトリのルートを返す。リポジトリ外なら None。"""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            check=True,
        )
        return proc.stdout.decode("utf-8", errors="replace").strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def resolve_target_dir(output_dir: str = "") -> Path:
    """ログの出力先を決めて用意する。

    基準ディレクトリは git リポジトリ内ならリポジトリルート、そうでなければカレント。
    新規作成時のみ `*` の .gitignore を同梱する。既存ディレクトリには触らない
    （ユーザーの Git 管理意図を尊重する — DESIGN-POLICY）。
    """
    base_dir = git_toplevel() or os.getcwd()

    if not output_dir:
        target_dir = Path(base_dir) / ".llm-ask"
    elif os.path.isabs(output_dir):
        target_dir = Path(output_dir)
    else:
        target_dir = Path(base_dir) / output_dir

    try:
        if not target_dir.is_dir():
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / ".gitignore").write_text("*\n", encoding="utf-8")
        return target_dir.resolve()
    except OSError as exc:
        raise AskLogError(f"出力先ディレクトリの初期化に失敗しました: {exc}") from exc


def make_file_stem(agent: str) -> str:
    """`<YYYYMMDD_HHMMSS_mmm>_<プロジェクト名>_<agent>` を組み立てる。"""
    now = datetime.now()
    ts = now.strftime("%Y%m%d_%H%M%S_") + f"{now.microsecond // 1000:03d}"
    project = Path.cwd().name or "_"
    return f"{ts}_{project}_{agent}"


def json_staging_dir(agent: str) -> Path:
    """中間 JSON の置き場（<tempdir>/<model>-ask/）を用意して返す。

    save-ask-log.py が Markdown を書く先と同じディレクトリ。0700 を適用するのは
    共用ホストで作業指示を覗かれないようにするため。
    """
    log_prefix = agent.partition("-")[0]
    json_dir = Path(tempfile.gettempdir()) / f"{log_prefix}-ask"
    json_dir.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        try:
            os.chmod(json_dir, 0o700)
        except OSError:
            pass
    return json_dir


def write_json(
    json_path: Path,
    agent: str,
    message: str,
    session_id: str,
    mode: str,
    answer: str,
    status: str,
    exit_code: int,
    error_detail: str = "",
) -> None:
    """JSON ペイロードを json_path に書く。save-ask-log.py が読む形式。"""
    model, _, type_ = agent.partition("-")
    payload: dict[str, object] = {
        "model": model,
        "type": type_ or agent,
        "mode": mode,
        "session_id": session_id or "",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "directory": str(Path.cwd()),
        "project": Path.cwd().name or "_",
        "message": message,
        "answer": answer,
        "status": status,
        "exit_code": exit_code,
    }
    if error_detail:
        payload["error_detail"] = error_detail
    json_path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        json_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    else:
        old_umask = os.umask(0o077)
        try:
            json_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        finally:
            os.umask(old_umask)


def run_step(script: Path, args: list[str]) -> tuple[str, int]:
    """同一 Python インタプリタでスクリプトを実行し (stdout, exit_code) を返す。

    python-wrapper.sh が解決済みのランタイム (sys.executable) をそのまま使うため、
    各ステップで再度ランタイム解決のオーバーヘッドが発生しない。
    """
    try:
        proc = subprocess.run(
            [sys.executable, str(script), *args],
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        print(f"ERROR: {script.name} の実行に失敗しました: {exc}", file=sys.stderr)
        return "", 1
    stderr = proc.stderr.decode("utf-8", errors="replace").strip()
    if stderr:
        print(stderr, file=sys.stderr)
    stdout = proc.stdout.decode("utf-8", errors="replace").strip()
    return stdout, proc.returncode


def safe_unlink(path: Path) -> None:
    """Windows のファイルロックなど OSError を無視してファイルを削除する。"""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def atomic_copy(src: Path, dst: Path) -> None:
    """src を dst に書く。同ディレクトリの一時ファイルへ copy2 してから os.replace() で置換する。

    Windows では直接上書きより FILE_SHARE_DELETE で開かれたファイルへの置換が通りやすい。
    """
    tmp = dst.parent / f".tmp-{dst.name}"
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
    except OSError:
        safe_unlink(tmp)
        raise


def render_markdown(plugin_root: Path, json_path: Path, target_dir: Path) -> tuple[Path, int]:
    """save-ask-log.py で Markdown を生成し target_dir へ配置して (パス, exit_code) を返す。"""
    save_script = plugin_root / "bin" / "save-ask-log.py"
    log_path, exit_code = run_step(save_script, [str(json_path)])
    if not log_path:
        raise AskLogError("save-ask-log.py がパスを返しませんでした")

    source = Path(log_path)
    # 中間 JSON は Markdown が生成できた時点で不要
    if source.is_file():
        safe_unlink(json_path)

    copied_path = target_dir / source.name
    try:
        atomic_copy(source, copied_path)
    except OSError as exc:
        raise AskLogError(f"Markdown ログの配置に失敗しました: {exc}") from exc

    # 一時領域の下書きは恒久保存先へ移した時点で役目を終える（DESIGN-POLICY）
    if source.resolve() != copied_path.resolve():
        safe_unlink(source)
    return copied_path, exit_code
