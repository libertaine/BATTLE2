param([string]$Mode="Release")

$ErrorActionPreference="Stop"
Set-Location (Resolve-Path "..")
. .\.venv\Scripts\Activate.ps1

pip install -r requirements-core.txt -r requirements-client.txt -r requirements-dev.txt

Remove-Item -Recurse -Force build\windows -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force dist\windows  -ErrorAction SilentlyContinue
mkdir build\windows | Out-Null
mkdir dist\windows  | Out-Null

pyinstaller --noconfirm --clean `
  --workpath build\windows `
  --distpath  dist\windows `
  tools\agent_designer.spec

pyinstaller --noconfirm --clean `
  --workpath build\windows `
  --distpath  dist\windows `
  tools\replay_viewer.spec

Write-Host "EXEs in dist/windows/BattleAgentDesigner and dist/windows/BattleReplayViewer"
