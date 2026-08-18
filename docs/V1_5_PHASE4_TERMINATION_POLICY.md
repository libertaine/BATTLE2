# v1.5 Phase 4 — Ruleset-v1 termination policy centralization

This is the durable record of v1.5 Phase 4: moving the common Ruleset-v1
match **termination decision/reason** semantic behind the same policy seam
Phase 3 established for scheduling, while leaving each runtime's tick
lifecycle -- when it asks whether the match has ended -- exactly where it
was.

Phase 1 characterized the pre-refactor architecture and flagged this
duplication directly ([the Phase 1 baseline](V1_5_PHASE1_RULESET_V1_BASELINE.md)'s
"Match termination" ownership-table row and finding #2); Phase 2 unified
entrant scheduling into one shared implementation
([the Phase 2 record](V1_5_PHASE2_SCHEDULER_ABSTRACTION.md)); Phase 3 gave
that implementation one dispatch seam,
`battle_engine.ruleset_policy.RulesetPolicy`
([the Phase 3 record](V1_5_PHASE3_RULESET_POLICY_DISPATCH.md)), and
explicitly recommended termination as the next semantic to migrate through
it. Phase 4 does exactly that, and nothing else.

## Pre-refactor termination architecture

Before this phase, VM, unsupervised Python, and supervised Python each
computed the identical `alive_count == 0` / `== 1` / else rule **twice**,
at two different points in their own separately-maintained control flow:

1. A **mid-tick-loop decision check** -- purely `bool`, no reason -- that
   decides whether the runtime should keep ticking.
2. A **post-loop reason computation** -- the same three-way rule, re-derived
   from the same final alive count -- that decides what to report as
   `termination_reason` on the eventual result object.

| | VM | Unsupervised Python | Supervised Python |
|---|---|---|---|
| Decision predicate | `sum(1 for a in state.agents if a.alive) <= 1` | `sum(state.alive for s in self.states) <= 1` | identical to unsupervised |
| Decision location | `match.MatchRunner.run`, end of each tick body (after `_alive_prev` update, before the loop's next iteration) | `python_runtime.PythonEntrantController.run`, end of each tick body (after `replay.publish_tick`/verbose print) | `supervised_runtime.SupervisedPythonEntrantController.run`, identical position |
| Reason predicate | `not any(alive)` → `ALL_AGENTS_DEAD`; `elif sum(alive)==1` → `LAST_AGENT_STANDING`; `else` → `TICK_LIMIT` | identical three-way rule | identical three-way rule |
| Reason location | `match_service._build_result`, a **separate function**, called from `_run_vm_match` only after `Kernel.run()` (tick loop + summary + renderer result) has fully returned | inline in `PythonEntrantController.run`, immediately after the `finally: replay.close()` block and the final source-fingerprint recompute, still inside the same method as the tick loop | identical position in `SupervisedPythonEntrantController.run` |
| Reason values | `TerminationReason.{ALL_AGENTS_DEAD, LAST_AGENT_STANDING, TICK_LIMIT}` (imported from `python_runtime`) | same enum, defined in this module (pre-Phase-4) | same enum, imported from `python_runtime` |

**Predicates and reason labels were byte-identical across all three
paths** -- this was genuine duplication, not three subtly different rules
wearing the same names. The only real difference was *where in each
runtime's overall function* the two checks lived, driven by each runtime's
own structure (VM's reason computation lives outside `Kernel.run()`
entirely, in `match_service.py`, because that is where `NativeMatchResult`
is built from final `Kernel` state; both Python controllers build their
result object inline at the end of their own `run()`).

Neither predicate ever consulted the tick number or configured tick limit
directly. The `else`/`TICK_LIMIT` branch worked only because it is the
logical complement of the other two: by the time either check runs, the
match has already stopped ticking, so "not 0 alive, not 1 alive" can only
mean the configured tick limit was reached without a decisive alive count.
Phase 4's policy makes that implicit fact explicit -- see "Policy design"
below.

## Termination matrix

| Scenario | VM | Unsupervised Python | Supervised Python | Reason |
|---|---|---|---|---|
| >1 alive, below tick limit | continue | continue | continue | none |
| exactly 1 alive | stop | stop | stop | `LAST_AGENT_STANDING` |
| 0 alive | stop | stop | stop | `ALL_AGENTS_DEAD` |
| tick limit reached, >1 alive | stop | stop | stop | `TICK_LIMIT` |
| tick limit reached, exactly 1 alive | stop, `LAST_AGENT_STANDING` (alive-count check wins) | same | same | `LAST_AGENT_STANDING` |
| tick limit reached, 0 alive | stop, `ALL_AGENTS_DEAD` (alive-count check wins) | same | same | `ALL_AGENTS_DEAD` |
| Python forfeit leaves one alive | n/a | stop | stop | `LAST_AGENT_STANDING` (forfeit only changes `alive`; the reason is derived the same way as any other death) |
| Python forfeit leaves zero alive (mutual forfeit) | n/a | stop | stop | `ALL_AGENTS_DEAD` |
| HALT leaves one alive | stop (VM `HALT` opcode) | stop (Python `ActionKind.HALT`) | stop | `LAST_AGENT_STANDING` |
| all entrants halt/forfeit same tick | stop | stop | stop | `ALL_AGENTS_DEAD` |

**Precedence** (confirmed identical in all three runtimes, before and
after this phase): alive-count-based reasons always take priority over the
tick limit. A match that happens to reach its configured tick limit on the
exact same tick its last-but-one entrant dies is reported as
`LAST_AGENT_STANDING`/`ALL_AGENTS_DEAD`, never `TICK_LIMIT` --
`test_termination_precedence_prefers_alive_count_over_tick_limit`
(`engine/tests/test_ruleset_policy.py`) pins this directly at the policy
level.

**HALT and forfeit affect only liveness, never termination directly.** VM's
`HALT` opcode and Python's `ActionKind.HALT`/`forfeit_entrant` all do
exactly one relevant thing: set `alive = False` on the affected entrant
(`vm.py`'s `step`, `python_runtime.py`'s `apply_action`/`forfeit_entrant`).
None of them touch `termination_reason`, call into termination logic, or
know that a termination policy exists -- the policy only ever sees the
*resulting* alive count, never *why* an entrant died. This was already true
before Phase 4 and remains true after it; see "Semantic preservation"
below.

**Tick-0 initial-state publication, statistics, alive/territory scoring,
VM kill attribution, and replay/renderer publication all happen before the
termination check on the terminating tick**, in every runtime -- confirmed
directly by
`test_tick_lifecycle_checks_termination_after_renderer_publication`
(new this phase, extending Phase 1's
`test_tick_lifecycle_runs_in_the_documented_order_with_no_death`) for VM,
and by the unchanged Python/supervised tick loops (statistics → alive
scoring → territory scoring → replay publication → verbose print →
termination check, same relative order as before).

**Winner resolution is computed relative to termination reason differently
per runtime, and Phase 4 leaves this real, pre-existing asymmetry alone**:
VM's `Kernel.run()` computes `winner = resolve_winner(...)` immediately
after the tick loop returns, *before* `_build_result` (called later, from
`_run_vm_match`) computes `termination_reason`; both Python controllers
compute `termination_reason` first and `winner = resolve_winner(...)`
immediately after, within the same `run()` method. Neither order changed
in this phase, and nothing about winner resolution's own logic or timing
was touched.

## Policy design

**Module:** `engine/src/battle_engine/ruleset_policy.py` (same module
Phase 3 introduced for scheduling; termination is now its second tenant,
as Phase 3's own "Recommended Phase 4 boundary" anticipated).

```python
class TerminationReason(str, Enum):
    LAST_AGENT_STANDING = "last_agent_standing"
    ALL_AGENTS_DEAD = "all_agents_dead"
    TICK_LIMIT = "tick_limit"


@dataclass(frozen=True)
class TerminationDecision:
    terminated: bool
    reason: TerminationReason | None


class RulesetPolicy:
    ...
    def resolve_termination(
        self, *, alive_count: int, tick: int, max_ticks: int
    ) -> TerminationDecision:
        if alive_count == 0:
            return TerminationDecision(True, TerminationReason.ALL_AGENTS_DEAD)
        if alive_count == 1:
            return TerminationDecision(True, TerminationReason.LAST_AGENT_STANDING)
        if tick >= max_ticks:
            return TerminationDecision(True, TerminationReason.TICK_LIMIT)
        return TerminationDecision(False, None)
```

**Inputs**: exactly `alive_count: int`, `tick: int`, `max_ticks: int` --
the three integers Step 4 of the phase brief anticipated as sufficient, and
nothing more. `resolve_termination` receives no `Agent`, no
`PythonEntrantState`, no `Kernel`/controller reference, no runtime-kind
string, and no replay/scoring/statistics object. This is the same
"resulting match state, not runtime technology" boundary
`run_scheduler` already respected for scheduling.

**Output**: `TerminationDecision`, a small frozen dataclass with exactly
two fields. `reason` is `None` if and only if `terminated` is `False` --
callers that only need the continue/stop decision (the mid-tick-loop call
sites) read `.terminated` and ignore `.reason`; callers that need the
final reason (the post-loop call sites) read `.reason` after already
knowing (by construction -- the loop has exited) that `.terminated` is
`True`.

**Both existing call-site *shapes* are preserved, not merged into one.**
Each runtime still calls `resolve_termination` twice -- once per tick,
mid-loop, for the continue/stop decision, and once more, post-loop, for the
final reason -- exactly mirroring the pre-Phase-4 structure of "two
separate computations of the same rule, at two different points." This was
a deliberate choice: collapsing to one call site (e.g., by having the
mid-loop call cache its last decision for the post-loop code to read back)
would have meant threading new stored state through `Kernel`/`MatchState`,
a lifecycle change the phase brief's "Critical boundary" explicitly
disallows in spirit, for a savings of one redundant (and computationally
trivial) function call per match. The chosen design is the minimal one
that reaches the goal -- three duplicated *rule implementations* become
one -- without touching *when* either check runs.

**Why runtime-neutral**: `ruleset_policy.py`'s only non-stdlib imports
remain `battle_engine.rules` (for `BYTEFRAY_RULESET_ID`) and
`battle_engine.scheduler` (for `run_sequential_quota`/`StateT`), exactly as
Phase 3 left it. It still does not import or reference VM `Agent`,
`PythonEntrantState`, `Kernel`, either Python controller, `AgentAction`,
replay sinks, or any `"vm"`/`"python"` runtime-kind string.

## Reason representation

**Unchanged.** `TerminationReason` is still a `str`-subclassing `Enum`
with the exact same three members and the exact same string values
(`"last_agent_standing"`, `"all_agents_dead"`, `"tick_limit"`) it had
before this phase -- only its *defining module* moved, from
`battle_engine.python_runtime` to `battle_engine.ruleset_policy`.
`battle_engine.python_runtime.TerminationReason` (imported and re-exported
via `python_runtime.py`'s `__all__`, unchanged) and
`battle_engine.ruleset_policy.TerminationReason` are the exact same class
object -- confirmed directly (`TerminationReason is TerminationReason`
across both import paths, plus via `battle_engine.match_service` and
`battle_engine.supervised_runtime`'s own re-exports). Every existing
`from battle_engine.python_runtime import TerminationReason` import across
production code and tests continues to work unmodified; no serialization,
`.value`, or persisted `result.json`/replay content changed.

## VM integration

**Changed**: `match.MatchRunner.run`'s mid-tick-loop check
(`match.py`) now reads

```python
if self.ruleset_policy.resolve_termination(
    alive_count=sum(1 for agent in state.agents if agent.alive),
    tick=tick,
    max_ticks=max_ticks,
).terminated:
    break
```

in place of the inline `if sum(1 for agent in state.agents if agent.alive)
<= 1: break`. Nothing else in `MatchRunner.run`/`_execute_agents`/
`_attribute_deaths` changed -- same statement position (immediately after
the `_alive_prev` update, immediately before the loop's next iteration),
same variables read, same side effects (none beyond the `break`).

`match_service._build_result` (a separate function, unchanged in every
other respect) now computes the final reason via

```python
termination_decision = kernel.ruleset_policy.resolve_termination(
    alive_count=sum(agent.alive for agent in kernel.agents),
    tick=ticks_run,
    max_ticks=max_ticks,
)
```

in place of the inline ternary chain, using `kernel.ruleset_policy` (the
same `RulesetPolicy` instance `Kernel` already stored since Phase 3) and a
new `max_ticks: int` parameter threaded from `_run_vm_match`'s
`request.max_ticks` (the one piece of state `_build_result` did not
previously need, because the old ternary never consulted the tick limit
explicitly). `_build_result`'s signature is the only VM-side signature
change; every other parameter, every statistics/score/agent-result field,
and the function's call site in `_run_vm_match` are otherwise unchanged.

**Not changed**: `_execute_agents`, `_attribute_deaths`, kill scoring,
statistics, replay publication, renderer publication, `Kernel.run`'s
`resolve_winner`/`build_summary`/`renderer.publish_result` sequence, or any
VM-only mortality logic.

## Unsupervised Python integration

**Changed**: `python_runtime.PythonEntrantController.run`'s mid-tick-loop
check and post-loop reason computation both now call
`self.ruleset_policy.resolve_termination(...)` (the same `RulesetPolicy`
instance the controller already stored since Phase 3), at exactly the same
two statement positions the inline `sum(...) <= 1` check and the inline
`if/elif/else` reason block previously occupied. The local
`class TerminationReason(str, Enum)` definition (previously this module's
canonical home for the enum) was removed; the name is now imported from
`battle_engine.ruleset_policy` and re-exported exactly as before.

**Not changed**: `_execute_action_slot` (HALT/forfeit/exception handling),
`apply_action`, `forfeit_entrant`, event construction, trace-decision
recording, the `finally: replay.close()` block, the post-loop
`local_source_fingerprint_final` recompute (still runs *before* the
termination-reason call, exactly as before), or `resolve_winner`'s call
position relative to the (now policy-derived) reason.

## Supervised Python integration

**Changed**: identical shape to unsupervised Python --
`SupervisedPythonEntrantController.run`'s mid-loop check and post-loop
reason computation both now call `self.ruleset_policy.resolve_termination
(...)`, at the same two statement positions. The now-unused
`TerminationReason` import (previously imported from `python_runtime` only
to build the inline `if/elif/else`) was removed from this module's import
list; the name is still reachable through `python_runtime`'s re-export
wherever this module needs it (it no longer does, directly).

**Not changed**: `_run_one_action`, worker-handle timeout/exit/protocol-
error mapping onto `forfeit_entrant`, `_close_all_handles`, the
`finally: replay.close(); self._close_all_handles()` block, or the
post-loop fingerprint recompute.

## Lifecycle preservation

Confirmed directly, not just by absence of a diff:

- `test_tick_lifecycle_checks_termination_after_renderer_publication`
  (new, `engine/tests/test_scheduler_characterization.py`) instruments a
  duck-typed `RulesetPolicy` stand-in (a frozen dataclass instance cannot
  be monkeypatched in place, unlike the other collaborators Phase 1's
  order tests already spy on) and proves the VM termination check is still
  the *last* stage of every tick, after `replay_emit` and
  `renderer_publish`, extending Phase 1's own stage-order proof.
- `test_vm_termination_reasons_for_one_survivor_all_dead_and_tick_limit`
  (new, `engine/tests/test_native_match_service.py`) and the pre-existing
  `test_python_runtime.py::test_halt_and_tick_limit_have_explicit_
  termination_reasons`/`test_both_forfeits_are_ordered_and_have_no_false_
  kills`/`test_repeated_service_runs_reload_modules_and_do_not_leak_state`
  and `test_supervised_runtime.py::test_normal_supervised_match_completes`/
  `test_hung_act_forfeits_only_that_entrant` together exercise all three
  reasons on all three runtimes end-to-end, unchanged from before this
  phase (all passed both before and after the refactor).
- The unchanged golden corpus (`test_ruleset_v1_equivalence.py`, 8 tests,
  zero digest differences) transitively re-proves tick count, event
  ordering, and replay content are identical.

## Winner-resolution preservation

`results.resolve_winner` was not touched, imported differently, or called
from a different location in any runtime. Its call-site position relative
to termination-reason computation (VM: winner first, in `Kernel.run`,
reason later, in `_build_result`; both Python controllers: reason first,
winner immediately after, in `run`) is exactly the pre-existing asymmetry
documented above, left alone deliberately. No test's winner assertion
changed value.

## Semantic preservation

Explicitly confirmed via the full test run (see "Validation" below) and
the direct policy-level precedence tests:

- **One-survivor behavior**: unchanged (`LAST_AGENT_STANDING`, exact
  terminating tick unchanged, final replay/scoring unchanged -- proven by
  every pre-existing test above plus the new VM-level test).
- **All-dead behavior**: unchanged (`ALL_AGENTS_DEAD`).
- **Tick-limit behavior**: unchanged (`TICK_LIMIT`, only reached when
  neither alive-count condition holds).
- **HALT behavior**: unchanged -- HALT still only ever mutates `alive`.
- **Forfeit behavior**: unchanged -- `forfeit_entrant` still only ever
  mutates `alive`; termination reason is still derived from the resulting
  count, never from *why* an entrant died.
- **Termination precedence**: unchanged and now directly pinned by
  `test_termination_precedence_prefers_alive_count_over_tick_limit`.
- **Exact reason values**: unchanged (same enum, same strings, same class
  object across every import path).

## Identity preservation

- `BYTEFRAY_RULESET_ID`: unchanged (`rules.py` has no diff this phase).
- `derive_agent_seed`: unchanged (`python_runtime.py`'s seed derivation
  code was not touched).
- `canonical_match_id`/`_finalize_native_artifacts`: unchanged (neither
  function nor its call sites were touched; both still reference the
  literal `BYTEFRAY_RULESET_ID` constant, never a policy-derived value).
- `result_id`/`replay_id`: unchanged (both are pure functions of match
  identity and final result/replay content, neither of which changed).
- `replay_sha256`/replay equivalence: unchanged -- confirmed directly by
  the unchanged golden-corpus digests below.
- No new termination-policy identifier (class name, version, or otherwise)
  was serialized anywhere.

## Golden corpus

`engine/tests/test_ruleset_v1_equivalence.py`: **8 passed, zero Ruleset-v1
golden differences** -- all six pinned scenarios' `snapshot_sha256`/
`match_id`/`result_id` values are unchanged from the Phase 3 baseline.

## Tests added

- `engine/tests/test_ruleset_policy.py` (7 new tests):
  - `test_termination_continues_when_multiple_alive_below_tick_limit` --
    the continue case.
  - `test_termination_reports_last_agent_standing_when_exactly_one_alive`.
  - `test_termination_reports_all_agents_dead_when_none_alive`.
  - `test_termination_reports_tick_limit_when_multiple_alive_at_the_limit`.
  - `test_termination_precedence_prefers_alive_count_over_tick_limit`
    (parametrized, 2 cases) -- the competing-conditions case: alive-count
    reasons win over a simultaneously-true tick limit.
  - `test_termination_decision_is_immutable`.
- `engine/tests/test_scheduler_characterization.py` (1 new test):
  - `test_tick_lifecycle_checks_termination_after_renderer_publication` --
    proves the VM termination check still runs after every other per-tick
    stage, via a duck-typed `RulesetPolicy` stand-in (`_RecordingRulesetPolicy`)
    since the real, frozen `RulesetPolicy` cannot be monkeypatched in
    place.
- `engine/tests/test_native_match_service.py` (1 new test):
  - `test_vm_termination_reasons_for_one_survivor_all_dead_and_tick_limit`
    -- direct `NativeMatchResult.termination_reason` coverage for the VM
    path at the `NativeMatchService` boundary; previously only the golden
    corpus exercised VM termination, and every one of its three VM
    scenarios happens to end via `tick_limit`, so `last_agent_standing`/
    `all_agents_dead` were never directly proven for VM the way Python's
    `test_halt_and_tick_limit_have_explicit_termination_reasons` already
    proved them for Python.

No existing test was modified.

## Validation

**Focused** (policy/resolver + scheduler characterization + Python
scheduler characterization + Python runtime + supervised runtime + native
match service + match services + golden corpus, 91 tests before adding new
tests, 100 after): **all passed** both before touching source (confirming
the pre-refactor baseline) and after the full refactor plus new tests.

**Full suite** (`python -m pytest`): **1273 passed, 6 skipped, 2
deselected, 0 failures, 0 errors** -- exactly 9 more than Phase 3's
baseline (`1264 passed, 6 skipped, 2 deselected`), matching the 9 tests
added this phase (7 in `test_ruleset_policy.py`, 1 in
`test_scheduler_characterization.py`, 1 in `test_native_match_service.py`).
No pre-existing test's outcome changed.

**Static validation:**

- `ruff check .`: all checks passed.
- `mypy engine/src/battle_engine`: no issues found (59 source files, same
  count as Phase 3 -- termination logic moved into the existing
  `ruleset_policy.py`, no new source module).
- `mypy client/src/battle_client`: no issues found (10 source files,
  unchanged).

## Files changed

- `engine/src/battle_engine/ruleset_policy.py` -- adds `TerminationReason`
  (relocated from `python_runtime.py`, same values), `TerminationDecision`,
  and `RulesetPolicy.resolve_termination`.
- `engine/src/battle_engine/match.py` -- `MatchRunner.run`'s mid-tick-loop
  termination check now calls `self.ruleset_policy.resolve_termination`.
- `engine/src/battle_engine/match_service.py` -- `_build_result` gains a
  `max_ticks: int` parameter and now calls
  `kernel.ruleset_policy.resolve_termination` instead of an inline ternary
  chain; its one call site in `_run_vm_match` passes `request.max_ticks`.
- `engine/src/battle_engine/python_runtime.py` -- removes the local
  `TerminationReason` definition (now imported from `ruleset_policy`,
  still re-exported); both the mid-loop check and the post-loop reason
  computation in `PythonEntrantController.run` now call
  `self.ruleset_policy.resolve_termination`.
- `engine/src/battle_engine/supervised_runtime.py` -- identical shape for
  `SupervisedPythonEntrantController.run`; drops the now-unused
  `TerminationReason` import from `python_runtime`.
- `engine/tests/test_ruleset_policy.py` -- new direct `resolve_termination`
  unit tests (see "Tests added").
- `engine/tests/test_scheduler_characterization.py` -- new VM
  termination-check lifecycle-order test.
- `engine/tests/test_native_match_service.py` -- new direct VM
  `termination_reason` coverage.
- `docs/V1_5_PHASE4_TERMINATION_POLICY.md` (new, this document).
- `docs/ROADMAP.md` -- v1.5 section updated with Phase 4 status.

## Architectural debt intentionally left

- **Scoring** (`ScoringPolicy`) is still outside the Ruleset policy seam --
  called directly by `MatchRunner`/both Python controllers, unchanged by
  this phase.
- **Winner resolution** (`results.resolve_winner`) is still outside the
  policy seam, called directly by each runtime, at the same
  runtime-specific position relative to termination-reason computation as
  before.
- **Entrant-identity/execution-state separation** is still absent; `Agent`
  and `PythonEntrantState` remain exactly as Phase 1 classified them.
- **Runtime controllers remain distinct.** `PythonEntrantController` and
  `SupervisedPythonEntrantController` are still separately maintained,
  deliberately near-duplicate tick loops (per `supervised_runtime.py`'s own
  module docstring, unchanged this phase) -- Phase 4 routes two more lines
  in each through the shared policy without unifying the loops themselves.
- **Only Ruleset v1 exists.** `_RULESET_POLICIES` still has exactly one
  entry.
- **Mixed VM/Python execution remains unsupported** -- homogeneous
  composition validation in `NativeMatchService.run` is unchanged.
- **Remaining duplicated termination-*adjacent* code, intentionally not
  centralized because it is genuinely runtime-specific**: each runtime's
  own `sum(... for ... in ...)` alive-count expression (VM sums
  `Agent.alive` over `state.agents`; both Python controllers sum
  `PythonEntrantState.alive` over `self.states`) -- these read different
  concrete state-shapes and cannot be unified without either the policy
  taking runtime-specific state types (explicitly disallowed by the phase
  brief) or introducing the entrant-identity/execution-state
  unification that is Phase 5's job, not Phase 4's.

## Phase 4 verdict

**PHASE 4 COMPLETE — RULESET-v1 TERMINATION POLICY CENTRALIZED**

Bytefray's three previously-duplicated Ruleset-v1 termination
decision/reason computations (VM, unsupervised Python, supervised Python)
now delegate to one tested implementation,
`RulesetPolicy.resolve_termination`, reached through the same Phase 3
dispatch seam already used for scheduling. Every runtime still decides
*when* to ask the question, at exactly the same lifecycle position as
before; the policy only ever decides *what the answer is*, from three
plain integers. Zero golden differences, zero full-suite regressions, an
unchanged static-analysis baseline, and exactly the tests this phase added.

## Recommended Phase 5 boundary

**Entrant identity versus execution-state separation** remains the
strongest candidate, now that scheduling (Phase 3) and termination
(Phase 4) are both centralized behind `RulesetPolicy` and nothing else
Ruleset-owned is left duplicated across runtimes in a way a dispatch seam
could address: scoring and winner resolution are already single shared
implementations (never duplicated per runtime the way scheduling/
termination were), so routing them through the policy seam would be a
structural relocation with no duplication to eliminate, not a genuine
Phase-4-shaped win. Entrant identity/execution-state separation is
different in kind -- it is the one item on Phase 1's original architecture
list that has not been touched by any phase so far, and Phase 1's own
field-by-field classification (`Agent`, `PythonEntrantState`) is already
the input a Phase 5 could work from directly. Recommend Phase 5 scope
itself narrowly around that classification rather than opening scoring/
winner-resolution migration at the same time.
