<# 
  Purpose: Sync working copy on Windows
  - Fetch/pull latest, optional auto-stash
  - Init/update submodules
  - Ensure venv and install requirements
  Usage:
    pwsh -ExecutionPolicy Bypass -File .\sync_win.ps1
    pwsh -ExecutionPolicy Bypass -File .\sync_win.ps1 -Branch main -NoStash -NoDevDeps
#>

[CmdletBinding()]
param(
  [string]$Branch = "main",
  [switch]$NoStash,
  [switch]$NoSubmodules,
  [switch]$NoDevDeps
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Has-GitChanges {
  $status = git status --porcelain
  return -not [string]::IsNullOrWhiteSpace($status)
}

# 0) Preconditions
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "git not found in PATH." }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "python not found in PATH." }

# Normalize line endings for Windows devs (safe for CRLF checkouts)
git config core.autocrlf true | Out-Null

# 1) Stash any local changes (unless disabled)
if (-not $NoStash) {
  if (Has-GitChanges) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    git stash push -u -m "sync_win auto-stash $stamp" | Out-Null
    Write-Host "[sync] Local changes stashed: sync_win auto-stash $stamp"
  }
}

# 2) Fetch & fast-forward to target branch
Write-Host "[sync] Fetching..."
git fetch --all --prune

Write-Host "[sync] Checking out $Branch..."
git checkout $Branch

Write-Host "[sync] Pulling latest (ff-only)..."
git pull --ff-only origin $Branch

# 3) Submodules
if (-not $NoSubmodules) {
  Write-Host "[sync] Updating submodules..."
  git submodule update --init --recursive --jobs 4
}

# 4) Python venv
$venv = Join-Path $PWD ".venv"
if (-not (Test-Path $venv)) {
  Write-Host "[sync] Creating virtual environment..."
  python -m venv .venv
}

Write-Host "[sync] Activating virtual environment..."
. .\.venv\Scripts\Activate.ps1

# 5) Pip + requirements
python -m pip install --upgrade pip wheel

# Install core/client requirements if present
$reqs = @()
if (Test-Path ".\requirements-core.txt")   { $reqs += ".\requirements-core.txt" }
if (Test-Path ".\requirements-client.txt") { $reqs += ".\requirements-client.txt" }
if (-not $NoDevDeps -and (Test-Path ".\requirements-dev.txt")) { $reqs += ".\requirements-dev.txt" }

if ($reqs.Count -gt 0) {
  Write-Host "[sync] Installing requirements: $($reqs -join ', ')"
  pip install -r $reqs
} else {
  Write-Host "[sync] No requirements files found; skipping pip install."
}

# 6) Create common run/build dirs (idempotent)
New-Item -ItemType Directory -Force -Path ".\runs\_loose" | Out-Null
New-Item -ItemType Directory -Force -Path ".\dist\windows" | Out-Null
New-Item -ItemType Directory -Force -Path ".\build\windows" | Out-Null

# 7) Helpful environment echo
$sep = ";"
Write-Host "[sync] Recommended PYTHONPATH for this shell:"
Write-Host ("engine\src{0}client\src" -f $sep)

Write-Host "[done] Sync complete. Activate venv with:  .\.venv\Scripts\Activate.ps1"
Write-Host "[done] Next: run editor via:  python .\app\main.py"
