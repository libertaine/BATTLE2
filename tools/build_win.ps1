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

# Keep each app in its own onedir folder so the same
# layout can be copied beneath an installer's bin directory without renaming.
$Artifacts = @(
  @{ Name = "bytefray";                 Spec = "tools\bytefray.spec" },
  @{ Name = "bytefray-cli";             Spec = "tools\bytefray_cli.spec" },
  @{ Name = "bytefray-agent-designer";  Spec = "tools\agent_designer.spec" },
  @{ Name = "bytefray-replay-viewer";   Spec = "tools\replay_viewer.spec" }
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
#
# AgentDesigner.__init__ eagerly calls ensure_starter_agents() against
# whatever data root get_data_root() resolves; a portable/frozen app with no
# BYTEFRAY_ROOT set defaults to writing beside its own executable
# (battle_engine.paths), so without isolation this smoke test previously
# left a runtime-generated agents/ directory inside the distributable trees,
# contaminating the exact tree
# tools/installer.iss and the portable ZIP both package verbatim. Isolated
# the same way the 'agents create' smoke block below already isolates
# BYTEFRAY_ROOT, so build qualification cannot pollute the distributable
# tree regardless of what a smoked GUI happens to initialize on startup.
$PreviousSmokeExit = $env:BYTEFRAY_GUI_SMOKE_EXIT_MS
$PreviousGuiSmokeRoot = $env:BYTEFRAY_ROOT
$GuiSmokeRoot = Join-Path ([IO.Path]::GetTempPath()) ("bytefray-gui-smoke-" + [Guid]::NewGuid().ToString("N"))
try {
  New-Item -ItemType Directory -Force -Path $GuiSmokeRoot | Out-Null
  $env:BYTEFRAY_GUI_SMOKE_EXIT_MS = "750"
  $env:BYTEFRAY_ROOT = $GuiSmokeRoot
  foreach ($Smoke in @(
    @{ Path = (Join-Path $DistDir "bytefray\bytefray.exe"); Args = @("design") },
    @{ Path = (Join-Path $DistDir "bytefray-agent-designer\bytefray-agent-designer.exe"); Args = @() }
  )) {
    Write-Host ("[build] GUI import/startup smoke: {0}" -f $Smoke.Path)
    # PowerShell does not wait for a Windows GUI-subsystem executable when
    # invoked with `&`. Start-Process -Wait is therefore required for the
    # standalone Designer: without it, $LASTEXITCODE is stale and the temp
    # root can be deleted before the still-starting child writes to it.
    $SmokeProcess = Start-Process -FilePath $Smoke.Path -ArgumentList @($Smoke.Args) -Wait -PassThru -WindowStyle Hidden
    if ($SmokeProcess.ExitCode -ne 0) {
      throw "GUI import/startup smoke failed with exit code $($SmokeProcess.ExitCode)`: $($Smoke.Path)"
    }
  }
} finally {
  if ($null -eq $PreviousSmokeExit) {
    Remove-Item Env:BYTEFRAY_GUI_SMOKE_EXIT_MS -ErrorAction SilentlyContinue
  } else {
    $env:BYTEFRAY_GUI_SMOKE_EXIT_MS = $PreviousSmokeExit
  }
  if ($null -eq $PreviousGuiSmokeRoot) {
    Remove-Item Env:BYTEFRAY_ROOT -ErrorAction SilentlyContinue
  } else {
    $env:BYTEFRAY_ROOT = $PreviousGuiSmokeRoot
  }
  if (Test-Path -LiteralPath $GuiSmokeRoot) {
    Remove-Item -LiteralPath $GuiSmokeRoot -Recurse -Force -ErrorAction Stop
  }
  if (Test-Path -LiteralPath $GuiSmokeRoot) {
    throw "GUI smoke temporary root could not be removed: $GuiSmokeRoot"
  }
}

# Exercise 'bytefray agents create' against the actual frozen bytefray.exe in
# an isolated, throwaway BYTEFRAY_ROOT. This is a regression check for a
# real, previously-shipped defect: the unified executable spec bundled
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
  $BytefrayExe = Join-Path $DistDir "bytefray\bytefray.exe"
  Write-Host "[build] 'agents create' smoke test against $BytefrayExe (BYTEFRAY_ROOT=$SmokeRoot)"
  & $BytefrayExe agents create smoke_agent
  if ($LASTEXITCODE -ne 0) {
    throw "'bytefray.exe agents create smoke_agent' failed with exit code $LASTEXITCODE"
  }
  $ManifestPath = Join-Path $SmokeRoot "agents\smoke_agent\agent.yaml"
  $SourcePath = Join-Path $SmokeRoot "agents\smoke_agent\agent.py"
  if (-not (Test-Path $ManifestPath) -or -not (Test-Path $SourcePath)) {
    throw "'bytefray.exe agents create smoke_agent' did not write the expected agent.yaml/agent.py under $SmokeRoot"
  }
  Write-Host "[build] 'agents create' smoke test passed."
} finally {
  if ($null -eq $PreviousBytefrayRoot) {
    Remove-Item Env:BYTEFRAY_ROOT -ErrorAction SilentlyContinue
  } else {
    $env:BYTEFRAY_ROOT = $PreviousBytefrayRoot
  }
  if (Test-Path -LiteralPath $SmokeRoot) {
    Remove-Item -LiteralPath $SmokeRoot -Recurse -Force -ErrorAction Stop
  }
  if (Test-Path -LiteralPath $SmokeRoot) {
    throw "'agents create' smoke temporary root could not be removed: $SmokeRoot"
  }
}

# Final proof, not just a hope, that build qualification above (GUI smoke,
# 'agents create' smoke) left no runtime-generated data root under any of
# the four distributable application trees -- both smoke blocks isolate
# their own BYTEFRAY_ROOT, so an agents\ directory appearing here means
# something still resolved the frozen app's default (beside-the-exe) data
# root instead of the isolated one.
foreach ($Artifact in $Artifacts) {
  $ResidueDir = Join-Path $DistDir "$($Artifact.Name)\agents"
  if (Test-Path $ResidueDir) {
    throw "Build qualification left runtime-generated data under $ResidueDir -- smoke tests must run against an isolated BYTEFRAY_ROOT, not the app's default data root."
  }
}

Write-Host ""
Write-Host "[build] Success."
foreach ($Artifact in $Artifacts) {
  Write-Host ("[build] {0}: {1}" -f $Artifact.Name, (Join-Path $DistDir "$($Artifact.Name)\$($Artifact.Name).exe"))
}
Write-Host ("[build] Dist dir: {0}" -f $DistDir)
