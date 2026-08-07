# Changelog

This changelog records notable user- and developer-visible changes to BATTLE2.

## [Unreleased]

### Added

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

### Changed

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

### Fixed

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
  for non-returning callbacks are not implemented.
- Tournament execution has not yet been rebuilt on `NativeMatchService`.
- Replay and result schemas retain the existing compatibility formats pending
  later normalization.

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
