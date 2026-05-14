#!/usr/bin/env python3
"""decode_puml_url: PlantUML エンコード文字列または Kroki URL を PlantUML ソースに戻す。

呼び出し:
    decode_puml_url.py <url_or_encoded>
    decode_puml_url.py -            # stdin から読む
"""

from __future__ import annotations

import re
import sys
import zlib

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"


def decode_puml(s: str) -> bytes:
    out = bytearray()
    i = 0
    ln = len(s)
    while i < ln:
        c1 = ALPHABET.index(s[i])
        i += 1
        c2 = ALPHABET.index(s[i])
        i += 1
        c3 = ALPHABET.index(s[i]) if i < ln else 0
        i += 1
        c4 = ALPHABET.index(s[i]) if i < ln else 0
        i += 1
        b1 = (c1 << 2) | (c2 >> 4)
        b2 = ((c2 & 0x0F) << 4) | (c3 >> 2)
        b3 = ((c3 & 0x03) << 6) | c4
        out.extend((b1, b2, b3))
    return zlib.decompress(bytes(out), -15)


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        raw = sys.argv[1]
    else:
        if sys.stdin.isatty():
            print(
                "usage: decode_puml_url.py <plantuml_url_or_encoded>",
                file=sys.stderr,
            )
            return 2
        raw = sys.stdin.buffer.read().decode("utf-8")

    # 全空白を除去（tr -d ' \t\r\n' 相当）
    raw = re.sub(r"\s+", "", raw)

    # URL の /svg/<x>, /png/<x>, /txt/<x>, /uml/<x> から <x> を抜き出す
    m = re.search(r"/(?:svg|png|txt|uml)/([^/?#]+)", raw)
    encoded = m.group(1) if m else raw

    try:
        data = decode_puml(encoded)
    except Exception as exc:
        print(f"[decode error] {exc}", file=sys.stderr)
        return 1

    sys.stdout.write(data.decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
