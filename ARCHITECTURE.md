# BATTLE2 v0.1 Architecture

This document records the architecture at the v0.1 baseline. It is descriptive,
not a proposal: some responsibilities overlap and some historical code remains in
the repository. Proposed v0.2 boundaries are in
[`docs/V0_2_MIGRATION.md`](docs/V0_2_MIGRATION.md).

## Runtime components

### Engine package (`engine/src/battle_engine`)

`battle_engine.core` is the simulation implementation and the primary public
compatibility surface. It contains:

- the byte-oriented ISA constants and `enc` assembler helper;
- `Config` and `Weights` dataclasses;
- `Agent`, the mutable execution state;
- `VM`, including circular arena memory, ownership, instruction decoding, and
  per-tick memory differences;
- `Kernel`, including scheduling, match lifecycle, statistics, scoring, kill
  attribution, winner resolution, renderer callbacks, and summary creation; and
- `JSONLSink`, the replay writer.

The VM supports `NOP`, `MOV`, `ADD`, `LOAD`, `STORE`, `JMP`, `JZ`, `HALT`,
`MOVP`, `ADDP`, `LOADI`, and `STOREI`. Values encoded by `enc` use one opcode byte
and, where applicable, a four-byte little-endian immediate.

`battle_engine.builtins` assembles the native `runner`, `writer`, `bomber`,
`flooder`, `spiral`, and `seeker` programs into VM bytecode.

`battle_engine.agents` discovers directories below `agents/`. A directory is
valid when it has `agent.yaml` or `agent.py`. Despite its name, `agent.yaml` may
contain JSON; YAML syntax is supported when PyYAML is installed. The resolver
recognizes an optional `model.blob`, display metadata, and default parameters.
The current CLI executes blobs and built-ins; it detects `agent.py` but does not
load Python agent code itself.

### Engine CLI (`battle_engine.cli`)

The `battle-cli` command and `python -m battle_engine.cli` use the same argparse
entry point. The CLI:

1. resolves configuration and agent parameters from flags and environment;
2. resolves agent slots in this order: `BATTLE_AGENTS_JSON`, direct blob flag,
   discovered agent, built-in agent;
3. runs either the native B2 `Kernel` or an external pMARS process for
   `redcode94` mode; and
4. writes match artifacts.

The native replay is newline-delimited JSON. Its first record is a version 6
header containing configuration, followed by one snapshot per executed tick.
Each snapshot contains agent state, score, events, and memory ownership diffs.
The CLI writes a sibling `summary.json` with schema version 2. `Kernel.run` also
attempts to write a summary to `summary.json` in the current working directory;
the CLI's sibling summary is the user-facing artifact.

The external pMARS mode writes a version 2 summary but no native replay stream.

### Replay client (`client/src/battle_client`)

`battle_client.cli` reads existing JSONL streams and optionally reads a sibling
`summary.json`. Rendering is selected at the client boundary:

- `HeadlessRenderer` prints stable text and has no Pygame dependency.
- `PygameRenderer` is imported lazily only when selected.

The client does not run the simulation. The repository also retains older
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

- `battle-cli` → `battle_engine.cli:main`
- `match-runner` → `app.match_runner:main`
- `battle-agent-designer` → `app.agent_designer:main`

`app/pyproject.toml` separately describes the desktop designer and maps
`battle-agent-designer` to `app.main:main`. The root project is the authoritative
whole-repository package used by the documented install flow.

Windows builds remain implemented by the PowerShell scripts and PyInstaller spec
files under `tools/`; `tools/build_win.ps1` is invoked by CI.

## Tests and automation

`pytest.ini` includes `_legacy/tests`, `engine/tests`, `client/tests`, and
`sdk/tests`. The legacy tests intentionally import the top-level legacy `core`
module. The engine and client characterization tests import the packaged modules
and freeze v0.1 behavior without starting a visible window.

GitHub Actions runs the full pytest suite on Linux and builds Windows executables
with the existing scripts on Windows. Dependency installation in CI uses the
three requirements files.

## Dependency direction as implemented

```text
agent manifests/blobs + built-ins
              |
              v
      battle_engine.cli -----> pMARS (redcode94 only)
              |
              v
       battle_engine.core ----> replay.jsonl + summary.json
              |
              v
       app tools / replay client ----> headless or Pygame presentation
```

There is not yet a formal application-service or persistence interface between
these layers. `core.py` and the CLI are therefore coupled to file formats and
match orchestration details.
