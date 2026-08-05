<#
Smoke validation for either a BATTLE2 install root or dist\windows build root.

Examples:
  pwsh tools/smoke_after_install.ps1
  pwsh tools/smoke_after_install.ps1 -AppDir dist\windows -SkipGui
#>
[CmdletBinding()]
param(
  [string]$AppDir = "$Env:ProgramFiles\BATTLE2",
  [int]$GuiHoldSeconds = 6,
  [switch]$SkipGui
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$B2Data = [Environment]::ExpandEnvironmentVariables("%ProgramData%\BATTLE2")
$LogDir = Join-Path $B2Data "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Global:LogFile = Join-Path $LogDir "smoke.log"

function Log([string]$Message) {
  $Line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $Message"
  Write-Host $Line
  Add-Content -Path $Global:LogFile -Value $Line
}

function Resolve-Artifact([string]$Name) {
  $Candidates = @(
    (Join-Path $AppDir "$Name\$Name.exe"),
    (Join-Path $AppDir "bin\$Name\$Name.exe")
  )
  foreach ($Candidate in $Candidates) {
    if (Test-Path $Candidate) { return (Resolve-Path $Candidate).Path }
  }
  throw "Missing $Name executable. Checked: $($Candidates -join ', ')"
}

function Invoke-Checked([string]$Exe, [string[]]$Arguments, [string]$Description) {
  Log "$Description`: $Exe $($Arguments -join ' ')"
  & $Exe @Arguments
  if ($LASTEXITCODE -ne 0) { throw "$Description failed with exit code $LASTEXITCODE" }
}

function Test-GuiStartup([string]$Exe, [string]$Description) {
  Log "Launching $Description for $GuiHoldSeconds seconds..."
  $Process = Start-Process -FilePath $Exe -PassThru
  Start-Sleep -Seconds $GuiHoldSeconds
  if ($Process.HasExited) { throw "$Description exited early (ExitCode=$($Process.ExitCode))." }
  try { $Process.CloseMainWindow() | Out-Null; Start-Sleep -Seconds 1 } catch {}
  try { if (-not $Process.HasExited) { Stop-Process -Id $Process.Id -Force } } catch {}
}

Log "=== BATTLE2 Windows smoke test ==="
Log "AppDir=$AppDir"

$ExeBattle2  = Resolve-Artifact "battle2"
$ExeCli      = Resolve-Artifact "battle-cli"
$ExeRunner   = Resolve-Artifact "match-runner"
$ExeDesigner = Resolve-Artifact "battle-agent-designer"
$ExeViewer   = Resolve-Artifact "battle-replay-viewer"

# CLI startup and compatibility command validation.
Invoke-Checked $ExeBattle2 @("--help") "battle2 help"
Invoke-Checked $ExeCli @("--help") "legacy battle-cli help"

# A short primary-command native match creates the replay consumed below.
$RunsDir = Join-Path $B2Data "runs\_loose"
New-Item -ItemType Directory -Force -Path $RunsDir | Out-Null
$Replay = Join-Path $RunsDir ("smoke_{0:yyyyMMdd_HHmmss}.jsonl" -f (Get-Date))
Invoke-Checked $ExeBattle2 @("run", "--ticks", "10", "--replay", $Replay, "--quiet") "headless native match"
if (-not (Test-Path $Replay)) { throw "Native match did not create replay: $Replay" }
if ((Get-Item $Replay).Length -le 0) { throw "Native match replay is empty: $Replay" }

# Both supported viewer argument forms must reach the shared replay service.
Invoke-Checked $ExeViewer @("--help") "replay viewer help"
Invoke-Checked $ExeViewer @($Replay, "--renderer", "headless") "replay viewer positional replay"
Invoke-Checked $ExeViewer @("--replay", $Replay, "--renderer", "headless") "replay viewer named replay"

if (-not $SkipGui) {
  Test-GuiStartup $ExeRunner "match-runner"
  Test-GuiStartup $ExeDesigner "battle-agent-designer"
}

Log "=== SUCCESS: all requested Windows smokes passed ==="
