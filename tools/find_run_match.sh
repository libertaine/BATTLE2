#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-$(pwd)}"
cd "$ROOT"

echo "== Searching under: $PWD =="

# Prefer ripgrep if present (fast, smart), else fall back to grep -R
RG=""
if command -v rg >/dev/null 2>&1; then
  RG="rg --no-ignore -n --hidden --glob '!**/.venv/**' --glob '!**/__pycache__/**'"
fi

py_globs=(
  "client/src/**/*.py"
  "app/**/*.py"
  "*/src/**/*.py"
  "**/*.py"
)

ui_globs=(
  "client/src/**/*.ui"
  "app/**/*.ui"
  "**/*.ui"
)

echo
echo "== 1) UI labels & object names possibly named 'Run' / 'Run Match' =="
if [ -n "$RG" ]; then
  $RG -i -e 'Run Match' -e '\brun\b' -e 'runButton' -e 'run_btn' -e 'btnRun' -- ${ui_globs[@]} ${py_globs[@]} || true
else
  grep -RIn --include='*.{py,ui}' -E 'Run Match|\brun\b|runButton|run_btn|btnRun' . || true
fi

echo
echo "== 2) Qt signal connections to slots (clicked.connect / triggered.connect) =="
if [ -n "$RG" ]; then
  $RG -n -e '\.clicked\.connect' -e '\.triggered\.connect' -- ${py_globs[@]} || true
else
  grep -RIn --include='*.py' -E '\.clicked\.connect|\.triggered\.connect' . || true
fi

echo
echo "== 3) Function names that look like handlers =="
if [ -n "$RG" ]; then
  $RG -n -e 'def on_.*run' -e 'def run_?match' -e 'def .*run.*\(self' -- ${py_globs[@]} || true
else
  grep -RIn --include='*.py' -E 'def on_.*run|def run_?match|def .*run.*\(self' . || true
fi

echo
echo "== 4) Places that launch subprocesses (engine starter suspects) =="
if [ -n "$RG" ]; then
  $RG -n -e 'subprocess\.Popen' -e 'subprocess\.run' -e 'Popen\(' -- ${py_globs[@]} || true
else
  grep -RIn --include='*.py' -E 'subprocess\.Popen|subprocess\.run|Popen\(' . || true
fi

echo
echo "== 5) Direct or module-based engine calls (what we need to change) =="
if [ -n "$RG" ]; then
  $RG -n -e 'battle_engine\.cli' -e 'python -m battle_engine\.cli' -e 'engine/src/battle_engine/cli\.py' -- ${py_globs[@]} || true
else
  grep -RIn --include='*.py' -E 'battle_engine\.cli|python -m battle_engine\.cli|engine/src/battle_engine/cli\.py' . || true
fi

echo
echo "== 6) PySide6 imports (narrow likely files) =="
if [ -n "$RG" ]; then
  $RG -n -e '^from PySide6' -e '^import PySide6' -- ${py_globs[@]} || true
else
  grep -RIn --include='*.py' -E '^from PySide6|^import PySide6' . || true
fi

echo
echo "Hints:"
echo " - Look for a file that both imports PySide6 AND has a clicked.connect line near a button named 'run*'."
echo " - Common spots: client/src/app/main.py, client/src/app/widgets/*, client/src/app/windows/*."
echo " - If using Qt Designer, a .ui may define objectName='runButton'; wiring might be in a generated ui_* file or after uic.loadUi()."
