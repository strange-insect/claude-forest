#!/usr/bin/env python3
"""ask-pipeline: ask 系の処理パイプラインを実行し、Markdown ログファイルパスを返す。

呼び出し (python-wrapper.sh 経由、CLAUDE_PLUGIN_ROOT / CLAUDE_PLUGIN_DATA が必要):
    python-wrapper.sh ask-pipeline.py --agent <name> [--lock-prefix PREFIX] [--session-id SESSION_ID] [--output-dir PATH] [--model MODEL] [--effort EFFORT] --message "msg"
    python-wrapper.sh ask-pipeline.py --agent <name> [--lock-prefix PREFIX] [--session-id SESSION_ID] [--output-dir PATH] [--model MODEL] [--effort EFFORT] <<EOF
    質問テキスト（複数行可）
    EOF

stdout:
    <出力先にコピーされた Markdown ログファイルの絶対パス>

終了コード:
    0: 成功
    1: エラー

各パイプラインステップの exit code を個別に捕捉してエラー内容を含むログを残すため、
ステップ失敗時も可能な限り後続を続行する。
"""

from __future__ import annotations

import atexit
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from filelock import FileLock
from filelock import Timeout as FileLockTimeout


def die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def _build_agent_prompt(
    run_script: Path,
    message: str,
    session_id: str,
    inject_fixed_prompt: bool = False,
) -> str:
    """agentスクリプルの build_prompt を動的importして呼び出す。
    build_prompt が存在しない場合は message をそのまま返す。
    inject_fixed_prompt を受け取れるシグネチャの場合のみ追加で渡す（後方互換）。
    """
    try:
        spec = importlib.util.spec_from_file_location("_agent_tmp", run_script)
        if spec is None or spec.loader is None:
            return message
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        fn = getattr(mod, "build_prompt", None)
        if callable(fn):
            import inspect
            try:
                params = inspect.signature(fn).parameters
            except (TypeError, ValueError):
                params = {}
            if "inject_fixed_prompt" in params:
                return fn(message, session_id, inject_fixed_prompt=inject_fixed_prompt)
            return fn(message, session_id)
    except Exception:
        pass
    return message


def _make_file_stem(agent: str) -> str:
    now = datetime.now()
    ts = now.strftime("%Y%m%d_%H%M%S_") + f"{now.microsecond // 1000:03d}"
    project = Path.cwd().name or "_"
    return f"{ts}_{project}_{agent}"


def _write_json(
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


def _cleanup_temp(json_path: Path, placeholder_log: str = "") -> None:
    candidates = [json_path]
    if placeholder_log:
        candidates.append(Path(placeholder_log))
    for path in candidates:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _safe_unlink(path: Path) -> None:
    """Windows のファイルロックなど OSError を無視してファイルを削除する。"""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _atomic_copy(src: Path, dst: Path) -> None:
    """src を dst に書く。同ディレクトリの一時ファイルへ copy2 してから os.replace() で置換する。
    Windows では直接上書きより FILE_SHARE_DELETE で開かれたファイルへの置換が通りやすい。
    """
    tmp = dst.parent / f".tmp-{dst.name}"
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
    except OSError:
        _safe_unlink(tmp)
        raise


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


def main() -> int:
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not plugin_root:
        die("CLAUDE_PLUGIN_ROOT is required")
    plugin_root_path = Path(plugin_root)

    # --- 引数パース ---
    agent = ""
    lock_prefix = ""
    session_id = ""
    output_dir = ""
    message = ""
    inject_fixed_prompt = False
    model_override = ""
    effort_override = ""

    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--agent" and i + 1 < len(argv):
            agent = argv[i + 1]
            i += 2
        elif arg == "--lock-prefix" and i + 1 < len(argv):
            lock_prefix = argv[i + 1]
            i += 2
        elif arg == "--message" and i + 1 < len(argv):
            message = argv[i + 1]
            i += 2
        elif arg == "--session-id" and i + 1 < len(argv):
            session_id = argv[i + 1]
            i += 2
        elif arg == "--output-dir" and i + 1 < len(argv):
            output_dir = argv[i + 1]
            i += 2
        elif arg == "--inject-fixed-prompt":
            inject_fixed_prompt = True
            i += 1
        elif arg == "--model" and i + 1 < len(argv):
            model_override = argv[i + 1]
            i += 2
        elif arg == "--effort" and i + 1 < len(argv):
            effort_override = argv[i + 1]
            i += 2
        else:
            die(f"不明なオプション: {arg}")

    if not agent:
        die("--agent が指定されていません")
    # パストラバーサル防止: agent 名は英数・ハイフン・アンダースコアのみ許可
    if not re.fullmatch(r"[A-Za-z0-9_-]+", agent):
        die(f"不正な agent 名: {agent}")
    if lock_prefix and not re.fullmatch(r"[A-Za-z0-9_-]+", lock_prefix):
        die(f"不正な lock_prefix: {lock_prefix}")
    if not message:
        message = sys.stdin.buffer.read().decode("utf-8")
    if not message:
        die("--message または stdin でメッセージを指定してください")

    # --- agent スクリプトの解決 ---
    run_script = plugin_root_path / "agents" / f"{agent}.py"
    if not run_script.is_file():
        die(f"agent 実装が見つかりません: {run_script}")

    # --- 排他ロック ---
    # 同じ lock_prefix（未指定時は agent）+ session_id の重複実行を防ぐ。
    # filelock は OS レベルのロックを使うため、プロセスが kill されても自動解放される。
    if session_id:
        plugin_data = os.environ.get("CLAUDE_PLUGIN_DATA", "")
        if plugin_data:
            lock_dir = Path(plugin_data) / "locks"
            lock_dir.mkdir(parents=True, exist_ok=True)
            lock_path = lock_dir / f"{lock_prefix or agent}_{session_id}.lock"
            lock = FileLock(str(lock_path), timeout=0)
            try:
                lock.acquire()
            except FileLockTimeout:
                die(f"重複実行は禁止です: {agent}/{session_id}")
            atexit.register(lock.release)

    # --- 出力先ディレクトリの決定（agent 実行前に行う）---
    # 基準ディレクトリ: git リポジトリ内ならリポジトリルート、そうでなければカレントディレクトリ
    base_dir = git_toplevel() or os.getcwd()

    if not output_dir:
        target_dir = Path(base_dir) / ".llm-ask"
    elif os.path.isabs(output_dir):
        target_dir = Path(output_dir)
    else:
        target_dir = Path(base_dir) / output_dir

    # 新規作成時のみ .gitignore(*) を同梱。既存ディレクトリには触らない（ユーザーの Git 管理意図を尊重）
    try:
        if not target_dir.is_dir():
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / ".gitignore").write_text("*\n", encoding="utf-8")
        target_dir = target_dir.resolve()
    except OSError as exc:
        die(f"出力先ディレクトリの初期化に失敗しました: {exc}")

    # --- ファイル名の先決定とプレースホルダー配置 ---
    # pending JSON → save-ask-log → target_dir の順でプレースホルダーを作る。
    # agent 実行後に同じファイル名で上書きされるため、フォーマットが完全に一致する。
    save_script = plugin_root_path / "bin" / "save-ask-log.py"
    file_stem = _make_file_stem(agent)
    log_prefix = agent.partition("-")[0]
    json_dir = Path(tempfile.gettempdir()) / f"{log_prefix}-ask"
    json_path = json_dir / f"{file_stem}.json"

    mode = "continuation" if session_id else "new"
    built_prompt = _build_agent_prompt(run_script, message, session_id, inject_fixed_prompt)

    try:
        json_dir.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            try:
                os.chmod(json_dir, 0o700)
            except OSError:
                pass
        _write_json(json_path, agent, built_prompt, session_id, mode,
                    "（処理中...）", "pending", 0)
    except OSError as exc:
        die(f"プレースホルダー準備に失敗しました: {exc}")

    placeholder_log, _ = run_step(save_script, [str(json_path)])
    placeholder_md = target_dir / f"{file_stem}.md"
    if placeholder_log:
        try:
            shutil.copy2(placeholder_log, placeholder_md)
        except OSError:
            pass

    # --- パイプライン実行 ---
    pipeline_exit = 0

    # Step 1: agent 実行（stdout に結果 JSON を返す）
    run_args = ["--message", message]
    if session_id:
        run_args += ["--session-id", session_id]
    if inject_fixed_prompt:
        run_args += ["--inject-fixed-prompt"]
    # 未指定時は渡さない（agent 側で既定値が使われる）
    if model_override:
        run_args += ["--model", model_override]
    if effort_override:
        run_args += ["--effort", effort_override]

    agent_stdout, exit_code = run_step(run_script, run_args)
    if exit_code != 0:
        pipeline_exit = exit_code

    # agent stdout をパース
    agent_result: dict = {}
    if agent_stdout:
        try:
            agent_result = json.loads(agent_stdout)
        except json.JSONDecodeError:
            pass

    if not agent_result:
        _cleanup_temp(json_path, placeholder_log)
        _safe_unlink(placeholder_md)
        die(f"agent 実装が結果を返しませんでした: {run_script}", pipeline_exit or 1)

    extracted_session_id = agent_result.get("session_id") or session_id or "unresolved"
    answer = agent_result.get("answer") or "（回答の取得に失敗しました）"
    status = agent_result.get("status") or ("error" if pipeline_exit != 0 else "success")
    result_exit_code = int(agent_result.get("exit_code") or pipeline_exit)
    error_detail = str(agent_result.get("error_detail") or "")

    # プロセス終了コードと payload の整合: agent が success を返した後に finally 等で
    # non-zero 終了した場合はログの status/exit_code を補正する
    if exit_code != 0 and status == "success":
        status = "error"
        result_exit_code = exit_code
        error_detail = error_detail or f"agent process exited with {exit_code} after emitting success payload"

    # Step 1 完了 JSON を書く
    try:
        _write_json(json_path, agent, built_prompt, extracted_session_id, mode,
                    answer, status, result_exit_code, error_detail)
    except OSError as exc:
        _cleanup_temp(json_path, placeholder_log)
        _safe_unlink(placeholder_md)
        die(f"JSON の書き込みに失敗しました: {exc}")

    # Step 2: Markdown ログ生成
    log_path, exit_code = run_step(save_script, [str(json_path)])
    if exit_code != 0:
        pipeline_exit = exit_code
    if not log_path:
        _cleanup_temp(json_path, placeholder_log)
        _safe_unlink(placeholder_md)
        die("save-ask-log.py がパスを返しませんでした", pipeline_exit or 1)

    # --- 中間 JSON ファイルの削除 ---
    if Path(log_path).is_file():
        json_path.unlink(missing_ok=True)

    # --- プレースホルダーを完成 Markdown で上書き ---
    try:
        copied_path = target_dir / Path(log_path).name
        _atomic_copy(Path(log_path), copied_path)
        if copied_path != placeholder_md:
            _safe_unlink(placeholder_md)
    except OSError as exc:
        die(f"Markdown ログの配置に失敗しました: {exc}")

    sys.stdout.write(copied_path.as_posix())
    sys.stdout.flush()
    return pipeline_exit


if __name__ == "__main__":
    raise SystemExit(main())
