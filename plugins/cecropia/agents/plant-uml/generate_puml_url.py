#!/usr/bin/env python3
"""generate_puml_url: PlantUML ソースを読み込んで Kroki SVG URL を出力する。

呼び出し:
    generate_puml_url.py <file.puml> [...]
    generate_puml_url.py -            # stdin から読む

Env:
    PLANTUML_SERVER (default: https://kroki.io/plantuml)

移植性: tr / sed / curl 依存を Python stdlib (re / urllib) に寄せる。
"""

from __future__ import annotations

import os
import re
import sys
import urllib.error
import urllib.request
import zlib

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"


def plantuml_encode(data: bytes) -> str:
    compressed = zlib.compress(data)[2:-4]  # raw deflate stream
    out: list[str] = []
    i = 0
    ln = len(compressed)
    while i < ln:
        chunk = compressed[i : i + 3]
        original_chunk_len = len(chunk)
        i += 3
        while len(chunk) < 3:
            chunk += b"\x00"
        b1, b2, b3 = chunk
        c1 = (b1 >> 2) & 0x3F
        c2 = ((b1 & 0x03) << 4) | ((b2 >> 4) & 0x0F)
        c3 = ((b2 & 0x0F) << 2) | ((b3 >> 6) & 0x03)
        c4 = b3 & 0x3F
        n = 4
        if original_chunk_len < 3:
            if original_chunk_len == 1:
                n = 2
            elif original_chunk_len == 2:
                n = 3
        out.append(ALPHABET[c1])
        out.append(ALPHABET[c2])
        if n > 2:
            out.append(ALPHABET[c3])
        if n > 3:
            out.append(ALPHABET[c4])
    return "".join(out)


def normalize_crlf(text: str) -> str:
    """旧 shell 実装 (`cat ... | tr -d '\\r' | sed 's/$/\\r/'`) と等価な CRLF 正規化。

    - bash の `INPUT="$(cat ...)"` は最末尾の連続 `\\n` を除去するため、ここでも先に剥がす。
    - 残った内容を行ごとに分割し、各行末に `\\r` を付ける（最終行に末尾 `\\n` は付かない）。
      これにより最終行は `<行内容>\\r` で終わる（旧挙動）。
    """
    text = text.replace("\r", "")
    text = text.rstrip("\n")
    if not text:
        return ""
    parts = text.split("\n")
    return "\r\n".join(parts) + "\r"


def read_input(args: list[str]) -> str:
    if args and args != ["-"]:
        chunks: list[str] = []
        for path in args:
            with open(path, "r", encoding="utf-8") as fp:
                chunks.append(fp.read())
        return "".join(chunks)
    return sys.stdin.buffer.read().decode("utf-8")


def fetch_text(url: str, timeout: float = 30.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "cecropia-plant-uml/1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        return body.decode("utf-8", errors="replace")


def main() -> int:
    args = sys.argv[1:]
    server = os.environ.get("PLANTUML_SERVER", "https://kroki.io/plantuml").rstrip("/")

    src = read_input(args)
    src = normalize_crlf(src)
    encoded = plantuml_encode(src.encode("utf-8"))

    try:
        text = fetch_text(f"{server}/txt/{encoded}")
    except urllib.error.URLError as exc:
        print(f"Failed to contact PlantUML server: {server}", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 3

    if re.search(r"Syntax Error\?|^Error line|^ERROR", text, re.MULTILINE):
        print("PlantUML syntax error detected.", file=sys.stderr)
        print("---- server message ----", file=sys.stderr)
        print(text, file=sys.stderr)
        return 1

    print(f"{server}/svg/{encoded}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
