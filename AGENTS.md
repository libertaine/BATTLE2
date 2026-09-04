# Agent Development Guidance

This file is the authoritative, tool-agnostic reference for any coding agent
(Claude, Codex, or otherwise) working in this repository. Tool-specific entry
points (e.g. [`CLAUDE.md`](CLAUDE.md)) should defer to this file rather than
duplicating it.

## What this project is

Bytefray is a programmable-agent arena inspired by Core
War: deterministic VM and Python agents compete in a shared memory arena,
with canonical replay/result recording and a headless tournament service.
See [README.md](README.md) for the user-facing overview and
[ARCHITECTURE.md](ARCHITECTURE.md) for the full component map — read that
file before making non-trivial changes; the summary below is intentionally
abbreviated.

## Architecture boundaries

- **Multi-root source layout.** Packages live under `engine/src/battle_engine`
  (simulation core, CLI), `client/src/battle_client` (replay client,
  renderers), and `app/` (PySide6 designer, Pygame-oriented tools, packaged
  from the repo root rather than a `src` tree). `pyproject.toml` discovers
  all three via `tool.setuptools.packages.find`.
- **Dependency direction is intentionally acyclic.** `config`, `instructions`,
  and `agent_state` are standard-library-only leaves; `vm` depends on
  `instructions`/`agent_state`; `core` (the `Kernel` facade) sits above `vm`;
  `match`/`scoring`/`statistics`/`results` sit above `core`; telemetry
  adapters and the CLI/app layer sit above that. Don't introduce a dependency
  that runs the other direction (e.g. `vm` importing `core`). See the
  "Dependency direction as implemented" section of ARCHITECTURE.md for the
  full diagram.
- **The VM executes instructions only.** It does not calculate scores or
  statistics; those are separate services (`ScoringPolicy`,
  `StatisticsCollector`). Domain statistics and result construction do not
  write files — replay/summary serialization is confined to `telemetry`.
- **Compatibility surfaces are deliberate, not accidental.** `battle_engine.core`
  re-exports names like `VM`, `Config`, `Weights`, `Agent`, `enc` from their
  new extracted modules so existing imports keep working. `Kernel` remains
  the public mutable match-state object. Don't collapse these re-exports or
  "clean up" the facade without checking who still imports through it.
- **`_legacy/` is frozen historical code**, retained as a characterized
  migration fixture. Don't assume something is unused just because it looks
  legacy — check whether it is imported, tested, or wired to an entry point
  before deleting it.

## Testing expectations

- Run the suite with `python -m pytest` — no extra flags required.
  `pytest.ini` already sets `-m "not gui"`, repo-local cache/temp dirs, and
  `testpaths` (`_legacy/tests`, `engine/tests`, `client/tests`).
- Tests marked `gui` are display-backed and intentionally excluded from the
  headless run; they're exercised by a dedicated CI workflow instead. Don't
  add plain (unmarked) tests that require a display.
- Type-check with `mypy engine/src/battle_engine` and
  `mypy client/src/battle_client` (two separate invocations — see
  `[tool.mypy]` in `pyproject.toml` and
  [docs/WINDOWS_DEV_NOTES.md](docs/WINDOWS_DEV_NOTES.md) for why a plain
  `mypy .` doesn't resolve imports correctly on some platforms).
- Lint with `ruff check .` — required by `ci.yml`'s `test-linux-core` job.
  Three rule codes (`BLE001`, `S110`, `TRY004`) are ignored project-wide
  because they conflict with a deliberate, documented `except Exception:
  pass` pattern used in several compatibility/optional-feature code paths;
  see [docs/RUFF_DEBT.md](docs/RUFF_DEBT.md) before changing that ignore
  list or adding a new one. `_legacy/`'s frozen source files are excluded from
  linting entirely (same doc).
- If `pytest` fails with a Windows `PermissionError` on a temp/cache path,
  that's a known stale-directory/ACL class of problem documented in
  WINDOWS_DEV_NOTES.md, not a project bug — don't "fix" it by changing
  `pytest.ini`'s repo-local cache/temp paths back to OS defaults.
- New engine behavior should get characterization or scenario coverage under
  `engine/tests`; client/renderer behavior under `client/tests`. Prefer
  extending existing focused test modules over adding ad hoc scripts at the
  repo root.

## Supported environments

- Runtime Python support is **3.10 through 3.14**; CI validates all five.
  Some legacy *release-build* tooling pins Python 3.11 for reproducible
  PyInstaller executables — that does not raise the package's runtime
  minimum.
- Core install requires only PyYAML. GUI/dev functionality is opt-in via
  extras: `replay` (pygame-ce, providing the `pygame` import namespace),
  `designer` (PySide6), `dev`, `windows-build`; `gui` is a compatibility
  aggregate of `replay`+`designer`.
- The Linux wheel is **headless-first** — see
  [docs/LINUX_INSTALL.md](docs/LINUX_INSTALL.md). Windows is the primary GUI
  development target; see [docs/WINDOWS_DEV_NOTES.md](docs/WINDOWS_DEV_NOTES.md).
- Windows packaging targets AMD64 only (no ARM64 claim) and requires
  administrative installation via the Inno Setup installer.

## Release / build constraints

- Windows builds are produced by the PowerShell scripts and PyInstaller spec
  files under `tools/` (`tools/build_win.ps1` is invoked by CI). The unified
  `bytefray.exe` explicitly collects the `app` package and Qt dependencies so
  all four dispatcher commands work from one build.
- Wheels contain **Python packages and package-local assets only**. Repo-level
  `agents/` directories are runtime/user data, not package data. pMARS
  executables, SDK archives, historical builds, and `third_party_licenses/`
  are deliberately excluded from the Python wheel. Any future binary
  distribution that bundles pMARS must preserve its GPLv2 licensing
  materials (see `third_party_licenses/`).
- CI runs the headless suite on Python 3.10–3.14, validates the pure wheel,
  and builds the four Windows executables. Optional workflows cover Linux
  X11/Xvfb GUI startup smoke and Ubuntu pMARS build/runtime — these are
  startup checks, not a substitute for manual interactive testing.

## Compatibility requirements

- Bytefray is the only current product and command name. The obsolete
  `battle2`, `battle-cli`, and `battle-*` command wrappers and Windows
  executable names were retired for v1.4. Do not reintroduce them as active
  compatibility surfaces.
- Internal package names (`battle_engine`, `battle_client`) and the
  `battle2.*` schema identifiers (`battle2.result`, `battle2.replay`) are
  **stable protocol identifiers** and are retained unchanged even though the
  product is now branded Bytefray. Do not rename these to match the new
  branding.
- `BYTEFRAY_ROOT` is the sole supported data-root environment variable.
  Obsolete predecessor variables are intentionally ignored.
- Schema/version changes (replay, result, Agent API) are versioned
  explicitly — see [docs/REPLAY_SCHEMA.md](docs/REPLAY_SCHEMA.md),
  [docs/RESULT_SCHEMA.md](docs/RESULT_SCHEMA.md),
  [docs/AGENT_API_V1.md](docs/AGENT_API_V1.md), and
  [docs/AGENT_API_V2.md](docs/AGENT_API_V2.md). Bump the version and update
  the schema doc rather than silently changing wire shape in place.
- v4.0.0-alpha1's Ruleset (`bytefray-rules-4-alpha1`) and Agent API v2 are
  alpha contracts, not replacements for the frozen historical ones above —
  see [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md)'s "v4.0.0-alpha1
  compatibility boundary" for exactly what stays frozen (API v1, Ruleset
  v1/v2, schema-3 replays) alongside what v4 alpha adds.
- **Three v4 Rulesets now exist.** `bytefray-rules-4-alpha2` differs from
  alpha1 in exactly two gameplay semantics — seed-derived core placement and
  round-robin intra-entrant process selection — on the same Agent API v2 and
  the same replay schema 4. Both alphas' semantics are **frozen**: an alpha1
  or alpha2 fixture, golden, or deterministic vector that starts failing is
  an implementation defect, never something to re-bless. As of `v4.0.0-rc1`
  Phase 2, the permanent `bytefray-rules-4` identity is gameplay-identical to
  alpha2 (never aliased to it — a fully distinct dispatch/hash/persistence
  identity, proven equivalent by
  `engine/tests/test_v4_stable_ruleset_equivalence.py`) and is what an
  omitted `--ruleset` now resolves to for an Agent API v2 roster; both alphas
  stay explicitly selectable everywhere. See
  [docs/V4_ALPHA2_DESIGN.md](docs/V4_ALPHA2_DESIGN.md) and
  [docs/RULES_V4.md](docs/RULES_V4.md).
- A Ruleset's gameplay semantics belong on its
  `RulesetPolicy` (`core_placement`, `process_selection`, the scheduler
  fields), not on `MatchRequest`. A per-match override field that only
  research code can set is how a hidden experiment switch becomes accidental
  public API — the Phase 4 research branch's five such fields were
  deliberately not carried into the product for exactly this reason.

## Git safety

- Before modifying files, inspect the current branch, working-tree status,
  and any existing uncommitted changes. Preserve unrelated user changes.
- Never force-push, `reset --hard`, or otherwise rewrite `main`, any
  release/foundation branch, or any `origin/*` branch without explicit user
  instruction.
- Prefer new commits over amending; never amend a commit that's already been
  pushed.
- Don't bypass hooks (`--no-verify`) or disable signing to get a commit or
  push through — fix the underlying failure instead.
- Only commit when asked. When staging, review what's actually included
  rather than blindly using `git add -A`/`git add .`.

## Task discipline

- Before implementing non-trivial behavior, read the relevant
  architecture/schema documentation and check `docs/specs/` for an existing
  specification.
- Make the smallest change that satisfies the requested behavior; don't
  opportunistically refactor adjacent code unless required for correctness.
- Preserve public and compatibility surfaces unless the task explicitly
  changes them.
- Run the focused tests first, then the appropriate broader validation
  (`python -m pytest`, relevant `mypy` invocation) before reporting
  completion.

## Where to look for deeper documentation

| Topic | Doc |
|---|---|
| Full architecture / dependency graph | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Contribution workflow (spec → issue → prompt → PR) | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Version history | [CHANGELOG.md](CHANGELOG.md) |
| Install paths, env vars | [INSTALL.md](INSTALL.md) |
| Windows dev environment quirks | [docs/WINDOWS_DEV_NOTES.md](docs/WINDOWS_DEV_NOTES.md) |
| Linux wheel install | [docs/LINUX_INSTALL.md](docs/LINUX_INSTALL.md) |
| Writing agents | [docs/AGENT_AUTHORING.md](docs/AGENT_AUTHORING.md) |
| Debugging agents: trace, inspect, diverge, timeouts | [docs/AGENT_LAB.md](docs/AGENT_LAB.md) |
| Agent API v1 contract (historical, frozen) | [docs/AGENT_API_V1.md](docs/AGENT_API_V1.md) |
| Agent API v2 contract (`declare_processes()`, `ObservationV2`, `ActionKindV2`) | [docs/AGENT_API_V2.md](docs/AGENT_API_V2.md) |
| Bytefray Ruleset v1 (gameplay semantics, historical/frozen) | [docs/RULES.md](docs/RULES.md) |
| Bytefray Ruleset v2 beta (gameplay semantics, historical/frozen) | [docs/RULES_V2.md](docs/RULES_V2.md) |
| Bytefray Ruleset v4 alpha1 design/semantics -- frozen historical behavior for this alpha, not a live target for further gameplay iteration | [docs/V4_ALPHA1_DESIGN.md](docs/V4_ALPHA1_DESIGN.md) |
| Bytefray Ruleset v4 alpha2 gameplay contract (current v4 prerelease; written as a delta against the alpha1 freeze) | [docs/V4_ALPHA2_DESIGN.md](docs/V4_ALPHA2_DESIGN.md) |
| Evidence behind the alpha2 rule changes (Phase 4 controlled gameplay study) | [docs/V4_ALPHA2_PHASE4_GAMEPLAY_STUDY.md](docs/V4_ALPHA2_PHASE4_GAMEPLAY_STUDY.md) |
| Result schema | [docs/RESULT_SCHEMA.md](docs/RESULT_SCHEMA.md) |
| Replay schema | [docs/REPLAY_SCHEMA.md](docs/REPLAY_SCHEMA.md) |
| Headless tournaments | [docs/TOURNAMENTS.md](docs/TOURNAMENTS.md) |
| Compatibility axes (Ruleset/Agent API/schema/methodology) | [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md) |
| Manual smoke-test checklist | [docs/MANUAL_SMOKE_TESTS.md](docs/MANUAL_SMOKE_TESTS.md) |
| Feature specs (source of truth before implementing) | `docs/specs/` |
