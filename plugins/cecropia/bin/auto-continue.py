#!/usr/bin/env python3
"""auto-continue: Stop フックの判定本体。

エージェントの最後の発話が作業宣言・続行確認・作業量を理由とする中断提案で
終わっている場合に、停止をブロックして処理を続行させる。

stdin : Claude Code が渡す Stop フックの payload JSON
stdout: {"decision":"block","reason":"..."} (続行させる場合のみ)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agents"))

import _ask_common as common  # noqa: E402

JUDGE_MODEL = "haiku"

CONTINUE_REASON = "ユーザからの停止指示はありません。処理を続行するか、停止する **必要がある** 場合はその理由を説明してください。"

JUDGE_PROMPT = """以下は AI コーディングエージェントの最後の発話です。エージェントはこの発話の直後に停止し、ユーザの入力待ちになりました。

この停止が次のいずれかに該当するか判定してください。

A) 「これから〇〇します」「次に〇〇を実装します」のように、これから行う作業を宣言しただけで、実行せずに停止している
B) 選択肢を一切提示せず「続行しますか？」「進めてよいですか？」のように、単なる続行確認だけで停止している
C) 作業量が多いことを理由に、続行の確認をしている、または分割・中断・別途実施を推奨して停止している

該当する場合は continue、該当しない場合は stop と出力してください。

以下の場合は必ず stop です。
- 作業が完了し、その結果を報告している
- ユーザに具体的な選択肢を提示して選択を求めている
- ユーザにしか答えられない情報・判断を質問している
- エラーや障害で作業を継続できない状態を報告している
- バックグラウンドで実行中の処理や subagent の完了を待つために停止している

出力は continue または stop のどちらか一語のみとし、他の文字を一切含めないでください。

--- エージェントの最後の発話 ---
"""

# task-notification が伝える tool-use-id を取り出す。バックグラウンド実行の完了はこの通知でのみ伝えられる。
# 通知は completed / failed / stopped / killed のいずれでも届くため、status は見ない。
# 通知本文には subagent の返却テキストが含まれ、そこに tool-use-id が引用されている場合がある。
# 対象の tool-use-id は返却テキストより前に位置するため、通知の開始以降で最初の 1 件を取る。
_NOTIFIED_TOOL_USE_ID = re.compile(
    r"<task-notification>.*?<tool-use-id>([^<]+)</tool-use-id>", re.DOTALL
)

# 非同期起動した subagent の tool_result が持つ toolUseResult.status の値。
_ASYNC_LAUNCHED = "async_launched"


def iter_records(transcript: Path) -> Iterator[dict]:
    """transcript (JSONL) のレコードを記録順に返す。"""
    with transcript.open(encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if line:
                yield json.loads(line)


def notified_tool_use_id(text: str) -> str:
    """task-notification が完了を伝える tool-use-id を返す。通知でなければ空文字を返す。"""
    match = _NOTIFIED_TOOL_USE_ID.search(text)
    return match.group(1) if match else ""


def has_running_background_task(payload: dict) -> bool:
    """payload が伝えるバックグラウンドタスクがあるか判定する。

    background_tasks には実行中のタスクだけが列挙される。
    """
    tasks = payload.get("background_tasks")
    return isinstance(tasks, list) and bool(tasks)


def has_pending_subagent(records: Iterator[dict]) -> bool:
    """実行中の subagent があるか判定する。

    非同期起動した subagent の tool_result は起動の応答として即座に返るため、
    完了は task-notification で伝えられる。停止済みの subagent は SendMessage で
    再開されるため、起動・再開・完了は時系列の状態遷移として扱う。
    """
    agents: set[str] = set()
    pending: set[str] = set()

    for record in records:
        if record.get("type") == "attachment":
            attachment = record.get("attachment") or {}
            if attachment.get("commandMode") == "task-notification":
                pending.discard(notified_tool_use_id(attachment.get("prompt") or ""))
            continue

        content = (record.get("message") or {}).get("content")

        # 通知の多くは user メッセージの本文そのものとして届く。
        # ユーザが会話中に引用した通知と区別するため origin.kind を確認する。
        if isinstance(content, str):
            if (record.get("origin") or {}).get("kind") == "task-notification":
                pending.discard(notified_tool_use_id(content))
            continue

        if not isinstance(content, list):
            continue

        if record.get("type") == "assistant" and not record.get("isSidechain"):
            for block in content:
                if block.get("type") == "tool_use" and block.get("name") == "Agent":
                    agents.add(block["id"])
            continue

        tool_use_result = record.get("toolUseResult")
        if not isinstance(tool_use_result, dict):
            continue

        for block in content:
            if block.get("type") != "tool_result":
                continue
            tool_use_id = block.get("tool_use_id")

            if tool_use_id in agents and tool_use_result.get("status") == _ASYNC_LAUNCHED:
                pending.add(tool_use_id)

            # SendMessage は停止済みの subagent をバックグラウンドで再開させ、
            # 再開した場合にかぎり resumedAgentId を返す。
            # 再開後の task-notification は、再開元の Agent ではなく
            # この SendMessage の tool-use-id で完了を伝える。
            elif tool_use_result.get("resumedAgentId"):
                pending.add(tool_use_id)

    return bool(pending)


def judge(message: str) -> str:
    """Haiku に continue / stop を判定させ、その出力を返す。"""
    claude_path, use_shell = common.resolve_command("claude")
    if claude_path == "claude":
        return ""

    # --safe-mode で子プロセス側のプラグインとフックを無効化し、このフック自身の再帰を防ぐ
    proc = subprocess.run(
        [claude_path, "-p", "--safe-mode", "--model", JUDGE_MODEL, "--max-turns", "1"],
        input=(JUDGE_PROMPT + message + "\n").encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        shell=use_shell,
    )
    return proc.stdout.decode("utf-8", errors="replace").lower()


def main() -> int:
    payload = json.load(sys.stdin)

    # block した結果の再停止で無限に continue し続けないようにする
    if payload.get("stop_hook_active"):
        return 0

    if has_running_background_task(payload):
        return 0

    if has_pending_subagent(iter_records(Path(payload["transcript_path"]))):
        return 0

    message = payload.get("last_assistant_message") or ""
    if not message:
        return 0

    verdict = judge(message)

    # continue を含まない、または continue と stop の両方を含む場合は何も返さない
    if "continue" not in verdict or "stop" in verdict:
        return 0

    json.dump({"decision": "block", "reason": CONTINUE_REASON}, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
