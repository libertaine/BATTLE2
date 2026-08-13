<#
  Purpose: Optional Windows convenience script for a returning contributor.
  - Fetch/pull latest (optional auto-stash of local changes)
  - Create/activate a .venv if missing
  - Install the project in editable mode with the extras CONTRIBUTING.md
    documents (dev, replay, designer)
  Usage:
    pwsh -ExecutionPolicy Bypass -File .\sync_win.ps1
    pwsh -ExecutionPolicy Bypass -File .\sync_win.ps1 -Branch main -NoStash -NoDevDeps
#>

[CmdletBinding()]
param(
  [string]$Branch = "main",
  [switch]$NoStash,
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

# 3) Python venv
$venv = Join-Path $PWD ".venv"
if (-not (Test-Path $venv)) {
  Write-Host "[sync] Creating virtual environment..."
  python -m venv .venv
}

Write-Host "[sync] Activating virtual environment..."
. .\.venv\Scripts\Activate.ps1

# 4) Editable install with the extras CONTRIBUTING.md/INSTALL.md document
python -m pip install --upgrade pip wheel

$extras = "replay,designer"
if (-not $NoDevDeps) { $extras = "dev,$extras" }
Write-Host "[sync] Installing: pip install -e .[$extras]"
python -m pip install -e ".[$extras]"

Write-Host "[done] Sync complete. Activate venv with:  .\.venv\Scripts\Activate.ps1"
Write-Host "[done] Next: run the designer via:  bytefray design"
Write-Host "[done] Or run tests via:  python -m pytest"
