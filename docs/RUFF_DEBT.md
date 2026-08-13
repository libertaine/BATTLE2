# Ruff Debt Strategy

Ruff was declared as a `dev` extra dependency from early in the project but
was never actually run as part of CI, and its `pyproject.toml` config was a
placeholder (`line-length`/`target-version` only, no `select`/`ignore`
decisions, literally commented `# Ruff (example)`). A post-1.0 maintenance
pass audited every finding under that unconfigured default and turned the
result into an enforced, documented configuration. This file records what
was found and why the current `[tool.ruff]`/`[tool.ruff.lint]` configuration
in `pyproject.toml` looks the way it does, so a future contributor doesn't
have to re-derive it before changing it.

## What was found

Running `ruff check .` under the (undocumented) default rule selection
produced 246 findings. After removing dead files identified by the same
maintenance pass (which accounted for some of them) and reviewing the rest
by rule code:

- **The large majority (194 of 225 remaining findings) were purely
  mechanical and safe**: `UP006`/`UP035`/`UP045`/`UP037`/`UP034` (PEP
  585/604 typing modernization for this project's Python 3.10+ floor),
  `I001` (import sorting), `F401` (unused imports), `PLR0402`/`PLR1730`,
  `SIM114`, `FURB122`, `PIE790`. These were applied via `ruff check . --fix`
  and verified against the full test suite, both `mypy` invocations, and a
  wheel build/`check_wheel.py` pass.

- **One of those "safe" auto-fixes was not actually safe**: `ruff --fix`'s
  `F401` pass deleted `battle_engine/core.py`'s entire compatibility
  re-export block (`Weights`, `HALT`, `NOP`, `ADD`, etc. — see AGENTS.md's
  "Compatibility surfaces are deliberate, not accidental"), because nothing
  *within that file* references those names; their only purpose is being
  importable *from* `battle_engine.core` by other modules. This broke 12
  test modules' imports immediately (caught by running the full suite
  before committing, not by ruff itself). The fix was adding an explicit
  `__all__` to `core.py` listing every re-exported name — this tells
  pyflakes/ruff the imports are intentional, and is now the required
  pattern for any future facade-style module in this codebase. Check
  `git log`/`docs/PROJECT_HISTORY.md` for the incident if this pattern
  needs re-explaining.

- **A handful of small, safe fixes needed manual (not `--fix`) attention**:
  `UP022` (`subprocess.run(stdout=PIPE, stderr=PIPE)` → `capture_output=True`,
  5 test-file instances, behavior-identical per the stdlib docs), `C408`
  (`dict(...)` → `{...}` literal, 5 instances in
  `tournament/scripts/btctl.py`), one `RUF012` (a test double's
  intentionally-shared mutable class attribute, annotated `ClassVar`
  instead of restructured), and one `PLR0402`/import-alias cleanup that
  `--fix` picked up in a later pass.

- **A cluster of findings reflect a deliberate, pre-existing codebase
  pattern that the rule set doesn't fit, not oversights**: `BLE001`
  (blind-except) and `S110` (try/except/pass) fire on `except Exception:
  pass` blocks that are individually documented in-place as intentional —
  e.g. `battle_engine/core.py`'s `Kernel.run` ("v0.1 compatibility: summary
  persistence failures were suppressed") and
  `battle_engine/telemetry.py`'s renderer teardown ("optional final
  renderer pages never fail a match"). Several call sites already carried
  hand-added `# noqa: BLE001` comments from before this audit, which is
  independent confirmation that this is an established project convention,
  not an unreviewed gap. `TRY004` (prefer `TypeError` over `ValueError` for
  one type check in `battle_engine/agents.py`) was excluded for the same
  reason it wasn't hand-fixed: changing a raised exception's type is a
  behavior change for any caller catching the original type, not a lint
  fix. These three codes (`BLE001`, `S110`, `TRY004`) are now in
  `[tool.ruff.lint].ignore` project-wide, with the same rationale repeated
  as a comment there.

- **A few one-off false positives got a targeted inline `# noqa: <CODE>`**
  instead of a project-wide ignore, because the underlying rule is
  otherwise a good fit for this codebase: `S102` (`exec()` use) on
  `engine/tests/test_windows_packaging_spec.py`'s deliberate introspection
  of the repo's own trusted `.spec` files; `PYI034` (`__enter__` should
  return `Self`) on `TraceWriter.__enter__`, left as `TraceWriter` rather
  than `typing.Self` because `Self` requires Python 3.11+ and this
  project's runtime floor is 3.10; `SIM115` (open a file via context
  manager) on `JSONLSink.__init__`, which deliberately holds a file handle
  open across the sink object's lifetime, closed by its own `close()`.

- **Frozen/dead code was excluded from linting entirely, not fixed**:
  `_legacy/core.py`, `agents.py`, `main.py`, `renderers.py`,
  `agents_tooling/`, and `app/match_runner.py` are documented dead code
  (AGENTS.md's "Architecture boundaries") kept for compatibility/historical
  reasons, not under active maintenance. They're listed in
  `[tool.ruff].extend-exclude`. `_legacy/tests/` is deliberately **not**
  excluded — it's an active suite that `pytest.ini`'s `testpaths` still
  runs against the packaged engine.

## Current state and how it's enforced

`ruff check .` is clean (`All checks passed!`) as of this pass and is now a
required step in `.github/workflows/ci.yml`'s `test-linux-core` job, so new
findings fail CI rather than silently accumulating the way this batch did.
`ruff`'s default (broad, multi-plugin) rule selection is otherwise left
as-is rather than pinned to an explicit `select` list — narrowing it further
wasn't warranted by anything found in this audit, and pinning a `select`
list is easy to add later if a real reason shows up.

## If you hit a new finding

1. If it's a real, safely-fixable issue: fix it (via `--fix` if the fix is
   mechanical, by hand if not) and run the test suite.
2. If it's a false positive specific to one line: add `# noqa: <CODE>` with
   a one-line reason, the same way the instances above are documented.
3. If you're about to add `BLE001`/`S110`/`TRY004` to a *new* piece of code
   because it matches this project's existing "documented, intentional
   broad-except" pattern: that's fine, that's exactly why those three codes
   are ignored project-wide — but the *documentation* (the comment
   explaining why the exception is being suppressed) is still expected,
   the same way every existing instance has one.
4. If you think a whole rule code doesn't belong in this project at all:
   don't just add it to `ignore` — update this file's rationale too, so
   the next person doesn't have to re-derive why.
