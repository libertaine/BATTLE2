# Bytefray Architecture

This document describes Bytefray's architecture as of the v0.4.0 release
(NativeMatchService, Agent API v1 Python-vs-Python matches, canonical
`battle2.replay` schema v3, the headless tournament service, and the
`bytefray agents create/validate/test` authoring commands plus the
Designer's Agent Development tab added in v0.4). It supersedes the
v0.2-era architecture document; that superseded text remains available in
git history (see the `v0.2.0` tag) and in
[`docs/V0_2_MIGRATION.md`](docs/V0_2_MIGRATION.md) for migration context.
This document describes what exists today (see "v0.4 direction" at the end
for how the current agent-authoring functionality was delivered in phases).

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
- Historical run output, prebuilt executables, pMARS binaries, SDK
  examples, and `_legacy/` coexist with the active source tree but are
  not part of the current architecture.

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
console-script entry point was removed in v0.3 (see CHANGELOG). The only
references that would build it into an executable are two older helper
scripts, `tools/build_executables.ps1` and
`tools/build_executables_windows.ps1` — both predate the current
four-executable build, are not invoked by CI or any documented workflow,
and would fail if run today because `app/match_runner.py` calls
`PygameRenderer.setup()`/`.update()`/`.on_complete()`/`.teardown()`,
methods that no longer exist on `PygameRenderer` (see
[`docs/WINDOWS_DEV_NOTES.md`](docs/WINDOWS_DEV_NOTES.md)). `tools/match_runner.spec`,
the PyInstaller spec for it, is likewise not referenced by any build
script CI runs. Because none of these three files are part of the actual
release build surface today, none were changed as part of this cleanup;
whether to delete them as unreachable leftovers is left for a human
decision rather than treated as implied by this audit.

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

## Agent Lab (v0.5, unreleased)

Development branch (`v0.5-agent-lab`) work, not yet released; see
`docs/specs/agent_lab.md` for the full design. Where v0.4 built
create → validate → test → replay, Agent Lab attacks
inspect → debug → modify → repeat: deterministic behavioral tracing of
the Python Agent API boundary, and development-time hang containment for
a `reset()`/`act()` call that never returns.

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
