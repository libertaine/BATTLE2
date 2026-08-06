# Installation Guide

## Windows installer candidate

The v0.2 installer candidate is `BATTLE2-Setup-0.2.0.exe`. It installs five
onedir applications beneath `C:\Program Files\BATTLE2\bin`: `battle2`,
`battle-cli`, `match-runner`, `battle-agent-designer`, and
`battle-replay-viewer`. The CI artifact containing the corresponding portable
application trees is named `windows-exes`.

The installer sets `BATTLE2_ROOT` to `%ProgramData%\BATTLE2` and does not modify
`PATH`. Uninstall removes programs, shortcuts, and the installed environment
setting, but preserves user-created agents, replays, summaries, logs, and other
data beneath `%ProgramData%\BATTLE2`.

The installed executables remain available by their full paths, for example:

```powershell
& 'C:\Program Files\BATTLE2\bin\battle2\battle2.exe' --help
& 'C:\Program Files\BATTLE2\bin\battle-agent-designer\battle-agent-designer.exe'
& 'C:\Program Files\BATTLE2\bin\battle-replay-viewer\battle-replay-viewer.exe'
```

## Python wheel on Windows

A normal, non-editable wheel installation uses `%LOCALAPPDATA%\BATTLE2` for
writable data. If `LOCALAPPDATA` is unavailable, it falls back to
`%USERPROFILE%\AppData\Local\BATTLE2` (or the equivalent current-user home).
`BATTLE2_ROOT` overrides this location; legacy `BATTLE_ROOT` is used only when
`BATTLE2_ROOT` is unset or blank.

## Windows development

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[replay,designer,dev]"
battle2 design
```
