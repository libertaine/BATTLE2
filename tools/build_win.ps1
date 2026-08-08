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

# Exercise the dynamically imported Designer from the unified dispatcher and
# the standalone Designer. The internal timeout enters the Qt event loop and
# closes deterministically without requiring desktop automation.
$PreviousSmokeExit = $env:BATTLE2_GUI_SMOKE_EXIT_MS
try {
  $env:BATTLE2_GUI_SMOKE_EXIT_MS = "750"
  foreach ($Smoke in @(
    @{ Path = (Join-Path $DistDir "battle2\battle2.exe"); Args = @("design") },
    @{ Path = (Join-Path $DistDir "battle-agent-designer\battle-agent-designer.exe"); Args = @() }
  )) {
    Write-Host ("[build] GUI import/startup smoke: {0}" -f $Smoke.Path)
    & $Smoke.Path @($Smoke.Args)
    if ($LASTEXITCODE -ne 0) {
      throw "GUI import/startup smoke failed with exit code $LASTEXITCODE`: $($Smoke.Path)"
    }
  }
} finally {
  if ($null -eq $PreviousSmokeExit) {
    Remove-Item Env:BATTLE2_GUI_SMOKE_EXIT_MS -ErrorAction SilentlyContinue
  } else {
    $env:BATTLE2_GUI_SMOKE_EXIT_MS = $PreviousSmokeExit
  }
}

# Exercise 'bytefray agents create' against the actual frozen battle2.exe in
# an isolated, throwaway BYTEFRAY_ROOT. This is a regression check for a
# real, previously-shipped defect: tools/battle2.spec bundled
# battle_engine/data/starter_agents but not the sibling
# battle_engine/data/agent_template directory 'agents create' depends on, so
# the resource was silently absent from the frozen build's _MEIPASS
# extraction directory even though source checkouts and installed wheels
# both already had it. A config-level test (engine/tests/
# test_windows_packaging_spec.py) covers the .spec file's data list without
# needing a real build; this block is the actual, executable-level proof.
$SmokeRoot = Join-Path ([IO.Path]::GetTempPath()) ("bytefray-agents-create-smoke-" + [Guid]::NewGuid().ToString("N"))
$PreviousBytefrayRoot = $env:BYTEFRAY_ROOT
try {
  New-Item -ItemType Directory -Force -Path $SmokeRoot | Out-Null
  $env:BYTEFRAY_ROOT = $SmokeRoot
  $Battle2Exe = Join-Path $DistDir "battle2\battle2.exe"
  Write-Host "[build] 'agents create' smoke test against $Battle2Exe (BYTEFRAY_ROOT=$SmokeRoot)"
  & $Battle2Exe agents create smoke_agent
  if ($LASTEXITCODE -ne 0) {
    throw "'battle2.exe agents create smoke_agent' failed with exit code $LASTEXITCODE"
  }
  $ManifestPath = Join-Path $SmokeRoot "agents\smoke_agent\agent.yaml"
  $SourcePath = Join-Path $SmokeRoot "agents\smoke_agent\agent.py"
  if (-not (Test-Path $ManifestPath) -or -not (Test-Path $SourcePath)) {
    throw "'battle2.exe agents create smoke_agent' did not write the expected agent.yaml/agent.py under $SmokeRoot"
  }
  Write-Host "[build] 'agents create' smoke test passed."
} finally {
  if ($null -eq $PreviousBytefrayRoot) {
    Remove-Item Env:BYTEFRAY_ROOT -ErrorAction SilentlyContinue
  } else {
    $env:BYTEFRAY_ROOT = $PreviousBytefrayRoot
  }
  Remove-Item -Recurse -Force $SmokeRoot -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "[build] Success."
foreach ($Artifact in $Artifacts) {
  Write-Host ("[build] {0}: {1}" -f $Artifact.Name, (Join-Path $DistDir "$($Artifact.Name)\$($Artifact.Name).exe"))
}
Write-Host ("[build] Dist dir: {0}" -f $DistDir)
