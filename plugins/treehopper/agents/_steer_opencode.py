"""opencode 用 steering backend。task-supervisor.py から読み込まれる。

`opencode serve` を子プロセスとして起動し、HTTP API でセッションを操作する。
これにより実行中のセッションへ `prompt_async` で指示を送り込める。

## API（opencode 1.18.11 で実測）

    POST  /session                        {agent, model, permission} → {id: "ses_..."}
    PATCH /session/{id}                   {permission}（既存の規則へ追記される）
    POST  /session/{id}/prompt_async      {agent, parts:[{type:"text",text}]} → 即座に null
    GET   /session/{id}/message           [{info:{role,time,finish,error}, parts:[...]}, ...]
    GET   /session/status                 {"<session id>": {type: "idle"|"busy"|"retry"}, ...}

完了判定はメッセージのポーリングで行う。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _ask_common as common  # noqa: E402

#: `opencode serve` が待ち受けを始めるまでの待ち上限。
SERVER_START_TIMEOUT = 60.0

#: メッセージ一覧をポーリングする間隔。完了検知の遅延の上限になる。
POLL_INTERVAL = 2.0

#: 操作（セッション作成・prompt_async）の HTTP タイムアウト。
HTTP_TIMEOUT = 20.0

#: ポーリングの HTTP タイムアウト。pump() は非ブロッキングという契約なので、
#: サーバが応答しない場合でも supervisor のループを長く止めない値にする。
POLL_HTTP_TIMEOUT = 5.0

#: ワーカー終了時にプロセスの回収を待つ上限。
SHUTDOWN_WAIT = 10.0

#: 明示的に deny されていない権限要求をすべて許可する。
#: 非対話実行では承認プロンプトに応答できないため（DESIGN-POLICY）。
PERMISSION_RULESET = [{"permission": "*", "pattern": "*", "action": "allow"}]

#: 書き込みを許可する build エージェントを使う。読み取り専用の ask / review は plan を使う。
AGENT = "build"

#: 作業がまだ続いていることを示す finish 理由。ツール呼び出しの区切りで完了扱いにしないため。
NON_TERMINAL_FINISH = {"tool-calls", "tool_calls"}

#: セッションが処理中であることを示す状態。これ以外へ指示を送ると新しい turn が始まる。
BUSY_STATUS = {"busy", "retry"}

#: 起動ログから待ち受けポートを取り出す。
PORT_RE = re.compile(r"http://127\.0\.0\.1:(\d+)")


def create(ctx):
    return OpencodeBackend(ctx)


class OpencodeBackend:
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self._proc: subprocess.Popen | None = None
        self._base = ""
        self._session_id = ""
        self._active = False
        self._final_message = ""
        self._error = ""
        self._last_poll = 0.0
        #: 継続セッションに元から存在していたメッセージ。完了判定と報告収集から除外する。
        self._preexisting_messages: set[str] = set()
        #: start() で解決した実効モデルと variant
        self._model_payload: dict | None = None
        self._variant = ""
        self._port = 0
        self._port_ready = threading.Event()

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
        opencode_path, use_shell = common.resolve_command("opencode")
        if opencode_path == "opencode":
            raise RuntimeError(
                "'opencode' コマンドが見つかりません。opencode CLI をインストールしてください。"
            )

        # --port 0 で空きポートを OS に選ばせ、起動ログから実際のポートを読み取る。
        # 固定ポートだと同時に走る別の run と衝突する。
        self._proc = subprocess.Popen(  # noqa: S603
            [opencode_path, "serve", "--port", "0", "--hostname", "127.0.0.1"],
            cwd=self.ctx.cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            shell=use_shell,
        )
        # stdout を読み続けないとパイプが埋まって opencode serve が停止する。
        threading.Thread(target=self._read_output, daemon=True).start()
        if not self._port_ready.wait(SERVER_START_TIMEOUT):
            raise RuntimeError("opencode serve のポートを特定できませんでした")
        self._base = f"http://127.0.0.1:{self._port}"

        # 呼び出し時の明示指定 > 環境変数 > CLI 既定、の優先順位で解決する。
        model, self._variant = common.resolve_model(
            "OPENCODE_TASK_DEFAULT_MODEL",
            overrides={
                "model": str(self.ctx.meta.get("model") or ""),
                "effort": str(self.ctx.meta.get("effort") or ""),
            },
        )
        self._model_payload = self._build_model_payload(model)

        resume_id = str(self.ctx.meta.get("session_id") or "")
        if resume_id:
            self._session_id = resume_id
            # 継続対象が ask / review のセッションの場合、書き込みが許可されていない。
            # task はワークスペースを変更するため、権限を明示的に上書きする。
            self._call("PATCH", f"/session/{self._session_id}",
                       {"permission": PERMISSION_RULESET})
            self._mark_existing_messages()
            return

        payload: dict[str, object] = {"agent": AGENT, "permission": PERMISSION_RULESET}
        if self._model_payload:
            payload["model"] = self._model_payload
        session = self._call("POST", "/session", payload) or {}
        self._session_id = str(session.get("id") or "")
        if not self._session_id:
            raise RuntimeError("opencode セッションの作成に失敗しました")

    def send_initial(self, text: str) -> None:
        self._prompt(text)
        self._active = True

    def steer(self, text: str) -> tuple[bool, str]:
        """実行中のセッションへ介入する。処理が走っていなければ投入しない。

        `_active` は最大 POLL_INTERVAL 秒前の状態なので、それだけを見て投入すると
        既に終わったセッションに新しい turn を始めてしまう。直前に実状態を問い合わせる。
        """
        if not self._active:
            return False, "実行中の作業がありません"
        try:
            if not self._session_busy():
                return False, "実行中の作業がありません"
            self._prompt(text)
        except RuntimeError as exc:
            return False, f"指示を投入できませんでした: {exc}"
        return True, ""

    def _session_busy(self) -> bool:
        """セッションが処理中かどうかを問い合わせる。idle のセッションは載らない。"""
        statuses = self._call("GET", "/session/status", timeout=POLL_HTTP_TIMEOUT)
        if not isinstance(statuses, dict):
            return False
        entry = statuses.get(self._session_id)
        if not isinstance(entry, dict):
            return False
        return str(entry.get("type") or "") in BUSY_STATUS

    def pump(self) -> None:
        """メッセージ一覧をポーリングして作業報告と完了を取り込む。"""
        now = time.monotonic()
        if now - self._last_poll < POLL_INTERVAL:
            return
        self._last_poll = now

        if not (self._session_id and self._active):
            return
        try:
            messages = self._call("GET", f"/session/{self._session_id}/message",
                                  timeout=POLL_HTTP_TIMEOUT)
        except RuntimeError as exc:
            self._error = f"メッセージの取得に失敗しました: {exc}"
            self._active = False
            return
        if not isinstance(messages, list) or not messages:
            return

        for message in messages:
            self._collect_report(message)

        info = (messages[-1] or {}).get("info") or {}
        if info.get("role") != "assistant":
            return
        # 継続セッションに元からあったメッセージは今回の作業の完了を表さない
        if str(info.get("id") or "") in self._preexisting_messages:
            return

        # 認証エラー・コンテキスト溢れ・出力上限などは error に入る。
        # 見落とすと失敗した作業を正常終了として扱ってしまう。
        if info.get("error"):
            self._error = json.dumps(info["error"], ensure_ascii=False)[:1000]
            self._active = False
            return

        completed = (info.get("time") or {}).get("completed")
        if completed and str(info.get("finish") or "") not in NON_TERMINAL_FINISH:
            self._active = False

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

    # --- 内部 -----------------------------------------------------------------

    def _build_model_payload(self, raw: str) -> dict | None:
        """`provider/model` 形式の指定を API の {providerID, id} へ分解する。

        形式が違う指定を黙って捨てると、指定したつもりのないモデルで作業が進む。
        """
        raw = raw.strip()
        if not raw:
            return None
        if "/" not in raw:
            raise RuntimeError(
                f"opencode のモデルは provider/model 形式で指定してください: {raw}"
            )
        provider, _, model_id = raw.partition("/")
        payload: dict[str, object] = {"providerID": provider, "id": model_id}
        if self._variant:
            payload["variant"] = self._variant
        return payload

    def _mark_existing_messages(self) -> None:
        """継続セッションに既に存在するメッセージを、今回の作業の対象外として記録する。

        これをしないと、前回までの完了済みメッセージを今回の完了と誤認し、
        作業を始めた直後に前回の回答を今回の報告として保存してしまう。
        """
        messages = self._call("GET", f"/session/{self._session_id}/message",
                              timeout=POLL_HTTP_TIMEOUT)
        if not isinstance(messages, list):
            return
        for message in messages:
            message_id = str(((message or {}).get("info") or {}).get("id") or "")
            if message_id:
                self._preexisting_messages.add(message_id)

    def _prompt(self, text: str) -> None:
        payload: dict[str, object] = {
            "agent": AGENT,
            "parts": [{"type": "text", "text": text}],
        }
        if self._model_payload:
            # 継続セッションでも明示指定したモデルを反映させる
            payload["model"] = {
                "providerID": self._model_payload["providerID"],
                "modelID": self._model_payload["id"],
            }
        if self._variant:
            payload["variant"] = self._variant
        self._call("POST", f"/session/{self._session_id}/prompt_async", payload)
        # 次の pump で即座に状況を取りに行く
        self._last_poll = 0.0

    def _read_output(self) -> None:
        """サーバの出力を supervisor.log へ流し、起動時にポートを取り出す。"""
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            if not self._port:
                match = PORT_RE.search(line)
                if match:
                    self._port = int(match.group(1))
                    self._port_ready.set()
            line = line.rstrip()
            if line:
                print(f"[opencode serve] {line}", file=sys.stderr)
        # 起動しないまま終了した場合に start() の待ちを解放する
        self._port_ready.set()

    def _call(self, method: str, path: str, body: dict | None = None,
              timeout: float = HTTP_TIMEOUT):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            self._base + path, data=data, method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise RuntimeError(f"{method} {path}: {exc}") from exc
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def _collect_report(self, message: dict) -> None:
        """assistant メッセージのテキストを作業報告として取り込む。

        同じ part がストリーミングで更新されるため毎回上書きする。
        既読管理を掛けると書きかけのテキストが報告として固定される。
        """
        info = message.get("info") or {}
        if info.get("role") != "assistant":
            return
        if str(info.get("id") or "") in self._preexisting_messages:
            return
        for part in message.get("parts") or []:
            if str(part.get("type") or "") != "text":
                continue
            text = str(part.get("text") or "").strip()
            if text:
                self._final_message = text
