#!/usr/bin/env bash
# md-convert.sh: Convert between PlantUML code blocks and Kroki URLs in Markdown
#
# Usage:
#   md-convert.sh to-url  <file.md>   # ```puml code blocks → Kroki image URLs
#   md-convert.sh to-code <file.md>   # Kroki image URLs → ```puml code blocks
#
# Output goes to stdout. Original file is not modified.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Prefer bundled helpers; fall back to $HOME/.claude/ for backward compatibility
GENERATE="${SCRIPT_DIR}/generate_puml_url.sh"
[[ -x "$GENERATE" ]] || GENERATE="$HOME/.claude/generate_puml_url.sh"
DECODE="${SCRIPT_DIR}/decode_puml_url.sh"
[[ -x "$DECODE" ]] || DECODE="$HOME/.claude/decode_puml_url.sh"

die(){ echo "ERROR: $*" >&2; exit 1; }

[[ $# -ge 2 ]] || die "usage: $0 <to-url|to-code> <file.md>"

MODE="$1"
INPUT_FILE="$2"

[[ -f "$INPUT_FILE" ]] || die "file not found: $INPUT_FILE"

case "$MODE" in
  to-url)
    # Replace ```puml / ```plantuml code blocks with Kroki SVG image markdown
    python3 - "$INPUT_FILE" "$GENERATE" <<'PYEOF'
import sys, re, subprocess, tempfile, os

input_file = sys.argv[1]
generate_script = sys.argv[2]

with open(input_file, 'r', encoding='utf-8') as f:
    content = f.read()

pattern = re.compile(
    r'^([ \t]*)```(?:puml|plantuml)\s*\n(.*?)^\1```\s*$',
    re.MULTILINE | re.DOTALL
)

def replace_block(m):
    indent = m.group(1)
    source = m.group(2).rstrip('\n')
    try:
        result = subprocess.run(
            [generate_script],
            input=source,
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            err = result.stderr.strip()
            print(f"WARNING: encode failed, keeping original block: {err}", file=sys.stderr)
            return m.group(0)
        url = result.stdout.strip()
        return f"{indent}![PlantUML]({url})"
    except Exception as e:
        print(f"WARNING: encode error, keeping original block: {e}", file=sys.stderr)
        return m.group(0)

output = pattern.sub(replace_block, content)
sys.stdout.write(output)
PYEOF
    ;;

  to-code)
    # Replace Kroki PlantUML image URLs with ```puml code blocks
    python3 - "$INPUT_FILE" "$DECODE" <<'PYEOF'
import sys, re, subprocess

input_file = sys.argv[1]
decode_script = sys.argv[2]

with open(input_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Match: ![...](https://kroki.io/plantuml/svg/ENCODED)
# Also match plain URLs on their own line
pattern = re.compile(
    r'^([ \t]*)!\[([^\]]*)\]\((https://kroki\.io/plantuml/(?:svg|png|txt)/[^)\s]+)\)'
    r'|'
    r'^([ \t]*)(https://kroki\.io/plantuml/(?:svg|png|txt)/[^\s]+)\s*$',
    re.MULTILINE
)

def replace_url(m):
    if m.group(1) is not None:
        indent = m.group(1)
        url = m.group(3)
    else:
        indent = m.group(4)
        url = m.group(5)
    try:
        result = subprocess.run(
            [decode_script, url],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            err = result.stderr.strip()
            print(f"WARNING: decode failed, keeping original: {err}", file=sys.stderr)
            return m.group(0)
        source = result.stdout.rstrip('\n')
        lines = source.split('\n')
        indented = '\n'.join(indent + line if line else line for line in lines)
        return f"{indent}```puml\n{indented}\n{indent}```"
    except Exception as e:
        print(f"WARNING: decode error, keeping original: {e}", file=sys.stderr)
        return m.group(0)

output = pattern.sub(replace_url, content)
sys.stdout.write(output)
PYEOF
    ;;

  *)
    die "unknown mode: $MODE (use 'to-url' or 'to-code')"
    ;;
esac
