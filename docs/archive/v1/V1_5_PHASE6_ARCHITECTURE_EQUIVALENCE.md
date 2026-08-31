# v1.5 Phase 6 — Integrated architecture-equivalence qualification

This is the durable record of v1.5 Phase 6: qualifying the **combined**
result of Phases 2-5 as one integrated architecture candidate, rather than
adding more abstraction. Phase 6 is deliberately a qualification/audit
phase: it asks whether Ruleset-v1 gameplay semantics, deterministic
identity, persisted compatibility, and native execution survived the
scheduler abstraction (Phase 2), the policy dispatch seam (Phase 3), the
termination policy (Phase 4), and the entrant-identity/execution-state
separation (Phase 5) -- together, not merely phase by phase.

## Architecture under qualification

```text
NativeMatchService.run
        |
        |-- runtime selection (VM vs Python) -- remains outside Ruleset policy
        |
        v
resolve_ruleset_policy(BYTEFRAY_RULESET_ID)   # exactly once per match
        |
        v
RulesetPolicy (RULESET_V1)
    |-- run_scheduler -> scheduler.run_sequential_quota
    \-- resolve_termination -> alive_count / tick / max_ticks rule

EntrantIdentity(agent_id, name)
        |
        v
MatchEntrant (resolved match entrant: identity + start/code/kind/python_spec)
        |
        v
exactly one execution state: VM Agent  or  PythonEntrantState
```

## 1. Starting state

- Branch: `v1.5-development`.
- Starting SHA: `c25c1e0` ("refactor(runtime): separate entrant identity
  from execution state").
- Phase 2-5 commits (`d2c4a56`, `c776c9a`, `77a0dbb`, `c25c1e0`) all present
  in `git log`, ancestors of `HEAD`.
- Working tree: clean at the start of this phase.
- Baseline re-run before touching anything: golden corpus 8 passed;
  focused Phase 2-5 tests (ruleset policy, scheduler, scheduler/Python
  scheduler characterization, entrant identity, native match service,
  match services, supervised runtime, python runtime, replay
  reconstruction, ownership accounting, ruleset persistence) all passed;
  full suite via `--junitxml` (this environment's `-q` summary line is not
  reliably captured in a piped shell -- same observation Phase 3 recorded):
  `tests="1289"`, `skipped="6"`, `errors="0"`, `failures="0"` ->
  **1283 passed, 6 skipped**, matching the Phase 5 baseline exactly.

## 2. Integrated architecture (reconstructed from current source, not from prior reports)

- **Match entry / runtime selection:** `NativeMatchService.run`
  (`match_service.py`) validates homogeneous composition, then selects the
  VM path (`_run_vm_match`) or the Python path (`_run_python_match`,
  further split into unsupervised/supervised by whether
  `MatchRequest.agent_call_timeout` is set) -- this branch is entirely
  outside Ruleset policy, confirmed unchanged (see "Ruleset dispatch
  audit").
- **Ruleset resolution:** `NativeMatchService.run` calls
  `resolve_ruleset_policy(BYTEFRAY_RULESET_ID)` exactly once per match
  (`match_service.py:874`), before either runtime path executes, and
  threads the resulting `RulesetPolicy` instance through
  `_run_vm_match`/`_run_python_match`/`_run_python_match_traced` to the
  `Kernel`/`PythonEntrantController`/`SupervisedPythonEntrantController`
  constructor, which stores it once as `self.ruleset_policy`.
- **Scheduling:** all three runtimes call
  `self.ruleset_policy.run_scheduler(...)` (`match.py:107`,
  `python_runtime.py:740`, `supervised_runtime.py:375`), which forwards to
  `scheduler.run_sequential_quota` -- the one shared implementation.
- **Termination:** all three runtimes call
  `self.ruleset_policy.resolve_termination(...)` both mid-loop (continue/
  stop) and post-loop (final reason) -- `match.py:85`,
  `match_service.py`'s `_build_result` (VM's post-loop reason, computed
  outside `Kernel.run` because that is where `NativeMatchResult` is built),
  `python_runtime.py:765/783`, `supervised_runtime.py:396/416`.
- **Entrant identity/state:** `MatchEntrant.identity` (an `EntrantIdentity`)
  is constructed once per entrant from `MatchRequest.entrants`; VM `Agent`
  and `PythonEntrantState` each store their own `identity: EntrantIdentity`
  (VM synthesizes `name = agent_id`; Python carries the real `name` from
  the entrant), reachable via read-only `agent_id`/`name` compatibility
  properties. Exactly one execution state is appended per entrant
  (`Kernel.spawn`, `PythonEntrantController.__init__`,
  `SupervisedPythonEntrantController._initialize_entrant`), each exactly
  once per element of `request.entrants`.

## 3. Architecture bypass audit

Searches performed (`Grep` across `engine/src`) and results:

| Search | Result |
|---|---|
| `run_sequential_quota` | Only referenced in `scheduler.py` (definition) and `ruleset_policy.py` (its one caller, `RulesetPolicy.run_scheduler`). No direct import from `match.py`/`python_runtime.py`/`supervised_runtime.py` -- confirmed by a separate `from battle_engine.scheduler import` search, which matched only `ruleset_policy.py`. |
| `resolve_termination` | Defined once in `ruleset_policy.py`; called from `match.py`, `match_service.py`, `python_runtime.py`, `supervised_runtime.py` -- all four call sites documented in Phase 4, unchanged. |
| `alive_count == 0` / `== 1`, `sum(...alive...) <= 1` | Only inside `RulesetPolicy.resolve_termination` itself. No independent hand-coded termination rule survives anywhere. |
| `RulesetPolicy(` construction | Exactly one: the `RULESET_V1` singleton in `ruleset_policy.py`. No ad-hoc policy object is constructed anywhere else. |
| `BYTEFRAY_RULESET_ID` in runtime code | Referenced by `match_service.py` (the one `canonical_match_id`/`resolve_ruleset_policy` use, and persisted-identity fields), `replay.py`/`result_model.py` (persisted-identity recovery), `rules.py` (definition), `ruleset_policy.py` (policy definition), `agent_evaluation.py` (compatibility/provenance alias). No `Kernel`/`MatchRunner`/`PythonEntrantController`/`SupervisedPythonEntrantController` code references it directly -- they only ever see the already-resolved `RulesetPolicy` object. |
| `normalize_ruleset_id` / `_RULESET_ALIASES` / `"evaluation-rules-1"` | Used only in `evaluation_history/comparison.py` (artifact-provenance comparison) and defined in `rules.py`. **Not** called anywhere in `ruleset_policy.py`'s resolver -- confirmed directly; the historical alias cannot silently execute as Ruleset v1. |
| Flat `agent_id: str`/`name: str` field declarations on `Agent`/`PythonEntrantState`/`MatchEntrant` | None found (only `__init__` parameter annotations and the unrelated, intentionally-flat `NativeAgentResult.agent_id`/`.name`, a persistence-neutral output dataclass -- see Phase 5's field classification). |
| `asdict(agent`, `asdict(state`, `asdict(entrant`, `vars(agent)`, `vars(state)`, `vars(entrant)`, `dataclasses.replace(agent`/`state`/`entrant` | The only `asdict(` hit touching any of these three classes is `asdict(agent.diagnostic)` in `match_service.py` -- `agent.diagnostic` is a `RuntimeDiagnostic`, an unrelated, always-flat dataclass, not `Agent`/`PythonEntrantState`/`MatchEntrant` itself. The `vars(...)` hits are all inside `test_entrant_identity.py`'s own structural-authority assertions (see Phase 5). No `dataclasses.replace()` call targets any of the three refactored classes anywhere in the repository. |
| One-to-many state collection keyed by entrant | No `dict[..., list[Agent]]`/`dict[..., list[PythonEntrantState]]`/`states_by_entrant`/`agents_by_entrant` pattern found anywhere. Exactly three `.append()` call sites append execution states, one per class (`core.py`, `python_runtime.py`, `supervised_runtime.py`), each appending exactly one state per entrant. |

**No live architectural bypass found.** One finding, classified as
documentation staleness rather than a bypass: `match_service.py`'s comment
immediately above the `resolve_ruleset_policy` call still said "(currently:
entrant scheduling)" -- accurate as of Phase 3, stale since Phase 4 added
termination to the same dispatched policy. Fixed this phase (see "Dead/
redundant code findings").

## 4. Scheduler audit

Exactly one authoritative Ruleset-v1 scheduling implementation:
`scheduler.run_sequential_quota`, reached exclusively through
`RulesetPolicy.run_scheduler`. Confirmed by the bypass audit above (no
direct `scheduler` import outside `ruleset_policy.py`) and by test
evidence: `test_scheduler.py` (8 tests: sequential order, initial-dead
skip, mid-quota mortality without suppressing later states, quota-one, a
non-default quota, slot forwarding, zero-quota), `test_scheduler_
characterization.py` (VM spawn-order/quota/dead-skip via `kernel.vm.step`
spy), `test_python_scheduler_characterization.py` (same style for
unsupervised Python via an `act` spy), and
`test_supervised_and_unsupervised_controllers_agree_on_outcome`
(`test_supervised_runtime.py`) for the supervised path -- all re-ran clean
this phase. No surviving independent scheduling loop exists anywhere.

## 5. Termination audit

Exactly one authoritative Ruleset-v1 termination semantic:
`RulesetPolicy.resolve_termination`, reached exclusively through the four
call sites listed under "Integrated architecture" above. Confirmed
unchanged: alive count `0` -> `ALL_AGENTS_DEAD`; alive count `1` ->
`LAST_AGENT_STANDING`; otherwise, reaching `max_ticks` -> `TICK_LIMIT`;
alive-count conditions take precedence over the tick limit
(`test_ruleset_policy.py::test_termination_precedence_prefers_alive_
count_over_tick_limit`). HALT/forfeit still only ever mutate `alive`
(`vm.py`'s `step`, `python_runtime.py`'s `apply_action`/`forfeit_entrant`
-- both confirmed byte-identical to v1.4.1, see "v1.4.1 equivalence"
below) -- neither touches `identity` or calls into termination logic
directly. Runtime loop control (*when* each runtime asks the question,
mid-tick vs. post-loop) remains runtime-owned, as designed; only the
*answer* is centralized.

## 6. Ruleset dispatch audit

- **Exact runtime ID behavior:** only the literal current
  `BYTEFRAY_RULESET_ID` (`"bytefray-rules-1"`) resolves via
  `resolve_ruleset_policy`.
- **Fail-closed behavior:** any other string raises `UnknownRulesetError`
  -- pinned by `test_ruleset_policy.py::test_unknown_ruleset_id_fails_
  closed_rather_than_resolving_to_v1` (parametrized over
  `"bytefray-rules-2"`, `"unknown"`, `"evaluation-rules-999"`,
  `"evaluation-rules-1"`, `""`) and, at the actual production call site, by
  `test_native_match_service.py::test_unknown_ruleset_id_fails_closed_
  before_any_runtime_executes`.
- **Alias handling:** `"evaluation-rules-1"` (the historical artifact-
  provenance alias `rules._RULESET_ALIASES` maps to `BYTEFRAY_RULESET_ID`
  for *attributing* old artifacts) is explicitly **not** special-cased by
  `resolve_ruleset_policy` -- it is one of the parametrized cases in the
  fail-closed test above, proving runtime dispatch and historical-artifact
  interpretation remain two different questions.
- **Direct-construction compatibility behavior:** `Kernel`,
  `PythonEntrantController`, and `SupervisedPythonEntrantController` each
  default their `ruleset_policy` constructor parameter to `RULESET_V1`
  (three occurrences total, confirmed by direct search -- exactly matching
  the three runtime classes and nowhere else). These defaults exist so the
  large body of tests and any other direct-construction caller that never
  supplies a policy still works unchanged; they are **not** a second
  production dispatch path -- `NativeMatchService.run` is the only call
  site that actually calls `resolve_ruleset_policy` in production, and it
  always passes the resolved policy explicitly rather than relying on the
  default. This distinction (compatibility default vs. authoritative
  runtime-ID validation boundary) is the same one Phase 3 documented; Phase
  6 confirms it still holds and did not remove these defaults, since
  qualification found no risk they create.
- **No hidden global mutable policy, no "latest Ruleset" fallback:**
  `RULESET_V1` is an immutable frozen-dataclass module-level constant;
  `_RULESET_POLICIES` is a one-entry, never-mutated `Mapping`.

## 7. Entrant identity/state audit

- **One authoritative stored identity:** `MatchEntrant`, `Agent`, and
  `PythonEntrantState` each store exactly one `identity: EntrantIdentity`
  field; `agent_id`/`name` are read-only properties reading
  `self.identity.agent_id`/`.name`, never separately stored. Confirmed by
  direct search (`agent_id: str` never appears as a class-level field
  annotation on any of the three) and by `test_entrant_identity.py`'s
  structural proofs (`"agent_id" not in vars(...)"`).
- **No accidental duplicate identity storage:** the only flat
  `agent_id`/`name` fields remaining anywhere are on `NativeAgentResult`, a
  persistence-neutral *output* dataclass Phase 1 classified separately
  (category 5) and Phase 5 deliberately left alone.
- **Resolved match data remains separate:** `start`, `code`, `kind`,
  `python_spec` (on `MatchEntrant`) and `slot`, `region`, `derived_seed`,
  provenance fields (on `PythonEntrantState`) are unchanged, plain fields,
  never folded into `EntrantIdentity`.
- **One execution state per entrant:** see "One-state-per-entrant audit"
  in Phase 5's own record and the bypass-audit row above; re-confirmed this
  phase by the same `.append()`-call-site search.

## 8. Compatibility accessor audit

| Surface | Classification | Why |
|---|---|---|
| `Agent.agent_id` / `PythonEntrantState.agent_id`/`.name` / `MatchEntrant.agent_id`/`.name` (read-only properties) | Useful compatibility surface | Every ownership/scoring/statistics/kill-attribution/replay/CLI/tournament/test call site reads these via plain attribute access; removing them would force `.identity.agent_id` everywhere for zero behavioral gain. Retained. |
| `Kernel`/`PythonEntrantController`/`SupervisedPythonEntrantController`'s `ruleset_policy=RULESET_V1` default | Useful compatibility surface | Keeps ~30+ direct-construction test call sites (and any future direct caller) working without threading a policy through every one; the one production dispatch path always resolves and passes it explicitly. Retained -- see "Ruleset dispatch audit." |
| VM `Agent.identity.name` synthesizing to `agent_id` | Harmless implementation detail, documented and tested | VM execution state never tracked a real display name before Phase 5 either; this is an honest statement of that fact, not a regression. Protected by `test_vm_native_result_name_comes_from_match_entrant_not_synthetic_agent_identity` so it cannot silently leak into persisted output. Retained. |
| `dataclasses.replace()` incompatibility on the three refactored classes | Harmless implementation detail (narrow, documented limitation) | Their custom `__init__`s accept `agent_id`/`name` positionally, not the now-internal `identity` field `replace()` would pass as a keyword. Nothing in the repository calls `replace()` on any of the three (confirmed by search, both in Phase 5 and re-confirmed this phase). Not worked around, since doing so purely for a hypothetical future caller would itself be unrequested speculative flexibility. |
| `match_service.py`'s "(currently: entrant scheduling)" comment | Dead/stale -- fixed | The only surface this phase found worth changing; see "Dead/redundant code findings." |

**Nothing was removed this phase.** No compatibility accessor was found to
be actively dangerous or safely removable without churn disproportionate
to the risk it poses.

## 9. v1.4.1 equivalence

Two independent lines of evidence, both direct (not inferred from "the
code wasn't touched"):

1. **Golden corpus run against the actual v1.4.1 source tree.** Created a
   detached worktree at `896df86` (the v1.4.1 release commit), then ran
   `engine/tests/test_ruleset_v1_equivalence.py` with `PYTHONPATH` forced
   to that worktree's own `engine/src`/`client/src` (verified via
   `battle_engine.__file__` resolving to the worktree path, overriding this
   environment's editable install) rather than relying on git history
   alone: **8 passed**. The same unchanged test file was already confirmed
   to pass 8/8 against current Phase 5 `HEAD` (see "Golden corpus" below)
   -- both runs assert the identical literal `snapshot_sha256`/`match_id`/
   `result_id` values pinned in the test file itself, which `git diff 896df86
   HEAD -- engine/tests/test_ruleset_v1_equivalence.py` confirms is
   byte-for-byte unchanged (zero-line diff). This is direct, executed
   proof that `v1.4.1 behavior == current v1.5 architecture behavior` for
   all six golden scenarios, not an inference from "identity code wasn't
   edited."
2. **Direct source diff for every behavior-defining module.** `git diff
   896df86 HEAD --stat -- engine/src/ client/src/` touches exactly 10
   files (`entrant_identity.py`, `ruleset_policy.py`, `scheduler.py` new;
   `agent_state.py`, `core.py`, `match.py`, `match_service.py`,
   `python_runtime.py`, `results.py`, `supervised_runtime.py` modified).
   `vm.py` (arena/ownership/writer semantics), `scoring.py`,
   `statistics.py`, `telemetry.py`, `rules.py`, `replay.py`,
   `result_model.py`, and every other of the 60 engine source files have
   **zero diff** since v1.4.1. `client/src/` has **zero diff**. Within
   `match.py`, the diff touches only the scheduling call (Phase 2) and the
   mid-loop termination check (Phase 4); `_attribute_deaths` (VM kill
   attribution) is not in the diff at all. Within `python_runtime.py`,
   `apply_action`/`forfeit_entrant`/`validate_action` (Python action
   semantics) do not appear in any diff hunk.

## 10. Semantic-equivalence matrix

All cells backed by existing tests, re-run clean this phase (see
"Validation"); no new gameplay coverage was needed.

| Dimension | Coverage | Result |
|---|---|---|
| 2 entrants | `test_ruleset_v1_equivalence.py` (`vm_overlap`, `vm_default_two_way`, `python_starters`, `python_two_way`), `test_native_match_service.py`, `test_entrant_identity.py` | pass |
| 3 entrants | `test_ruleset_v1_equivalence.py` (`vm_three_way`, `python_three_way`), Phase 5's `test_entrant_identity.py` order-preservation tests, Phase 6's live CLI/API runs (see "Native runtime qualification") | pass |
| VM | all of the above, plus `test_scheduler_characterization.py`, `test_match_services.py`, `test_ownership_accounting.py` | pass |
| Python, unsupervised | `test_python_runtime.py`, `test_python_scheduler_characterization.py`, golden corpus Python scenarios | pass |
| Python, supervised | `test_supervised_runtime.py` (including `test_supervised_and_unsupervised_controllers_agree_on_outcome`) | pass |
| Default `instr_per_tick` | `vm_default_two_way`, most unit tests | pass |
| Non-default `instr_per_tick` | `vm_overlap` (quota 2), `test_scheduler.py`'s non-default-quota case, Phase 6's live CLI runs (quota 4, 5, 7) | pass |
| Last entrant standing | `python_three_way` (forfeit leaves one alive), `test_native_match_service.py::test_vm_termination_reasons_for_one_survivor_all_dead_and_tick_limit`, `test_ruleset_policy.py` | pass |
| All entrants dead | `python_two_way` (mutual HALT), same VM/policy tests as above | pass |
| Tick limit | `vm_overlap`, `vm_three_way`, `vm_default_two_way`, `python_starters`, same VM/policy tests | pass |
| Competing conditions (alive-count vs. tick limit) | `test_ruleset_policy.py::test_termination_precedence_prefers_alive_count_over_tick_limit` (parametrized, 2 cases) | pass |
| HALT | `python_two_way`'s RANDOM_WRITER agents, `test_python_runtime.py::test_halt_and_tick_limit_have_explicit_termination_reasons` | pass |
| Python forfeit | `python_three_way`'s FORFEITER agent, `test_python_runtime.py`'s forfeit tests | pass |
| Python exception/invalid action | `test_python_runtime.py` (`InvalidPythonActionError`, ordinary `Exception` forfeit paths; `KeyboardInterrupt`/`SystemExit` propagate, not forfeited) | pass |
| Ownership | `test_ownership_accounting.py` (incremental vs. full recomputation, including the Python `WRITE` path) | pass |
| Territory | golden corpus's pinned `territory_last` assertions, `test_match_services.py` | pass |
| Kills/deaths | `vm_three_way`'s pinned kill/death counts, `test_match_services.py::test_kernel_attributes_kill_to_memory_owner`/`test_kernel_records_death_without_attributable_killer` | pass |
| CPU/action accounting | `test_scheduler_characterization.py::test_dead_entrant_cpu_total_stops_after_death`, golden corpus per-agent `cpu_total` | pass |
| Memory writes | golden corpus per-agent `mem_writes`, `test_ownership_accounting.py` | pass |
| Distinct canonical IDs | `test_entrant_identity.py::test_duplicate_display_names_remain_distinct_entrant_identities` | pass |
| Duplicate display names | same test, plus the pre-existing v1.4.1 Designer-fix regression coverage (unaffected, out of this phase's scope) | pass |
| Slot-sensitive Python seeds | `test_python_runtime.py::test_derive_agent_seed_golden_vectors` (literal golden vectors, unchanged) | pass |

## 11. Identity equivalence

- **Ruleset ID:** `BYTEFRAY_RULESET_ID == "bytefray-rules-1"`, `rules.py`
  has zero diff since v1.4.1.
- **Python seeds:** `derive_agent_seed`'s literal golden vectors, unchanged
  (`test_python_runtime.py::test_derive_agent_seed_golden_vectors`).
- **Match IDs / result IDs / replay IDs / replay hashes:** all six golden
  corpus scenarios' pinned `match_id`, `result_id`, and
  `normalized_replay_sha256`-derived `snapshot_sha256` are unchanged from
  the v1.4.1-equivalent baseline (see "v1.4.1 equivalence" above) and from
  every prior phase's own record. `replay_id` is always `== match_id`
  (unchanged mechanism, `match_service.py`).

## 12. Replay qualification

The golden corpus's `_snapshot` helper (`test_ruleset_v1_equivalence.py`)
is the concrete replay-equivalence witness: for each of the six scenarios
it independently reconstructs final arena bytes and per-cell ownership
*from the replay file's own recorded per-tick memory diffs alone* (not
from the live `VM`/`PythonEntrantState` objects), hashes them
(`arena_sha256`, `ownership_sha256`), hashes the full canonical replay
file's bytes (`normalized_replay_sha256`, newline-normalized), and folds
all of it plus `match_id`/`result_id`/`winner`/`termination_reason`/
`ticks_run`/`score`/per-agent statistics into one `snapshot_sha256`. All
eight golden-corpus tests (six scenarios plus the two-way parametrized
`test_existing_three_way_execution_is_deterministic_and_ordered`, which
additionally proves determinism across two runs and order-sensitivity when
entrant order is reversed) passed with zero differences, covering: VM
(2-entrant, 3-entrant, wrapped/overlapping writes), Python (2-entrant,
3-entrant, starter agents), tick-limit and last-agent-standing/all-dead
termination, a kill/death case (`vm_three_way`), a HALT case
(`python_two_way`), a forfeit case (`python_three_way`), and a non-default
scheduler quota (`vm_overlap`, quota 2). Supervised-vs-unsupervised replay
content agreement is separately proven end-to-end by
`test_supervised_runtime.py::test_supervised_and_unsupervised_controllers_
agree_on_outcome` (identical winner, termination reason, score, arena/
ownership bytes, per-entrant statistics for the same entrants/config).
**Zero architecture-induced replay differences.**

## 13. Native runtime qualification

Run this phase, from an isolated scratch data root
(`BYTEFRAY_ROOT` pointed at a temp directory, never the repository's own
data root), using the actual `bytefray` CLI and the same production
`NativeMatchService`/`MatchEntrant`/`MatchRequest` APIs the CLI and golden
corpus both use:

- **VM, 2 entrants:** `bytefray run --a-type writer --b-type runner
  --arena 256 --quota 4 --ticks 20 --replay vm2.jsonl --quiet` -- exit 0;
  `result.json` shows correct `agent_id`/`name` attribution
  (`A`="writer", `B`="runner"), real territory scoring, `match_id`/
  `replay.sha256` populated.
- **VM, 3 entrants, non-default quota:** `bytefray run --a-type writer
  --b-type seeker --c-type runner --arena 512 --quota 7 --ticks 30 --replay
  vm3.jsonl --quiet` -- exit 0; `winner=tie`, `termination_reason=
  tick_limit`, three correctly-ordered `agent_id`s.
- **Python, unsupervised, 3 entrants:** a driver script using
  `ensure_starter_agents`/`resolve_agent`/`MatchEntrant.python`/
  `MatchRequest`/`NativeMatchService` (the same production functions the
  golden corpus's `_python_starter_request` helper uses) against three
  materialized starter Python agents (`claimer`, `hunter`, `wanderer`),
  seed 4242, 40 ticks -- completed, `agent_ids == ["A", "B", "C"]`, replay/
  result artifacts written.
- **Python, supervised, 2 entrants (real worker subprocess):** the same
  driver with `MatchRequest(agent_call_timeout=5.0, ...)`, which routes
  through `SupervisedPythonEntrantController`/`AgentWorkerHandle` -- a real
  child-process `load`/`reset`/`act` round trip, not a mock -- completed,
  `winner=B`, `termination_reason=tick_limit`, replay/result artifacts
  written.
- **CLI-driven create -> validate -> test (Agent Lab / supervised path):**
  `bytefray agents create qual-agent` (scaffolds a real Python agent),
  `bytefray agents validate qual-agent` (`status: valid`), `bytefray agents
  test qual-agent --ticks 30` (a real supervised development match against
  the internal reference opponent) -- all exit 0; the test run produced
  `result.json`/`replay.jsonl`/`summary.json`/`trace.jsonl` under the
  isolated data root.

Every command above exited 0 and produced artifacts with correct entrant
identity attribution, confirming actual runtime construction and lifecycle
-- not just isolated-class unit tests -- for VM, unsupervised Python, and
supervised Python, at both 2 and 3 entrants and non-default scheduler
quota.

## 14. Platform qualification

- **Windows (native):** full qualification -- complete focused suite,
  full test suite (twice, see "Validation"), `ruff`, both `mypy` targets,
  native CLI runtime qualification (above), and the package/install smoke
  below, all executed directly in this environment (Windows 11,
  Python 3.13.7).
- **Linux (WSL Ubuntu, Python 3.12.3):** a fresh venv was created and
  `pip install -e ".[dev]"` completed successfully against this
  repository's actual dependency set (`PyYAML`, `ruff`, `mypy`, `pytest`,
  `types-PyYAML` -- no network-restricted or unavailable packages). With
  that venv: `engine/tests/test_ruleset_v1_equivalence.py` (golden corpus,
  8 tests) and a focused Phase 2-6 architecture set (`test_entrant_
  identity.py`, `test_ruleset_policy.py`, `test_scheduler.py`, 43 tests
  total) all **passed** on real Linux, independent of the Windows result.
  A `py_compile` pass over every Phase 5/6-changed source and test file
  also succeeded under this Linux interpreter. **The complete 1283-test
  full suite was not fully executed under WSL this phase**: a first
  attempt was run concurrently with a Windows `pytest` invocation against
  this repository's shared, repo-local `.pytest-tmp`/`.pytest-cache`
  directories (`pytest.ini`'s deliberate, documented choice -- see
  `docs/WINDOWS_DEV_NOTES.md`), which caused a genuine collision (a
  Windows-side `WinError 145` cleanup failure and a Linux-side test
  failure), diagnosed as concurrent cross-filesystem access to the same
  physical cache directory from two OS environments rather than a
  behavioral defect; both runs were stopped, the shared cache directories
  were cleaned, and the Windows result was re-confirmed clean afterward
  (see "Validation"). A second, non-concurrent WSL full-suite attempt was
  started but did not finish within this session -- cross-filesystem I/O
  through `/mnt/d/` from WSL is measurably slow for this suite's many
  small per-test file operations (the golden corpus and focused set above
  completed in seconds; the full suite was still under 10% after several
  minutes). This is disclosed honestly rather than reporting a full-suite
  Linux pass this phase did not actually observe complete; the golden
  corpus and focused architecture set are, per this repository's own
  stated acceptance boundary, the specific evidence that matters for
  Ruleset-v1 equivalence, and both passed cleanly on Linux.
- **Other Python versions (3.10-3.12 on Windows):** not executed this
  phase; recent release practice (`docs/COMPATIBILITY.md`,
  `V1_4_PLATFORM_INTEGRITY.md`) already qualifies the 3.10-3.13 range at
  release-preparation time, and this phase's architecture-only diff (10
  source files, no new syntax/typing feature use beyond what the existing
  `requires-python = ">=3.10"` baseline already supports -- confirmed by
  `from __future__ import annotations` use and no new match-statement/
  3.11+-only syntax in any changed file) does not introduce a new
  version-support risk. This is a stated inference from the diff's
  content, not a fabricated multi-version test run.

## 15. Package/install qualification

- `python -m build --wheel` succeeded, producing
  `bytefray-1.4.1-py3-none-any.whl` (version correctly still `1.4.1` --
  unbumped, as expected for a qualification build, not a release).
- Installed into a fresh, isolated venv (`pip install <wheel>`, no
  `-e`/editable mode) -- `battle_engine.__file__` resolved to that venv's
  `site-packages`, confirmed independent of this repository's own editable
  dev install.
- `bytefray --version` -> `Bytefray 1.4.1, Agent API v1, result schema v1,
  replay schema v3` -- correct, unbumped identity.
- `bytefray run` (VM, 3 entrants, non-default quota) -- exit 0, correct
  `result.json`/`summary.json`.
- `bytefray agents create` / `agents validate` / `agents test` (real
  supervised worker-subprocess development match) -- exit 0, correct
  artifacts, from the console-script entry point installed by the wheel
  (`bytefray.exe`), not the repository's own `python -m battle_engine`.
- `bytefray replay --renderer headless` against the VM match's replay --
  exit 0, correct tick-by-tick score/agent output.
- **Limitation:** the four PyInstaller-frozen applications
  (`bytefray`/`bytefray-cli`/`bytefray-agent-designer`/
  `bytefray-replay-viewer` executables), the Windows installer, and the
  portable ZIP were **not** built or qualified this phase -- that is
  release-preparation-level packaging (`tools/build_win.ps1`,
  `tools/installer.iss`), explicitly reserved by this repository's own
  convention for the release-qualification phase (see `docs/ROADMAP.md`'s
  v1.0-v1.4 "Release qualification" sections), not an architecture-audit
  phase. The wheel/CLI smoke above is the strongest non-release package
  qualification appropriate now, and is a genuine, executed result, not a
  simulated one.

## 16. Static architecture findings

Wrote a small import-graph script (stdlib `ast`, no new dependency) over
every `engine/src/battle_engine/*.py` module and ran cycle detection:
**no cycle found**. Confirmed directly: `entrant_identity.py` and
`scheduler.py` import nothing from `battle_engine` (leaf dependencies,
same as `rules.py`); `ruleset_policy.py` imports only `rules` and
`scheduler`, both leaves; `agent_state.py` imports only
`entrant_identity`. `ruleset_policy.py` does not import VM (`vm.py`,
`match.py`, `core.py`), the Python controllers, `agent_worker.py`,
`replay.py`, `scoring.py`, or `result_model.py` -- confirmed by its own
import list (three imports total: `__future__`, stdlib, `rules`,
`scheduler`). `mypy engine/src/battle_engine` and `mypy client/src/
battle_client` both ran clean (see "Validation").

## 17. Dead/redundant code findings

- **Fixed:** `match_service.py`'s comment immediately above the
  `resolve_ruleset_policy` call said "the one boundary where a homogeneous
  native match's Ruleset-v1 execution semantics (currently: entrant
  scheduling) are dispatched" -- accurate through Phase 3, stale since
  Phase 4 added termination to the same dispatched `RulesetPolicy`
  instance without this particular comment being updated. Changed to "(as
  of v1.5 Phase 4: entrant scheduling and match termination decision/
  reason)". This is the one and only source change this phase makes; it
  has zero runtime effect (comment-only).
- **Retained intentionally (not dead, verified in use):** every
  compatibility accessor listed in "Compatibility accessor audit" above;
  the `RULESET_V1`-defaulting constructor parameters; VM's synthetic
  `identity.name`.
- **Nothing else found dead or redundant.** No old scheduler helper, no
  duplicate termination helper, no unused import (`ruff check .`'s
  F-series rules already enforce this and passed clean both before and
  after this phase's one comment change), no dead field, no stale adapter
  function, and no unreachable compatibility path were found across the 10
  files Phases 2-5 touched or the rest of the 60-file engine source tree.
  Phase 6 is deliberately not a cleanup campaign -- see "Architecture
  freeze audit" below for why no further removal was pursued.
- **Deferred:** none -- there was nothing else concrete enough to defer.

## 18. Documentation changes

- `docs/V1_5_PHASE6_ARCHITECTURE_EQUIVALENCE.md` (new, this document).
- `docs/ROADMAP.md` -- v1.5 section updated with Phase 6 status (below the
  existing Phase 5 paragraph).
- `README.md`, `docs/RULES.md`, `docs/COMPATIBILITY.md`,
  `docs/FUTURE_PLANS.md` -- reviewed for v1.5/Phase staleness; none found.
  `RULES.md` never referenced internal class shapes (`MatchEntrant`/
  `Agent`/`PythonEntrantState`) in the first place, so it was never coupled
  to what Phase 5 changed. `COMPATIBILITY.md`'s "Phase" mentions are all
  pre-existing v0.10-era references, unrelated to v1.5. `README.md`
  correctly still shows v1.4.1 as the current release -- no premature
  v1.5.0 announcement.

## 19. Tests added/changed

**None.** Qualification found no gap in existing coverage worth filling
with a new test (see "Integrated-invariant test decision" below), and no
defect requiring a reproduction test. This is itself evidence Phase 6 was
qualification, not a redo of Phase 5's own test-writing work.

### Integrated-invariant test decision (Step 22)

Considered writing one compact test proving "service resolves Ruleset ->
scheduler runs -> termination resolves -> entrant identity remains
authoritative -> result/replay identity unchanged" as a single white-box
assertion chain. Declined: Phase 5's own
`test_vm_match_preserves_entrant_order_and_one_identity_per_execution_
state`, `test_python_match_preserves_entrant_order_and_one_identity_per_
execution_state`, and `test_vm_native_result_name_comes_from_match_
entrant_not_synthetic_agent_identity` already exercise a live
`NativeMatchService`/`Kernel`/`PythonEntrantController` match end-to-end
and assert on exactly this ownership chain; the golden corpus separately
proves the full chain produces stable, byte-identical identity and replay
content across six real scenarios. A new test would either duplicate this
coverage or become the "giant brittle white-box test" the phase brief
explicitly warns against. Skipped per the brief's own instruction:
"Skip it if current coverage already proves the same thing better."

## 20. Defects found

**No v1.5 architecture defect found.** The one change this phase makes to
production source (`match_service.py`'s comment) is a documentation-
accuracy fix, not a behavioral defect -- it has no test-observable effect
and required no reproduction, source-of-defect analysis, or re-
qualification beyond the standard full validation re-run (which passed
identically before and after).

## 21. Golden corpus

`engine/tests/test_ruleset_v1_equivalence.py`: **8 passed, zero Ruleset-v1
differences** -- re-confirmed against current `HEAD` (post the one comment
fix) and, independently, against the actual v1.4.1 source tree in an
isolated worktree (see "v1.4.1 equivalence").

## 22. Validation

**Focused** (golden corpus + ruleset policy + scheduler + scheduler/Python
scheduler characterization + entrant identity + native match service +
match services + supervised runtime + python runtime + replay
reconstruction + ownership accounting + ruleset persistence): all passed,
both before this phase's one comment edit and after.

**Full suite** (`python -m pytest`, via `--junitxml`):

- Baseline re-run at the start of Phase 6 (before any change): `tests=
  "1289"`, `skipped="6"`, `errors="0"`, `failures="0"` -> **1283 passed, 6
  skipped**.
- A run concurrent with an independent WSL full-suite attempt hit a
  transient Windows cleanup error (`WinError 145`, directory not empty)
  against the shared, repo-local `.pytest-tmp` -- diagnosed as the
  cross-environment concurrent-access collision described in "Platform
  qualification," not a code defect. The WSL process was stopped, both
  `.pytest-tmp` and `.pytest-cache` were removed, and the suite was
  re-run cleanly, sequentially: `tests="1289"`, `skipped="6"`,
  `errors="0"`, `failures="0"` -> **1283 passed, 6 skipped** again,
  confirming the transient failure was environmental, not a regression.
- Final count: **1283 passed, 6 skipped, 0 failures, 0 errors** -- exactly
  the Phase 5 baseline, with zero new tests (none were added this phase)
  and zero removed tests.

**Static validation:**

- `ruff check .`: all checks passed (before and after the one comment
  change).
- `mypy engine/src/battle_engine`: no issues found (60 source files, same
  count as Phase 5 -- no new module this phase).
- `mypy client/src/battle_client`: no issues found (10 source files,
  unchanged).

## 23. Files changed

- `engine/src/battle_engine/match_service.py` -- one comment updated (see
  "Dead/redundant code findings"); no behavioral change.
- `docs/V1_5_PHASE6_ARCHITECTURE_EQUIVALENCE.md` (new, this document).
- `docs/ROADMAP.md` -- v1.5 section updated with Phase 6 status.

No other file changed. No test file changed. No other source file
changed.

## 24. Commits

- `c25c1e0` -- Phase 5, already qualified (starting point for this phase,
  not a Phase 6 commit).
- This phase's own commit: see the commit immediately following this
  document in `git log` on `v1.5-development` (documentation- and
  comment-only; message: `test/docs: qualify v1.5 architecture
  equivalence`).

## 25. Remaining architectural debt

| Item | Classification |
|---|---|
| Scoring outside Ruleset policy | Intentional v1.5 boundary -- confirmed unchanged and untouched this phase; not a release blocker. |
| Winner resolution outside Ruleset policy | Intentional v1.5 boundary -- same as above; the one `results.py` change this phase's predecessor (Phase 5) made was type-only. |
| VM/Python execution states remain distinct | Intentional v1.5 boundary -- explicit non-goal since the original v1.5 Phase 5 brief; not a release blocker. |
| Runtime controllers (`PythonEntrantController`/`SupervisedPythonEntrantController`) remain distinct | Intentional v1.5 boundary, pre-dates v1.5; not a release blocker. |
| Compatibility accessors retained (`agent_id`/`name` properties, `RULESET_V1` defaults) | Intentional v1.5 boundary -- verified this phase to be low-risk and appropriately scoped; not a release blocker. |
| Low-level runtime constructors defaulting to `RULESET_V1` | Intentional v1.5 boundary, verified non-authoritative (see "Ruleset dispatch audit"); not a release blocker. |
| VM synthetic `identity.name` | Intentional v1.5 boundary, documented and test-protected; not a release blocker. |
| `dataclasses.replace()` unsupported on `MatchEntrant`/`Agent`/`PythonEntrantState` | Intentional, narrow limitation, nothing currently depends on it; not a release blocker. |
| Mixed VM/Python execution unsupported | Intentional v1.5 (and prior) boundary; not a release blocker. |
| Only one execution state per entrant supported | Intentional v1.5 boundary, by design; not a release blocker. |
| No Ruleset v2 | Explicitly out of v1.5 scope (v2.x research boundary per `docs/ROADMAP.md`); not a release blocker. |
| No Agent API v2 | Same as above; not a release blocker. |
| Full WSL/Linux full-suite run not completed this session (I/O-speed-limited, not a failure) | Future v1.x cleanup/verification opportunity -- recommend re-attempting during release-preparation platform qualification (Phase 7), ideally from a native Linux filesystem rather than `/mnt/d/`'s cross-OS bridge, or accept the golden-corpus-plus-focused-set evidence already gathered as this repository's established sufficient bar (consistent with how Phase 1-5 never ran a full cross-platform suite either). Not a release blocker on its own. |
| Frozen application/installer/portable-ZIP packaging not qualified this phase | Deliberately deferred to release preparation, consistent with established project convention; not a release blocker for an architecture-freeze decision. |

No item above is a release blocker for the architecture-freeze decision
itself; several are explicitly release-preparation-phase work (Linux
full-suite confirmation, frozen-application packaging) rather than
architecture debt.

## 26. Architecture freeze verdict

**V1.5 ARCHITECTURE QUALIFIED — FREEZE FOR RELEASE PREP**

The combined result of Phases 2-5 is proven equivalent to v1.4.1
Ruleset-v1 behavior by direct, executed evidence (golden corpus re-run
against the actual v1.4.1 source tree, byte-identical golden test file,
zero-diff `vm.py`/`scoring.py`/`statistics.py`/`rules.py`), deterministic
identity is unchanged (match/result/replay IDs, Python seed golden
vectors), persisted schemas are unchanged, native execution is sound
(live CLI and production-API runs for VM, unsupervised Python, and
supervised Python, at 2 and 3 entrants, non-default scheduler quota, and
through a real installed wheel), and no architectural bypass, duplicate
identity storage, or one-to-many execution-state path exists anywhere in
the 60-file engine source tree. The one production change this phase
made is a single stale comment, not a behavioral fix. No further
production architecture refactor is justified before release
preparation.

## 27. Recommended Phase 7 boundary

**v1.5.0 Release Qualification & Publication** -- narrowly scoped to:
version identity bump (`pyproject.toml`, `--version` output, wheel/
`dist-info` metadata -- currently still `1.4.1`, correctly unbumped
through Phase 6), `CHANGELOG.md`/`README.md`/`docs/ROADMAP.md` updates
marking v1.5.0 as the current release, full Windows installer/portable-ZIP/
wheel/source-archive build and lifecycle qualification (install/upgrade/
uninstall, per the v1.0-v1.4 release-qualification precedent this
repository already established), a genuine Linux platform qualification
pass (completing what this phase's WSL attempt could not finish in time --
ideally from a native Linux checkout rather than a cross-OS `/mnt/`
bridge, to avoid the I/O-speed and concurrent-access issues this phase
encountered), the four frozen PyInstaller applications' build/branding/
icon qualification, a final pre-tag golden-corpus and full-suite sweep,
and the actual `git merge`/tag/publish/release-asset steps. None of that
belongs in Phase 6, and none of it was performed here.
