# v1.5 Phase 3 — Ruleset-v1 policy and dispatch seam

This is the durable record of v1.5 Phase 3: introducing an executable
Ruleset policy/dispatch seam for the already-frozen Ruleset v1, and routing
VM, unsupervised Python, and supervised Python entrant scheduling through
it, with no change to Ruleset-v1 behavior.

Phase 1 characterized the pre-refactor architecture
([the Phase 1 baseline](V1_5_PHASE1_RULESET_V1_BASELINE.md)); Phase 2
replaced three duplicated scheduling loops with one shared
`battle_engine.scheduler.run_sequential_quota`
([the Phase 2 record](V1_5_PHASE2_SCHEDULER_ABSTRACTION.md)). Phase 3 does
not touch that scheduler's behavior. It answers a narrower question Phase 2
deliberately left open: *how does runtime code obtain that scheduler*, and
*what happens if a Ruleset ID other than the one that exists is ever asked
for*. Before this phase, the answer to the first question was "each of the
three call sites imports `run_sequential_quota` directly," and there was no
answer to the second question at all -- nothing in the runtime path ever
consulted a Ruleset ID before executing gameplay.

## Existing Ruleset identity architecture, before this phase

`battle_engine.rules` is, and remains, the single frozen record of Ruleset
*identity*: the `BYTEFRAY_RULESET_ID = "bytefray-rules-1"` constant, a
finite historical-alias table (`_RULESET_ALIASES`/`normalize_ruleset_id`,
used only for recovering/attributing a Ruleset ID on old artifacts), and a
`RulesetProvenance` confidence vocabulary for that attribution. It is
deliberately dependency-free (standard library only) so the runtime,
artifact, and evaluation layers can all import it without an import cycle.

Before this phase, `BYTEFRAY_RULESET_ID` participated in exactly these
places, none of which changed this phase:

- `match_service.canonical_match_id` -- includes the literal constant as
  the `ruleset_id` field of the match-identity payload (persisted
  identity/deterministic identity).
- `match_service._finalize_native_artifacts` -- writes the literal constant
  into the replay header (`ReplayHeader.ruleset_id`) and the result
  envelope (`ResultEnvelope.ruleset_id`) (persisted identity).
- `replay.py`/`result_model.py` -- import the constant only to type/default
  those same persisted fields (persisted identity, no logic).
- `agent_evaluation.py` -- derives `EVALUATION_RULES_COMPATIBILITY_ID` from
  it for evaluation-artifact provenance (compatibility/provenance).
- `evaluation_history/comparison.py` -- uses `normalize_ruleset_id` to
  compare/attribute historical evaluation artifacts (compatibility/
  provenance).

Nothing in the runtime execution path (`Kernel`, `MatchRunner`,
`PythonEntrantController`, `SupervisedPythonEntrantController`) referenced
`BYTEFRAY_RULESET_ID`, `rules.py`, or any Ruleset concept at all -- the
three scheduling loops (Phase 2's shared `run_sequential_quota` call sites)
ran unconditionally, with no gate on which Ruleset was nominally in effect.
There was exactly one Ruleset and exactly one way to execute a match, so
this was never observably wrong, but it meant "Ruleset v1" was a
*persisted label*, not something the runtime ever actually consulted before
running.

## Policy design

New module: `engine/src/battle_engine/ruleset_policy.py`.

```python
@dataclass(frozen=True)
class RulesetPolicy:
    ruleset_id: str

    def run_scheduler(
        self,
        states: Iterable[StateT],
        quota: int,
        execute_slot: Callable[[StateT, int], None],
    ) -> None:
        run_sequential_quota(states, quota, execute_slot)


RULESET_V1 = RulesetPolicy(ruleset_id=BYTEFRAY_RULESET_ID)
```

`run_scheduler` is a generic *method* (its own `StateT` type variable,
matching `scheduler.run_sequential_quota`'s), not a stored callable field --
a stored field typed loosely enough to satisfy mypy across all three call
sites (`Agent`, `PythonEntrantState`, used identically by both Python
controllers) would have erased the per-call-site type checking `mypy
engine/src/battle_engine` currently gets for free at each of the three
integration points. A method preserves it: each call site is still checked
against its own concrete state type.

The policy exposes exactly one thing: Ruleset-v1's entrant scheduler. It
does not expose scoring, statistics, termination, winner resolution, or any
runtime-kind concept -- see "Runtime-selection boundary confirmation"
below.

**Dependency decisions.** `ruleset_policy.py` imports only
`battle_engine.rules` (for `BYTEFRAY_RULESET_ID`) and
`battle_engine.scheduler` (for `run_sequential_quota`/`StateT`), both
themselves standard-library-only. It sits one layer above both, forming the
split the Phase 3 brief suggested conceptually: `rules.py` stays the stable
identity/provenance record; `ruleset_policy.py` is the executable policy +
resolver built on top of it. Neither `rules.py` nor `scheduler.py` import
`ruleset_policy.py` or anything runtime-specific, so no cycle exists between
this module and `core.py`/`match.py`/`python_runtime.py`/
`supervised_runtime.py`/`match_service.py`, all of which now import
*upward* from `ruleset_policy.py` (never the reverse).

## Resolver design

```python
def resolve_ruleset_policy(ruleset_id: str) -> RulesetPolicy:
    try:
        return _RULESET_POLICIES[ruleset_id]
    except KeyError:
        raise UnknownRulesetError(ruleset_id) from None
```

`_RULESET_POLICIES` is a one-entry `Mapping[str, RulesetPolicy]` keyed by
the exact current `BYTEFRAY_RULESET_ID`. Only that exact string resolves.

**Historical aliases are deliberately not accepted here.**
`rules._RULESET_ALIASES`/`normalize_ruleset_id` map the one established
historical artifact-provenance alias (`"evaluation-rules-1"`) to
`BYTEFRAY_RULESET_ID` for *attributing* an old artifact's Ruleset identity.
That is a different question from "should a match requesting
`ruleset_id="evaluation-rules-1"` execute as Ruleset v1 today" -- no such
request path exists (no `MatchRequest`/`Config` field carries a Ruleset ID;
the runtime always executes under the one frozen identity), and
`resolve_ruleset_policy` does not consult `normalize_ruleset_id` or accept
that alias. `test_ruleset_policy.py` pins this directly: `"evaluation-
rules-1"` is in the parametrized unknown-ID list and raises
`UnknownRulesetError` exactly like `"bytefray-rules-2"` or `"unknown"`.
Runtime dispatch and historical-artifact interpretation are different
concerns; only the former is this resolver's job.

**Exception shape.** `UnknownRulesetError(LookupError)`, carrying the
rejected `ruleset_id` as an attribute. One small, specific exception type
for one resolver -- not a hierarchy.

## Runtime integration

**VM.** `match_service.NativeMatchService.run` resolves
`resolve_ruleset_policy(BYTEFRAY_RULESET_ID)` once (see "Where policy is
resolved" below) and passes it to `Kernel(..., ruleset_policy=policy)`.
`Kernel.run` passes `self.ruleset_policy` into `MatchRunner`'s new required
constructor parameter. `MatchRunner._execute_agents` now calls
`self.ruleset_policy.run_scheduler(state.agents, state.instr_per_tick,
execute_slot)` in place of the Phase 2 direct `run_sequential_quota(...)`
call -- same arguments, same local `execute_slot` closure, unchanged.
`Kernel.__init__` also accepts `ruleset_policy` as an optional
keyword-only parameter defaulting to the module-level `RULESET_V1`
singleton, so every existing direct `Kernel(...)` construction (production
and the many tests that construct one without a policy) is unaffected.

**Unsupervised Python.** `NativeMatchService.run` passes the same resolved
policy to `PythonEntrantController(..., ruleset_policy=policy)`, also an
optional keyword-only parameter defaulting to `RULESET_V1`.
`PythonEntrantController.run` calls
`self.ruleset_policy.run_scheduler(self.states, self.config.instr_per_tick,
execute_slot)` in place of the Phase 2 direct call. `_execute_action_slot`
and everything else in the tick loop (observation construction, tracing,
accounting, HALT, forfeit handling) is untouched -- the policy has no
visibility into any of it; it only receives the same `execute_slot`
closure Phase 2 already built.

**Supervised Python.** Identical shape:
`SupervisedPythonEntrantController(..., ruleset_policy=policy)`, same
default, same one-line replacement of the direct scheduler call with
`self.ruleset_policy.run_scheduler(...)` inside `run`. `_run_one_action`,
worker handles, timeouts, and diagnostics are untouched.

**Where policy is resolved.** `NativeMatchService.run` resolves the policy
exactly once, immediately after composition validation and before either
runtime path executes, then threads it as an explicit parameter through
`_run_vm_match`/`_run_python_match`/`_run_python_match_traced` to the
`Kernel`/controller constructor call. This is the one call site in
production code that actually calls `resolve_ruleset_policy` -- the
default-`RULESET_V1` parameters on `Kernel`/`PythonEntrantController`/
`SupervisedPythonEntrantController` exist for direct construction
(overwhelmingly: tests) to keep working unchanged, not as a second
production dispatch path. There is exactly one resolution per match, no
per-tick or per-action-slot re-resolution, and no global mutable state or
singleton mutation -- `RULESET_V1` is an immutable frozen dataclass
instance, and `resolve_ruleset_policy` reads from a module-level constant
mapping.

## Runtime-selection boundary confirmation

`RulesetPolicy` and `resolve_ruleset_policy` do not reference, import, or
know about `"vm"`/`"python"` branching, `Kernel`, `PythonEntrantController`,
`SupervisedPythonEntrantController`, `MatchEntrant.kind`, `AgentAction`, or
Python worker handles. The `if "python" in kinds: ... else: ...` branch in
`NativeMatchService.run` that selects which controller executes is
completely unchanged by this phase -- it still exists, still runs first,
and the resolved `RulesetPolicy` is simply handed to whichever runtime that
branch already decided to construct. Ruleset policy answers "what
scheduling rule applies," never "which runtime should run."

## Semantic preservation

Unchanged, confirmed by the unchanged golden corpus and unchanged focused
characterization tests: scheduler order and quota semantics (Phase 2's
`run_sequential_quota` is still the only scheduling implementation, called
with identical arguments); mortality/forfeit mid-quota stopping; VM-only
kill attribution (`MatchRunner._attribute_deaths` untouched); scoring
(`ScoringPolicy` untouched); statistics (`StatisticsCollector` untouched);
tick lifecycle (stage order in `MatchRunner.run` and both Python
controllers' `run` untouched); termination-reason computation (still the
same three separate `alive_count` blocks Phase 1 found duplicated --
deliberately not consolidated this phase); winner resolution
(`results.resolve_winner` untouched).

## Identity preservation

`canonical_match_id` and `_finalize_native_artifacts` still reference the
literal `BYTEFRAY_RULESET_ID` constant directly, exactly as before this
phase -- neither was changed to read `policy.ruleset_id` or any other
policy-derived value, per the Phase 3 brief's explicit guidance not to
couple artifact production to execution-policy objects without a clear
correctness reason (none existed here). Consequently:

- `match_id`/`result_id`/`replay_id` computation is byte-for-byte unchanged
  (same inputs, same `stable_id` calls).
- Python derived seeds (`derive_agent_seed`) are unchanged -- nothing in
  this phase touches seed derivation.
- `test_ruleset_v1_equivalence.py`'s six pinned scenarios' `snapshot_sha256`
  (which covers match/result identity, normalized replay bytes, winner,
  termination reason, tick count, score, and per-agent state) are unchanged
  -- see "Golden corpus" below.

## Unknown Ruleset behavior (fail-closed evidence)

`test_ruleset_policy.py::test_unknown_ruleset_id_fails_closed_rather_than_resolving_to_v1`
is parametrized over `"bytefray-rules-2"`, `"unknown"`,
`"evaluation-rules-999"`, `"evaluation-rules-1"` (the historical alias --
explicitly proven *not* special-cased here), and `""`; every one raises
`UnknownRulesetError` carrying the rejected ID, never returns `RULESET_V1`.

`test_native_match_service.py::test_unknown_ruleset_id_fails_closed_before_any_runtime_executes`
demonstrates this at the actual production call site: with
`match_service.resolve_ruleset_policy` monkeypatched to always raise,
`NativeMatchService().run(...)` propagates `UnknownRulesetError` and no
replay/result/summary artifact is written -- proving resolution sits before
`Kernel`/controller construction on the critical path, not merely available
and unused.

## Golden corpus

`engine/tests/test_ruleset_v1_equivalence.py`: **8 passed, zero Ruleset-v1
golden differences** -- all six pinned scenarios' `snapshot_sha256`/
`match_id`/`result_id` values are unchanged from the Phase 2 baseline.

## Tests added

- `engine/tests/test_ruleset_policy.py` (10 tests, new file):
  - `test_current_ruleset_id_resolves_to_the_v1_policy` -- resolving
    `"bytefray-rules-1"` returns the exact `RULESET_V1` singleton.
  - `test_resolved_policy_identity_matches_the_frozen_ruleset_id` -- the
    resolved policy's `ruleset_id` is exactly `BYTEFRAY_RULESET_ID`.
  - `test_ruleset_v1_singleton_identity_is_the_frozen_constant` -- same
    check directly against the module-level singleton.
  - `test_policy_scheduler_matches_the_phase_2_sequential_quota_behavior`
    -- `RulesetPolicy.run_scheduler` produces an identical call sequence
    (including mid-quota mortality) to calling
    `scheduler.run_sequential_quota` directly, protecting against the
    policy ever silently becoming a different scheduling rule.
  - `test_unknown_ruleset_id_fails_closed_rather_than_resolving_to_v1`
    (parametrized, 5 cases) -- see "Unknown Ruleset behavior" above.
  - `test_ruleset_policy_is_immutable` -- `RulesetPolicy` instances reject
    attribute mutation (`FrozenInstanceError`).
- `engine/tests/test_native_match_service.py`
  (`test_unknown_ruleset_id_fails_closed_before_any_runtime_executes`, 1
  new test) -- see "Unknown Ruleset behavior" above.

No existing test was modified.

## Validation

**Focused** (policy/resolver + scheduler + Phase 1/2 characterization +
runtime/identity/golden corpus, 143 tests): **143 passed**.

**Full suite** (`python -m pytest`): **1264 passed, 6 skipped, 2
deselected, 0 failures, 0 errors** -- exactly 11 more than Phase 2's
baseline (`1253 passed, 6 skipped, 2 deselected`), matching the 11 tests
added this phase (10 in `test_ruleset_policy.py` plus 1 in
`test_native_match_service.py`). No pre-existing test's outcome changed.
(One `test_default_python_agents.py` test hit a transient Windows
`PermissionError` renaming a temp file on one run of the full suite,
unrelated to any file this phase touches; it passed cleanly both in
isolation and on a clean re-run of the full suite, confirmed via a
`--junitxml` report showing `errors="0" failures="0"` with `tests="1270"`
non-skipped-inclusive count matching 1264 passed + 6 skipped.)

**Static validation:**

- `ruff check .`: all checks passed.
- `mypy engine/src/battle_engine`: no issues found (59 source files, one
  more than Phase 2's 58 -- the new `ruleset_policy.py`).
- `mypy client/src/battle_client`: no issues found (10 source files,
  unchanged).

## Files changed

- `engine/src/battle_engine/ruleset_policy.py` (new) -- `RulesetPolicy`,
  `RULESET_V1`, `UnknownRulesetError`, `resolve_ruleset_policy`.
- `engine/src/battle_engine/match.py` -- `MatchRunner` takes a required
  `ruleset_policy` constructor parameter; `_execute_agents` calls
  `self.ruleset_policy.run_scheduler(...)` instead of importing
  `run_sequential_quota` directly.
- `engine/src/battle_engine/core.py` -- `Kernel` takes an optional
  keyword-only `ruleset_policy` parameter (default `RULESET_V1`), stores
  it, and passes it to `MatchRunner`.
- `engine/src/battle_engine/python_runtime.py` -- `PythonEntrantController`
  takes an optional keyword-only `ruleset_policy` parameter (default
  `RULESET_V1`); `run` calls `self.ruleset_policy.run_scheduler(...)`
  instead of importing `run_sequential_quota` directly.
- `engine/src/battle_engine/supervised_runtime.py` -- identical shape for
  `SupervisedPythonEntrantController`.
- `engine/src/battle_engine/match_service.py` -- `NativeMatchService.run`
  resolves the Ruleset policy once via `resolve_ruleset_policy
  (BYTEFRAY_RULESET_ID)` and threads it through `_run_vm_match`/
  `_run_python_match`/`_run_python_match_traced` to the constructor calls
  above. No change to `canonical_match_id`, `_finalize_native_artifacts`,
  or any persisted-identity code.
- `engine/tests/test_ruleset_policy.py` (new) -- direct policy/resolver
  tests.
- `engine/tests/test_native_match_service.py` -- one added fail-closed
  service-level test.
- `docs/V1_5_PHASE3_RULESET_POLICY_DISPATCH.md` (new, this document).
- `docs/ROADMAP.md` -- v1.5 section updated with Phase 3 status.

## Architectural debt intentionally left

- **Scoring** (`ScoringPolicy`) is still outside the Ruleset policy seam --
  called directly by `MatchRunner`/both Python controllers, not through
  `RulesetPolicy`.
- **Termination-reason computation** is still duplicated three ways
  (`_build_result` and both Python controllers' `run`), unconsolidated
  since Phase 1's finding #2 -- unchanged by this phase.
- **Winner resolution** (`results.resolve_winner`) is still outside the
  policy seam, called directly by each runtime.
- **Entrant-identity/execution-state separation** is still absent; `Agent`
  and `PythonEntrantState` remain exactly as Phase 1 classified them.
- **Only Ruleset v1 exists.** `_RULESET_POLICIES` has exactly one entry;
  there is no Ruleset v2, no plugin mechanism, and no way to register a
  second Ruleset short of editing this module.
- **Mixed VM/Python execution remains unsupported** --
  `NativeMatchService.run`'s homogeneous-composition validation is
  unchanged.

## Phase 3 verdict

**PHASE 3 COMPLETE — RULESET DISPATCH FOUNDATION ESTABLISHED**

Bytefray now has an executable, fail-closed Ruleset-v1 policy seam
(`ruleset_policy.RulesetPolicy`/`resolve_ruleset_policy`), and the Phase 2
shared scheduler is obtained through that seam by all three execution
paths (VM, unsupervised Python, supervised Python) instead of being
imported directly. Runtime-kind selection remains entirely outside Ruleset
policy. Every Ruleset-v1 match remains identical to the Phase 2 baseline:
zero golden differences, zero full-suite regressions, and an unchanged
static-analysis baseline plus exactly the tests this phase added.

## Recommended Phase 4 boundary

Recommend Phase 4 focus on **migrating one additional narrow Ruleset-owned
policy behind the now-established dispatch seam** (most likely termination-
reason computation, since Phase 1 already identified and Phase 2
deliberately deferred its three-way duplication, and it is a pure function
of already-available state with no runtime-kind knowledge required) rather
than entrant-identity/execution-state separation. Justification: this
phase's `RulesetPolicy` is currently a one-method seam exercised by real
call sites; the fastest way to prove the seam generalizes -- and to keep
following this repo's own decision principle of not adding empty
future-facing hooks -- is to move a second real, already-characterized
semantic through it next, rather than opening the larger and structurally
unrelated entrant-identity/execution-state redesign before the dispatch
seam itself has more than one tenant. Entrant-identity/execution-state
separation remains a legitimate later phase, but is not blocked on or
blocking this one.
