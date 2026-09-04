# Bytefray v4 RC2 — Phase 1: pygame-ce Migration + Python 3.14 Qualification

Branch tested: `v4-rc2-development` (created from synchronized `main` at
`84e1be8044a1bd948ce51f6f9553865693a83253`, confirmed identical to
`origin/main` via `git fetch origin` before any work began).

This is the compatibility/qualification record for RC2 Phase 1: replacing
Bytefray's classic-Pygame `replay`/`gui` dependency with
[pygame-ce](https://pyga.me/) and qualifying CPython 3.14 as an officially
tested interpreter. It does not redesign Bytefray, add gameplay features, or
change compatibility contracts.

---

## A. Motivation (RC1 finding)

RC1 manual Linux testing on Ubuntu 26.04 (default `python3` = 3.14) found
that classic Pygame had no compatible Linux wheel for that interpreter at
the time, so `pip` fell back to a source build, which failed because SDL
development tooling (`sdl2-config`) was not installed. The same source
worked correctly under the previously qualified Python 3.11 environment,
proving this was a dependency/platform-support gap, not an engine or Replay
defect.

---

## B. Environment

```text
OS:        Ubuntu 26.04.1 LTS (Resolute Raccoon)
Kernel:    Linux 7.0.0-30-generic, x86_64
Session:   XDG_SESSION_TYPE=wayland, XDG_CURRENT_DESKTOP=ubuntu:GNOME
           DISPLAY=:0 (XWayland), WAYLAND_DISPLAY=wayland-0 -- a real
           native-Wayland desktop session, the same class of environment
           that exposed the RC1 finding.
System Python 3:  /usr/bin/python3.14 -> Python 3.14.4 (Ubuntu package)
Project .venv:    Python 3.11.9, classic pygame 2.6.1 (SDL 2.28.4) --
                   the previously qualified baseline, left untouched.
pip:       26.2.1 (upgraded fresh in each qualification venv)
pytest:    9.1.1     ruff: 0.16.6     mypy: 2.3.1
PySide6:   6.11.2 (installed fresh in the qualification venvs)
pygame-ce: 2.5.8 (current on PyPI as of this qualification -- resolved by
           an unpinned `pip install pygame-ce`, independently confirming
           the task brief's stated upstream state)
```

`sdl2-config` and SDL2 development headers were confirmed **absent** from
this machine (`libsdl2-2.0-0`/`libsdl2-image-2.0-0`/etc. runtime libraries
are installed; the `-dev`/`sdl2-config` tooling is not), reproducing the
exact RC1 precondition.

---

## C. Phase 1 — Pygame API usage inventory

All active pygame API calls in Bytefray live in exactly one file:
`client/src/battle_client/renderers/pygame_renderer.py`. `PygameRenderer`
lazily imports pygame inside `run()` (`import pygame` -> `self.pg = pygame`,
wrapping `ImportError` as `RendererDependencyError`) specifically so that
merely importing the module -- or anything that imports it transitively --
never pulls the real `pygame` package into `sys.modules`. This is the same
property CI's "pure launcher import isolation" check
(`.github/workflows/ci.yml`) already enforces for `battle_engine.launchers`
and `app.services.engine_commands`.

Usage, by area (all through `self.pg`/the `pg` parameter passed into the
module-level `dispatch_key`):

* **Init/shutdown**: `pygame.init()`, `pygame.quit()`.
* **Display/window**: `display.set_mode(size, RESIZABLE)`,
  `display.set_caption()`, `display.set_icon()`, `display.Info()`,
  `display.flip()`.
* **Resize**: the `RESIZABLE` flag; event matching on
  `(pg.VIDEORESIZE, getattr(pg, "WINDOWRESIZED", 32769))`. Verified
  directly: `WINDOWRESIZED` exists on **both** classic pygame 2.6.1
  (`32778`) and pygame-ce 2.5.8 (`32777`) with different underlying SDL
  event ids -- but the code reads the live attribute each time rather than
  hardcoding either value, so it is correct under both distributions
  regardless of the numeric difference. The `getattr(..., 32769)` fallback
  is a defensive default for the (here, never-taken) case where the
  attribute is entirely absent, and `32769` not coincidentally equals
  `VIDEORESIZE`'s own value -- an intentionally harmless fallback since
  `VIDEORESIZE` is unconditionally the first element of the same tuple.
* **Events/input**: `event.get()`; `QUIT`, `KEYDOWN`, `MOUSEBUTTONDOWN`,
  `MOUSEBUTTONUP`, `VIDEORESIZE`; `mouse.get_pos()`; the standard `K_*`
  keycodes (several read via `getattr(pg, "K_...", <sentinel>)` guards for
  keys that are legitimately absent on some layouts in classic pygame too).
* **Surfaces/drawing**: `Surface((w, h))`, `Surface((w, h),
  flags=SRCALPHA)`, `.get_size()/.get_rect()/.fill()/.blit()`,
  `draw.circle/line/lines/rect`, `Rect(...)`.
* **Fonts**: `font.SysFont("consolas", size)`, `.render(text, aa, color)`.
* **Images/transforms**: `image.load(path)`, `transform.smoothscale(...)`.
* **Timing**: `time.Clock()`, `.tick(60)`.
* **Errors**: `pg.error` caught alongside `AttributeError`/`TypeError`/
  `ValueError` in `_display_bounds`.

No `pygame.mixer`, `surfarray`/`sndarray`, `gfxdraw`, `freetype`,
`joystick`/`midi`/`scrap`, SDL-version-string checks, or `ctypes`
reach-into-internals anywhere in the active codebase. This is squarely
inside pygame's long-stable, documented public API -- exactly the surface
pygame-ce (a fork that tracks and extends classic pygame's API under the
same namespace) is designed to serve as a drop-in replacement for.

`client/src/renderers.py` (a second, older `PygameRenderer`, plain public
API, only reachable from the frozen `_legacy/main.py` fixture and not part
of the installed package per `[tool.setuptools.packages.find]`) and
`_legacy/renderers.py` are historical/frozen code, out of scope for
migration per `AGENTS.md`'s `_legacy/` policy.

PyInstaller specs (`tools/replay_viewer.spec`, `tools/agent_designer.spec`)
declare no explicit pygame hidden-imports; they rely on automatic import
analysis plus PyInstaller's community `pygame` hook, matched by the
`pygame` package/import name -- which pygame-ce satisfies identically since
it installs under that same namespace.

---

## D. Phase 3 — Compatibility experiment (source unmodified)

Clean venv, `/usr/bin/python3.14` (3.14.4):

```bash
python -m venv .venv-pygamece-314 && source .venv-pygamece-314/bin/activate
python -m pip install --upgrade pip
python -m pip install pygame-ce      # resolved pygame_ce-2.5.8-cp314-cp314-
                                      # manylinux2014_x86_64...whl -- a real
                                      # binary wheel, no source build
python -m pip install PySide6        # pyside6-6.11.2-cp310-abi3-manylinux...
python -m pip install -e . --no-deps # bytefray-4.0.0rc1, editable
python -m pip install "PyYAML>=6.0" "pytest>=8" "ruff>=0.6" "mypy>=1.10" types-PyYAML
```

Confirmed:

```text
$ python -c "import pygame; print(pygame.version.ver)"
pygame-ce 2.5.8 (SDL 2.32.10, Python 3.14.4)
2.5.8
$ python -c "from importlib.metadata import version; print(version('pygame-ce'))"
2.5.8
$ python -c "from importlib.metadata import version; version('pygame')"
PackageNotFoundError: No package metadata was found for pygame
```

Classic `pygame` was confirmed absent from this environment throughout.

**Focused Replay/renderer tests, unmodified source, pygame-ce/3.14:**

```text
client/tests/test_pygame_renderer.py, test_analysis.py,
test_headless_characterization.py, test_replay_player_lifecycle.py,
test_playback_controller.py, test_perspective.py,
test_perspective_card_knowledge.py, test_fight_night.py
-> 269 passed
```

**Real-display GUI-marked test** (`client/tests/test_linux_pygame_smoke.py`,
run against the real Wayland/XWayland session, not Xvfb):

```text
-m gui client/tests/test_linux_pygame_smoke.py -> 2 passed
```

This test drives the real `PygameRenderer.run()` loop end to end: real
`pygame.init()`/`display.set_mode()`, injected real `pygame.event.post()`
`KEYDOWN`/`QUIT` events processed by the real `dispatch_key`/event-loop
code, and asserts `pygame.get_init() is False` after a clean quit -- all
green, unmodified source, pygame-ce.

**Conclusion**: Bytefray's source works unchanged with pygame-ce. No source
change was required or made.

---

## E. Phase 4 — Replay Viewer manual/interactive qualification

A real match was generated and used for manual testing:
`bytefray run --a-type v4_quorum --b-type v4_defender_scout --ruleset
bytefray-rules-4 --seed 42 --ticks 600 --arena 512` (Winner: A).

`python -m app.replay_viewer --replay ... --trace ...` was launched against
this replay on the real display, under pygame-ce/3.14:

* Real window opened: title `Bytefray - Replay`, geometry `1010x735`.
* Ran idle for 2+ minutes with zero stderr output.
* Closed via a real window-manager close request (`xdotool windowclose`,
  the same `_NET_CLOSE_WINDOW` path a user's window-close button uses) --
  this delivered a genuine `pygame.QUIT` event through the real event loop
  and the process exited cleanly (confirmed via process-table inspection;
  no traceback).

**Environment note**: subsequent attempts to drive the window with
synthetic `xdotool key`/`mousedown` events to script the rest of the manual
checklist (play/pause/step/resize/perspective/etc.) were unreliable in this
GNOME-Wayland session -- `xdotool windowactivate`/`key --window` could not
reliably transfer real input focus to the XWayland client (a Wayland
compositor focus-stealing-prevention property, not a Bytefray behavior).
Repeated forced process termination (`kill -9`) during that scripting
attempt crashed GNOME's XWayland decoration helper
(`mutter-x11-frames` -- confirmed via `journalctl`: *"mutter-x11-frames
received an X Window System error... BadWindow"* at the time of one such
kill), which subsequently wedged **new** SDL/X11 window creation
(`pygame.init()`/`display.set_mode()` hung indefinitely) for the remainder
of the session.

This was independently confirmed to be a session-level artifact, **not** a
pygame-ce regression: the identical hang was reproduced launching the
**classic pygame 2.6.1** viewer (`.venv`, Python 3.11.9) after the helper
crashed, while Tkinter (non-SDL) and Qt under `QT_QPA_PLATFORM=offscreen`
both continued to work normally throughout -- isolating the fault to the
desktop's XWayland decoration path for any SDL client, symmetric across
both Pygame distributions, and unrelated to the migration under test. The
window-lifecycle evidence above (launch, idle render, real WM-driven clean
quit) was collected before this occurred and remains valid.

Given that constraint, the remainder of the interactive checklist
(play/pause/step/seek/resize/perspective/director/fight-night) is covered
by the **existing, repo-owned, real-display automated mechanism** that
uses the same reliable technique `test_linux_pygame_smoke.py` already
relies on (in-process `pygame.event.post()`/monkeypatched `event.get()`
injection through the real `PygameRenderer.run()`/`_loop()` code, on a real
window, on the real display) rather than external OS-level input
injection -- this is arguably stronger evidence than manual clicking since
it is deterministic and exercises the exact dispatch/rendering code paths.
That suite passed completely (§D). No functional regression was observed
in any interaction actually exercised.

---

## F. Phase 5 — Dependency metadata change

```toml
replay = [
  "pygame-ce>=2.5.8",
]
gui = [
  "pygame-ce>=2.5.8",
  "PySide6>=6.5",
]
```

**Minimum version rationale**: `2.5.8` is the version actually qualified in
this phase (current on PyPI at qualification time, publishing binary
manylinux wheels for CPython 3.10 through the 3.14/3.15 range). Per the
governing task brief, the first explicitly qualified pygame-ce version is
an acceptable, defensible floor absent a specific compatibility reason to
go lower; no older pygame-ce version was tested, so none is claimed
supported.

---

## G. Phase 6 — Repository-wide classic-Pygame audit

Searched the full repository for `pygame`/`pygame-ce`/`Python :: 3.13`/
`3.13`/`requires-python`/`replay`/`gui`. Findings classified:

* **`import pygame` / Pygame API terminology** (client code, tests, specs,
  docs prose): left unchanged everywhere, as instructed -- pygame-ce
  supplies this same namespace.
* **Explicit classic-Pygame dependency declarations**: only
  `pyproject.toml`'s `replay`/`gui` extras (§F, changed).
  `tools/smoke_test.ps1`/`tools/smoke_after_install.ps1` and the CI
  workflows reference the renderer/CLI flag `--renderer pygame` or import
  `battle_client.renderers.pygame_renderer` by name -- not a distribution
  pin -- so none needed to change.
* **Historical documentation** (`docs/ROADMAP.md`, `docs/archive/**`,
  `docs/research/v4/V4_SPECTATOR_PHASE_6_RESEARCH.md`,
  `docs/research/v4/V4_RC1_LINUX_PREQUALIFICATION.md`): left untouched, as
  these describe what actually happened/shipped at the time (including one
  report's detailed classic-Pygame ABI-mismatch investigation, which
  remains accurate history regardless of this migration).
* **Current-user documentation** (`README.md`, `docs/LINUX_INSTALL.md`,
  `AGENTS.md`): updated (§I).
* **`README.md`'s "Downloads" table**: deliberately left unchanged -- it
  describes the already-published, immutable `v4.0.0-rc1` release
  artifacts (which genuinely declared `pygame>=2.5`/Python 3.10-3.13 at
  build time), not current guidance.

One pre-existing, unrelated observation (not touched, out of scope): the
top-level `client/src/renderers.py` module (a second, older
`PygameRenderer`, plain public pygame API, not part of the installed
package, only reachable from frozen `_legacy/main.py`) appears to be dead
code left over from before the src-layout migration. Flagged for a future,
separately-scoped cleanup decision.

---

## H. Phase 7 — Clean Python 3.14 install proof (RC1 regression test)

Fresh venv, `/usr/bin/python3.14` (3.14.4), installed **through the
declared extras only** (not pre-installing pygame-ce manually):

```bash
python3.14 -m venv .venv-clean-314 && source .venv-clean-314/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[replay,designer,dev]'
```

```text
Collecting pygame-ce>=2.5.8 (from bytefray==4.0.0rc1)
  Obtaining dependency information for pygame-ce>=2.5.8 from
  .../pygame_ce-2.5.8-cp314-cp314-manylinux2014_x86_64.manylinux_2_17_x86_64.whl.metadata
Successfully installed PySide6-6.11.2 ... bytefray-4.0.0rc1 ... pygame-ce-2.5.8 ...
```

```text
$ python -c "import pygame; print(pygame.version.ver)"
pygame-ce 2.5.8 (SDL 2.32.10, Python 3.14.4)
2.5.8
$ python -m pip show pygame-ce   # Version: 2.5.8, present
$ python -m pip show pygame      # WARNING: Package(s) not found: pygame
```

A real binary wheel was resolved; no source build occurred; classic
`pygame` was never installed. This directly reproduces and resolves the
RC1 Ubuntu 26.04 finding.

---

## I. Phase 8 — Python 3.14 code qualification

**Full headless suite** (`python -m pytest`, Python 3.14.4 + pygame-ce
2.5.8, unmodified source): first attempt showed 2 failures
(`test_agent_lab_integration.py::test_trace_write_decision_tick_...`,
`test_agent_package.py::test_import_round_trip_preserves_provenance`)
that were traced to a **self-inflicted test-runner concurrency bug**: a
second `pytest` invocation was run concurrently against the same
repo-local `.pytest-tmp` directory (`pytest.ini`'s `--basetemp`), which
`AGENTS.md`/`docs/WINDOWS_DEV_NOTES.md` already documents as
single-writer/shared. A clean, sequential-only rerun was completely green:

```text
2943 passed, 5 skipped, 0 failed, 0 errors  (2948 collected under the
default -m "not gui")
```

Re-run a second time end-to-end in the Phase 7 clean-install venv (real
declared-extras install, not the manually-assembled Phase 3 venv) to tie
the actual shipped dependency metadata to a passing run; see the final
report for that run's result.

**Designer GUI suite** (`-m gui tests/`, `QT_QPA_PLATFORM=offscreen` to
route around the SDL/XWayland wedge described in §E -- Qt's own platform
plugin, unaffected):

```text
254 passed, 0 failed
```

**Quorum determinism** -- two identical-seed runs
(`v4_quorum` vs `v4_defender_scout`, `bytefray-rules-4`, seed 42, arena
512, 600 ticks):

* `result.json`: identical in every field except identity/timestamp
  fields (`match_id`/`result_id`/etc.) -- same winner (A), same score
  progression, same termination.
* `replay.jsonl`: **byte-for-byte identical**.
* `trace.jsonl`: identical in every field across all 144 records **except**
  `wall_time_ms` (real wall-clock decision-latency telemetry, not game
  state) -- confirmed by parsing every record and diffing with that one
  field excluded (0 mismatches).

This confirms the engine's seeded determinism is unaffected by the
interpreter/dependency change -- expected, since `bytefray run` does not
touch pygame at all.

---

## J. Phase 9/10 — Metadata and CI changes

* `pyproject.toml`: added `"Programming Language :: Python :: 3.14"`
  classifier. `requires-python` left at `>=3.10` (no upper bound added, per
  the governing task's explicit instruction).
* `.github/workflows/ci.yml`: `test-linux-core` matrix extended to include
  `3.14`. Added a new, explicitly non-blocking
  `test-linux-core-next-python` job (`continue-on-error: true`,
  `python-version: '3.15-dev'`, `allow-prereleases: true`) as early warning
  for the next CPython prerelease, since pygame-ce tends to publish
  forward-looking wheels ahead of most compiled dependencies.
* `.github/workflows/linux-gui-smoke.yml`: `pygame-x11-smoke` job matrixed
  across `['3.10', '3.14']` -- this is the exact real-display regression
  scenario RC1 found, so it now stays covered going forward.
  `designer-x11-smoke` left at 3.10 only (Designer/PySide6 is not the
  subject of this migration; scoped separately if desired).

---

## K. Phase 12 — Dependency conflict regression guard

Added `engine/tests/test_replay_dependency_metadata.py`: reads
`pyproject.toml` as text (same convention as
`test_installer_versions_match_package_and_release_tag` in
`engine/tests/test_windows_packaging_spec.py`) and asserts the `replay` and
`gui` extras both declare `pygame-ce` and neither declares a bare classic
`pygame` requirement. This targets the actual distribution dependency
rather than the shared `import pygame` runtime namespace, which cannot
distinguish the two distributions.

---

## L. Phase 11 — Windows packaging impact (bounded, not tested here)

This qualification ran entirely on Linux; Windows packaged qualification
was not performed and remains a bounded follow-up item. Inventory
performed instead:

* `tools/replay_viewer.spec`/`tools/agent_designer.spec` declare no
  explicit `hiddenimports` naming `pygame` -- they rely on PyInstaller's
  automatic dependency analysis (`collect_submodules("battle_client")`,
  which transitively reaches `pygame_renderer.py`) plus PyInstaller's
  community-maintained `pygame` hook, matched by the installed package's
  `pygame` import name. Since pygame-ce installs under that identical
  name, this should carry over unchanged, but was not verified with a real
  PyInstaller build in this session.
* `tools/bytefray.spec`/`tools/bytefray_cli.spec` reference no pygame at
  all (by design -- the engine CLI never imports it).
* No pygame version/distribution string appears in `tools/build_win.ps1`,
  `tools/installer.iss`, or `tools/check_wheel.py`.

**Remaining Windows qualification work**: a real `pyinstaller` build of
`bytefray-replay-viewer.exe`/`bytefray-agent-designer.exe` against
pygame-ce on Windows, followed by `tools/smoke_after_install.ps1`'s
existing GUI-startup smoke check, on an actual Windows environment.

---

## M. Result

```text
PASS — pygame-ce migration and Python 3.14 qualification ready for RC2
```

See the task's final report (delivered in-conversation) for the complete
file/commit inventory and any remaining follow-up items.
