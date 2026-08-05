# Manual Smoke Tests

The automated characterization suite covers deterministic engine execution,
basic VM instructions, native match completion, scoring/winners, replay and
summary creation, agent discovery, CLI help, and headless replay processing.
The following checks require an interactive desktop, platform toolchain, or
external executable and are intentionally manual for the v0.1 freeze.

## Pygame live match and replay viewer

1. Install the GUI extra and run `python -m app.match_runner`.
2. Confirm a visible window opens, updates during a match, responds to close/input
   controls, and exits without leaving a Python process.
3. Open a newly generated replay with `python -m app.replay_viewer`.
4. Confirm playback, window resize/fit behavior, final frame, and close controls.

These are not automated because they require a display server and meaningful
visual/input assertions. Headless JSONL consumption is automated separately.

## PySide6 agent designer

1. Run `python -m app.agent_designer` (and, where applicable,
   `battle-agent-designer`).
2. Confirm the catalog loads existing agent directories and manifests.
3. Select two agents, launch a match, locate its replay/summary, and open the
   replay viewer.
4. Confirm malformed form input produces a usable error and does not corrupt an
   existing manifest.

This remains manual because widget layout, native dialogs, and subprocess handoff
need human inspection across supported desktop environments.

## pMARS / Redcode integration

1. Set `PMARS_CMD` to the supported pMARS executable.
2. Run `battle-cli --mode redcode94 --red-a <warrior-a> --red-b <warrior-b>`.
3. Confirm pMARS launches, the reported winner agrees with its output, and the
   version 2 `summary.json` records parameters and return code.

The repository does not provide one portable pMARS executable for CI, and the
external program's output/platform behavior is outside the Python process.

## Windows packaging and installation

1. On a clean supported Windows host, run `pwsh tools/build_win.ps1`.
2. Launch every produced executable and exercise `battle-cli --help`, one native
   match, agent discovery, and replay viewing.
3. Build/run the Inno Setup installer where release validation requires it.
4. Confirm Start Menu/PATH choices, `%ProgramData%` locations, bundled resources,
   uninstall behavior, and operation from a path containing spaces.

CI builds the executables, but install-shell integration and visible GUI behavior
require a Windows host and are not reasonably asserted by the unit suite.

## Release artifact compatibility

Open representative archived v0.1 replay files and agent packs from a clean
installed environment, not only a source checkout. Confirm missing optional GUI
dependencies do not prevent `battle-cli --help` or native headless matches.
