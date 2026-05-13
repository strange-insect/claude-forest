#!/usr/bin/env python3
"""get-working-set: ワーキングセット (staged + unstaged + untracked) のファイル一覧を出力する。

呼び出し:
    get-working-set.py

引数なし。カレントディレクトリを git リポジトリとして扱う。

stdout に、ワーキングセットに含まれるファイルパス（リポジトリルート相対）を 1 行ずつ出力する。
重複は除去済み。空行は出力しない。

git リポジトリでない、git コマンドが PATH に無い、個別 git コマンドが non-zero 終了、
いずれの場合も例外を握りつぶし、得られた範囲で結果を返す（exit 0）。
"""

from __future__ import annotations

import subprocess
import sys


GIT_COMMANDS: list[list[str]] = [
    ["git", "diff", "--name-only"],                       # unstaged
    ["git", "diff", "--name-only", "--cached"],           # staged
    ["git", "ls-files", "--others", "--exclude-standard"],  # untracked
]


def main() -> int:
    files: set[str] = set()
    for cmd in GIT_COMMANDS:
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode != 0:
            continue
        for line in proc.stdout.splitlines():
            stripped = line.strip()
            if stripped:
                files.add(stripped)

    for path in sorted(files):
        sys.stdout.write(path)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
