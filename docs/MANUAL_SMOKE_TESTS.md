# Manual Smoke Tests

The automated characterization suite covers deterministic engine execution,
basic VM instructions, native match completion, scoring/winners, replay and
summary creation, agent discovery, CLI help, and headless replay processing.
The following checks require an interactive desktop, platform toolchain, or
external executable and remain manual release checks.

## Pygame replay viewer

1. Install the GUI extra and open a newly generated replay with
   `python -m app.replay_viewer` (or `bytefray replay --renderer pygame`).
2. Confirm playback, window resize/fit behavior, final frame, and close controls.
3. At the start prompt, confirm no replay tick is shown until Space is pressed.
4. During playback, press Space to pause and leave it paused for several seconds;
   confirm tick/event counters do not advance.
5. While paused, press `N` once and confirm exactly one logical replay record
   advances. Repeat, then resume with Space and confirm no records were skipped.
6. Close the window from the start prompt, while paused, during playback, and on
   the completion screen; confirm each path exits without a lingering process.
7. Let playback finish and confirm the completion screen appears before the
   window closes; Space or Escape should close it cleanly.

Linux CI provides X11/Xvfb startup smoke for this window. Visible rendering,
input, resizing/scaling, deterministic close behavior, and native Wayland remain
manual and Wayland is not yet validated. Headless JSONL consumption is automated
separately.

## Bytefray interactive Pygame replay viewer keyboard controls (Phase 7a)

`bytefray replay --replay <path> --renderer pygame` opens the interactive
viewer described in `client/src/battle_client/renderers/pygame_renderer.py`.
`client/tests/test_linux_pygame_smoke.py` (the `gui`-marked pytest suite)
exercises the real event loop and confirms arrow-key stepping and
QUIT-event handling programmatically, but full keyboard coverage --
especially anything involving a held modifier -- needs a human at a real
keyboard: synthetic Win32 `SendKeys` automation was tried and found
unreliable for modifier and some special-key delivery in an automated
session (arrow keys and letters register; `Shift+arrow`, `Home`, `End`,
and `Q`/`Esc` did not reliably reach the window that way), so it is not
worth chasing further with more OS-input automation. Run a canonical
replay and confirm each control:

- [ ] `Space` -- toggles play/pause; pressing it at the final tick restarts
      from tick 0 and begins playing (not a loop -- it only restarts once,
      on that explicit press).
- [ ] `Right` / `Left` -- steps forward/backward exactly one recorded tick;
      a safe no-op at the last/first tick.
- [ ] `Shift+Right` / `Shift+Left` -- seeks forward/backward roughly 10
      ticks, clamped to the replay's range.
- [ ] `Home` -- restarts to the first tick.
- [ ] `End` -- jumps to the final tick.
- [ ] `+` / `-` -- cycles playback speed through 0.25x/0.5x/1x/2x/4x/8x.
- [ ] `[` / `]` -- decreases/increases the window's cell scale.
- [ ] `T` -- toggles agent trails on/off.
- [ ] `Q` / `Esc` -- quits the window cleanly (no lingering process).

Record the result (date, machine, who ran it, pass/fail per control) here
or in the PR/issue tracking the Phase 7a closeout when performed.

## PySide6 agent designer

1. Run `python -m app.agent_designer` (and, where applicable,
   `battle-agent-designer`).
2. Confirm the catalog loads existing agent directories and manifests.
3. Select two agents, launch a match, locate its replay/summary, and open the
   replay viewer.
4. Confirm malformed form input produces a usable error and does not corrupt an
   existing manifest.

`client/src/battle_client/renderers/pygame_canvas.py` defines `PygameCanvas`,
a Qt-embeddable renderer widget, but nothing in the Designer or elsewhere in
the repository currently instantiates it -- it has no callers. There is no
embedded-canvas smoke test to run today; remove this note once `PygameCanvas`
is either wired into a consumer or removed.

This remains manual because widget layout, native dialogs, and subprocess handoff
need human inspection across supported desktop environments.

### Agent Development tab (v0.4 Phase 4, packaged application)

The automated `gui`-marked suite (`tests/test_agent_development_*.py`)
exercises this tab's Qt plumbing against stubbed and real subprocesses
under `QT_QPA_PLATFORM=offscreen`; the sequence below is the interactive,
packaged-application confirmation that automation cannot substitute for
(real window focus, real `battle2.exe` sibling-executable resolution from
the standalone `battle-agent-designer.exe`, and human judgment of the
rendered text).

1. Launch `battle-agent-designer.exe`; open the **Agent Development** tab.
2. **New Agent** with a fresh id; confirm it appears, selected, in all
   three tabs' agent combos (Simple, Advanced, Agent Development).
3. **Validate** the new agent (its unmodified template): confirm "Last
   validation: Valid" with `API: 1` and a `WRITE operand=... value=165`
   dry-run action.
4. **Development Test** with defaults (Reference opponent, seed 1337,
   ticks 200): confirm "Last development test: Complete" with a
   winner/termination/ticks line, `Open Replay` enabled, and that clicking
   it opens the existing external Pygame viewer showing the same replay.
5. Change the seed and/or ticks, and separately re-run Test against an
   explicit Python opponent (create a second agent first); confirm the
   options are reflected in the result text.
6. **Open Agent Folder**: confirm Windows Explorer opens the correct
   directory.
7. Edit `agent.py` externally to raise inside `reset()`; return to the
   Designer without restarting it; **Validate** again: confirm the
   `reset`-stage failure renders as "Last validation: Invalid" and does
   not confuse the prior "Valid" result with the new one.
8. **Development Test** the same broken agent: confirm "Last development
   test: Initialization failed" with `Stage: reset`/`Code:
   agent_reset_failed`, no `Open Replay` button enabled, and text stating
   no replay was created because the match did not start (an
   agent-development outcome, not an application/tool failure).
9. Repeat step 8 with an explicit `--opponent` whose `agent.py` raises in
   `reset()`: confirm the result names the opponent (`Opponent: ...`), not
   the tested agent, as the entrant that failed to initialize.
10. Confirm a Simple-tab match launch is disabled while a development test
    is running, and vice versa (Validate/Test disabled during a
    Simple/Advanced/Tournament run).
11. Confirm Stop (Simple or Advanced tab) cancels an in-flight Validate or
    Test and shows "Stopped by user" rather than any completed/failed
    shape.

## pMARS / Redcode integration

1. Optionally set `PMARS_CMD` to one pMARS executable path. Windows packaged
   CLI artifacts otherwise use their bundled `pmars/windows/pmars.exe`.
2. Run `battle-cli --mode redcode94 --red-a <warrior-a> --red-b <warrior-b>`.
3. Confirm pMARS launches, the reported winner agrees with its output, and the
   version 2 `summary.json` records parameters and return code.

The automated suite mocks process edge cases. Windows release validation also
uses the bundled executable to cover its real output and platform behavior.

## Windows packaging and installation

1. On a clean supported Windows host, run `pwsh tools/build_win.ps1`.
2. Launch every produced executable and exercise `battle-cli --help`, one native
   match, agent discovery, and replay viewing.
3. Build/run the Inno Setup installer where release validation requires it.
4. Confirm Start Menu/PATH choices, `%ProgramData%` locations, bundled resources,
   uninstall behavior, and operation from a path containing spaces.
5. Confirm all four executable trees exist and both CLI executables provide help.
6. Initialize starters, run native and bundled-pMARS matches, and verify no data
   is written beneath Program Files.
7. Close all application processes, uninstall, and confirm program files and
   shortcuts are removed while user data is preserved.
8. Reinstall and repeat the CLI and GUI startup checks.

For an isolated install/upgrade/uninstall cycle, compile `tools/installer.iss`
and run `tools/smoke_after_install.ps1 -Lifecycle` with explicit `-InstallerPath`,
`-AppDir`, and `-DataRoot` values. The smoke retains its data directory after
uninstall so the preservation checks remain inspectable; remove that test data
manually after review.

CI builds the executables, but install-shell integration and visible GUI behavior
require a Windows host and are not reasonably asserted by the unit suite.

## Release artifact compatibility

Open representative archived v0.1 replay files and agent packs from a clean
installed environment, not only a source checkout. Confirm missing optional GUI
dependencies do not prevent `battle-cli --help` or native headless matches.
