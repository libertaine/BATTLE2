# Installation Guide

## Windows installer

Download `Bytefray-Setup-1.1.0.exe` from the
[v1.1.0 release](https://github.com/libertaine/Bytefray/releases/tag/v1.1.0)
(see [README.md](README.md#-downloads) for the current release; the exact
filenames below track that latest tag as later versions ship). It installs
four
onedir applications beneath `C:\Program Files\Bytefray\bin`: `battle2`,
`battle-cli`, `battle-agent-designer`, and `battle-replay-viewer`. The v0.1
`match-runner` command was removed in v0.3; use `battle-replay-viewer` (or
`bytefray replay --renderer pygame`) instead. The release archive containing
the corresponding portable
application trees is `bytefray-1.1.0-windows.zip`. Extract the entire ZIP
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

## Portable Windows applications

Download `bytefray-1.1.0-windows.zip` from the release (see
[README.md](README.md#-downloads) for the current release) and extract the
entire archive; do not copy only the top-level executables, since their
adjacent DLLs, Qt plugins, resources, and pMARS files are required.

Each of the four extracted applications (`battle2`, `battle-cli`,
`battle-agent-designer`, `battle-replay-viewer`) is self-contained and, with
no `BYTEFRAY_ROOT` set, defaults its writable data (agents, replays,
history) to its own directory beside its `.exe` — the same behavior the
Windows installer relies on before it sets a shared `BYTEFRAY_ROOT`. This
means the four portable applications do **not** share one agents/replays
catalog with each other by default: an agent created with the portable
`battle-agent-designer.exe` is not visible to a separately-launched portable
`battle-replay-viewer.exe` or `battle-cli.exe` from the same extracted ZIP.
Set `BYTEFRAY_ROOT` once, to any writable directory, before launching any of
the four executables (for example in a small wrapper script placed next to
the extracted folder) so they all read and write the same data:

```powershell
$env:BYTEFRAY_ROOT = "C:\path\to\shared\bytefray-data"
& ".\battle-agent-designer\battle-agent-designer.exe"
```

Using only the unified `battle2.exe` (`battle2.exe run`, `battle2.exe
design`, `battle2.exe replay`, `battle2.exe agents ...`) has the same effect
without setting anything, since every one of its subcommands runs in that
same process and therefore already shares its own adjacent data directory.

## Python wheel on Windows

Python users can install the release wheel into an isolated environment:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install .\bytefray-1.1.0-py3-none-any.whl
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
