# v1.5 Phase 2 — Ruleset-v1 scheduler abstraction

This is the durable record of v1.5 Phase 2: replacing the three duplicated
Ruleset-v1 entrant scheduling loops identified in
[the Phase 1 baseline](V1_5_PHASE1_RULESET_V1_BASELINE.md) (see its
"Findings / architectural hazards" §1) with one shared, narrowly-scoped
scheduler abstraction, with no change to Ruleset-v1 behavior.

Phase 1 is deliberately a *pre*-refactor snapshot and stays unmodified;
this document is the corresponding *post*-refactor record for the same
architecture area, following the same `V1_5_PHASE{n}_...` naming this repo
already established.

## What changed

A new module, `battle_engine.scheduler`
(`engine/src/battle_engine/scheduler.py`), holds one function:

```python
def run_sequential_quota(
    states: Iterable[StateT],
    quota: int,
    execute_slot: Callable[[StateT, int], None],
) -> None: ...
```

For each state in `states`, in iteration order: skip it entirely if it is
already not alive (`state.alive` is `False`). Otherwise call
`execute_slot(state, slot)` once per `slot` in `range(quota)`, rechecking
`state.alive` before each call and stopping -- without a further
`execute_slot` call -- the instant it becomes `False`. A state that dies
mid-quota receives no more opportunities that tick; later states are
unaffected and still receive their own full quota. `StateT` is bound to a
`Protocol` requiring only an `alive: bool` attribute, so the function
works unchanged against VM `Agent` and `PythonEntrantState` (used by both
Python controllers) without either being imported by the scheduler module.

This is intentionally the entire abstraction. It owns only "which state
gets the next execution opportunity, in what order, how many per tick, and
when to stop because it died." It has no knowledge of what an execution
opportunity *is* -- that is supplied entirely by the caller's
`execute_slot` callback -- and no knowledge of scoring, statistics,
replay, termination resolution, kill attribution, or which runtime it is
scheduling. `scheduler.py` imports nothing from `battle_engine` other than
the standard library; it is not imported by anything runtime-specific
either, only by the three call sites below.

## The three call sites, before and after

All three previously hand-rolled the identical shape: reset per-tick
accounting for every state, then for each state in order, if alive, call
an execution primitive up to `quota` times, stopping early if the state
dies. Each retains that per-tick accounting reset (`agent.cpu_used = 0` /
`state.cpu_used = 0`) locally, since it precedes the state-by-state pass
entirely and is not part of "which state gets the next turn."

### VM (`match.MatchRunner._execute_agents`, `match.py`)

`_execute_agents` now resets `cpu_used` as before, then defines a small
local `execute_slot(agent, slot)` that calls `state.vm.step(agent)` and
increments `agent.cpu_used`, and passes it to
`run_sequential_quota(state.agents, state.instr_per_tick, execute_slot)`.
Nothing else in `MatchRunner.run` -- tick-0 publication, per-tick stage
order (execute → statistics → alive scoring → territory scoring → death
attribution → replay → renderer → `_alive_prev` update → termination
check), or `_attribute_deaths` -- changed.

### Unsupervised Python (`python_runtime.PythonEntrantController.run`)

The entire per-slot body (observation construction, `act()` call, CPU/
action accounting, tracing, action application, HALT handling, and the
`InvalidPythonActionError`/`Exception` forfeit handling, including the
exact accounting-increment timing difference between the two exception
paths) moved verbatim, unchanged line-for-line, into a new method,
`_execute_action_slot(self, state, action_slot, tick, events)`. `run`
now resets `cpu_used` as before, then calls
`run_sequential_quota(self.states, self.config.instr_per_tick,
execute_slot)` with a small local `execute_slot` that forwards to
`_execute_action_slot` with the current tick's `tick`/`events` bound as
keyword-only defaults (needed only to satisfy both Ruff's B023
loop-variable-binding check and mypy's inference across the tick loop --
not a behavior change, since the callback is still invoked synchronously
within the same tick iteration it was defined in). Statistics, scoring,
replay publication, and termination-reason computation are untouched.

### Supervised Python (`supervised_runtime.SupervisedPythonEntrantController.run`)

Same shape as unsupervised. The pre-existing `_run_one_action` method
(worker invocation, timeout/exited/protocol-error mapping, diagnostics,
tracing, forfeit, accounting) is unchanged. `run` now resets `cpu_used`,
then calls `run_sequential_quota(self.states, self.config.instr_per_tick,
execute_slot)` with a local `execute_slot` that looks up the entrant's
`AgentWorkerHandle` from `self.handles` and forwards to `_run_one_action`.
The one incidental change: the handle lookup (`self.handles[state.
agent_id]`) now happens once per action slot instead of once per entrant,
since the scheduler's callback only receives `(state, slot)`. `self.
handles` is never mutated during a tick, so this has no observable effect
-- confirmed by the unchanged supervised-vs-unsupervised equivalence test.
The scheduler itself has no knowledge of processes, pipes, timeouts, or
worker crashes; all of that machinery remains entirely inside
`_run_one_action` and `AgentWorkerHandle`.

## What stayed exactly where it was

Per Phase 1's ownership table and tick-lifecycle sections, none of the
following moved:

- statistics recording (`StatisticsCollector`);
- alive/territory scoring (`ScoringPolicy`);
- VM kill attribution (`MatchRunner._attribute_deaths`, still VM-only --
  neither Python controller calls `score_kill` or `record_death(...,
  killer=...)`, unchanged from Phase 1);
- replay publication (`ReplayPublisher`) and renderer publication;
- termination-reason computation (still three separate, unconsolidated
  `alive_count == 0` / `== 1` / else blocks -- Phase 1's finding #2 was
  explicitly about this duplication and it remains open; the scheduler
  abstraction addresses only the entrant/quota loop, not termination);
- winner resolution (`results.resolve_winner`);
- the entrant-identity/execution-state field classification from Phase 1
  (`Agent`, `PythonEntrantState` are unchanged);
- all deterministic identity computation (`derive_agent_seed`,
  `canonical_match_id`, `result_id`, `replay_id`, `replay_sha256`).

## Validation

- New direct scheduler tests: `engine/tests/test_scheduler.py` (8 tests)
  -- sequential ordering, initial-dead skip, mid-quota mortality with no
  suppression of later states, quota-one, a non-default quota (5), slot
  index forwarding, and zero-quota (iterates states, executes no slots,
  matching the pre-existing behavior of `range(0)`/`range(negative)` in
  all three original loops -- none of the three callers validate
  `instr_per_tick` for the VM path, and both Python controllers already
  reject non-positive `instr_per_tick` at construction, so the scheduler
  intentionally does not add its own quota validation).
- Focused characterization re-run after integration, all passing
  unchanged: `test_scheduler_characterization.py` (VM),
  `test_python_scheduler_characterization.py` (unsupervised Python),
  `test_supervised_runtime.py` (including
  `test_supervised_and_unsupervised_controllers_agree_on_outcome`),
  `test_python_runtime.py`, `test_ruleset_v1_equivalence.py` (golden
  corpus), `test_match_services.py`, `test_replay_reconstruction.py`,
  `test_ownership_accounting.py`, `test_ruleset_persistence.py` -- 116
  tests, 116 passed.
- `ruff check .`: all checks passed.
- `mypy engine/src/battle_engine`: no issues found (58 source files, one
  more than Phase 1's 57 -- the new `scheduler.py`).
- `mypy client/src/battle_client`: no issues found (10 source files).
- Full suite (`python -m pytest`): **1253 passed, 6 skipped, 2
  deselected** -- exactly 8 more than Phase 1's baseline (`1245 passed, 6
  skipped, 2 deselected`), matching the 8 new scheduler tests added this
  phase. No pre-existing test's outcome changed.
- `test_ruleset_v1_equivalence.py` specifically: all six pinned scenarios'
  `snapshot_sha256`/`match_id`/`result_id` values are unchanged --
  **zero Ruleset-v1 golden differences**.

## Architectural debt intentionally left for later phases

- No Ruleset dispatch/registry exists yet; `BYTEFRAY_RULESET_ID` is
  untouched.
- Entrant-identity/execution-state separation is still not implemented;
  `Agent` and `PythonEntrantState` remain as classified in Phase 1.
- Termination-reason computation is still duplicated three ways (Phase
  1's finding #2), deliberately not consolidated in this phase to keep
  the diff limited to the scheduling loops.
- VM/Python kill-attribution asymmetry remains permanent, documented
  Ruleset-v1 behavior, not something this or a future phase should
  "normalize."
- `supervised_runtime.SupervisedPythonEntrantController` remains a
  deliberate near-duplicate of `PythonEntrantController` outside the now-
  shared scheduling loop; unifying their non-scheduling machinery (load/
  reset/act dispatch) was explicitly out of this phase's scope and is not
  recommended without its own dedicated risk/benefit review.

## Phase 2 verdict

**PHASE 2 COMPLETE — SAFE TO BEGIN RULESET/POLICY DISPATCH**

Three independently maintained copies of the same Ruleset-v1 sequential-
quota scheduling rule are now one tested implementation
(`scheduler.run_sequential_quota`), consumed identically by the VM,
unsupervised Python, and supervised Python execution paths. Everything
else Phase 1 characterized -- tick lifecycle, scoring, statistics, replay,
kill attribution, termination, winner resolution, and every deterministic
identity -- is unchanged, confirmed by the unchanged golden corpus and a
full-suite count that grew by exactly the tests added this phase.
