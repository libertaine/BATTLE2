<# 
Build BATTLE2 executables (Windows, Python 3.11)

Outputs:
  dist\battle-agent-designer\battle-agent-designer.exe  (Qt / PySide6 GUI)
  dist\match_runner\match_runner.exe                    (Pygame renderer)
  dist\battle-cli\battle-cli.exe                        (Engine CLI)

Usage:
  powershell -ExecutionPolicy Bypass -File tools\build_executables.ps1
  powershell -ExecutionPolicy Bypass -File tools\build_executables.ps1 -RecreateVenv
#>

[CmdletBinding()]
param(
  [switch]$RecreateVenv = $false,
  [switch]$SkipPipUpgrade = $false
)

$ErrorActionPreference = "Stop"

function Write-Head($text) { Write-Host "`n=== $text ===" -ForegroundColor Cyan }
function Die($text) { Write-Host "ERROR: $text" -ForegroundColor Red; exit 1 }

# --- Paths (repo-root relative) ---
$RepoRoot   = Resolve-Path -LiteralPath "$PSScriptRoot\.." | Select-Object -ExpandProperty Path
$VenvDir    = Join-Path $RepoRoot ".venv"
$Py311Exe   = "python"
$Vpy        = Join-Path $VenvDir "Scripts\python.exe"
$Vpip       = Join-Path $VenvDir "Scripts\pip.exe"
$Vpyi       = Join-Path $VenvDir "Scripts\pyinstaller.exe"

# --- Helpers ---
function Ensure-Py311 {
  Write-Head "Checking Python 3.11 availability"
  try {
    $ver = (& $Py311Exe -V)
    if ($LASTEXITCODE -ne 0) { throw "py -3.11 not found" }
    if ($ver -notmatch "3\.11\.") { throw "py -3.11 reported: $ver" }
    Write-Host "Found: $ver"
  } catch {
    Die "Python 3.11 not found via 'py -3.11'. Install Python 3.11 and re-run."
  }
}

function New-Or-Reset-Venv {
  if ($RecreateVenv -and (Test-Path $VenvDir)) {
    Write-Head "Removing existing venv"
    Remove-Item -Recurse -Force $VenvDir
  }
  if (-not (Test-Path $VenvDir)) {
    Write-Head "Creating venv (3.11)"
    & $Py311Exe -m venv $VenvDir | Out-Null
  }
  if (-not (Test-Path $Vpy)) { Die "venv creation failed; $Vpy not found." }

  $ver = (& $Vpy -V)
  if ($ver -notmatch "3\.11\.") {
    Die "venv is not 3.11 ($ver). Delete .venv and re-run."
  }
  Write-Host "venv OK: $ver"
}

function Install-Deps {
  Write-Head "Installing build deps into venv"
  if (-not $SkipPipUpgrade) {
    & $Vpy -m pip install --upgrade pip
  }
  & $Vpip install --upgrade setuptools wheel
  # Core deps
  & $Vpip install pyinstaller
  # GUI stacks
  & $Vpip install PySide6
  & $Vpip install pygame
  # Optional: install your package to make imports available everywhere
  # (comment out if you prefer pure sys.path based dev)
  Push-Location $RepoRoot
  try { & $Vpip install -e . } finally { Pop-Location }
}

function Clean-BuildDirs {
  Write-Head "Cleaning build/ and dist/"
  Push-Location $RepoRoot
  try {
    if (Test-Path "$RepoRoot\build") { Remove-Item -Recurse -Force "$RepoRoot\build" }
    if (Test-Path "$RepoRoot\dist")  { Remove-Item -Recurse -Force "$RepoRoot\dist" }
  } finally { Pop-Location }
}

# ---- Builders ----
function Build-Designer {
  Write-Head "Building battle-agent-designer (Qt / PySide6)"
  Push-Location $RepoRoot
  try {
    & $Vpyi -y --clean --name battle-agent-designer --windowed `
      --paths "client\src" `
      --collect-all "battle_client" `
      --collect-all "PySide6" `
      "app\agent_designer.py"
  } finally { Pop-Location }
}

function Build-MatchRunner {
  Write-Head "Building match_runner (Pygame)"
  Push-Location $RepoRoot
  try {
    & $Vpyi -y --clean --name match_runner --windowed `
      --paths "client\src" `
      --collect-all "battle_client" `
      --collect-submodules "pygame" `
      "app\match_runner.py"
  } finally { Pop-Location }
}

function Build-CLI {
  Write-Head "Building battle-cli (engine CLI)"
  Push-Location $RepoRoot
  try {
    & $Vpyi -y --clean --name battle-cli --console `
      --paths "engine\src" `
      --collect-all "battle_engine" `
      --collect-all "battle_client" `
      "engine\src\battle_engine\cli.py"
  } finally { Pop-Location }
}

# ---- Smoke tests ----
function Smoke-Tests {
  Write-Head "Smoke tests (existence)"
  $paths = @(
    "dist\battle-agent-designer\battle-agent-designer.exe",
    "dist\match_runner\match_runner.exe",
    "dist\battle-cli\battle-cli.exe"
  )
  foreach ($p in $paths) {
    $full = Join-Path $RepoRoot $p
    if (-not (Test-Path $full)) { Die "Missing expected artifact: $p" }
    Write-Host "OK: $p"
  }

  Write-Head "Smoke tests (run --help where applicable)"
  # CLI should print help/version without GUI
  & "$RepoRoot\dist\battle-cli\battle-cli.exe" --help | Out-Host
  Write-Host "RUN: GUI apps manually (double-click) to verify windows appear."
}

# ---- Main ----
Ensure-Py311
New-Or-Reset-Venv
Install-Deps
Clean-BuildDirs

Build-Designer
Build-MatchRunner
Build-CLI

Smoke-Tests

Write-Head "Build complete."
Write-Host "Artifacts:"
Write-Host "  $RepoRoot\dist\battle-agent-designer\battle-agent-designer.exe"
Write-Host "  $RepoRoot\dist\match_runner\match_runner.exe"
Write-Host "  $RepoRoot\dist\battle-cli\battle-cli.exe"
