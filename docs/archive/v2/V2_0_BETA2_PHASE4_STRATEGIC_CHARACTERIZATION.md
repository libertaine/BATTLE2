# Bytefray v2.0.0-beta2 Phase 4 — Strategic Characterization

Branch: `v2.0-beta2-development`. Base: Phase 3's final commit `2662a5f`.
Status: implementation complete, not yet released.

Phases 1-3 proved Bytefray can reliably schedule, execute, identify,
resume, compare, and explain multi-entrant evaluations. Phase 4 uses that
instrument for its intended purpose: pointing it at the actual strategic
question behind Ruleset v2 — does the current game produce strategically
rich, context-sensitive, multi-agent behavior, or does one simple strategy
threaten to make the rest of the design moot? This is a research and
characterization phase. No rule, scheduler, scoring, or agent change was
made; every finding below was obtained by running the existing, unmodified
system through its existing production evaluation harness.

## 1. Repository state

- Starting branch: `v2.0-beta2-development`, starting SHA `2662a5f` — matched exactly.
- Final SHA: see §25.
- Working tree: clean at completion (see §22).
- Protected/unrelated references confirmed unchanged: `main`=`2076576`,
  `origin/main`=`2076576`, `v2.0-beta1-development`=`79f61f4`,
  `v2.0-development`=`ad67a0f`, `origin/v2.0-development`=`151866c`.
- Nothing pushed, merged, tagged, or published.

## 2. Research design

**Primary corpus** (pre-registered in `runs/research_v2_beta2_phase4/
matrix_config.json` before any of it was run — see that file for every
roster's stated hypothesis in full):

- **11 group (3-entrant) rosters**, 90 cells each (`bytefray-rules-2`,
  seeds `1-5`, all 3 standard layouts, all 6 seat permutations, 400
  ticks) — 3 reused byte-for-byte from Phase 3 (Matrices A/B/C), 8 newly
  run. **990 group cells total.**
- **3 pairwise (1v1) controls**, 15 cells each (`bytefray-rules-2`, seeds
  `1-5`, all 3 standard placements, 400 ticks) — **45 pairwise cells**,
  chosen specifically to re-test three of alpha.11's own headline 1v1
  numbers under Beta2's methodology.
- **3 additional pairwise controls at 200 ticks** (same pairs), added
  after discovering the 400-tick default deviates from alpha.11's own
  200-tick budget (§16) — a small, explicitly-justified follow-up, not a
  silent expansion of the pre-registered set.

Rosters, in the order run (▲ = reused from Phase 3):

| id | roster | hypothesis (abbreviated) |
|---|---|---|
| ▲ `claimer_coredefender_reactive` | claimer, core_defender, reactive_core_defender | negative control: no offense present |
| `claimer_hunter_coredefender` | claimer, hunter, core_defender | second expansion rival vs. defender-only |
| `claimer_hunter_reactive` | claimer, hunter, reactive_core_defender | same, reactive defender variant |
| `claimer_coretracker_coredefender` | claimer, core_tracker, core_defender | reproduce alpha.11 A17 trio |
| `claimer_coretracker_reactive` | claimer, core_tracker, reactive_core_defender | reproduce alpha.11 A17 trio |
| `claimer_coretracker_hunter` | claimer, core_tracker, hunter | reproduce alpha.11 A17 trio |
| `claimer_coreseeker_hunter` | claimer, core_seeker, hunter | two independent searchers vs. Claimer |
| ▲ `hunter_coretracker_coredefender` | hunter, core_tracker, core_defender | non-Claimer-focal corpus diversity |
| ▲ `reactive_hunter_coreseeker` | reactive_core_defender, hunter, core_seeker | defender under dual offensive pressure |
| `hunter_coretracker_coreseeker` | hunter, core_tracker, core_seeker | offense-heavy, zero defenders |
| `coredefender_reactive_coreseeker` | core_defender, reactive_core_defender, core_seeker | defense-heavy, minimal expansion |

Every group-analysis number quoted below comes from
`battle_engine.evaluation_group_analysis.analyze_group` run directly
against these artifacts (`runs/research_v2_beta2_phase4/analyze_corpus.py`)
— no numbers in this document were hand-computed or estimated.

## 3. Agent/archetype inventory

| Agent | Primary behavior (from source/docs) | Archetype |
|---|---|---|
| Claimer | Sweeps the whole arena with a fixed stride, claims every cell visited; no reading, no reacting | blind expansion |
| Hunter | Scans for contested ground (cells neither blank nor its own), seizes with a short write burst | opportunistic offense |
| Core Defender | Spends part of its budget unconditionally refreshing its own core, rest expanding | unconditional (blind) defense + expansion |
| Reactive Core Defender | Signs its core once, patrols with cheap `READ`, repairs only when a mismatch is actually detected | reactive/efficient defense + expansion |
| Core Tracker | RNG-anchored coarse scan for foreign-looking bytes, coarse-to-fine probe requiring a second confirming read before a `WRITE` assault; placement-agnostic by design | dedicated search-and-destroy offense |
| Core Seeker | `READ`-scans for foreign ownership signs, commits a `WRITE` burst once the same signal is found twice in a row (locked-on region) | dedicated search-and-destroy offense (Core Tracker's simpler predecessor) |

Selected because these six span every archetype alpha.10/alpha.11 already
identified as strategically distinct (blind expansion, opportunistic
offense, unconditional defense, reactive defense, two independent
search-based offense implementations) — no new agent was created.

## 4. Simple-strategy dominance (Claimer)

**7 of 11 rosters contain Claimer, 630 of 990 group cells.** Overall
Claimer results, by roster (win rate / survival / captured / caused):

| roster | claimer win rate | 2nd place | 3rd place |
|---|---:|---|---|
| claimer_coredefender_reactive | **100.0%** | core_defender 0.0% | reactive 0.0% |
| claimer_hunter_coredefender | 50.0% | hunter 50.0% | core_defender 0.0% |
| claimer_hunter_reactive | 44.4% | hunter 55.6% | reactive 0.0% |
| claimer_coretracker_coredefender | 44.4% | core_defender 45.6% | core_tracker 10.0% |
| claimer_coretracker_reactive | 48.9% | reactive 42.2% | core_tracker 8.9% |
| claimer_coretracker_hunter | **36.7%** | hunter 33.3% | core_tracker 30.0% |
| claimer_coreseeker_hunter | 44.4% | hunter 33.3% | core_seeker 22.2% |

**Answer: Claimer is matchup-dominant, not broadly/universally dominant.**
Its 100% Matrix-A result is a negative control, not a Ruleset-level fact:
neither `core_defender` nor `reactive_core_defender` attacks *anything*
(`caused=0%` in every roster where either appears without an offense
agent present), so a roster of two non-attacking defenders can never
generate a capture, and territory-only expansion wins unopposed by
construction. **This is not a new finding — it independently reproduces
alpha.11 §12's own documented result** ("`claimer`/`hunter` vs either
defender: expansion 100%, capture 0%"), now at a larger sample (90 vs.
16 cells) and Beta2's own methodology.

The moment a real search-based offense agent (`core_tracker`/
`core_seeker`) is present, Claimer's margin collapses: 44.4% vs. 45.6%
(core_defender, essentially tied) in one roster, and only a narrow raw
lead in `claimer_coretracker_hunter` (claimer 36.7%, hunter 33.3%, core
tracker 30.0%). The three estimates are statistically indistinguishable
at this sample size: their intervals overlap, so the evidence supports a
three-way contest rather than a meaningful first/second/third ordering.
Claimer never falls to *weak* (it remains close to the raw leader in every
tested roster), but that is a materially different, weaker claim than
"90/90" suggested in isolation — this directly confirms
alpha.11's own finding (§11 there): "pure expansion is no longer
near-universal — `claimer` 1v1 98.4% → 60.9%."

**Counterexamples found**: `core_defender` (45.6% in
`claimer_coretracker_coredefender`) and `reactive_core_defender` (42.2%
in `claimer_coretracker_reactive`) both *approach or match* Claimer's own
win rate once `core_tracker` is present — but, per §9 below, this is a
kingmaking-like effect (a passive defender inheriting wins from
Core Tracker's attacks on Claimer), not the defender actively
out-competing Claimer through its own play.

## 5. Counter-strategy evidence

`core_tracker`/`core_seeker` are the only strategies in this corpus that
materially constrain Claimer, and only by causing it to be captured (§4;
`caused` rate 39-61% in every roster either appears in). No agent
out-scores or out-territories Claimer through ordinary expansion play —
the only lever that works is core capture. This is a narrow but real
counter-strategy: the search-and-destroy archetype is the sole
demonstrated answer to blind expansion.

## 6. Third-party / kingmaking effects

Matched-pair comparisons (same focal pair, varying third entrant, all
other methodology held fixed):

**Focal pair (Claimer, Core Tracker):**

| third entrant | claimer | core_tracker | third |
|---|---:|---:|---:|
| core_defender | 44.4% | 10.0% | **45.6%** |
| reactive_core_defender | 48.9% | 8.9% | **42.2%** |
| hunter | 36.7% | 30.0% | 33.3% (hunter, an active competitor) |

**Focal pair (Hunter, Core Tracker):**

| third entrant | hunter | core_tracker | third |
|---|---:|---:|---:|
| core_defender (Matrix B) | 45.6% | 16.7% | **37.8%** |
| core_seeker | 25.6% | 33.3% | 41.1% (core_seeker, an active competitor) |

**Answer to Section 10's operational definition**: yes, a real
kingmaking-like effect is present and reproducible. When the third
entrant is a **passive** defender (never attacks: `caused` 0-1%), it
wins 33-46% of matches purely by outlasting whichever of Claimer/Hunter
`core_tracker` happens to eliminate — `core_tracker` does the work
(highest `caused` rate, 42-50%) but rarely wins itself (8.9-16.7%). When
the third entrant is instead **active** (Hunter or Core Seeker, itself
capable of attacking), no such windfall occurs — outcomes redistribute
roughly evenly among all three genuine competitors instead.

**Mechanism, directly evidenced, not merely inferred**: the passive-third
benefit correlates tightly with whether captures actually occur. In
`claimer_hunter_coredefender`/`claimer_hunter_reactive` (no search agent
present, `caused` rates 0-5.6%), the passive third wins **0%** — it is
never captured, but nothing ever creates the opportunity for it to
inherit a win either. The kingmaking effect requires an actual
elimination event to open the door; without one, a passive third stays
strategically irrelevant rather than benefiting.

## 7. Directed capture interactions

Aggregated across the corpus, `core_tracker`/`core_seeker` are the
dominant captors everywhere they appear (`caused` 39-61%); every other
agent's `caused` rate is 0-11%, with one notable exception: Claimer
causes Hunter captures at a small but nonzero rate (5.6% in both rosters
where they coexist without a search agent). This is not deliberate
hunting — Claimer never reads the arena — and is consistent with
alpha.4 §16's own documented "incidental interference" mechanism: a
blind, wide sweep can overwrite cells a nearby core happens to occupy
purely as a side effect of expansion, not intent.

Full directed matrix for the two rosters with the richest interaction
(`claimer_coretracker_hunter`, `hunter_coretracker_coreseeker`):

```text
claimer_coretracker_hunter:
  claimer -> hunter:        1  (1.1%)
  core_tracker -> claimer: 25 (27.8%)
  core_tracker -> hunter:  17 (18.9%)
  hunter -> core_tracker:   2  (2.2%)
  unattributed: 68

hunter_coretracker_coreseeker:
  core_seeker -> core_tracker: 13 (14.4%)
  core_seeker -> hunter:        4  (4.4%)
  core_tracker -> core_seeker: 10 (11.1%)
  core_tracker -> hunter:       5  (5.6%)
  unattributed: 116
```

The high `unattributed` counts (§13 of Phase 3's own docstring: capture
attribution requires exactly one death in the whole match) are expected
and not concerning — offense-heavy rosters with multiple active
attackers produce multi-death matches routinely, which is exactly the
case Tier-2 (`result.json`-only) attribution honestly declines to guess
at rather than misattributing.

## 8. Hunter vulnerability

Phase 3 observed Hunter being captured by `core_tracker`/`core_seeker`.
This corpus generalizes it, with an important refinement:

| roster | hunter captured | claimer captured (if present) |
|---|---:|---:|
| claimer_hunter_coredefender (no search agent) | 5.6% | 0.0% |
| claimer_hunter_reactive (no search agent) | 5.6% | 0.0% |
| claimer_coretracker_hunter | **57.8%** | 57.8% |
| claimer_coreseeker_hunter | **61.1%** | 55.6% |
| hunter_coretracker_coredefender (Matrix B) | 54.4% | n/a |
| reactive_hunter_coreseeker (Matrix C) | 50.0% | n/a |
| hunter_coretracker_coreseeker | **74.4%** | n/a |

**Refined finding: this is not a Hunter-specific vulnerability.** Claimer
is captured at essentially the same rate as Hunter (55.6-57.8% vs.
57.8-61.1%) in every roster where both coexist with a search agent. The
real pattern is: **any agent that neither searches for nor defends
against core assault (Claimer, Hunter alike) is captured 50-74% of the
time once a dedicated search agent is present, vs. 0-5.6% when none is**
— a property of *not defending*, not of Hunter's own strategy
specifically.

## 9. Defensive strategy value

`reactive_core_defender`'s survival rate is 80-100% in every roster it
appears in — always the highest or tied-highest survival in that roster
— confirming defense provides real denial value (Phase 3's own §9
question). Its win rate, however, swings from 0% to 42.2% depending
entirely on whether a search agent is present to create a capture
opportunity for it to inherit (§6) — defense converts to *wins* only
indirectly, through the kingmaking mechanism, never through its own
offense (`caused` is 0% in 3 of its 4 roster appearances, 5.6% in the
fourth — see §14 for the one exception). This matches alpha.4 §15's own
finding, now generalized across more rosters: survival alone does not
translate into competitiveness without an external trigger.

## 10. Seat / scheduler-order sensitivity

Distribution of the largest per-entrant seat-sensitivity range within
each roster, sorted by contest closeness (win-rate spread across
entrants — see §11 for the full table):

- **Uncontested roster** (100pp win-rate spread): seat sensitivity 0pp.
- **Fully 3-way-contested rosters** (6.7-35.6pp spread, all three
  entrants genuinely active): seat sensitivity 13.3-43.3pp — real but
  moderate.
- **2-active + 1-passive-bystander rosters** (50-55.6pp spread — a
  near-50/50 split between the two active entrants, third at ~0%): seat
  sensitivity **83.3-100pp** — the largest in the corpus, and
  qualitatively different in shape: in `claimer_hunter_coredefender`,
  Claimer wins **100% in one seat and 0% in another**, same for Hunter —
  the aggregate 50/50 win rate is not two entrants trading close wins,
  it is a *seat-deterministic coin flip* that happens to average to 50%
  across the six permutations.

**Refined answer to the "concentrates in contested matches" hypothesis**:
partially true, but not simply monotonic. The single largest seat effects
are not in the *closest* aggregate contests (those are moderate, 13-43pp)
but specifically in 2-active/1-passive rosters, where seat assignment
appears to fully determine which of the two active entrants wins a given
condition, and the near-50/50 aggregate is an artifact of averaging over
seat rather than evidence of a genuinely close per-condition contest.

## 11. Global seat-bias check

Aggregated across all 990 group cells (zero ties occurred anywhere in
this corpus, confirmed directly — every cell's `winner` matched exactly
one entrant, so this is a clean per-seat share of a fixed total):

```text
seat A: 233/990 entrant-cells won (23.5%)
seat B: 345/990 entrant-cells won (34.8%)
seat C: 412/990 entrant-cells won (41.6%)
```

**This is a real, systematic effect, and it deserves flagging.** A
consistent, monotonic A < B < C ordering across 11 unrelated rosters
spanning every archetype combination is not plausibly a per-roster
coincidence. The most direct explanation, consistent with the engine's
own documented behavior (not independently re-verified via replay
tracing in this phase): seat position is also scheduler execution order
(§14 of the governing prompt, and Phase 2/3's own design docs), and a
contested arena cell's ownership resolves to whichever entrant wrote it
**most recently** — so the last-acting entrant within a tick (seat C,
always) has a structural tie-breaking advantage on any cell more than one
entrant targets in the same tick, compounding over 400 ticks.

**Is this the "concerning" bias Section 29 describes?** No, by its own
criterion. The effect (18.1pp between the extreme seats) is real but does
not "overwhelm strategic differences" — every roster's own strategic
spread (0-100pp, §11's table below) is comparable to or larger than the
seat effect, and Beta2's exhaustive-permutation methodology **already
neutralizes this exactly where it matters**: every entrant occupies every
seat equally within a roster's own 90 cells, so no *individual entrant's*
aggregate win rate is inflated or deflated by this bias — the methodology
was specifically built to guarantee this (Phase 2's design doc), and this
phase's own numbers confirm it does. This is a real, disclosed engine/
scheduler property, not a methodology defect, and not a blocker.

## 12. Layout sensitivity

Layout-sensitivity ranges (max-min winner rate across `spread`/
`spread-shifted`/`close`) span 0-33.3pp in this corpus, with no single
layout universally favoring one archetype: `close` favored expansion-
heavy outcomes in some rosters (`claimer_coretracker_coredefender`:
claimer 53.3% close vs. 46.7% spread) and favored offense in others
(`reactive_hunter_coreseeker`: `core_seeker` 66.7% close vs. 33.3%
spread-shifted, the *opposite* direction for `hunter` in the same roster:
33.3% close vs. 66.7% spread-shifted). No consistent "close favors
offense" or "spread favors expansion" rule held across the corpus —
layout interacts with roster composition, not with archetype alone.

**Translation robustness (`spread` vs. `spread-shifted`)**: these are
**not** translation-equivalent in observed outcomes. Example
(`claimer_coretracker_coredefender`): claimer 46.7% (spread) vs. 33.3%
(spread-shifted), core_tracker 3.3% vs. 20.0% — a 13-17pp swing from a
pure arena rotation. The most direct, already-documented explanation
(alpha.4 §16, not re-derived here but directly applicable): at least one
search agent (`core_seeker`, and by the same design principle likely
`core_tracker`) anchors its scan schedule to a fixed **absolute** arena
address rather than a position relative to its own spawn point — shifting
the layout changes which absolute addresses seats land on, which
interacts with a fixed absolute scan schedule in a real, mechanistic way.
This is an **agent implementation assumption**, not an engine defect: the
engine's own arena is a uniform wraparound ring with no privileged
address, and other layout-insensitive agents in the same rosters (e.g.
`reactive_core_defender`, 0pp layout sensitivity throughout) show no such
effect.

## 13. Seed sensitivity

Per-roster seed-sensitivity ranges span 0-33.3pp (comparable to layout).
The global seed-bias check (§11's methodology, per seed instead of per
roster) shows the **same A < B < C seat ordering holds at every seed**,
with narrow variation (seat A: 21.7-26.3%, B: 32.8-36.9%, C: 39.9-45.5%
across seeds 1-5) — no seed reverses or materially amplifies the seat
effect. **No global seed bias was found beyond the already-identified
seat effect.** Per-entrant seed sensitivity (e.g. `core_tracker`
27.8pp in `claimer_coretracker_coredefender`) reflects genuine
condition-dependent strategy interaction, not a systematic seed artifact.

## 14. Pairwise vs. group divergence

The most informative case: `core_tracker` beats **both** Claimer and
Hunter individually in 1v1 (§16), yet does not dominate when facing them
**simultaneously** — `claimer_coretracker_hunter`'s three-way split is
core_tracker 30.0%, claimer 36.7%, hunter 33.3%, essentially even, a long
way from what pairwise dominance over both individual opponents would
predict. The most direct explanation: `core_tracker` can only pursue one
assault target at a time, while Claimer and Hunter each independently
expand/threaten in parallel — splitting the attacker's effective coverage
in a way no pairwise contest can expose. This is a clean demonstration
that Bytefray's group mode captures real multi-agent structure, not a
sum of independent 1v1 duels (classified: **interaction reversal** — a
pairwise-dominant strategy loses its dominance once its two opponents can
act independently rather than sequentially against it alone).

## 15. Non-transitive / cyclic behavior

No credible 3-cycle (A beats B, B beats C, C beats A) was found in this
corpus. The pairwise controls (§16) show a consistent, non-cyclic order
among Claimer/Hunter/Core Tracker (core_tracker beats both; Claimer beats
Hunter). §14's divergence is a real, important multi-agent effect, but it
is a *magnitude* change (dominant → contested), not a *reversal* (nobody
who loses a 1v1 to `core_tracker` goes on to beat it in the trio). No
further cyclic search was performed beyond the pairs/trios this corpus
already covers, per the governing task's instruction not to brute-force
every theoretical cycle absent a signal the data actually suggests one.

## 16. Global tick-budget methodology finding

Not a pre-registered research question, but discovered while comparing
pairwise controls against alpha.11's own reported numbers, and reported
in full because it materially affects interpretation:

```text
                          alpha.11 (200 ticks)   this corpus, 400 ticks   this corpus, 200 ticks
claimer vs core_tracker    40% / 60%              23% / 77%                47% / 53%
hunter  vs core_tracker    45% / 55%              23% / 77%                37% / 63%
claimer vs hunter          87.5% / 12.5%           67% / 33%                67% / 33%
```

`agent_test.DEFAULT_TICKS = 200`; this corpus's group methodology used
`--ticks 400` throughout (matching Phase 3's own established convention,
kept for internal consistency with the three reused matrices). The
200-tick reproduction is **much closer** to alpha.11's own numbers than
the 400-tick run, for both matchups involving `core_tracker` — consistent
with a real, sensible mechanism: a longer match gives a search-based
attacker more time to locate and assault a core, which should and does
shift outcomes toward it. The `claimer` vs. `hunter` matchup, which
involves no core-search dynamic, is **identical** at both tick budgets
(67%), consistent with that mechanism being the actual driver rather than
a generic "longer match, different result" effect. The residual gap at
200 ticks (47%/53% vs. alpha.11's 40%/60%) is plausibly attributable to
Beta2's own standard-placement/5-seed methodology differing from
alpha.11's own fixed single-seed thirds-of-the-arena placement — not
investigated further, as it does not affect any Phase 4 conclusion (every
comparison within this corpus uses one consistent tick budget throughout;
only this specific cross-study check mixed them, and is reported as such).

**This is a disclosed methodology parameter, not a defect**: every
within-corpus comparison in this document (all of §4-§15) uses the same
400-tick budget consistently, so none of those comparisons are affected.

## 17. Strategic diversity assessment

- **Multiple viable archetypes**: yes. Five of the six agents have the
  highest raw win rate in at least one tested roster: Claimer (5 of
  its 7 rosters), Hunter (`claimer_hunter_reactive`,
  and near-tied in `claimer_coretracker_hunter`), Core Defender
  (`claimer_coretracker_coredefender`, near-tied with Claimer), Reactive
  Core Defender (`claimer_coretracker_reactive`, `coredefender_reactive_
  coreseeker`), and Core Seeker (`reactive_hunter_coreseeker`
  tied at 50.0%, `hunter_coretracker_coreseeker` at 41.1%). Core Tracker
  has none outright — its best result is a
  three-way near-tie at 33.3% in `hunter_coretracker_coreseeker`, still
  consistent with alpha.11's own finding that search-based offense pays a
  real opportunity cost. Both search agents are nevertheless the
  *decisive* factor (highest
  `caused` rate) in every roster they join (§5/§7), a form of strategic
  value distinct from raw win rate.
- **Counter-strategies**: yes, one clear one (§5) — dedicated search
  defeats blind expansion, the central problem alpha.10/alpha.11 already
  set out to fix, confirmed still working under Beta2's own methodology.
- **Context-sensitivity**: yes, extensively (§10-§13) — seat, layout,
  and seed all materially affect outcomes, in roster-specific rather than
  universal patterns.
- **Multi-agent-specific behavior beyond repeated 1v1**: yes, clearly
  (§6 kingmaking, §14 pairwise-vs-group divergence).
- **Evidence of a simple universal solution**: no single strategy wins
  broadly across dissimilar rosters at a rate approaching 90-100% except
  in the one negative-control roster with zero offensive pressure present
  by construction.

## 18. Claimer risk assessment

**Conclusion after the expanded experiments**: Claimer's Matrix-A 90/90
result was matchup-specific, not roster-independent. Across the 7 Claimer
rosters in this corpus, its win rate ranges from 100% (no offense
present) to 36.7% (against two independent active rivals) — a 63pp
spread driven entirely by roster composition. It is the strongest or
co-strongest strategy only when statistical overlap, rather than raw
rank, is the intended meaning: Hunter has the higher raw rate in
`claimer_hunter_reactive`, and Core Defender narrowly leads in
`claimer_coretracker_coredefender`, but the corresponding intervals
overlap. That persistent statistical competitiveness is worth continued
monitoring as the roster pool grows, but it is not a
"solved game" by the standard this phase used (§17's five criteria):
counter-strategies exist and work, and its dominance is conditional, not
universal.

## 19. Instrumentation findings

One audit was performed directly against this phase's own data (Sec 42
of the governing prompt): every group record across all 2,430
entrant-cells in this corpus (990 primary + 45×3 reruns/pairwise-adjacent
checks) was checked for a `WINNER` outcome paired with `alive=False` —
the one theoretically-possible contradiction given the engine's
zero-survivor score-fallback rule (a dead entrant *can* legitimately win
only when literally every entrant is dead, per alpha.4.1's own documented
semantics). **Zero anomalies found** — no zero-survivor match occurred in
this corpus, and no `EntrantCellRecord` contradicted its own `alive`/
`outcome` fields. No instrumentation defect was found or fixed *during
this phase*. A later independent pre-qualification review found that
Phase 3's capture-tick repair was incomplete for multi-death last-agent-
standing matches: victim-side timing could still inherit the final match
tick even when that victim died earlier. Phase 4.1 corrected that
boundary. This Phase 4 analysis used capture occurrence/rate and
attribution, not victim-side capture-tick aggregates, so the correction
does not change any strategic conclusion or require a corpus rerun.

## 20. Factorial scaling

Not re-tested this phase — Phase 3's estimate (`docs/
V2_0_BETA2_PHASE3_MULTI_ENTRANT_ANALYSIS.md` §19) is unrevised: N=3
exhaustive remains cheap (measured again here, §21), N=4 is estimated
practical, N=5+ is the point a sampling/rotation policy becomes worth
considering. This phase's own corpus stayed entirely at N=3, consistent
with the governing task's instruction not to run a large N=4/5 corpus
merely to validate the existing estimate.

## 21. Performance

- 8 new group rosters (720 cells) + 6 pairwise runs (45+45 cells): total
  wall time **~99s** for all group runs (10.9-14.6s per 90-cell roster,
  consistent with Phase 3's measured ~6 cells/sec) plus **~15s** for the
  six pairwise runs.
- Analysis (`analyze_group` over all 11 group artifacts plus the seat/
  seed/closeness aggregation across the whole corpus): well under 1s
  total — consistent with Phase 3's measured ~3,800 cells/sec analysis
  throughput; not separately re-measured given the negligible cost
  already established.
- One reproducibility rerun (`claimer_coretracker_coredefender`, 90
  cells): **12.9s**, byte-identical `evaluation_id`/cell outcomes to the
  original run (§25).

## 22. Reproducibility

At the time of the study, retained local research artifacts under
`runs/research_v2_beta2_phase4/` included `matrix_config.json`,
`run_corpus.py`, `analyze_corpus.py`, and the generated results. The
configuration recorded every roster's exact candidate/opponents/
methodology, and the scripts called the production `agent_evaluation.main`
and `evaluation_group_analysis.analyze_group` entry points directly.
Those `runs/` inputs were intentionally untracked research data, however,
so a clean repository checkout alone is not a complete durable
reproduction bundle; this document is the durable evidence summary and
the retained local artifacts provide the stronger reproduction path where
available. One headline result was independently rerun and diffed
field-by-field: `claimer_coretracker_coredefender` produced an identical
`evaluation_id`, identical cell count, and byte-identical
`(schedule_id, match_id, outcome, score_subject)` for every one of its 90
cells. Per Phase 2/3's own determinism contracts (unchanged, not
re-verified exhaustively here), this generalizes to the rest of the
corpus.

## 23. Compatibility and regression

No production code was changed during Phase 4 itself. The later Phase 4.1
review did identify verification, compatibility, comparison, timing, and
presentation defects in the surrounding evaluation tooling; its fixes and
identity evidence are recorded separately in
`V2_0_BETA2_PHASE4_1_PRE_QUALIFICATION_REMEDIATION.md`.

## 24. Tests and quality

No new production tests were added — this phase found no production
defect and added no reusable production tooling beyond the research-area
scripts in `runs/research_v2_beta2_phase4/` (untracked, matching every
`runs/v2_0_alphaN_*/` precedent; see that directory's own `README.md`).
Per the governing task's explicit instruction, no strategic outcome
(e.g. "Claimer must win 100%") was encoded into any regression test.

```text
pytest:  1860 passed, 6 skipped, 2 deselected  (0 failed, 0 errors)
ruff check .:              All checks passed
mypy engine/src/battle_engine:  Success -- 73 source files
mypy client/src/battle_client:  Success -- 12 source files
git diff --check:          clean
```

Identical to Phase 3's own final qualification — expected, since no
production/test code changed in this phase.

## 25. Files changed

**Production**: none.

**Tests**: none.

**Research/tooling** (untracked, `runs/` — see §22): `matrix_config.json`,
`README.md`, `run_corpus.py`, `analyze_corpus.py`, `results/*`
(11 group + 6 pairwise evaluation artifacts), `summary.txt`.

**Documentation**: this file (new); `docs/V2_0_BETA2_PLAN.md`,
`docs/ROADMAP.md` updated.

## 26. Commits

Listed in the final report delivered alongside this document.

## 27. Remaining strategic concerns

**Important but non-blocking:**

- Claimer remains statistically indistinguishable from the raw leader in
  every tested roster even where it does not rank first by the point
  estimate (§18) — worth continued monitoring, particularly as the roster
  pool grows or new archetypes are added, but not currently evidence of a
  solved game.
- The global seat bias (§11, ~18pp A-to-C spread, plausibly last-write-
  wins-driven) is real and worth an eventual mechanistic confirmation via
  replay tracing — currently a plausible, unverified explanation, not
  independently proven. Does not currently threaten per-entrant
  evaluation fairness (exhaustive permutation neutralizes it), so it is
  not a blocker.
- The kingmaking-like passive-third-entrant benefit (§6) is real
  strategic depth, but also means some strategies win substantially
  through others' conflicts rather than their own merit — worth
  continued attention as Phase 4's own future work (roster composition
  at scale) proceeds.

**Future research** (not concerns, opportunities):

- The layout translation-robustness finding (§12) suggests at least one
  search agent's fixed-absolute-address scan schedule is worth
  documenting explicitly as a known agent-implementation property (not
  an engine property) if future agent-authoring guidance is written.
- Non-transitivity (§15) was not found in this corpus but was only
  checked among the specific pairs/trios already run — a dedicated
  search across a larger roster pool remains open for Phase 4's
  recommended successor.

No blocker-level concern was found.

## 28. Strategic assessment

```text
STRATEGIC ASSESSMENT: PROCEED WITH DOCUMENTED CONCERNS
```

Evidence for proceeding: real, working counterplay (search defeats blind
expansion, confirmed under Beta2's own methodology); genuine multi-agent-
specific structure not reducible to pairwise duels (§14); context
sensitivity that is roster-specific rather than universal (§10-§13); no
single strategy approaching a "solved game" by this phase's own five
criteria (§17); and Phase 4.1 confirmed that its later timing correction
does not affect the occurrence/rate evidence this research used (§19).
Evidence for
documenting rather than declaring unconditional success: Claimer's
persistent statistical overlap with the raw leader across every roster,
the real and only-plausibly-explained global seat bias, and the
kingmaking dynamic's potential to make win rate a less-than-fully-
informative signal on its own in future, larger-scale strategic work.
None of these individually or together constitute "broad simple-strategy
dominance," "severe uncontrolled seat bias," "pathological layout
dependence," or "lack of viable counterplay" — the four concrete triggers
for a Ruleset-research recommendation — so no Ruleset change is
recommended.

## 29. Phase 5 handoff

Recommended:

> **Beta2 Phase 5 — Integrated Qualification & Release Decision**

Scope, informed directly by this phase's findings:

- Full integrated regression/qualification pass across every Beta2 phase
  together (test suite, Ruff, mypy, `git diff --check`, a real
  source-tree smoke, an isolated-wheel smoke if packaging code changed
  anywhere in Beta2) — mirroring Beta1's own final integration phase.
- Carry forward, as documented (not blocking) concerns for whichever
  phase eventually does broader strategic work (this document's own
  recommended next research direction, previously slotted as "Beta2
  Phase 4" in the plan doc before this phase absorbed and completed that
  scope): roster-composition effects at larger scale, a mechanistic
  (replay-level) confirmation of the seat-bias hypothesis, and further
  kingmaking/non-transitivity search across a wider roster pool. None of
  these block Phase 5 or a Beta2 release.
- No Ruleset, scheduler, scoring, or agent changes belong in Phase 5.

## 30. Decision

```text
Beta2 Phase 4: COMPLETE
```
