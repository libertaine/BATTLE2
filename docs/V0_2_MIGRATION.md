# BATTLE2 v0.2 Migration Plan

## Current architectural limitations

- `battle_engine.core` combines ISA, VM state, scheduling, scoring, match policy,
  telemetry, rendering callbacks, and filesystem summary output.
- The CLI combines parsing, environment configuration, discovery, orchestration,
  pMARS integration, artifact paths, and summary serialization.
- Replay and summary schemas are implicit dictionaries rather than versioned
  model boundaries with reader compatibility tests.
- Runtime defaults exist both in Python and in a JSON configuration file.
- Agent discovery recognizes source agents, but the match path directly executes
  blobs or built-ins and does not define one execution protocol for every format.
- The engine has a renderer callback while the replay client separately defines
  a presentation interface.
- Direct `Kernel.run` callers retain an injectable compatibility summary sink;
  the CLI suppresses that sink and writes one canonical summary beside the replay.
- Active, compatibility, historical, generated, and prebuilt content coexist at
  the repository root, making supported ownership boundaries difficult to see.
- Root packaging and `app/pyproject.toml` expose differing designer entry points.
- The original automated suite covered a legacy API rather than the installed
  engine and client.

## Proposed v0.2 component boundaries

These are target responsibilities, not instructions to move all files at once.

1. **Domain/ISA** — instruction definitions, encoding/decoding, and immutable
   value types with no CLI, rendering, or filesystem access.
2. **VM runtime** — arena, ownership, registers, and deterministic single-step
   execution.
3. **Match application service** — spawning, scheduling, termination, statistics,
   scoring, and winner policy. Inputs and results should be explicit models.
4. **Agent catalog and execution adapters** — discovery plus adapters for native
   blob, future Python, and pMARS agents behind stable contracts.
5. **Replay/summary I/O** — versioned serialization, JSONL reading/writing, schema
   validation, and compatibility fixtures.
6. **CLI adapter** — argparse and environment translation into application-service
   requests; no simulation policy.
7. **Presentation adapters** — headless and Pygame consumers of replay or match
   events, with Pygame remaining optional and lazy.
8. **Desktop application** — PySide6/Pygame launchers consuming public application
   and replay interfaces rather than engine internals.

During migration, facades in `battle_engine.core` should re-export or delegate to
new internals so existing imports remain valid.

## Compatibility requirements

- Existing imports from `battle_engine.core` continue to work, including ISA
  constants, `enc`, `Config`, `Weights`, `Agent`, `VM`, `Kernel`, and `JSONLSink`.
- `battle-cli`, `match-runner`, and `battle-agent-designer` command names remain.
- Existing CLI flags, defaults, exit behavior, and native/pMARS mode selection do
  not change unintentionally.
- Replay version 6 JSONL remains readable. New writers must either preserve it or
  introduce an explicitly versioned format while readers accept both.
- Canonical v0.2 replay records use schema `battle2.replay`, schema version `2`,
  and explicit `header`, `tick`, or `result` record types. Future incompatible
  changes require a new schema version and a reader compatibility decision.
- Version 2 CLI summaries remain readable and retain established keys.
- Existing `agents/<name>` directories, JSON-or-YAML manifests, blobs, default
  parameters, and environment overrides remain usable.
- Fixed inputs and seeds retain deterministic match results. Scheduling, scoring,
  kill attribution, and winner tie-breaking remain stable until deliberately
  versioned.
- Headless processing must not import or initialize Pygame.
- Existing PowerShell, PyInstaller, installer, and pMARS Windows assets are not
  removed during migration. The v0.2 Windows release validation rebuilds all
  five artifacts and exercises an isolated install/upgrade/uninstall cycle.

## Migration phases

### Phase 0 — Freeze v0.1

Maintain this architecture inventory, behavioral characterization suite, artifact
schema assertions, and manual smoke checklist. No engine redesign occurs here.

### Phase 1 — Define contracts

Introduce typed match requests/results, event and summary models, agent adapter
protocols, and replay reader/writer interfaces. Adapt current code without moving
public names or changing serialized output.

Replay/event portion completed: `battle_engine.replay` now defines schema
`battle2.replay` version 2, typed replay records, serializers, useful validation
errors, and the v0.1 compatibility adapter. Replay clients consume canonical
models internally while the v0.1 engine writer remains unchanged. Match request
and agent adapter contracts remain future Phase 1 work. See
[`REPLAY_SCHEMA.md`](REPLAY_SCHEMA.md).

### Phase 2 — Extract deterministic runtime

Move ISA and VM implementation behind internal modules. Keep
`battle_engine.core` as a compatibility facade and compare behavior against the
v0.1 characterization suite and fixed fixtures.

Completed for the initial runtime boundary: configuration and weights now live in
`battle_engine.config`, ISA constants and bytecode encoding in
`battle_engine.instructions`, mutable execution state in
`battle_engine.agent_state`, and the VM in `battle_engine.vm`. `core` re-exports
the same objects and retains `Kernel` and scoring orchestration. A serialized
fixed-seed comparison covering result, stats, replay records, arena bytes, and
ownership was byte-for-byte identical before and after extraction.

### Phase 3 — Extract match policy

Separate scheduling, statistics, scoring, and winner resolution from the VM.
Remove implicit filesystem writes from the new service while retaining them in
the compatibility facade where required.

Completed while preserving `Kernel` as a facade: `battle_engine.match` schedules
ticks, `battle_engine.scoring` applies policy, `battle_engine.statistics` collects
in-memory counters, and `battle_engine.results` resolves winners and builds plain
summary data. `battle_engine.telemetry` supplies injected replay/summary ports and
the legacy renderer adapter. The compatibility facade still supplies default
`replay.jsonl` and `summary.json` adapters, while callers may inject both sinks.
Representative survival, tie, kill, unattributed-death, and territory matches
were byte-for-byte identical before and after extraction.

### Phase 4 — Isolate adapters and persistence

Move agent discovery/execution, pMARS invocation, replay I/O, and summary I/O to
adapters. Add explicit backward-compatible readers before any writer evolves.

Replay and kernel-summary persistence adapters are now isolated in
`battle_engine.telemetry`. CLI-specific summary persistence, agent execution
adapters, and pMARS isolation remain Phase 4 work.

### Phase 5 — Rewire CLI and presentation

Make CLI and desktop tools consume the application boundary. Consolidate renderer
event contracts and retain the headless/Pygame separation.

Replay presentation lifecycle completed: `AbstractRenderer` now defines setup,
interactive start, delivery readiness, canonical event ingestion, frame update,
completion, hold-open, and teardown. `ReplayPlayer` owns iteration and guarantees
ordering/cleanup. The replay CLI no longer probes optional methods, headless mode
keeps Pygame lazy, and the Qt canvas uses the same lifecycle for updates and
closure. Broader desktop-tool consolidation remains Phase 5 work.

## Linux pMARS release boundary

The platform-neutral Python wheel does not contain pMARS. Linux discovery skips
the repository's Windows PE resources and accepts an explicit executable through
`PMARS_CMD`, an executable in the Linux data/resource layout, or `pmars` on
`PATH`. The Ubuntu pMARS 0.9.5 package is an X11 build and is not a headless
release dependency.

`tools/build_pmars_linux.sh` is experimental release-engineering support for the
checksum-pinned authoritative pMARS 0.9.5 source. It builds a console-only,
libc-only executable without a source patch, but does not install, bundle, or
publish it. Any later portable artifact must define and validate a separate
GPL-2.0-or-later corresponding-source bundle before adding that executable.

### Phase 6 — Packaging cleanup

Only after runtime compatibility is demonstrated, reconcile package metadata,
entry-point ownership, defaults, build inputs, and historical/generated layout.

Initial normalization completed: `battle2 run|replay|design|agents` is the v0.2
primary interface, with lazy optional UI imports and a `python -m battle_engine`
equivalent. Dependencies are split into core, replay, designer, development, and
Windows-build groups; runtime support is consistently Python 3.10+.

Legacy-command deprecation policy: `battle-cli`, `match-runner`, and
`battle-agent-designer` remain installed compatibility wrappers for all v0.2
releases. Documentation may prefer `battle2`, but v0.2 must not warn, remove, or
change the legacy commands' exit behavior. Removal may only be considered in a
future major release after a separately announced deprecation period.

Root handling is centralized in `battle_engine.paths`. `BATTLE2_ROOT` is the
preferred writable-data setting and `BATTLE_ROOT` remains its legacy fallback.
These variables do not select PyInstaller's temporary extraction directory:
frozen resources are resolved independently, installed Windows builds should
set `BATTLE2_ROOT` to their writable data location, and an unconfigured portable
build defaults to the directory containing its executable.

Desktop child launching follows the same source/frozen boundary. Source tools
use Python modules, while a frozen Agent Designer launches the packaged sibling
`battle2.exe` and `battle-replay-viewer.exe` applications directly. It never
uses its own frozen executable as a Python interpreter or delegates replay files
to operating-system file associations.

The Agent Designer also initializes a small starter catalog before its first
discovery pass. Canonical manifests remain read-only package resources; only
missing Runner, Writer, Seeker, and Spiral files are copied into the writable
`agents` directory. Existing files and custom agents are never replaced or
removed.

## Out of scope for the initial migration

- Rewriting `core.py` in the v0.1 freeze task.
- A new ISA, changed opcode semantics, or a new arena representation.
- Scoring rebalance, scheduling changes, new winner rules, or seed semantics.
- Replay or summary schema redesign and removal of old readers.
- New agent formats or a redesign of existing manifests and directories.
- Implementing a Python-agent sandbox or changing blob execution.
- Replacing pMARS or changing Redcode match semantics.
- Rendering redesign, visible-window automation, or GUI framework replacement.
- Broad packaging modernization, repository-history cleanup, or removal of
  Windows build scripts and checked-in release assets.
- Tournament, SDK, network service, security sandbox, or performance work not
  required to establish the component boundaries.
