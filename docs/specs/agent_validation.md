# agent_validation

**Module:** `engine/src/battle_engine/agent_validation.py` (new), with a
small, precisely-scoped reuse-enabling extraction inside
`engine/src/battle_engine/python_runtime.py` (see §5).
**Purpose:** `bytefray agents validate <agent-id>` — a controlled,
deterministic, single-tick dry run that answers "can Bytefray discover,
load, initialize, and successfully execute this agent's Agent API v1
contract?" without running a full match.

## 0. Relationship to v0.4

This is **Phase 2** of v0.4's Agent Authoring & Development Feedback Loop
theme (`ARCHITECTURE.md`'s "v0.4 direction": create → validate → test →
inspect → modify → repeat). Phase 1 (`docs/specs/agent_scaffold.md`,
implemented) added `bytefray agents create <agent-id>`. Nothing this
document describes is implemented yet; this is a specification only,
written before implementation per `CONTRIBUTING.md`'s spec → issue →
prompt → PR flow. `agents test` (development matches), GUI validation
affordances, and Agent API v2 are explicitly out of scope here (§12).

## 1. Purpose and non-goals

**Purpose.** Provide one CLI operation, `bytefray agents validate
<agent-id>`, that:

- discovers the agent by ID the same way `bytefray run`/`bytefray
  tournament` do (`battle_engine.agents.resolve_agent`);
- confirms it is a `kind: python` agent (Phase 2 validates Agent API v1
  Python agents only — see §9 for every other kind);
- loads it through the exact production loader
  (`battle_engine.agent_api.load_python_agent`);
- constructs one deterministic, documented `MatchContext` and calls
  `reset()` on a fresh instance, exactly as
  `battle_engine.python_runtime.PythonEntrantController` does before tick
  zero of a real match;
- constructs one deterministic, documented `Observation` and calls `act()`
  exactly once, then validates the returned action through the exact
  production validator (`battle_engine.python_runtime.validate_action`);
- reports one precise, typed, traceback-free result — success or the first
  failing stage — reusing the existing `RuntimeDiagnostic` model rather
  than inventing a second diagnostic taxonomy.

**Non-goals** (see also §12):

- Proving the agent is strategically sound, competitive, or free of
  later-tick failures, hangs, or timeouts (§8 states this boundary
  precisely — it is the semantic core of this spec, not a footnote).
- Running any part of a real match, multiple ticks, or more than one
  `act()` call.
- Static source linting, style checking, or type-checking the agent's code.
- Sandboxing or interrupting a non-returning `act()`/`reset()` call — no
  existing runtime facility does this today (`docs/AGENT_AUTHORING.md`'s
  "Not yet implemented" list), so Phase 2 does not invent one.
- A general validation framework for VM, blob, or Redcode agents (§9).

## 2. Existing building blocks this spec reuses

Inspected before writing this spec (all under `engine/src/battle_engine/`
unless noted):

- **`agents.py`** — `resolve_agent(root, name)` returns a validated
  `AgentSpec` or raises `SystemExit` for an unknown or path-escaping name
  (see `test_resolve_agent_rejects_a_name_that_escapes_the_agents_directory`
  in `engine/tests/test_agent_api.py`). `battle_engine.cli._resolve_agent`
  already catches this exact `SystemExit` from a library call
  (`cli.py:351`, `except SystemExit: spec_obj = None`) — validation reuses
  that same catch pattern rather than treating `SystemExit`-from-a-library
  as novel.
- **`agent_api.py`** — `load_python_agent(agent_spec)` is the single
  production entry point for import/factory/contract checking. It raises
  one of six `AgentValidationError` subclasses
  (`AgentManifestError`/`agent_manifest_invalid`,
  `UnsupportedAgentAPIVersionError`/`agent_api_version_unsupported`,
  `AgentSourceError`/`agent_source_invalid`,
  `AgentImportError`/`agent_import_failed`,
  `AgentFactoryError`/`agent_factory_failed`,
  `AgentContractError`/`agent_contract_invalid`), each already carrying a
  stable `.code`. `MatchContext` and `Observation` (both frozen
  dataclasses) are the exact types `AgentV1.reset`/`.act` are declared
  against — Phase 2 constructs real instances of these, not parallel
  validation-only types.
- **`python_runtime.py`** — the actual per-entrant lifecycle a real match
  runs:
  - `PythonEntrantController.__init__` calls `load_python_agent`, derives a
    per-entrant seed with `derive_agent_seed(match_seed, slot, agent_id,
    api_version)`, builds a `MatchContext`, and calls `instance.reset
    (context)` — catching `AgentValidationError` (stage `"load"`) and,
    separately, any `Exception` from `reset()` (stage `"reset"`, code
    `"agent_reset_failed"`), each wrapped as a
    `RuntimeDiagnostic`/`PythonEntrantInitializationError`.
  - `PythonEntrantController.run()`'s per-tick loop calls
    `instance.act(observation)`, catches `InvalidPythonActionError` from
    `validate_action(action)` (code `"agent_action_invalid"`) and any other
    `Exception` from `act()` itself (code `"agent_action_failed"`), both at
    stage `"action"`, via `self._forfeit(...)`.
  - `RuntimeDiagnostic` (frozen dataclass: `code`, `stage`, `message`,
    `agent_id`, `slot`, `exception_type`, `tick`, `action_slot`) is already
    the one structured-failure model used for both initialization failures
    and in-match forfeits (`match_service.py` reuses it too, for
    `PythonMatchExecutionError` and `UnsupportedMatchCompositionError`).
    It is general enough to carry a validation result unchanged — see §6.
  - `validate_action(action)` is the exact, already-public function
    (`__all__` includes it) that decides whether a returned `AgentAction`
    is acceptable. It has no side effects and does not require a live
    match/VM to call.
  - `derive_agent_seed` is the exact, already-public seed-derivation
    function. Reusing it for the validation fixture (§7) means the
    validation RNG is derived by the identical SHA-256 construction real
    matches use — not a second, independently-invented RNG scheme.
- **`match_service.py`** — `MatchEntrant.python(...)`,
  `NativeMatchService`, and `_run_python_match` show how a resolved
  `AgentSpec` becomes a running Python entrant end-to-end; confirms that
  nothing between `resolve_agent` and `PythonEntrantController` does
  additional contract checking Phase 2 would need to duplicate.
- **`command.py`** — `_agents(argv)` already special-cases a leading
  `"create"` token (Phase 1, implemented) and delegates to
  `battle_engine.agent_scaffold.main`. §3.2 extends the identical pattern
  for `"validate"`.
- **`agent_scaffold.py`** — the direct Phase 1 precedent for this spec's
  CLI shape, exit-code convention, stdout/stderr split, and
  `data_root`-parameterized library function. Phase 2 follows it, not a
  new convention.
- **Tests inspected:** `engine/tests/test_agent_api.py` (loader/diagnostic
  contract, containment regressions), `engine/tests/test_python_runtime.py`
  (`validate_action`/`apply_action`/forfeit-diagnostic coverage),
  `engine/tests/test_battle2_command.py` (subcommand dispatch, CLI
  subprocess idiom, Python-agent-match end-to-end tests, `agents` command
  tests), `engine/tests/test_agent_scaffold.py` (CLI test conventions and
  hand-built `MatchContext`/`Observation` fixture idiom this spec's own
  fixture builds on — see §7 for where it deliberately diverges).

## 3. Command/API surface

### 3.1 Exact CLI syntax

```text
bytefray agents validate <agent-id>
```

`battle2 agents validate <agent-id>` behaves identically (the existing
`battle2_main` deprecation-notice wrapper already applies uniformly).

### 3.2 Dispatch — extends `_agents`, mirroring Phase 1's `create`

```python
def _agents(argv: list[str]) -> int:
    if argv and argv[0] == "create":
        from battle_engine.agent_scaffold import main as scaffold_main
        return scaffold_main(argv[1:])
    if argv and argv[0] == "validate":
        from battle_engine.agent_validation import main as validate_main
        return validate_main(argv[1:])
    if argv == ["--help"] or argv == ["-h"]:
        return _simple_help("agents", ...)  # mentions list, create, validate
    if argv:
        parser = argparse.ArgumentParser(prog="bytefray agents", add_help=False)
        parser.error(f"unrecognized arguments: {' '.join(argv)}")
    from battle_engine.cli import main as engine_main
    return engine_main(["--list-agents"])
```

Bare `bytefray agents` and `bytefray agents --help`/`-h` are unchanged in
behavior (existing tests keep passing unmodified); only the help text
gains a one-line mention of `validate`. `battle_engine.agent_validation.
main(argv)` owns its own small `argparse` parser (`prog="bytefray agents
validate"`, one required positional `agent_id`, no other arguments in this
phase — see §12), mirroring `agent_scaffold._parser()` exactly.

`validate` is a verb on the agent catalog, the same conceptual level as
`create` and the bare-`agents` list — not a new top-level command, for the
identical reasoning `agent_scaffold.md`'s §3.2 already gives for `create`
(not repeated here).

### 3.3 Exit codes

| Condition | Exit code |
|---|---|
| Validation passes (all stages succeed) | `0` |
| `--help`/`-h` | `0` |
| Missing/extra positional arguments (argparse usage error) | `2` |
| Any validation failure — discovery, kind, load, reset, or act stage (§4) | `2` |
| Unexpected internal validation failure (§6's `validation_internal_error`) | `2` |

One exit code for every failure category, matching the uniform convention
already established by `agent_scaffold.md`'s §3.3/§13-decision-4 and by
every other existing subcommand's error path. No tooling in this
repository branches on a finer-grained code today, and Phase 2 has no
stronger case for inventing one than Phase 1 did.

### 3.4 stdout/stderr behavior

- **Success** prints to **stdout** only, four lines:

  ```text
  agent: <agent-id>
  status: valid
  api_version: <n>
  dry_run_action: <ACTION_KIND>[ operand=<operand>][ value=<value>]
  ```

  `operand`/`value` are included only for action kinds that carry them
  (matching the Action vocabulary table in `docs/AGENT_API_V1.md`) — e.g.
  `dry_run_action: WRITE operand=173 value=165` for a `WRITE`, but plain
  `dry_run_action: HALT` for a no-operand kind. This mirrors the
  `label: value` line shape `agent_scaffold.py`'s success output and
  `cli.py`'s match output already use.

- **Failure** prints a structured, traceback-free diagnostic to
  **stderr** only, four or five lines:

  ```text
  agent: <agent-id>
  status: invalid
  stage: <stage>
  code: <code>
  error: <message>
  ```

  plus an optional trailing `detail: <ExceptionType>` line when
  `RuntimeDiagnostic.exception_type` is set (omitted when the failure has
  no underlying exception, e.g. an unknown agent). Nothing is printed to
  stdout on failure — scripts can rely on stdout being validation-result
  content only when the exit code is `0`.

- **No progress output.** A dry run is one factory call, one `reset()`,
  and one `act()` — no spinner/streaming needed, matching
  `agent_scaffold.py`'s equivalent judgment.

## 4. Validation stages and failure semantics

Stages run strictly in order; the **first** failing stage stops
validation and is reported (§4.8 explains why this is not a multi-error
lint collector). Each stage below states exactly what it checks, what
existing code performs the check, and the `RuntimeDiagnostic` produced on
failure.

### 4.1 Discovery

Calls `battle_engine.agents.resolve_agent(root, agent_id)`.

- **Unknown / path-escaping ID:** `resolve_agent` raises `SystemExit`.
  Caught and converted to `RuntimeDiagnostic(code="agent_unknown",
  stage="discovery", message="Unknown agent '<agent-id>'. ...",
  agent_id=<agent-id>)`. The message reuses `resolve_agent`'s own
  `SystemExit` text (already user-facing and precise) rather than
  rewording it.
- **Manifest parse failure:** `resolve_agent` → `discover_agents_in` →
  `_spec_from_dir` can raise `AgentManifestError` directly (a malformed
  `agent.yaml`, wrong-typed field, etc.) before a `kind` is even known.
  This is caught here too (it is an `AgentValidationError`, handled
  identically to §4.3's load-stage catch) and reported as
  `stage="discovery"`, `code="agent_manifest_invalid"` (its own `.code`),
  since it happens strictly before this spec's kind check and is not yet
  a "load" in the `load_python_agent` sense — see §6 for why this one
  code can legitimately appear at two different stages depending on
  timing, and why that is not a taxonomy conflict. **As implemented:**
  this reuses `diagnose_load_failure` verbatim for the code/message, then
  relabels only the `stage` field via `dataclasses.replace(...,
  stage="discovery")` — not a second message-construction path.

### 4.2 Kind check

Given a resolved `AgentSpec`, requires `spec.kind == "python"`.

- **Non-Python kind** (`builtin` or `blob`): `RuntimeDiagnostic
  (code="agent_kind_unsupported", stage="discovery", message="Agent
  '<agent-id>' is kind '<kind>'; validation currently supports Python
  agents only.", agent_id=<agent-id>)`. See §9 for the full non-Python
  agent decision.

### 4.3 Manifest / entry point, 4.4 Import / factory, 4.5 Contract

These three stages the task requests are, in the current implementation,
**one indivisible call**: `battle_engine.agent_api.load_python_agent
(spec)`. It internally checks API version, entry-point syntax and
containment, source-file existence, module import, factory callability,
factory success, and returned-instance `reset`/`act` callability — each
already raising a distinct `AgentValidationError` subclass with its own
stable `.code` (§2). Phase 2 calls this exact function and does not
re-implement, reorder, or split its internal checks; splitting it into
three CLI-visible sub-stages would require either duplicating its control
flow or speculatively guessing where inside it a given failure occurred,
both of which this spec's "reuse real runtime contracts" requirement
rules out.

Reported as `RuntimeDiagnostic(code=<exc.code>, stage="load",
message=<normalized>, agent_id=<agent-id>, exception_type=<type(exc).
__name__>)` — identical `stage` and `code` values a real match's
`PythonEntrantInitializationError` already produces for the same
underlying failure (§5's extraction is what makes this identity exact,
not merely similar).

### 4.6 Reset

Builds one deterministic `MatchContext` (§7) and calls
`loaded.instance.reset(context)` on the fresh instance `load_python_agent`
just returned.

- **Exception during `reset`:** caught as `Exception` (not
  `BaseException` — `KeyboardInterrupt`/`SystemExit` propagate and abort
  the validation process, exactly as `python_runtime.py`'s own inline
  comment already justifies for the real controller). Reported as
  `RuntimeDiagnostic(code="agent_reset_failed", stage="reset",
  message="Python agent <agent-id> reset failed: <ExcType>: <msg>",
  agent_id=<agent-id>, exception_type=<type(exc).__name__>)` — the exact
  code, stage, and message template `PythonEntrantController.__init__`
  already uses.

### 4.7 Act dry-run

Builds one deterministic `Observation` (§7) and calls
`loaded.instance.act(observation)` exactly once.

- **Exception during `act`:** `RuntimeDiagnostic(code=
  "agent_action_failed", stage="action", message="Python agent <agent-id>
  act failed: <ExcType>: <msg>", agent_id=<agent-id>, tick=1,
  action_slot=0, exception_type=<type(exc).__name__>)`.
- **Returned value rejected by `validate_action`:** the *exact* function
  `battle_engine.python_runtime.validate_action`, imported and called
  unmodified. On `InvalidPythonActionError`: `RuntimeDiagnostic(code=
  "agent_action_invalid", stage="action", message="Python agent
  <agent-id> returned an invalid action: <msg>", agent_id=<agent-id>,
  tick=1, action_slot=0, exception_type="InvalidPythonActionError")`.

Both codes and the `stage="action"` value are identical to what a real
match's forfeit path produces for the same underlying agent behavior
(§11's equivalence test proves this directly, not just by code-reading).

### 4.8 Why fail-at-first-stage, not a multi-error collector

A real match's initialization is itself fail-fast: `load_python_agent`
raises on the first internal problem it finds, and
`PythonEntrantController.__init__` never attempts `reset()` after a load
failure. A validator that collected "every problem in the file" would
therefore sometimes report a `reset`-stage or `act`-stage finding for an
agent that could never have reached that stage in a real match (e.g. one
whose `reset()` also happens to be buggy but whose `load` already failed) —
misleading, and a second semantics layer the task explicitly warns against
inventing. Fail-at-first-stage is therefore not merely simpler, it is the
only stage ordering that stays truthful to what the runtime actually does.

### 4.9 Success

All five stages passing means exactly what §8 states precisely — the
agent was discoverable, loadable, reset successfully, accepted one
deterministic observation, and returned one action the current action
validator accepts. `ValidationResult(agent_id, api_version, dry_run_action)`
is returned (§6).

## 5. Reuse mechanics: the extraction this spec requires

`PythonEntrantController` currently builds each `RuntimeDiagnostic`
**inline**, mixed into per-entrant state/loop bookkeeping the validator has
no use for (VM construction, quota tracking, replay events, scoring).
Calling `load_python_agent`/`reset()`/`act()`/`validate_action` directly
is already safe and side-effect-free to reuse as-is (§2); the one thing
worth factoring out is the four inline diagnostic-construction sites, so
the *message templates* — not just the codes — are provably identical
between a real match's forfeit/initialization failure and a validation
failure, rather than two hand-synchronized copies that can drift.

Proposed minimal extraction, entirely inside `python_runtime.py` (adding
to its existing `__all__`, changing no existing signature or behavior):

```python
def diagnose_load_failure(
    exc: AgentValidationError, *, agent_id: str, slot: int = 0
) -> RuntimeDiagnostic: ...   # stage="load"; body = the dict literal
                              # currently inlined in __init__'s
                              # `except AgentValidationError` block

def diagnose_reset_failure(
    exc: Exception, *, agent_id: str, slot: int = 0
) -> RuntimeDiagnostic: ...  # stage="reset", code="agent_reset_failed";
                              # body = __init__'s `except Exception` block
                              # around instance.reset(context)

def diagnose_action_exception(
    exc: Exception, *, agent_id: str, slot: int = 0,
    tick: int, action_slot: int,
) -> RuntimeDiagnostic: ...  # stage="action", code="agent_action_failed"

def diagnose_invalid_action(
    exc: InvalidPythonActionError, *, agent_id: str, slot: int = 0,
    tick: int, action_slot: int,
) -> RuntimeDiagnostic: ...  # stage="action", code="agent_action_invalid"
```

`PythonEntrantController.__init__` and `_forfeit`'s two call sites in
`run()` are updated to call these four functions instead of constructing
`RuntimeDiagnostic(...)` inline — a pure refactor with unchanged output
(existing `test_python_runtime.py`/`test_battle2_command.py` assertions on
`.code`, `.stage`, and message substrings continue to pass unmodified,
since the extracted functions reproduce the exact current text).
`agent_validation.py` then imports and calls these same four functions,
so a validation diagnostic and a real-match diagnostic for the identical
underlying failure are constructed by the identical code, not merely
"the same shape by convention." This is the "smallest safe extraction"
the task's brief anticipates might be necessary — nothing else in
`python_runtime.py` needs to move or change.

## 6. Diagnostic model

**`RuntimeDiagnostic` is reused directly, unmodified.** It already has
every field this spec needs (`code`, `stage`, `message`, `agent_id`,
`exception_type`; `slot`/`tick`/`action_slot` are populated where
meaningful and left `None` otherwise, exactly as real-match diagnostics
already do for stages where they don't apply). No new diagnostic
dataclass is introduced, and no second taxonomy of codes is invented:
every code Phase 2 can produce is either an existing `AgentValidationError.
code` (§4.3–4.5), an existing `python_runtime.py` code reused verbatim via
§5's extraction (§4.6–4.7), or one of exactly two validation-only codes
that have no real-match analog because they describe conditions a real
match's request-building layer already prevents from reaching
`PythonEntrantController` at all:

| Code | Stage | When |
|---|---|---|
| `agent_unknown` | `discovery` | `resolve_agent` raises `SystemExit` (unknown/escaping ID). |
| `agent_kind_unsupported` | `discovery` | Resolved spec's `kind != "python"`. |
| `agent_manifest_invalid` | `discovery` | `AgentManifestError` raised by `resolve_agent` itself, before a kind is known (§4.1). |
| `agent_manifest_invalid`, `agent_api_version_unsupported`, `agent_source_invalid`, `agent_import_failed`, `agent_factory_failed`, `agent_contract_invalid` | `load` | `load_python_agent` (§4.3–4.5), identical to `PythonEntrantInitializationError`. |
| `agent_reset_failed` | `reset` | §4.6, identical to a real match's initialization failure. |
| `agent_action_failed`, `agent_action_invalid` | `action` | §4.7, identical to a real match's forfeit. |
| `validation_internal_error` | `internal` | Defensive catch-all (§6.1). |

`agent_manifest_invalid` legitimately appearing at both `discovery` and
`load` stages is not a taxonomy split: it is the same code describing the
same underlying problem (a broken manifest), observed at two different
points only because `_spec_from_dir` can itself raise it before this
spec's own kind check runs. A caller keying off `code` alone still gets
one stable meaning; only `stage` differs, and `stage` is documented here
precisely for that reason.

### 6.1 Unexpected internal validation failure

Any exception `agent_validation.py`'s own orchestration raises that is
**not** one of the typed exceptions above (a bug in this module, not the
agent under test) is caught once at the top of `validate_agent`/`main` and
reported as `RuntimeDiagnostic(code="validation_internal_error",
stage="internal", message=<normalized, bounded>, exception_type=<type
(exc).__name__>)` — never a raw traceback to stdout/stderr, matching every
other failure path's no-traceback requirement, but distinguishable by code
from an agent-authoring problem so a bug report can tell them apart.

### 6.2 No raw tracebacks

Every message text in §4 already reuses `python_runtime._safe_message`'s
existing whitespace-normalized, length-bounded formatting (via §5's
extracted functions) or `resolve_agent`'s already-concise `SystemExit`
text — Phase 2 introduces no new place where an exception's raw
`str()`/traceback could leak, and needs no new normalization helper.

## 7. Deterministic dry-run fixture

Two module-level constants and two small pure builder functions in
`agent_validation.py`, using the exact `MatchContext`/`Observation`
dataclasses from `agent_api.py` — no pseudo-match engine, no VM instance,
no Kernel:

```python
VALIDATION_AGENT_ID = "A"
VALIDATION_SEED = Config().seed          # 1337 -- the project's own default
VALIDATION_ARENA_SIZE = Config().arena_size  # 4096 -- the project's own default
VALIDATION_SLOT = 0

def build_validation_context(api_version: int, rng_seed: int) -> MatchContext:
    return MatchContext(
        agent_id=VALIDATION_AGENT_ID,
        seed=rng_seed,
        arena_size=VALIDATION_ARENA_SIZE,
        tick_limit=1,
        action_budget=1,
        rng=random.Random(rng_seed),
    )

def build_validation_observation() -> Observation:
    return Observation(
        tick=1,
        agent_id=VALIDATION_AGENT_ID,
        pc=0,
        register_a=0,
        register_p=0,
        zero_flag=False,
        last_read=None,
        alive=True,
    )
```

where `rng_seed = derive_agent_seed(VALIDATION_SEED, VALIDATION_SLOT,
VALIDATION_AGENT_ID, api_version)` — the *exact* production
seed-derivation function (§2), so the validation RNG stream is
constructed by the same SHA-256 scheme real matches use, just with fixed,
documented inputs instead of a real match's seed/slot.

**Why these exact values, and why they are not arbitrary:**

- `agent_id="A"` — **not** the agent's own discovery ID (e.g. `hunter`
  for `bytefray agents validate hunter`), and **not** a validation-only
  sentinel either. Traced through the real match path: `cli.py` builds
  `MatchEntrant.python("A", nameA, startA, pythonA)` — the discovery ID
  (`nameA`) goes into the entrant's `name` field, never into `agent_id`.
  `PythonEntrantController` copies `entrant.agent_id` straight into
  `PythonEntrantState.agent_id`, and every `Observation`/`MatchContext`
  built from that state carries `"A"` (or `"B"`), never the discovery ID.
  **No real match ever exposes an agent's own discovery ID to its own
  `reset()`/`act()`** — only the slot letter. An earlier draft of this
  spec used the discovery ID here, reasoning that an agent might
  legitimately branch on its own identity and deserved its real name;
  that was corrected after tracing the actual runtime path, since the
  discovery ID is a value the agent would *never* see in any real match,
  making it a fabricated identity in exactly the way the discovery-ID
  choice was trying to avoid. `"A"` is what a real match actually passes
  to slot A's Python entrant, so it is the faithful choice, not the
  synthetic one.
- `tick=1`, `pc=0`, `register_a=0`, `register_p=0`, `zero_flag=False`,
  `last_read=None`, `alive=True` are **exactly** the field values a fresh
  entrant's genuine first `act()` observation has in a real match: tick 0
  is published before any `act()` call (`PythonEntrantController.run`,
  `replay.publish_tick(0, ...)`), the real loop's first `act()` happens at
  `tick=1`; `pc` starts at `entrant.start & 0xFFFFFFFF` and `--a-start`'s
  own CLI default is `0`; every other field is `PythonEntrantState`'s
  un-mutated dataclass default. The validation fixture is therefore not
  "a plausible-looking observation" but a faithful reproduction of a real
  agent's actual first observation, justified field-by-field rather than
  chosen by convenience.
- `tick_limit=1`, `action_budget=1` describe the dry run honestly: exactly
  one `act()` call is ever made. An agent that reads `context.tick_limit`/
  `context.action_budget` during `reset()` sees the truth about this dry
  run, not a fabricated "pretend full match" budget.
- `arena_size`/`seed` reuse `Config()`'s own defaults for familiarity (an
  author who has run `bytefray run` with no `--arena`/`--seed` override has
  already seen these exact numbers) — not because either value has any
  other significance to a single-tick, no-arena-access dry run. `READ`/
  `WRITE` operands still wrap against `arena_size` inside `validate_action`
  /`apply_action`'s semantics, but Phase 2 never calls `apply_action` or
  touches an actual arena (§1 non-goals) — no VM is constructed, so a
  `WRITE`'s address/value are validated for *shape*, never actually
  written anywhere.
- **Determinism:** every input above is a fixed literal or a pure function
  of fixed literals plus `loaded.metadata.api_version` (itself fixed for a
  given agent's manifest). Two validations of the same agent source
  therefore always produce byte-identical `dry_run_action` output — this
  is asserted directly by a test (§11).

## 8. Semantic boundary (what "valid" does and does not mean)

Passing validation means exactly:

> The agent was discoverable, loadable, reset successfully, accepted one
> valid deterministic observation, and returned one action accepted by
> the current Agent API v1 runtime contract.

It does **not** mean:

- the agent is strategically correct or competitive;
- the agent cannot fail, forfeit, or behave unexpectedly on a later tick
  or a different observation;
- the agent cannot time out or hang (no timeout/process containment
  exists anywhere in this codebase yet — `docs/AGENT_AUTHORING.md`'s "Not
  yet implemented" list — and Phase 2 does not add one, per §12);
- the agent can participate in a mixed VM/Python match (unsupported for
  every Python agent today, not specific to validation);
- the agent's `act()`/`reset()` is sandboxed in any way (it runs the exact
  same unrestricted in-process Python a real match runs);
- the agent will complete, or even meaningfully begin, an entire match.

This boundary is stated verbatim (or near-verbatim) in the CLI `--help`
text and in the `docs/AGENT_AUTHORING.md` update (§13).

## 9. Non-Python agents

| Selector resolves to | Behavior |
|---|---|
| `kind: builtin` (a built-in VM agent, or a starter-populated manifest like `agents/runner/agent.yaml`) | `agent_kind_unsupported`, §4.2. Exit `2`. |
| `kind: blob` | `agent_kind_unsupported`, §4.2. Exit `2`. |
| Redcode/pMARS warrior | Redcode warriors are never entries under `<data_root>/agents/`; they are separate files passed to `bytefray run --mode redcode94 --red-a/--red-b` and never reach `discover_agents`/`resolve_agent` at all (`ARCHITECTURE.md`'s "run" description). Passing a Redcode filename or warrior name as `<agent-id>` therefore resolves as an **unknown agent** (`agent_unknown`, §4.1) — there is no separate "this looks like Redcode" detection, because nothing distinguishes it from any other unknown ID at this layer, and inventing such detection would be exactly the "static source linting" this spec excludes (§12). |
| Unknown ID | `agent_unknown`, §4.1. Exit `2`. |

Phase 2 does not pretend validation has meaning for any non-Python kind;
`agent_kind_unsupported`'s message says so explicitly rather than
attempting a VM- or Redcode-specific dry run this phase does not define.

## 10. Architecture placement

**New module: `battle_engine.agent_validation`.** Considered and rejected:

- **Inside `agent_api.py`:** `agent_api.py` is the *loading* boundary
  (manifest → instance), deliberately without runtime/lifecycle
  execution concerns (`reset`/`act` calling, RNG derivation, diagnostics)
  — those already live in `python_runtime.py`. Adding orchestration and a
  CLI-facing result type there would blur that existing boundary.
- **Inside `python_runtime.py`:** this module owns the *real match*
  lifecycle (VM, quota, replay events, scoring-adjacent state). Phase 2
  needs exactly four small reusable pieces of it (§5) and none of the
  rest; growing it with a second, match-shaped-but-not-a-match orchestrator
  would tangle two responsibilities the task explicitly asks to keep
  separate ("reuse... where practical" is not "merge into").
- **Inside `command.py`:** would grow the CLI dispatcher into business
  logic, which `AGENTS.md`'s "avoid growing `command.py` into business
  logic" guidance (echoed in this task's brief) directly rules out.
- **A small service object built from existing components, as its own
  module** (`agent_validation.py`) — **chosen.** It depends on
  `agent_api`, `agents`, and the four extracted `python_runtime` functions
  (§5), exactly mirroring `agent_scaffold.py`'s existing shape (a focused,
  independently-testable module with its own `main(argv)`, sitting beside
  its sibling Phase 1 module rather than inside any of the modules it
  reuses).

Public surface:

```python
@dataclass(frozen=True)
class ValidationResult:
    agent_id: str
    api_version: int
    dry_run_action: AgentAction

class AgentValidationFailedError(RuntimeError):
    """Validation stopped at the first failing stage; see .diagnostic."""
    def __init__(self, diagnostic: RuntimeDiagnostic): ...

def validate_agent(agent_id: str, *, data_root: Path | None = None) -> ValidationResult:
    """Raises AgentValidationFailedError; returns ValidationResult on success."""

def main(argv: list[str] | None = None) -> int: ...
```

`validate_agent`'s `data_root` parameter mirrors `agent_scaffold.
create_agent`'s exact pattern (defaults to `get_data_root()`, never
re-derives `BYTEFRAY_ROOT`/`BATTLE2_ROOT`/`BATTLE_ROOT` fallback logic).

## 11. Required tests

Location: `engine/tests/test_agent_validation.py` (co-located with the
other `battle_engine` CLI/catalog test modules; no `gui` marker).

**Successful validation**
- A Phase 1 `bytefray agents create`-scaffolded agent (built via
  `agent_scaffold.create_agent`, not hand-written) validates successfully:
  `status: valid`, `api_version: 1`, `dry_run_action` is a `WRITE` with
  `operand` in `range(256)` and `value == 0xA5`.
- A custom hand-written valid Python agent (arbitrary `reset`/`act`)
  validates successfully.
- Calling `validate_agent` twice against the same agent source produces
  byte-identical `ValidationResult.dry_run_action` (confirms §7's
  determinism claim).

**Discovery / kind failures**
- Unknown agent ID → `AgentValidationFailedError` with
  `diagnostic.code == "agent_unknown"`, `stage == "discovery"`; CLI exits
  `2`.
- A `kind: builtin` agent (e.g. a starter-populated `runner`) →
  `agent_kind_unsupported`, `stage == "discovery"`.
- A `kind: blob` agent → `agent_kind_unsupported`, `stage == "discovery"`.
- An agent whose `agent.yaml` is malformed (invalid `api_version` type,
  bad `kind` value, etc.) → `agent_manifest_invalid`, `stage ==
  "discovery"` (§4.1's earlier-than-load manifest failure path).

**Load-stage failures** (one test per `AgentValidationError` subclass,
each asserting `diagnostic.code` matches the exact existing `.code` and
`diagnostic.stage == "load"`):
- unsupported API version;
- missing/unparseable entry point;
- missing source file;
- import failure (syntax error and import-time exception);
- missing/non-callable factory;
- factory exception;
- factory result missing `reset`/`act`.

**Reset-stage failure**
- Agent whose `reset()` raises → `agent_reset_failed`, `stage == "reset"`,
  `exception_type` set, no traceback text in the message.

**Act-stage failures**
- Agent whose `act()` raises → `agent_action_failed`, `stage == "action"`.
- Agent whose `act()` returns a non-`AgentAction`, an unsupported kind, a
  malformed operand, or an extra/missing operand (parametrized over the
  same invalid-action cases `test_python_runtime.py` already covers for
  `validate_action`) → `agent_action_invalid`, `stage == "action"`.

**Equivalence with real runtime (the load-bearing test)**
- `battle_engine.agent_validation.validate_action is battle_engine.
  python_runtime.validate_action` — proves the act-dry-run step calls the
  literal production function, not a reimplementation.
- For one agent whose `act()` returns an invalid action: run it once
  through `NativeMatchService`/`PythonEntrantController` (a real,
  one-entrant-forfeits Python match) and once through `validate_agent`;
  assert both diagnostics have the same `code` (`"agent_action_invalid"`)
  and `stage` (`"action"`), and that both messages were produced by
  `diagnose_invalid_action` (§5) — not two independently-worded strings
  that happen to agree today.
- Equivalent test for an agent whose `reset()` raises: real-match
  `PythonEntrantInitializationError.diagnostic` vs. `validate_agent`'s
  `AgentValidationFailedError.diagnostic` — same `code`/`stage`, same
  message template.

**Custom data root**
- `validate_agent(agent_id, data_root=tmp_path)` and the CLI with
  `BYTEFRAY_ROOT` set both resolve under that root, not the default.

**No traceback for expected user errors**
- For every failure case above, assert the diagnostic `message` and the
  CLI's stderr output contain no `Traceback`/`File "`/multi-line stack
  text, and are within `_safe_message`'s existing length bound.

**CLI behavior**
- Success: exit `0`, stdout has exactly the four documented lines,
  stderr empty.
- Failure: exit `2`, stderr has the documented lines, stdout empty.
- `--help`/`-h`: exit `0`, usage text mentions `agent_id`.
- Missing positional argument: argparse usage error, exit `2`.
- End-to-end subprocess test (mirroring `test_agents_command_
  initializes_starters_idempotently`'s idiom): `python -m battle_engine
  agents create <id>` followed by `python -m battle_engine agents
  validate <id>` as two separate subprocess invocations succeeds.

## 12. Explicitly out of scope for Phase 2

- Full-match execution or anything resembling `agents test`.
- Performance benchmarking or timing measurement of `act()`/`reset()`.
- Sandboxing, process isolation, or a hard timeout for a non-returning
  callback (no such facility exists anywhere in this codebase yet).
- Static source linting or code-style checking of the agent's Python.
- Strategy analysis or any judgment about competitiveness.
- Multiple-tick simulation, or validating behavior across more than one
  observation.
- Any GUI validation control (the Designer is not touched by this spec).
- Redcode/pMARS validation tooling.
- Agent API v2.
- A `--data-root`/other CLI flag beyond the single positional `agent_id`
  (env-var override only, matching `agent_scaffold.py`'s precedent).

## 13. Documentation impact

`docs/AGENT_AUTHORING.md` implementation changes (not made by this spec
itself):

- A new short section, "Validate before running" (or similar), placed
  between "Recommended: scaffold a starting agent" and "Underlying file
  format", showing:

  ```bash
  bytefray agents validate my_agent
  ```

  with the success output shape from §3.4, and one sentence stating the
  §8 boundary ("this proves the agent's Agent API v1 contract is
  satisfied for one deterministic dry-run tick — it does not prove the
  agent will win, survive, or avoid failing on a later tick").
- The existing scaffold walkthrough's suggested next command changes from

  ```text
  Run 'bytefray run --a-type my_agent --b-type <opponent>' to try it.
  ```

  in prose (not the CLI's own printed hint, which stays as Phase 1
  specified it — changing printed CLI output is this spec's own
  implementation's concern, not a doc-only change) to describe the
  intended author workflow as **create → validate → run**, matching
  `ARCHITECTURE.md`'s "v0.4 direction" journey with the first two steps
  now real.
- `docs/AGENT_API_V1.md` is not changed: Phase 2 adds no new contract
  surface, only a new consumer of the existing one.

## 14. Design decisions needing human approval

1. **Resolved: `agent_id="A"` in the fixture (§7), not the agent's
   discovery ID and not a validation-only sentinel.** This spec originally
   proposed a fixed sentinel (`"validate"`), then — after human review
   asked why not use the agent's real discovery ID (e.g. `hunter`) so an
   agent that legitimately inspects its own identity sees something
   real — traced the actual runtime path. Neither the sentinel nor the
   discovery ID matches reality: `cli.py` builds `MatchEntrant.python
   ("A", nameA, startA, pythonA)`, and every `Observation`/`MatchContext`
   a Python entrant's `reset()`/`act()` ever receives carries the slot
   letter (`"A"`/`"B"`), never the discovery ID (`nameA`/`name`) and never
   a validation-only placeholder. `agent_id="A"` is therefore the one
   choice that is actually faithful to what a real match passes, settling
   both the original sentinel concern and the discovery-ID counter
   proposal at once. §7 reflects this.
2. **Resolved (approved, conditional): the four-function extraction
   inside `python_runtime.py` (§5).** Approved on the condition already
   stated in this spec — it must be genuinely behavior-preserving (every
   existing `test_python_runtime.py`/`test_battle2_command.py` assertion
   on `.code`/`.stage`/message text continues to pass unmodified) and must
   be covered by the §11 equivalence tests proving validation and
   real-match diagnostics are constructed by the identical extracted
   function, not merely matching by convention.
3. **`agent_manifest_invalid` appearing at both `discovery` and `load`
   stages depending on timing (§4.1, §6).** Not yet reviewed. An
   alternative is forcing every manifest problem through a single stage
   name regardless of when `_spec_from_dir` raises it, at the cost of a
   small amount of internal branching to normalize the stage label. Kept
   as two legitimate stages here because it is literally true to when the
   exception is raised; flagged in case a reviewer prefers one stage name
   for operational simplicity (e.g. simpler log-based alerting on
   `stage="load"` alone).
4. **Resolved (approved): `tick_limit=1`/`action_budget=1` in the fixture
   (§7)**, rather than echoing a real match's default `Config.
   instr_per_tick` (`8`). Approved as honestly constraining the dry run
   rather than overstating what it does.
5. **Resolved (approved): no `--data-root` CLI flag (§12)**, matching
   `agent_scaffold.py`'s existing precedent of env-var-only root override.
   Approved; use the existing environment/path system.
