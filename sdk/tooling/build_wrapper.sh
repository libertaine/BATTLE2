#!/usr/bin/env bash
set -euo pipefail
ASM_SRC="$1"; OUT_BLOB="$2"; shift 2
ENTRY=0; HEADER=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --entry)  ENTRY="$2"; shift 2;;
    --header) HEADER="$2"; shift 2;;
    *) echo "warn: unknown arg: $1" >&2; shift;;
  esac
done

# Map ASM source basename to legacy .bin
base="$(basename "$ASM_SRC")"
case "$base" in
  chatgpt_hunter.asm) BIN="_legacy/agents_tooling/chatgpt_hunter.bin" ;;
  claude_agent.asm)   BIN="_legacy/agents_tooling/claude_hunter.bin" ;;
  *) echo "error: no mapping for $base" >&2; exit 2;;
esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="$ROOT/$BIN"
DST="$OUT_BLOB"
mkdir -p "$(dirname "$DST")"
cp -f "$SRC" "$DST"

# (Optional) write a tiny sidecar with entry/header so tools can read it later
echo "{\"entry\": $ENTRY, \"header\": $HEADER}" > "${DST}.meta.json"
echo "built $DST (entry=$ENTRY header=$HEADER)"
