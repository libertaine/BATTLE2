# v1.5 Phase 1 — Ruleset-v1 semantic ownership map and architecture baseline

This is the durable record of the v1.5 Phase 1 audit: a pre-refactor
behavioral baseline for Bytefray Ruleset v1, built before any v1.5
architecture work (Ruleset/policy dispatch, entrant identity vs.
execution-state separation, scheduler abstraction) begins. Phase 1 itself
implements none of that architecture — it locates and characterizes the
current implementation so later phases can move code without rediscovering
behavior.

This document complements, and deliberately does not duplicate,
[RULES.md](RULES.md) (what Ruleset v1 means) and
[COMPATIBILITY.md](COMPATIBILITY.md) (which compatibility axis a change
belongs to). Its job is narrower: for each Ruleset-v1 semantic, *where* it
is currently implemented, whether it is duplicated between runtimes,
whether it is protected by a test, and what the v1.5 architecture must not
break while moving it.

## Architecture path overview

Three execution paths exist, all reached through
`match_service.NativeMatchService.run`:

- **VM path**: `NativeMatchService.run` → `match_service._run_vm_match` →
  `core.Kernel` (spawns agents, owns `vm.VM`, `rng`, `score`, `stats`) →
  `match.MatchRunner.run` (the tick loop) → `vm.VM.step` per instruction.
- **Python path (unsupervised)**: `NativeMatchService.run` →
  `match_service._run_python_match` →
  `python_runtime.PythonEntrantController` (owns its own `vm.VM` instance,
  `score`, `statistics`, and a private copy of the tick loop) → each
  entrant's `reset()`/`act()` called in-process.
- **Python path (supervised)**: selected only when
  `MatchRequest.agent_call_timeout` is set (Agent Lab development tooling;
  `bytefray run`/`tournament` never set it —
  `match_service.py:71-80`) → `supervised_runtime.
  SupervisedPythonEntrantController`, a **deliberate, reviewed near-copy**
  of `PythonEntrantController`'s tick loop (see its module docstring,
  `supervised_runtime.py:1-24`) that relocates only `load`/`reset`/`act`
  into a per-entrant worker subprocess via `agent_worker.AgentWorkerHandle`,
  with a per-call timeout.

All three converge again in `match_service._finalize_native_artifacts`,
which computes canonical `match_id`/`result_id`, writes the canonical
`replay.jsonl` (schema 3) and `result.json` (`battle2.result` v1), and is
itself runtime-agnostic — it reads a `NativeMatchResult` built by
runtime-specific `_build_result`/`_build_python_result` adapters.

Both Python controllers share `python_runtime.apply_action` (action
semantics), `python_runtime.derive_agent_seed` (RNG derivation), and
`results.resolve_winner`/`scoring.ScoringPolicy`/`statistics.
StatisticsCollector` (shared with the VM path too) — see "Duplication" in
the ownership table below for exactly what is and is not shared.

## Ruleset-v1 semantic ownership table

| Semantic | Current owner | Duplicated? | Tested? | Likely v1.5 owner |
|---|---|---|---|---|
| Arena model (circular byte array, modulo addressing) | `vm.VM` (`arena`, `_rd32`, `_wr8`) | One implementation; both runtimes' Python `READ`/`WRITE` (`python_runtime.apply_action`) and the VM's `LOAD`/`STORE`/`LOADI`/`STOREI` route through the same `VM` instance each controller owns | Yes — `test_ownership_accounting.py`, golden corpus | Stays with a `VM`-shaped core; not scheduler-owned |
| Ownership/last-writer tracking | `vm.VM._wr8` + `ownership_counts` | One implementation, shared by both runtimes | Yes — `test_ownership_accounting.py` | Same as arena |
| VM opcode execution (12 opcodes, invalid-opcode death) | `vm.VM.step` | VM-only; no Python analogue | Yes — `test_scheduler_characterization.py`, golden corpus | VM-runtime-owned |
| Python action semantics (`NOP`/`SET_A`/…/`WRITE`/`HALT`) | `python_runtime.apply_action` | One implementation, **shared** by both Python controllers (`supervised_runtime` imports it directly rather than reimplementing it — `supervised_runtime.py:53-71`) | Yes — `test_python_runtime.py::test_every_action_has_defined_state_and_arena_semantics`, `test_supervised_and_unsupervised_controllers_agree_on_outcome` | Python-runtime-owned |
| Scheduling order (spawn/request order, sequential) | `match.MatchRunner._execute_agents` (VM); `PythonEntrantController.run`'s tick loop (Python); `SupervisedPythonEntrantController.run`'s tick loop (supervised) | **Three separately maintained loops**, not one shared scheduler — see "Findings" below | Yes — `test_scheduler_characterization.py` (VM), `test_python_scheduler_characterization.py` (Python, added this phase) | The named v1.5 "scheduler abstraction" target |
| Action/instruction quota (`instr_per_tick`) | Same three loops as scheduling order | Same three implementations | Yes — same tests as scheduling order | Same as scheduling order |
| Mid-quota death/forfeit stops remaining quota | `match.MatchRunner._execute_agents`'s `if not agent.alive: break` (VM); the equivalent `if not state.alive: break` in each Python loop | Same three implementations | Yes — `test_scheduler_characterization.py::test_dead_entrant_is_skipped_on_later_ticks`, `test_python_scheduler_characterization.py::test_forfeited_entrant_is_skipped_on_later_ticks_and_next_entrant_still_gets_full_quota` | Same as scheduling order |
| CPU/action accounting (`cpu_used`, `total_actions`) | `agent_state.Agent.cpu_used` (VM); `PythonEntrantState.cpu_used`/`total_actions` (Python) | Parallel fields, not shared, but semantically identical: one unit per opcode/callback attempted, including a step that kills the entrant | Yes — `test_scheduler_characterization.py::test_dead_entrant_cpu_total_stops_after_death` | Execution-state field either way |
| Survival scoring | `scoring.ScoringPolicy.score_alive` | One implementation, shared by both runtimes via the `HasAgentIdentity`-shaped protocol (`scoring.py` takes `list[Agent]`, called with `PythonEntrantState` objects too — see `python_runtime.py:674`) | Yes — golden corpus, `test_match_services.py` | Scoring-service-owned |
| Territory scoring | `scoring.ScoringPolicy.score_territory` | Same as survival scoring | Yes — golden corpus, `test_match_services.py` | Same as survival scoring |
| Kill scoring/attribution | `scoring.ScoringPolicy.score_kill`, invoked only from `match.MatchRunner._attribute_deaths` | **VM-only in practice.** Nothing in either Python controller ever calls `score_kill` or `statistics.record_death(..., killer=...)` — Python deaths (`forfeit_entrant`, HALT) never attribute a killer. This is documented Ruleset-v1 behavior (`docs/RULES.md`'s "No Python kill attribution"), not an oversight | Yes — `test_match_services.py::test_kernel_attributes_kill_to_memory_owner` (VM), `test_python_runtime.py`'s forfeit tests assert `kills == 0` (Python) | Kill attribution stays VM-specific; a shared scheduler must not invent Python kill attribution |
| Statistics (alive ticks, CPU/writes, kills/deaths, territory last/max/sum) | `statistics.StatisticsCollector` | One implementation, shared by both runtimes the same way scoring is | Yes — golden corpus, `test_match_services.py` | Statistics-service-owned |
| Winner resolution | `results.resolve_winner` | One implementation, explicitly documented as shared (`results.py:39-45`) | Yes — `test_match_services.py::test_winner_resolution_preserves_survival_score_fallback_and_ties`, golden corpus | Stays shared |
| Match termination (all dead / one left / tick limit) | Computed identically but **redundantly** in `match_service._build_result` (VM) and inline at the end of both Python controllers' `run` (`alive_count == 0`/`== 1`/else) | Three separate `if/elif/else` blocks computing the same `TerminationReason` from the same three-way alive-count condition | Yes — golden corpus, `test_python_runtime.py::test_halt_and_tick_limit_have_explicit_termination_reasons` | Candidate for consolidation without behavior change |
| Tick-0 initial-state publication | `match.MatchRunner.run` (VM, before the tick loop); each Python controller's `run` (before its own tick loop) | Two implementations, same shape: publish once, before any action | Yes — `test_replay_reconstruction.py` (both runtimes) | Replay-publication concern, not gameplay |
| Ruleset identity (`BYTEFRAY_RULESET_ID`) | `rules.py` (dependency-free) | One value, consumed by `match_service.canonical_match_id`/`_finalize_native_artifacts`, `replay.py`, `result_model.py` | Yes — `test_rules.py`, `test_ruleset_persistence.py` | Stays a single frozen identity module |

## Tick lifecycle

### VM (`match.MatchRunner.run`, `match.py:41-88`)

Before the loop: `replay.publish_header`, `renderer.start()`, then
`replay.publish_tick(0, ...)` publishing tick 0 using whatever
`vm.tick_diffs` code-loading already left behind.

Per tick, in this exact order:

1. `state.tick = tick`
2. `state.vm.clear_tick_diffs()`
3. `self._execute_agents()` — resets every agent's `cpu_used` to 0, then
   for each agent in spawn order, up to `instr_per_tick` `vm.step` calls,
   stopping early if the agent dies mid-quota
4. `self.statistics.record_tick(...)` — alive ticks, cumulative CPU/writes,
   territory last/sum/max, using the **post-execution** alive/ownership
   state
5. `self.scoring.score_alive(...)`
6. `self.scoring.score_territory(...)`
7. `self._attribute_deaths(events)` — compares each agent's alive state to
   `state._alive_prev` (last tick's snapshot) to find newly-dead agents
   this tick, attributes a kill via last-writer-at-PC if a different agent
   owns that byte, calls `scoring.score_kill` and
   `statistics.record_death`
8. `self.replay.publish_tick(tick, ...)`
9. `self.renderer.publish_tick(tick, ...)`
10. (verbose printing, no state effect)
11. `state._alive_prev[agent_id] = agent.alive` for every agent
12. termination check: stop if `<= 1` agents alive

This exact order — statistics and scoring both read *post-execution,
pre-death-attribution* alive state, while kill attribution and its scoring
happen *after* alive/territory scoring but *before* replay publication —
is now pinned directly by
`test_scheduler_characterization.py::test_tick_lifecycle_runs_in_the_documented_order_with_no_death`
and
`...::test_tick_lifecycle_scores_the_kill_after_territory_and_before_replay_publication`,
in addition to the aggregate golden-corpus digest.

### Python, unsupervised (`python_runtime.PythonEntrantController.run`, `python_runtime.py:597-719`)

Same shape as the VM loop, with one structural difference: there is no
separate "execute all, then score" split at the sub-tick level — score/
statistics happen once per tick, after all entrants have taken their full
turn, same as the VM. Per tick: `clear_tick_diffs`, reset every state's
`cpu_used`, then for each state in order, up to `instr_per_tick` `act()`
calls (each wrapped to catch `InvalidPythonActionError` and ordinary
`Exception` — never `BaseException` — and convert either into a
`forfeit_entrant` call), then `statistics.record_tick`,
`scoring.score_alive`, `scoring.score_territory`, `replay.publish_tick`.
There is no Python equivalent of VM's `_attribute_deaths` step — Python
mortality never attributes a kill (see the ownership table).

### Python, supervised (`supervised_runtime.SupervisedPythonEntrantController.run`, `supervised_runtime.py:347-419`)

Structurally identical to the unsupervised loop (same statistics/scoring/
replay call sequence), with `act()` replaced by
`AgentWorkerHandle.act(...)` over a per-call timeout, and worker-specific
failure modes (`TIMEOUT`, `EXITED`, protocol error) mapped to the same
`RuntimeDiagnostic`/`forfeit_entrant` path unsupervised exceptions use.
`test_supervised_and_unsupervised_controllers_agree_on_outcome` (added
this phase) confirms both controllers reach identical final score,
winner, termination reason, arena bytes, ownership, and per-entrant
statistics for the same entrants/config — the first direct test of the
"same authoritative match semantics" claim in `supervised_runtime.py`'s
own module docstring.

## Entrant identity versus execution state

Field-by-field classification (see Step 4 categories: 1 = entrant
identity, 2 = resolved match input, 3 = execution state, 4 = runtime/
provenance metadata, 5 = derived/persisted result state).

### `match_service.MatchEntrant` (`match_service.py:51-64`)

| Field | Category | Notes |
|---|---|---|
| `agent_id` | 1 | Match-slot identity (`"A"`/`"B"`/…), not a stable cross-match agent identity |
| `name` | 1 | Display name |
| `start` | 2 | Resolved spawn address for this match |
| `code` | 2 | VM bytecode, `None` for Python |
| `kind` | 2 | `"vm"` or `"python"` |
| `python_spec` | 2 | Resolved `AgentSpec`, `None` for VM |

### VM `agent_state.Agent` (`agent_state.py:8-16`)

| Field | Category | Notes |
|---|---|---|
| `agent_id` | 1 | |
| `pc` | 3 | Mutates every `vm.step` |
| `alive` | 3 | |
| `regs` (`A`/`Z`/`P`) | 3 | |
| `cpu_used` | 3 | Reset every tick |
| `mem_writes` | 3 | Cumulative |
| `region` | 2 | Fixed at spawn (`load_code`'s return); descriptive only, never consulted for read/write validity |

### `python_runtime.PythonEntrantState` (`python_runtime.py:288-325`)

| Field | Category | Notes |
|---|---|---|
| `agent_id`, `name` | 1 | |
| `loaded` (`LoadedPythonAgent`) | 4 | Metadata + live instance; the instance itself is execution state by nature (mutable Python object) but engine treats it opaquely |
| `rng` | 3 | Seeded once from `derived_seed`, mutates as the agent consumes it |
| `slot` | 2 | Fixed at construction, feeds identity |
| `derived_seed` | 4 (identity input) | Computed once, never mutates; participates in `canonical_match_id` |
| `source_digest`, `local_source_fingerprint`, `local_source_fingerprint_final` | 4 | Provenance/reproducibility evidence, not gameplay |
| `agent_dir` | 4 | Retained only to recompute `local_source_fingerprint_final` |
| `pc`, `register_a`, `register_p`, `zero_flag`, `last_read` | 3 | Controller-side bookkeeping; Python `pc` is never fetched from, unlike the VM's real instruction pointer (`docs/RULES.md`'s "Source is not arena content") |
| `alive`, `cpu_used`, `total_actions`, `mem_writes` | 3 | |
| `region` | 2 | Fixed at construction from `entrant.start` |
| `diagnostic`, `entrant_termination` | 5 | Populated only on forfeit/halt; output, not input |

### `match_service.NativeAgentResult` (`match_service.py:92-134`)

Entirely category 5 (derived/persisted result state) — this dataclass
exists specifically to be persistence-neutral output, built once per
match from whichever runtime's final state, and is never read back into a
running match.

### `replay.AgentState` (`replay.py:34-55`)

Entirely category 5 for the same reason — the canonical per-tick replay
record. Its `termination_reason` field is explicitly documented as
"always `None` for VM entrants" (`replay.py:50-54`), a real, intentional
VM/Python asymmetry at the schema level, not a bug.

### What this means for v1.5

`agent_id`, `derived_seed`, `source_digest`/fingerprints, and `slot` are
identity-adjacent fields that already participate in deterministic
identity computation (see below) — any future entrant-identity/execution-
state split must keep them reachable from wherever `canonical_match_id`
and `derive_agent_seed` read them today, under the same names or via an
equally direct path. Everything else in `PythonEntrantState`/`Agent`
mutates during a match and is unambiguously execution state. `region` is
the one field that looks like execution state but is actually fixed,
descriptive match input in both runtimes — worth flagging so a future
identity/execution-state split does not accidentally reclassify it.

## Identity dependencies

### `derive_agent_seed` (`python_runtime.py:338-345`, frozen — see `docs/AGENT_API_V1.md`)

Inputs, in order, joined with NUL bytes into `"battle2-python-v1\0{match_seed}\0{slot}\0{agent_id}\0{api_version}"`,
then SHA-256'd:

- `config.seed`
- `slot` (position in `entrants`, i.e. schedule order)
- `entrant.agent_id`
- `api_version` (`AGENT_API_VERSION`, currently always `1`)

Pinned by literal golden vectors in
`test_python_runtime.py::test_derive_agent_seed_golden_vectors`.

### `canonical_match_id` (`match_service.py:504-569`)

A `stable_id("match", {...})` over:

- `mode`: literal `"b2"`
- `ruleset_id`: `BYTEFRAY_RULESET_ID`
- `reproducibility`: `seed`, `arena_size`, `tick_limit` (`max_ticks`),
  `action_budget` (`instr_per_tick`), `win_mode`, `weights` (all four
  fields), `entrant_order` (the `agent_id` list in schedule order)
- `entrants`: for each entrant, in schedule order —
  `agent_id`, `name`, and a `kind`-specific metadata dict:
  - VM: `entry` (start address), `code_sha256`
  - Python: `slot`, `derived_seed`, `source_sha256` (of `python_spec.source_path`),
    `api_version`, `agent_version`

Notably **excludes**: `verbose`, `trace_path`, `agent_call_timeout`
(supervised vs. unsupervised execution is not an identity input — the
equivalence test added this phase confirms why that is safe), and any
outcome/diagnostic data.

### `result_id` (`match_service.py:609-619`)

A `stable_id("result", {...})` over `match_id`, `winner`,
`termination_reason.value`, `ticks_run`, `score`, and each entrant's
`agent_id`/`name`/`alive`/`score`/`termination_reason`/**identity-safe**
diagnostic (message text stripped — `_identity_safe_diagnostic`,
`match_service.py:485-501` — specifically because exception message text
can be nondeterministic; `test_replay_reconstruction.py::test_result_id_is_stable_despite_nondeterministic_exception_text`
proves this)/metadata.

### `replay_id`

Always set equal to `match_id` (`match_service.py:634-636`) — there is no
independent replay identity in the current schema.

### `replay_sha256`

Computed from the final canonical replay file's bytes
(`match_service.py:694`), so it transitively depends on everything that
affects wire content, including the deterministic-serialization guarantee
(`replay.serialize_record`'s `sort_keys=True`).

## Existing golden corpus

`engine/tests/test_ruleset_v1_equivalence.py` (added in `2a3c6de`, "Add
Ruleset v1 equivalence corpus", v1.4) is the one golden/equivalence corpus
for Ruleset v1. It pins six scenarios end-to-end:

| Case | Entrants | What it specifically exercises |
|---|---|---|
| `vm_overlap` | 2 VM | Wrapped/overlapping code loads and writes, non-default weights |
| `vm_default_two_way` | 2 VM | Fully default `Config()` |
| `vm_three_way` | 3 VM | Kill/death attribution, three-entrant scheduling |
| `python_starters` | 2 Python (packaged starter agents) | Real shipped agent behavior, default config |
| `python_two_way` | 2 Python (RNG writer) | RNG-driven writes, mutual HALT, all-agents-dead termination |
| `python_three_way` | 3 Python (RNG writer, wrapping writer, forfeiter) | Forfeit mid-quota, mixed live/dead outcome |

For every case it asserts a single aggregate `snapshot_sha256` (covering
match/result identity, normalized replay bytes, winner, termination
reason, tick count, score, and per-agent alive/score/statistics/
diagnostic state) plus direct, named assertions for a few
specifically-interesting values (e.g. `vm_three_way`'s kill/death counts).
A companion test,
`test_existing_three_way_execution_is_deterministic_and_ordered`,
confirms both determinism (two runs of the same request produce identical
snapshots) and order-sensitivity (reversing entrant order changes
`match_id` and is reflected consistently through the replay and
`result.json`), parametrized over both VM and Python.

This corpus is deliberately compact, not exhaustive — its own module
docstring frames it as "a legitimate ruleset, Agent API, RNG, methodology,
or schema change must version its contract instead of refreshing these
values in place." Broader characterization of scheduling/termination/
identity edge cases lives in the more numerous, more targeted tests
described below and in "New characterization coverage."

### Coverage already present outside the golden corpus (verified this phase)

Before adding anything, Phase 1 confirmed the following are **already**
directly tested, not just implied by the golden corpus's aggregate digest:

- VM spawn-order/quota scheduling and dead-entrant-skip
  (`test_scheduler_characterization.py`, pre-existing);
- VM kill attribution vs. unattributed death
  (`test_match_services.py::test_kernel_attributes_kill_to_memory_owner`/`test_kernel_records_death_without_attributable_killer`);
- Python quota/reset-once/fresh-instance semantics, same-tick write
  visibility, HALT stopping future callbacks, invalid-action and
  exception forfeit with structured diagnostics, `KeyboardInterrupt`/
  `SystemExit` propagation (not forfeiture), RNG determinism and per-
  entrant independence, derived-seed golden vectors
  (`test_python_runtime.py`, pre-existing);
- supervised timeout/crash/protocol-error handling in isolation
  (`test_supervised_runtime.py`, pre-existing);
- persisted-`ruleset_id` recovery/consistency policy for both runtimes
  (`test_ruleset_persistence.py`, pre-existing);
- full replay-content reconstruction (arena, ownership, per-agent state)
  from the public replay reader alone, independently re-derived (not
  compared against the code under test), for both runtimes, including
  tick 0 (`test_replay_reconstruction.py`, pre-existing);
- `match_id`/`result_id` sensitivity to seed, code, config path, and
  Ruleset identity, and stability under nondeterministic diagnostic text
  (`test_replay_reconstruction.py`, pre-existing);
- incremental VM ownership-count bookkeeping against full recomputation,
  including the Python `WRITE` path (`test_ownership_accounting.py`,
  pre-existing).

## New characterization coverage (added this phase)

Five new tests, chosen because each protects a behavior a v1.5 scheduler-
abstraction or entrant-identity/execution-state refactor could plausibly
break without any of the above tests catching it directly (only the
golden corpus's opaque digest would, if the case happened to be covered):

1. **`test_python_scheduler_characterization.py::test_alive_entrants_consume_full_quota_in_spawn_order`**
   — direct call-order proof (via an instance-level `act` spy) that three
   Python entrants are called in spawn order, each consuming its full
   quota. The VM side has had this exact style of test since before this
   phase; Python did not. A shared scheduler abstraction that reordered
   Python entrant iteration would fail this test with a readable diff
   instead of an opaque golden-digest mismatch.
2. **`...::test_forfeited_entrant_is_skipped_on_later_ticks_and_next_entrant_still_gets_full_quota`**
   — same style, for the case where a middle entrant halts mid-quota:
   proves the following entrant is unaffected in the same tick, and the
   halted entrant is skipped (not merely idle) on the next tick. Directly
   protects the "entrant that dies mid-quota stops immediately and is
   skipped in later ticks" clause of `docs/RULES.md`'s "Scheduling order"
   for the Python runtime specifically.
3. **`test_scheduler_characterization.py::test_tick_lifecycle_runs_in_the_documented_order_with_no_death`**
   — pins the VM tick loop's exact stage order (execute → statistics →
   alive scoring → territory scoring → replay publication → renderer
   publication) via collaborator spies, independent of any death.
4. **`...::test_tick_lifecycle_scores_the_kill_after_territory_and_before_replay_publication`**
   — same, with an actual kill, proving kill attribution/scoring happens
   after alive/territory scoring but before that tick's replay record is
   published. This is the single most refactor-fragile ordering fact in
   the VM path: a scheduler extraction that moved statistics/scoring
   calls relative to death attribution would silently change which tick a
   kill is scored/replayed in.
5. **`test_supervised_runtime.py::test_supervised_and_unsupervised_controllers_agree_on_outcome`**
   — runs identical entrants/config through both `PythonEntrantController`
   and `SupervisedPythonEntrantController` and asserts identical winner,
   termination reason, score, arena/ownership bytes, and per-entrant
   statistics. `supervised_runtime.py`'s own module docstring claims "same
   authoritative match semantics" as the unsupervised controller; nothing
   in the pre-existing suite verified that end-to-end. This is the test
   most directly relevant to a future scheduler abstraction: if such an
   abstraction is only ever wired up to one of the two Python controllers,
   this test is what would catch the resulting behavioral drift.

All five were written from source inspection, not from watching a real
failure — each passed on its first run, which itself is evidence the
Phase 1 read of the scheduling/lifecycle code above is accurate.

## Findings / architectural hazards

Recorded for Phase 2+ to plan around; none of these are defects and none
were changed in this phase.

1. **Three independent scheduling-loop implementations.** VM
   (`match.MatchRunner._execute_agents`), unsupervised Python
   (`PythonEntrantController.run`), and supervised Python
   (`SupervisedPythonEntrantController.run`) each hand-roll the identical
   "reset cpu_used, then for each living entrant in order, up to
   `instr_per_tick` units, stop early on death" shape. This is the
   concrete duplication the v1.5 "scheduler abstraction" is aimed at. Any
   extraction must preserve all three call orders exactly (now directly
   tested, see above) and must not accidentally unify VM and Python
   mortality semantics (kill attribution is VM-only, by design).
2. **Termination-reason computation is duplicated three ways** (see the
   ownership table's "Match termination" row) with the identical
   `alive_count == 0` / `== 1` / else logic written out separately in
   `_build_result`, `PythonEntrantController.run`, and
   `SupervisedPythonEntrantController.run`. Low risk, since the tests
   above pin the output, but worth consolidating carefully rather than
   leaving three copies to drift.
3. **`supervised_runtime.py` is an intentional, reviewed fork of
   `python_runtime.py`'s tick loop**, not a shared base class, specifically
   to avoid risking the unsupervised path's existing coverage (see its own
   module docstring). A v1.5 scheduler abstraction is the first real
   opportunity to unify them behind one interface — the new equivalence
   test in this phase is the safety net that would make such a unification
   verifiable.
4. **VM/Python kill attribution is a real, permanent asymmetry, not a
   parity gap to close.** `docs/RULES.md` already documents this
   explicitly ("No Python kill attribution"), and it is now directly
   tested on both sides. Recorded here only so a future "unify VM and
   Python scheduling" effort does not treat the asymmetry as an oversight
   to fix — doing so would be a Ruleset bump, explicitly out of v1.5's
   scope.
5. **`region` is fixed match input, not execution state, in both
   runtimes**, despite living on the same mutable dataclass as genuine
   execution-state fields (`Agent`, `PythonEntrantState`). A future
   entrant-identity/execution-state split should place it with "resolved
   match input," not "execution state" — see "Entrant identity versus
   execution state" above.
6. **`agent_call_timeout`/`trace_path` select which of two controllers
   runs, but participate in no identity computation.** This is
   intentional and now verified safe (finding 3's equivalence test), but a
   future scheduler abstraction must preserve this: which controller
   implementation ran must never become an identity input, or every
   existing supervised/unsupervised pair of otherwise-identical matches
   would silently diverge in `match_id`.

## v1.5 architecture invariants

Non-negotiable for any v1.5 change (Ruleset/policy dispatch, entrant
identity/execution-state separation, scheduler abstraction):

- **Ruleset identity.** `BYTEFRAY_RULESET_ID` remains `"bytefray-rules-1"`.
  No Ruleset bump is justified by architecture-only rearrangement.
- **Entrant/execution-state cardinality.** Under Ruleset v1, exactly one
  entrant owns exactly one execution state. The architecture may later
  make one-to-many *representable*, but v1.5 itself must not enable it.
- **Scheduling.** Current sequential entrant scheduling and per-entrant
  action quota — including mid-quota death/forfeit stopping immediately
  and being skipped thereafter — remain unchanged, for both VM and Python,
  in both supervised and unsupervised form.
- **Runtime compositions.** Existing homogeneous VM and homogeneous Python
  behavior remains unchanged. Mixed VM/Python execution remains
  unsupported.
- **Agent API.** Agent API v1 (`AGENT_API_VERSION == 1`) remains frozen,
  including the exact `derive_agent_seed` formula.
- **Persistence.** No `battle2.replay`/`battle2.result`/`bytefray.
  evaluation`/`bytefray.agent_package` schema change is expected or
  required merely for internal architecture.
- **Identity.** Architecture-only changes must not change
  `match_id`/`result_id`/`replay_id`/`replay_sha256` for equivalent
  Ruleset-v1 inputs. The golden corpus in
  `test_ruleset_v1_equivalence.py` is the acceptance boundary for this.
- **Evaluation methodology.** Unchanged (`bytefray.evaluation`'s
  orientation/alignment fields, matrix construction).
- **Gameplay.** No new action, scoring rule, scheduler *behavior* (as
  opposed to internal structure), mortality rule, resource, arena
  semantic, or combat mechanic enters v1.5.

## Validation record (Phase 1 baseline)

Run from `v1.5-development` at the commit this document was added in:

- Focused (golden corpus + scheduler/runtime/identity tests, 140 tests):
  **140 passed**.
- Full suite (`python -m pytest`): **1245 passed, 6 skipped, 2 deselected**
  (skips/deselections are the existing `gui`-marked and environment-gated
  cases `pytest.ini` already excludes from the headless run — unrelated to
  this phase). This is 5 more than the v1.4.1 baseline's 1240, exactly the
  five characterization tests this phase added; no pre-existing test's
  outcome changed.
- `ruff check .`: **all checks passed**.
- `mypy engine/src/battle_engine`: **no issues found (57 source files)**.
- `mypy client/src/battle_client`: **no issues found (10 source files)**.

A later phase can reproduce this by running the same four commands from
the same branch and diffing against these counts, plus re-running
`test_ruleset_v1_equivalence.py` specifically: an unexplained change to
any of its pinned `snapshot_sha256`/`match_id`/`result_id` values is a
defect in that later phase until proven otherwise (see this repository's
`docs/specs/`-adjacent decision principle already established for v1.4).
