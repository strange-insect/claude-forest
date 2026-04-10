#!/usr/bin/env bash
# generate_puml_url: Read PlantUML source and output an SVG URL for PlantUML Server
# - If syntax error exists, print the error detail to stderr and exit with non‑zero.
#
# Usage:
#   generate_puml_url.sh diagram.puml
#   echo "@startuml\nAlice->Bob: Hi\n@enduml" | generate_puml_url.sh
#
# Env:
#   PLANTUML_SERVER  (default: https://kroki.io/plantuml)

set -euo pipefail

SERVER="${PLANTUML_SERVER:-https://kroki.io/plantuml}"

# ---- read entire input ----
if [[ $# -gt 0 ]]; then
  INPUT="$(cat "$@")"
else
  INPUT="$(cat -)"
fi

# ---- normalize line endings to CRLF ----
# First remove all CR to unify to LF, then convert all LF to CRLF
INPUT="$(printf '%s' "$INPUT" | tr -d '\r' | sed 's/$/\r/')"

# ---- encode (deflate + PlantUML base64) ----
ENCODED="$(
python3 - "$INPUT" <<'PY'
import sys, zlib

ALPHABET="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"

def plantuml_encode(data: bytes) -> str:
    compressed = zlib.compress(data)[2:-4]  # raw deflate stream
    out = []
    i = 0
    ln = len(compressed)
    while i < ln:
        chunk = compressed[i:i+3]
        original_chunk_len = len(chunk)
        i += 3
        # pad
        while len(chunk) < 3:
            chunk += b'\x00'
        b1, b2, b3 = chunk
        c1 =  (b1 >> 2) & 0x3F
        c2 = ((b1 & 0x03) << 4) | ((b2 >> 4) & 0x0F)
        c3 = ((b2 & 0x0F) << 2) | ((b3 >> 6) & 0x03)
        c4 =  b3 & 0x3F
        n = 4
        # 最後のチャンクの処理を修正
        if original_chunk_len < 3:
            if original_chunk_len == 1:
                n = 2
            elif original_chunk_len == 2:
                n = 3
        out.append(ALPHABET[c1])
        out.append(ALPHABET[c2])
        if n > 2: out.append(ALPHABET[c3])
        if n > 3: out.append(ALPHABET[c4])
    return "".join(out)

src = sys.stdin.read()
if len(sys.argv) > 1:
    src = sys.argv[1]
print(plantuml_encode(src.encode('utf-8')))
PY
)"

# ---- check syntax via /txt/ ----
TXT_OUT="$(curl -fsS "${SERVER%/}/txt/${ENCODED}")" || {
  echo "Failed to contact PlantUML server: ${SERVER}" >&2
  exit 3
}

# Simple heuristics: PlantUML puts 'Syntax Error?' or 'Error line' when broken.
if echo "$TXT_OUT" | grep -qE 'Syntax Error\?|^Error line|^ERROR'; then
  echo "PlantUML syntax error detected." >&2
  echo "---- server message ----" >&2
  echo "$TXT_OUT" >&2
  exit 1
fi

# ---- success: output URL ----
echo "${SERVER%/}/svg/${ENCODED}"
