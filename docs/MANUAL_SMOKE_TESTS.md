# Manual Smoke Tests

The automated characterization suite covers deterministic engine execution,
basic VM instructions, native match completion, scoring/winners, replay and
summary creation, agent discovery, CLI help, and headless replay processing.
The following checks require an interactive desktop, platform toolchain, or
external executable and remain manual release-candidate checks.

## Pygame live match and replay viewer

1. Install the GUI extra and run `python -m app.match_runner`.
2. Confirm a visible window opens, updates during a match, responds to close/input
   controls, and exits without leaving a Python process.
3. Open a newly generated replay with `python -m app.replay_viewer`.
4. Confirm playback, window resize/fit behavior, final frame, and close controls.
5. At the start prompt, confirm no replay tick is shown until Space is pressed.
6. During playback, press Space to pause and leave it paused for several seconds;
   confirm tick/event counters do not advance.
7. While paused, press `N` once and confirm exactly one logical replay record
   advances. Repeat, then resume with Space and confirm no records were skipped.
8. Close the window from the start prompt, while paused, during playback, and on
   the completion screen; confirm each path exits without a lingering process.
9. Let playback finish and confirm the completion screen appears before the
   window closes; Space or Escape should close it cleanly.

Linux CI provides X11/Xvfb startup smoke for this window. Visible rendering,
input, resizing/scaling, deterministic close behavior, and native Wayland remain
manual and Wayland is not yet validated. Headless JSONL consumption is automated
separately.

## PySide6 agent designer

1. Run `python -m app.agent_designer` (and, where applicable,
   `battle-agent-designer`).
2. Confirm the catalog loads existing agent directories and manifests.
3. Select two agents, launch a match, locate its replay/summary, and open the
   replay viewer.
4. Confirm malformed form input produces a usable error and does not corrupt an
   existing manifest.
5. Where the embedded `PygameCanvas` is available, open and close its containing
   Qt window repeatedly. Confirm timer updates stop on close, Pygame tears down,
   and reopening creates a working canvas without terminating the Qt process.

This remains manual because widget layout, native dialogs, and subprocess handoff
need human inspection across supported desktop environments.

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
5. Confirm all five executable trees exist and both CLI executables provide help.
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
