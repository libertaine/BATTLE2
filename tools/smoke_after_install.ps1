<#
Validates an installed Bytefray tree or performs an isolated install/upgrade/uninstall cycle.

Post-install smoke:
  pwsh tools/smoke_after_install.ps1

Full isolated lifecycle validation:
  pwsh tools/smoke_after_install.ps1 -InstallerPath dist\installer\Bytefray-Setup-1.0.1.exe `
    -AppDir "D:\Bytefray Test\Application" -DataRoot "D:\Bytefray Test\Data" -Lifecycle
#>
[CmdletBinding()]
param(
  [string]$AppDir = "$Env:ProgramFiles\Bytefray",
  # Installer keeps the writable data directory at ProgramData\BATTLE2 for
  # upgrade continuity; see the comment in tools/installer.iss GetDataRoot.
  [string]$DataRoot = "$Env:ProgramData\BATTLE2",
  [string]$InstallerPath,
  [int]$GuiHoldSeconds = 5,
  [switch]$SkipGui,
  [switch]$Lifecycle
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ArtifactNames = @(
  "battle2",
  "battle-cli",
  "battle-agent-designer",
  "battle-replay-viewer"
)
$AppDir = [IO.Path]::GetFullPath($AppDir)
$DataRoot = [IO.Path]::GetFullPath($DataRoot)
$Global:LogFile = Join-Path $DataRoot "logs\installer-smoke.log"

function Write-SmokeLog([string]$Message) {
  $Line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $Message"
  Write-Host $Line
  $Parent = Split-Path -Parent $Global:LogFile
  New-Item -ItemType Directory -Force -Path $Parent | Out-Null
  Add-Content -LiteralPath $Global:LogFile -Value $Line
}

function Invoke-ProcessChecked {
  param(
    [Parameter(Mandatory)][string]$Executable,
    [string[]]$Arguments = @(),
    [Parameter(Mandatory)][string]$Description,
    [int[]]$ExpectedExitCodes = @(0),
    [switch]$CaptureOutput
  )
  Write-SmokeLog "$Description`: $Executable $($Arguments -join ' ')"
  $StartInfo = [Diagnostics.ProcessStartInfo]::new()
  $StartInfo.FileName = $Executable
  $StartInfo.UseShellExecute = $false
  foreach ($Argument in $Arguments) { $StartInfo.ArgumentList.Add($Argument) }
  if ($CaptureOutput) {
    $StartInfo.RedirectStandardOutput = $true
    $StartInfo.RedirectStandardError = $true
  }
  $Process = [Diagnostics.Process]::Start($StartInfo)
  if ($CaptureOutput) {
    $Stdout = $Process.StandardOutput.ReadToEndAsync()
    $Stderr = $Process.StandardError.ReadToEndAsync()
  }
  $Process.WaitForExit()
  $Code = $Process.ExitCode
  if ($CaptureOutput) {
    $Output = $Stdout.GetAwaiter().GetResult() + $Stderr.GetAwaiter().GetResult()
    if ($Output) { Write-SmokeLog $Output.TrimEnd() }
  } else {
    $Output = ""
  }
  if ($Code -notin $ExpectedExitCodes) {
    throw "$Description failed with exit code $Code; expected $($ExpectedExitCodes -join ', ')."
  }
  return [PSCustomObject]@{ ExitCode = $Code; Output = $Output }
}

function Resolve-Artifact([string]$Name) {
  $Path = Join-Path $AppDir "bin\$Name\$Name.exe"
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    throw "Missing installed artifact: $Path"
  }
  return (Resolve-Path -LiteralPath $Path).Path
}

function Stop-SmokeApplication([string]$Executable, [string]$Description) {
  $Processes = @(Get-Process | Where-Object { $_.Path -eq $Executable })
  foreach ($Process in $Processes) {
    try { $null = $Process.CloseMainWindow() } catch {}
  }
  Start-Sleep -Seconds 2
  $Remaining = @(Get-Process | Where-Object { $_.Path -eq $Executable })
  foreach ($Process in $Remaining) {
    Write-SmokeLog "$Description did not close gracefully; stopping process $($Process.Id)."
    Stop-Process -Id $Process.Id -Force
  }
}

function Test-GuiStartup(
  [string]$Executable,
  [string[]]$Arguments,
  [string]$Description
) {
  Write-SmokeLog "Launching $Description for $GuiHoldSeconds seconds."
  $StartInfo = [Diagnostics.ProcessStartInfo]::new()
  $StartInfo.FileName = $Executable
  $StartInfo.UseShellExecute = $false
  foreach ($Argument in $Arguments) { $StartInfo.ArgumentList.Add($Argument) }
  $Process = [Diagnostics.Process]::Start($StartInfo)
  Start-Sleep -Seconds $GuiHoldSeconds
  $Running = @(Get-Process | Where-Object { $_.Path -eq $Executable })
  if ($Process.HasExited -and $Running.Count -eq 0) {
    throw "$Description exited before the startup hold completed (ExitCode=$($Process.ExitCode))."
  }
  Stop-SmokeApplication $Executable $Description
}

function Install-Battle2([string]$Description) {
  if (-not $InstallerPath) { throw "-InstallerPath is required with -Lifecycle." }
  $ResolvedInstaller = (Resolve-Path -LiteralPath $InstallerPath).Path
  $Result = Invoke-ProcessChecked -Executable $ResolvedInstaller -Description $Description -Arguments @(
    "/VERYSILENT",
    "/SUPPRESSMSGBOXES",
    "/NORESTART",
    "/DIR=$AppDir",
    "/BATTLE2DATAROOT=$DataRoot"
  ) -CaptureOutput
  if ($Result.ExitCode -ne 0) { throw "$Description failed." }
}

function Invoke-InstalledSmoke {
  $env:BYTEFRAY_ROOT = $DataRoot
  Remove-Item Env:BATTLE_ROOT -ErrorAction SilentlyContinue
  Write-SmokeLog "Application root: $AppDir"
  Write-SmokeLog "Writable data root: $DataRoot"

  $Executables = @{}
  foreach ($Name in $ArtifactNames) { $Executables[$Name] = Resolve-Artifact $Name }
  $StructureLog = Join-Path $DataRoot "logs\installed-files.txt"
  Get-ChildItem -LiteralPath $AppDir -Recurse -Force | ForEach-Object {
    $_.FullName.Substring($AppDir.Length).TrimStart([IO.Path]::DirectorySeparatorChar)
  } | Set-Content -LiteralPath $StructureLog

  foreach ($CliArtifact in @("battle2", "battle-cli")) {
    $ArtifactDir = Split-Path -Parent $Executables[$CliArtifact]
    foreach ($Resource in @("pmars.exe", "COPYING")) {
      $ResourcePath = Join-Path $ArtifactDir "_internal\pmars\windows\$Resource"
      if (-not (Test-Path -LiteralPath $ResourcePath -PathType Leaf)) {
        throw "Bundled pMARS resource missing: $ResourcePath"
      }
    }
  }

  foreach ($WritableDirectory in @("agents", "replays", "logs", "runs\_loose")) {
    $Directory = Join-Path $DataRoot $WritableDirectory
    if (-not (Test-Path -LiteralPath $Directory -PathType Container)) {
      throw "Writable data directory missing: $Directory"
    }
  }

  $StartMenuGroup = Join-Path $Env:ProgramData "Microsoft\Windows\Start Menu\Programs\Bytefray"
  foreach ($ShortcutName in @("Bytefray Agent Designer.lnk", "Bytefray Replay Viewer.lnk")) {
    $Shortcut = Join-Path $StartMenuGroup $ShortcutName
    if (-not (Test-Path -LiteralPath $Shortcut -PathType Leaf)) {
      throw "Installed Start Menu shortcut missing: $Shortcut"
    }
  }

  $DesignerParent = Split-Path -Parent (Split-Path -Parent $Executables["battle-agent-designer"])
  $ExpectedBattle2 = Join-Path $DesignerParent "battle2\battle2.exe"
  $ExpectedViewer = Join-Path $DesignerParent "battle-replay-viewer\battle-replay-viewer.exe"
  if (-not (Test-Path -LiteralPath $ExpectedBattle2)) { throw "Designer sibling match executable missing: $ExpectedBattle2" }
  if (-not (Test-Path -LiteralPath $ExpectedViewer)) { throw "Designer sibling replay executable missing: $ExpectedViewer" }

  Invoke-ProcessChecked $Executables["battle2"] @("--help") "battle2 help" -CaptureOutput | Out-Null
  Invoke-ProcessChecked $Executables["battle-cli"] @("--help") "battle-cli help" -CaptureOutput | Out-Null
  Invoke-ProcessChecked $Executables["battle-replay-viewer"] @("--help") "replay viewer help" -CaptureOutput | Out-Null

  if (-not $SkipGui) {
    Test-GuiStartup $Executables["battle-agent-designer"] @() "Agent Designer"
  }

  $ExpectedAgents = @("runner", "writer", "seeker", "spiral")
  foreach ($Agent in $ExpectedAgents) {
    $Manifest = Join-Path $DataRoot "agents\$Agent\agent.yaml"
    if (-not (Test-Path -LiteralPath $Manifest)) { throw "Starter manifest missing: $Manifest" }
  }

  $Runs = Join-Path $DataRoot "runs\installer-smoke"
  New-Item -ItemType Directory -Force -Path $Runs | Out-Null
  $Replay = Join-Path $Runs "starter replay.jsonl"
  Invoke-ProcessChecked $Executables["battle2"] @(
    "run", "--ticks", "200", "--arena", "128", "--a-type", "seeker",
    "--b-type", "writer", "--b-start", "64", "--replay", $Replay, "--quiet"
  ) "starter-agent match" -CaptureOutput | Out-Null
  if ((Get-Item -LiteralPath $Replay).Length -le 0) { throw "Starter replay is missing or empty: $Replay" }

  if (-not $SkipGui) {
    Test-GuiStartup $Executables["battle-replay-viewer"] @(
      "--replay", $Replay, "--renderer", "pygame", "--tick-delay", "0.05"
    ) "Replay Viewer"
  }

  $WarriorDir = Join-Path $DataRoot "smoke warriors"
  New-Item -ItemType Directory -Force -Path $WarriorDir | Out-Null
  $WarriorA = Join-Path $WarriorDir "imp one.red"
  $WarriorB = Join-Path $WarriorDir "imp two.red"
  Set-Content -LiteralPath $WarriorA -Encoding ascii -Value ";redcode`n;name Imp One`nmov 0, 1`nend"
  Set-Content -LiteralPath $WarriorB -Encoding ascii -Value ";redcode`n;name Imp Two`nmov 0, 1`nend"
  Remove-Item Env:PMARS_CMD -ErrorAction SilentlyContinue
  Invoke-ProcessChecked $Executables["battle2"] @(
    "run", "--mode", "redcode94", "--red-a", $WarriorA, "--red-b", $WarriorB,
    "--rounds", "1", "--replay", (Join-Path $Runs "pmars replay.jsonl"), "--quiet"
  ) "bundled pMARS match" -CaptureOutput | Out-Null

  $InvalidDir = Join-Path $Runs "invalid-pmars"
  $env:PMARS_CMD = Join-Path $DataRoot "missing pMARS\pmars.exe"
  $Invalid = Invoke-ProcessChecked $Executables["battle2"] @(
    "run", "--mode", "redcode94", "--red-a", $WarriorA, "--red-b", $WarriorB,
    "--replay", (Join-Path $InvalidDir "replay.jsonl"), "--quiet"
  ) "invalid PMARS_CMD" -ExpectedExitCodes @(2) -CaptureOutput
  if ($Invalid.Output -notmatch "Configured PMARS_CMD executable was not found") {
    throw "Invalid PMARS_CMD did not produce the normalized diagnostic."
  }
  if (Test-Path -LiteralPath (Join-Path $InvalidDir "summary.json")) {
    throw "Invalid PMARS_CMD produced a false success summary."
  }
  Remove-Item Env:PMARS_CMD -ErrorAction SilentlyContinue

  $Running = @(
    Get-Process | Where-Object { $_.Path -and $_.Path.StartsWith($AppDir, [StringComparison]::OrdinalIgnoreCase) }
  )
  if ($Running.Count -ne 0) { throw "Installed Bytefray processes remain: $($Running.Id -join ', ')" }
  Write-SmokeLog "Installed application smoke passed."
}

Write-SmokeLog "=== Bytefray Windows installer smoke ==="
if (-not $Lifecycle) {
  Invoke-InstalledSmoke
  Write-SmokeLog "=== SUCCESS ==="
  exit 0
}

$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$Principal = [Security.Principal.WindowsPrincipal]::new($Identity)
if (-not $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw "-Lifecycle must run from an elevated PowerShell because the installer sets a machine environment variable."
}
$PreviousMachineRoot = [Environment]::GetEnvironmentVariable("BATTLE2_ROOT", "Machine")
$PreviousMachineBytefrayRoot = [Environment]::GetEnvironmentVariable("BYTEFRAY_ROOT", "Machine")
try {
  Install-Battle2 "initial silent install"
  $MachineRoot = [Environment]::GetEnvironmentVariable("BATTLE2_ROOT", "Machine")
  if ([IO.Path]::GetFullPath($MachineRoot) -ne $DataRoot) {
    throw "Machine BATTLE2_ROOT mismatch: expected '$DataRoot', found '$MachineRoot'."
  }
  $MachineBytefrayRoot = [Environment]::GetEnvironmentVariable("BYTEFRAY_ROOT", "Machine")
  if ([IO.Path]::GetFullPath($MachineBytefrayRoot) -ne $DataRoot) {
    throw "Machine BYTEFRAY_ROOT mismatch: expected '$DataRoot', found '$MachineBytefrayRoot'."
  }
  Invoke-InstalledSmoke

  $RunnerManifest = Join-Path $DataRoot "agents\runner\agent.yaml"
  $ModifiedContent = (Get-Content -LiteralPath $RunnerManifest -Raw) + "`r`n "
  Set-Content -LiteralPath $RunnerManifest -Value $ModifiedContent -NoNewline
  $ModifiedHash = (Get-FileHash -LiteralPath $RunnerManifest -Algorithm SHA256).Hash
  $UserFile = Join-Path $DataRoot "agents\user-upgrade-sentinel.txt"
  Set-Content -LiteralPath $UserFile -Value "preserve across upgrade and uninstall"

  Install-Battle2 "upgrade silent install"
  Invoke-InstalledSmoke
  if ((Get-FileHash -LiteralPath $RunnerManifest -Algorithm SHA256).Hash -ne $ModifiedHash) {
    throw "Upgrade or second startup overwrote the user-modified runner manifest."
  }
  if (-not (Test-Path -LiteralPath $UserFile)) { throw "Upgrade removed the user agent sentinel." }

  $Uninstaller = Join-Path $AppDir "unins000.exe"
  Invoke-ProcessChecked $Uninstaller @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") "silent uninstall" -CaptureOutput | Out-Null
  for ($Attempt = 0; $Attempt -lt 20 -and (Test-Path -LiteralPath $AppDir); $Attempt++) {
    Start-Sleep -Milliseconds 500
  }
  if (Test-Path -LiteralPath $AppDir) { throw "Program directory remains after uninstall: $AppDir" }
  if (-not (Test-Path -LiteralPath $UserFile)) { throw "Uninstall removed retained user data." }
  $Group = Join-Path $Env:ProgramData "Microsoft\Windows\Start Menu\Programs\Bytefray"
  foreach ($ShortcutName in @("Bytefray Agent Designer.lnk", "Bytefray Replay Viewer.lnk")) {
    $Shortcut = Join-Path $Group $ShortcutName
    if (Test-Path -LiteralPath $Shortcut) {
      throw "Installed Start Menu shortcut remains after uninstall: $Shortcut"
    }
  }
  $MachineRootAfterUninstall = [Environment]::GetEnvironmentVariable("BATTLE2_ROOT", "Machine")
  if ($null -ne $MachineRootAfterUninstall) {
    throw "Machine BATTLE2_ROOT remains after uninstall: $MachineRootAfterUninstall"
  }
  $MachineBytefrayRootAfterUninstall = [Environment]::GetEnvironmentVariable("BYTEFRAY_ROOT", "Machine")
  if ($null -ne $MachineBytefrayRootAfterUninstall) {
    throw "Machine BYTEFRAY_ROOT remains after uninstall: $MachineBytefrayRootAfterUninstall"
  }
  $Remaining = @(Get-Process | Where-Object { $_.Path -and $_.Path.StartsWith($AppDir, [StringComparison]::OrdinalIgnoreCase) })
  if ($Remaining.Count -ne 0) { throw "Bytefray processes remain after uninstall: $($Remaining.Id -join ', ')" }
  Write-SmokeLog "Upgrade preserved modified agents; uninstall removed programs and retained data."
  Write-SmokeLog "=== SUCCESS: full installer lifecycle passed ==="
} finally {
  [Environment]::SetEnvironmentVariable("BATTLE2_ROOT", $PreviousMachineRoot, "Machine")
  [Environment]::SetEnvironmentVariable("BYTEFRAY_ROOT", $PreviousMachineBytefrayRoot, "Machine")
  Write-SmokeLog "Restored previous machine BATTLE2_ROOT and BYTEFRAY_ROOT values."
}
