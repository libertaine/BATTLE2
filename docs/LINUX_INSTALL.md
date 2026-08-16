# Bytefray Linux wheel installation

Bytefray supports Python 3.10 through 3.13. The Linux release artifact is a
Python wheel; no PyInstaller, AppImage, Debian, or Flatpak artifact is currently
provided. (See [README.md](../README.md#-downloads) for the current release;
the exact wheel filename below tracks that latest tag as later versions ship.)

Create an isolated environment and install the wheel:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install ./bytefray-1.2.0-py3-none-any.whl
```

The core install supports native matches and headless replay. Optional desktop
dependencies are separate:

```bash
python -m pip install 'bytefray[replay]'    # Pygame replay viewer
python -m pip install 'bytefray[designer]'  # PySide6 Agent Designer
```

PySide6 and Pygame are not required for the core CLI. CI validates Pygame and
Designer startup under X11/Xvfb. That is not full visible/input GUI validation,
and native Wayland remains unvalidated, so the Linux wheel should still be
treated as headless-first.

## Writable data and starter agents

`BYTEFRAY_ROOT` selects the writable data root. The legacy `BATTLE2_ROOT` and
`BATTLE_ROOT` variables are honored, in that order, only when `BYTEFRAY_ROOT`
is unset. With none of these variables set, an installed Linux wheel
uses `$XDG_DATA_HOME/battle2`, or `~/.local/share/battle2` when
`XDG_DATA_HOME` is unset. Recognized source and editable checkouts continue to
use the repository root.

Packaged starter manifests are read-only resources. `bytefray agents` initializes
missing Runner, Writer, Seeker, and Spiral manifests before listing the catalog,
without overwriting user files:

```bash
bytefray agents
```

With no `--replay` option, matches write
`<data-root>/runs/_loose/replay.jsonl` and its sibling `summary.json`. An
explicit relative `--replay` path remains relative to the current working
directory; an explicit absolute path is preserved. The canonical summary is
always beside the selected replay.

## Headless operation

```bash
bytefray --help
bytefray run --ticks 500 --quota 2 --a-type writer --b-type runner
bytefray replay --replay ~/.local/share/battle2/runs/_loose/replay.jsonl \
  --renderer headless
```

The `battle2` command remains a deprecated compatibility alias for `bytefray`,
dispatching to the identical implementation.

The wheel does not bundle a Linux pMARS executable or select the repository's
Windows PE executables on Linux. `PMARS_CMD` remains authoritative and an
executable `pmars` may be discovered through `PATH`. Upstream supports a
console-only build, but the audited Ubuntu 0.9.5 package is compiled with X11;
`-b` means brief output and does not disable its display. Bytefray now provides a
pinned, experimental build script for the authoritative pMARS 0.9.5 source in
`tools/build_pmars_linux.sh`; it produces a libc-only console executable without
patching or modifying the supplied source. Linux Redcode operation still requires
a user-provided executable and is not part of wheel validation.
Any future bundled pMARS build must comply with GPL-2.0-or-later distribution
requirements, including the license notice and corresponding source offer or
delivery; the current wheel deliberately contains neither pMARS nor its source.
The corresponding-source and separately licensed documentation layout for a
future binary release remains a release-policy task; see `tools/pmars/README.md`.

Select one console-only executable path without fixed arguments:

```bash
PMARS_CMD=/absolute/path/to/pmars bytefray run --mode redcode94 \
  --red-a path/to/a.red --red-b path/to/b.red
```
