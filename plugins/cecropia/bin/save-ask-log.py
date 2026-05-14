#!/usr/bin/env python3
"""save-ask-log: ask 系の中間 JSON を読んで Markdown ログを生成する。

呼び出し:
    save-ask-log.py <json-file-path>

stdout に Markdown ログファイルの絶対パスを 1 行で返す。
保存先は <tempdir>/<model>-ask/<basename>.md。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


def die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def main() -> int:
    if len(sys.argv) != 2:
        die("使い方: save-ask-log.py <json-file-path>")

    json_path = Path(sys.argv[1])
    if not json_path.is_file():
        die(f"JSON ファイルが見つかりません: {json_path}")

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        die(f"JSON の解析に失敗しました: {exc}")
        return 1

    model = data.get("model") or data.get("type") or ""
    type_ = data.get("type", "")
    mode = data.get("mode") or "new"
    session_id = data.get("session_id", "")
    timestamp = data.get("timestamp", "")
    directory = data.get("directory", "")
    message = data.get("message", "")
    answer = data.get("answer", "")
    status = data.get("status", "")
    exit_code = data.get("exit_code", 0)
    error_detail = data.get("error_detail", "")

    label_map = {"codex": "Codex", "opus": "Opus"}
    label = label_map.get(model, model)

    type_map = {"ask": "Ask", "review": "Review"}
    skill_label = type_map.get(type_, (type_[:1].upper() + type_[1:]) if type_ else "")

    # 保存先（<tempdir>/<model>-ask/）と Markdown ファイルパス
    # _ask_common.ensure_save_dir と同じ 0700 を適用する（共用ホストでの覗き見回避）
    save_dir = Path(tempfile.gettempdir()) / f"{model}-ask"
    save_dir.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        try:
            os.chmod(save_dir, 0o700)
        except OSError:
            pass

    base = json_path.stem  # ".json" を取った名前
    md_path = save_dir / f"{base}.md"

    lines: list[str] = []
    lines.append(f"# {label} {skill_label} Log")
    lines.append("")
    lines.append(f"- **日時**: {timestamp}")
    lines.append(f"- **モード**: {mode}")
    lines.append(f"- **ディレクトリ**: {directory}")
    lines.append(f"- **セッションID**: {session_id}")
    if status == "error":
        lines.append(f"- **ステータス**: エラー (exit code: {exit_code})")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## メッセージ")
    lines.append("")
    lines.append(message)
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"## {label} の回答")
    lines.append("")
    lines.append(answer)
    lines.append("")

    if error_detail:
        lines.append("---")
        lines.append("")
        lines.append("## エラー情報")
        lines.append("")
        lines.append(error_detail)
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    # Windows native Python 対応:
    #   - text mode `\n` → `\r\n` 翻訳を避けるため改行を出さず sys.stdout.write を使う
    #   - str(Path) の C:\... backslash 形式は Git Bash の POSIX util が扱えないため、
    #     as_posix() で C:/... 形式に揃える
    sys.stdout.write(md_path.as_posix())
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
