# tools/smoke_test.ps1
# Smoke tests for the battle project on Windows (PowerShell 5+).
# - Simple CLI agent vs agent
# - Redcode94 via pMARS (if present)
# - Agent "builder" execution (no extra weights)
# Assumes repo layout with engine\src\battle_engine\cli.py

param(
  [switch]$Strict # If set, fail when pmars is missing (instead of skipping test 2)
)

$ErrorActionPreference = 'Stop'

function Write-Log([string]$msg) {
  $ts = Get-Date -Format HH:mm:ss
  Write-Host "[$ts] $msg"
}

function Fail([string]$msg) {
  Write-Error $msg
  exit 1
}

# Return best available python launcher: python, python3, or py -3
function Get-PythonCmd {
  foreach ($candidate in @('python', 'python3')) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) { return $candidate }
  }
  if (Get-Command py -ErrorAction SilentlyContinue) { return 'py -3' }
  Fail "Python not found. Install Python 3 or ensure it's on PATH."
}

# --- config ----------------------------------------------------------------
$RepoRoot   = Resolve-Path (Join-Path $PSScriptRoot '..')
$EngineSrc  = Join-Path $RepoRoot 'engine\src'
$CliMod     = 'battle_engine.cli'
$RunRoot    = Join-Path $RepoRoot 'runs\_smoke'
$Timestamp  = Get-Date -Format 'yyyyMMdd-HHmmss'
$RunDir     = Join-Path $RunRoot $Timestamp

$AgentA     = 'runner'
$AgentB     = 'bomber'

$RedRounds        = 3
$RedCoreSize      = 8000
$RedMaxCycles     = 80000
$RedMaxProcesses  = 8000
$RedMaxLen        = 100
$RedMinDist       = 100

# --- environment -----------------------------------------------------------
Set-Location $RepoRoot
Write-Log "Project root: $RepoRoot"

# Activate venv if present
$VenvActivate = Join-Path $RepoRoot '.venv\Scripts\Activate.ps1'
if (Test-Path $VenvActivate) {
  . $VenvActivate
  Write-Log "Activated venv: $($RepoRoot)\.venv"
} else {
  Write-Log "No .venv found. Using system Python."
}

# Ensure PYTHONPATH includes engine\src
if (-not $env:PYTHONPATH) {
  $env:PYTHONPATH = $EngineSrc
  Write-Log "PYTHONPATH set to include engine\src"
} elseif ($env:PYTHONPATH -notlike "*$EngineSrc*") {
  $env:PYTHONPATH = "$EngineSrc;$($env:PYTHONPATH)"
  Write-Log "PYTHONPATH augmented to include engine\src"
}

# Ensure run dir
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
Write-Log "Run dir: $RunDir"

$PY = Get-PythonCmd

# Verify CLI import path
& $PY - << 'PYCODE'
import importlib, sys
try:
    m = importlib.import_module("battle_engine.cli")
    print("[check] battle_engine.cli path:", m.__file__)
except Exception as e:
    print("[check] FAILED to import battle_engine.cli:", e)
    sys.exit(1)
PYCODE

function Invoke-CLI([string[]]$Args) {
  Write-Log ("Running CLI: " + ($Args -join ' '))
  & $PY -m $CliMod @Args
}

# --- helpers ---------------------------------------------------------------
function Prepare-RedcodeWarriors([string]$Dir) {
  New-Item -ItemType Directory -Force -Path $Dir | Out-Null

  $imp = @"
;name Imp
;author SmokeTest
;strategy 1-instruction process that marches through core
        MOV     0, 1
"@
  Set-Content -NoNewline -Path (Join-Path $Dir 'imp.red') -Value $imp

  $dwarf = @"
;name Dwarf
;author SmokeTest
;strategy Bomb every 4 cells
STEP    EQU     4
        ADD     #STEP,   BAIT
BAIT    DAT     #0,      #0
        MOV     BAIT,    @BAIT
        JMP     -2
        END
"@
  Set-Content -NoNewline -Path (Join-Path $Dir 'dwarf.red') -Value $dwarf

  return ,(Join-Path $Dir 'imp.red'),(Join-Path $Dir 'dwarf.red')
}

function Have-Cmd([string]$name) {
  return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

# --- tests -----------------------------------------------------------------
function Test-1-SimpleCLI {
  Write-Log "=== [1/3] Simple CLI battle with built-in agents ($AgentA vs $AgentB) ==="
  Invoke-CLI @(
    '--ticks','50',
    '--arena','512',
    '--win-mode','score_fallback',
    '--a-type', $AgentA,
    '--b-type', $AgentB,
    '--q
