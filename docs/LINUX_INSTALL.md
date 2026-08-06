# Linux wheel installation

BATTLE2 v0.2 supports Python 3.10 through 3.13. The first Linux artifact is a
Python wheel; no PyInstaller, AppImage, Debian, or Flatpak artifact is currently
provided.

Create an isolated environment and install the wheel:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install ./battle2-0.2.0-py3-none-any.whl
```

The core install supports native matches and headless replay. Optional desktop
dependencies are separate:

```bash
python -m pip install 'battle2[replay]'    # Pygame replay viewer
python -m pip install 'battle2[designer]'  # PySide6 Agent Designer
```

PySide6 and Pygame are not required for the core CLI. Linux GUI operation has
not yet been validated across X11 and Wayland, so the v0.2 Linux wheel should be
treated as headless-first.

## Writable data and starter agents

`BATTLE2_ROOT` selects the writable data root. If it is unset, legacy
`BATTLE_ROOT` is honored. With neither variable set, an installed Linux wheel
uses `$XDG_DATA_HOME/battle2`, or `~/.local/share/battle2` when
`XDG_DATA_HOME` is unset. Recognized source and editable checkouts continue to
use the repository root.

Packaged starter manifests are read-only resources. `battle2 agents` initializes
missing Runner, Writer, Seeker, and Spiral manifests before listing the catalog,
without overwriting user files:

```bash
battle2 agents
```

With no `--replay` option, matches write
`<data-root>/runs/_loose/replay.jsonl` and its sibling `summary.json`. An
explicit relative `--replay` path remains relative to the current working
directory; an explicit absolute path is preserved. The canonical summary is
always beside the selected replay.

## Headless operation

```bash
battle2 --help
battle2 run --ticks 500 --quota 2 --a-type writer --b-type runner
battle2 replay --replay ~/.local/share/battle2/runs/_loose/replay.jsonl \
  --renderer headless
```

The wheel does not bundle a Linux pMARS executable or select the repository's
Windows PE executables on Linux. `PMARS_CMD` remains authoritative and an
executable `pmars` may be discovered through `PATH`. Upstream supports a
console-only build, but the audited Ubuntu 0.9.5 package is compiled with X11;
`-b` means brief output and does not disable its display. Until a reproducible,
licensed console build is supplied, Linux Redcode operation is supported only
with a user-provided console-only executable and is not part of wheel validation.
Any future bundled pMARS build must comply with GPL-2-or-later distribution
requirements, including the license notice and corresponding source offer or
delivery; the current wheel deliberately contains neither pMARS nor its source.
