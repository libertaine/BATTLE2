param([string]$Mode = "Release")

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDir = $PSScriptRoot
$RepoRoot  = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $RepoRoot

# venv paths
$VenvDir = Join-Path $RepoRoot ".venv"
$PyExe   = Join-Path $VenvDir "Scripts\python.exe"
$ActPs1  = Join-Path $VenvDir "Scripts\Activate.ps1"

# Ensure Python available to create venv if needed
if (-not (Test-Path $VenvDir)) {
  Write-Host "[build] Creating virtual environment at .venv..."
  python -m venv $VenvDir
}

# Activate only if not already active (ok to skip if your policy blocks it)
if (-not $env:VIRTUAL_ENV) {
  try {
    . $ActPs1
  } catch {
    Write-Warning "[build] Activation script blocked; continuing without dot-activation."
  }
}

# Sanity: use venv's python exclusively (avoid PATH/Git '/usr/bin' issues)
if (-not (Test-Path $PyExe)) {
  throw "Venv python not found at $PyExe"
}

# Helper to run 'python -m <module> ...'
function Run-PyMod {
  param([Parameter(Mandatory)][string]$Module, [Parameter()][string[]]$Args)
  & $PyExe -m $Module @Args
  if ($LASTEXITCODE -ne 0) { throw "python -m $Module failed with exit code $LASTEXITCODE" }
}

# --- Dependencies -------------------------------------------------------------
Run-PyMod -Module pip -Args @("install","--upgrade","pip","wheel")

$reqs = @()
if (Test-Path ".\requirements-core.txt")   { $reqs += ".\requirements-core.txt" }
if (Test-Path ".\requirements-client.txt") { $reqs += ".\requirements-client.txt" }
if (Test-Path ".\requirements-dev.txt")    { $reqs += ".\requirements-dev.txt" }

if ($reqs.Count -gt 0) {
  Write-Host "[build] Installing requirements: $($reqs -join ', ')"
  $reqArgs = @("install")
  foreach ($r in $reqs) { $reqArgs += @("-r", $r) }
  Run-PyMod -Module pip -Args $reqArgs
} else {
  Write-Host "[build] No requirements files found. Installing minimal build deps..."
  Run-PyMod -Module pip -Args @("install","pyinstaller")
}

# Ensure PyInstaller available (from venv)
Run-PyMod -Module pip -Args @("show","pyinstaller") | Out-Null

# Output dirs
$BuildDir = Join-Path $RepoRoot "build\windows"
$DistDir  = Join-Path $RepoRoot "dist\windows"
Remove-Item -Recurse -Force $BuildDir -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $DistDir  -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null
New-Item -ItemType Directory -Force -Path $DistDir  | Out-Null

# Spec files
$SpecEditor = Join-Path $RepoRoot "tools\agent_designer.spec"
$SpecViewer = Join-Path $RepoRoot "tools\replay_viewer.spec"
if (-not (Test-Path $SpecEditor)) { throw "Missing spec: tools\agent_designer.spec" }
if (-not (Test-Path $SpecViewer)) { throw "Missing spec: tools\replay_viewer.spec" }

# Build using venv's PyInstaller
Write-Host "[build] Building BattleAgentDesigner..."
& $PyExe -m PyInstaller --noconfirm --clean --workpath $BuildDir --distpath $DistDir $SpecEditor
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build (editor) failed." }

Write-Host "[build] Building BattleReplayViewer..."
& $PyExe -m PyInstaller --noconfirm --clean --workpath $BuildDir --distpath $DistDir $SpecViewer
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build (viewer) failed." }

Write-Host ""
Write-Host "[build] Success."
Write-Host ("[build] Editor:   {0}" -f (Join-Path $DistDir "BattleAgentDesigner\BattleAgentDesigner.exe"))
Write-Host ("[build] Viewer:   {0}" -f (Join-Path $DistDir "BattleReplayViewer\BattleReplayViewer.exe"))
Write-Host ("[build] Dist dir: {0}" -f $DistDir)
