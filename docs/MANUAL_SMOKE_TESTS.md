# Manual Smoke Tests

The automated characterization suite covers deterministic engine execution,
basic VM instructions, native match completion, scoring/winners, replay and
summary creation, agent discovery, CLI help, and headless replay processing.
The following checks require an interactive desktop, platform toolchain, or
external executable and remain manual release checks.

## Pygame replay viewer

1. Install the GUI extra and open a newly generated replay with
   `python -m app.replay_viewer` (or `bytefray replay --renderer pygame`).
2. Confirm the viewer opens at a useful automatically fitted size, then confirm
   playback, window resize/fit behavior, final frame, and close controls.
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
- [ ] `0` -- fits the arena to the available display, enlarging or shrinking
      as needed while preserving integer cell scaling.
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

### Agent package integration (v1.3, packaged application)

Release checklist for Designer "Export Agent…"/"Import Agent Package…"/
"Inspect Agent Package…" (Area A of `docs/ROADMAP.md`'s v1.3.0 section).
Automated coverage (`tests/test_agent_package_dialogs.py`, `gui`-marked)
exercises the Qt plumbing against real `battle_engine.agent_package` calls
under `QT_QPA_PLATFORM=offscreen`; this sequence is the interactive,
two-data-root confirmation automation cannot substitute for.

1. Set two isolated data roots, e.g. `BYTEFRAY_ROOT=C:\temp\root-a` and
   `BYTEFRAY_ROOT=C:\temp\root-b` for two separate `battle-agent-designer.exe`
   launches (or two portable extractions).
2. In Data Root A's Designer, select an existing Python agent (e.g.
   `hunter`) in Agent Development and click **Export Agent…**; choose a
   destination folder. Confirm the success dialog reports the agent id,
   revision id, file count, package path, and a SHA-256, and that a
   `hunter-<fingerprint>.bytefray-agent` file exists at that path.
3. In Data Root B's Designer, **Tools → Inspect Agent Package…**, select
   that file. Confirm the dialog shows agent id/kind/entry point/Agent API
   version/revision/completeness/integrity/compatibility and the trust
   disclosure text, with **Close** only (no Import option from this
   action), and that nothing under Data Root B's `agents/` changed.
4. In Data Root B's Designer, **Tools → Import Agent Package…**, select the
   same file. Confirm the same read-only details appear first, with an
   **Import…** button this time; click it, then confirm a success message
   naming the imported agent id/target path and the trust disclosure, and
   that the Agent Development combo now shows the imported agent selected
   without restarting the Designer.
5. Validate/Test the freshly imported agent from Data Root B's Agent
   Development tab; confirm it behaves identically to the original.
6. Re-run step 4 for the same package a second time; confirm the dialog
   reports "already present with this exact revision; nothing imported"
   rather than an error, and nothing under `agents/` changes.
7. In Data Root B, create a *different* agent already using the same id as
   the package (e.g. hand-edit `agents/hunter/agent.py`), plus two occupied
   alternate ids. Repeat step 4; confirm each occupied alternate prompts
   again without a crash, then enter a free id. Confirm import selects that
   exact discovery id and leaves every pre-existing directory untouched.
   Repeat with display names that differ from directory ids (and, if
   practical, duplicate display names) to confirm selection never targets a
   same-looking but different agent.
8. Attempt to inspect/import a hand-corrupted `.bytefray-agent` (flip a
   byte, or rename an unrelated `.zip`); confirm a clear, non-crashing error
   and that nothing is written to `agents/`.
9. Attempt to export a native VM starter agent (`runner`/`writer`/`seeker`/
   `spiral`) if reachable through any picker; confirm this is rejected with
   a clear message rather than producing an empty/misleading package (these
   are not selectable through the Agent Development picker at all, per
   Sec 9 of `docs/specs/agent_designer_workflow.md`, so this step may only
   be reachable via a hand-invoked package function during development,
   not through the shipped UI).
10. Start a deliberately long Agent Development Test or evaluation. While
    its subprocess is running, confirm package export/import controls cannot
    mutate agent source. Stop or let the run finish and confirm the controls
    become available again. (Metadata/resource-limit, malicious-manifest,
    and cross-platform ADS/device-name/path cases are adversarially covered
    by `engine/tests/test_agent_package.py`; do not manufacture a zip bomb
    for this manual smoke.)

### Evaluation comparison drill-down and revision restore (v1.3, packaged application)

Release checklist for Area B/C of `docs/ROADMAP.md`'s v1.3.0 section.
Automated coverage lives in `tests/test_agent_evaluation_history_dialog.py`
(`gui`-marked); this sequence is the interactive confirmation.

1. Produce two evaluations for the same candidate using the same opponent,
   seeds, ticks, rules, and both-orientations setting; change only the
   candidate source between runs so they have distinct candidate revisions.
   Candidate source is the experimental variable, **not** a changed
   condition. Select one history entry, choose **Compare With…**, and select
   the other.
2. Select a directly-comparable row (a real per-opponent match on both
   sides); confirm **Test in Agent Lab**/**Open Replay** become enabled,
   the Side control offers **Left (selected)** and **Right (comparison)**
   (neutral picker roles, not an old/new promise), defaulting to Right. With
   both entrant orientations present, select each orientation row in turn;
   confirm the detail text identifies it and each side opens that exact
   schedule's replay. Confirm **Test in Agent Lab** preserves that cell's
   ticks and physical entrant orientation; `opponent_first` must swap the
   launched roles. The dialog must also disclose that this is a rerun of
   currently installed source, not automatic execution of archived source.
3. Produce a separate pair of single-orientation evaluations that differ
   only in ticks (for example 10 versus 25). Compare them, reveal **Show
   Unmatched / Changed-Condition / Ambiguous Details**, and select the
   changed-condition entry. Confirm neither action is enabled until you
   explicitly choose **Left (selected)** or **Right (comparison)**; then
   confirm Agent Lab receives 10 or 25 ticks respectively.
4. Create an unmatched case (for example, change the opponent or seed set)
   and confirm only its one real side is offered and actionable. For a real
   ambiguous group, compare two both-orientation evaluations whose ticks
   differ: multiple cells share the nominal opponent/seed bucket, so no
   unique changed-condition pairing exists. Confirm neither action is ever
   enabled and the guidance tells you to select concrete cells in each
   evaluation's Cells list, or use `evaluations show <id> --json` to locate
   `schedule_id`/`artifact_dir`; it must not claim the CLI accepts a
   schedule-id selector.
5. From an evaluation with archived agent revisions, **Show Revision…**,
   then **Restore Files…**. Confirm the dialog shows the archived revision
   id, completeness, and current-source-drift status, a target directory
   pre-filled to `<data_root>/agent_revisions_restored/<revision_id>/`, and
   an unchecked option allowing writes into a non-empty target. Its text
   must state that matching paths are overwritten but unrelated files are
   left in place.
6. Confirm restoring to the default (empty) target succeeds, writes the
   expected files, and offers to open the resulting folder.
7. Point the target field at that same directory again without enabling the
   non-empty-target option; confirm restore is refused with nothing written
   or changed.
8. Create an unrelated sentinel file in the default target, enable the
   non-empty-target option, and restore again. Confirm matching archived
   paths are overwritten and the sentinel remains; this operation is not a
   directory replacement.
9. Point the target field explicitly at an existing live `agents/<id>/`
   directory whose source has since changed. Confirm the drift line reports
   the change and a second, live-target-specific warning names the agent and
   requires explicit confirmation. After confirming, verify the catalog
   refreshes automatically, keeps that exact agent selected, and clears any
   stale Validate/Test result so the restored source must be validated and
   tested again. Also confirm unrelated live-directory files remain.
10. Attempt a restore against an unknown/removed revision id (e.g. delete
   the `agent_revisions/<id>/` directory externally first); confirm a clear
   error, not a crash, and nothing written.
11. While a Designer-owned match, validation, test, tournament, or evaluation
    process is running, open Evaluation History and Show Revision. Confirm
    browsing remains available but **Restore Files…** is disabled, so live
    source cannot be changed underneath the active child process. Also open
    History while idle, launch **Test in Agent Lab** from a cell or comparison,
    and confirm revision restore remains disabled for that still-open History
    session; close and reopen History after the process finishes to restore it.

### Agent Lab (v0.5, packaged application)

This is the release checklist for the Agent Lab feature set (deterministic
decision tracing, `agents inspect`/`diverge`, and supervised-timeout hang
containment) -- see [AGENT_LAB.md](AGENT_LAB.md) for the user-facing
reference these steps exercise. Automated coverage
(`engine/tests/test_agent_trace.py`, `test_agent_worker.py`,
`test_supervised_runtime.py`, `test_agent_inspect.py`,
`test_agent_lab_integration.py`, `test_process_containment.py`, and the
`gui`-marked `tests/test_agent_development_*.py` trace-inspector cases)
covers the mechanics headlessly; this sequence is the human,
packaged-application confirmation.

1. `bytefray agents create smoke_agent`, then `bytefray agents validate
   smoke_agent`; confirm `status: valid` and a `trace:` line is **not**
   printed (no `--trace-path` was passed).
2. `bytefray agents test smoke_agent`; confirm the printed summary
   includes a `trace: <path>/trace.jsonl` line and the suggested
   `bytefray agents inspect <run-dir>` command.
3. Run the suggested `bytefray agents inspect <run-dir>` command from
   step 2; confirm the summary reports `failures: 0` and a sane tick
   range.
4. `bytefray replay --replay <replay-path>` from step 2's output; confirm it opens
   the same match the trace describes (spot-check one tick's arena state
   against `agents inspect --tick N`'s reported action).
5. Edit `smoke_agent`'s `agent.py` to introduce a **legal but wrong**
   behavioral bug (e.g. always `WRITE` to address `0` instead of a
   computed address) -- not an exception, a plain behavioral change.
   Re-run `agents test`; confirm the match still completes normally (no
   forfeit) but the outcome changed.
6. `bytefray agents inspect <new-run-dir> --failures`; confirm `no
   failures recorded` (the bug is behavioral, not a crash/timeout --
   `inspect --failures` is the wrong tool for it, which is itself the
   point of this step).
7. Fix the bug; re-run `agents test`, then `bytefray agents diverge
   <buggy-run-dir> <fixed-run-dir>`; confirm `status: diverged` and that
   the reported tick is the first tick the fix actually changed behavior
   at (not tick 0, not the last tick).
8. `bytefray agents diverge <fixed-run-dir> <fixed-run-dir>` (a run
   against itself, or two separate fixed runs with the same seed);
   confirm `status: identical`.
9. Edit `agent.py` to hang inside `act()` (`while True: pass`); run
   `bytefray agents test smoke_agent --timeout 2`; confirm the command
   returns within a few seconds (not 200 ticks x hang), the printed
   summary shows a `forfeit:` line with `code=agent_action_timeout`, and
   `agents inspect <run-dir> --failures` shows the same diagnostic.
10. Immediately after step 9, confirm no orphaned worker process remains
    (Task Manager / `tasklist` on Windows, `ps` on Linux) -- there should
    be no lingering `battle2`/`bytefray`/Python process beyond the
    terminal itself.
11. Launch `battle-agent-designer.exe`, open **Agent Development**,
    select `smoke_agent` (still hanging from step 9); run **Development
    Test** with the default Timeout (5s); confirm the Designer stays
    responsive (window remains movable/resizable, other tabs still
    clickable) while the test is outstanding, and that it resolves to
    "Could not be completed" or an equivalent timeout-shaped result
    within roughly 5-10 seconds rather than hanging the GUI.
12. Click **Inspect Trace** on the result from step 11 (frozen build):
    confirm the dialog opens, shows the timeout diagnostic for the
    correct tick/agent, and that tick/agent navigation and "Failures
    only" work. Confirm closing the dialog and re-opening it (or running
    a second Test) does not show stale data from the previous run.
13. Fix `agent.py` back to a non-hanging implementation; run
    **Development Test** again from the Designer; confirm **Inspect
    Trace** now reflects the new, non-hung run, not step 11's stale
    trace.
14. Repeat step 10's orphan check after closing the Designer entirely
    (not just after step 9/11's individual tests) -- confirm no worker
    process outlives the Designer window closing.

Record the result (date, machine, Windows/Linux, pass/fail per step) here
or in the PR/issue tracking the release this checklist gates.

## pMARS / Redcode integration

1. Optionally set `PMARS_CMD` to one pMARS executable path. Windows packaged
   CLI artifacts otherwise use their bundled `pmars/windows/pmars.exe`.
2. Run `battle-cli --mode redcode94 --red-a <warrior-a> --red-b <warrior-b>`.
3. Confirm pMARS launches, the reported winner agrees with its output, and the
   version 2 `summary.json` records parameters and return code.

The automated suite mocks process edge cases. Windows release validation also
uses the bundled executable to cover its real output and platform behavior.

## Windows packaging and installation

1. On a clean supported Windows host, run `pwsh tools/build_win.ps1`. Confirm it
   waits for both GUI startup smokes, checks their actual exit codes, and prints
   success only after they have exited.
2. Confirm no new `bytefray-gui-smoke-*` or
   `bytefray-agents-create-smoke-*` directory remains under the system temp
   directory, and no `agents/` directory exists under any `dist/windows/<app>/`
   tree. Confirm pre-existing `BYTEFRAY_ROOT` and
   `BATTLE2_GUI_SMOKE_EXIT_MS` values are restored exactly (or remain
   unset). Cleanup failure is a build failure, not a warning.
3. Launch every produced executable and exercise `battle-cli --help`, one native
   match, agent discovery, and replay viewing.
4. Build/run the Inno Setup installer where release validation requires it.
5. Confirm Start Menu/PATH choices, `%ProgramData%` locations, bundled resources,
   uninstall behavior, and operation from a path containing spaces.
6. Confirm all four executable trees exist and both CLI executables provide help.
7. Initialize starters, run native and bundled-pMARS matches, and verify no data
   is written beneath Program Files.
8. Close all application processes, uninstall, and confirm program files and
   shortcuts are removed while user data is preserved.
9. Reinstall and repeat the CLI and GUI startup checks.

For an isolated install/upgrade/uninstall cycle, compile `tools/installer.iss`
and run `tools/smoke_after_install.ps1 -Lifecycle` with explicit `-InstallerPath`,
`-AppDir`, and `-DataRoot` values. The smoke retains its data directory after
uninstall so the preservation checks remain inspectable; remove that test data
manually after review.

Do not alter a development workstation's installed-product state solely to run
this lifecycle check. When the frozen applications are already qualified and
the installer compiles successfully with the intended embedded version, lack of
an install/uninstall cycle is not by itself a release blocker. Run the stronger
lifecycle qualification in Windows Sandbox or another disposable Windows
environment when it is required.

CI builds the executables, but install-shell integration and visible GUI behavior
require a Windows host and are not reasonably asserted by the unit suite.

## Release artifact compatibility

Open representative archived v0.1 replay files and agent packs from a clean
installed environment, not only a source checkout. Confirm missing optional GUI
dependencies do not prevent `battle-cli --help` or native headless matches.
