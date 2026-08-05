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
- `Kernel.run` writes `summary.json` to the working directory while the CLI writes
  a second, different summary beside the replay.
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
- Version 2 CLI summaries remain readable and retain established keys.
- Existing `agents/<name>` directories, JSON-or-YAML manifests, blobs, default
  parameters, and environment overrides remain usable.
- Fixed inputs and seeds retain deterministic match results. Scheduling, scoring,
  kill attribution, and winner tie-breaking remain stable until deliberately
  versioned.
- Headless processing must not import or initialize Pygame.
- Existing PowerShell, PyInstaller, installer, and pMARS Windows assets are not
  removed during the migration.

## Migration phases

### Phase 0 — Freeze v0.1

Maintain this architecture inventory, behavioral characterization suite, artifact
schema assertions, and manual smoke checklist. No engine redesign occurs here.

### Phase 1 — Define contracts

Introduce typed match requests/results, event and summary models, agent adapter
protocols, and replay reader/writer interfaces. Adapt current code without moving
public names or changing serialized output.

### Phase 2 — Extract deterministic runtime

Move ISA and VM implementation behind internal modules. Keep
`battle_engine.core` as a compatibility facade and compare behavior against the
v0.1 characterization suite and fixed fixtures.

### Phase 3 — Extract match policy

Separate scheduling, statistics, scoring, and winner resolution from the VM.
Remove implicit filesystem writes from the new service while retaining them in
the compatibility facade where required.

### Phase 4 — Isolate adapters and persistence

Move agent discovery/execution, pMARS invocation, replay I/O, and summary I/O to
adapters. Add explicit backward-compatible readers before any writer evolves.

### Phase 5 — Rewire CLI and presentation

Make CLI and desktop tools consume the application boundary. Consolidate renderer
event contracts and retain the headless/Pygame separation.

### Phase 6 — Packaging cleanup

Only after runtime compatibility is demonstrated, reconcile package metadata,
entry-point ownership, defaults, build inputs, and historical/generated layout.

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
