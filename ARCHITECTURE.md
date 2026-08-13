# Bytefray Architecture

This document describes Bytefray's architecture as of the v0.7 evaluation
history work (NativeMatchService, Agent API v1 Python-vs-Python matches,
canonical `battle2.replay` schema v3, the headless tournament service, the
`bytefray agents create/validate/test` authoring commands plus the
Designer's Agent Development tab added in v0.4, the Agent Lab
deterministic tracing/`agents inspect`/`agents diverge`/supervised
timeout containment added in v0.5, the Agent Evaluation work
(`bytefray agents evaluate`, the additive `bytefray.evaluation`
artifact, and the Designer's Evaluate dialog) added in v0.6, the
default Python starter-agent roster added in v0.6.1, and the
`bytefray.evaluation` v2 capture hardening plus the Qt-free
`battle_engine.evaluation_history` discovery/comparison package and
`bytefray agents evaluations list/show/compare` added in v0.7). It
supersedes the v0.2-era architecture document; that superseded text
remains available in git history (see the `v0.2.0` tag) and in
[`docs/V0_2_MIGRATION.md`](docs/V0_2_MIGRATION.md) for migration context.
This document describes what exists today (see "v0.4.0 delivery history",
"Agent Lab (v0.5.0)", "Agent Evaluation (v0.6.0)", "Default Agent
Build-Out (v0.6.1)", and "Evaluation History (v0.7)" at the end for how
each milestone was delivered).

## Runtime components

### Engine package (`engine/src/battle_engine`)

Low-level layers remain acyclic and mostly standard-library-only, as before:

- `battle_engine.config` owns the mutable `Config` and `Weights` dataclasses.
- `battle_engine.instructions` owns byte-oriented ISA constants and `enc`.
- `battle_engine.agent_state` owns the mutable execution-time `Agent` state.
- `battle_engine.vm` owns circular arena memory, ownership, instruction
  decoding, wrapping behavior, and per-tick memory differences. The VM
  executes instructions only; it does not calculate scores or statistics.
- `battle_engine.core` re-exports `VM`, `Config`, `Weights`, `Agent`, `enc`,
  and the `Kernel` facade from their extracted modules, so
  `from battle_engine.core import VM, Config, ...` keeps working.
- `battle_engine.match.MatchRunner`, `battle_engine.scoring.ScoringPolicy`,
  and `battle_engine.statistics.StatisticsCollector` own tick scheduling,
  scoring, and in-memory counters respectively, without persisting
  anything. `battle_engine.results` owns winner resolution
  (`results.resolve_winner`) and persistence-neutral summary construction.
  `battle_engine.telemetry` defines the replay/summary sink protocols
  (`JSONLSink`, `NullSummarySink`, etc.) used by both the VM and Python
  execution paths.

**`NativeMatchService`** (`battle_engine.match_service`) is the canonical
execution/orchestration boundary for every native (non-pMARS) match,
whether invoked from the single-match CLI, the Designer, or the
tournament service. It accepts a typed `MatchRequest` (a `Config`, a tuple
of `MatchEntrant`s, a tick limit, and a replay path) and returns a typed
`NativeMatchResult`. It:

1. rejects mixed VM/Python compositions, missing bytecode, missing Python
   specs, or duplicate entrant IDs (`UnsupportedMatchCompositionError`)
   before anything runs;
2. routes an all-VM request through `Kernel.run()` (the VM scheduler) or an
   all-Python request through `PythonEntrantController.run()`
   (`battle_engine.python_runtime`, built on Agent API v1 —
   `battle_engine.agent_api`), each writing an intermediate replay through
   the same `JSONLSink`/temp-file-then-rename discipline;
3. calls `_finalize_native_artifacts` to compute the canonical `match_id`
   and `result_id` (via `battle_engine.result_model.stable_id`), rewrite
   every intermediate replay record into the typed `battle_engine.replay`
   dataclasses at schema version 3, and atomically publish the canonical
   replay (`replay.jsonl`) alongside `result.json`
   (`battle2.result` schema v1, written by `write_json_atomic`) with a
   SHA-256 replay digest recorded in `result.json`'s `replay` reference.
   Both the replay header and the result envelope also carry `ruleset_id:
   "bytefray-rules-1"` (`battle_engine.rules.BYTEFRAY_RULESET_ID`, v0.10
   Phase 4) — an additive field on both schemas; see
   [`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md) for the historical
   recovery policy for artifacts written before it existed.

A partially-failed match never leaves a success-shaped replay, result, or
`summary.json` at the requested path — every write path clears stale
artifacts up front and again on any failure. `battle_engine.replay` itself
remains the standard-library-only, frozen-dataclass module that defines
the canonical wire contract (headers, per-tick snapshots, memory diffs,
engine events, terminal `MatchResult`), plus JSON (de)serialization,
JSONL streaming (`iter_replay`), and `write_replay`. The full wire
contract is in [`docs/REPLAY_SCHEMA.md`](docs/REPLAY_SCHEMA.md).

`battle_engine.agent_api` validates and loads Python agents against
Agent API v1: versioned manifests, explicit entry points/factories,
fresh-instance construction per match, collision-resistant module loading
(so two agents with the same source filename import independently), and
validation of callable `reset()`/`act()` lifecycle methods. See
[`docs/AGENT_API_V1.md`](docs/AGENT_API_V1.md). Python-vs-Python matches
are deterministic: restricted immutable observations, a versioned
single-action vocabulary, independent per-agent RNG streams derived from
the match seed, and the existing VM instruction quota reused as the
action budget. Mixed VM/Python matches remain explicitly unsupported.

`battle_engine.agents` discovers directories below `agents/`. A directory
is valid when it has `agent.yaml` (JSON syntax also accepted; YAML when
PyYAML is installed) or `agent.py`. `battle_engine.starters` validates the
canonical Runner, Writer, Seeker, and Spiral manifests bundled under
`battle_engine/data/starter_agents` and non-destructively copies only
missing files into the writable `get_data_root()/agents` catalog.

`battle_engine.builtins` assembles the native `runner`, `writer`,
`bomber`, `flooder`, `spiral`, and `seeker` VM programs into bytecode.

### Engine CLI (`battle_engine.cli`, `battle_engine.command`)

The `bytefray` command (`battle_engine.command:main`) and
`python -m battle_engine` dispatch to five lazy subcommands: `run`,
`tournament`, `replay`, `design`, and `agents`. `battle2`
(`battle_engine.command:battle2_main`) is a deprecated compatibility
alias that prints a one-line deprecation notice and otherwise dispatches
to the identical implementation.

- **`run`** reuses `battle_engine.cli.main(argv)` directly. It resolves
  configuration and agent slots from flags/environment, then branches on
  `--mode`:
  - `b2` (default, native engine): resolves VM bytecode or a Python
    `AgentSpec` per slot, builds `MatchEntrant`/`MatchRequest`, and calls
    `NativeMatchService().run(...)`. This is how ordinary single-match CLI
    execution reaches the canonical boundary.
  - `redcode94`: invokes `battle_engine.pmars.run_pmars` directly — this
    path does **not** go through `NativeMatchService` and produces no
    canonical replay (`result.json`'s `replay` field is `null`). It writes
    a `summary.json` (schema version 2) and a `battle2.result` v1 envelope
    with `mode="redcode94"` built by hand in `cli.py`, using the same
    `stable_id`/`ResultEnvelope` machinery `NativeMatchService` uses for
    identity, but with no replay to digest.
- **`tournament`** reuses `battle_engine.tournament_cli.main(argv)`,
  which drives `TournamentService` (`battle_engine.tournament_service`).
  `TournamentService` constructs a deterministic round-robin schedule and
  calls `NativeMatchService().run(...)` once per scheduled match — this is
  how tournament execution reaches the canonical boundary, identically to
  single-match `run`. See [`docs/TOURNAMENTS.md`](docs/TOURNAMENTS.md) for
  resume/retry/standings behavior.
- **`replay`** reuses the replay client (`battle_client.cli.main`).
- **`design`** lazily imports `app.agent_designer` only when launched, so
  `--help` and other non-GUI paths never import PySide6.
- **`agents`** reuses `battle_engine.cli.main(["--list-agents"])`.

The legacy `battle-cli` command and `python -m battle_engine.cli`
(`battle_engine.legacy:battle_cli`) continue to use the same engine
argparse entry point as `bytefray run`. `battle-agent-designer`
(`battle_engine.legacy:agent_designer`) is a compatibility wrapper that
lazily imports `app.agent_designer` — see "Desktop application" below.
The v0.1 `match-runner` console-script entry point was removed in v0.3.

### Replay client (`client/src/battle_client`)

`battle_client.cli` reads existing canonical (or legacy-compatible) JSONL
replay streams and an optional sibling `summary.json`, then dispatches to
one of two independent presentation paths:

- `battle_client.player.ReplayPlayer` drives a **renderer** through an
  explicit lifecycle (`setup -> wait_for_start ->
  [wait_until_ready -> on_event -> update]* -> on_complete -> hold_open ->
  teardown`, with `teardown` always run from a `finally` block). Pausing
  and single-step gating happen before delivery of each record, so a
  paused renderer cannot drop records. `HeadlessRenderer` has no Pygame
  dependency; `PygameRenderer` is imported lazily only when selected and
  implements the interactive viewer described in the README (play/pause,
  step, seek, speed control, a runtime-aware HUD, a clickable event
  timeline, and territory/heatmap overlays). `AbstractRenderer` supplies
  no-op interactive/update/completion/hold-open methods so renderers share
  one interface without capability probing.
- `battle_client.session.ReplaySession` is a renderer-independent,
  fully-buffered, seekable cursor over reconstructed engine-observable
  state (arena bytes, ownership, per-entrant `AgentState`, score), built
  only on `battle_engine.replay.iter_replay`. It powers the interactive
  viewer's territory/timeline analysis without rerunning any agent or
  coupling to a specific renderer. `seek` replays forward from tick 0 (or
  incrementally from the current tick) — there is no snapshot/checkpoint
  shortcut for a long match, a documented known limitation.
- `battle_client.analysis` (v0.4 Phase 5) is the one authoritative,
  Pygame-free implementation of the replay-domain facts `PygameRenderer`
  needs: territory ownership (`territory_summary`, `TerritoryHistory`/
  `compute_territory_history`), match event collection/query
  (`collect_match_events`, `events_near_tick`), and selected-arena-cell
  state (`SelectedCellInfo`/`selected_cell_info`). It depends only on
  `battle_client.session`/`battle_engine.replay`, is importable with no
  display and no Pygame installed, and is the module `PygameRenderer`
  itself now calls into rather than maintaining private duplicates — see
  `docs/specs/replay_analysis.md`.

Neither the renderer path nor `ReplaySession` runs the simulation; both
consume only the canonical replay file the engine already wrote. This is
the architectural separation between engine execution
(`NativeMatchService` / `Kernel` / `PythonEntrantController`, which never
read a replay back) and replay consumption (`battle_client`, which never
re-executes an agent).

`client/src/battle_client/renderers/pygame_canvas.py` defines
`PygameCanvas`, a `QtWidgets.QWidget`-embeddable renderer intended to host
Pygame rendering inside a Qt window. **It currently has no callers
anywhere in the repository** — it is not imported by `app/agent_designer.py`,
`app/replay_viewer.py`, or any other module — and is not wired into the
Designer. It exists as unused, unremoved code; do not infer from its
presence that the Designer embeds a live replay view.

### Desktop application (`app`)

`app` is packaged from the repository root rather than a `src` tree and
holds PySide6/Pygame-oriented tools that are adjacent consumers of the
engine, not part of `battle_engine.core`.

- **`app/agent_designer.py` is the actual, sole supported Agent Designer
  entry point.** It is a PySide6 `QMainWindow` application with three tabs
  (Simple, Advanced, and Agent Development) built from `app.services.*` and
  `app.views.*`. Simple/Advanced launch a homogeneous VM-vs-VM or
  Python-vs-Python match; a Tools-menu dialog launches a tournament. The
  **Agent Development** tab (`app/views/development.py`, v0.4 Phase 4a-4c)
  brings the `create → validate → test → replay` authoring loop
  (`docs/specs/agent_designer_workflow.md`) into the GUI: `New Agent` calls
  `battle_engine.agent_scaffold.create_agent` directly in-process (no
  agent-author code runs during scaffolding), while `Validate` and `Test`
  each run `bytefray agents validate`/`bytefray agents test` out-of-process
  via the same `QProcess` machinery — and the same single active-process
  slot — as Simple/Advanced/Tournament, because both execute arbitrary,
  un-timed-out user Python. Their structured `label: value` stdout/stderr
  is parsed by `app/services/agent_workflows.py` (Qt-free) into typed
  presentation dataclasses (`ValidationPresentation`,
  `DevelopmentTestPresentation`) that distinguish an agent-development
  outcome (valid/invalid, completed/initialization-failed) from a
  tool/infrastructure failure; a completed test's winner/termination/replay
  path are read from the exact canonical `result.json` a real match writes,
  not re-derived from CLI text. A development test's own replay is opened
  through the existing `open_pygame_client_direct` launcher but is
  deliberately kept independent of Simple/Advanced's "Open Last Replay"
  target, so switching tabs never repoints that button at a development
  test's replay. It is reached two ways: the `battle-agent-designer`
  console script (`battle_engine.legacy:agent_designer`, which lazily
  imports `app.agent_designer` and calls its `main()`) and `bytefray design`
  (`battle_engine.command._design`, same lazy import). Both reject stray
  arguments and print a usage message for `--help` without importing
  PySide6.
- **`app/replay_viewer.py` is the actual `battle-replay-viewer` entry
  point.** Its `main()` normalizes viewer-friendly arguments (a bare path
  becomes `--replay <path>`, `--renderer pygame` is the default unless
  overridden) and delegates to `battle_client.cli.main`. It is built by
  `tools/replay_viewer.spec` into the `battle-replay-viewer` executable.
- **`app/main.py` is not the active entry point for anything.** Its own
  docstring states that `app/agent_designer.py` and `app/replay_viewer.py`
  "should import" `from app.main import main`, but neither file does —
  both are self-contained and use their own `main()`. `app/main.py` is not
  referenced by any PyInstaller spec, console script, or the
  `battle_engine.command`/`legacy` dispatchers; running it directly opens
  a generic blank Pygame window with no relationship to the Designer or
  replay viewer. It is stale/orphaned source, not an active entry point;
  this task does not delete it (see "Packaging" below for the one
  documentation reference that did incorrectly point at it).
- **`app/match_runner.py` is dead source**, not part of any supported
  entry point or the shipped Windows build (see "Packaging" below).

## Configuration and artifacts

- `engine/config/battle.defaults.json` is a reference defaults file;
  runtime defaults also live in the `Config` dataclass.
- `agents/<name>/agent.yaml` (or `agent.py`, or both) and an optional
  `model.blob` form the agent catalog.
- Every native match writes exactly three sibling artifacts:
  canonical `replay.jsonl` (schema v3), `result.json` (`battle2.result`
  v1, with a SHA-256 digest of the replay), and a compatibility
  `summary.json`. A `redcode94` match writes `summary.json` and
  `result.json` with `replay: null` — no canonical replay stream.
- Historical run output, prebuilt executables, pMARS binaries, and
  `_legacy/` coexist with the active source tree but are not part of the
  current architecture. (A `sdk/` directory of unreferenced early-migration
  examples and an accidental duplicate result bundle previously sat
  alongside these; it was removed in a post-1.0 maintenance pass — see
  `docs/PROJECT_HISTORY.md`.)

## Packaging and commands

The root `pyproject.toml` uses setuptools and discovers packages from
`engine/src`, `client/src`, and the repository root (`app`). Public
commands:

| Command | Target |
|---|---|
| `bytefray` | `battle_engine.command:main` |
| `battle2` (deprecated alias) | `battle_engine.command:battle2_main` |
| `battle-cli` (compatibility) | `battle_engine.legacy:battle_cli` |
| `battle-agent-designer` (compatibility) | `battle_engine.legacy:agent_designer` → `app.agent_designer.main()` |

Windows executables are built by **`tools/build_win.ps1`**, the script CI
actually invokes (`.github/workflows/ci.yml`'s `build-windows-exe` job).
It builds exactly four onedir applications from four PyInstaller specs —
`tools/battle2.spec`, `tools/battle_cli.spec`,
`tools/agent_designer.spec` (→ `app/agent_designer.py`), and
`tools/replay_viewer.spec` (→ `app/replay_viewer.py`) — then runs a
deterministic frozen GUI-import smoke test against `battle2.exe design`
and the standalone Designer. `tools/installer.iss` (Inno Setup) packages
the same four onedir trees beneath `{app}\bin\`.

**`app/match_runner.py` is not shipped.** There is no PyInstaller spec
invoked by `tools/build_win.ps1` or `tools/installer.iss` for it, and its
console-script entry point was removed in v0.3 (see CHANGELOG). Two older
helper scripts, `tools/build_executables.ps1` and
`tools/build_executables_windows.ps1`, and their matching PyInstaller spec
`tools/match_runner.spec`, once could have built it into an executable —
they predated the current four-executable build, were not invoked by CI or
any documented workflow, and would have failed if run because
`app/match_runner.py` calls
`PygameRenderer.setup()`/`.update()`/`.on_complete()`/`.teardown()`,
methods that no longer exist on `PygameRenderer` (see
[`docs/WINDOWS_DEV_NOTES.md`](docs/WINDOWS_DEV_NOTES.md)). All three were
removed in a post-1.0 maintenance pass as confirmed-unreachable leftovers;
`app/match_runner.py` itself is unchanged and remains intentionally
retained dead source (see AGENTS.md's "Architecture boundaries").

Wheels contain Python packages and package-local assets only (see
`[tool.setuptools.package-data]`). Repository-level `agents/` directories
are runtime/user data. pMARS executables, SDK archives, historical
builds, and `third_party_licenses/` are deliberately excluded from the
Python wheel.

## Tests and automation

`pytest.ini` sets `testpaths` to `_legacy/tests`, `engine/tests`, and
`client/tests`, and excludes tests marked `gui` from ordinary headless
runs. `.github/workflows/ci.yml` runs three jobs: `test-linux-core`
(headless suite on Python 3.10–3.13, plus a check that importing
`battle_engine.launchers`/`app.services.engine_commands` never pulls in
`PySide6`/`pygame`), `build-linux-wheel` (build + `tools/check_wheel.py`),
and `build-windows-exe` (`tools/build_win.ps1`). Optional workflows
(`.github/workflows/linux-gui-smoke.yml`,
`.github/workflows/linux-pmars-build.yml`) cover Linux X11/Xvfb GUI
startup smoke and Ubuntu pMARS build/runtime — these are startup checks,
not a substitute for manual interactive testing.

## Dependency direction as implemented

```text
agent manifests/blobs/Python sources + built-ins
              |
              v
      battle_engine.cli ------------------> pMARS (redcode94 only,
              |                              bypasses NativeMatchService)
              | (mode b2)
              v
      battle_engine.tournament_service --\
              |                          |
              v                          v
       battle_engine.match_service.NativeMatchService
              |
    +---------+----------+
    v                     v
 Kernel (VM)      PythonEntrantController
    |                     |
 match -> scoring/statistics -> results
              |
              v
   canonical battle2.replay v3 (replay.jsonl)
   + battle2.result v1 (result.json)
   + compatibility summary.json
              |
              v
   battle_client (ReplayPlayer + renderers, or ReplaySession)
              |
              v
      app.replay_viewer / app.agent_designer
```

The extracted low-level dependency direction remains acyclic:

```text
config                 instructions     agent_state
                            \              /
                             \            /
                                  vm
                         \       |       /
                          \      v      /
                           core (Kernel facade)
                                  |
                         MatchRunner / NativeMatchService
```

`config`, `instructions`, and `agent_state` use only the standard library.
`vm` depends on `instructions` and `agent_state`; none imports `core`.

## Application roots

`battle_engine.paths` is the shared root-resolution boundary.
`BYTEFRAY_ROOT` is the preferred writable-data-root environment variable;
`BATTLE2_ROOT` and then `BATTLE_ROOT` are checked, in that order, as
deprecated fallbacks. The application *resource* root is separate: source
checkouts use the repository root, installed packages use package-local
resources, and frozen applications use PyInstaller's `_MEIPASS` extraction
directory for read-only bundled files — `_MEIPASS` is never a writable
data root. Without an explicit root, a frozen portable application writes
beside its executable; the Windows installer sets both `BYTEFRAY_ROOT` and
`BATTLE2_ROOT` to `%ProgramData%\BATTLE2` (kept under the legacy name for
upgrade continuity with existing installs). A regular installed Windows
wheel defaults to `%LOCALAPPDATA%\BATTLE2`; a regular installed Linux
wheel uses `$XDG_DATA_HOME/battle2` or `~/.local/share/battle2`.

`battle_engine.launchers` owns child command construction for both the
Designer and any other launcher of a match/replay subprocess. Frozen
applications resolve sibling `.exe` files beside the current executable
(the installer's onedir sibling-folder layout); source/editable checkouts
invoke the current Python interpreter. Commands are always argument lists,
never shell strings.

## v0.4.0 delivery history

v0.4's primary theme is **Agent Authoring & Development Feedback Loop**:
tightening the loop an agent author works in, from writing an agent to
seeing how it performs. The delivered user journey is:

**create → validate → test → inspect → modify → repeat**

This section records how that loop was delivered, phase by phase, across
the v0.4.0 release. Phase 0 (documentation/packaging hygiene) landed no code. Phase 1
(`docs/specs/agent_scaffold.md`) added `bytefray agents create <agent-id>`,
which scaffolds a minimal Agent API v1 Python agent from a bundled
`battle_engine/data/agent_template/` resource. Phase 2
(`docs/specs/agent_validation.md`) added `bytefray agents validate
<agent-id>`, a single-tick dry run of the Agent API v1 contract reusing the
production loader/action-validator. Phase 3
(`docs/specs/agent_test.md`) added `bytefray agents test <agent-id>`, a
short (200-tick default), deterministic real match run through the exact
`NativeMatchService` boundary against either an internal reference Python
opponent (built from the same Phase 1 template resource, loaded directly
from the package resource directory and never copied into the user's
`agents/` catalog) or an explicit `--opponent <agent-id>`; it writes the
same canonical `replay.jsonl`/`result.json`/`summary.json` artifacts any
other native match writes, under `<data_root>/runs/agents_test/<agent-id>/
<run-label>/`. A tested agent's own forfeit, death, or loss within a
completed match is still a successful evaluation (exit `0`); only a
tool/infrastructure failure — an unknown or non-Python agent/opponent, or
the internal bundled reference opponent failing to initialize — is exit
`2` (an explicit `--opponent`'s own initialization failure is exit `0`
too, for the identical reason: it is user-provided agent code being
evaluated by the test, exactly like the tested agent itself). Phase 4
(`docs/specs/agent_designer_workflow.md`; Phase 4a-4c landed) brought this
same loop into the PySide6 Agent Designer as a third "Agent Development"
tab — see the Desktop application section above for how Validate/Test are
wired through the existing `QProcess`/single-active-process machinery
without forking any Phase 1-3 semantic. Phase 4d (integration polish,
documentation, and frozen-app verification) completed that tab. Phase 5
(`docs/specs/replay_analysis.md`) is supporting architectural work, not a
further step in the create → validate → test → inspect → modify loop
itself: it extracted the replay-domain facts `PygameRenderer` already
computed (territory ownership/history, match events, selected-cell state)
into the headless `battle_client.analysis` module described above, and
migrated the renderer to consume it. Phase 6 (final hardening and release)
closed out v0.4 as the tagged `v0.4.0` release described throughout this
document. Do not treat any further feedback-loop tooling described in
future specs under `docs/specs/` as already built until it lands and this
document is updated to describe it.

## Agent Lab (v0.5.0)

Delivered in the v0.5.0 release; see `docs/specs/agent_lab.md` for the
full design. Where v0.4 built create → validate → test → replay, Agent
Lab attacks inspect → debug → modify → repeat: deterministic behavioral
tracing of the Python Agent API boundary, and development-time hang
containment for a `reset()`/`act()` call that never returns.

`battle_engine.agent_trace` defines `bytefray.agent_trace` v1, a
separate, versioned JSONL artifact independent of `battle2.replay`/
`battle2.result` — one record per `reset()`/`act()` call attempt
(Observation, AgentAction or diagnostic, wall time). `MatchRequest`
(`battle_engine.match_service`) gains two independently optional fields,
`trace_path` and `agent_call_timeout`, both defaulting to `None`; `bytefray
run` and the tournament service never set either, so their code path is
the unmodified v0.4.0 `PythonEntrantController`. `bytefray agents
test`/`agents validate` set both by default at their CLI entry points
(library callers keep an unsupervised, untimed default for backward
compatibility with existing programmatic callers/tests).

When `agent_call_timeout` is set, `battle_engine.supervised_runtime.
SupervisedPythonEntrantController` replaces the in-process controller:
one whole-match-lifetime worker subprocess per Python entrant
(`battle_engine.agent_worker`, spawned via the existing
`launchers.build_agents_command` pattern through a hidden `agents
_worker` verb — no `multiprocessing`, no new executable) owns that
entrant's `load`/`reset`/`act` calls; the parent still owns the arena and
applies every action, so execution semantics are unchanged, only
production is relocated. A newline-delimited-JSON protocol over the
worker's stdin/stdout, read via a dedicated per-worker reader thread and
a bounded `queue.get(timeout=...)`, gives every call a timeout on both
Windows and POSIX. A stalled call reports a new diagnostic
(`agent_load_timeout`/`agent_reset_timeout`/`agent_action_timeout`/
`agent_worker_exited`/`agent_worker_protocol_error`, reusing the existing
`RuntimeDiagnostic` shape) and forfeits that entrant exactly as an
equivalent in-process exception already did.
`battle_engine.process_containment` ties each worker's lifetime to its
parent (a Windows Job Object / POSIX `PDEATHSIG`) so a worker stuck in a
hung call cannot outlive a parent that is itself force-killed. This is
development-time hang **containment**, not a security sandbox — worker
code runs with the same OS privileges as the parent.

`battle_engine.agent_inspect` (`bytefray agents inspect`/`agents
diverge`) and the Designer's `TraceInspectorDialog`
(`app/views/trace_inspector.py`, reached from a new "Inspect Trace"
button on the existing Agent Development tab) both read an
already-written trace file and execute no agent code, so neither needs a
timeout or process boundary. `runs/agents_test/<agent-id>/<run-label>/`
gains an optional `trace.jsonl` fourth file alongside the existing
`replay.jsonl`/`result.json`/`summary.json` — additive only.

## Agent Evaluation (v0.6.0)

Delivered in the v0.6.0 release; see `docs/specs/agent_evaluation.md`
for the full design. Where v0.4
built create → validate → test → replay and v0.5 built inspect → debug →
modify → repeat, Agent Evaluation adds the step after "modify": did this
candidate actually get better?

`battle_engine.agent_evaluation.EvaluationService` is a new, headless
orchestrator sibling to `TournamentService` — both sit over
`NativeMatchService`, but schedule genuinely different experiment shapes.
A tournament schedules a symmetric round-robin among peers; an evaluation
schedules a candidate (and optional baseline) each playing an explicit,
author-chosen opponent/seed matrix, with literal (never re-derived)
seeds, so any cell is directly reproducible. `EvaluationService` does not
wrap or extend `TournamentService` — it reuses `agent_test.test_agent`
itself as its per-cell executor (a small, additive `run_dir` parameter on
`test_agent` lets the evaluation service place each cell's artifacts
under its own `matches/` tree), so every evaluation cell is executed by
the exact same code path `bytefray agents test` uses standalone, and a
cell's reproduction command is always exactly `bytefray agents test
<subject> --opponent <opponent> --seed <seed> --ticks <ticks>`.

Per-cell outcomes are classified into `win`/`loss`/`tie` (a real
completed match — forfeits are already folded into these via the
existing `winner` field, same as any other match), `subject_init_failed`/
`opponent_init_failed` (a pre-tick-zero initialization failure of either
side — a valid evaluation outcome, not a tool failure, since no
`result.json` exists to aggregate), or `failed` (a genuine
infrastructure/tool error, excluded from all aggregation). A
candidate-vs-baseline comparison classifies each matched `(opponent,
seed)` cell `improved`/`regressed`/`unchanged` using only the engine's
own `win > tie > loss` outcome rank — score and territory are reported
alongside every cell as supporting data but never independently produce
that classification, deliberately avoiding both an opaque single
"strength" number and an unjustified secondary ranking across dimensions
`scoring.py`/`RESULT_SCHEMA.md` do not themselves treat as ordered.

The evaluation artifact, `evaluation.json` (`bytefray.evaluation` v1,
following the newer `bytefray.*` schema-naming precedent
`bytefray.agent_trace` established rather than the pre-rename `battle2.*`
canonical-protocol namespace), is additive and independently versioned:
it references each cell's canonical `replay.jsonl`/`result.json` by
relative path rather than duplicating their content, and is written with
the same atomic-JSON-checkpoint discipline (`result_model.
write_json_atomic`) `tournament.json` already uses. Resume reuses
`TournamentService`'s verified-trust resume pattern, adapted to one
cell's two-entrant shape: a recorded `completed` cell's `result.json` is
trusted only after its entrant order, seed, `match_id`, and replay digest
are all re-verified against what the scheduled cell expects; a mismatch
demotes it to `corrupted` rather than being silently trusted or silently
re-run.

`bytefray agents evaluate` (`battle_engine.agent_evaluation.main`, wired
through `command.py`'s existing `agents` dispatch) always runs
unsupervised and untraced — the intended workflow is bulk evaluation
first, then a single, targeted `bytefray agents test`/`agents inspect`
rerun of exactly the cell that looks interesting, reusing Agent Lab's
existing tracing/inspection machinery unmodified rather than adding a
second one. The Designer's Agent Development tab gains an "Evaluate…"
button (`app/views/evaluation.py`'s `EvaluationDialog`) that launches the
same CLI out-of-process (the existing `QProcess`/single-active-process
machinery, since evaluation runs arbitrary user Python) and, on
completion, a read-only `EvaluationResultsDialog` reading the canonical
`evaluation.json` (`app/services/designer_workflows.
read_evaluation_presentation`) with two drill-down actions on a selected
cell: rerun it through Agent Lab (reusing the existing
`TraceInspectorDialog` unmodified) or open its replay.

Evaluation is Python-agent-only in v0.6, inheriting `agents test`'s
existing Python-only requirement by construction (its per-cell executor
*is* `agents test`) rather than introducing a second, VM-flavored
executor — VM/blob agents remain comparable via `bytefray tournament`.

## Default Agent Build-Out (v0.6.1)

Delivered in the v0.6.1 release. Where v0.3–v0.6 built the authoring,
debugging, and evaluation *tools*, v0.6.1 addresses first-run *content*:
before v0.6.1, the only Python (Agent API v1) agent behavior a new user
ever saw was `battle_engine/data/agent_template`'s scaffold/reference
agent — a single fixed byte written to a uniformly random address in the
first 256 bytes of the arena — reused unmodified as both `bytefray agents
create`'s starting point and `agents test`'s default opponent. Two
identical copies of it playing each other are then decided almost purely
by which one is scheduled second within a tick (Python-only matches
execute entrants in fixed slot order, A before B, every tick — see
`battle_engine.python_runtime.PythonEntrantController.run`), not by
strategy. `bytefray agents` also had no Python starters at all: the four
existing native VM starters (`runner`/`writer`/`seeker`/`spiral`,
`battle_engine.starters`) never included a Python entrant a new user could
run, read, or copy.

`battle_engine.starters.STARTER_AGENT_NAMES` gained five entries —
`claimer`, `strider`, `hunter`, `wanderer`, `adaptive` — each a full
Agent API v1 agent (`agent.yaml` + `agent.py`) bundled under
`battle_engine/data/starter_agents/<name>/`, discovered and copied into
the writable catalog by the same `ensure_starter_agents()` non-destructive
mechanism the native VM starters already use; no new discovery, catalog,
or packaging concept was introduced; `[tool.setuptools.package-data]`'s
existing `battle_engine = ["data/**/*"]` glob already covers the new
subdirectories. Each agent's module docstring is a self-contained
explanation of its strategy, the state it tracks, and (for several of
them) what an earlier, less successful version tried and why it was
retuned — see each `agent.py` under `battle_engine/data/starter_agents/`
for specifics, and the README's "Try the bundled agents" section for the
user-facing summary and example `agents evaluate` invocations.

The design was driven entirely by `bytefray agents evaluate` against the
engine's actual scoring mechanics (`battle_engine.scoring.ScoringPolicy`,
`battle_engine.python_runtime`), not assumption, through many iterative
rounds. Claimer — a disciplined, uninterrupted blind sweep, never reading,
never stopping — was treated as the fixed strong-baseline strategy
throughout; the rest of the portfolio was designed and repeatedly retuned
around it rather than by weakening it. Several findings shaped every
shipped agent's final form:

- Because `Observation` exposes no ownership map (only a raw byte value
  via `READ`) and a first-time `WRITE` to any cell is never wasted
  regardless of what was there before, reading a cell before claiming it
  only pays for itself once genuinely revisiting already-owned ground is
  common — within `agents test`/`evaluate`'s typical tick budgets against
  the default 4096-byte arena, blind full-arena coverage essentially
  never reaches that point. Several candidate designs that read before
  every write, at any frequency above a low, occasional sampling rate,
  measured worse than agents that simply wrote every action.
- Two entrants sweeping with the *same* stride are walking the same
  cyclic sequence of addresses, just entered at the same or a different
  point. This looks harmless but is not: whichever one's writes to a
  shared cell land later in real tick time wins that cell every time, so
  an agent whose stride happens to match another's — even coincidentally,
  even in an otherwise well-designed agent — can end up either trivially
  dominating or trivially losing to it for reasons that have nothing to
  do with either one's actual strategy. This surfaced three separate
  times during development (Hunter's dense sweep initially reused
  Claimer's stride and became a strict superset of it; Strider's rolling
  defense initially reused Claimer's stride and won every contested cell
  by construction; Strider's replacement stride then coincidentally
  matched Adaptive's). Every shipped agent now uses a distinct stride from
  every other, and the module docstrings note the failure mode explicitly
  so a reader extending this pattern doesn't reintroduce it.
- Score accumulates every tick a cell is owned, and there is no combat —
  only overwrite-based denial. An opponent that never stops expanding
  eventually sweeps through nearly the whole arena and, because a
  candidate's writes are scheduled before its opponent's every tick (see
  `agent_test.TESTED_AGENT_SLOT`/`OPPONENT_SLOT` and the Python scheduling
  order above), wins any cell it reaches after the candidate already
  claimed it. Consequently, any strategy that pauses or bounds its own
  expansion — to patrol a fixed region, to read before writing, to hold a
  phase that stops claiming new ground — cedes ground over the course of
  a full match to one that simply never stops. This is almost certainly a
  fact about the current scoring model rather than a tuning mistake in
  any one agent; see "Known Limitations" in the CHANGELOG for why it is
  recorded here rather than addressed in this release.

Two prototypes were built, retuned across several evaluation passes each,
and not shipped as a result of the third finding above. `sentinel` (a
reactive defender patrolling a growing home range, using the engine's P
register as its patrol pointer) never exceeded a small fraction of the
arena regardless of starting size, anchor placement, or expansion policy.
An early version of `hunter` (a scanner that read for contested ground and
burst-attacked it) lost consistently for the same underlying reason before
being redesigned into its shipped form (an early wide dispersal followed
by dense fill-in, always writing, never reading more than occasionally).
Neither rejected version's source was committed. Adaptive is the one
shipped agent that still deliberately pauses expansion (its `CONTEST` and
`DEFEND` phases), specifically to demonstrate the engine's `PC`/`JUMP`
actions as a phase state machine; it is, honestly and by design, the
weakest of the five bundled agents — evaluation puts it at 0% against the
other four in both the development and held-out seed matrices — kept for
that demonstration value rather than for competitiveness (see its own
module docstring for the full reasoning). The final development-matrix
standing across the five shipped agents: Claimer and Hunter each win
around three-quarters of their matches (Hunter loses only to Claimer),
Strider is close to even, Wanderer wins roughly a quarter, and Adaptive
wins none — real matchup texture rather than a single dominant agent,
while still leaving Claimer as the strongest performer throughout.

`engine/tests/test_default_python_agents.py` adds structural coverage for
the new roster — clean discovery as `kind: python`, successful validation,
successful match completion against the reference opponent, and a
behavioral smoke matrix (every shipped agent against every other) — all
asserting only that matches complete without infrastructure failure, never
that a particular agent wins a particular seed (see AGENTS.md's testing
guidance). `engine/tests/test_starter_agents.py`'s file-count assertions,
previously hard-coded to the single-file (`agent.yaml`-only) shape every
native VM starter happens to have, were generalized to compute the
expected file set from each starter's actual source directory, since the
Python starters are the first starters to ship more than one file
(`agent.yaml` and `agent.py`).

## Evaluation History (v0.7)

Delivered in the v0.7 release; see `docs/specs/evaluation_history.md` for
the full design. Where v0.6 answered "did this candidate beat this
baseline, right now," v0.7 makes a single evaluation's capture honest
enough to trust in isolation, and adds the ability to compare *across*
separately-run evaluations after the fact, without rerunning anything.

**Capture hardening.** `battle_engine.agent_evaluation`'s writer now
produces `bytefray.evaluation` **v2** (`SCHEMA_VERSION = 2`) by default.
Beyond v1's fields, v2 persists: a readable planned identity
(`agent_identity()`-shaped) for the candidate, the baseline (if any), and
every opponent occurrence in request order; `EffectiveConditions` — every
behavior-relevant `Config` field (arena size, action budget, win mode,
weights, tick limit), not just seed — plus an `effective_conditions_fingerprint`;
a narrow, hand-maintained `EVALUATION_RULES_COMPATIBILITY_ID`, separate
from `ProjectInfo.version`, bumped only when scoring/winner-resolution/
Python-scheduling-order/derived-seed semantics actually change;
`created_at`/`updated_at`/`finished_at` UTC lifecycle timestamps (the
first checkpoint, with `created_at` set, is written before any cell
executes, so a crash during cell 1 still leaves discoverable state); an
`execution_contexts` list recording which `ProjectInfo`/rules-compatibility
environment each freshly executed cell actually ran under (a no-op resume
never appends to or rewrites this list); and four duplicate-occurrence
coordinates per cell (`opponent_index`, `seed_index`, `matrix_ordinal`,
`condition_occurrence_index`) that survive candidate-source changes across
evaluations and are what cross-evaluation alignment uses -- never
`schedule_id`, which keeps its v1 role as an evaluation-local resume/
Designer-drill-down key only.

`evaluation_id` remains a deterministic plan identity (never a run
occurrence, output path, timestamp, or outcome), computed with the
`stable_id("evaluation-v2", ...)` prefix so a v2 id can never be mistaken
for a v1 id computed from otherwise-identical inputs. Because the v2
identity payload is strictly richer than v1's, a v0.6.1 evaluation
directory is never implicitly resumed by an equivalent v0.7 invocation —
a new v2 artifact is produced at a new, v2-identity-derived path, and the
old v1 artifact is left untouched.

**Source drift protection.** `EvaluationService._execute_cell` re-resolves
the subject and opponent immediately before every freshly executed cell
and compares each identity against a snapshot frozen at the start of the
run (never re-derived from a live `AgentSpec.source_path`, which would
silently defeat the check by reading whatever the file currently contains
on both sides of the comparison). After execution, `_post_execution_identity_drift`
compares the frozen planned identity against the identity the *executor
itself* recorded on `NativeAgentResult.metadata` — never a second,
independent disk read by this module, which a running agent's own edit
could equally observe and thus pass despite drift. The required invariant
(v0.7 closure pass) is three-way: the executor's load-time
`local_source_fingerprint`, the frozen planned fingerprint, and the
executor's post-match `local_source_fingerprint_final` (covering lazy
imports a running agent performed after load) must all agree. The first
detected drift (pre-execution or post-execution) stops the matrix
immediately: no further cells are scheduled, every already-completed cell
is preserved, the drifted cell itself is retained with
`status: "drift_detected"` for diagnosis, and the final checkpoint sets
`lifecycle_state: "aborted"`, `abort_reason: "source_drift"` with no
`finished_at`. A fresh evaluation (implied automatically, since the
changed source now hashes to a different `evaluation_id`) is required to
continue. This detects durable source changes only: it fingerprints
agent-local Python source, not imports/dependencies outside the agent's
own directory, and a transient edit-and-restore within the same
fingerprinting window can still escape detection — see
`docs/specs/evaluation_history.md` §7 for the full residual-limitation
discussion.

**`battle_engine.evaluation_history`** is a new, Qt-free package
(`models.py`, `v1_adapter.py`, `v2_adapter.py`, `discovery.py`,
`comparison.py`, `cli.py`) that depends only on
`battle_engine.{agent_evaluation,agents,config,paths,project_info,
result_model,replay}` and never imports Qt/pygame/Designer code. Its
common domain model (`EvaluationSummary`, `AdaptedCell`, `HealthReport`,
...) wraps every field that might be absent from a legacy artifact in a
`ConfidenceValue` (`recorded`/`recovered`/`unknown`/`conflicting`/
`verified`) rather than silently defaulting it. The v1 adapter never
mutates a v1 artifact and never treats current agent discovery as
historical evidence; it also establishes, by direct inspection of what
`match_service`/`result_model` actually persist, that v1's canonical
`result.json` never wrote `api_version`/`agent_version`/`source_sha256`
anywhere retrievable (those fields are hashed transiently into `match_id`
and discarded) — so v1 candidate/baseline/opponent executable-identity
recovery is honestly reported `UNKNOWN`, not fabricated. Both adapters
always recompute aggregates from cells via the existing
`agent_evaluation.aggregate_cells`/`compare_candidate_baseline` rather than
trusting a stored `aggregates`/`comparison` block, so a tampered or
missing stored summary can never override canonical cell state.

Discovery (`discover()`) performs shallow, non-recursive, one-level scans
of `<data-root>/runs/evaluations/*/evaluation.json` by default (or
explicit roots/paths); one malformed/unsupported sibling is reported as
its own entry with a typed `HealthCode` rather than aborting the scan.
Moved evaluation directories remain usable (every artifact reference is
relative); copied directories sharing an `evaluation_id` are flagged as
duplicate *locations*, never presented as separate execution occurrences.

Comparison (`align(left, right)`) is always oriented "right relative to
left." It deliberately excludes candidate identity from the shared
condition key (opponent identity, seed, effective conditions, rules
compatibility, duplicate occurrence index) since the candidate is the
experimental variable being compared, not a condition to hold fixed; an
unknown required dimension on either side never compares equal to
anything, including another unknown. Verdicts reuse `win > tie > loss`
only (`improved`/`regressed`/`unchanged`/`inconclusive`) and every
denominator (matched, unmatched, changed-condition, ambiguous-duplicate,
corrupt/missing) is always populated, even at zero. An identical,
`--verify`-checked candidate fingerprint with differing deterministic
outcomes is flagged as a `reproducibility_anomaly` rather than silently
labeled improved/regressed.

`bytefray agents evaluations list|show|compare` (`evaluation_history.cli`)
is wired into `command.py`'s existing `_agents` dispatch (reached
identically through the `battle2` alias) alongside `evaluate`/`test`/
`validate`/`inspect`/`diverge`. `show --verify`/`compare --verify` perform
canonical `verify_result_replay` digest checks only for the selected
artifact(s), never during default `list`, keeping on-demand scanning fast
regardless of how many evaluations exist — no index was introduced or
found necessary.

Two narrowly scoped, evaluation-specific Designer defects (not the history
UI itself, which is deferred — see `docs/specs/evaluation_history.md`
Sec 17/20) were fixed: `app.services.agent_catalog.AgentRow` now carries
an `agent_id` field (the discovery id, `spec.name`) distinct from `name`
(the display name, `spec.display`); `AgentDevelopmentPanel.python_agent_names()`
and `EvaluationDialog` thread that id through so `bytefray agents evaluate`
always receives discovery ids, never display text, even when they differ.
`AgentDesigner._on_evaluate` no longer defaults every plan's output to one
fixed `runs/evaluations/designer-evaluation` path; it calls
`EvaluationService.preflight` in-process (Qt-free, no agent code executes)
to compute this specific plan's own content-addressed default, matching
what a bare CLI invocation would use, only when the user hasn't typed a
different path themselves.

## Agent Revision & Provenance (v0.8)

Delivered in v0.8; see `docs/specs/agent_revision.md` for the full design.
v0.7 gave an evaluation honest *identity* (§7 above); v0.8 gives an agent's
exact source at that identity's freeze point a durable *copy*, so history
stays meaningful after the live source keeps changing — closing v0.7's own
recorded "Known Limitations" gap (no historical copy is kept, only
identification).

**`battle_engine.agent_revisions`** is a new, self-contained, Qt-free
module — deliberately *not* built on top of `agent_api.local_source_
fingerprint` (a real pre-3.13 symlink-traversal inconsistency in that
function's own `rglob` walk would otherwise have been silently inherited;
see the spec §2.1 for the full argument). It provides: a canonical
tree-walk (`walk_agent_files`) that includes every regular file under an
agent directory except `__pycache__`/`.git`, dereferences an internal file
symlink, and never traverses a directory symlink/junction in either
direction, explicitly recording every omission (external target, broken
link, unreadable file, resolve error) rather than silently dropping it; a
versioned, full-64-hex-digest content fingerprint over that walk's
included bytes *and* its omission evidence (`agent_revision_fingerprint`/
`agent_revision_id`) that is a strictly wider, separate value from
`local_source_fingerprint` and is never folded into `evaluation_id` or
`agent_identity()` — revision identity, evaluation-plan identity, and
drift-detection scope stay three independent axes; and a content-addressed
store under `<data_root>/agent_revisions/` with atomic temp-then-`os.replace`
publication that is verified (fingerprint reconstructed from the written
bytes) *before* being promoted to its canonical path, so a case-insensitive
store collision or an interrupted write can never result in a canonical
directory whose contents don't match its own name.

**Freeze-time integration.** `EvaluationService.run()` archives every
distinct candidate/baseline/opponent agent's revision immediately after
`planned_identities` is computed and before `evaluation_id`/`matrix`/any
checkpoint — never lazily on first cell execution, which would let the
live tree drift between the plan's own read and the archive's. A
freeze-time cross-check (the archival walk's own `.py`-subset fingerprint
against the plan's already-recorded `local_source_fingerprint`) must
agree; a mismatch aborts the whole run with no `evaluation.json` written
at all, before any cell executes. A revision-store *write* failure (disk
full, permissions) is non-fatal and recorded as `agent_revision_error` on
the evaluation artifact — new, additive infrastructure must not take down
evaluation itself. `bytefray.evaluation` bumped to **schema v3**
(`IDENTITY_VERSION` unchanged — nothing about what `evaluation_id` hashes
changed) with one wholly separate, additive top-level `agent_revisions`
sibling field to `planned_identities`, deliberately never merged into it
(an earlier implementation attempt that did merge them broke the existing
"recomputing `evaluation_id` from the persisted `planned_identities`
reproduces the stored value" invariant). v1 and v2 artifacts remain fully
readable, are never mutated, and are honestly reported as having `UNKNOWN`
revision provenance rather than a guessed value.

**`evaluation_history` integration.** `AdaptedCell`/`EvaluationSummary`
gained revision-id/archive-error/verification fields following the same
per-role-once-per-cell-for-opponents pattern already used for identity
fields, each wrapped in the existing `ConfidenceValue` machinery — a
malformed `agent_revisions` entry for one role degrades only that field to
`UNKNOWN`, never destroys a sibling role's data or aborts the artifact.
`verify_summary` (used by `show --verify`/`compare --verify`) gained local
revision-store evidence, distinguishing four states that must never be
conflated: not checked, not available (no local snapshot — never reported
as corruption), invalid (a present snapshot that fails to verify — the one
state that fails overall verification), and verified. This check consults
only the revision store, never live agent source.

**CLI.** `bytefray agents revisions list <agent-id>|show <revision-id>|
restore <revision-id> [--to <dir>] [--force]` (`agent_revisions_cli.py`),
wired into `command.py`'s `_agents` dispatch alongside `evaluate`/
`evaluations`/`test`/`validate`. `list`'s relevance filter is source_agent_id
match *or* a live fingerprint match against the agent's current on-disk
content (content-addressed dedup means the recorded, purely informational
`source_agent_id` can legitimately name a different agent than one whose
current content matches). `restore` never touches `agents/<id>/` implicitly,
refuses a non-empty target without `--force`, and — found and fixed during
this integration — now fails closed (nothing written) if the canonical
snapshot itself doesn't verify, rather than only checking containment on
the manifest-declared paths. Rerunning a historical revision is
compositional: `restore` writes plain files to an explicit target, and the
existing `agents test`/`agents evaluate`/`agents validate` commands operate
on that directory like any other agent folder — no second, revision-aware
execution path.
