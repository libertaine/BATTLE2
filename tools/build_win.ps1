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
Run-PyMod -Module pip -Args @("install", "-e", ".[replay,designer,windows-build]")

# Ensure PyInstaller available (from venv)
Run-PyMod -Module pip -Args @("show","pyinstaller") | Out-Null

# Output dirs
$BuildDir = Join-Path $RepoRoot "build\windows"
$DistDir  = Join-Path $RepoRoot "dist\windows"
Remove-Item -Recurse -Force $BuildDir -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $DistDir  -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null
New-Item -ItemType Directory -Force -Path $DistDir  | Out-Null

# Required v0.2 artifacts. Keep each app in its own onedir folder so the same
# layout can be copied beneath an installer's bin directory without renaming.
$Artifacts = @(
  @{ Name = "battle2";                 Spec = "tools\battle2.spec" },
  @{ Name = "battle-cli";              Spec = "tools\battle_cli.spec" },
  @{ Name = "match-runner";            Spec = "tools\match_runner.spec" },
  @{ Name = "battle-agent-designer";   Spec = "tools\agent_designer.spec" },
  @{ Name = "battle-replay-viewer";    Spec = "tools\replay_viewer.spec" }
)

foreach ($Artifact in $Artifacts) {
  $SpecPath = Join-Path $RepoRoot $Artifact.Spec
  if (-not (Test-Path $SpecPath)) { throw "Missing spec: $($Artifact.Spec)" }
  Write-Host "[build] Building $($Artifact.Name)..."
  & $PyExe -m PyInstaller --noconfirm --clean --workpath $BuildDir --distpath $DistDir $SpecPath
  if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed: $($Artifact.Name)" }

  $ExePath = Join-Path $DistDir "$($Artifact.Name)\$($Artifact.Name).exe"
  if (-not (Test-Path $ExePath)) { throw "Expected artifact was not produced: $ExePath" }
}

Write-Host ""
Write-Host "[build] Success."
foreach ($Artifact in $Artifacts) {
  Write-Host ("[build] {0}: {1}" -f $Artifact.Name, (Join-Path $DistDir "$($Artifact.Name)\$($Artifact.Name).exe"))
}
Write-Host ("[build] Dist dir: {0}" -f $DistDir)
