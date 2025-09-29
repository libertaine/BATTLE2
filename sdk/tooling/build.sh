#!/usr/bin/env bash
set -euo pipefail
# build.sh SRC OUT --entry N --name NAME [--ptr PTR] [--src SRC_ADDR] [--dst DST_ADDR] [--stride STRIDE] [--byte BYTE]
if [ $# -lt 2 ]; then
  echo "usage: $0 src.asm out.bin [--entry N] [--name NAME] [--ptr N] [--src N] [--dst N] [--stride N] [--byte N]"
  exit 1
fi

SRC="$1"; OUT="${2}"; shift 2

# defaults
ENTRY=128; NAME="agent"; PTR=""; STRIDE=""; BYTE=""
SRC_REPL=""; DST_REPL=""

while (( "$#" )); do
  case "$1" in
    --entry) ENTRY="$2"; shift 2;;
    --name) NAME="$2"; shift 2;;
    --ptr) PTR="$2"; shift 2;;
    --stride) STRIDE="$2"; shift 2;;
    --byte) BYTE="$2"; shift 2;;
    --src) SRC_REPL="$2"; shift 2;;
    --dst) DST_REPL="$2"; shift 2;;
    *) echo "unknown arg: $1"; exit 1;;
  esac
done

TMPASM="$(mktemp /tmp/agentXXXX.asm)"
# Replace common tokens if present in source; safe if tokens not used.
sed -e "s/\bentry\b/${ENTRY}/g" \
    -e "s/\bptr_start\b/${PTR:-$((ENTRY+256))}/g" \
    -e "s/\bptr\b/${PTR:-$((ENTRY+256))}/g" \
    -e "s/\bsrc_ptr\b/${SRC_REPL:-$((ENTRY+0))}/g" \
    -e "s/\bdst_ptr\b/${DST_REPL:-$((ENTRY+512))}/g" \
    -e "s/\bstride\b/${STRIDE:-64}/g" \
    -e "s/\bbyte\b/${BYTE:-0x99}/g" \
    "$SRC" > "$TMPASM"

python3 asm_assembler.py "$TMPASM" -o "$OUT" --entry "$ENTRY"
rm -f "$TMPASM"

# basic validator
python3 - <<PY
blob = open("$OUT","rb").read()
ALLOWED = set(range(0,12))
i=0
while i < len(blob):
    op = blob[i]
    if op not in ALLOWED:
        print("INVALID OPCODE",op,"at",i); raise SystemExit(2)
    if op in {1,2,3,4,5,6,8,9}:
        i+=5
    else:
        i+=1
print("VALIDATED", "$OUT", len(blob), "bytes")
PY

META="${OUT}.meta.json"
cat > "$META" <<JSON
{"name": "${NAME}", "entry": ${ENTRY}, "size": $(stat -c%s "$OUT")}
JSON
echo "WROTE metadata -> $META"

