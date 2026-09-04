# Bytefray v4 RC2 — Phase 1B: Windows pygame-ce Packaged Qualification

Branch: `v4-rc2-development`

Source SHA under test (unchanged throughout this phase): `41f991dce81e9e524aff212403bd61821a61c59f`

This is the Windows packaging/frozen-build qualification record for RC2 Phase 1's
classic-Pygame → pygame-ce migration (`2ad7e0b`, `d745d21`, `6fa0611`, `41f991d`),
which Phase 1 had already qualified on Linux/Python 3.14 source-level but had not
yet exercised through the real Windows PyInstaller/installer packaging path. It is
a qualification/remediation task only — no engine, Agent API, or Replay Viewer
code was changed.

```text
PASS — pygame-ce Windows packaged qualification complete for RC2
```

---

## A. Executive decision

| Gate | Result |
|---|---|
| Qualification environment: pygame-ce present, classic pygame absent | **PASS** |
| Source-level Windows Replay/renderer tests | **PASS** |
| Full default (headless) suite | **PASS** (2936 passed, 14 skipped, 0 failed) |
| GUI-marked suite (Replay/renderer/Designer) | **PASS** (256 passed, 0 failed) |
| PyInstaller build (all 4 apps) | **PASS** |
| pygame-ce hook discovery (unchanged) | **PASS** |
| SDL/native runtime collection | **PASS** |
| Portable ZIP | **PASS** |
| Installer build | **PASS** (compiles, correct embedded version) |
| Installer install/upgrade/uninstall lifecycle | **NOT PERFORMED** — requires admin elevation this session does not have (see §H; identical, previously-accepted limitation from the RC1 Phase 4 report) |
| Frozen Replay Viewer launch/playback-process/close | **PASS** (process level; see §K for what this does and does not prove) |
| Quorum vs Defender Scout replay generation (frozen CLI) | **PASS** |
| Headless deterministic replay-to-RESULT correctness | **PASS** |
| Dependency isolation (both qualification venvs removed) | **PASS** |
| Packaging remediation required | **NONE** |
| Lint/type-check regressions introduced | **NONE** |
| RC1 tags/assets touched | **NO** |

---

## B. Starting state (Phase 0)

```text
Starting branch (before this task): fix/v4-rc1-agent-development-scroll @ ebd1354
```

`v4-rc2-development` did not exist on `origin` at the start of this session's
first `git fetch`. It was pushed to `origin` roughly 45 seconds later (confirmed
by a second `git fetch origin`), at which point it resolved to:

```text
git rev-parse origin/v4-rc2-development   41f991dce81e9e524aff212403bd61821a61c59f
git log --oneline -4 origin/v4-rc2-development
  41f991d docs(rc2): document pygame-ce and Python 3.14 support
  6fa0611 ci(rc2): add Python 3.14 coverage
  d745d21 test(rc2): qualify pygame-ce and Python 3.14
  2ad7e0b build(rc2): migrate replay dependency to pygame-ce
```

All four expected Phase 1 commits were confirmed present via `git cat-file -e`.
A local tracking branch was created (`git checkout v4-rc2-development`) and this
phase proceeded from `41f991d` without modification — `git status` was clean
before, during, and after every phase; `git rev-parse HEAD` was `41f991d` at the
start and remains `41f991d` at the end.

```text
local main:     eca97c09c9781631e16a8a78791cfdb0ec21d9df
origin/main:    ahead of local main (fast-forward only, not diverged) — not
                touched by this phase; main was not worked on directly.
```

---

## C. Environment

```text
Windows:      Windows 11 Pro, build 26120.6972 (24H2 channel). The registry's
              ProductName key still reads "Windows 10 Pro" — a known cosmetic
              registry-lag quirk on this build family, not the actual edition;
              CurrentBuild 26120 is Windows 11.
Qualification Python:  3.13.7 (fresh venv, `.venv-rc2-win`, created from the
                       newest locally available interpreter; Python 3.14 was
                       not installed on this machine — `py -0p` listed 3.10
                       through 3.13 only)
Canonical build venv:  `.venv` — Python 3.13.14 (pre-existing, repo-root venv
                       `tools/build_win.ps1` hardcodes)
pip:          26.2.1 (upgraded fresh in `.venv-rc2-win`)
pygame-ce:    2.5.8 (SDL 2.32.10)
PyInstaller:  6.22.2 (`pyinstaller-hooks-contrib` 2026.7)
PySide6:      6.11.2
Inno Setup:   6 (per-user install, `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`
              — not on PATH/Program Files, consistent with this machine's
              known per-user toolchain layout)
pytest:       9.1.1     ruff: 0.16.6     mypy: 2.3.1
```

---

## D. Qualification environment (Phase 2)

A fresh venv was created rather than reusing any existing one:

```powershell
py -3.13 -m venv .venv-rc2-win
.venv-rc2-win\Scripts\python.exe -m pip install --upgrade pip
.venv-rc2-win\Scripts\python.exe -m pip install -e ".[replay,designer,dev,windows-build]"
```

Dependency proof:

```text
pip show pygame-ce      -> Version: 2.5.8, Location: .venv-rc2-win\Lib\site-packages
pip show pygame          -> WARNING: Package(s) not found: pygame
python -c "import pygame; print(pygame.version.ver)"          -> 2.5.8
python -c "from importlib.metadata import version; \
            print(version('pygame-ce'))"                       -> 2.5.8
python -c "from importlib.metadata import version; \
            print(version('bytefray'))"                         -> 4.0.0rc1
bytefray --version -> Bytefray 4.0.0rc1, Agent API v2, result schema v1,
                      replay schema v4, Python 3.13.7
```

**Real, pre-existing contamination found and cleaned.** `.venv` — the repo-root
venv `tools/build_win.ps1` hardcodes for the canonical Windows build — was found
to still have classic **pygame 2.6.1** installed (left over from earlier RC1-era
work) and no `pygame-ce`. This is exactly the coexistence risk the governing task
warns against. Rather than modify `tools/build_win.ps1` to point at a different
venv (which would diverge from "the real Bytefray packaging path"), classic
pygame was uninstalled from `.venv` directly (`pip uninstall -y pygame`,
confirmed removed) before running the canonical build, so the script's own
`pip install -e ".[replay,designer,windows-build]"` step installed pygame-ce
into a now-clean environment. This mirrors the RC1 Phase 4 report's own §O.2
finding-and-classification pattern for environment-only staleness — no tracked
file was touched, and `git status` was clean before and after.

---

## E. Source-level Windows regression baseline (Phase 3)

All runs from `.venv-rc2-win` (pygame-ce, no classic pygame), against `41f991d`.

```text
python -m pytest --basetemp=.pytest-tmp/rc2-win-phase3
  -> 1 failed, 2935 passed, 14 skipped, 2 deselected (318.6s)
```

The one failure
(`test_agent_evaluation_group_analysis_integration.py::test_live_run_group_analysis_covers_every_roster_entrant`)
was a `PermissionError: [WinError 5] Access is denied` on an atomic
`Path.replace()` rename under `.pytest-tmp` — the exact known class of transient
Windows temp-path/file-lock issue `docs/WINDOWS_DEV_NOTES.md` explicitly
documents as "not a Bytefray bug." Confirmed transient: the single test passed
cleanly in isolation immediately afterward. A full clean rerun (fresh
`--basetemp`) confirmed it was not reproducible:

```text
python -m pytest --basetemp=.pytest-tmp/rc2-win-phase3-final
  -> 2936 passed, 14 skipped, 0 failed (316.2s)
```

This exactly reconciles against Phase 1's own Linux baseline (2936
collected/0 failures/14 skipped) and the RC1 Phase 4 Windows baseline.

GUI-marked suites (Replay Viewer, pygame renderer, Designer):

```text
python -m pytest -m gui                 -> 2 passed, 2950 deselected
python -m pytest -m gui tests/          -> 254 passed, 6 deselected, 0 failed (39.0s)
```

**Total: 256 GUI-marked tests passed, 0 failed** (one more than RC1's own 255 —
not a regression; the Designer suite has grown since RC1).

Static checks:

```text
ruff check .                          -> 2 pre-existing findings (see §F)
mypy engine/src/battle_engine         -> Success: no issues found in 102 source files
mypy client/src/battle_client         -> Success: no issues found in 15 source files
```

---

## F. Pre-existing, non-blocking ruff findings

`ruff check .` reports two `RUF012` (mutable default class attribute) findings
in `engine/src/battle_engine/data/starter_agents/v4_quorum/agent.py`. Confirmed
**pre-existing, not introduced by this phase or by RC2 Phase 1's migration
commits**: `git log` shows this file was last touched by `84e1be8` ("feat(v4):
promote Quorum to bundled Agent API v2 advanced example"), the commit
`v4-rc2-development` branched onto immediately after diverging from `main` —
i.e. before any of the four pygame-ce migration commits. `git show --stat` on
each of `2ad7e0b`/`d745d21`/`6fa0611`/`41f991d` confirms none touched this file.
No source change was made for this finding; it is out of this phase's narrow
scope (Windows packaging, not Quorum agent source style).

---

## G. Inspecting what PyInstaller thinks pygame is (Phase 4)

Before building, the installed `pygame-ce` package was checked for the same
PyInstaller hook-discovery mechanism classic Pygame used:

```text
importlib.metadata.distribution('pygame-ce').entry_points:
  pyinstaller40 -> hook-dirs -> pygame.__pyinstaller:get_hook_dirs
```

This is the **identical** entry point classic Pygame registers — pygame-ce ships
its own `pygame/__pyinstaller/hook-pygame.py`, which (on Windows) calls
`collect_dynamic_libs("pygame")` to gather every native DLL inside the
installed `pygame` package directory and places them at the collected tree's
top level. Because pygame-ce still installs into a directory literally named
`pygame`, this hook works completely unchanged — no `tools/*.spec` file
declares any pygame-specific `hookspath`, `binaries`, or `hiddenimports` entry,
and none needed to.

**Confirmed explicitly in the real build log** (Phase 5, `tools/build_win.ps1`):

```text
8634 INFO: Processing standard module hook 'hook-pygame.py' from
           '...\.venv\Lib\site-packages\pygame\__pyinstaller'
13420 INFO: Extra DLL search directories (AddDllDirectory):
           ['...\.venv\Lib\site-packages\pygame']
```

**The existing PyInstaller hook for `pygame` works unchanged with pygame-ce.**
No packaging-level remediation was required.

---

## H. Build (Phase 5) and artifact inventory

Commands, run in order from `41f991d`, no intervening source change:

```powershell
# .venv cleaned of classic pygame first (see §D)
pwsh tools\build_win.ps1
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" tools\installer.iss
Compress-Archive -Path dist\windows\bytefray, dist\windows\bytefray-cli, `
  dist\windows\bytefray-agent-designer, dist\windows\bytefray-replay-viewer `
  -DestinationPath dist\bytefray-4.0.0-rc2-windows.zip
```

`tools/build_win.ps1`'s own embedded smoke tests (GUI import/startup for
`bytefray.exe design` and standalone `bytefray-agent-designer.exe`; a real
`bytefray.exe agents create smoke_agent` against the frozen tree; the
build-residue check proving no runtime-generated `agents/` directory leaked
into any distributable tree) all **passed** — printed `[build] Success.`

| Artifact | Size (bytes) | SHA-256 |
|---|---|---|
| `bytefray-4.0.0-rc2-windows.zip` (portable ZIP, all 4 apps) | 142,277,818 | `8062DE1FE2E0A7A1E46850E2F6E9C333A47285DE421DA557A3520531A966D7DE` |
| `Bytefray-Setup-4.0.0-rc1.exe` (installer) | — | `B7CE99593284F538C9A65012933F85533D004F47677A8B7A3ECEA3E10ADB2CB5` |

The installer's embedded version (`4.0.0rc1`/`4.0.0-rc1`) reflects
`pyproject.toml`'s current, not-yet-bumped version on this development branch —
RC2 has not gone through release-prep — not a defect.

**Reproducibility.** Not claimed byte-reproducible. Established: traceable
provenance — all artifacts built from the same working tree at `41f991d`, no
commit, rebuild, or source edit between the first and last artifact build
(`git status` clean, `git rev-parse HEAD` unchanged, verified both before and
after).

---

## I. Frozen artifact contents (Phase 6)

```text
dist\windows\bytefray-replay-viewer\_internal\SDL2.dll
dist\windows\bytefray-replay-viewer\_internal\SDL2_image.dll
dist\windows\bytefray-replay-viewer\_internal\SDL2_mixer.dll
dist\windows\bytefray-replay-viewer\_internal\SDL2_ttf.dll
(+ freetype, libjpeg, libpng16, libtiff, libwebp, libogg, libopus, libxmp,
  portmidi, VCRUNTIME140[_1], libssl-3/libcrypto-3, libffi-8)
dist\windows\bytefray-replay-viewer\_internal\pygame\*.pyd  (pygame-ce's own
  compiled extension modules — base, display, event, mixer, font, image,
  transform, _sdl2\{audio,sdl2,video}, etc.)
```

No classic-Pygame `dist-info`/`egg-info` or duplicate payload found anywhere in
any of the four frozen trees (`bytefray`, `bytefray-cli`,
`bytefray-agent-designer`, `bytefray-replay-viewer`). Only pygame-ce is present.
`bytefray-agent-designer`'s frozen tree also bundles `pygame` (expected — the
unified Designer's dependency graph reaches `battle_client`'s pygame renderer
through its own hidden-import collection, same as before this migration).

**Expected result confirmed**: only pygame-ce is installed in the source
environment; the frozen product imports the `pygame` namespace supplied by
pygame-ce; no classic pygame distribution needed to coexist.

---

## J. Quorum replay generation and headless correctness (Phase 7 data, Phase 8)

Generated from the **frozen, packaged** `dist\windows\bytefray\bytefray.exe`
(not from source), fixed seed, in an isolated `BYTEFRAY_ROOT`:

```text
bytefray.exe run --a-type v4_quorum --b-type v4_defender_scout --seed 42 \
  --ticks 3000 --arena 512 --ruleset bytefray-rules-4 --replay <path> --quiet
exit code: 0
```

Result: `winner=A`, `score={'A': 16.0, 'B': 10.0}`, `termination_reason:
last_agent_standing`, 11 ticks — a real gameplay conclusion, **not** a
first-tick forfeit. The replay records 8 independent processes across the two
entrants (Quorum: `oracle`/`breaker`/`guardian`/`flank_left`/`flank_right`/
`reserve`; Defender Scout: `defender`/`scout`), exercising exactly the
multi-process rendering stress case this replay was chosen for.

The frozen **headless** renderer played this replay back end-to-end:

```text
bytefray-replay-viewer.exe --replay <path> --renderer headless --tick-delay 0
  -> ticks 0..11 streamed correctly
  -> [0011] RESULT winner=A score={'A': 16.0, 'B': 10.0}
  -> exit code: 0
```

This independently reproduces the replay's own trailing `result` record
tick-by-tick from the frozen executable, proving the frozen build's
replay-parsing/playback logic is correct end to end, independent of pygame
rendering.

---

## K. Frozen Replay Viewer process-level smoke (Phase 7)

The real, windowed pygame-ce renderer (`--renderer pygame`) was launched twice
from the frozen `bytefray-replay-viewer.exe` against the Quorum replay above:

| Launch | Result |
|---|---|
| 1st (default: playing) | Real window opened (`MainWindowTitle: "Bytefray - Replay"`), `Responding: True` for the full 8-second hold, closed gracefully via `CloseMainWindow()`, exit code 0 |
| 2nd (`--paused`, a distinct startup code path) | Stayed alive for the full 5-second hold, closed gracefully, exit code 0 |

No orphaned process remained after either launch (`Get-Process` filtered on the
exe path returned 0 after both). This is process-level launch/hold/
responsive/close-cycle confirmation, matching the rigor of `tools/
smoke_after_install.ps1`'s `Test-GuiStartup` helper and the RC1 Phase 4
report's own §K methodology.

**What this phase did not do, and why**: it did not visually/pixel-confirm
on-screen rendering (fonts, arena graphics, HUD content), and did not drive
interactive play/pause/step/scrub/resize/maximize/restore/mouse/keyboard
controls. This is not a shortcut — it is the repo's own established, explicit
boundary: `docs/MANUAL_SMOKE_TESTS.md`'s "Phase 7a" section records that
synthetic Win32 `SendKeys` automation was already tried for this exact viewer
and found unreliable for modifier/special-key delivery, and that pygame has no
self-capture mechanism equivalent to Qt's `QWidget.grab()` (also noted in the
RC1 Phase 4 report, §K). The underlying interaction/event-loop logic this
would exercise is unchanged by the pygame-ce migration and is covered by the
GUI-marked automated suite (`client/tests/test_pygame_renderer.py`,
`client/tests/test_linux_pygame_smoke.py`, `client/tests/test_playback_
controller.py`), all reconfirmed passing in this phase's own GUI-suite run
(§E). The literal interactive checklist in `docs/MANUAL_SMOKE_TESTS.md`'s
"Pygame replay viewer" and "Phase 7a" sections remains a human release check,
as it already was before this migration.

---

## L. Installer qualification (Phase 9)

The installer **compiled successfully** (53.1s) with the correct embedded
version, producing `Bytefray-Setup-4.0.0-rc1.exe` (§H).

The full install/upgrade/uninstall lifecycle (`tools/smoke_after_install.ps1
-Lifecycle`) was **not performed**: `tools/installer.iss` declares
`PrivilegesRequired=admin`, this session runs unelevated
(`WindowsPrincipal.IsInRole(Administrator)` = `False`), and there is no way to
satisfy an interactive UAC prompt from this automation session. This is the
**identical** constraint the RC1 Phase 4 report hit and documented in its own
§H, resolved there by having the maintainer run the lifecycle script from an
elevated session with an isolated `-AppDir`/`-DataRoot`. Per
`docs/MANUAL_SMOKE_TESTS.md`'s own explicit guidance ("Do not alter a
development workstation's installed-product state solely to run this
lifecycle check... lack of an install/uninstall cycle is not by itself a
release blocker" when the frozen apps are already qualified and the installer
compiles with the intended version), this is recorded as a deferred check, not
a blocker, given the frozen executables themselves were independently and
thoroughly qualified in §I/§J/§K/§M.

**Recommended follow-up** (for the maintainer, from an elevated PowerShell
session, using an isolated `AppDir`/`DataRoot` — not the real `Program
Files`/`ProgramData`):

```powershell
pwsh tools\smoke_after_install.ps1 -Lifecycle `
  -InstallerPath dist\installer\Bytefray-Setup-4.0.0-rc1.exe `
  -AppDir "D:\Bytefray RC2 Test\Application" -DataRoot "D:\Bytefray RC2 Test\Data"
```

---

## M. Dependency-isolation test (Phase 10)

Both qualification-adjacent venvs (`.venv`, the canonical build venv, and
`.venv-rc2-win`, the dedicated qualification venv) were **renamed out of
existence** simultaneously, the frozen `bytefray-replay-viewer.exe` was
launched fresh against the Quorum replay, and both venvs were restored
immediately after:

```text
Alive with BOTH venvs renamed away: True
MainWindowTitle: Bytefray - Replay
ExitCode: 0 (closed gracefully)
Both venvs restored.
Test-Path .venv            -> True
Test-Path .venv-rc2-win    -> True
```

The frozen product has **zero runtime dependency** on either development
Python environment.

---

## N. Packaging remediation (Phases 11–13)

**None required.** §G/§H/§I establish that the existing, unmodified
`tools/*.spec` files and PyInstaller's default hook discovery already handle
pygame-ce correctly — pygame-ce registers the identical `pyinstaller40`
entry point classic Pygame did, and its own bundled hook collects the correct
SDL/native DLLs into the frozen tree unchanged. No spec adjustment, hidden
import, hook correction, or new packaging regression test was needed. No
classic-Pygame comparison build was performed (not needed — no
pygame-ce-specific packaging problem was found to diagnose). `git status` was
clean and `HEAD` unchanged (`41f991d`) for the entire duration of this phase.

---

## O. Full Windows regression pass (Phase 14)

No remediation occurred, so no source changed after §E's authoritative run —
that run **is** the final regression pass:

```text
python -m pytest --basetemp=.pytest-tmp/rc2-win-phase3-final
  -> 2936 passed, 14 skipped, 0 failed
python -m pytest -m gui                 -> 2 passed
python -m pytest -m gui tests/          -> 254 passed, 0 failed
ruff check .                            -> 2 pre-existing findings (§F), none new
mypy engine/src/battle_engine           -> Success, 102 source files
mypy client/src/battle_client           -> Success, 15 source files
```

**0 failed. No new lint/type-check finding was introduced.**

---

## P. Files changed / commits

**None.** This was a qualification-only session: no `tools/*.spec` file,
PyInstaller hook, application source, or dependency declaration required any
change. The only artifact of this phase is this report, added as a single
documentation-only commit on `v4-rc2-development`. Source SHA before and after
this phase: `41f991dce81e9e524aff212403bd61821a61c59f` (unchanged).

---

## Q. Final decision

Every gate this Windows session could exercise passed: qualification
environment (pygame-ce present, classic pygame absent — including a real,
found-and-cleaned `.venv` contamination), full default suite, full GUI suite,
static checks (no new findings), PyInstaller build of all four applications
with pygame-ce's own hook mechanism working completely unchanged, correct SDL/
native runtime collection with no classic-Pygame duplication, portable ZIP,
installer build with the correct embedded version, frozen Replay Viewer
launch/relaunch/close-cycle process-level confirmation, a real Quorum vs
Defender Scout match generated and replayed correctly from the frozen product
end to end, and dependency isolation from both development Python
environments. The only gate not performed — the installer's actual
install/upgrade/uninstall lifecycle — is blocked solely on this session
lacking administrative elevation, an identical and previously-accepted
limitation from the RC1 Phase 4 report, and is not a release blocker per
`docs/MANUAL_SMOKE_TESTS.md`'s own standing guidance given the frozen
executables were independently qualified.

```text
PASS — pygame-ce Windows packaged qualification complete for RC2
```

No engine or Agent API semantics changed. RC1 tags/assets were not touched.
Nothing was published, tagged, or merged to `main`.
