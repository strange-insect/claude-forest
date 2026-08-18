"""claude 用 steering backend。task-supervisor.py から読み込まれる。

Streaming Input モードで起動し、stdin を開いたまま保持する。
これにより実行中のセッションへ user message を追加投入できる。

## 起動と入出力（Claude Code 2.1.231 で実測）

    claude -p --input-format stream-json --output-format stream-json --verbose ...

    stdin  ← {"type":"user","message":{"role":"user","content":[{"type":"text",...}]}}
    stdout → {"type":"system","subtype":"init","session_id":"..."}
             {"type":"assistant","message":{...}}
             {"type":"result","subtype":"success","result":"...","session_id":"..."}

`result` の到着が作業の完了を表す。
"""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _ask_common as common  # noqa: E402

#: 書き込みを許可するツール。claude-ask / claude-review の許可リストに Write / Edit を足したもの。
#: Bash を含むため、ファイル編集に限らず外部コマンドの実行も発生し得る（DESIGN-POLICY）。
ALLOWED_TOOLS = "Read,Glob,Grep,Bash,Write,Edit,WebSearch,WebFetch"

#: ワーカー終了時にプロセスの回収を待つ上限。
SHUTDOWN_WAIT = 10.0


def create(ctx):
    return ClaudeBackend(ctx)


class ClaudeBackend:
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._messages: queue.Queue = queue.Queue()
        self._session_id = str(ctx.meta.get("session_id") or "")
        self._active = False
        self._final_message = ""
        self._error = ""

    # --- supervisor へ公開する状態 -------------------------------------------

    @property
    def active(self) -> bool:
        return self._active

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def final_message(self) -> str:
        return self._final_message

    @property
    def error(self) -> str:
        return self._error

    # --- ライフサイクル -------------------------------------------------------

    def start(self) -> None:
        claude_path, use_shell = common.resolve_command("claude")
        if claude_path == "claude":
            raise RuntimeError(
                "'claude' コマンドが見つかりません。Claude Code CLI をインストールしてください。"
            )

        cmd = [
            claude_path,
            "-p",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--verbose",
        ]
        # 呼び出し時の明示指定 > 環境変数 > CLI 既定、の優先順位で解決する。
        model, effort = common.resolve_model(
            "CLAUDE_TASK_DEFAULT_MODEL",
            overrides={
                "model": str(self.ctx.meta.get("model") or ""),
                "effort": str(self.ctx.meta.get("effort") or ""),
            },
        )
        if model:
            cmd += ["--model", model]
        if effort:
            cmd += ["--effort", effort]

        resume_id = str(self.ctx.meta.get("session_id") or "")
        if resume_id:
            cmd += ["--resume", resume_id]
        else:
            # セッション ID を先に決めておくと、init を待たずに継続用 ID を確定できる。
            self._session_id = str(uuid.uuid4())
            cmd += ["--session-id", self._session_id]

        cmd += ["--dangerously-skip-permissions", "--tools", ALLOWED_TOOLS]

        self._proc = subprocess.Popen(  # noqa: S603
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.ctx.cwd,
            text=True,
            bufsize=1,
            shell=use_shell,
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def send_initial(self, text: str) -> None:
        self._send_user_message(text)
        self._active = True

    def steer(self, text: str) -> tuple[bool, str]:
        """実行中のセッションへ介入する。処理が走っていなければ投入しない。"""
        if not self._active:
            return False, "実行中の作業がありません"
        try:
            self._send_user_message(text)
        except RuntimeError as exc:
            return False, f"追加メッセージの送信に失敗しました: {exc}"
        return True, ""

    def pump(self) -> None:
        while True:
            try:
                message = self._messages.get_nowait()
            except queue.Empty:
                return
            self._handle_message(message)

    def shutdown(self) -> None:
        proc = self._proc
        if proc is None:
            return
        # stdin を閉じると claude は入力の終わりとして正常終了する
        try:
            if proc.stdin is not None:
                proc.stdin.close()
        except OSError:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=SHUTDOWN_WAIT)
            return
        except (OSError, subprocess.TimeoutExpired):
            pass
        try:
            proc.kill()
            # kill 後も wait しないとゾンビプロセスが残る
            proc.wait(timeout=SHUTDOWN_WAIT)
        except (OSError, subprocess.TimeoutExpired) as exc:
            # 生き残っている場合だけ失敗として扱う
            if proc.poll() is None:
                raise RuntimeError(f"ワーカーを終了できませんでした: {exc}") from exc

    # --- 入出力 ---------------------------------------------------------------

    def _send_user_message(self, text: str) -> None:
        self._write_line({
            "type": "user",
            "message": {"role": "user", "content": [{"type": "text", "text": text}]},
        })

    def _write_line(self, payload: dict) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise RuntimeError("claude プロセスが起動していません")
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        with self._lock:
            try:
                proc.stdin.write(line)
                proc.stdin.flush()
            except (OSError, ValueError) as exc:
                raise RuntimeError(f"claude への書き込みに失敗しました: {exc}") from exc

    def _read_stdout(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self._messages.put(json.loads(line))
            except json.JSONDecodeError:
                continue

        if self._active:
            self._error = self._error or "claude プロセスが予期せず終了しました"
        self._active = False

    def _read_stderr(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        for line in proc.stderr:
            line = line.rstrip()
            if line:
                print(f"[claude] {line}", file=sys.stderr)

    # --- メッセージの解釈 -----------------------------------------------------

    def _handle_message(self, message: dict) -> None:
        message_type = str(message.get("type") or "")

        if message_type == "system":
            session_id = str(message.get("session_id") or "")
            if session_id:
                self._session_id = session_id
            return

        if message_type == "result":
            self._active = False
            if message.get("subtype") not in (None, "success"):
                self._error = json.dumps(message, ensure_ascii=False)[:1000]
            result = str(message.get("result") or "").strip()
            if result:
                self._final_message = result
