# Contributing to Bytefray

Thanks for your interest in contributing. This guide covers what you need to
set up a development environment, run the checks a change is expected to
pass, and understand how the repository is organized. None of it requires
AI tooling of any kind — see [AI tooling](#ai-tooling) at the end.

## Supported Python versions

Bytefray supports Python **3.10 through 3.13**; CI validates all four. A few
release-build tools (PyInstaller-based Windows packaging) pin Python 3.11
for reproducible executables, but that does not change the package's
runtime minimum.

## Setting up a development environment

```bash
git clone https://github.com/libertaine/Bytefray.git
cd Bytefray
python -m venv .venv
.venv\Scripts\activate        # Windows PowerShell
# or
source .venv/bin/activate     # Linux / macOS

pip install -U pip setuptools wheel
pip install -e ".[dev,replay,designer]"
```

This installs the engine and CLI in editable mode plus the `dev` extra
(pytest, ruff, mypy, types-PyYAML), the `replay` extra (Pygame, for the
replay viewer), and the `designer` extra (PySide6, for the Agent Designer
GUI). If you only need the headless engine and CLI, `pip install -e .` is
enough — GUI extras are optional.

On Windows, `sync_win.ps1` (`pwsh -ExecutionPolicy Bypass -File .\sync_win.ps1`)
is an optional convenience script that fetches/pulls the current branch
(auto-stashing local changes first) and then creates/activates `.venv` and
runs the same editable install for you; it's equivalent to the manual steps
above, not a separate workflow.

Windows is the primary GUI development target; see
[docs/WINDOWS_DEV_NOTES.md](docs/WINDOWS_DEV_NOTES.md) for platform-specific
quirks (stale cache/temp directories, mypy import resolution). The Linux
wheel is headless-first; see [docs/LINUX_INSTALL.md](docs/LINUX_INSTALL.md).

## Repository structure

Bytefray uses a multi-root source layout:

- `engine/src/battle_engine/` — the simulation core and CLI (`bytefray`).
- `client/src/battle_client/` — the replay client and renderers.
- `app/` — the PySide6 Agent Designer and Pygame-oriented desktop tools,
  packaged from the repository root rather than a `src/` tree.
- `engine/tests/`, `client/tests/`, `_legacy/tests/` — the pytest suites
  that make up `pytest.ini`'s `testpaths`.
- `tests/` (top level) — display-backed Designer GUI tests, intentionally
  excluded from the default headless run and exercised by a dedicated CI
  workflow instead.
- `docs/` — architecture, schema, and how-to reference documentation, plus
  `docs/specs/` (see [Specs before implementation](#specs-before-implementation)).
- `tools/` — Windows build/installer scripts, wheel/smoke-test checks, and
  optional local-AI developer tooling.

Read [AGENTS.md](AGENTS.md) and [ARCHITECTURE.md](ARCHITECTURE.md) before
making non-trivial changes — they describe the dependency-direction rules
between packages and the compatibility surfaces (`battle_engine.core`
re-exports, the `battle2` CLI alias, `BATTLE2_ROOT`/`BATTLE_ROOT` fallbacks,
etc.) that must not be broken without an explicit, separate decision to do
so.

## Running tests

```bash
python -m pytest
```

No extra flags are required — `pytest.ini` already sets `testpaths`
(`_legacy/tests`, `engine/tests`, `client/tests`), excludes tests marked
`gui`, and points pytest's cache/temp directories at repo-local paths
instead of OS defaults. Tests marked `gui` are display-backed and are
exercised by a dedicated CI workflow (Xvfb on Linux) rather than the default
run; don't add plain (unmarked) tests that require a display.

New engine behavior should get characterization or scenario coverage under
`engine/tests`; client/renderer behavior under `client/tests`. Prefer
extending an existing focused test module over adding an ad hoc script at
the repository root.

## Linting and type-checking

```bash
ruff check .
mypy engine/src/battle_engine
mypy client/src/battle_client
```

mypy is invoked as two separate commands because the engine and client
packages live under two separate `src` roots; a plain `mypy .` does not
resolve imports correctly on some platforms (see
[docs/WINDOWS_DEV_NOTES.md](docs/WINDOWS_DEV_NOTES.md) for why). Both `ruff`
and `mypy` are declared as part of the `dev` extra; run them locally before
opening a PR.

## Compatibility constraints

Bytefray 1.x has a documented compatibility contract that a routine change
must not break without a deliberate, separately-called-out decision:

- The `bytefray-rules-1` gameplay ruleset, Agent API version 1, result
  schema, and replay schema are versioned explicitly — see
  [docs/AGENT_API_V1.md](docs/AGENT_API_V1.md),
  [docs/RESULT_SCHEMA.md](docs/RESULT_SCHEMA.md), and
  [docs/REPLAY_SCHEMA.md](docs/REPLAY_SCHEMA.md).
- `battle2`, `battle-cli`, and `battle-agent-designer` are supported
  compatibility command aliases, not accidental leftovers.
- `BYTEFRAY_ROOT` is the preferred data-root variable; `BATTLE2_ROOT` and
  `BATTLE_ROOT` remain supported deprecated fallbacks, in that order.

See [AGENTS.md](AGENTS.md)'s "Compatibility requirements" section and
[docs/COMPATIBILITY.md](docs/COMPATIBILITY.md) for the full reference.

## Specs before implementation

For function-level engine/client work, [docs/specs/](docs/specs/) holds
specifications written *before* implementation. Check there for an existing
spec before inventing new behavior for a requested function. The optional
internal workflow this repository has used is: write or adjust a spec under
`docs/specs/`, open a "Function task" issue that links it (see
[.github/ISSUE_TEMPLATE/function_task.md](.github/ISSUE_TEMPLATE/function_task.md)),
implement it, add tests, and open a PR that references the issue. This
workflow is a convenience, not a requirement — see [AI tooling](#ai-tooling)
below.

## Branches and pull requests

- Keep PRs focused: one logical change per PR, with tests covering new or
  changed behavior.
- Run the test suite (and `ruff`/`mypy` for changed areas) before opening a
  PR; CI runs the headless suite on Python 3.10–3.13, builds and validates
  the pure wheel, and builds the Windows executables.
- Reference the issue a PR addresses, if one exists.
- Update [CHANGELOG.md](CHANGELOG.md) for user-visible changes.

## Reporting bugs

Open an issue at <https://github.com/libertaine/Bytefray/issues> with
reproduction steps, the Bytefray version (`bytefray --help` prints it, or
see the installed package version), and your platform. For anything you
believe is a security issue, see [SECURITY.md](SECURITY.md) instead of
opening a public issue.

## AI tooling

You do **not** need ChatGPT, Claude, Codex, Ollama, or any other AI tool to
contribute to Bytefray. The `docs/specs/` → issue → prompt → PR workflow
described above is an optional convenience some contributors (including the
maintainer) use; the `prompts/` directory and `tools/local_ai/` are
supporting tooling for that optional workflow, not requirements. A plain
patch with tests and a clear description is equally welcome. See
[docs/DEVELOPMENT_METHOD.md](docs/DEVELOPMENT_METHOD.md) if you're curious
how AI tooling factors into this project's own development process.
