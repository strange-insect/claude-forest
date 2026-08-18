"""`*-task` の run 状態を扱う共通ヘルパ。

task-control.py（subagent が叩く短命プロセス）と task-supervisor.py（ワーカーの接続を
保持する常駐プロセス）の間の通信路。両者は同一ホスト・同一ユーザーで動くため、
ソケットではなくファイルで受け渡す。

run の状態は OS の一時領域に置き、task-control.py が完了結果を返した時点で削除する。
`CLAUDE_PLUGIN_DATA` は永続領域であり、実行のたびに残ると際限なく肥大化するため使わない。

ディレクトリ構成 (<tempdir>/<cli>-task/<run_id>/):
    meta.json      run の不変情報（agent / cwd / model / 初回プロンプト等）
    status.json    supervisor が更新する現在状態
    command.json   task-control.py → supervisor へ渡す指示
    result.json    supervisor → task-control.py へ返す指示の投入結果
    supervisor.log supervisor の stdout / stderr

書き込みはすべて「一時ファイル + os.replace」で原子的に行う。読み手が
書きかけの JSON を掴むことがないようにするため。
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

# --- run の状態 ---------------------------------------------------------------
STATE_RUNNING = "running"    # ワーカーが作業中
STATE_SUCCESS = "success"    # 作業が完了し、ログを書き終えた
STATE_ERROR = "error"        # ワーカーまたは supervisor が失敗した


def runs_root(cli: str) -> Path:
    """run ディレクトリの親（`<tempdir>/<cli>-task/`）を返す。

    CLI ごとに分けるのは、中間 JSON の `<tempdir>/<cli>-ask/` と揃えるため。
    """
    return Path(tempfile.gettempdir()) / f"{cli}-task"


def new_run_id(agent: str) -> str:
    """別の Bash 呼び出しから同じ run を特定するための識別子を作る。"""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{agent}_{stamp}_{secrets.token_hex(3)}"


def run_dir(run_id: str) -> Path:
    """run_id は `<cli>-task_<日時>_<乱数>` 形式なので、先頭要素から置き場を決められる。"""
    return runs_root(run_id.partition("-")[0]) / run_id


def meta_path(run_id: str) -> Path:
    return run_dir(run_id) / "meta.json"


def status_path(run_id: str) -> Path:
    return run_dir(run_id) / "status.json"


def command_path(run_id: str) -> Path:
    return run_dir(run_id) / "command.json"


def steer_result_path(run_id: str) -> Path:
    return run_dir(run_id) / "result.json"


def supervisor_log_path(run_id: str) -> Path:
    return run_dir(run_id) / "supervisor.log"


def _harden(path: Path) -> None:
    """POSIX で 0700 を適用する。共用ホストで作業指示を覗かれないようにするため。"""
    if os.name == "nt":
        return
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def create(run_id: str, meta: dict) -> None:
    """run ディレクトリを作り、meta.json を書く。"""
    base = run_dir(run_id)
    base.mkdir(parents=True, exist_ok=True)
    _harden(runs_root(run_id.partition("-")[0]))
    _harden(base)
    write_json_atomic(meta_path(run_id), meta)


def discard(run_id: str) -> None:
    """run ディレクトリを削除する。"""
    shutil.rmtree(run_dir(run_id), ignore_errors=True)


def write_json_atomic(path: Path, payload: dict) -> None:
    """同一ディレクトリの一時ファイルへ書いてから os.replace で置換する。

    読み手が書きかけの JSON を掴まないようにするため。umask を絞るのは
    作業指示に機微情報が含まれ得るため。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".tmp-{path.name}-{secrets.token_hex(4)}"
    data = json.dumps(payload, ensure_ascii=False)
    if os.name == "nt":
        tmp.write_text(data, encoding="utf-8")
    else:
        old_umask = os.umask(0o077)
        try:
            tmp.write_text(data, encoding="utf-8")
        finally:
            os.umask(old_umask)
    try:
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def read_json(path: Path) -> dict:
    """JSON を読む。存在しない・書きかけで壊れている場合は空の dict を返す。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return {}


def read_meta(run_id: str) -> dict:
    return read_json(meta_path(run_id))


def read_status(run_id: str) -> dict:
    return read_json(status_path(run_id))


def write_status(run_id: str, **fields: object) -> None:
    """status.json を書く。supervisor だけが呼ぶ。"""
    write_json_atomic(status_path(run_id), fields)


# --- 指示の受け渡し -----------------------------------------------------------
# subagent はフォアグラウンド Bash を順に実行するため、同じ run への指示は
# 常に 1 件ずつしか存在しない。固定ファイル 1 つで足りる。
# ワーカーが受理したかどうかは作業報告に現れないため、supervisor が result.json
# へ結果を書き、task-control.py がそれを読んで呼び出し元へ返す。

def send_steer(run_id: str, text: str) -> None:
    """ワーカーへ渡す指示を置く。前回の投入結果は先に捨てる。"""
    try:
        steer_result_path(run_id).unlink(missing_ok=True)
    except OSError:
        pass
    write_json_atomic(command_path(run_id), {"text": text})


def take_steer(run_id: str) -> str:
    """置かれた指示を取り出す（取り出したファイルは消す）。無ければ空文字列。"""
    path = command_path(run_id)
    command = read_json(path)
    text = str(command.get("text") or "")
    if not text:
        return ""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return ""
    return text


def write_steer_result(run_id: str, accepted: bool, detail: str) -> None:
    """指示をワーカーへ投入できたかどうかを返す。supervisor だけが呼ぶ。"""
    write_json_atomic(steer_result_path(run_id), {"accepted": accepted, "detail": detail})


def read_steer_result(run_id: str) -> dict:
    """投入結果を読む。まだ書かれていなければ空の dict。"""
    return read_json(steer_result_path(run_id))
