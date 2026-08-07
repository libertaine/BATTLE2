# BATTLE2 v0.2 Architecture

This document records the released v0.2.0 architecture while
retaining clearly identified v0.1 compatibility boundaries. Some responsibilities
overlap and historical code remains in the repository. Migration history is in
[`docs/V0_2_MIGRATION.md`](docs/V0_2_MIGRATION.md).

## Runtime components

### Engine package (`engine/src/battle_engine`)

`battle_engine.core` remains the primary public compatibility surface and owns
the `Kernel` facade and its established mutable attributes. Match responsibilities
now delegate to focused services:

- `battle_engine.match.MatchRunner` owns tick scheduling, instruction quotas,
  termination, and the established per-tick operation order.
- `battle_engine.scoring.ScoringPolicy` owns alive, territory-bucket, and kill
  point application without executing instructions.
- `battle_engine.statistics.StatisticsCollector` owns in-memory counters and
  territory accumulation without persistence.
- `battle_engine.results` owns winner resolution and persistence-neutral summary
  construction.
- `battle_engine.telemetry` defines replay/summary sink protocols, the v0.1 JSONL
  publisher, JSON summary adapter, and legacy renderer boundary adapter.

`Kernel.run()` delegates scheduling to `MatchRunner`, resolves/builds the result,
and preserves its direct-caller compatibility summary through an injectable
`SummarySink`. CLI callers inject a null sink and persist only the canonical
replay-adjacent summary. `JSONLSink` is re-exported from `core`. Lower-level
implementations remain extracted:

- `battle_engine.config` owns the mutable `Config` and `Weights` dataclasses.
- `battle_engine.instructions` owns byte-oriented ISA constants and `enc`.
- `battle_engine.agent_state` owns the mutable execution-time `Agent` state.
- `battle_engine.vm` owns circular arena memory, ownership, instruction decoding,
  wrapping behavior, and per-tick memory differences.

`core` imports and re-exports these names, so existing imports such as
`from battle_engine.core import VM, Config, Weights, Agent, enc` resolve to the
new implementation objects without duplicate compatibility classes.

The VM supports `NOP`, `MOV`, `ADD`, `LOAD`, `STORE`, `JMP`, `JZ`, `HALT`,
`MOVP`, `ADDP`, `LOADI`, and `STOREI`. Values encoded by `enc` use one opcode byte
and, where applicable, a four-byte little-endian immediate.

`battle_engine.builtins` assembles the native `runner`, `writer`, `bomber`,
`flooder`, `spiral`, and `seeker` programs into VM bytecode.

`battle_engine.replay` defines the canonical, standard-library-only v0.2 replay
contract. Frozen dataclasses model headers, match configuration, agent state,
memory differences, tick snapshots, engine events, and match results. The module
also owns JSON serialization, validation, JSONL streaming, and conversion from
supported v0.1 native and legacy event records. The detailed wire contract is in
[`docs/REPLAY_SCHEMA.md`](docs/REPLAY_SCHEMA.md).

`battle_engine.agents` discovers directories below `agents/`. A directory is
valid when it has `agent.yaml` or `agent.py`. Despite its name, `agent.yaml` may
contain JSON; YAML syntax is supported when PyYAML is installed. The resolver
recognizes an optional `model.blob`, display metadata, and default parameters.
The current CLI executes blobs and built-ins; it detects `agent.py` but does not
load Python agent code itself.

`battle_engine.starters` validates the canonical Runner, Writer, Seeker, and
Spiral manifests bundled under `battle_engine/data/starter_agents`, then copies
only missing files into the writable `get_data_root()/agents` catalog. It reads
resources through `get_resource_root()`, never writes into `_MEIPASS`, and uses
exclusive file creation so user edits and custom agents remain untouched.

### Engine CLI (`battle_engine.cli`)

The primary `battle2` command and `python -m battle_engine` dispatch to four lazy
subcommands: `run`, `replay`, `design`, and `agents`. `run` reuses
`battle_engine.cli.main(argv)` directly, `replay` reuses the replay client,
`agents` reuses engine discovery, and `design` imports the optional PySide6 app
only when launched. Help paths therefore require no GUI dependencies.

The legacy `battle-cli` command and `python -m battle_engine.cli` continue to use
the engine argparse entry point. The engine CLI:

1. resolves configuration and agent parameters from flags and environment;
2. resolves agent slots in this order: `BATTLE_AGENTS_JSON`, direct blob flag,
   discovered agent, built-in agent;
3. runs either the native B2 `Kernel` or an external pMARS process for
   `redcode94` mode; and
4. writes match artifacts.

The v0.1 native replay is newline-delimited JSON. Its first record is a version 6
header containing configuration, followed by one snapshot per executed tick.
Each snapshot contains agent state, score, events, and memory ownership diffs.
The CLI writes one sibling `summary.json` with schema version 2. Its default
replay is `<data-root>/runs/_loose/replay.jsonl`; explicitly supplied relative
paths remain relative to the current working directory. Direct `Kernel` callers
retain the injectable compatibility summary sink.

The external pMARS mode writes a version 2 summary but no native replay stream.
Executable discovery and execution are owned by `battle_engine.pmars`. It keeps
commands as argument lists, resolves read-only packaged files through the
resource root, supports installer/portable files beneath the writable layout,
and normalizes missing, timeout, process-exit, and output-parsing failures before
they reach either the CLI or a GUI-launched engine subprocess.
The v0.1 engine writer remains active in this migration phase; canonical v0.2
writing is available through `battle_engine.replay.write_replay` but is not yet
wired into `Kernel` or the CLI.

### Replay client (`client/src/battle_client`)

`battle_client.cli` reads existing JSONL streams and optionally reads a sibling
`summary.json`. `battle_client.utils` delegates replay parsing to
`battle_engine.replay`, so renderers receive only canonical `ReplayRecord`
dataclasses. It also normalizes historical summary metadata locations before
renderer setup. `battle_client.player.ReplayPlayer` owns replay iteration and the
explicit presentation lifecycle:

```text
setup -> wait_for_start -> [wait_until_ready -> on_event -> update]*
      -> on_complete -> hold_open -> teardown
```

`teardown` runs from a `finally` block after setup is attempted. Pausing and
single-step gating happen before delivery of the pending canonical record, so a
paused renderer cannot drop records and a step permit processes one record.
Rendering is selected at the client boundary:

- `HeadlessRenderer` prints stable text and has no Pygame dependency.
- `PygameRenderer` is imported lazily only when selected.

`AbstractRenderer` supplies no-op interactive, update, completion, and hold-open
methods. Concrete renderers therefore share one interface without capability
probing. `PygameCanvas` uses `update` from a Qt timer, imports Pygame only when the
widget is shown, and completes/tears down the renderer when the widget closes.

Schema/version and legacy-shape checks are confined to the read boundary rather
than individual renderers. The client does not run the simulation. The repository also retains older
renderer modules and a compatibility module at `client/src/renderers.py`.

### Desktop application (`app`)

`app.agent_designer`, `app.match_runner`, and `app.replay_viewer` provide desktop
tools and service adapters. They are packaged from the repository root rather
than the two `src` trees. The designer uses PySide6 and the live runner/viewer use
Pygame-oriented presentation paths. These are adjacent consumers of the engine,
not part of `battle_engine.core`.

## Configuration and artifacts

- `engine/config/battle.defaults.json` is a reference defaults file. Runtime
  defaults are also encoded in the `Config` dataclass.
- `agents/<name>/agent.yaml` and optional `model.blob` form the agent catalog.
- Native runs produce `replay.jsonl` and `summary.json`.
- Historical run output, prebuilt executables, pMARS binaries, SDK examples, and
  `_legacy/` coexist with the active source tree.

## Packaging and commands

The root `pyproject.toml` uses setuptools and discovers packages from
`engine/src`, `client/src`, and the repository root. Public commands are:

- `battle2` → `battle_engine.command:main`
- `battle-cli` → compatibility wrapper for `battle_engine.cli:main`
- `match-runner` → compatibility wrapper for `app.match_runner:main`
- `battle-agent-designer` → lazy compatibility wrapper for the designer

`app/pyproject.toml` separately describes the desktop designer and maps
`battle-agent-designer` to `app.main:main`. The root project is the authoritative
whole-repository package used by the documented install flow.

Windows builds remain implemented by the PowerShell scripts and PyInstaller spec
files under `tools/`; `tools/build_win.ps1` is invoked by CI.
The unified Windows `battle2.exe` explicitly collects the dynamically loaded
`app` package and Qt dependencies, so all four dispatcher commands are available.
The Windows build runs deterministic frozen startup smoke for both
`battle2.exe design` and the standalone Designer; this is startup coverage, not
a substitute for manual visible/input GUI testing.

Runtime Python support is 3.10 through 3.13. Core installation requires PyYAML. Optional
extras are `replay` (Pygame), `designer` (PySide6), `dev`, and `windows-build`;
the v0.1 `gui` aggregate remains as an alias. Some legacy release scripts choose
Python 3.11 for reproducible executable builds, but this does not raise the
package runtime minimum.

Wheels contain Python packages and package-local assets only. Repository-level
agent directories remain runtime/user data. pMARS executables, SDK archives,
historical builds, and third-party license trees are deliberately excluded from
the Python wheel; any future binary distribution must preserve the applicable
pMARS GPLv2 licensing materials.

## Tests and automation

`pytest.ini` includes `_legacy/tests`, `engine/tests`, and `client/tests` while
excluding tests marked `gui` from ordinary headless runs. Display-backed smoke
tests are invoked explicitly by the dedicated Linux GUI workflow, including the
Designer test under root `tests/`. The legacy tests intentionally import the
top-level legacy `core` module. The engine and client characterization tests
import the packaged modules and freeze v0.1 behavior without starting a visible
window.

GitHub Actions runs the headless suite on Python 3.10, 3.11, 3.12, and 3.13,
validates the pure wheel, and builds the five Windows executables. Optional
workflows provide Linux X11/Xvfb startup smoke for Pygame and the Designer and
Ubuntu 22.04 pMARS build/runtime validation. These startup checks do not replace
manual visible rendering, input, scaling, close-lifecycle, or native Wayland tests.

## Dependency direction as implemented

```text
agent manifests/blobs + built-ins
              |
              v
      battle_engine.cli -----> pMARS (redcode94 only)
              |
              v
       battle_engine.core (Kernel facade)
              |
              v
 match -> scoring/statistics -> results
              |
              v
 telemetry adapters -> replay.jsonl / summary.json / legacy renderer
              |
              v
       app tools / replay client
```

The extracted low-level dependency direction is acyclic:

```text
config                 instructions     agent_state
                            \              /
                             \            /
                                  vm
                         \       |       /
                          \      v      /
                           core (Kernel facade)
                                  |
                         CLI and consumers
```

`config`, `instructions`, and `agent_state` use only the standard library. `vm`
depends on `instructions` and `agent_state`; none imports `core`. Built-in agents
depend directly on `instructions`.

The VM executes instructions only; it does not calculate scores or statistics.
Domain statistics and result construction do not write files. Replay dictionary
construction and serialization live in telemetry, outside the scheduling logic.
Renderer-specific `__owners__` compatibility remains isolated in
`LegacyRendererObserver`.

Remaining coupling is intentional for compatibility: `Kernel` remains the public
mutable match state consumed by `MatchRunner`; the CLI still creates the v0.1
replay sink and writes its separate version 2 user-facing summary; and the kernel
facade suppresses default summary-output failures as v0.1 did.

## Application roots

`battle_engine.paths` is the shared root-resolution boundary. `BATTLE2_ROOT`
(with `BATTLE_ROOT` as a legacy fallback) selects the writable data root used
for agents, replays, logs, generated files, and user configuration. Relative
configured values are normalized against the current working directory.

The application resource root is separate. Source checkouts use the repository
root, installed packages use package-local resources, and frozen applications
use PyInstaller's `_MEIPASS` extraction directory for read-only bundled files.
`_MEIPASS` is never a writable data root. Without an explicit root, a frozen
portable application writes beside its executable; the Windows installer sets
`BATTLE2_ROOT` to select its writable ProgramData location.

With neither root variable set, a regular installed Linux wheel uses
`$XDG_DATA_HOME/battle2` or `~/.local/share/battle2`. A regular installed Windows
wheel uses `%LOCALAPPDATA%\BATTLE2`, falling back beneath the current user's
`AppData\Local` directory. Source and editable checkouts continue to use the
repository root.

The v0.2 installer preserves each PyInstaller onedir artifact beneath
`{app}\bin\<application>`, so the Designer's frozen sibling lookup reaches the
installed `battle2` and replay-viewer directories without duplicating their
internals. Installation is administrative and AMD64-only. It sets the machine
`BATTLE2_ROOT` to `%ProgramData%\BATTLE2` by default, does not modify `PATH`, and
retains writable application data during uninstall.

`battle_engine.launchers` owns child command construction. Source and editable
applications invoke the primary dispatcher or replay client with the current
Python interpreter. Frozen applications resolve `battle2.exe` and
`battle-replay-viewer.exe` beside the current executable (including the v0.2
onedir sibling-folder layout); writable-data settings never redirect executable
discovery. Commands are always argument lists rather than shell strings.
