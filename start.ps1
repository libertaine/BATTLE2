# -----------------------------------------------
# Project startup script for BATTLE2
# -----------------------------------------------

# Move to repo root
Set-Location -Path "D:\Projects\BATTLE2"

# Activate virtual environment
$venv = ".\.venv\Scripts\Activate.ps1"
if (Test-Path $venv) {
    & $venv
    Write-Host "✓ Virtual environment activated." -ForegroundColor Green
} else {
    Write-Warning "Virtual environment not found. Run: python -m venv .venv"
}

# Set PYTHONPATH for engine + client
$env:PYTHONPATH = (Resolve-Path .\engine\src).Path + ';' + (Resolve-Path .\client\src).Path

# (optional) Default agents directory (helps GUI find agents)
$env:BATTLE_AGENTS_DIR = (Resolve-Path .\agents).Path

# (optional) Extra PATH entries if you want CLI tools callable
$env:Path = (Resolve-Path .\tools).Path + ";" + $env:Path

# Confirm setup
Write-Host "PYTHONPATH =" $env:PYTHONPATH -ForegroundColor DarkGray
Write-Host "BATTLE_AGENTS_DIR =" $env:BATTLE_AGENTS_DIR -ForegroundColor DarkGray
Write-Host "`nReady to run:" -ForegroundColor Cyan
Write-Host "   python app\agent_designer.py"
Write-Host "   python -m battle_engine.cli --help"


if (Test-Path .\tools\smoke_test.ps1) {
    Write-Host "`nRunning smoke test..." -ForegroundColor Cyan
    & .\tools\smoke_test.ps1
}


code . 

