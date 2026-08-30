# Bytefray v2.0.0-beta2 Phase 3 — Multi-Entrant Analysis & Strategic Metrics

Branch: `v2.0-beta2-development`. Base: Phase 2's final commit `a5cc78a`.
Status: implementation complete, not yet released.

Phase 2 answered: *can Bytefray reliably schedule, identify, resume, and
compare a genuine multi-entrant evaluation?* Yes — see
`docs/V2_0_BETA2_PHASE2_MULTI_ENTRANT_EVALUATION.md`. Phase 2 deliberately
stopped there: multi-entrant behavior/capture aggregate analysis was
explicitly deferred rather than computed with 1v1-shaped assumptions.

Phase 3 answers the follow-on question: *can Bytefray explain what
happened to every entrant in a multi-entrant evaluation, without reducing
a multi-agent battle back into misleading 1v1 assumptions?*

This phase does not change multi-entrant execution, the engine, the
scheduler, or the Ruleset. It does not change Phase 2's identity/schema
model. It adds one new analysis layer.

## 1. Existing analysis architecture and its pairwise assumptions

Audited in full before writing any new code:

| Module | Question it answers | Pairwise assumption found |
|---|---|---|
| `evaluation_analysis.py` (Phase 4) | Did the candidate do better (win rate, paired significance)? | `SubjectAggregate`/`ComparisonEntry` are subject-vs-opponent shaped; `compare_candidate_baseline` only ever runs when `baseline_id` is set, which group mode always rejects — harmless for group, but not a source of N-entrant answers either. |
| `evaluation_behavior.py` (Phase 5) | How did the candidate play (survival, writes, territory, kills)? | `CellRef`/`CellBehaviorSample` resolve the subject's physical slot via `physical_slots_for_orientation` — a 2-value candidate-first/opponent-first axis, meaningless for a group cell whose subject occupies whichever seat `subject_seat` says. |
| `evaluation_capture.py` (Beta2 Phase 1) | Was Ruleset v2's Vulnerable Core exercised, by whom? | Same orientation-based slot resolution; `CellCaptureSample` has exactly two capture facts (`subject_captured`, `opponent_captured`) and a two-value `killer: "subject" \| "opponent" \| None` — structurally cannot name a third entrant. |
| `agent_evaluation.aggregate_cells` | `SubjectAggregate.score_differential_avg`/`territory_differential_avg` | **A real, previously-undiscovered defect** (§2 below): computed unconditionally for every scope including group, silently treating `score_opponent`/`territory_opponent` (always `None` for a group cell) as `0.0` — producing a number that looked like a real differential but was actually just the raw score/territory relabeled. |
| `evaluation_history/cli.py` `_cmd_show` | Historical `evaluations show` presentation | Already correctly *guarded* against computing behavior/capture for a group artifact (Phase 2's own audit finding) — but had nothing to show in their place beyond "deferred". |

None of these were rewritten. Phase 1/Phase-5/pre-existing pairwise
behavior remains byte-for-byte what it was; the group guards Phase 2 added
stay exactly as they were.

## 2. A defect found and fixed: silently-fabricated group differentials

`SubjectAggregate.score_differential_avg`/`territory_differential_avg`
were typed `float` (never `None`) and computed as
`(score_subject or 0.0) - (score_opponent or 0.0)`. For a group cell,
`score_opponent`/`territory_opponent` are always `None` (Phase 2's own
design: "ill-defined for more than one opponent") — so this arithmetic
silently produced `score_subject - 0`, i.e. the entrant's raw score,
presented under a field name that means "how much better than the
opponent." This was already being *printed* by the live CLI's
`_print_aggregate` for every `--group` run (the loop iterating
`result.aggregates` has no group guard), so a real, if easy to miss, false
signal reached the terminal on every existing Phase 2 group run.

Fixed in `aggregate_cells` (`agent_evaluation.py`): the field type became
`float | None`; when the aggregate's cells are group cells the value is
now `None` (never computed), unconditionally, matching the prompt's own
"existing pairwise differential fields may remain `None` for group cells
— do not overload old names with new semantics" rule. A non-group scope's
arithmetic is completely unchanged (verified: `test_agent_evaluation.py`'s
existing differential assertion is untouched and still passes). CLI
formatting (`_print_aggregate`) now prints `n/a (group)` rather than
crashing on `:g`-formatting `None`.

## 3. Per-entrant analysis architecture

New sibling module: `battle_engine.evaluation_group_analysis`. Sibling of
`evaluation_analysis.py`/`evaluation_behavior.py`/`evaluation_capture.py`
— not a replacement or extension of any of them, and none of those three
were modified beyond the one defect fix in §2 (which lives in
`agent_evaluation.py`, not any of the three).

Same data-tier discipline as its siblings: Tier 2 only (`result.json`, one
read per cell, fanned out into records for every entrant that cell
contains — never one read per entrant per cell). No replay reconstruction.
Real I/O — computed only when a caller deliberately asks for it (the live
CLI's `--group` result printing, or `evaluations show`'s opt-in
`--no-behavior`-gated group-analysis computation), never from
discovery/listing code.

```text
GroupCellRef                    -- resolved (schedule_id, roster, seat
                                    assignment, layout, seed, result path)
  -> load_group_cell_records()  -- one result.json read -> N EntrantCellRecord
       EntrantCellRecord         -- one entrant's raw evidence, one cell
                                    (outcome, alive, score, score_rank,
                                    margin_to_winner, territory, kills,
                                    deaths, capture facts)
  -> analyze_group(roster, refs) -> GroupAnalysis
       entrant_summaries          -- one EntrantSummary per roster agent_id
       seat_sensitivity            -- per-agent, grouped by seat
       layout_sensitivity          -- per-agent, grouped by layout_id
       seed_summary                 -- per-agent, grouped by seed
       interaction_matrix          -- directed captor -> victim counts/rates
  -> candidate_focused_view(analysis, candidate_id) -- pure selection, Sec 6/22
```

Three explicit layers, kept structurally distinct end to end (Sec 8):
**raw evidence** (`EntrantCellRecord`, one per entrant per cell, always
retained on `GroupAnalysis.records`) → **aggregated entrant summary**
(`EntrantSummary`, "all"/one-seat/one-layout/one-seed scopes, all built by
the same `entrant_summary()` function so there is exactly one aggregation
implementation) → **cross-condition sensitivity** (`SeatSensitivity`/
`LayoutSensitivity`/`SeedSummary`, transparent per-bucket tables plus a
`*_range` measure, never an opaque composite).

**The central architectural decision (Sec 6/21):** `analyze_group` takes
no candidate id. Its signature is `(roster_agent_ids, refs) ->
GroupAnalysis`; nothing about which entrant a caller later calls "the
candidate" can leak into the computation, because that argument does not
exist. `candidate_focused_view(analysis, candidate_id)` is *pure
selection* over an already-computed, already-symmetric `GroupAnalysis` —
it reruns nothing. This is enforced, not just documented: a unit test
(`test_analyze_group_never_takes_a_candidate_id`) inspects the function
signature directly, and both unit and integration tests confirm that
`candidate_focused_view(analysis, "a").candidate.to_json() ==
analysis.summary_for("a").to_json()` regardless of which entrant is
selected.

## 4. Outcome/ranking model

The engine's own winner semantics (`results.resolve_winner`,
survivor-only eligible since alpha.4.1) remain authoritative and
untouched. Three per-entrant `EntrantOutcome` states are derived from the
persisted `winner`/`alive` fields, never a flat win/loss:

- **`WINNER`** — this seat's agent_id is literally `result.winner`.
- **`SURVIVING_NON_WINNER`** — alive at match end, not the winner. This
  includes every entrant in a tied/no-unique-winner cell (`winner ==
  "tie"`, `results.WINNER_TIE_SENTINEL`) — no fourth "tie" enum value is
  needed, because "no entrant here is `WINNER`" already expresses it
  exactly.
- **`ELIMINATED`** — not alive at match end.

`agent_evaluation.EvaluationCell.outcome` (the existing candidate-oriented
`win`/`loss`/`tie` field, unchanged) still collapses
`SURVIVING_NON_WINNER` and `ELIMINATED` into `loss` — it remains valid for
resume/comparison/history compatibility (Phase 2's job), but is no longer
the only lens: a match with `A wins, B survives on a lower score, C is
eliminated` now visibly distinguishes B from C
(`test_winner_maps_to_correct_entrant_survivor_and_eliminated_distinguished`,
plus a real-engine version of the same assertion in the integration
suite).

## 5. Behavior/score/territory metrics

Per entrant, over any scope (all cells / one seat / one layout / one
seed), `EntrantSummary` reports:

- **Outcome rates**: `winner`, `survival` (winner + surviving-non-winner),
  `elimination` — each a `RateStat` (successes/trials/rate + Wilson
  interval, reusing `evaluation_analysis.wilson_interval` unchanged).
- **Score**: `score` (mean/n/min/max, a `Stat`), `margin_to_winner`
  (winner's score minus this entrant's, `0` for the winner itself, well
  defined regardless of sign or whether the total is zero). `score_rank`
  is available on every raw record (1 = highest this cell, ties broken by
  seat label, disclosed). **Score share (entrant score / total score) was
  considered and explicitly not implemented** — Bytefray scores can be
  negative or (rarely) sum to zero, which would make a share fraction
  nonsensical exactly as the prompt warned; rank and margin-to-winner
  cover the same "how did this entrant do relative to the field" need
  without that failure mode.
- **Territory**: `territory_last_pct`/`territory_max_pct`/
  `territory_avg_pct`/`territory_retention` (last/max, same formula as
  `evaluation_behavior`'s existing 1v1 definition, reimplemented here
  since this module never imports `evaluation_behavior`'s subject-shaped
  internals). No "opponent territory" — territories never summed to 100%,
  since unowned cells and 3+ owners both exist; "territory share among
  owned cells" was considered and not implemented (no characterization
  evidence yet that it adds signal beyond the per-entrant percentages
  already shown side by side — left for Phase 4 if real experiments show
  otherwise).
- **Kills/deaths**: `kills_per_match`/`deaths_per_match` (mean, `Stat`),
  `kill_involvement` (fraction of matches with >= 1 kill, a `RateStat`).

## 6. Capture model

`captured`/`captor_of` are per-entrant, per-cell facts on
`EntrantCellRecord`, aggregated into `capture_caused`/`capture_suffered`
`RateStat`s per entrant.

**Attribution** (`_resolve_group_captors`): the direct N-entrant
generalization of `evaluation_capture.py`'s existing 2-entrant heuristic
("the opponent's recorded kill can only be of the subject, since there is
no third party"). At N >= 3 that uniqueness argument only holds when
exactly one entrant died in the whole match — the aggregate `kills` count
is a match-wide total, not a per-death log, so with two or more deaths in
one match, aggregate kill counts alone cannot say which death which
entrant caused. `_resolve_group_captors` requires `total_deaths == 1`
before attributing anything; otherwise every victim in that cell is left
unattributed (`captor_of=()`), counted honestly in
`InteractionMatrix.unattributed_captures` rather than guessed. This exact
generalization reduces to the 2-entrant module's own behavior at N=2 (a
lone victim always implies `total_deaths == 1` there) without replacing
or touching that module.

**Directed interaction matrix** (`InteractionMatrix`): `captor_agent_id ->
victim_agent_id: count, rate` for every attributed pair, denominator
`cells_analyzed` (every cell of one fixed roster necessarily includes
every entrant, so "rate" is simply captures-of-that-pair /
cells-analyzed — no separate "matches where both participated" count is
needed, unlike a variable-opponent pairwise evaluation).

**Capture timing — a second real defect found via this phase's own
characterization** (not hypothesized, observed): a cell's own `ticks`
field is the match's *final* tick count, which only equals a specific
capture's own tick when that capture is what ended the match
(`termination_reason` alive-count-driven: `last_agent_standing`/
`all_agents_dead`). At N >= 3, a capture very often does *not* end the
match — two or more entrants can remain alive afterward, so the match
keeps running under `tick_limit` until the tick budget is exhausted. The
first implementation reported `capture_tick = ticks_run` unconditionally
whenever `captured` was true; running Matrix B (§9 below) surfaced every
single attributed capture reporting `capture_tick == 400` — the exact
tick budget, for captures that (given `total_deaths == 1` was required for
attribution, and a 3-entrant match needs 2 deaths to reach
`last_agent_standing`) can *never* have been terminal events. That
`400` was therefore wrong, potentially by hundreds of ticks, for every
capture in a 3-entrant roster's characterization run.

Fixed: `capture_tick`/`capture_tick_caused` are now populated only when
`termination_reason in {"last_agent_standing", "all_agents_dead"}` — the
fact and attribution of the capture (`captured`, `captor_of`, every rate)
are unaffected; only the numeric tick is withheld when it cannot be
trusted. `InteractionPair.count` (always exact) and `InteractionPair.
capture_ticks` (only the subset of `count` whose tick is known,
`len(capture_ticks) <= count` in general) were separated accordingly. A
dedicated regression test
(`test_capture_tick_withheld_when_match_ends_by_tick_limit_not_the_capture`)
and re-verification against the real Matrix A/B/C artifacts (§9) confirm
`capture_ticks` is now empty for every tick-limit-terminated capture in
this phase's own 3-entrant corpora — the count/rate numbers are unchanged
(still exact), only the misleading tick values are gone. This is disclosed
explicitly as a Tier-2 boundary, not silently worked around: true per-event
capture timing at N >= 3 (when the capture is non-terminal) requires
replay reconstruction (Tier 3), deliberately not implemented here (§13).

## 7. Seat sensitivity

`seat_sensitivity(agent_id, records)` groups an entrant's own records by
`seat` (`"A"`/`"B"`/`"C"`...) and calls `entrant_summary` once per bucket
— the identical aggregation function used for the "all" scope, so there is
never a second, drifting per-seat computation. `winner_rate_range`/
`survival_rate_range` are `max - min` across seats that actually have
`n > 0`, `None` when fewer than two seats qualify — a transparent range,
never an opaque composite (per the prompt's explicit preference and this
module's Sec 11-mirroring "no manufactured weights" stance).

Real measured seat sensitivity (§9): 0pp for Matrix A (no sensitivity at
all — pure dominance), up to 43pp for Core Tracker in Matrix B, up to 33pp
for both non-defender entrants in Matrix C. Seat sensitivity is real and
large in this corpus, not a theoretical concern.

## 8. Permutation sensitivity vs. seat sensitivity

Kept structurally distinct throughout, per the prompt's explicit
terminology distinction. Every `EntrantCellRecord` carries both `seat`
(this entrant's own position) and the complete `seat_agent_ids` tuple
(the full roster ordering for that cell) — seat grouping never discards
the full-permutation coordinate, it is simply not the group key for
`seat_sensitivity`'s own output. `test_full_permutation_detail_preserved_
alongside_seat_grouping` proves two records sharing the same `agent_id`
and `seat` but different `seat_agent_ids` (i.e. the same seat, different
full permutations) both survive in `GroupAnalysis.records` untouched. A
future analysis (not built in this phase — no characterization evidence
yet motivated it) could group by the full `seat_agent_ids` tuple using the
exact same `_group_by(records, key)` helper, since it already accepts an
arbitrary key function (Sec 19's "explicit dimensions" requirement).

## 9. Layout sensitivity

Identical shape to seat sensitivity, grouped by `layout_id`
(`spread`/`spread-shifted`/`close`, Phase 2's existing three standard
layouts — this phase adds no new layout). Measured: near-zero for Matrix A
(0pp — dominance again), up to 17pp for Matrix B, up to 33pp for Matrix C
— materially different layout-sensitivity *profiles* per roster, discussed
in §11.

## 10. Seed treatment

Every record retains its `seed`; `seed_summary` groups by seed the same
way as seat/layout, plus a compact `best_seed`/`worst_seed` (ranked by
winner rate, tie-broken by seed number) and `winner_rate_range` summary —
deliberately not a full seed-by-seed table in the default CLI presentation
(Sec 18: "avoid producing huge seed tables by default"), while the full
per-seed breakdown remains available in both the structured JSON output
and `GroupAnalysis.records`.

## 11. Statistics

Wilson score intervals (`evaluation_analysis.wilson_interval`, unchanged)
for every binary per-cell fact: `winner`/`survival`/`elimination`/
`kill_involvement`/`capture_caused`/`capture_suffered`. Continuous metrics
(score, territory, capture tick) get mean/n/min/max only (`Stat`), no
interval — mirrors `evaluation_behavior.DimensionValue`'s identical
existing precedent that a rate or an average-of-ratios is not the same
statistical object a Wilson interval applies to. Every `RateStat`/`Stat`
discloses its own `trials`/`n`; a zero-trial scope reports `rate=None`,
never a fabricated `0.0` (verified by `test_zero_cells_produces_
insufficient_data_not_a_crash`).

## 12. Structured output and `evaluations show`

Every dataclass in the module has a `to_json()`; `GroupAnalysis.to_json()`
composes them into one self-contained structure (`roster_agent_ids`,
`cells_analyzed`/`available_cells`, `entrant_summaries`,
`seat_sensitivity`, `layout_sensitivity`, `seed_summary`,
`interaction_matrix`) with no large redundant copy of `result.json`
embedded — every summary traces back to `EntrantCellRecord.schedule_id`/
`seat`/`layout_id`/`seed`, and those records are themselves serializable
via `to_json()` if a caller wants the full audit trail.

`evaluations show --json` now includes a `"group_analysis"` key (`null`
for a non-group/pairwise artifact) alongside the existing `"behavior"`/
`"capture"` keys, using the identical opt-in-real-I/O `--no-behavior` gate.
The plain-text `evaluations show` for a v6 artifact now prints a real
`group analysis:` section — cells analyzed, every roster entrant's own
summary (not just the candidate's, since this is the "drill deeper"
workflow — mirrors `_print_analysis`/`_print_behavior`'s existing
"show everything here" precedent), seat/layout sensitivity lines (only
when a range is actually computable), and the directed capture matrix —
replacing what used to be nothing but the roster/layout/seat-assignment
counts.

`evaluation_history/group_adapter.py` (new, mirrors `behavior_adapter.py`
exactly) supplies the containment-checked, historical-artifact
`GroupCellRef`s — a pairwise (v1/v4/v5) cell is silently skipped (empty
`seat_agent_ids`), so `group_cell_refs` can be called against any
`EvaluationSummary` without the caller pre-filtering by
`summary.group.value` first (`test_pairwise_v5_artifact_group_adapter_
returns_no_refs`).

## 13. Candidate-focused compatibility view

`agent_evaluation._print_group_analysis` (live CLI) and
`evaluation_history/cli.py`'s `_print_group_analysis_history` (historical
`evaluations show`) are both pure presentation functions over an
already-computed `GroupAnalysis`/`CandidateGroupView` — see §3's signature
discussion. The live CLI leads with the candidate (mirroring existing 1v1
CLI conventions: candidate overall, then by-seat, then by-layout, then
"other entrants"); the historical `evaluations show` — already the
"drill deeper" surface — shows every entrant's summary up front with the
candidate simply marked `(candidate)`. Both read from the identical
`GroupAnalysis`; nothing is recomputed for either presentation.

## 14. Designer

Not touched this phase. `docs/V2_0_BETA2_PLAN.md`'s Phase 3 sketch listed
"show group evaluation summaries" / "show entrant list" / "show seat/
layout sensitivity summary" as *possible* low-risk Designer improvements,
gated on the CLI/history/analysis model actually being complete and
tested first. That gate is now satisfied, but no Designer code was
inspected or changed in this phase — the prompt was explicit that GUI work
must not drive analysis architecture, and estimating Designer integration
risk properly needs its own investigation of the existing Designer's
evaluation-consumption code, which this phase did not do. Recommendation:
a small, scoped Designer follow-up (distinct from any Replay Viewer/HUD
work, which stays explicitly out of scope per this milestone's own
guardrails) is reasonable to schedule after Phase 4, once real Phase 4
strategic experiments have exercised this analysis model further.

## 15. Characterization: Matrix A

```text
candidate: claimer
opponents: core_defender, reactive_core_defender
ruleset: bytefray-rules-2   ticks: 400
seeds: 1,2,3,4,5  layouts: 3  permutations: 6  cells: 90/90
```

| entrant | winner | survival | eliminated | score mean | captured | caused |
|---|---|---|---|---|---|---|
| claimer | 90/90 (100%) | 90/90 (100%) | 0/90 | 6790.4 | 0/90 | 0/90 |
| core_defender | 0/90 | 90/90 (100%) | 0/90 | 5105.6 | 0/90 | 0/90 |
| reactive_core_defender | 0/90 | 90/90 (100%) | 0/90 | 4866.4 | 0/90 | 0/90 |

Seat sensitivity: **0pp** for all three entrants. Layout sensitivity:
**0pp**. Seed sensitivity: **0pp**. No captures at all (both defenders are
purely reactive/static; Claimer's territory-expansion strategy dominates
on score without ever needing to fight). This is a genuinely *stable*
result — not a sparse-sample artifact: every one of 90 cells, across every
seat/layout/seed combination, produced the identical outcome. Claimer's
dominance against this pairing of purely defensive opponents is total and
condition-independent.

## 16. Characterization: Matrix B (validates Phase 2's finding)

```text
candidate: core_tracker
opponents: hunter, core_defender
ruleset: bytefray-rules-2   ticks: 400
seeds: 1,2,3,4,5  layouts: 3  permutations: 6  cells: 90/90
```

| entrant | winner | survival | eliminated | score mean | captured | caused |
|---|---|---|---|---|---|---|
| core_defender | 34/90 (38%) | 71/90 (79%) | 19/90 (21%) | 4664.0 | 19/90 | 0/90 |
| core_tracker | 15/90 (17%) | 84/90 (93%) | 6/90 (7%) | 4188.0 | 6/90 | 38/90 (42%) |
| hunter | 41/90 (46%) | 41/90 (46%) | 49/90 (54%) | 4746.9 | 49/90 | 6/90 |

Seat sensitivity (winner rate range): core_defender 13pp, **Core Tracker
43pp** (0% in seat A, 43% in seat C), hunter 10pp. Layout sensitivity:
core_defender 3pp, Core Tracker 17pp, hunter 13pp. Seed sensitivity: Core
Tracker's own winner rate ranges from 6% (seed 3) to 28% (seed 5) — 22pp.

Interaction matrix: `core_tracker -> hunter: 34 (38%)`,
`core_tracker -> core_defender: 4 (4%)`, `hunter -> core_tracker: 6 (7%)`,
30 captures unattributed (multi-death cells, §6). Core Tracker is the
dominant *capturer* in this roster (42% of cells) despite a comparatively
modest win rate — a direct illustration of why capture and winning must
stay structurally separate (§6): being effective at eliminating a
particular rival does not by itself translate into winning the match,
since the third entrant (core_defender here) can still out-survive/out-
score both combatants.

**Answering Sec 30's question directly**: this phase's own Phase-2-vintage
smoke run of the identical roster/candidate at 3 seeds (54 cells,
identical to Phase 2's characterization shape) measured Core Tracker at
**7/54 (13%)** — already substantially different from Phase 2's originally
reported 2/54 (4%). Expanding the *same* seeds plus two more (5 seeds, 90
cells) moved the observed rate to 15/90 (17%). Since seeds 1-3 are common
to both runs, seeds 4-5 alone contributed a materially different rate
(8/36, 22%) than seeds 1-3 did (7/54, 13%) — a real, internally-consistent
seed effect, not run-to-run noise from a different code path (both runs
used this session's identical build). Combined with the measured 43pp
seat-sensitivity range, the honest conclusion is: **Core Tracker's low win
rate is a real, seat-and-seed-sensitive phenomenon, not fixed — and Phase
2's original 3-seed, 54-cell sample was too small to characterize it
reliably.** This is exactly the kind of instability the new analysis model
exists to surface rather than hide behind one pooled rate.

## 17. Characterization: Matrix C

```text
candidate: reactive_core_defender
opponents: hunter, core_seeker
ruleset: bytefray-rules-2   ticks: 400
seeds: 1,2,3,4,5  layouts: 3  permutations: 6  cells: 90/90
```

Chosen because Matrix A already showed `reactive_core_defender` losing
every cell to Claimer without ever fighting; Matrix C asks whether that
same purely-reactive strategy fares any better when the *other* two
entrants are aggressive/scanning strategies (`hunter`, `core_seeker`) that
fight each other as much as they threaten the defender, rather than one
dominant expansionist.

| entrant | winner | survival | eliminated | captured | caused |
|---|---|---|---|---|---|
| core_seeker | 45/90 (50%) | 85/90 (94%) | 5/90 (6%) | 5/90 | 35/90 (39%) |
| hunter | 45/90 (50%) | 45/90 (50%) | 45/90 (50%) | 45/90 (50%) | 5/90 |
| reactive_core_defender | 0/90 | 80/90 (89%) | 10/90 (11%) | 10/90 | 0/90 |

Seat sensitivity: core_seeker and hunter both **33pp**;
reactive_core_defender **0pp** (it never wins regardless of seat). Layout
sensitivity: core_seeker and hunter both **33pp**; reactive_core_defender
**0pp**. Seed sensitivity: **0pp for every entrant** — the outcome split
is stable across all five seeds even though it is highly seat/layout
sensitive. This is a materially different sensitivity *fingerprint* than
Matrix B (which was seed-and-seat sensitive, less layout-sensitive):
different rosters do not share one universal sensitivity shape (§8's
interaction-effects point, made concrete).

`reactive_core_defender` never wins and never causes a capture (0/90) —
structurally consistent with a purely reactive strategy: it can avoid/
survive attacks (89% survival) but never goes on offense, so it can never
accumulate the score lead needed to win outright even when it's the sole
survivor of a two-way core_seeker/hunter fight. `core_seeker` captures
`hunter` roughly 7x as often as the reverse (35 vs. 5) — a clear predator/
prey asymmetry between those two specific strategies, visible only because
the interaction matrix keeps captor/victim directed rather than reporting
a single symmetric "capture count."

## 18. Interaction findings

Across all three matrices: captures are meaningfully directed and
asymmetric (Core Tracker → Hunter dominant in B; Core Seeker → Hunter
dominant in C), never symmetric coincidence. `reactive_core_defender`
caused zero captures in either matrix it appeared in — consistent, not
matrix-specific. These are descriptive observations from three specific
5-agent, 3-entrant rosters at one tick budget; they are not claimed to
generalize to other rosters, tick budgets, or the wider strategic
questions (kingmaking, roster-composition effects at scale) Phase 4 is
scoped to investigate systematically.

## 19. Permutation scaling assessment

Schedule cardinality (`seeds x len(standard_layouts(N))=3 x N!`, at 5
seeds, mechanically computed via `standard_layouts`/
`enumerate_seat_assignments` themselves rather than assumed):

| N | permutations (N!) | cells (5 seeds x 3 layouts x N!) | measured/estimated runtime @ 400 ticks |
|---|---|---|---|
| 3 | 6 | 90 | ~15s (measured: Matrix A/B/C, 14-16s each) |
| 4 | 24 | 360 | ~1 minute (estimated, linear extrapolation from measured ~6 cells/sec) |
| 5 | 120 | 1,800 | ~5 minutes (estimated) |
| 6 | 720 | 10,800 | ~30 minutes (estimated) |

The N=4/5/6 figures are extrapolated from N=3's measured per-cell rate and
are very likely **optimistic** (a lower bound): more entrants per match
plausibly costs more per tick (each entrant still acts once per tick, so
per-tick cost should grow with N even before considering any O(N^2)
interaction effects), which this phase did not measure directly (no N=4/5
roster was run — three real reference-quality N=4/5 agents were not
selected/validated as part of this phase's scope, and doing so risked
scope creep into Phase 4's strategic-experiment territory).

**Recommendation**: exhaustive permutation scheduling remains appropriate
through N=3 (proven, cheap, already shipped in Phase 2) and is very likely
still practical at N=4 (a few minutes per full evaluation). N=5 exhaustive
(1,800+ cells, several minutes to run and already noticeably slower to
review 120 raw permutation rows for) is the point at which a rotation/
sampling policy becomes worth considering rather than default. No such
policy is implemented in this phase — the prompt was explicit that a
"very small abstraction... only if justified" is the right bar, and no
concrete N=4/5 roster requirement has arisen yet to justify one.
`_group_by`'s explicit-key-function design (§8) means adding a
"balanced Latin-style" or "deterministic sampled" seat-assignment policy
later would not require touching this module's aggregation code — only
`enumerate_seat_assignments` itself, in `agent_evaluation.py`, if and when
Phase 4 needs it.

## 20. Performance

Match execution (Matrix A/B/C, 90 cells each, 400 ticks): 13.9-16.2s wall
(~5.6-6.5 cells/sec) — unchanged from Phase 2 (this phase touched no
execution code).

Analysis-only (`analyze_group` against an already-written artifact's
`result.json` files, measured separately via `time.perf_counter` around
the call, excluding artifact discovery/adaptation): **23.2-23.6ms for 90
cells** (~3,800-3,900 cells/sec) across all three matrices. Analysis is
roughly **650x cheaper** than match execution — confirms the prompt's
expectation that "Phase 3 analysis should be cheap relative to executing
matches" without needing any optimization work. No replay files were read
for any of this phase's metrics (Tier 2 only, per §6's disclosed
boundary).

## 21. Compatibility

- **v1**: `test_non_group_v1_evaluation_unaffected_by_group_analysis_
  module` — a v1 evaluation's cells report `is_group=False`,
  `roster_agent_ids=()`; `evaluation_group_analysis` is never imported
  from that path.
- **v4 artifacts**: `group_cell_refs` returns `()` for any pairwise
  artifact (empty `seat_agent_ids` on every cell) — verified directly
  (`test_pairwise_v5_artifact_group_adapter_returns_no_refs`, same code
  path serves v4/v5 identically since both lack group cells).
- **Phase-1 v5 artifacts**: unaffected — `evaluations show` still shows
  placements/orientation/behavior/capture exactly as Phase 1/2 left them;
  `group_analysis` is `None` for these.
- **Pairwise behavior/capture analysis**: `evaluation_behavior.py`/
  `evaluation_capture.py` were not modified. Full targeted regression
  (`test_evaluation_behavior.py`, `test_evaluation_capture.py`,
  `test_agent_evaluation_behavior.py`, `test_evaluation_history_
  behavior.py`) passes unchanged.
- **Phase-2 v6 identity/resume/comparison**: not touched by this phase
  (this phase adds analysis over already-resolved cells; it changes
  nothing about how cells are scheduled, identified, resumed, or
  compared). Full targeted regression
  (`test_agent_evaluation_multi_entrant.py`,
  `test_agent_evaluation_v2_methodology.py`,
  `test_evaluation_history_comparison.py`) passes unchanged.

## 22. Tests and quality

New tests this phase: 25 unit (`test_evaluation_group_analysis.py`,
hand-built `result.json` fixtures — per-entrant extraction, outcome
classification, capture attribution and its ambiguity/timing boundaries,
seat/layout/seed sensitivity, symmetry, candidate-focused view, sparse
data) + 7 integration (`test_agent_evaluation_group_analysis_
integration.py`, real `EvaluationService --group` runs through the actual
engine, plus real `evaluations show` reads of the resulting artifact).

Full qualification:

```text
pytest:  1860 passed, 6 skipped, 2 deselected  (0 failed, 0 errors)
ruff check .:              All checks passed
mypy engine/src/battle_engine:  Success: no issues found in 73 source files
mypy client/src/battle_client:  (client untouched this phase — not re-run;
                                  no client code was modified)
git diff --check:          clean
```

Phase 2's baseline was 1834 collected / 1828 passed / 6 skipped / 0
failed / 0 errors. This run's pytest summary line reports 1860 passed + 6
skipped + 2 deselected = 1868 collected — 34 more than Phase 2's baseline
(32 new tests from this phase's two new test files, exactly accounting for
the growth; the "2 deselected" reflects `pytest.ini`'s pre-existing
`-m "not gui"` marker filter and is unrelated to this phase's changes —
Phase 2's own report did not separately call out a deselected count, so
this is a reporting-detail difference, not a regression). 0 failed, 0
errors either way.

## 23. Files changed

**Production**:
`engine/src/battle_engine/evaluation_group_analysis.py` (new),
`engine/src/battle_engine/evaluation_history/group_adapter.py` (new),
`engine/src/battle_engine/agent_evaluation.py` (modified:
`SubjectAggregate` differential-field fix, `_print_group_analysis` and its
formatting helpers, `_print_aggregate` `None`-safe formatting),
`engine/src/battle_engine/evaluation_history/cli.py` (modified:
`group_analysis` computation/JSON key, `_print_group_analysis_history`
and its formatting helpers).

**Tests**: `engine/tests/test_evaluation_group_analysis.py` (new, 25
tests), `engine/tests/test_agent_evaluation_group_analysis_integration.py`
(new, 7 tests).

**Docs**: this file (new); `docs/V2_0_BETA2_PLAN.md`, `docs/ROADMAP.md`
updated (§26).

## 24. Remaining limitations

- **Per-event capture timing at N >= 3 when the capture is non-terminal**
  requires replay reconstruction (Tier 3) — genuinely deferred, not
  worked around; the fact/attribution of the capture is still reported,
  only its tick is withheld when untrustworthy (§6).
- **Minimum core integrity over time** remains deferred exactly as Phase
  1 left it (same replay-reconstruction cost boundary) — not revisited in
  this phase.
- **N! exhaustive scheduling** grows rapidly past N~4-5 (§19) — a
  disclosed, unsolved scaling boundary with a recommended next policy
  direction, not a blocker for the N=3 rosters this phase's own
  characterization used.
- **Designer** has no group-evaluation-aware presentation yet — explicitly
  deferred (§14), not attempted, pending its own scoped investigation.
- **Self-play (duplicate-agent roster) analysis semantics**: `analyze_
  group` aggregates by logical `agent_id`, so two seats occupied by the
  same agent in one cell contribute to one combined summary rather than
  being tracked as separate "occurrences" — mirrors `EvaluationCell.
  subject_seat`'s own Phase 2 precedent (first-occurrence resolution) and
  was not a focus of this phase's characterization (all three matrices
  use distinct 3-entrant rosters, matching the prompt's own characterization
  scope).
- **Territory-share-among-owned-cells and full-permutation-table
  grouping** were designed for (the underlying data supports both, via
  the existing `_group_by`/`Stat` machinery) but not implemented, absent
  concrete evidence from real experiments that they add signal beyond
  what is already reported (§5/§8).

## 25. Phase 4 handoff

Recommended next phase:

> **Beta2 Phase 4 — Strategic Characterization**

Phase 3 built and validated the analysis instrument; Phase 4 should point
it at real strategic questions with deliberately controlled experiments,
using the sensitivity model this phase delivered rather than raw win
rates alone:

- **Roster-composition effects / kingmaking**: does a weak third entrant
  systematically decide the outcome between two strong ones (a direct
  extension of Matrix B/C's captor/victim asymmetries onto more rosters)?
- **Seat/order bias at scale**: Matrix B/C both showed large (17-43pp)
  seat sensitivity for some entrants and zero for others — is that
  strategy-dependent (aggressive vs. reactive) or roster-dependent? Needs
  more than three rosters to say.
- **Layout bias**: same question for arena layout, which showed a
  different profile than seat sensitivity in every matrix here (§8/§17).
- **Seed sensitivity re-examination**: Matrix B showed real 22pp seed
  sensitivity, Matrix A/C showed none — worth a dedicated experiment
  varying only the roster while holding seat/layout methodology fixed.
- **Simple-strategy dominance**: Matrix A's 100%-every-cell Claimer result
  is either genuine dominance against passive opponents or an artifact of
  a roster with no real contest — worth testing against more aggressive
  third entrants.
- **N! scaling policy**: if Phase 4 needs N=4/5 rosters, revisit §19's
  estimate with real measurements before committing to exhaustive
  scheduling at that size.

Phase 4 should not introduce alliances, teams, communication, fog of war,
MARL, a new Ruleset, or new Agent API instructions — none of that is
required to investigate any of the above with the existing engine and this
phase's new analysis layer.

## 26. Decision

```text
Beta2 Phase 3: COMPLETE
```
