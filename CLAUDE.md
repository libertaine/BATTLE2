# Claude Code Guidance

Follow [AGENTS.md](AGENTS.md) — it's the authoritative, tool-agnostic guide to
this repository's architecture boundaries, testing expectations, supported
environments, release/build constraints, compatibility requirements, and Git
safety rules. This file only adds guidance specific to working here through
Claude Code.

## Environment specifics

- Primary development platform here is **Windows**, with PowerShell as the
  default shell tool and Bash (Git Bash) also available — pick whichever
  matches the command's native syntax rather than mixing quoting styles.
- The active virtualenv is `.venv/` at the repo root. Don't create a second
  one (e.g. `venv/`) alongside it.
- `pytest`/`mypy` cache and temp directories are intentionally repo-local
  (`.pytest-cache/`, `.pytest-tmp/`) rather than OS defaults — see
  AGENTS.md's testing section before touching `pytest.ini`.

## Repo-specific things to double-check before editing

- Check whether a name that looks unused is actually a retained compatibility
  surface (`battle_engine.core` re-exports and stable protocol identifiers,
  for example) before removing it — AGENTS.md's "Compatibility
  requirements" section lists the ones that come up most.
- `docs/specs/` holds the specs that are meant to be written *before*
  implementation for function-level tasks (see CONTRIBUTING.md's
  spec → issue → prompt → PR flow). Check there for an existing spec before
  inventing new behavior for a requested function.
