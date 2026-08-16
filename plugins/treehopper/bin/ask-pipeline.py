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
import sys
from pathlib import Path

from filelock import FileLock
from filelock import Timeout as FileLockTimeout

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _ask_log as asklog  # noqa: E402


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


def _cleanup_temp(json_path: Path, placeholder_log: str = "") -> None:
    candidates = [json_path]
    if placeholder_log:
        candidates.append(Path(placeholder_log))
    for path in candidates:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


#: ログ生成の実処理は _ask_log に集約している（task-supervisor.py と共有するため）。
_safe_unlink = asklog.safe_unlink
run_step = asklog.run_step


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
    try:
        target_dir = asklog.resolve_target_dir(output_dir)
    except asklog.AskLogError as exc:
        die(str(exc))

    # --- ファイル名の先決定とプレースホルダー配置 ---
    # pending JSON → save-ask-log → target_dir の順でプレースホルダーを作る。
    # agent 実行後に同じファイル名で上書きされるため、フォーマットが完全に一致する。
    save_script = plugin_root_path / "bin" / "save-ask-log.py"
    file_stem = asklog.make_file_stem(agent)

    mode = "continuation" if session_id else "new"
    built_prompt = _build_agent_prompt(run_script, message, session_id, inject_fixed_prompt)

    try:
        json_path = asklog.json_staging_dir(agent) / f"{file_stem}.json"
        asklog.write_json(json_path, agent, built_prompt, session_id, mode,
                          "（処理中...）", "pending", 0)
    except OSError as exc:
        die(f"プレースホルダー準備に失敗しました: {exc}")

    placeholder_log, _ = run_step(save_script, [str(json_path)])
    placeholder_md = target_dir / f"{file_stem}.md"
    if placeholder_log:
        source = Path(placeholder_log)
        # 配置先と下書きが同じ場合に消すと、配置したファイル自体を消すことになる。
        if source != placeholder_md:
            try:
                asklog.atomic_copy(source, placeholder_md)
            except OSError:
                pass
            else:
                # 一時領域の下書きは恒久保存先へ移した時点で役目を終える（DESIGN-POLICY）
                _safe_unlink(source)

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
        asklog.write_json(json_path, agent, built_prompt, extracted_session_id, mode,
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
        source = Path(log_path)
        copied_path = target_dir / source.name
        asklog.atomic_copy(source, copied_path)
        if copied_path != placeholder_md:
            _safe_unlink(placeholder_md)
        # 一時領域の下書きは恒久保存先へ移した時点で役目を終える（DESIGN-POLICY）。
        # 配置先が下書きと同じ場合に消すと、返すはずのログ自体を消すことになる。
        if copied_path != source:
            _safe_unlink(source)
    except OSError as exc:
        die(f"Markdown ログの配置に失敗しました: {exc}")

    sys.stdout.write(copied_path.as_posix())
    sys.stdout.flush()
    return pipeline_exit


if __name__ == "__main__":
    raise SystemExit(main())
