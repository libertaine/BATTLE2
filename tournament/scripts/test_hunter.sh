#!/usr/bin/env bash
# test_hunter.sh — compatibility-aware runner for claude_hunter.bin vs built-ins
# Bash 4.2+. No external deps.

set -euo pipefail

# -------------------------
# Config (override via env)
# -------------------------
ARENA="${ARENA:-2048}"
TICKS="${TICKS:-2000}"
WIN_MODE="${WIN_MODE:-score_fallback}"
TERR_W="${TERR_W:-1}"
TERR_BUCKET="${TERR_BUCKET:-32}"
PARALLEL_JOBS="${PARALLEL_JOBS:-1}"
HUNTER_BLOB="${HUNTER_BLOB:-agents_tooling/claude_hunter.bin}"

OPPONENTS="${OPPONENTS:-runner writer bomber flooder spiral seeker}"
SEEDS="${SEEDS:-1 2 3 4 5}"

A_START="${A_START:-256}"
B_START="${B_START:-1536}"
A_PTR="${A_PTR:-$A_START}"
B_PTR="${B_PTR:-$B_START}"

PYGAME_FLAG="${PYGAME_FLAG:---pygame}"

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT_ROOT="results/hunter-${STAMP}"
mkdir -p "${OUT_ROOT}"

# -------------------------
# Detect CLI capabilities
# -------------------------
HELP="$(python3 main.py -h 2>&1 || true)"

has_flag() {
  # crude but robust: search the help text for the flag literal
  grep -q -- "$1" <<<"$HELP"
}

HAS_RECORD=false
HAS_AGENT_PTR=false
if has_flag "--record"; then HAS_RECORD=true; fi
if has_flag "--a-ptr" && has_flag "--b-ptr"; then HAS_AGENT_PTR=true; fi

# optional: detect per-agent blob flags; if not present, fall back to generic --b

