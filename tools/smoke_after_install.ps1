<# 
Smoke test for BATTLE2 installed apps.

Usage examples:
  # default path (C:\Program Files\BATTLE2)
  powershell -ExecutionPolicy Bypass -File tools\smoke_after_install.ps1

  # if you installed to E:\Program Files\BATTLE2
  powershell -ExecutionPolicy Bypass -File tools\smoke_after_install.ps1 -AppDir "E:\Program Files\BATTLE2"
#>

[CmdletBinding()]
param(
  [string]$AppDir = "$Env:ProgramFiles\BATTLE2",
  [int]$GuiHoldSeconds = 6
)

$ErrorActionPreference = "Stop"

function Log($msg) {
  $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  $line = "$ts  $msg"
  Write-Host $line
  Add-Content -Path $Global:LogFile -Value $line
}
function Assert-Exists($path, $what) {
if (!(Test-Path $path)) { throw "Missing ${what}: ${path}" }
  Log "OK: $what exists -> $path"
}
function Assert-True($cond, $msg) {
  if (-not $cond) { throw $msg }
  Log "OK: $msg"
}

# --- Setup log/output locations ---
$B2Data = [Environment]::ExpandEnvironmentVariables("%ProgramData%\BATTLE2")
$LogDir = Join-Path $B2Data "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Global:LogFile = Join-Path $LogDir "smoke.log"

Log "=== BATTLE2 Smoke Test ==="
Log "AppDir=$AppDir"
Log "ProgramData=$B2Data"
Log "LogFile=$LogFile"

# --- Resolve app folders/exes (onedir layout) ---
$ExeDesigner = Join-Path $AppDir "bin\battle-agent-designer\battle-agent-designer.exe"
$ExeRunner   = Join-Path $AppDir "bin\match_runner\match_runner.exe"
$ExeCli      = Join-Path $AppDir "bin\battle-cli\battle-cli.exe"

Assert-Exists $ExeDesigner "Designer exe"
Assert-Exists $ExeRunner   "Match runner exe"
Assert-Exists $ExeCli      "CLI exe"

# verify embedded Python runtimes exist (common failure)
Assert-Exists (Join-Path $AppDir "bin\battle-agent-designer\_internal\python311.dll") "Designer runtime"
Assert-Exists (Join-Path $AppDir "bin\match_runner\_internal\python311.dll")         "Runner runtime"
Assert-Exists (Join-Path $AppDir "bin\battle-cli\_internal\python311.dll")           "CLI runtime"

# --- 1) CLI smoke: run short match and create replay ---
$RunsDir = Join-Path $B2Data "runs\_loose"
New-Item -ItemType Directory -Force -Path $RunsDir | Out-Null
$Replay = Join-Path $RunsDir ("smoke_{0:yyyyMMdd_HHmmss}.jsonl" -f (Get-Date))
$cliArgs = @('--ticks', '100', '--replay', $Replay, '--quiet')

Log "Running CLI: $ExeCli $($cliArgs -join ' ')"
$cli = Start-Process -FilePath $ExeCli -ArgumentList $cliArgs -NoNewWindow -PassThru -Wait
Assert-True ($cli.ExitCode -eq 0) "CLI exit code = 0"

Assert-Exists $Replay "Replay output"
$fileInfo = Get-Item $Replay
Assert-True ($fileInfo.Length -gt 0) "Replay non-empty"
# peek at first line (JSONL)
$head = Get-Content $Replay -TotalCount 1
Assert-True ($head.Length -gt 0) "Replay has at least one JSON line"

# --- 2) GUI smoke: match_runner (Pygame) ---
Log "Launching match_runner for $GuiHoldSeconds seconds…"
$pr = Start-Process -FilePath $ExeRunner -PassThru
Start-Sleep -Seconds $GuiHoldSeconds
# if it died immediately, ExitCode will be set; if still running, Close it
if ($pr.HasExited) {
  throw "match_runner exited early (ExitCode=$($pr.ExitCode))."
}
# try to close gracefully; if not, kill
try { $pr.CloseMainWindow() | Out-Null; Start-Sleep 1 } catch {}
try { if (-not $pr.HasExited) { Stop-Process -Id $pr.Id -Force } } catch {}
Log "match_runner stayed up, then closed."

# --- 3) GUI smoke: battle-agent-designer (Qt) ---
Log "Launching battle-agent-designer for $GuiHoldSeconds seconds…"
$pd = Start-Process -FilePath $ExeDesigner -PassThru
Start-Sleep -Seconds $GuiHoldSeconds
if ($pd.HasExited) {
  throw "battle-agent-designer exited early (ExitCode=$($pd.ExitCode))."
}
try { $pd.CloseMainWindow() | Out-Null; Start-Sleep 1 } catch {}
try { if (-not $pd.HasExited) { Stop-Process -Id $pd.Id -Force } } catch {}
Log "battle-agent-designer stayed up, then closed."

Log "=== SUCCESS: All smokes passed ==="
"OK"
