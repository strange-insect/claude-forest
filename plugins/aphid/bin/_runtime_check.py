#!/usr/bin/env python3
"""Python 層 runtime 検証。

shell 層の共通 wrapper (`python-wrapper.sh`) が選定した候補 Python を、二層探索の
Python 層として本ファイルが受け取り、§2.3 の検証条件を再確認する。

Usage:
    <candidate-python> _runtime_check.py <candidate-path> [--base]

candidate-path には呼び出し時に sys.argv[1] として候補 Python の path を渡す。
本スクリプトは「その path で実行された Python 自身が正当な interpreter か」を
検証するため、内部の subprocess は基本的に sys.executable を使う。

--base を渡すと venv 整合性チェック (§2.5 condition 3) をスキップする。
base Python 候補（pyenv / conda / system の python）は venv 配下でないため
pyvenv.cfg が存在せず、このチェックを通らない。

exit code:
    0  全ての §2.3 条件を満たす
    1  いずれかの条件を満たさない（shell 層に次候補へのフォールスルーを促す）
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REQUIRED_VERSION = (3, 10)


def main() -> int:
    if len(sys.argv) < 2:
        return 1
    candidate = Path(sys.argv[1])
    is_base = "--base" in sys.argv[2:]

    # §2.3 condition 1: ファイル存在
    #   Windows の os.access(X_OK) は信頼できない（finding B1-os-access-xok）ため
    #   is_file() + 後続の --version 成功で代替する。POSIX は os.access(X_OK)。
    if os.name == "nt":
        if not candidate.is_file():
            return 1
    else:
        if not os.access(candidate, os.X_OK):
            return 1

    # §2.3 condition 2: バージョン
    #   `<python> --version` の出力から major.minor を parse する。
    try:
        proc = subprocess.run(
            [str(candidate), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return 1
    if proc.returncode != 0:
        return 1
    # Python 3.4+ は stdout に出力するが、古い Python では stderr に出るため両方を見る。
    version_text = (proc.stdout or "") + (proc.stderr or "")
    m = re.search(r"Python\s+(\d+)\.(\d+)", version_text)
    if not m:
        return 1
    if (int(m.group(1)), int(m.group(2))) < REQUIRED_VERSION:
        return 1

    # §2.3 condition 3: venv 利用可能
    #   `<python> -m venv --help` が returncode 0
    try:
        proc = subprocess.run(
            [str(candidate), "-m", "venv", "--help"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return 1
    if proc.returncode != 0:
        return 1

    # §2.5 condition 3: venv 環境の整合性
    #   候補が plugin venv 配下（`<venv_root>/bin/python3` または `<venv_root>/Scripts/python.exe`）
    #   なら、想定 layout の親に `pyvenv.cfg` が存在することを確認する。
    #   base Python 候補（pyenv / conda / system python）は venv 配下でないため
    #   --base フラグでこのチェックをスキップする。
    if not is_base:
        parent_name = candidate.parent.name
        if parent_name in {"bin", "Scripts"}:
            venv_root = candidate.parent.parent
            if not (venv_root / "pyvenv.cfg").is_file():
                return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
