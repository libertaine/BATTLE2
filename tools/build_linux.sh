#!/usr/bin/env bash
# tools/build_linux.sh
#
# Canonical self-contained Linux PyInstaller build for the four Bytefray
# applications (bytefray, bytefray-cli, bytefray-agent-designer,
# bytefray-replay-viewer), mirroring tools/build_win.ps1's structure and
# embedded smoke tests. Produces onedir bundles under dist/linux/.
#
# Usage:
#   tools/build_linux.sh
#
# Environment overrides:
#   BYTEFRAY_LINUX_BUILD_VENV  - venv directory to create/use (default: .venv,
#                                 the same repo-root convention build_win.ps1
#                                 uses on Windows). Override for a dedicated
#                                 qualification venv, e.g.
#                                 BYTEFRAY_LINUX_BUILD_VENV=.venv-rc2-linux-build
#   BYTEFRAY_LINUX_BUILD_PYTHON - interpreter used to *create* the venv if it
#                                 does not already exist (default: python3).
#                                 Ignored if the venv already exists.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

VENV_DIR="${BYTEFRAY_LINUX_BUILD_VENV:-.venv}"
VENV_PYTHON_FOR_CREATE="${BYTEFRAY_LINUX_BUILD_PYTHON:-python3}"
PY_EXE="${REPO_ROOT}/${VENV_DIR}/bin/python"

log() { printf '[build] %s\n' "$*"; }
die() { printf '[build] ERROR: %s\n' "$*" >&2; exit 1; }

if [[ ! -d "${REPO_ROOT}/${VENV_DIR}" ]]; then
  log "Creating virtual environment at ${VENV_DIR} (using ${VENV_PYTHON_FOR_CREATE})..."
  command -v "${VENV_PYTHON_FOR_CREATE}" >/dev/null 2>&1 \
    || die "interpreter not found: ${VENV_PYTHON_FOR_CREATE}"
  "${VENV_PYTHON_FOR_CREATE}" -m venv "${REPO_ROOT}/${VENV_DIR}"
fi

[[ -x "${PY_EXE}" ]] || die "venv python not found or not executable at ${PY_EXE}"

run_py_mod() {
  "${PY_EXE}" -m "$@" || die "python -m $1 failed"
}

# --- Dependencies -------------------------------------------------------
run_py_mod pip install --upgrade pip wheel
run_py_mod pip install -e ".[replay,designer,linux-build]"
run_py_mod pip show pyinstaller >/dev/null

# --- Output dirs ----------------------------------------------------------
BUILD_DIR="${REPO_ROOT}/build/linux"
DIST_DIR="${REPO_ROOT}/dist/linux"
rm -rf "${BUILD_DIR}" "${DIST_DIR}"
mkdir -p "${BUILD_DIR}" "${DIST_DIR}"

# Keep each app in its own onedir folder, matching the Windows layout, so
# the same relative tree shape can be archived/relocated without renaming.
ARTIFACT_NAMES=(bytefray bytefray-cli bytefray-agent-designer bytefray-replay-viewer)
ARTIFACT_SPECS=(tools/bytefray.spec tools/bytefray_cli.spec tools/agent_designer.spec tools/replay_viewer.spec)

for i in "${!ARTIFACT_NAMES[@]}"; do
  name="${ARTIFACT_NAMES[$i]}"
  spec="${ARTIFACT_SPECS[$i]}"
  [[ -f "${REPO_ROOT}/${spec}" ]] || die "Missing spec: ${spec}"
  log "Building ${name}..."
  "${PY_EXE}" -m PyInstaller --noconfirm --clean \
    --workpath "${BUILD_DIR}" --distpath "${DIST_DIR}" "${spec}" \
    || die "PyInstaller build failed: ${name}"

  exe_path="${DIST_DIR}/${name}/${name}"
  [[ -f "${exe_path}" ]] || die "Expected artifact was not produced: ${exe_path}"
  [[ -x "${exe_path}" ]] || die "Produced artifact is not executable: ${exe_path}"
done

# The unified dispatcher imports the Designer dynamically; prove its frozen
# tree contains the same runtime branding resource as the standalone GUI
# build (mirrors tools/build_win.ps1's identical check).
UNIFIED_BRANDING_ICON="${DIST_DIR}/bytefray/_internal/assets/branding/bytefray-icon.png"
[[ -f "${UNIFIED_BRANDING_ICON}" ]] \
  || die "Unified Designer branding resource missing: ${UNIFIED_BRANDING_ICON}"

# --- GUI import/startup smoke -------------------------------------------
# Exercises the dynamically imported Designer from the unified dispatcher
# and the standalone Designer, the same regression class tools/
# build_win.ps1 guards (AgentDesigner.__init__ eagerly calls
# ensure_starter_agents() against get_data_root(), which a frozen app with
# no BYTEFRAY_ROOT set resolves beside its own executable -- so without
# isolation this would leave a runtime-generated agents/ directory inside
# the distributable tree tools/build_linux.sh's own callers ship verbatim).
# QT_QPA_PLATFORM=offscreen keeps this headless: unlike the Windows build
# (typically unattended CI/build hosts), this runs against a real, live
# desktop session, and a real window flashing open/closed during an
# automated build serves no purpose here -- the real, on-screen GUI
# qualification is a separate, deliberate manual phase.
PREVIOUS_SMOKE_EXIT="${BYTEFRAY_GUI_SMOKE_EXIT_MS:-}"
PREVIOUS_GUI_SMOKE_ROOT="${BYTEFRAY_ROOT:-}"
GUI_SMOKE_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/bytefray-gui-smoke.XXXXXXXX")"

cleanup_gui_smoke() {
  if [[ -n "${PREVIOUS_SMOKE_EXIT}" ]]; then
    export BYTEFRAY_GUI_SMOKE_EXIT_MS="${PREVIOUS_SMOKE_EXIT}"
  else
    unset BYTEFRAY_GUI_SMOKE_EXIT_MS
  fi
  if [[ -n "${PREVIOUS_GUI_SMOKE_ROOT}" ]]; then
    export BYTEFRAY_ROOT="${PREVIOUS_GUI_SMOKE_ROOT}"
  else
    unset BYTEFRAY_ROOT
  fi
  rm -rf "${GUI_SMOKE_ROOT}"
  [[ -e "${GUI_SMOKE_ROOT}" ]] && die "GUI smoke temporary root could not be removed: ${GUI_SMOKE_ROOT}"
  return 0
}
trap cleanup_gui_smoke EXIT

export BYTEFRAY_GUI_SMOKE_EXIT_MS="750"
export BYTEFRAY_ROOT="${GUI_SMOKE_ROOT}"
export QT_QPA_PLATFORM=offscreen

log "GUI import/startup smoke: ${DIST_DIR}/bytefray/bytefray design"
"${DIST_DIR}/bytefray/bytefray" design \
  || die "GUI import/startup smoke failed: bytefray design"

log "GUI import/startup smoke: ${DIST_DIR}/bytefray-agent-designer/bytefray-agent-designer"
"${DIST_DIR}/bytefray-agent-designer/bytefray-agent-designer" \
  || die "GUI import/startup smoke failed: bytefray-agent-designer"

unset QT_QPA_PLATFORM
cleanup_gui_smoke
trap - EXIT

# --- 'agents create' resource smoke --------------------------------------
# Regression check mirroring tools/build_win.ps1: proves the frozen unified
# executable's bundled battle_engine/data/agent_template resource is
# actually reachable at runtime, not just declared in the .spec's datas.
SMOKE_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/bytefray-agents-create-smoke.XXXXXXXX")"
PREVIOUS_BYTEFRAY_ROOT="${BYTEFRAY_ROOT:-}"

cleanup_agents_create_smoke() {
  if [[ -n "${PREVIOUS_BYTEFRAY_ROOT}" ]]; then
    export BYTEFRAY_ROOT="${PREVIOUS_BYTEFRAY_ROOT}"
  else
    unset BYTEFRAY_ROOT
  fi
  rm -rf "${SMOKE_ROOT}"
  [[ -e "${SMOKE_ROOT}" ]] && die "'agents create' smoke temporary root could not be removed: ${SMOKE_ROOT}"
  return 0
}
trap cleanup_agents_create_smoke EXIT

export BYTEFRAY_ROOT="${SMOKE_ROOT}"
BYTEFRAY_EXE="${DIST_DIR}/bytefray/bytefray"
log "'agents create' smoke test against ${BYTEFRAY_EXE} (BYTEFRAY_ROOT=${SMOKE_ROOT})"
"${BYTEFRAY_EXE}" agents create smoke_agent \
  || die "'bytefray agents create smoke_agent' failed"

[[ -f "${SMOKE_ROOT}/agents/smoke_agent/agent.yaml" && -f "${SMOKE_ROOT}/agents/smoke_agent/agent.py" ]] \
  || die "'bytefray agents create smoke_agent' did not write the expected agent.yaml/agent.py under ${SMOKE_ROOT}"
log "'agents create' smoke test passed."

cleanup_agents_create_smoke
trap - EXIT

# --- Final residue proof --------------------------------------------------
# Both smoke blocks above isolate their own BYTEFRAY_ROOT; an agents/
# directory appearing inside a distributable tree here means something
# still resolved the frozen app's default (beside-the-exe) data root
# instead of the isolated one.
for name in "${ARTIFACT_NAMES[@]}"; do
  residue_dir="${DIST_DIR}/${name}/agents"
  if [[ -e "${residue_dir}" ]]; then
    die "Build qualification left runtime-generated data under ${residue_dir} -- smoke tests must run against an isolated BYTEFRAY_ROOT, not the app's default data root."
  fi
done

log ""
log "Success."
for i in "${!ARTIFACT_NAMES[@]}"; do
  log "${ARTIFACT_NAMES[$i]}: ${DIST_DIR}/${ARTIFACT_NAMES[$i]}/${ARTIFACT_NAMES[$i]}"
done
log "Dist dir: ${DIST_DIR}"
