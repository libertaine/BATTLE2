# Bytefray Linux wheel installation

Bytefray supports Python 3.10 through 3.14. The Linux release artifact is a
Python wheel; no PyInstaller, AppImage, Debian, or Flatpak artifact is currently
provided. (See [README.md](../README.md#-downloads) for the current release;
the exact wheel filename below tracks that latest tag as later versions ship.)

Create an isolated environment and install the wheel:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install ./bytefray-4.0.0rc1-py3-none-any.whl
```

The core install supports native matches and headless replay. Optional desktop
dependencies are separate:

```bash
python -m pip install 'bytefray[replay]'    # pygame-ce replay viewer
python -m pip install 'bytefray[designer]'  # PySide6 Agent Designer
```

PySide6 and pygame-ce are not required for the core CLI. Replay rendering
uses [pygame-ce](https://pyga.me/), a maintained, actively-released fork of
Pygame, through the standard `pygame` Python namespace -- application and
agent code continues to `import pygame` unchanged. pygame-ce publishes
binary wheels for current CPython releases (including 3.14) promptly, so a
supported Python normally installs `replay`/`gui` without needing SDL2
development headers or a local compiler; classic Pygame's Linux wheel
coverage can lag a new CPython release, which forces pip to fall back to a
source build that fails without `sdl2-config` and the SDL2 dev packages
installed. CI validates pygame-ce and Designer startup under X11/Xvfb across
the package's minimum and current-generation Python versions. That is not
full visible/input GUI validation, and native Wayland remains unvalidated,
so the Linux wheel should still be treated as headless-first.

## Writable data and starter agents

`BYTEFRAY_ROOT` selects the writable data root. When it is unset, an installed
Linux wheel uses `$XDG_DATA_HOME/bytefray`, or `~/.local/share/bytefray` when
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
bytefray replay --replay ~/.local/share/bytefray/runs/_loose/replay.jsonl \
  --renderer headless
```

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

## Looking ahead: RC2 self-contained Linux distribution

RC2 (not yet published; current downloads remain the RC1 wheel above) adds a
second, self-contained distribution path alongside the Python package install
described above. Once RC2 ships, Linux users will be able to choose either:

- **Self-contained binary distribution.** Download and extract a Linux
  tar.gz containing the frozen `bytefray`, `bytefray-cli`,
  `bytefray-agent-designer`, and `bytefray-replay-viewer` applications, then
  run them directly. No local Python interpreter, `pip`, or virtual
  environment is required.
- **Python package installation.** Advanced/development users can continue
  installing the wheel or an editable source checkout on a supported Python
  version, exactly as documented above.

**Official release-build baseline.** The self-contained Linux artifact is
built on **Ubuntu 24.04 LTS** (not a newer or arbitrary Ubuntu release);
newer Ubuntu releases are qualified against the exact bytes that baseline
produces, rather than being rebuilt on those newer releases. As actually
measured on the Ubuntu 24.04 RC2-development baseline build, the frozen
bundle's maximum required glibc symbol version is `GLIBC_2.38`, which
post-dates Ubuntu 22.04 LTS (glibc 2.35) and Debian 12 "Bookworm" (glibc
2.36). Neither of those, nor any other distribution, is claimed as supported
unless it is actually tested and found compatible with this measured glibc
requirement. See
[`docs/research/v4/V4_RC2_LINUX_RELEASE_BASELINE_QUALIFICATION.md`](research/v4/V4_RC2_LINUX_RELEASE_BASELINE_QUALIFICATION.md)
for the full qualification record.
