#!/usr/bin/env python3
"""task-supervisor: `*-task` のワーカーとの接続を保持し、実行中の指示投入を仲介する。

呼び出し（task-control.py が起動する）:
    task-supervisor.py --run-id <RUN_ID>

## 位置づけ

`*-task` subagent はフォアグラウンド Bash に入っている間、メインエージェントからの
メッセージを処理できない。そのため subagent は `wait` を短く刻んで呼び、
その合間に届いた指示を `steer` で投入する。

ワーカーとの接続は Bash 呼び出しをまたいで保持する必要があるため、このプロセスが
subagent の子プロセスとして常駐して接続を持つ。subagent が終われば道連れで終わる。

作業が終わった時点でログを書き出してワーカーを終了する。

## backend の契約

CLI ごとの差異は `agents/_steer_<cli>.py` の backend に閉じ込める。

    create(ctx) -> Backend      モジュールレベルのファクトリ
    start()                     ワーカーを起動し、セッションを用意する
    send_initial(text)          作業を開始する
    steer(text) -> (bool, str)  実行中の作業へ指示を投入する
    pump()                      ワーカーからの出力を取り込む（ブロックしない）
    shutdown()                  ワーカーを終了する

    active: bool                作業が実行中か
    session_id: str             継続に使えるワーカー側のセッション ID
    final_message: str          作業報告
    error: str                  非空なら致命的エラー
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _ask_log as asklog  # noqa: E402
import _task_run_store as store  # noqa: E402

#: 指示の受け取りと作業完了の検知を行う間隔。
POLL_INTERVAL = 0.2

#: 失敗時にログへ移す supervisor 出力の文字数。
SUPERVISOR_LOG_TAIL_CHARS = 4000


class Context:
    """backend へ渡す実行文脈。"""

    def __init__(self, meta: dict) -> None:
        self.meta = meta
        self.cwd = meta.get("cwd") or os.getcwd()


def _load_backend(plugin_root: Path, agent: str):
    """`agents/_steer_<cli>.py` を読み込む。

    agent 名は `codex-task` のような `<cli>-<type>` 形式なので、先頭要素が CLI 名になる。
    """
    cli = agent.partition("-")[0]
    path = plugin_root / "agents" / f"_steer_{cli}.py"
    if not path.is_file():
        raise RuntimeError(f"backend 実装が見つかりません: {path}")
    spec = importlib.util.spec_from_file_location(f"_steer_{cli}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"backend の読み込みに失敗しました: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tail_supervisor_log(run_id: str) -> str:
    """supervisor とワーカーの出力の末尾を返す。読めない場合は空文字列。"""
    try:
        text = store.supervisor_log_path(run_id).read_text(
            encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    if not text:
        return ""
    if len(text) > SUPERVISOR_LOG_TAIL_CHARS:
        text = "…\n" + text[-SUPERVISOR_LOG_TAIL_CHARS:]
    return f"supervisor ログ:\n{text}"


def _write_log(meta: dict, session_id: str,
               answer: str, error_detail: str) -> str:
    """作業報告を `.llm-ask/` の Markdown ログへ書き出し、パスを返す。"""
    agent = str(meta.get("agent") or "")
    plugin_root = Path(str(meta.get("plugin_root") or ""))
    status = "error" if error_detail else "success"

    target_dir = asklog.resolve_target_dir("")
    file_stem = asklog.make_file_stem(agent)
    json_path = asklog.json_staging_dir(agent) / f"{file_stem}.json"
    asklog.write_json(
        json_path, agent, str(meta.get("initial_prompt") or ""), session_id,
        "continuation" if meta.get("session_id") else "new",
        answer or "（作業報告を取得できませんでした）",
        status, 1 if error_detail else 0, error_detail,
    )
    log_path, _ = asklog.render_markdown(plugin_root, json_path, target_dir)
    return log_path.as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    run_id = args.run_id

    meta = store.read_meta(run_id)
    if not meta:
        print(f"ERROR: meta.json を読めません: {run_id}", file=sys.stderr)
        return 1

    plugin_root = Path(meta.get("plugin_root") or os.environ.get("CLAUDE_PLUGIN_ROOT", ""))
    agent = str(meta.get("agent") or "")
    ctx = Context(meta)

    # ワーカーは指示された作業ディレクトリで動かす。
    # subagent の cwd と一致しない場合があるため明示的に移動する。
    try:
        os.chdir(ctx.cwd)
    except OSError as exc:
        store.write_status(run_id, state=store.STATE_ERROR,
                           error_detail=f"作業ディレクトリへ移動できません: {exc}")
        return 1

    backend = None
    error_detail = ""

    try:
        backend_module = _load_backend(plugin_root, agent)
        backend = backend_module.create(ctx)
        backend.start()
        # 作業を始めてから running を記録する。先に記録すると、その間に届いた指示が
        # まだ作業を持たない backend へ渡されて拒否される。
        backend.send_initial(str(meta.get("initial_prompt") or ""))
        store.write_status(run_id, state=store.STATE_RUNNING, session_id=backend.session_id)

        while backend.active and not backend.error:
            backend.pump()
            text = store.take_steer(run_id)
            if text:
                accepted, detail = backend.steer(text)
                store.write_steer_result(run_id, accepted, detail)
            time.sleep(POLL_INTERVAL)

        backend.pump()
        error_detail = backend.error
    except Exception as exc:
        error_detail = f"{exc}\n{traceback.format_exc()}"

    session_id = getattr(backend, "session_id", "") or str(meta.get("session_id") or "")
    answer = getattr(backend, "final_message", "")

    # ワーカーを終了させてからログを書く。作業中の出力を取りこぼさないため。
    if backend is not None:
        try:
            backend.shutdown()
        except Exception as exc:
            error_detail = "\n".join(part for part in (error_detail, str(exc)) if part)

    # run ディレクトリは wait が結果を返した時点で削除されるため、
    # 失敗時は supervisor の出力もログへ移す。
    if error_detail:
        error_detail = "\n".join(
            part for part in (error_detail, _tail_supervisor_log(run_id)) if part
        )

    try:
        log_path = _write_log(meta, session_id or "unresolved",
                              answer, error_detail)
    except Exception as exc:
        store.write_status(run_id, state=store.STATE_ERROR, session_id=session_id,
                           error_detail=f"ログの書き出しに失敗しました: {exc}")
        return 1

    store.write_status(
        run_id,
        state=store.STATE_ERROR if error_detail else store.STATE_SUCCESS,
        session_id=session_id,
        log_path=log_path,
        error_detail=error_detail,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
