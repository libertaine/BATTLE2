# Installation Guide

## Windows installer

Download `Bytefray-Setup-0.5.0.exe` from the
[v0.5.0 release](https://github.com/libertaine/Bytefray/releases/tag/v0.5.0).
It installs four
onedir applications beneath `C:\Program Files\Bytefray\bin`: `battle2`,
`battle-cli`, `battle-agent-designer`, and `battle-replay-viewer`. The v0.1
`match-runner` command was removed in v0.3; use `battle-replay-viewer` (or
`bytefray replay --renderer pygame`) instead. The release archive containing
the corresponding portable
application trees is `Bytefray-0.5.0-windows-exes.zip`. Extract the entire ZIP
for portable use; do not copy only the top-level executables because their
adjacent DLLs, Qt plugins, resources, and pMARS files are required.

The installer sets `BYTEFRAY_ROOT` (the preferred variable) and the legacy
`BATTLE2_ROOT` to `%ProgramData%\BATTLE2` — kept under that name for upgrade
continuity with existing BATTLE2 installs — and does not modify `PATH`.
Uninstall removes programs, shortcuts, and the installed environment settings,
but preserves user-created agents, replays, summaries, logs, and other data
beneath `%ProgramData%\BATTLE2`.

The installed executables remain available by their full paths, for example:

```powershell
& 'C:\Program Files\Bytefray\bin\battle2\battle2.exe' --help
& 'C:\Program Files\Bytefray\bin\battle-agent-designer\battle-agent-designer.exe'
& 'C:\Program Files\Bytefray\bin\battle-replay-viewer\battle-replay-viewer.exe'
```

## Python wheel on Windows

Python users can install the release wheel into an isolated environment:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install .\bytefray-0.5.0-py3-none-any.whl
bytefray --help
```

A normal, non-editable wheel installation uses `%LOCALAPPDATA%\BATTLE2` for
writable data. If `LOCALAPPDATA` is unavailable, it falls back to
`%USERPROFILE%\AppData\Local\BATTLE2` (or the equivalent current-user home).
`BYTEFRAY_ROOT` overrides this location; the legacy `BATTLE2_ROOT` and
`BATTLE_ROOT` names are honored, in that order, only when `BYTEFRAY_ROOT` is
unset or blank.

## Windows development

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[replay,designer,dev]"
bytefray design
```
