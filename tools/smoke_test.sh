#!/usr/bin/env bash
# tools/smoke_test.sh
# Basic functionality checks for the battle project:
#  1) CLI run with built-in agents
#  2) Redcode run via pMARS backend
#  3) Agent-type battle ("builder" style) execution
#
# Assumptions:
#  - Linux environment (or WSL Ubuntu)
#  - Project root contains engine/src/battle_engine
#  - Python 3 available; optional .venv in project root
#  - pmars installed for the redcode test (script will skip if missing)

set -euo pipefail

# --- config ---------------------------------------------------------------
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINE_SRC="${PROJECT_ROOT}/engine/src"
CLI_MOD="battle_engine.cli"
RUN_ROOT="${PROJECT_ROOT}/runs/_smoke"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
RUN_DIR="${RUN_ROOT}/${TIMESTAMP}"

# Built-in agent types known by the CLI parser (adjust if your set differs)
AGENT_A="runner"
AGENT_B="bomber"

# Redcode params
RED_ROUNDS=3
RED_CORE_SIZE=8000
RED_MAX_CYCLES=80000
RED_MAX_PROCESSES=8000
RED_MAX_LEN=100
RED_MIN_DIST=100

# --- helpers --------------------------------------------------------------
log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
die() { log "ERROR: $*"; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

activate_venv_if_present() {
  if [[ -d "${PROJECT_ROOT}/.venv" ]]; then
    # shellcheck disable=SC1091
    source "${PROJECT_ROOT}/.venv/bin/activate"
    log "Activated venv: ${PROJECT_ROOT}/.venv"
  else
    log "No .venv found. Using system Python."
  fi
}

ensure_pythonpath() {
  if [[ -z "${PYTHONPATH-}" ]]; then
    export PYTHONPATH="${ENGINE_SRC}:${PYTHONPATH-}"
    log "PYTHONPATH set to include engine/src"
  elif [[ ":${PYTHONPATH}:" != *":${ENGINE_SRC}:"* ]]; then
    export PYTHONPATH="${ENGINE_SRC}:${PYTHONPATH}"
    log "PYTHONPATH augmented to include engine/src"
  fi
}

ensure_dirs() {
  mkdir -p "${RUN_DIR}"
  log "Run dir: ${RUN_DIR}"
}

# Create minimal Redcode warriors in a temp dir if not present
prepare_redcode_warriors() {
  local wdir="$1"
  mkdir -p "${wdir}"

  # Standard tiny "imp" (redcode'94 dialect)
  cat > "${wdir}/imp.red" <<'RED'
;name Imp
;author SmokeTest
;strategy 1-instruction process that marches through core
        MOV     0, 1
RED

  # Standard tiny "dwarf" bomber
  cat > "${wdir}/dwarf.red" <<'RED'
;name Dwarf
;author SmokeTest
;strategy Bomb every 4 cells
STEP    EQU     4
        ADD     #STEP,   BAIT
BAIT    DAT     #0,      #0
        MOV     BAIT,    @BAIT
        JMP     -2
        END
RED

  echo "${wdir}/imp.red;${wdir}/dwarf.red"
}

run_cli() {
  log "Running CLI: $*"
  python3 -m "${CLI_MOD}" "$@"
}

require_python3() {
  have python3 || die "python3 not found. Install Python 3."
}

# --- tests ---------------------------------------------------------------

test_1_simple_cli() {
  log "=== [1/3] Simple CLI battle with built-in agents (${AGENT_A} vs ${AGENT_B}) ==="
  run_cli \
    --ticks 50 \
    --arena 512 \
    --win-mode score_fallback \
    --a-type "${AGENT_A}" \
    --b-type "${AGENT_B}" \
    --quiet || die "Simple CLI test failed"

  log "PASS: simple CLI battle"
}

test_2_redcode_pmars() {
  log "=== [2/3] Redcode battle via pMARS ==="
  if ! have pmars; then
    log "pMARS not found; skipping redcode test. Install with: sudo apt-get install pmars"
    return 0
  fi

  local wdir="${RUN_DIR}/warriors"
  IFS=';' read -r WIMP WDWARF < <(prepare_redcode_warriors "${wdir}")

  run_cli \
    --mode redcode94 \
    --red-a "${WIMP}" \
    --red-b "${WDWARF}" \
    --rounds "${RED_ROUNDS}" \
    --core-size "${RED_CORE_SIZE}" \
    --max-cycles "${RED_MAX_CYCLES}" \
    --max-processes "${RED_MAX_PROCESSES}" \
    --max-len "${RED_MAX_LEN}" \
    --min-dist "${RED_MIN_DIST}" \
    --quiet || die "Redcode test failed (pmars present but run errored)"

  log "PASS: redcode/pmars battle executed"
}

test_3_agent_builder() {
  log "=== [3/3] Agent-type 'builder' execution (no extra weights) ==="
  run_cli \
    --ticks 120 \
    --arena 1024 \
    --win-mode score_fallback \
    --a-type runner \
    --b-type seeker \
    --quiet || die "Agent builder-style test failed"
  log "PASS: agent-type builder execution"
}

# Optional: write a concise JSON summary if your CLI produced one
post_check_artifacts() {
  # Many flows dump a summary; try to locate a recent one under runs/
  local latest_summary
  latest_summary="$(find "${PROJECT_ROOT}" -type f -path "*/runs/*/summary.json" -printf "%T@ %p\n" 2>/dev/null | sort -nr | awk 'NR==1{print $2}')"
  if [[ -n "${latest_summary}" ]]; then
    log "Detected summary file: ${latest_summary}"
  else
    log "No summary.json found (this may be normal depending on CLI flags)."
  fi
}

# --- main ----------------------------------------------------------------
main() {
  cd "${PROJECT_ROOT}"
  log "Project root: ${PROJECT_ROOT}"

  require_python3
  activate_venv_if_present
  ensure_pythonpath
  ensure_dirs

  # Verify the CLI is importable from the repo
  python3 - <<'PY'
import importlib, sys
try:
    m = importlib.import_module("battle_engine.cli")
    print("[check] battle_engine.cli path:", m.__file__)
except Exception as e:
    print("[check] FAILED to import battle_engine.cli:", e)
    sys.exit(1)
PY

  test_1_simple_cli
  test_2_redcode_pmars
  test_3_agent_builder
  post_check_artifacts

  log "=== ALL TESTS COMPLETED ==="
}
main "$@"
