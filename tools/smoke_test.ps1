#Requires -Version 5.1
<#
  BATTLE2 smoke_test.ps1
  Purpose: Quick, deterministic checks to ensure the repo runs from source on Windows.
  - Activates venv python (if available)
  - Sets PYTHONPATH for engine/src and client/src
  - Verifies key imports
  - Discovers agents
  - Performs a tiny CLI run (short, safe parameters)

  Usage:
    powershell -ExecutionPolicy Bypass -File tools\smoke_test.ps1
#>

$ErrorActionPreference = 'Stop'

# --- Helpers ---------------------------------------------------------------

function Write-Info([string]$msg)  { Write-Host "[INFO]  $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg)    { Write-Host "[ OK ]  $msg" -ForegroundColor Green }
function Write-Warn([string]$msg)  { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err([string]$msg)   { Write-Host "[FAIL] $msg" -ForegroundColor Red }

function Resolve-RepoRoot {
  # Prefer git root; fallback to script parent\..
  try {
    $gitTop = (git rev-parse --show-toplevel 2>$null)
    if ($LASTEXITCODE -eq 0 -and $gitTop) { return (Resolve-Path $gitTop).Path }
  } catch { }
  return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Get-Python {
  param([string]$RepoRoot)
  # 1) Active venv python if already activated
  if ($env:VIRTUAL_ENV) {
    $py = Join-Path $env:VIRTUAL_ENV 'Scripts\python.exe'
    if (Test-Path $py) { return (Resolve-Path $py).Path }
  }
  # 2) Local .venv
  $py = Join-Path $RepoRoot '.venv\Scripts\python.exe'
  if (Test-Path $py) { return (Resolve-Path $py).Path }
  # 3) Fallback to PATH
  $py = (Get-Command python -ErrorAction SilentlyContinue)?.Source
  if ($py) { return $py }
  throw "Python executable not found. Create venv:  python -m venv .venv"
}

function Ensure-Env {
  param([string]$RepoRoot)
  $engine = (Resolve-Path (Join-Path $RepoRoot 'engine\src')).Path
  $client = (Resolve-Path (Join-Path $RepoRoot 'client\src')).Path
  $env:PYTHONPATH = "$engine;$client"
  if (-not $env:BATTLE_AGENTS_DIR) {
    $agents = Join-Path $RepoRoot 'agents'
    if (Test-Path $agents) { $env:BATTLE_AGENTS_DIR = (Resolve-Path $agents).Path }
  }
  Write-Info "Repo root: $RepoRoot"
  Write-Info "PYTHONPATH = $($env:PYTHONPATH)"
  if ($env:BATTLE_AGENTS_DIR) { Write-Info "BATTLE_AGENTS_DIR = $($env:BATTLE_AGENTS_DIR)" }
}

function Invoke-PyCode {
  param(
    [string]$PythonExe,
    [string]$Code,
    [string]$What = "python snippet"
  )
  try {
    $Code | & $PythonExe - 2>&1 | ForEach-Object { $_ }
    if ($LASTEXITCODE -ne 0) { throw "$What failed with exit code $LASTEXITCODE" }
  } catch {
    Write-Err "$What failed."
    throw
  }
}

# --- Main -----------------------------------------------------------------

$repo = Resolve-RepoRoot
Set-Location $repo

$PY = Get-Python -RepoRoot $repo
Write-Ok "Python: $PY"

Ensure-Env -RepoRoot $repo

# 1) Import sanity: battle_engine and client renderer
Write-Info "Check: module imports"
Invoke-PyCode -PythonExe $PY -What "import check" -Code @'
import sys, pkgutil
sys.path[:0] = [r"engine/src", r"client/src"]
print("has battle_engine:", pkgutil.find_loader("battle_engine") is not None)
print("has battle_client.renderers.pygame_renderer:",
      pkgutil.find_loader("battle_client.renderers.pygame_renderer") is not None)
'@

# 2) Agent discovery (uses discover_agents(Path(root)))
Write-Info "Check: agent discovery"
Invoke-PyCode -PythonExe $PY -What "agent discovery" -Code @'
import sys, pathlib
sys.path[:0] = [r"engine/src", r"client/src"]
from app.services.osutil import get_battle_root
from battle_engine.agents import discover_agents
root = pathlib.Path(get_battle_root())
items = discover_agents(root)
names = [getattr(x, "display", None) or getattr(x, "name", None) or getattr(x, "id", None) for x in items]
print("agents count:", len(items))
print("agents:", names)
if len(items) == 0:
    raise SystemExit("No agents discovered; ensure agents/*/agent.yaml exist.")
'@

# 3) Tiny CLI run (safe/short)
Write-Info "Check: tiny CLI run"
# If your CLI is python -m battle_engine.cli; adjust flags to very small work.
& $PY -m battle_engine.cli --ticks 10 --arena 128 1>$null 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Err "CLI run failed (exit $LASTEXITCODE)"
  exit $LASTEXITCODE
}
Write-Ok "CLI run ok"

Write-Ok "Smoke tests passed."
exit 0
