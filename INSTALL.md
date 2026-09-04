# Installation Guide

## Windows installer

Download `Bytefray-Setup-4.0.0-rc1.exe` from the
[v4.0.0-rc1 release](https://github.com/libertaine/Bytefray/releases/tag/v4.0.0-rc1)
(see [README.md](README.md#-downloads) for the current release; the exact
filenames below track that latest tag as later versions ship). It installs
four onedir applications beneath `C:\Program Files\Bytefray\bin`: `bytefray`,
`bytefray-cli`, `bytefray-agent-designer`, and `bytefray-replay-viewer`. The
v0.1 `match-runner` command was removed in v0.3; use
`bytefray-replay-viewer` (or
`bytefray replay --renderer pygame`) instead. The release archive containing
the corresponding portable
application trees is `bytefray-4.0.0-rc1-windows.zip`. Extract the entire ZIP
for portable use; do not copy only the top-level executables because their
adjacent DLLs, Qt plugins, resources, and pMARS files are required.

The installer sets `BYTEFRAY_ROOT` to `%ProgramData%\Bytefray` and does not
modify `PATH`.
Uninstall removes programs, shortcuts, and the installed environment settings,
but preserves user-created agents, replays, summaries, logs, and other data
beneath `%ProgramData%\Bytefray`.

**The installer is not code-signed.** Bytefray is an independently published
hobby project with no code-signing certificate and no accumulated Microsoft
SmartScreen reputation, so Windows will very likely show a "Windows
protected your PC" SmartScreen warning (and some antivirus products may
flag or delay the download) the first time you run it. This reflects the
installer's lack of a paid signing certificate, not a known defect. If you
trust the source, choose **More info -> Run anyway** to proceed. There is
no plan to purchase a signing certificate at this time; this note will be
updated if that changes.

The installed executables remain available by their full paths, for example:

```powershell
& 'C:\Program Files\Bytefray\bin\bytefray\bytefray.exe' --help
& 'C:\Program Files\Bytefray\bin\bytefray-agent-designer\bytefray-agent-designer.exe'
& 'C:\Program Files\Bytefray\bin\bytefray-replay-viewer\bytefray-replay-viewer.exe'
```

## Portable Windows applications

Download `bytefray-4.0.0-rc1-windows.zip` from the release (see
[README.md](README.md#-downloads) for the current release) and extract the
entire archive; do not copy only the top-level executables, since their
adjacent DLLs, Qt plugins, resources, and pMARS files are required.

Each of the four extracted applications (`bytefray`, `bytefray-cli`,
`bytefray-agent-designer`, `bytefray-replay-viewer`) is self-contained and, with
no `BYTEFRAY_ROOT` set, defaults its writable data (agents, replays,
history) to its own directory beside its `.exe` — the same behavior the
Windows installer relies on before it sets a shared `BYTEFRAY_ROOT`. This
means the four portable applications do **not** share one agents/replays
catalog with each other by default: an agent created with the portable
`bytefray-agent-designer.exe` is not visible to a separately-launched portable
`bytefray-replay-viewer.exe` or `bytefray-cli.exe` from the same extracted ZIP.
Set `BYTEFRAY_ROOT` once, to any writable directory, before launching any of
the four executables (for example in a small wrapper script placed next to
the extracted folder) so they all read and write the same data:

```powershell
$env:BYTEFRAY_ROOT = "C:\path\to\shared\bytefray-data"
& ".\bytefray-agent-designer\bytefray-agent-designer.exe"
```

Using only the unified `bytefray.exe` (`bytefray.exe run`, `bytefray.exe
design`, `bytefray.exe replay`, `bytefray.exe agents ...`) has the same effect
without setting anything, since every one of its subcommands runs in that
same process and therefore already shares its own adjacent data directory.

## Python wheel on Windows

Python users can install the release wheel into an isolated environment:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install .\bytefray-4.0.0rc1-py3-none-any.whl
bytefray --help
```

A normal, non-editable wheel installation uses `%LOCALAPPDATA%\Bytefray` for
writable data. If `LOCALAPPDATA` is unavailable, it falls back to
`%USERPROFILE%\AppData\Local\Bytefray` (or the equivalent current-user home).
`BYTEFRAY_ROOT` overrides this location.

## Windows development

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[replay,designer,dev]"
bytefray design
```

## macOS

macOS is **not a currently supported or tested distribution target.** No
macOS build, packaging, or CI job exists for Bytefray. The pure Python
wheel may work there in principle, since Pygame and PySide6 both publish
macOS wheels upstream, but this has never been built or validated and
carries no support guarantee. If you try it, please report your results as
a GitHub issue — see [SECURITY.md](SECURITY.md) for how to report anything
security-sensitive privately instead.
