"""codex 用 steering backend。task-supervisor.py から読み込まれる。

`codex app-server` を子プロセスとして保持し、改行区切りの JSON-RPC 2.0 で
会話し続ける。これにより実行中の turn へ `turn/steer` で指示を差し込める。

## プロトコル（codex-cli 0.147.0 で実測）

    → initialize {clientInfo}                        ← {userAgent, codexHome, ...}
    → initialized (notification)
    → thread/start {cwd, sandbox, approvalPolicy}    ← {thread:{id}}
    → turn/start {threadId, input:[{type:"text"}]}   ← {turn:{id}}
    → turn/steer {threadId, expectedTurnId, input}   ← {turnId}

    ← turn/started    {turn:{id}}
    ← item/completed  {item:{type: agentMessage|...}}
    ← turn/completed  {turn:{status, error}}
    ← error

`expectedTurnId` は「実行中の turn がこれであること」の事前条件で、
一致しない場合はリクエストが失敗する。
"""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _ask_common as common  # noqa: E402

#: JSON-RPC リクエストの応答待ち上限。app-server はローカルプロセスなので
#: 通常は即応する。これを超えるのは app-server が死んでいる場合。
REQUEST_TIMEOUT = 20.0

#: ワーカー終了時にプロセスの回収を待つ上限。
SHUTDOWN_WAIT = 10.0

#: サンドボックス。ワークスペース外への書き込みは OS レベルで遮断される（DESIGN-POLICY）。
SANDBOX = "workspace-write"

#: 非対話実行なので承認は求めない。
APPROVAL_POLICY = "never"


def create(ctx):
    return CodexBackend(ctx)


class CodexBackend:
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self._proc: subprocess.Popen | None = None
        self._next_id = 0
        self._lock = threading.Lock()
        self._responses: dict[int, dict] = {}
        self._notifications: queue.Queue = queue.Queue()
        self._thread_id = ""
        self._turn_id = ""
        self._active = False
        self._final_message = ""
        self._error = ""
        #: start() で解決した実効 effort（turn/start で使う）
        self._effort = ""

    # --- supervisor へ公開する状態 -------------------------------------------

    @property
    def active(self) -> bool:
        return self._active

    @property
    def session_id(self) -> str:
        return self._thread_id

    @property
    def final_message(self) -> str:
        return self._final_message

    @property
    def error(self) -> str:
        return self._error

    # --- ライフサイクル -------------------------------------------------------

    def start(self) -> None:
        codex_path, use_shell = common.resolve_command("codex")
        if codex_path == "codex":
            raise RuntimeError(
                "'codex' コマンドが見つかりません。OpenAI Codex CLI をインストールしてください。"
            )

        self._proc = subprocess.Popen(  # noqa: S603
            [codex_path, "app-server"],
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

        self._request("initialize", {
            "clientInfo": {"name": "claude-forest", "title": "claude-forest task", "version": "1"},
        })
        self._notify("initialized", {})

        # 呼び出し時の明示指定 > 環境変数 > CLI 既定、の優先順位で解決する。
        model, self._effort = common.resolve_model(
            "CODEX_TASK_DEFAULT_MODEL",
            overrides={
                "model": str(self.ctx.meta.get("model") or ""),
                "effort": str(self.ctx.meta.get("effort") or ""),
            },
        )
        params: dict[str, object] = {
            "cwd": self.ctx.cwd, "sandbox": SANDBOX, "approvalPolicy": APPROVAL_POLICY,
        }
        if model:
            params["model"] = model

        resume_id = str(self.ctx.meta.get("session_id") or "")
        if resume_id:
            params["threadId"] = resume_id
            result = self._request("thread/resume", params)
        else:
            result = self._request("thread/start", params)

        self._thread_id = str(((result or {}).get("thread") or {}).get("id") or "")
        if not self._thread_id:
            raise RuntimeError(
                f"thread の開始に失敗しました: {json.dumps(result, ensure_ascii=False)[:500]}"
            )

    def send_initial(self, text: str) -> None:
        params: dict[str, object] = {
            "threadId": self._thread_id,
            "input": [{"type": "text", "text": text}],
        }
        if self._effort:
            params["effort"] = self._effort
        result = self._request("turn/start", params)
        self._turn_id = str(((result or {}).get("turn") or {}).get("id") or "")
        self._active = True

    def steer(self, text: str) -> tuple[bool, str]:
        """実行中の turn へ介入する。turn が走っていなければ投入しない。"""
        if not (self._active and self._turn_id):
            return False, "実行中の作業がありません"
        try:
            self._request("turn/steer", {
                "threadId": self._thread_id,
                "expectedTurnId": self._turn_id,
                "input": [{"type": "text", "text": text}],
            })
        except RuntimeError as exc:
            return False, f"turn/steer に失敗しました: {exc}"
        return True, ""

    def pump(self) -> None:
        """溜まった通知を処理する。ブロックしない。"""
        while True:
            try:
                message = self._notifications.get_nowait()
            except queue.Empty:
                return
            self._handle_notification(message)

    def shutdown(self) -> None:
        proc = self._proc
        if proc is None:
            return
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

    # --- JSON-RPC -------------------------------------------------------------

    def _send(self, payload: dict) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise RuntimeError("app-server が起動していません")
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        with self._lock:
            try:
                proc.stdin.write(line)
                proc.stdin.flush()
            except (OSError, ValueError) as exc:
                raise RuntimeError(f"app-server への書き込みに失敗しました: {exc}") from exc

    def _notify(self, method: str, params: dict) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _request(self, method: str, params: dict) -> dict:
        with self._lock:
            self._next_id += 1
            request_id = self._next_id
        event = threading.Event()
        self._responses[request_id] = {"event": event}
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})

        if not event.wait(REQUEST_TIMEOUT):
            self._responses.pop(request_id, None)
            raise RuntimeError(f"{method} が {REQUEST_TIMEOUT:.0f} 秒以内に応答しませんでした")

        slot = self._responses.pop(request_id, {})
        if "error" in slot:
            raise RuntimeError(json.dumps(slot["error"], ensure_ascii=False))
        return slot.get("result") or {}

    def _read_stdout(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue

            if "id" in message and "method" not in message:
                slot = self._responses.get(message["id"])
                if slot is not None:
                    if "error" in message:
                        slot["error"] = message["error"]
                    else:
                        slot["result"] = message.get("result") or {}
                    slot["event"].set()
                continue

            self._notifications.put(message)

        # stdout が閉じた = app-server が終了した
        if self._active:
            self._error = self._error or "app-server が予期せず終了しました"
        self._active = False

    def _read_stderr(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        for line in proc.stderr:
            line = line.rstrip()
            if line:
                print(f"[codex app-server] {line}", file=sys.stderr)

    # --- 通知の解釈 -----------------------------------------------------------

    def _handle_notification(self, message: dict) -> None:
        method = str(message.get("method") or "")
        params = message.get("params") or {}

        if method == "turn/started":
            turn_id = str((params.get("turn") or {}).get("id") or "")
            if turn_id:
                self._turn_id = turn_id
            self._active = True
            return

        if method == "turn/completed":
            # turn/completed は最終状態を伴う。failed を見落とすと、失敗した作業を
            # 正常終了として扱ってしまう。
            self._active = False
            turn = params.get("turn") or {}
            if str(turn.get("status") or "") == "failed":
                error = turn.get("error") or {}
                self._error = (str(error.get("message") or "")
                               or json.dumps(error, ensure_ascii=False))[:1000]
            return

        if method == "error":
            self._error = json.dumps(params, ensure_ascii=False)[:1000]
            self._active = False
            return

        if method == "item/completed":
            item = params.get("item") or {}
            if str(item.get("type") or "") == "agentMessage":
                text = str(item.get("text") or "").strip()
                if text:
                    self._final_message = text
