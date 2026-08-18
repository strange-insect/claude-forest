#!/usr/bin/env python3
"""task-control: `*-task` subagent がワーカーを操作する入口。

呼び出し (python-wrapper.sh 経由、CLAUDE_PLUGIN_ROOT / CLAUDE_PLUGIN_DATA が必要):
    task-control.py start --agent <name> [--session-id ID] [--model M] [--effort E]
                          [--inject-fixed-prompt] [--message TEXT]
    task-control.py wait  --run-id ID
    task-control.py steer --run-id ID [--text TEXT]

`--message` / `--text` を省略した場合は stdin から読む（複数行の指示を heredoc で渡すため）。

    start              → 作業を開始して run_id を返す
    wait               → 完了するか 60 秒経つまで待つ（これを繰り返す）
    steer --text "..." → 実行中の作業へ指示を投入する

`wait` を短く刻むのは、subagent がフォアグラウンド Bash を抜けたときにだけ
メインエージェントからのメッセージを受け取れるため。長い `wait` は
指示を受け付けられない時間をそのまま延ばすことになる。

stdout は subagent がそのまま読めるテキスト。終了コードは 0=正常 / 1=エラー。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _task_run_store as store  # noqa: E402

#: `wait` 1 回あたりの待ち時間。短いほど指示の受付機会が増え、長いほど Bash 呼び出しが減る。
WAIT_SECONDS = 60.0

#: 投入した指示の結果が返るのを待つ間隔。
STEER_POLL_INTERVAL = 0.2

#: 作業が始まる（または起動に失敗する）までの待ち上限。
#: opencode は `serve` の起動に数秒かかるため、余裕を持たせている。
START_TIMEOUT_SECONDS = 120.0

PROMPT_PREFIX = "依頼された作業を実施してください。\n\n"

DEVELOPMENT_GUIDELINES_REFERENCE = (
    "### 開発ガイドライン\n\n"
    "作業を開始する前に次のファイルを読み、記載された内容に従って作業すること。\n"
    "{path}\n\n"
)

DEVELOPMENT_GUIDELINES_DISABLE_VAR = "CLAUDEFOREST_DISABLE_DEVELOPMENT_GUIDELINES"


def die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def _plugin_root() -> Path:
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not root:
        die("CLAUDE_PLUGIN_ROOT is required")
    return Path(root)


def _read_message(explicit: str) -> str:
    """引数か stdin からメッセージを読む。"""
    if explicit:
        return explicit
    return sys.stdin.buffer.read().decode("utf-8")


def _build_initial_prompt(plugin_root: Path, agent: str, message: str,
                          session_id: str, inject_fixed_prompt: bool) -> str:
    """初回（session_id 無し）は必ず、継続時は明示指定時のみ固定プロンプトを付加する。

    固定プロンプト本体（作業報告の形式指定）は `<cli>-task-guidelines.txt` に外出ししている。
    開発ガイドラインは本文を埋め込まず、`development-guidelines.txt` のパスを参照させる。
    """
    if session_id and not inject_fixed_prompt:
        return message
    cli = agent.partition("-")[0]
    path = plugin_root / "agents" / f"{cli}-task-guidelines.txt"
    try:
        guidelines = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        die(f"固定プロンプトの読み込みに失敗しました: {path} ({exc})")
    reference = _development_guidelines_reference(plugin_root)
    return PROMPT_PREFIX + reference + guidelines + "\n【依頼内容】\n" + message


def _development_guidelines_reference(plugin_root: Path) -> str:
    """開発ガイドラインの参照指示を返す。無効化されている場合は空文字を返す。"""
    if os.environ.get(DEVELOPMENT_GUIDELINES_DISABLE_VAR, ""):
        return ""
    # Windows native Python 対応:
    #   str(Path) の C:\... backslash 形式は Git Bash の POSIX util が扱えないため、
    #   as_posix() で C:/... 形式に揃える
    path = (plugin_root / "agents" / "development-guidelines.txt").resolve()
    return DEVELOPMENT_GUIDELINES_REFERENCE.format(path=path.as_posix())


def _print_outcome(run_id: str, status: dict) -> int:
    """完了した run の結果を出力し、run の作業データを削除する。"""
    try:
        if str(status.get("state") or "") == store.STATE_SUCCESS:
            print(f"ログファイル: {status.get('log_path', '')}")
            return 0

        print("作業はエラーで終了しました。")
        detail = str(status.get("error_detail") or "").strip()
        if detail:
            print(detail[:2000])
        if status.get("log_path"):
            print(f"ログファイル: {status['log_path']}")
        return 1
    finally:
        store.discard(run_id)


# --- start --------------------------------------------------------------------

def cmd_start(args: argparse.Namespace) -> int:
    plugin_root = _plugin_root()
    agent = args.agent
    if not re.fullmatch(r"[A-Za-z0-9_-]+", agent):
        die(f"不正な agent 名: {agent}")

    supervisor = plugin_root / "bin" / "task-supervisor.py"
    if not supervisor.is_file():
        die(f"supervisor が見つかりません: {supervisor}")

    message = _read_message(args.message)
    if not message.strip():
        die("--message または stdin で作業指示を指定してください")

    run_id = store.new_run_id(agent)
    store.create(run_id, {
        "agent": agent,
        "plugin_root": str(plugin_root),
        "cwd": os.getcwd(),
        "model": args.model,
        "effort": args.effort,
        "session_id": args.session_id,
        "initial_prompt": _build_initial_prompt(
            plugin_root, agent, message, args.session_id, args.inject_fixed_prompt
        ),
    })

    # supervisor は subagent の子孫プロセスとして起動する。
    # stdout/stderr をログファイルへ向けるのは、パイプが埋まって supervisor が
    # ブロックするのと、呼び出し元の Bash がパイプの閉塞を待つのを避けるため。
    log_path = store.supervisor_log_path(run_id)
    try:
        with log_path.open("wb") as log_fp:
            subprocess.Popen(  # noqa: S603
                [sys.executable, str(supervisor), "--run-id", run_id],
                stdin=subprocess.DEVNULL,
                stdout=log_fp,
                stderr=subprocess.STDOUT,
                cwd=os.getcwd(),
            )
    except OSError as exc:
        # supervisor が動いていない以上、この run を進める手段も片付ける者もいない。
        store.discard(run_id)
        die(f"supervisor の起動に失敗しました: {exc}")

    # 作業が始まるまで待つ。ここで待たないと、起動失敗を検知できないまま
    # wait ループに入ってしまう。
    deadline = time.monotonic() + START_TIMEOUT_SECONDS
    status: dict = {}
    while time.monotonic() < deadline:
        status = store.read_status(run_id)
        if status.get("state"):
            break
        time.sleep(0.2)

    state = str(status.get("state") or "")
    if not state:
        print(f"{START_TIMEOUT_SECONDS:.0f} 秒待っても作業が開始されませんでした。")
        print(f"supervisor ログ: {log_path.as_posix()}")
        return 1

    print(f"run_id: {run_id}")
    if status.get("session_id"):
        print(f"セッションID: {status['session_id']}")
    if state != store.STATE_RUNNING:
        return _print_outcome(run_id, status)
    print("")
    print("作業を開始しました。wait で完了を待ってください。")
    return 0


# --- wait ---------------------------------------------------------------------

def cmd_wait(args: argparse.Namespace) -> int:
    run_id = args.run_id
    if not store.meta_path(run_id).is_file():
        die(f"run が見つかりません: {run_id}")

    deadline = time.monotonic() + WAIT_SECONDS
    status = store.read_status(run_id)
    while time.monotonic() < deadline:
        status = store.read_status(run_id)
        if str(status.get("state") or "") != store.STATE_RUNNING:
            break
        time.sleep(0.5)

    if str(status.get("state") or "") == store.STATE_RUNNING:
        print(f"run_id: {run_id}")
        print("状態: running")
        return 0

    return _print_outcome(run_id, status)


# --- steer --------------------------------------------------------------------

def cmd_steer(args: argparse.Namespace) -> int:
    run_id = args.run_id
    if not store.meta_path(run_id).is_file():
        die(f"run が見つかりません: {run_id}")

    # 空かどうかの判定にだけ strip を使い、投入する値は原文のまま渡す。
    text = _read_message(args.text)
    if not text.strip():
        die("--text または stdin で指示の内容を指定してください")

    store.send_steer(run_id, text)
    print(f"run_id: {run_id}")

    # supervisor がワーカーへ投入した結果を待つ。ここで待たずに戻ると、
    # ワーカーに届かなかった指示を投入できたものとして報告してしまう。
    # 作業が終われば指示は取り出されないまま残るため、run の終了も待ち終わりになる。
    while True:
        result = store.read_steer_result(run_id)
        if result:
            break
        if str(store.read_status(run_id).get("state") or "") != store.STATE_RUNNING:
            print("作業が終了していたため指示は投入されませんでした。")
            return 1
        time.sleep(STEER_POLL_INTERVAL)

    if result.get("accepted"):
        print("指示を投入しました。")
        return 0

    print("指示を投入できませんでした。")
    detail = str(result.get("detail") or "").strip()
    if detail:
        print(detail)
    return 1


# --- entry --------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", add_help=False)
    p_start.add_argument("--agent", required=True)
    p_start.add_argument("--message", default="")
    p_start.add_argument("--session-id", default="")
    p_start.add_argument("--model", default="")
    p_start.add_argument("--effort", default="")
    p_start.add_argument("--inject-fixed-prompt", action="store_true")
    p_start.set_defaults(func=cmd_start)

    p_wait = sub.add_parser("wait", add_help=False)
    p_wait.add_argument("--run-id", required=True)
    p_wait.set_defaults(func=cmd_wait)

    p_steer = sub.add_parser("steer", add_help=False)
    p_steer.add_argument("--run-id", required=True)
    p_steer.add_argument("--text", default="")
    p_steer.set_defaults(func=cmd_steer)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
