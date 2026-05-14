#!/usr/bin/env python3
"""md-convert: Markdown 中の PlantUML コードブロック ⇔ Kroki 画像 URL を相互変換する。

呼び出し:
    md_convert.py to-url  <file.md>     # ```puml ブロックを Kroki SVG URL に置換
    md_convert.py to-code <file.md>     # Kroki PlantUML URL を ```puml ブロックに置換

stdout に変換結果を返す（入力ファイルは変更しない）。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent

# 同階層の sibling .py を `sys.executable` で起動する。python-wrapper.sh 経由で
# 既に走っているため sys.executable がそのまま正しい interpreter になる。共通 wrapper
# 経由で再度起動するのは無駄な process 層なので、直接 subprocess する。
GENERATE_SCRIPT = str(SCRIPT_DIR / "generate_puml_url.py")
DECODE_SCRIPT = str(SCRIPT_DIR / "decode_puml_url.py")


def die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def to_url(content: str) -> str:
    pattern = re.compile(
        r"^([ \t]*)```(?:puml|plantuml)\s*\n(.*?)^\1```\s*$",
        re.MULTILINE | re.DOTALL,
    )

    def replace_block(m: re.Match[str]) -> str:
        indent = m.group(1)
        source = m.group(2).rstrip("\n")
        try:
            result = subprocess.run(
                [sys.executable, GENERATE_SCRIPT],
                input=source,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
            if result.returncode != 0:
                err = result.stderr.strip()
                print(
                    f"WARNING: encode failed, keeping original block: {err}",
                    file=sys.stderr,
                )
                return m.group(0)
            url = result.stdout.strip()
            return f"{indent}![PlantUML]({url})"
        except Exception as exc:
            print(
                f"WARNING: encode error, keeping original block: {exc}",
                file=sys.stderr,
            )
            return m.group(0)

    return pattern.sub(replace_block, content)


def to_code(content: str) -> str:
    # Match: ![...](https://.../plantuml/svg/ENCODED) or bare URL on its own line
    # Host is not fixed (supports kroki.io and self-hosted servers).
    # Image syntax is whole-line only to avoid breaking inline content.
    pattern = re.compile(
        r"^([ \t]*)!\[([^\]]*)\]\((https?://[^)\s]+/plantuml/(?:svg|png|txt)/[^)\s]+)\)\s*$"
        r"|"
        r"^([ \t]*)(https?://[^\s]+/plantuml/(?:svg|png|txt)/[^\s]+)\s*$",
        re.MULTILINE,
    )

    def replace_url(m: re.Match[str]) -> str:
        if m.group(1) is not None:
            indent = m.group(1)
            url = m.group(3)
        else:
            indent = m.group(4) or ""
            url = m.group(5)
        try:
            result = subprocess.run(
                [sys.executable, DECODE_SCRIPT, url],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
            if result.returncode != 0:
                err = result.stderr.strip()
                print(
                    f"WARNING: decode failed, keeping original: {err}",
                    file=sys.stderr,
                )
                return m.group(0)
            source = result.stdout.rstrip("\n")
            lines = source.split("\n")
            indented = "\n".join(indent + line if line else line for line in lines)
            return f"{indent}```puml\n{indented}\n{indent}```"
        except Exception as exc:
            print(
                f"WARNING: decode error, keeping original: {exc}",
                file=sys.stderr,
            )
            return m.group(0)

    return pattern.sub(replace_url, content)


def main() -> int:
    if len(sys.argv) < 3:
        die("usage: md_convert.py <to-url|to-code> <file.md>")

    mode = sys.argv[1]
    input_path = Path(sys.argv[2])

    if not input_path.is_file():
        die(f"file not found: {input_path}")

    content = input_path.read_text(encoding="utf-8")

    if mode == "to-url":
        sys.stdout.write(to_url(content))
    elif mode == "to-code":
        sys.stdout.write(to_code(content))
    else:
        die(f"unknown mode: {mode} (use 'to-url' or 'to-code')")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
