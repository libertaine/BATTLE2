# Changelog

This changelog records notable user- and developer-visible changes to Bytefray
(formerly BATTLE2).

## [Unreleased]

## [0.5.1] - 2026-08-09

Patch release: Linux virtual-environment compatibility for Agent Lab
supervised workers, plus dynamic-agent packaging hygiene.

### Fixed

- Linux supervised Agent Lab workers (`agents test`/`agents validate`) now
  preserve the active virtual environment's interpreter identity instead of
  resolving `sys.executable`'s symlink chain to the base interpreter it was
  created from. The previous resolution walked past a standard Linux venv's
  `bin/python` symlink to a base interpreter lacking the venv's
  site-packages, so every supervised worker subprocess failed with
  `No module named battle_engine`.
- Dynamic Python agent imports no longer leave `__pycache__`/`.pyc` files
  beside agent source -- including the bundled reference opponent under
  `battle_engine/data/...` -- preventing source-checkout pollution and
  wheel/sdist packaging contamination.
- Linux type checking no longer reports the Windows-only
  `ctypes.WinDLL` access as an `attr-defined` error.

## [0.5.0] - 2026-08-09

v0.5's primary theme is **Agent Lab**: v0.4 closed the
create → validate → test → inspect → modify → repeat loop's first half;
v0.5 attacks the second half -- understanding *why* an agent behaved the
way it did, and containing an agent that never returns. See
`docs/specs/agent_lab.md` for the full design rationale and
[docs/AGENT_LAB.md](docs/AGENT_LAB.md) for the user-facing reference.

### Added

- `bytefray.agent_trace` v1: a new, separate, versioned JSONL artifact
  recording each Python entrant's `reset()`/`act()` call boundary data
  (Observation, AgentAction, diagnostic, wall time) -- independent of and
  never folded into `battle2.replay`/`battle2.result`.
- Supervised worker-subprocess execution: `agents test`/`agents
  validate` can now run a Python entrant's `load`/`reset`/`act` calls
  through one whole-match-lifetime worker subprocess per entrant, with a
  configurable per-call timeout (`--timeout`, default 5s). A stalled call
  is reported with a new diagnostic (`agent_load_timeout`,
  `agent_reset_timeout`, `agent_action_timeout`, `agent_worker_exited`,
  `agent_worker_protocol_error`) and the entrant is forfeited (or, for a
  load/reset stall, the match never starts) exactly as an equivalent
  in-process exception already was -- the match continues with any
  surviving entrant. Development-time hang containment only, not a
  security sandbox. `bytefray run`/tournament are unaffected: both new
  `MatchRequest` fields default to off.
- `bytefray agents inspect <run>` / `bytefray agents diverge <a> <b>`:
  headless CLI inspection of a development trace (summary, one tick's
  decisions, decisions around a tick, failures only) and first-divergence
  comparison between two traces. Executes no agent code.
- Designer: an "Inspect Trace" button and Timeout(s) option in the
  existing Agent Development tab, backed by a new, modest
  `TraceInspectorDialog` (tick/agent navigation, no source editor, no
  general debugger).
- `runs/agents_test/<agent-id>/<run-label>/` gains an optional
  `trace.jsonl` sibling alongside the existing `replay.jsonl`/
  `result.json`/`summary.json` -- additive only, on by default.

### Fixed

- A worker subprocess stuck inside a hung `act()`/`reset()` could
  survive indefinitely as an orphan process if its immediate parent was
  itself abruptly killed (e.g. the Designer's `_dispose_process()`
  killing a supervised `agents test` mid-hang) -- the worker has no
  opportunity to notice its parent died via the cooperative EOF path
  while stuck in the agent's own tight loop. Fixed with OS-level
  containment (`battle_engine.process_containment`): a Windows Job
  Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` on the parent side,
  `prctl(PR_SET_PDEATHSIG, SIGKILL)` on POSIX.
- A supervised agent calling `input()` during `reset()`/`act()` could read
  from the same underlying pipe the parent's worker-protocol request loop
  was using, silently stealing the next protocol request line and
  permanently desynchronizing the wire protocol. Agent-visible `sys.stdin`
  is now rebound to a closed/empty stream before any agent code runs
  (mirroring the existing `sys.stdout` -> `sys.stderr` redirection), so
  `input()` now raises an immediate `EOFError` instead.
- Closed a race in the POSIX `PR_SET_PDEATHSIG` registration where a
  parent that died before the worker reached its own `prctl()` call could
  leave the signal armed too late to ever fire; `die_with_parent()` now
  captures the parent pid immediately before registering and
  self-terminates if it changed right after.
- The hidden `agents _worker` verb now rejects unexpected arguments
  instead of silently blocking on stdin.
- `battle-cli.exe`, `battle-agent-designer.exe`, and
  `battle-replay-viewer.exe` could fail to discover or parse any
  `agent.yaml` at all (`... is not valid JSON. Convert to JSON, or 'pip
  install pyyaml' to allow YAML.`) because PyYAML's import was dynamic
  and therefore invisible to PyInstaller's static analysis; only
  `battle2.exe` happened to bundle it, by accident, via an unrelated
  unused module. PyYAML is now imported statically wherever agent
  manifests are parsed, so all four frozen executables bundle it
  reliably.
- The Designer's Run/Tournament/Validate/Test child processes could look
  for agents in a different directory than the one the Designer itself
  used, in a portable (no-installer) checkout: the child environment
  relied on inheriting `BYTEFRAY_ROOT`/`BATTLE2_ROOT`/`BATTLE_ROOT` from
  the OS environment, which only matches the Designer's own resolved
  root when that root came from an explicit env var (true after a normal
  install, not in a portable extraction). All five child-process launches
  now explicitly set `BYTEFRAY_ROOT` to the Designer's own resolved data
  root.

## [0.4.0] - 2026-08-08

v0.4's primary theme is **Agent Authoring & Development Feedback Loop**:
tightening the loop an agent author works in, from writing an agent to
seeing how it performs. The supported user journey, available from both
the CLI and the Designer GUI, is
create → validate → test → inspect → modify → repeat.

### Added

- Added `bytefray agents create <agent-id>`, scaffolding a minimal Agent
  API v1 Python agent from a bundled template resource into the writable
  data root (Phase 1).
- Added `bytefray agents validate <agent-id>`, a single-tick dry run
  (discover, load, `reset()`, one `act()`) reusing the production
  loader/action-validator and reporting a stable stage/code diagnostic on
  failure, with no runtime timeout or sandbox (Phase 2).
- Added `bytefray agents test <agent-id> [--opponent <id>] [--seed <n>]
  [--ticks <n>]`, a short (200-tick default) real match run through the
  exact `NativeMatchService` boundary against an internal reference Python
  opponent or another discovered agent, writing the same canonical
  `replay.jsonl`/`result.json`/`summary.json` artifacts any other native
  match writes under `runs/agents_test/<agent-id>/<run-label>/`. A tested
  agent's own forfeit, death, loss, or pre-tick-zero initialization
  failure -- and an explicit `--opponent`'s own initialization failure --
  are all successfully-evaluated development tests (exit `0`); only the
  internal reference opponent failing to initialize, or an unknown/
  non-Python agent/opponent, is a tool failure (exit `2`) (Phase 3).
- Added an **Agent Development** tab to the PySide6 Agent Designer,
  bringing the same create → validate → test → replay loop into the GUI:
  `New Agent` (a direct, in-process scaffold call), out-of-process
  `Validate` and `Test` (with Opponent/Seed/Ticks options) sharing the
  Designer's existing `QProcess`/single-active-process machinery, typed
  completed/initialization-failed/tool-failure presentation read from the
  same canonical CLI output and `result.json` the CLI itself produces, and
  an `Open Replay` action independent of the Simple/Advanced tabs' own
  "Open Last Replay" (Phase 4a-4c; see
  `docs/specs/agent_designer_workflow.md`).

### Changed

- Extracted the replay-domain facts `PygameRenderer` already computed
  (territory ownership/history, match event collection/query,
  selected-arena-cell state) out of
  `client/src/battle_client/renderers/pygame_renderer.py` and into a new,
  Pygame-free `client/src/battle_client/analysis.py`, then migrated the
  renderer to consume it, removing the private duplicate implementations.
  The one deliberate behavior change: the renderer-local "recently
  changed" flag on a selected cell moved from a field on the domain
  `SelectedCellInfo` dataclass to an explicit keyword parameter on the
  renderer's own `format_inspector_lines`, since it reflects UI
  observation history, not a replay fact (Phase 5; see
  `docs/specs/replay_analysis.md`). Pygame viewer behavior is unchanged.
- Rewrote `ARCHITECTURE.md` to describe the current `NativeMatchService`-
  centered architecture (canonical `battle2.replay` v3 writing, the
  `bytefray run`/`tournament` routing to it, the `battle_client` replay-
  consumption boundary, and the actual `app.agent_designer`/
  `app.replay_viewer` entry points) instead of the superseded v0.2
  document.
- Confirmed `app/match_runner.py` is not part of the shipped Windows
  executable set: `tools/build_win.ps1` (the script CI's `build-windows-exe`
  job actually runs) and `tools/installer.iss` build/package only
  `battle2`, `battle-cli`, `battle-agent-designer`, and
  `battle-replay-viewer`. No build artifact or configuration change was
  needed as a result. `tools/match_runner.spec` and the match-runner build
  steps in `tools/build_executables.ps1`/`tools/build_executables_windows.ps1`
  are pre-v0.3 leftovers not invoked by CI or by `build_win.ps1`; they are
  left as-is pending a human decision on whether to remove them (see
  ARCHITECTURE.md's Packaging section).

### Fixed

- Corrected `app/README.md` and `README.md`'s directory overview, which
  described `app/main.py` as the Agent Designer's entry point or an
  alternate way to launch it. Neither `app/agent_designer.py` nor
  `app/replay_viewer.py` imports `app/main.py`; the supported entry
  points are `battle-agent-designer`/`bytefray design` (`app.agent_designer`)
  and `battle-replay-viewer` (`app.replay_viewer`).

## [0.3.0] - 2026-08-08

### Added

- Added a `runtime_kind` discriminator to the canonical replay header so a
  reader can tell whether `pc`/`region`/`cpu_used` mean the VM's real fetch
  address/code footprint/instruction count or the Python runtime's
  agent-opaque controller bookkeeping/callback count, instead of leaving
  that distinction implicit.
- Added byte-level `values` to canonical memory-diff records (previously only
  address/length/owner), and an explicit tick-zero initial-state record
  capturing each entrant's starting registers and (for VM matches) its
  loaded code -- together these make engine-observable arena content and
  per-entrant controller state reconstructable from a canonical replay alone,
  without rerunning any agent.
- Added `battle_engine.result_model.verify_replay_digest` and
  `verify_result_replay` for explicit, opt-in replay integrity verification
  against a result's recorded SHA-256 digest, raising a typed
  `ReplayIntegrityError` with a stable `.code` on mismatch, missing, or
  unreadable files.
- Added `engine/tests/test_replay_reconstruction.py`, including an
  independently-derived-ground-truth end-to-end test proving canonical VM and
  Python replays reconstruct live match state, plus coverage for digest
  verification, `result_id` stability under nondeterministic exception text,
  and `match_id` path-independence/change-sensitivity.
- Added Agent API v1 for Python agents, including versioned manifests, explicit
  entry points and factories, fresh-instance construction, engine-controlled
  metadata, and validation of callable `reset()` and `act()` lifecycle methods.
- Added collision-resistant module loading so Python agents with the same source
  filename can be imported independently.
- Added `NativeMatchService` with typed match requests, entrants, and results as
  the canonical boundary for native matches; the CLI now acts as an adapter over
  this service while retaining VM behavior and compatibility output.
- Added deterministic Python-vs-Python native matches with restricted immutable
  observations, a versioned single-action vocabulary, independent per-agent RNG
  streams, and the existing instruction quota reused as the action budget.
- Added sequential entrant-order execution for Python agents, including circular
  arena reads and writes, ownership tracking, `HALT`, structured forfeits, and
  replay records using the existing schema.
- Added focused Agent API, native-service, reference-agent, scheduler, and Python
  runtime coverage, including deterministic execution and failure behavior.
- Added Agent API, agent-authoring, and native-rules documentation.
- Added structured Python runtime diagnostics, internal match and entrant
  termination reasons, and internal source-digest and derived-seed metadata.
- Added `battle2.result` schema v1 and `battle2.replay` schema v3 with stable
  match/result IDs, replay digests, and reproducibility metadata.
- Added a resumable headless round-robin tournament service with deterministic
  seeds, canonical-result standings, and per-match artifact directories.
- Added the supported `battle2 tournament` headless workflow with canonical
  agent resolution, resume/retry controls, standings output, and stable exits.
- Added a minimal Designer tournament launcher and About surface using shared,
  package-safe runtime and schema metadata.
- Added `ReplaySession`, a replay-analysis foundation providing deterministic
  forward/backward seek and incremental state reconstruction from canonical
  replay records, independent of any renderer.
- Added an interactive Pygame replay viewer with play/pause/step/restart/jump
  and adjustable playback speed, a runtime-aware HUD distinguishing VM and
  Python match state, and a clickable event timeline with click-to-seek
  navigation.
- Added territory analysis: per-tick owned-cell count/percentage summaries, a
  selected-cell inspector, a precomputed territory-history trend graph, and a
  recent-activity (recently-changed-cell) heatmap overlay, all derived solely
  from existing replay/session state.
- Stabilized the Windows development and test baseline for the interactive
  viewer and its analysis overlays.

### Changed

- Renamed the project from BATTLE2 to Bytefray. The canonical public CLI is
  now `bytefray`; the `battle2` command remains a deprecated compatibility
  alias throughout the v0.3 transition, dispatching to the identical
  implementation with the same behavior and exit codes while printing a
  one-line deprecation notice. `BYTEFRAY_ROOT` is now the preferred
  writable-data-root environment variable, with the legacy `BATTLE2_ROOT`
  and `BATTLE_ROOT` variables retained as deprecated fallbacks in that
  order. Internal Python package names (`battle_engine`, `battle_client`)
  and the `battle2.*` artifact schema identifiers (`battle2.result`,
  `battle2.replay`) are intentionally unchanged, as they are stable
  protocol identifiers rather than product branding.
- The canonical native-replay writer (`match_service._finalize_native_artifacts`)
  now builds and serializes the same typed `battle_engine.replay` dataclasses
  any reader consumes, instead of hand-building a second, independently
  maintained dict-based representation; writer and reader can no longer drift
  from each other by construction. `serialize_record` now always sorts JSON
  keys, so re-serializing a parsed record reproduces byte-identical output.
- The canonical replay's terminal result record now carries genuine final
  per-entrant state (previously always an empty `agents` list) and uses
  `null` for "no single winner" instead of leaving the field unpopulated;
  `result.json`'s `winner` field keeps its existing non-null `"tie"`
  convention unchanged for compatibility.
- Consolidated winner resolution into one implementation
  (`results.resolve_winner`, now typed against a small structural protocol
  instead of the VM's concrete `Agent` class, removing a suppressed type
  error); `match_service._effective_winner` is now only a thin, non-recomputing
  mapper to the display sentinel rather than a second implementation of the
  same win-mode rules.
- `result_id`'s identity hash now excludes raw exception-message text (which
  can embed nondeterministic content such as a default object `repr`'s
  memory address) so two otherwise-identical reruns of a match that hits the
  same agent failure get the same `result_id`. The full message is unchanged
  everywhere it is displayed to a human.
- `TournamentService` now rejects the entrant ID `"tie"` (case-insensitively)
  before scheduling, reserving it from collision with the canonical
  "no winner" sentinel.
- Characterized the native VM scheduler explicitly: living entrants consume
  their quota in spawn order, and an earlier entrant can affect a later entrant
  during the same tick.
- Characterized the Runner, Writer, Bomber, Flooder, Seeker, and Spiral reference
  agents and corrected the documented Flooder and Spiral behavior.
- Updated the README to describe current Python-agent execution accurately and
  to document the project's AI-assisted, human-directed development method.
- Updated tournament tooling for the current `battle2` CLI, lazy and portable
  build-tool discovery, source-checkout execution, and a platform-neutral roster.
- Restored targeted pull-request and main-branch GUI and pMARS validation while
  keeping display-dependent tests outside ordinary headless pytest discovery.
- Made Python module reload behavior explicit: every entrant load executes a
  fresh private module and constructs a fresh instance.
- Unified VM, Python, and pMARS outcomes behind one canonical result envelope;
  pMARS records use `replay: null`, while `summary.json` remains compatible.
- Updated `battle2 run` terminal output to identify canonical `result.json` and
  replay artifacts alongside the compatibility summary.
- Routed Designer match completion through canonical result/replay artifacts,
  with explicit homogeneous-runtime preflight and concise result presentation.

### Removed

- Removed the v0.1 `match-runner` console-script entry point and its Windows
  build/installer artifact; it called a `PygameRenderer` API removed in
  Phase 7a and had no maintained functionality. Use `bytefray replay
  --renderer pygame` or `battle-replay-viewer.exe` instead.

### Fixed

- Kept native intermediate replays private until canonical v3 serialization
  succeeds, with failed publication removing replay, result, summary, and
  temporary artifacts.
- Bound resumed tournament results to the expected canonical match identity
  and replay-header IDs, retried newly detected corruption immediately when
  requested, and surfaced corrupted counts in CLI and Designer status.
- Allowed `KeyboardInterrupt` and `SystemExit` from Python-agent callbacks to
  propagate through `NativeMatchService` while retaining artifact cleanup.
- Fixed the canonical replay's terminal result record always recording an
  empty final-agent list regardless of what actually happened in the match.
- Fixed `VM.load_code` bypassing the same write-tracking path every other
  arena write uses, which meant an entrant's initial loaded code was
  invisible to replay memory diffs (including at reconstruction time).
- Fixed a stale "Tournament execution has not yet been rebuilt on
  `NativeMatchService`" limitation note that no longer matched the code
  (`TournamentService` has called `NativeMatchService.run()` directly since
  Phase 5) or `docs/TOURNAMENTS.md`.
- Corrected Seeker branch targets so its scan and attack paths remain on valid
  instruction boundaries.
- Reset per-tick CPU usage for every entrant, preventing a dead entrant's final
  tick usage from being added repeatedly to cumulative statistics.
- Removed obsolete tournament CLI arguments and machine-specific paths that
  prevented the tournament controller from working with current source trees.
- Prevented rejected or failed Python matches from leaving stale success
  artifacts, and published completed Python replays atomically.

### Known Limitations

- Python native execution currently supports Python-vs-Python matches only;
  mixed VM/Python matches are rejected explicitly.
- Python source and controller logic are not stored in, or corruptible through,
  arena memory.
- Python agents are trusted in-process code. Hard timeouts and process isolation
  for non-returning callbacks are not implemented; operator abort exceptions
  propagate, but they cannot interrupt a callback that never returns control.
- Canonical replay reconstruction requires a linear scan of memory diffs from
  tick 0; there is no snapshot/checkpoint shortcut for seeking directly to a
  late tick in a long match.
- Individual RNG draws inside agent code are not logged in the replay; only
  each entrant's derived seed is captured. Reproducing an agent's exact
  intermediate reasoning (not just its recorded actions) requires
  re-executing its source against that seed.
- A truncated or corrupted mid-stream replay still fails the whole read at
  the point of corruption rather than offering a partial-recovery mode.

## [0.2.0] - 2026-08-06

### Added

- Added the unified `battle2` dispatcher with `run`, `replay`, `design`, and
  `agents` commands, plus `python -m battle_engine` support.
- Added a canonical replay schema and compatibility reader, deterministic replay
  presentation lifecycle, and extracted VM, scheduling, scoring, statistics,
  results, and telemetry components behind the existing public interfaces.
- Added Python wheel packaging for Python 3.10 through 3.13 with optional replay
  and Designer dependencies kept out of the headless core installation.
- Added writable platform data roots: XDG data directories for installed Linux
  wheels, `%LOCALAPPDATA%\BATTLE2` for installed Windows wheels, and explicit
  `BATTLE2_ROOT` with legacy `BATTLE_ROOT` fallback.
- Added non-destructive initialization of the Runner, Writer, Seeker, and Spiral
  starter-agent catalog in the writable data root.
- Added headless Linux CI and wheel-content validation, optional Linux GUI smoke
  tests, Windows executable builds, and release smoke validation.
- Added reproducible, checksum-pinned tooling and provenance documentation for
  building a console-only Linux pMARS 0.9.5 executable.

### Changed

- Retained the v0.1 `battle-cli`, `match-runner`, and `battle-agent-designer`
  commands as compatibility wrappers while making `battle2` the primary CLI.
- Separated writable runtime data from packaged read-only resources and kept
  source, editable, installed-wheel, frozen-installer, and portable path behavior
  explicit across Windows and Linux.
- Made GUI imports optional and lazy so core commands, wheel checks, and headless
  Linux use do not require Pygame or PySide6.
- Hardened pMARS discovery and execution: explicit overrides, platform-aware
  lookup, shell-free invocation, normalized failures, and validation of runtime
  and wheel contents.
- Defined the release policy that Windows CLI applications bundle pMARS and its
  license, while the platform-neutral Python wheel and Linux wheel do not.
- Updated the Windows installer and portable distribution to build five onedir
  applications, including the unified dispatcher and replay viewer.

### Fixed

- Corrected installed-platform data-root selection and canonical match-output
  paths across Windows and Linux.
- Fixed unified Windows bundle packaging and launch behavior for the Agent
  Designer and its packaged sibling applications.
- Fixed Linux pMARS discovery so stale artifacts and Windows PE resources are not
  selected as Linux executables.
- Strengthened pMARS dependency, runtime, and release validation.
- Removed generated `egg-info` metadata and obsolete empty pMARS license
  placeholders from version control.

### Known Limitations

- The v0.2 Python wheel is headless-first; GUI tools require optional dependencies.
- Linux distributions do not bundle pMARS. Users must supply a compatible native
  executable or build one using the documented experimental tooling.
- Python agent source can be discovered in v0.2, but native matches still require
  a built-in or blob implementation.

## [0.1.0] - 2025-10-05

### Added

- Added the first public Windows build with an Inno Setup installer and portable
  archive.
- Added the headless `battle-cli` engine, Pygame `match-runner`, and Qt-based
  `battle-agent-designer`.
- Established the initial release and staging process.

### Known Limitations

- The starter-agent selection was limited.
- A replay viewer was not included.
- Several Designer controls and replay-playback behaviors were incomplete.
