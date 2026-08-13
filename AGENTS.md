# Agent Development Guidance

This file is the authoritative, tool-agnostic reference for any coding agent
(Claude, Codex, or otherwise) working in this repository. Tool-specific entry
points (e.g. [`CLAUDE.md`](CLAUDE.md)) should defer to this file rather than
duplicating it.

## What this project is

Bytefray (formerly BATTLE2) is a programmable-agent arena inspired by Core
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
- **`_legacy/` and `app/match_runner.py` are known dead/frozen code**, kept
  for compatibility or historical reasons (see
  [docs/WINDOWS_DEV_NOTES.md](docs/WINDOWS_DEV_NOTES.md) for why
  `match_runner.py` is dead source). Don't assume something is unused just
  because it looks legacy — check whether it's still imported or wired to a
  console script before deleting it.

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
- If `pytest` fails with a Windows `PermissionError` on a temp/cache path,
  that's a known stale-directory/ACL class of problem documented in
  WINDOWS_DEV_NOTES.md, not a project bug — don't "fix" it by changing
  `pytest.ini`'s repo-local cache/temp paths back to OS defaults.
- New engine behavior should get characterization or scenario coverage under
  `engine/tests`; client/renderer behavior under `client/tests`. Prefer
  extending existing focused test modules over adding ad hoc scripts at the
  repo root (note there are several stray one-off `*.py`/`.patch` files at
  the repo root already — don't treat their presence as precedent).

## Supported environments

- Runtime Python support is **3.10 through 3.13**; CI validates all four.
  Some legacy *release-build* tooling pins Python 3.11 for reproducible
  PyInstaller executables — that does not raise the package's runtime
  minimum.
- Core install requires only PyYAML. GUI/dev functionality is opt-in via
  extras: `replay` (Pygame), `designer` (PySide6), `dev`, `windows-build`;
  `gui` is a compatibility aggregate of `replay`+`designer`.
- The Linux wheel is **headless-first** — see
  [docs/LINUX_INSTALL.md](docs/LINUX_INSTALL.md). Windows is the primary GUI
  development target; see [docs/WINDOWS_DEV_NOTES.md](docs/WINDOWS_DEV_NOTES.md).
- Windows packaging targets AMD64 only (no ARM64 claim) and requires
  administrative installation via the Inno Setup installer.

## Release / build constraints

- Windows builds are produced by the PowerShell scripts and PyInstaller spec
  files under `tools/` (`tools/build_win.ps1` is invoked by CI). The unified
  `battle2.exe` explicitly collects the `app` package and Qt dependencies so
  all four dispatcher commands work from one build.
- Wheels contain **Python packages and package-local assets only**. Repo-level
  `agents/` directories are runtime/user data, not package data. pMARS
  executables, SDK archives, historical builds, and `third_party_licenses/`
  are deliberately excluded from the Python wheel. Any future binary
  distribution that bundles pMARS must preserve its GPLv2 licensing
  materials (see `third_party_licenses/`).
- CI runs the headless suite on Python 3.10–3.13, validates the pure wheel,
  and builds the five Windows executables. Optional workflows cover Linux
  X11/Xvfb GUI startup smoke and Ubuntu pMARS build/runtime — these are
  startup checks, not a substitute for manual interactive testing.

## Compatibility requirements

- The project was renamed BATTLE2 → Bytefray. `bytefray` is the canonical
  CLI; `battle2` is a deprecated but still-functional compatibility alias
  (identical implementation, prints a deprecation notice). Don't remove the
  `battle2` alias, `battle-cli`, or `battle-agent-designer` without an
  explicit decision to do so — they are documented, supported compatibility
  wrappers, not accidental leftovers.
- Internal package names (`battle_engine`, `battle_client`) and the
  `battle2.*` schema identifiers (`battle2.result`, `battle2.replay`) are
  **stable protocol identifiers** and are retained unchanged even though the
  product is now branded Bytefray. Do not rename these to match the new
  branding.
- `BYTEFRAY_ROOT` is the preferred data-root environment variable;
  `BATTLE2_ROOT` and `BATTLE_ROOT` remain supported deprecated fallbacks, in
  that precedence order. Preserve this fallback chain in any code that
  resolves the writable data root (`battle_engine.paths`).
- Schema/version changes (replay, result, Agent API) are versioned
  explicitly — see [docs/REPLAY_SCHEMA.md](docs/REPLAY_SCHEMA.md),
  [docs/RESULT_SCHEMA.md](docs/RESULT_SCHEMA.md), and
  [docs/AGENT_API_V1.md](docs/AGENT_API_V1.md). Bump the version and update
  the schema doc rather than silently changing wire shape in place.

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
| Agent API v1 contract | [docs/AGENT_API_V1.md](docs/AGENT_API_V1.md) |
| Bytefray Ruleset v1 (gameplay semantics) | [docs/RULES.md](docs/RULES.md) |
| Result schema | [docs/RESULT_SCHEMA.md](docs/RESULT_SCHEMA.md) |
| Replay schema | [docs/REPLAY_SCHEMA.md](docs/REPLAY_SCHEMA.md) |
| Headless tournaments | [docs/TOURNAMENTS.md](docs/TOURNAMENTS.md) |
| Compatibility axes (Ruleset/Agent API/schema/methodology) | [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md) |
| Manual smoke-test checklist | [docs/MANUAL_SMOKE_TESTS.md](docs/MANUAL_SMOKE_TESTS.md) |
| Feature specs (source of truth before implementing) | `docs/specs/` |
