# Bytefray v3 Phase 0 — Research Baseline and Experimental Infrastructure

Branch: `v3-research-phase0`. Base: `main` at `1093393`, immediately after
the published v2.0.0 release. Status: implementation complete, not merged,
not tagged, not published.

Phase 0 is **not** a Ruleset-v3 gameplay phase. It builds the trusted
experimental foundation every later v3 hypothesis will be tested against:
a frozen benchmark population, the evaluation plumbing needed to vary arena
size and action budget under control, and a measured Ruleset-v2 ecology
baseline scored against the Beta2 Phase 4 §17 rubric.

No locality, movement, multiple loci, replication, Agent API v2, fog of
war, new combat actions, resource systems, or Ruleset-3 semantics were
implemented, and none were needed.

---

## 1. Initial state

Verified before any change:

| ref | value |
|---|---|
| starting branch | `main` |
| HEAD | `1093393b401aabda243ed89b7c44fa91938477b5` |
| `main` | `1093393` (identical to HEAD) |
| `origin/main` | `1093393` (identical — no unpushed divergence) |
| `v2.0.0` tag | annotated, targets `965d2f6` ("chore(release): prepare Bytefray v2.0.0") |
| commits after the tag | `17725e4` "docs: mark v2.0.0 published", `1093393` "docs: remove stale duplicate v1.6.0 stable-release line from README" |
| working tree | clean |

`v2.0.0` is an ancestor of HEAD, and the only two commits past the tag are
documentation-only publication records. The published v2.0 state is
complete and Phase 0 begins from the intended post-v2 baseline.

v2 development branches present and untouched: `v2.0-development`,
`v2.0-beta1-development`, `v2.0-beta2-development`, `v2.0-beta3-development`,
`v2.0-rc2-development`, `v2.0-final-development`. No historical tag or
protected branch was modified. Work proceeded on a new branch
`v3-research-phase0` cut from `1093393`.

---

## 2. Phase 0 purpose

Phase 0 answers one question: *can later phases be trusted to measure what
they claim to measure?* It produces three things.

1. **A frozen benchmark population** — "the Phase-0 v2 benchmark
   population" names one exact set of immutable agent revisions, forever.
2. **Controlled experimental parameters** — arena size and per-tick action
   budget can now be varied through ordinary evaluation matrices, which
   Phase 1's arena-size-versus-action-budget research requires.
3. **A measured control corpus** — the final Ruleset-v2 ecology,
   reproduced from that frozen population under declared conditions and
   scored against Beta2 Phase 4 §17's own rubric, so Phase 1 and Phase 2
   are measured against evidence rather than recollection.

The governing engineering constraint throughout was that **omission changes
nothing**: an evaluation that does not name the new parameters behaves,
identifies, and persists exactly as it did before Phase 0.

---

## 3. Frozen benchmark population

The architecture review counted nine in-tree agents — five starter agents
and four reference agents. The repository confirms this, with a
clarification: there are **nine Python (Agent API v1) agents**, which is
the meaningful Ruleset-v2 strategic population. `starters.py` lists nine
starter names, but its first four (`runner`, `writer`, `seeker`, `spiral`)
are manifest-only native VM starters with no `agent.py`; the remaining five
are the Python starters added in v0.6.1. Adding the four v2 reference
agents from `reference_agents.py` gives nine.

The population is pinned in committed package data,
[`engine/src/battle_engine/data/benchmarks/v2_baseline.json`](../engine/src/battle_engine/data/benchmarks/v2_baseline.json),
and loaded/verified through the new `battle_engine.benchmarks` module.

### Mechanism, and why this one

Phase 0C asked for the lightest mechanism consistent with existing
architecture. The chosen mechanism is **a manifest layered over the
agent-revision provenance infrastructure that already exists** — not a
parallel identity scheme:

- Each member is pinned by `agent_revision_id`, the content-addressed
  `agent-revision_<sha256>` id `agent_revisions.agent_revision_fingerprint`
  already computes.
- `source_sha256` and `local_python_subset_fingerprint` are recorded
  alongside — the same two fields
  `agent_evaluation._post_execution_identity_drift` already treats as
  executor ground truth.
- `benchmarks.verify_population()` recomputes all three through those same
  functions, so a benchmark drift means exactly what an evaluation drift
  means.

No registry, no signing, no distribution surface was built. A repository
edit to an agent after Phase 0 changes what `verify_population` *reports*,
but cannot change what the benchmark *means*.

### The nine pinned members

All nine verify against the current tree.

| agent | catalog | strategic role | `agent_revision_id` (truncated) | `source_sha256` (truncated) |
|---|---|---|---|---|
| `claimer` | starter | blind expansion | `agent-revision_4b7b55c2ab0c…` | `3666d81cd6a30b51…` |
| `strider` | starter | expansion + rolling periodic defense | `agent-revision_05755119a20d…` | `98118005018c7580…` |
| `hunter` | starter | dispersed expansion | `agent-revision_e892536b4317…` | `cd988d1f22ec4755…` |
| `wanderer` | starter | randomized-order expansion | `agent-revision_fb90a6367cff…` | `c2dadede51f61a24…` |
| `adaptive` | starter | phase-switching generalist | `agent-revision_bb2f2858909e…` | `4555fe5a7c3916ab…` |
| `core_defender` | reference | unconditional (blind) defense + expansion | `agent-revision_c0e6fb0847b3…` | `316acd660777a90f…` |
| `reactive_core_defender` | reference | reactive/efficient defense + expansion | `agent-revision_51152cd2df94…` | `01c616c109752708…` |
| `core_seeker` | reference | dedicated search-and-destroy offense (historical control) | `agent-revision_d38b09bde99d…` | `a829d5fdf797284d…` |
| `core_tracker` | reference | dedicated search-and-destroy offense (placement-agnostic benchmark) | `agent-revision_307b9385af77…` | `4277d344fc86192f…` |

Full untruncated ids are in the manifest. Every member is
`runtime_kind: python`, `agent_api_version: 1`, `agent_version: 0.1.0`,
`entry_point: agent.py:create_agent`, with exactly two pinned files
(`agent.py`, `agent.yaml`) and a complete (nothing-omitted) revision walk.

### Ecology core

The manifest also names `ecology_core` — the six agents Beta2 Phase 4 §3
actually used for the final v2 ecology analysis: `claimer`, `hunter`,
`core_defender`, `reactive_core_defender`, `core_tracker`, `core_seeker`.
`strider`, `wanderer`, and `adaptive` are pinned members of the population
but were not part of that corpus; including them keeps the population
complete without retroactively widening the Beta2 rubric's evidence base.

### Continuity with Beta2

Every one of the nine agent sources is **byte-identical to its state at
Beta2 Phase 4's final commit `2662a5f`** (verified by `git hash-object`
against that tree). The Phase-0 baseline therefore reproduces Beta2's
numbers from literally the same code, not merely from equivalent code —
which is what makes §8's exact reproduction meaningful rather than
coincidental.

---

## 4. Evaluation plumbing changes

### The gap

The independent review's finding is confirmed. `bytefray run` already
accepted `--arena` and `--quota`, and `Config` already carried `arena_size`
and `instr_per_tick` — but the evaluation path constructed its match
configuration as `Config(seed=effective_seed)` in
`agent_test._test_agent`/`_test_agents`, and
`agent_evaluation.effective_conditions_for` hardcoded `Config()`'s own
defaults. Arena size and action budget could not be varied through an
evaluation matrix at all.

### The complete path, as it now runs

```text
CLI  --arena-size / --instr-per-tick        (or a preset's arena_size / instr_per_tick)
  ↓  explicit > preset > default resolution in agent_evaluation.main
EvaluationRequest.arena_size / .instr_per_tick        (None == "ordinary default")
  ↓  .resolved_arena_size / .resolved_instr_per_tick
  ├─→ standard_placements(resolved_arena_size)   → build_matrix        → cell starts
  ├─→ standard_layouts(n, resolved_arena_size)   → _build_group_matrix → seat starts
  ├─→ EvaluationService._effective_conditions
  │      ↓
  │   effective_conditions_for(ticks, api, arena_size, instr_per_tick)
  │      ↓
  │   EffectiveConditions.arena_size / .action_budget
  │      ├─→ _evaluation_id  ("effective_conditions" key)
  │      ├─→ effective_conditions_fingerprint  (persisted, drives comparability)
  │      └─→ evaluation.json "effective_conditions"
  └─→ EvaluationService._execute_cell(cell, ticks, data_root, identities,
                                      arena_size, instr_per_tick)
         ├─ serial:   direct call
         └─ parallel: _evaluation_dispatcher_loop → EvaluationCellWorkerHandle
                          .submit_cell(..., arena_size=, instr_per_tick=)
                      → worker wire keys → _handle_run_cell → _execute_cell
         ↓
      agent_test.test_agent(...)   /   agent_test.test_agents(...)
         ↓
      Config(seed=…, arena_size=…, instr_per_tick=…)
         ↓
      MatchRequest → NativeMatchService.run
         ├─→ canonical_match_id  ("reproducibility": arena_size, action_budget, tick_limit)
         ├─→ result.json  "reproducibility"
         └─→ replay.jsonl header  "config" + "reproducibility"
```

Resume verification (`_expected_cell_match_id` /
`_expected_group_cell_match_id`) received the same two parameters, because
it must rebuild the identical `Config` the original run executed under —
without that, every completed cell of a non-default evaluation would report
a false `resumed_result_mismatch`.

### Placements and layouts: a correctness fix, not just plumbing

`standard_placements()` and `standard_layouts()` already accepted an
`arena_size` argument, but **every call site invoked them without one**, so
they silently fell back to `Config().arena_size`. Left alone, a 1024-cell
arena would have been given the 4096-derived `opposed` placement
`(0, 2048)`; `MatchEntrant.python` wraps a start modulo arena size, so
`2048 % 1024 == 0` and both entrants would have started in the same core.
The experiment would have measured placement collision rather than the
variable under test. All five call sites now derive from
`request.resolved_arena_size`.

### Validation added

`EvaluationService._validate` fails closed on an arena too small for its
roster. The bound is derived, not arbitrary: the tightest standard layout
gap is `arena_size // (2 * entrant_count)`, and both placement functions
are documented non-overlapping only while that exceeds `CORE_SIZE` (8), so
the minimum is `2 * entrant_count * (CORE_SIZE + 1)`. A non-positive action
budget is likewise rejected.

### Tick limit

Match `ticks` was already cleanly configurable and fully persisted through
the identity path before Phase 0 — `EvaluationRequest.ticks`, `--ticks`,
the `ticks` preset field, `EffectiveConditions.tick_limit`, a top-level
`ticks` key *and* `effective_conditions` inside `_evaluation_id`, and
`tick_limit` in `canonical_match_id`'s reproducibility block. No change was
needed, and none was made.

---

## 5. Compatibility and identity assessment

**Nothing was bumped, and nothing needed to be.**

| axis | changed? | reasoning |
|---|---|---|
| Ruleset identity (`bytefray-rules-2`) | **No** | [docs/RULES.md](RULES.md)'s "Configuration values are not Ruleset identity" is explicit, and `canonical_match_id`'s own docstring restates it: `reproducibility` is "specifically about per-match *configuration*, not gameplay identity". Selecting an existing `Config` value the engine has always supported is not a semantic redefinition. Ruleset-v2 semantics are untouched. |
| Agent API version | **No** | No `Observation`, `AgentContext`, or `AgentAction` field changed. Agents receive no new information. (`Observation` does not expose arena size, which is itself a Phase 1 finding — see §12.) |
| Result schema (`battle2.result`) | **No** | `arena_size`, `action_budget`, and `tick_limit` were *already* fields of the persisted `reproducibility` block. Their wire shape is unchanged; only their range of values widened. |
| Replay schema (`battle2.replay`) | **No** | Same: the replay header already carried both a full `config` object and a `reproducibility` block containing them. |
| Evaluation schema (`bytefray.evaluation` v5/v6) | **No** | `effective_conditions` already contained `arena_size` and `action_budget`. No key was added, removed, or retyped in any persisted artifact. |
| Evaluation methodology identity | **No** | This is the important one. `_evaluation_id` already hashed `"effective_conditions": asdict(conditions)`, which already included both fields. Phase 0 made them *variable*; they were always *identity-bearing*. |

The decisive evidence is empirical, not argumentative:

```text
effective_conditions_for(400, 1)                              == 
effective_conditions_for(400, 1, arena_size=4096, instr_per_tick=8)     → True
stable_id("evaluation-conditions", …) for both                 → identical
```

and `preflight(...)` with the parameters omitted returns the same
`evaluation_id` as `preflight(..., arena_size=4096, instr_per_tick=8)`.
A varied arena produces a different `evaluation_id` — which is correct
behaviour for an identity that already covered the field, not a bump.

### The one non-identity change

`agents evaluations show` gained a **conditional** disclosure of non-default
arena size and action budget. At defaults it prints nothing, so every
historical artifact's `show` output is unchanged character-for-character.
This is not an identity or schema change; it exists because omitting a
now-variable condition from human-readable output would be misleading —
a 1024-cell artifact read back was previously indistinguishable from a
4096-cell one.

### Deferred surfaces deliberately left alone

Per Phase 0E's instruction not to "clean up" deliberately deferred
decisions, the following were observed and **not** touched: the
`WINNER_TIE_SENTINEL` winner semantics, `_classify_unmatched`'s
`(opponent_id, seed)` ambiguity grouping, the pairwise-only
`EvaluationPlacement` model kept separate from `EvaluationLayout`, the
`battle2.*` schema identifiers retained under the Bytefray brand, and
`--group`'s absence from the preset schema.

---

## 6. Experimental-variable matrix

Verified against current code and against real artifacts produced by this
phase, not from documentation.

| Variable | Runtime config | Persisted | Canonical match identity | Evaluation identity | Comparability |
|---|---|---|---|---|---|
| **arena size** | `Config.arena_size`; `run --arena`; `evaluate --arena-size`; preset `arena_size` | `result.json` + `replay.jsonl` `reproducibility.arena_size`; replay header `config.arena_size`; `evaluation.json` `effective_conditions.arena_size` | **Yes** — `reproducibility.arena_size` | **Yes** — via `effective_conditions`; also changes the hashed `placements`/`layouts` sets | **Yes** — via `effective_conditions_fingerprint` in `_condition_key` |
| **action budget** (`instr_per_tick`) | `Config.instr_per_tick`; `run --quota`; `evaluate --instr-per-tick`; preset `instr_per_tick` | `reproducibility.action_budget` (result + replay); replay header `config.instr_per_tick`; `effective_conditions.action_budget` | **Yes** — `reproducibility.action_budget` | **Yes** — via `effective_conditions` | **Yes** — via `effective_conditions_fingerprint` |
| **tick limit** | `MatchRequest.max_ticks`; `run --ticks`; `evaluate --ticks`; preset `ticks` | `reproducibility.tick_limit`; `effective_conditions.tick_limit`; top-level `ticks` | **Yes** — `reproducibility.tick_limit` | **Yes** — both a top-level `ticks` key and `effective_conditions.tick_limit` | **Yes** — via `effective_conditions_fingerprint` |
| **ruleset identity** | `run --ruleset`; `evaluate --ruleset`; preset `ruleset` | `result.json`/`replay.jsonl` `ruleset_id`; `evaluation.json` `rules_compatibility_id`; per-cell `rules_compatibility_id` | **Yes** — first-class `ruleset_id` axis, never folded into `reproducibility` | **Yes** — `rules_compatibility_id`, plus `identity_version`/`arena_alignment_mode` | **Yes** — `_rules_id`, fails closed on unknown |
| **entrant order / orientation** | orientation via `--single-orientation`/`--both-orientations`, preset `orientation`; physical order via entrant tuple position | `reproducibility.entrant_order`; per-cell `orientation`, `subject_start`, `opponent_start` | **Yes** — `reproducibility.entrant_order`, and positional order drives each entrant's derived seed | **Yes** — `orientation_mode`, plus the resolved `placements` set | **Yes** — orientation and placement are both `_condition_key` components |
| **entrant count / layout** | `--group` with N `--opponents` (not preset-settable) | per-cell `roster_agent_ids`, `seat_agent_ids`, `seat_starts`, `layout_id`; `evaluation.json` `group` | **Yes** — every seat is an entrant identity, and non-zero starts enter `metadata.start` | **Yes** — `group`, the resolved `layouts` set, `identity_version` 6 | **Yes** — keyed on canonical roster + seat assignment + layout, with non-candidate roster identities included |

**Gaps found and corrected**: exactly one — arena size and action budget
were not reachable from the evaluation path, and their derived placements
were computed from defaults. **Gaps found and deliberately not corrected**:
`--group` is not a preset field. That is not required for Phase 0's
controlled research (the corpus drives group mode through the CLI), and
adding it would be an opportunistic change to a surface Phase 0 has no
finding about.

---

## 7. Control corpus

Definition committed as package data at
[`engine/src/battle_engine/data/benchmarks/v2_baseline_corpus.json`](../engine/src/battle_engine/data/benchmarks/v2_baseline_corpus.json);
driver at
[`tools/v3_phase0_baseline_corpus.py`](../tools/v3_phase0_baseline_corpus.py).
The driver lives in `tools/` rather than gitignored `runs/` (Beta2's
convention) because a control corpus that Phase 1 and Phase 2 are measured
against has to stay rerunnable from the repository alone;
`tools/benchmark_platform_scaling.py` is the precedent.

```bash
python tools/v3_phase0_baseline_corpus.py run     --output runs/research_v3_phase0
python tools/v3_phase0_baseline_corpus.py analyze --output runs/research_v3_phase0
```

**Conditions**: `bytefray-rules-2`; arena size 4096; action budget 8 —
i.e. the ordinary defaults, stated explicitly. The control corpus
deliberately does **not** vary the new parameters: it is the baseline
Phase 1's varied conditions will be measured against, so it must not itself
vary them.

**Population**: the frozen `v2-baseline` benchmark, staged from the
manifest by `benchmarks.stage_population` rather than copied by hand.

**Size**: 1170 cells.

- **11 group rosters × 90 cells** = 990 cells. Each roster: seeds 1–5 × 3
  standard layouts × 6 seat permutations, 400 ticks.
- **6 pairwise controls × 30 cells** = 180 cells. Each: seeds 1–5 × 3
  standard placements × 2 entrant orientations, at 400 and 200 ticks.

The 11 rosters are Beta2 Phase 4's own pre-registered corpus, reproduced in
full rather than sampled. This is the *smallest* corpus that can score §17
verbatim: criterion 1 enumerates leaders across essentially all eleven
rosters, so a subset could not be scored against the rubric as written
without reinterpreting it.

Every number below comes from the production harness —
`agent_evaluation`'s CLI for execution,
`evaluation_group_analysis.analyze_group` for aggregates. Nothing is
hand-computed.

---

## 8. Reproduced v2 baseline

### Group rosters — all 25 published Beta2 rates reproduce at 0.0pp

`caused` is the capture-caused rate. 95% intervals are Wilson.

| roster | agent | Phase 0 | Beta2 | Δ | 95% interval | caused |
|---|---|---:|---:|---:|---|---:|
| claimer_coredefender_reactive | claimer | **100.0%** | 100.0% | +0.0 | [95.9, 100.0] | 0.0% |
| | core_defender | 0.0% | 0.0% | +0.0 | [0.0, 4.1] | 0.0% |
| | reactive_core_defender | 0.0% | 0.0% | +0.0 | [0.0, 4.1] | 0.0% |
| claimer_hunter_coredefender | claimer | **50.0%** | 50.0% | +0.0 | [39.9, 60.1] | 5.6% |
| | hunter | **50.0%** | 50.0% | +0.0 | [39.9, 60.1] | 0.0% |
| | core_defender | 0.0% | 0.0% | +0.0 | [0.0, 4.1] | 0.0% |
| claimer_hunter_reactive | claimer | 44.4% | 44.4% | +0.0 | [34.6, 54.7] | 5.6% |
| | hunter | **55.6%** | 55.6% | −0.0 | [45.3, 65.4] | 0.0% |
| | reactive_core_defender | 0.0% | 0.0% | +0.0 | [0.0, 4.1] | 0.0% |
| claimer_coretracker_coredefender | claimer | 44.4% | 44.4% | +0.0 | [34.6, 54.7] | 10.0% |
| | core_tracker | 10.0% | 10.0% | +0.0 | [5.4, 17.9] | 50.0% |
| | core_defender | **45.6%** | 45.6% | −0.0 | [35.7, 55.8] | 1.1% |
| claimer_coretracker_reactive | claimer | **48.9%** | 48.9% | −0.0 | [38.8, 59.0] | 11.1% |
| | core_tracker | 8.9% | 8.9% | −0.0 | [4.6, 16.6] | 50.0% |
| | reactive_core_defender | 42.2% | 42.2% | +0.0 | [32.5, 52.5] | 1.1% |
| claimer_coretracker_hunter | claimer | **36.7%** | 36.7% | −0.0 | [27.4, 47.0] | 1.1% |
| | core_tracker | 30.0% | 30.0% | +0.0 | [21.5, 40.1] | 46.7% |
| | hunter | 33.3% | 33.3% | +0.0 | [24.5, 43.6] | 2.2% |
| claimer_coreseeker_hunter | claimer | **44.4%** | 44.4% | +0.0 | [34.6, 54.7] | 0.0% |
| | core_seeker | 22.2% | 22.2% | +0.0 | [14.9, 31.8] | 61.1% |
| | hunter | 33.3% | 33.3% | +0.0 | [24.5, 43.6] | 0.0% |
| hunter_coretracker_coredefender | hunter | **45.6%** | 45.6% | −0.0 | [35.7, 55.8] | 6.7% |
| | core_tracker | 16.7% | 16.7% | −0.0 | [10.4, 25.7] | 42.2% |
| | core_defender | 37.8% | 37.8% | −0.0 | [28.5, 48.1] | 0.0% |
| reactive_hunter_coreseeker | reactive_core_defender | 0.0% | — | — | [0.0, 4.1] | 0.0% |
| | hunter | **50.0%** | — | — | [39.9, 60.1] | 5.6% |
| | core_seeker | **50.0%** | 50.0% | +0.0 | [39.9, 60.1] | 38.9% |
| hunter_coretracker_coreseeker | hunter | 25.6% | 25.6% | −0.0 | [17.7, 35.4] | 0.0% |
| | core_tracker | 33.3% | 33.3% | +0.0 | [24.5, 43.6] | 16.7% |
| | core_seeker | **41.1%** | 41.1% | +0.0 | [31.5, 51.4] | 18.9% |
| coredefender_reactive_coreseeker | core_defender | **50.0%** | — | — | [39.9, 60.1] | 5.6% |
| | reactive_core_defender | 44.4% | — | — | [34.6, 54.7] | 5.6% |
| | core_seeker | 5.6% | — | — | [2.4, 12.4] | 5.6% |

Bold marks the highest raw win rate in each roster. Four rosters' rates
were never published in full by Beta2 (those rows show "—"); they are
measured here for the first time and become part of the Phase-0 control.

### Pairwise controls — all six reproduce to rounding

| pair | ticks | cells | Phase 0 | Beta2 | Δ |
|---|---:|---:|---:|---:|---:|
| claimer vs core_tracker | 400 | 30 | 23.3% | 23% | +0.3pp |
| hunter vs core_tracker | 400 | 30 | 23.3% | 23% | +0.3pp |
| claimer vs hunter | 400 | 30 | 66.7% | 67% | −0.3pp |
| claimer vs core_tracker | 200 | 30 | 46.7% | 47% | −0.3pp |
| hunter vs core_tracker | 200 | 30 | 36.7% | 37% | −0.3pp |
| claimer vs hunter | 200 | 30 | 66.7% | 67% | −0.3pp |

Every delta is the rounding of an exact fraction (7/30 = 23.3%,
20/30 = 66.7%, 14/30 = 46.7%, 11/30 = 36.7%). Beta2's §16 tick-budget
finding reproduces exactly, including its mechanism: both `core_tracker`
matchups shift with tick budget (23.3% → 46.7% and 23.3% → 36.7%) while
the search-free `claimer` vs `hunter` matchup is **identical at both
budgets** (66.7%).

---

## 9. Beta2 Phase 4 §17 ecology rubric

The five criteria are reproduced **verbatim** from
[docs/V2_0_BETA2_PHASE4_STRATEGIC_CHARACTERIZATION.md](V2_0_BETA2_PHASE4_STRATEGIC_CHARACTERIZATION.md)
§17, unaltered, and the Phase-0 control is scored against each.

### Criterion 1 — "**Multiple viable archetypes**"

> **Multiple viable archetypes**: yes. Five of the six agents have the
> highest raw win rate in at least one tested roster: Claimer (5 of
> its 7 rosters), Hunter (`claimer_hunter_reactive`,
> and near-tied in `claimer_coretracker_hunter`), Core Defender
> (`claimer_coretracker_coredefender`, near-tied with Claimer), Reactive
> Core Defender (`claimer_coretracker_reactive`, `coredefender_reactive_
> coreseeker`), and Core Seeker (`reactive_hunter_coreseeker`
> tied at 50.0%, `hunter_coretracker_coreseeker` at 41.1%). Core Tracker
> has none outright — its best result is a
> three-way near-tie at 33.3% in `hunter_coretracker_coreseeker`, still
> consistent with alpha.11's own finding that search-based offense pays a
> real opportunity cost. Both search agents are nevertheless the
> *decisive* factor (highest
> `caused` rate) in every roster they join (§5/§7), a form of strategic
> value distinct from raw win rate.

**Phase 0 result: PASS, with a corrected count.** Four of the six ecology-core
agents hold the highest raw win rate in at least one roster:

| agent | rosters led |
|---|---|
| `claimer` | 5 — coredefender_reactive, hunter_coredefender (tied), coretracker_reactive, coretracker_hunter, coreseeker_hunter |
| `hunter` | 4 — hunter_coredefender (tied), hunter_reactive, hunter_coretracker_coredefender, reactive_hunter_coreseeker (tied) |
| `core_defender` | 2 — claimer_coretracker_coredefender, coredefender_reactive_coreseeker |
| `core_seeker` | 2 — reactive_hunter_coreseeker (tied), hunter_coretracker_coreseeker |
| `reactive_core_defender` | 0 |
| `core_tracker` | 0 |

Beta2's "five of the six" is not reproducible from Beta2's own §4 table;
see §10. The criterion's verdict is unaffected — four distinct archetypes
(blind expansion, dispersed expansion, unconditional defense, search
offense) lead across eleven rosters, and `core_tracker` remains the
*decisive* factor (highest `caused` rate, 42.2–50.0%) in every roster it
joins despite never leading on raw win rate. That distinction — strategic
importance without win-rate leadership — is the finding §17 most needed
preserved, and it reproduces exactly.

### Criterion 2 — "**Counter-strategies**"

> **Counter-strategies**: yes, one clear one (§5) — dedicated search
> defeats blind expansion, the central problem alpha.10/alpha.11 already
> set out to fix, confirmed still working under Beta2's own methodology.

**Phase 0 result: PASS, reproduced.** `claimer` falls to 23.3% against
`core_tracker` in direct 1v1 at 400 ticks. In group play the mechanism is
visible as capture: `core_tracker` `caused` 42.2–50.0% and `core_seeker`
18.9–61.1% in every roster they join, while every non-search agent stays
at 0.0–6.7%. Core capture remains the only demonstrated lever against
blind expansion.

### Criterion 3 — "**Context-sensitivity**"

> **Context-sensitivity**: yes, extensively (§10-§13) — seat, layout,
> and seed all materially affect outcomes, in roster-specific rather than
> universal patterns.

**Phase 0 result: PASS, reproduced.** Maximum within-roster win-rate range
across each axis: **seat 100.0pp**, **layout 33.3pp**, **seed 33.3pp**. The
patterns are roster-specific, not universal — `claimer_coredefender_reactive`
shows 0.0pp on all three axes (the negative control is fully determined),
while `claimer_hunter_coredefender` shows a 100.0pp seat swing with 0.0pp
layout and seed sensitivity.

### Criterion 4 — "**Multi-agent-specific behavior beyond repeated 1v1**"

> **Multi-agent-specific behavior beyond repeated 1v1**: yes, clearly
> (§6 kingmaking, §14 pairwise-vs-group divergence).

**Phase 0 result: PASS, reproduced.** Both effects:

*Kingmaking.* With a passive third present, `core_tracker` does the work
and someone else collects: in `claimer_coretracker_coredefender`,
`core_tracker` `caused` 50.0% but wins 10.0%, while `core_defender`
(`caused` 1.1%) wins 45.6%. Identically in `claimer_coretracker_reactive`
(50.0%/8.9% vs 1.1%/42.2%). The mechanism check reproduces too: remove the
search agent and the passive third wins **0.0%** in both
`claimer_hunter_coredefender` and `claimer_hunter_reactive` — an actual
elimination event is required to open the door.

*Pairwise-vs-group divergence.* `claimer` wins 23.3% against `core_tracker`
1v1, but 44.4% and 36.7% in the three-entrant rosters containing that same
pair. The reverse also holds: `claimer` beats `hunter` 66.7% 1v1 but drops
to 50.0% with a third present. Group outcomes are not repeated 1v1.

### Criterion 5 — "**Evidence of a simple universal solution**"

> **Evidence of a simple universal solution**: no single strategy wins
> broadly across dissimilar rosters at a rate approaching 90-100% except
> in the one negative-control roster with zero offensive pressure present
> by construction.

**Phase 0 result: PASS, reproduced exactly.** The only rate at or above 90%
in the entire corpus is `claimer`'s 100.0% in
`claimer_coredefender_reactive` — the negative control, where neither
opponent attacks anything (`caused` 0.0% for all three). Across the other
ten rosters, the highest rate by any agent is 55.6%. No universal solution.

**Overall: the Phase-0 control satisfies all five Beta2 §17 criteria.** The
Ruleset-v2 strategic ecology is reproduced and remains the ecology v2
shipped with.

---

## 10. Differences from historical v2 results

Three discrepancies were found. All are **documentation defects in Beta2
Phase 4, not measurement differences** — every measured value reproduces.

### 10.1 §17 credits Reactive Core Defender with two rosters it does not lead

§17 criterion 1 lists "Reactive Core Defender (`claimer_coretracker_reactive`,
`coredefender_reactive_coreseeker`)" among agents holding the highest raw
win rate in at least one roster. Beta2's **own §4 table** contradicts this
for the first: it records `claimer` 48.9% versus `reactive` 42.2%, so
`claimer` leads. Phase 0 reproduces both numbers exactly. For the second
roster, Beta2 published no rates; Phase 0 measures `core_defender` 50.0%
versus `reactive_core_defender` 44.4%, so `core_defender` leads there.

The likely cause is visible in §6's kingmaking table, where **bold marks
the passive third entrant**, not the roster leader. For the `core_defender`
row (44.4 / 10.0 / **45.6**) the bolded third happens also to be the
leader; for the `reactive_core_defender` row (48.9 / 8.9 / **42.2**) it is
not. Reading the bold as "leader" yields exactly §17's error.

**Consequence**: the correct count is four of six, not five of six. The
criterion still passes decisively. This is recorded, not corrected — the
rubric is used verbatim, and Phase 0 does not edit Beta2's historical
document.

### 10.2 §2 states 15-cell pairwise controls; the reported rates need 30

§2 describes the pairwise controls as "15 cells each (seeds 1-5, all 3
standard placements)" — i.e. single-orientation. But 23% is not
expressible on a 15-cell denominator, and a single-orientation rerun
measures 33.3% (5/15), not 23%. On the 30-cell both-orientations
denominator the published value reproduces exactly: 7/30 = 23.3%. Every
other pairwise control reproduces on the same 30-cell reading. The
committed corpus definition declares 30 cells and records this note.

### 10.3 §3's archetype table describes a superseded Hunter

§3 characterizes Hunter as "Scans for contested ground […] seizes with a
short write burst | opportunistic offense". The shipped `hunter/agent.py`
describes itself as a *disperser* that stakes scattered claims before
filling in, and its docstring explicitly records that the scan-and-burst
version was abandoned because it lost consistently. `git log` shows that
rebalance (`4f4f36b`, 2026-08-09) landed **before** Beta2 Phase 4's final
commit (`2662a5f`, 2026-08-20), so §3's description was already stale when
written. The *numbers* are unaffected — Phase 0 confirms the agent source
is byte-identical to Beta2's, so Beta2 ran the disperser too. Only the
archetype label was wrong. The benchmark manifest records the accurate role
("dispersed expansion") with a pointer to this section.

This matters for v3: Hunter is **not** a second offense archetype. The
corpus contains exactly two genuine offense agents (`core_tracker`,
`core_seeker`), which Phase 1 should not over-count when reasoning about
archetype coverage.

---

## 11. Performance baseline

Measured on the Phase 0 development machine (Windows 11, Python 3.11).
Recorded for later scaling comparison only; nothing was optimized.

| measure | value |
|---|---|
| representative match (400 ticks, 3 entrants, 4096 arena) | ~190 ms serial; ~60 ms/cell at `--workers 4` |
| pairwise cell (400 ticks, 2 entrants) | ~55 ms/cell at `--workers 4` |
| group evaluation (90 cells) | 17.1 s serial → 5.6 s at `--workers 4` (**3.1× speedup**) |
| full control corpus (1170 cells, 17 evaluations) | **69.1 s** at `--workers 4` |
| `replay.jsonl` per cell | mean 538 KB, max 790 KB |
| `result.json` per cell | mean 4.2 KB |
| `evaluation.json` per evaluation | mean 108 KB |
| full corpus on disk | **651 MB** |

The dominant cost is replay volume, not compute: 1170 replays account for
essentially all of the 651 MB. If a later phase multiplies cell counts
substantially, artifact volume will bind before wall-clock does. No
distributed evaluation or artifact compression was implemented — that
remains correctly out of scope.

---

## 12. Action-density metric groundwork

Phase 1 will investigate arena size versus action budget. Phase 0
deliberately **does not** declare a density formula. It records the
candidates, their assumptions, their computability, and one measured
observation that materially constrains Phase 1's design.

### Candidate normalizations

All are pure functions of values already persisted in
`effective_conditions` and each result's `reproducibility` block, so **all
are computable today with no new engine instrumentation**.

| candidate | formula | at defaults (3 entrants) | assumption |
|---|---|---|---|
| instantaneous density | `instr_per_tick / arena_size` | 0.00195 | Ignores match length; comparable only at equal ticks. |
| per-entrant action budget | `instr_per_tick × tick_limit` | 3200 | Not normalized by arena; not comparable across arena sizes. |
| **per-entrant sweeps** | `(instr_per_tick × tick_limit) / arena_size` | 0.781 | Assumes one action ≈ one cell claimed. An upper bound: a `READ` costs an action and claims nothing. |
| **aggregate contested pressure** | `(entrants × instr_per_tick × tick_limit) / arena_size` | 2.34 | Same, plus assumes entrant budgets are independent — true today (one fixed budget per entrant). |
| realized action density | `Σ cpu_total / arena_size` | measured per match | No modelling assumption at all: `cpu_total` and `mem_writes` are recorded per entrant in every result. Accounts for early termination. |

The last row is worth flagging: because matches can end before the tick
limit, *nominal* budget and *realized* actions diverge, and the harness
already records the realized figure. Phase 1 should prefer it wherever a
derived measure is compared across conditions.

Phase 0H's binding requirement is met: raw `arena_size`, `action_budget`,
`tick_limit`, realized `ticks`, and per-entrant `cpu_total`/`mem_writes`
are all retained in persisted artifacts, so any of these normalizations —
or one not yet conceived — remains derivable later.

No locality-derived concept (travel distance, reach radius) is proposed,
because those mechanics do not exist.

### Measured observation: the default arena is near-saturated

Summed final territory across all three entrants, per roster:

| roster | Σ territory | roster | Σ territory |
|---|---:|---|---:|
| claimer_hunter_coredefender | 97.8% | claimer_coreseeker_hunter | 83.8% |
| claimer_hunter_reactive | 97.7% | hunter_coretracker_coredefender | 83.8% |
| claimer_coredefender_reactive | 96.5% | claimer_coretracker_hunter | 81.0% |
| coredefender_reactive_coreseeker | 92.4% | hunter_coretracker_coreseeker | 59.0% |
| claimer_coretracker_reactive | 86.0% | | |
| claimer_coretracker_coredefender | 85.7% | | |

At default conditions the arena ends **81–98% claimed** in ten of eleven
rosters (the exception, 59%, is the offense-heavy roster where matches end
early on capture). Aggregate nominal pressure is 2.34 sweeps against an
arena that saturates well below that.

**Implication for Phase 1**: action budget is not the binding constraint at
current defaults — the arena is. An experiment that raises the action
budget without also raising arena size risks measuring a ceiling rather
than a strategy effect. This is a Phase-0 observation offered as an input
to Phase 1's design, not a conclusion about locality.

### An arena-size assumption already embedded in an agent

`wanderer`'s own docstring states it picks a random **odd** stride
"which keeps it coprime with the default power-of-two arena size, so it
still reaches every cell exactly once per full pass". That guarantee holds
only for power-of-two arenas. Phase 1 experiments that vary arena size
should either keep arena sizes powers of two or explicitly account for this
when `wanderer` is in the roster. `wanderer` is not in the Beta2 ecology
core, so no Phase-0 baseline number is affected.

---

## 13. Validation

| check | result |
|---|---|
| Focused Phase 0 tests | 36 passed (20 conditions + 16 benchmark/preset/comparability) |
| Full test suite (`python -m pytest`) | **1972 passed, 14 skipped, 2 deselected**. Measured pre-Phase-0 baseline (both new files ignored): 1936 passed — so the delta is exactly the 36 new tests, with no pre-existing test altered |
| `ruff check .` | All checks passed |
| `mypy engine/src/battle_engine` | Success, no issues in 75 source files |
| `mypy client/src/battle_client` | Success, no issues in 12 source files |
| Historical artifacts still load | 19 real pre-Phase-0 `evaluation.json` artifacts (schema v5 ×8, v6 ×11) load through `adapt_any` with 0 failures |
| Non-default evaluation reproduces deterministically | Yes — two independent runs at arena 1024 / budget 4 produce identical `evaluation_id` and identical per-cell `match_id`/`outcome` |
| Control corpus reproduces | Yes — a roster rerun into a fresh directory matches the corpus artifact cell-for-cell |
| Serial vs parallel equivalence | Yes — `--workers 1` and `--workers 3/4` produce identical results at non-default conditions |
| Resume verification at non-default conditions | Yes — no `resumed_result_mismatch`, no corrupted cells |
| Benchmark population verifies | 9/9 members match their pinned revisions |
| Working tree | clean |

No pre-existing static-analysis debt was encountered or altered.
[docs/RUFF_DEBT.md](RUFF_DEBT.md)'s three project-wide ignores
(`BLE001`, `S110`, `TRY004`) were not modified.

### Test coverage added

`engine/tests/test_v3_phase0_evaluation_conditions.py` (20 tests) —
defaults and identity preservation, conditions fingerprinting, placement
and layout derivation from arena size, validation bounds, pairwise and
group propagation into real matches, determinism, resume, serial/parallel
equivalence, and human-readable disclosure.

`engine/tests/test_v3_phase0_benchmark_population.py` (16 tests) —
manifest shape, revision pinning, live-tree verification, ecology-core
membership, staging and discoverability, preset field parsing/validation/
round-trip, and comparability (differing conditions do not cleanly compare;
identical and explicit-default conditions still align).

---

## 14. Phase 0 verdict

**PASS — Phase 1 research is supported.**

The control corpus reproduces the published v2 ecology exactly — all 25
Beta2 group win rates at 0.0pp, all 6 pairwise controls to rounding — from
a population pinned to immutable, verified agent revisions that are
byte-identical to Beta2's own. All five §17 criteria are satisfied by the
Phase-0 control. Arena size and action budget are controllable end-to-end
through pairwise, group, preset, and parallel paths, deterministically,
with no identity, schema, or Ruleset change and with byte-identical
behavior when omitted.

The three discrepancies in §10 are documentation defects in Beta2's report,
not failures to reproduce, and each is recorded with its evidence rather
than corrected in place.

No scope-excluded mechanic was required to establish the baseline, so there
is no BLOCKER finding.

---

## 15. Files changed

| file | change |
|---|---|
| `engine/src/battle_engine/agent_evaluation.py` | `EvaluationRequest.arena_size`/`instr_per_tick` + resolved properties; `effective_conditions_for` parameters; `_effective_conditions`, `preflight`, `_validate`; arena-derived placements/layouts at all 5 call sites; `_execute_cell`/`_execute_group_cell`/`_expected_*_match_id` threading; dispatcher wiring; `--arena-size`/`--instr-per-tick` CLI + resolution; `_print_experimental_conditions` |
| `engine/src/battle_engine/agent_test.py` | `test_agent`/`test_agents` (+ private forms) accept the two parameters and build `Config` from them |
| `engine/src/battle_engine/evaluation_worker.py` | `submit_cell` and `_handle_run_cell` carry the two values as explicit wire keys |
| `engine/src/battle_engine/evaluation_presets.py` | `arena_size`/`instr_per_tick` preset fields: allow-list, dataclass, validation, JSON round-trip, `show` output |
| `engine/src/battle_engine/evaluation_history/cli.py` | conditional non-default condition disclosure in `show` |
| `engine/src/battle_engine/benchmarks.py` | **new** — benchmark population manifest loader, verifier, stager |
| `engine/src/battle_engine/data/benchmarks/v2_baseline.json` | **new** — the frozen nine-member population |
| `engine/src/battle_engine/data/benchmarks/v2_baseline_corpus.json` | **new** — the control-corpus definition with pinned Beta2 rates |
| `tools/v3_phase0_baseline_corpus.py` | **new** — corpus `run`/`analyze` driver |
| `engine/tests/test_v3_phase0_evaluation_conditions.py` | **new** — 20 tests |
| `engine/tests/test_v3_phase0_benchmark_population.py` | **new** — 16 tests |
| `docs/V3_PHASE0_RESEARCH_BASELINE.md` | **new** — this report |

## 16. Commits

| SHA | message |
|---|---|
| `2370033` | feat(evaluation): expose arena size and action budget as controlled conditions |
| `253fccb` | feat(benchmarks): freeze the Ruleset-v2 benchmark population |
| `063111c` | feat(research): add the v3 Phase 0 Ruleset-v2 control corpus |
| `ebe72a1` | feat(evaluation-history): disclose non-default experimental conditions in show |

Nothing merged to `main`, nothing tagged, nothing published.

---

## 17. Recommended Phase 1 entry conditions

Phase 1 may now safely assume:

1. **A named, immutable population.** "The Phase-0 v2 benchmark
   population" resolves to nine verified agent revisions; the six-agent
   `ecology_core` is the subset the §17 rubric applies to.
2. **A reproducible control.** The v2 ecology baseline is measured, not
   recalled, and rerunnable in ~69 s from the repository alone.
3. **Controlled conditions.** `arena_size` and `instr_per_tick` vary
   through pairwise, group, preset, and parallel evaluation; they are
   identity-bearing, persisted, comparability-gating, and deterministic.
4. **Defaults are inert.** Any evaluation omitting them is byte-identical
   to a pre-Phase-0 one, so new work cannot disturb historical results.
5. **No compatibility debt was created.** No Ruleset, Agent API, or schema
   version moved, so Phase 1 inherits a clean compatibility position.

Constraints Phase 1 must respect:

- **The arena saturates at current defaults** (§12). Vary arena size and
  action budget together, or an experiment risks measuring a territory
  ceiling rather than a strategy effect.
- **Prefer realized over nominal action counts** when normalizing —
  matches end early, and `cpu_total` is already recorded.
- **Hunter is not an offense archetype** (§10.3). The corpus contains
  exactly two genuine offense agents.
- **`wanderer` assumes a power-of-two arena** (§12). Keep arena sizes
  powers of two, or account for it explicitly.
- **Arena size below `2 × entrants × (CORE_SIZE + 1)` is rejected**, and
  standard placements are non-overlapping only above that bound.
- **`Observation` does not expose arena size.** An agent cannot currently
  adapt its stride to a varied arena. Whether that is a confound or the
  point is a Phase 1 design decision — but it is an Agent API question, and
  Phase 0 deliberately did not decide it (governing decision 3).
- **The §17 rubric is used verbatim.** §10's corrections are recorded
  observations about Beta2's report, not amendments to the rubric.

Phase 1 is not designed here.
