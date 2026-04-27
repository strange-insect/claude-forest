#!/usr/bin/env bash
# decode_puml_url.sh
set -euo pipefail

die(){ echo "ERROR: $*" >&2; exit 2; }

if [[ $# -gt 0 ]]; then
  INPUT="$1"
else
  if [[ -t 0 ]]; then
    die "usage: $0 <plantuml_url_or_encoded>"
  fi
  INPUT="$(cat -)"
fi
INPUT="$(echo -n "$INPUT" | tr -d ' \t\r\n')"

# もし URL なら /svg/xxx や /png/xxx の xxx 部分だけ抜く
if [[ "$INPUT" =~ /(svg|png|txt|uml)/([^/?#]+) ]]; then
  ENCODED="${BASH_REMATCH[2]}"
else
  ENCODED="$INPUT"
fi

command -v python3 >/dev/null 2>&1 || die "python3 が見つかりません。"

python3 - "$ENCODED" <<'PY'
import sys, zlib
ALPHABET="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"

def decode_puml(s: str) -> bytes:
    out = bytearray()
    i = 0
    ln = len(s)
    while i < ln:
        c1 = ALPHABET.index(s[i]); i += 1
        c2 = ALPHABET.index(s[i]); i += 1
        c3 = ALPHABET.index(s[i]) if i < ln else 0; i += 1
        c4 = ALPHABET.index(s[i]) if i < ln else 0; i += 1
        b1 = (c1 << 2) | (c2 >> 4)
        b2 = ((c2 & 0x0F) << 4) | (c3 >> 2)
        b3 = ((c3 & 0x03) << 6) | c4
        out.extend((b1, b2, b3))
    return zlib.decompress(bytes(out), -15)

enc = sys.argv[1].strip()
try:
    data = decode_puml(enc)
except Exception as e:
    print(f"[decode error] {e}", file=sys.stderr)
    sys.exit(1)
sys.stdout.write(data.decode("utf-8"))
PY
