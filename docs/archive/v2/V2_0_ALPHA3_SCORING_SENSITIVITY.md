# Bytefray v2.0.0-alpha.3 — Scoring Sensitivity / Break-Even Analysis

This is a **measurement pass**, not a mechanic or scoring change. It uses
the existing `bytefray-rules-2-alpha1` evaluation matrix from
[V2_0_ALPHA2_REACTIVE_DEFENSE.md](V2_0_ALPHA2_REACTIVE_DEFENSE.md) to ask a
single question: how far would Bytefray's existing `Config.weights` need to
move before reactive core defense stops being globally dominated by
unrestricted expansion, and what would that shift do to the rest of the
strategic landscape? No new scoring formula, weight default, Ruleset ID, or
mechanic is introduced here. All match mechanics (`CORE_SIZE`, arena size,
tick/instruction budget, placement, core-capture semantics, Core Seeker,
Reactive Core Defender, all starters, seeds 1-5) are held byte-for-byte
identical to alpha.1/alpha.2.

Branched from the verified alpha.2 baseline, commit `50d32cc9691f9c07f8100ee45dc58d92b9a50bdf`
on `v2.0-development` (`main` unchanged at the v1.6.0 baseline throughout).

## 1. Verified starting state (Phase 1)

Confirmed directly, not assumed:

- Branch: `v2.0-development`.
- HEAD at start of this work: `50d32cc9691f9c07f8100ee45dc58d92b9a50bdf`.
- Working tree: clean.
- `main`: `5593d287f95a24996bb3b105befbc625a00795db`, unchanged.
- Recent log matches the governing task's description exactly (alpha.2
  reactive-defense evaluation as HEAD, alpha.1 Vulnerable Core and its
  architecture doc immediately prior).
- `docs/V2_0_ALPHA1_EVALUATION.md`, `docs/V2_0_ALPHA2_REACTIVE_DEFENSE.md`,
  `engine/src/battle_engine/scoring.py`, `engine/src/battle_engine/config.py`,
  `engine/src/battle_engine/results.py`, `engine/src/battle_engine/statistics.py`,
  `engine/src/battle_engine/match.py`, and `engine/src/battle_engine/python_runtime.py`
  were read directly before any analysis code was written.
- alpha.1's and alpha.2's raw evaluation records
  (`runs/v2_0_alpha1_evaluation/`, `runs/v2_0_alpha2_evaluation/`) were
  still present on disk (untracked local scratch, per `.gitignore`'s
  existing `runs/` entry) and were used as the evidentiary base for this
  work.

## 2. Objective

Per the governing task: determine whether a plausible region of
`Config.weights` values exists in which reactive defense gains strategic
value while expansion, Core Seeker, and multiple other strategic styles
remain meaningfully viable — using only the existing scoring model and
existing match evidence, not a new formula or a new permanent
configuration.

## 3. Mechanics — unchanged (Phase 10, Phase 11)

Not modified at any point in this work: `CORE_SIZE`, arena size,
`instr_per_tick`, tick budget, subject/opponent start placement,
spawn-time core seeding, capture semantics/timing/attribution, Core
Seeker, Reactive Core Defender, Core Defender, all five Python starters,
seeds 1-5, orientation convention, `bytefray-rules-1`/`bytefray-rules-2-alpha1`
identities. No new Ruleset ID was created. The one rerun performed (§7)
reproduced alpha.2's exact 560-match matrix byte-for-byte on every
alpha.2-persisted field — proof, not assertion, that this pass changed no
match behavior (see §7's `verify_against_alpha2`).

## 4. Current scoring equation, from source (Phase 2)

Verified directly against `scoring.py`, `statistics.py`, `match.py`, and
`python_runtime.py` — not inferred from `results.json` alone. Per agent,
per match:

```
score = alive_ticks * weights.alive
      + kills        * weights.kill
      + bucket_sum    * weights.territory
```

where `bucket_sum = Σ over every executed tick of (cells_owned_that_tick
// weights.territory_bucket)`.

| Term | Default | Unit | Accrual | Alive-gated? |
|---|---:|---|---|---|
| `weights.alive` | 1.0 | points / tick alive | every tick (`score_alive`) | yes — `score_alive` checks `agent.alive` |
| `weights.kill` | 5.0 | points / kill event | once per kill (`score_kill`, called adjacent to `record_death(victim, killer)` in both `match.py:117` (VM) and `python_runtime.py:215` (core-capture)) | n/a (event-based) |
| `weights.territory` | 1.0 | points / bucket / tick | **every tick** (`score_territory`), not once at match end | **no** — `score_territory` has no alive filter; a dead agent can still accrue bucket score from cells it nominally still owns |
| `weights.territory_bucket` | 64 | cells / bucket | quantization granularity, not itself a reward weight | n/a |

`resolve_winner` (`results.py:44-67`) resolves the match winner: **if
exactly one entrant is alive at match end, that entrant wins
unconditionally** — before `win_mode` or score is ever consulted. Only
when both entrants are alive (the ordinary `tick_limit` case) or both are
dead does `win_mode="score_fallback"` (the default, used throughout the
alpha.1/alpha.2 matrix) fall back to comparing `score`. This single fact
turns out to be the load-bearing structural constraint of the entire
analysis (§9).

## 5. Raw metrics available, and what a rerun was needed for (Phase 2/3)

alpha.2's persisted `runs/v2_0_alpha2_evaluation/raw_matches.json` (560
records) carries `subject_score`/`opponent_score` (final, default-weighted),
`subject_alive`/`opponent_alive`, `subject_kills`/`opponent_kills`,
`subject_territory_last/max/avg`, and termination/outcome fields — but
**not** `alive_ticks`, and not the per-tick `bucket_sum` term.

- `kills` is already exact and persisted — no gap.
- `alive_ticks` is computed by the engine (`NativeAgentResult.alive_ticks`,
  `match_service.py:145`) but alpha.2's own driver simply never wrote it
  to `raw_matches.json`. Reconstructible without inference: it is a field
  the engine already produces, just not one alpha.2 happened to save.
- `bucket_sum` is **not** linearly recoverable from `territory_avg`/`last`/`max`
  alone, because `cells // territory_bucket` is an integer floor applied
  *inside* the per-tick loop — floor division does not commute with
  averaging over a moving cell count. This is a genuine gap, not a
  convenience shortcut being skipped.

Per Phase 2's instruction, the smallest research-only fix was applied:
`runs/v2_0_alpha3_scoring_sensitivity/rerun_capture.py` mirrors alpha.2's
`run_evaluation.py:run_one` line-for-line (identical `Config`, identical
entrant construction, identical seeds/placement/ruleset loop) and
additionally reads `a.alive_ticks`/`b.alive_ticks` off the exact same
`NativeAgentResult` object alpha.2's own driver already had in hand — **no
engine code was touched**, this only changes which already-computed field
a research driver chooses to persist.

`verify_against_alpha2` in that same script then diffed all 560 rerun
records against alpha.2's original file on every previously-persisted
field (score, winner, alive, kills, territory, termination). Result:
**`REPRODUCIBILITY CONFIRMED: all 560 records byte-for-byte identical`.**
This is the direct evidence that the rerun is the same 560 matches, not a
new dataset, and that mechanics were not altered.

## 6. Offline rescoring: derivation and exact validation (Phase 3)

With `alive_ticks` and `kills` now exact, and `score` already exact, and
having independently confirmed alpha.2's evaluation used unmodified
`Config()` weight defaults (`run_evaluation.py` never passes `weights=`),
`bucket_sum` is the unique solution of one linear equation in one unknown:

```
bucket_sum = (score - alive_ticks * 1.0 - kills * 5.0) / 1.0
```

This is **not** an inference from final score alone (which the governing
task explicitly warns against) — it is an exact algebraic inversion using
two independently-verified exact inputs (`alive_ticks` from the rerun,
`kills` already persisted) and the confirmed default weight values.
`runs/v2_0_alpha3_scoring_sensitivity/decompose.py` computes it for all
560 × 2 = 1,120 (match, role) pairs and applies two independent
cross-checks:

1. **Integrality**: buckets are integer counts by construction
   (`cells // 64`), so a correct decomposition must produce a
   non-negative integer every time. Result: **all 1,120 values are exact
   non-negative integers** — a wrong equation or a wrong assumption
   (e.g. a mismatched default weight) would have produced fractional or
   negative values almost everywhere; it did not, once.
2. **Reconstruction**: recomputing `score` from the decomposed
   `(alive_ticks, kills, bucket_sum)` at the default weights must
   reproduce the originally-recorded score exactly. Result: **confirmed
   for all 560 records, zero mismatches.**

Given this, offline rescoring under **any** alternate `(w_alive, w_kill,
w_territory)` is exact and requires no further engine execution:

```
rescored_score = alive_ticks * w_alive + kills * w_kill + bucket_sum * w_territory
```

Every sensitivity, break-even, and margin result in §8 onward is pure
arithmetic over this one captured, verified dataset
(`decomposed_matches.json`) — one rerun total for this entire alpha, not
one per weight configuration.

## 7. Winner determination under rescoring

Match winner under a candidate weight triple is computed exactly as
`resolve_winner` does (§4): if `subject_alive != opponent_alive`, the
surviving entrant wins **regardless of any weight value** — this is
called a **survival-forced** match below. Otherwise the rescored scores
are compared (`rescoring.py:match_outcome`). Across the 280
`bytefray-rules-2-alpha1` matches, exactly **16 are survival-forced** (all
16 of alpha.2's core captures); the other 264 always run the full
200-tick budget with both entrants alive at the end. All 280
`bytefray-rules-1` matches are score-decided (0 kills, 0 early
terminations under that ruleset in this population).

## 8. The central structural finding (Phase 5)

Before any grid was swept, an exhaustive check (not a sample) of all 560
records found:

> **In every one of the 264 (alpha ruleset) and 280 (v1 ruleset)
> non-survival-forced matches in this entire corpus, `alive_ticks` and
> `kills` are exactly tied between subject and opponent, with zero
> exceptions.**

Confirmed programmatically: `alive_tied=264/264`, `kills_tied=264/264`
(alpha); `alive_tied=280/280`, `kills_tied=280/280` (v1).

This is not a coincidence of the specific agents in this population — it
is a **structural consequence of the current mechanics and win-resolution
rule**, true for any 1-on-1, fixed-tick-limit match under this engine:

- `alive_ticks` can only differ between two entrants in the same match if
  one died before the other. But with exactly two entrants, one death
  drops `alive_count` to 1, which `resolve_termination` treats as
  immediately terminal (`last_agent_standing`) — the match ends the same
  tick the death occurs. So the only two possible outcomes are: both
  entrants survive to the identical shared `max_ticks` (trivially tied
  `alive_ticks`), or one entrant dies and the match is *already*
  survival-forced (§7) before `alive_ticks` could ever matter to a score
  comparison.
- `kills` can only be nonzero via a death (`score_kill` is only ever
  called adjacent to `record_death(victim, killer)`), and any death in a
  2-entrant match is exactly the case above — already survival-forced.
  There is no way, under the current mechanics, for two entrants in the
  same 1-on-1 match to end with unequal kill counts *and* both still be
  alive.

**Consequence:** for every non-forced match in this corpus,
`score_subject(w) − score_opponent(w) = w_territory · (bucket_sum_subject
− bucket_sum_opponent)` exactly — `w_alive` and `w_kill` cancel out of the
comparison identically, at *any* value, including 0 or arbitrarily large.
The winner of every non-forced match therefore depends on **exactly one
quantity**: the sign of `w_territory · (bucket_sum_subject −
bucket_sum_opponent)`. Since `bucket_sum_subject ≠ bucket_sum_opponent` in
every tested matchup, that sign is invariant to the *value* of
`w_territory` for any `w_territory > 0`, changes to "tie" only at
`w_territory = 0` (§9), and would exactly invert (not rebalance) for
`w_territory < 0` — a case excluded per Phase 4's instruction to avoid
negative weights without a meaningful interpretation (a negative
territory reward has none in this game's design intent).

This one fact governs essentially every subsequent result in this report.

## 9. One-weight-at-a-time sensitivity (Phase 5)

`runs/v2_0_alpha3_scoring_sensitivity/sensitivity.py` swept multipliers
`{0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0}` on each of `weights.alive`,
`weights.kill`, `weights.territory` individually, holding the other two at
their default value, over both the 280-match alpha population and the
280-match v1 population (`sensitivity_one_weight.json`).

**Result, exactly as §8 predicts:**

| Dimension swept | Matches flipped vs. default, at any tested multiplier | Reactive Core Defender win rate |
|---|---|---|
| `weights.alive`, 0×–2× | **0** (every single point) | 0/70 (alpha), unchanged at every point |
| `weights.kill`, 0×–2× | **0** (every single point) | 0/70 (alpha), unchanged at every point |
| `weights.territory`, 0.25×–2× | **0** (every point except 0×) | 0/70 (alpha), unchanged at every point |
| `weights.territory`, 0× exactly | **264** (of 280) | still **0/70** |

The `territory = 0` cell does not help Reactive Core Defender or any other
agent "win more" — it collapses nearly the entire non-forced population to
**ties** (since `alive_ticks`/`kills` are tied everywhere in that subset,
zeroing `territory` makes both sides' score exactly equal), which is why
264 outcomes change (win/loss → tie) while every win-count that isn't
already 0 *drops*, including Claimer's (65/70 → 0/70) and Hunter's
(60/70 → 0/70). This is a mass-tie collapse, not a rebalancing.

**Baseline win rates (default weights, for context):**

| Agent | alpha ruleset | v1 ruleset |
|---|---:|---:|
| claimer | 92.9% (65/70) | 100.0% (70/70) |
| strider | 64.3% (45/70) | 71.4% (50/70) |
| hunter | 85.7% (60/70) | 85.7% (60/70) |
| wanderer | 54.3% (38/70) | 57.1% (40/70) |
| adaptive | 30.0% (21/70) | 28.6% (20/70) |
| core_defender | 21.4% (15/70) | 28.6% (20/70) |
| core_seeker | 51.4% (36/70) | 21.4% (15/70) |
| reactive_core_defender | **0.0% (0/70)** | 7.1% (5/70) |

(The exact 7.1% under v1 is not zero — see §13.)

## 10. Break-even thresholds (Phase 6)

`runs/v2_0_alpha3_scoring_sensitivity/breakeven.py` solved the linear
break-even equation directly (not by grid search) for each of the seven
requested matchups, holding the other two weights at default, across all
5 seeds, in the orientation where the agent of interest plays the
"defender" role (starts at address 0).

**Result: every requested matchup falls into the `no_dependence` /
`impossible` categories, for a specific, provable reason — not "the
threshold is extreme," but "no finite reweighting of the existing three
terms can move this matchup's winner at all, except to a tie at
`w_territory = 0`":**

| Matchup (defender as subject) | `w_alive` break-even | `w_kill` break-even | `w_territory` break-even |
|---|---|---|---|
| Reactive Defender vs Core Seeker | no dependence (A_s=A_o=200) | no dependence (K_s=K_o=0) | 0.0 exactly (tie only) |
| Reactive Defender vs Claimer | no dependence | no dependence | 0.0 exactly |
| Reactive Defender vs Hunter | no dependence | no dependence | 0.0 exactly |
| Reactive Defender vs Core Defender | no dependence | no dependence | 0.0 exactly |
| Core Seeker vs Claimer | no dependence | no dependence | 0.0 exactly |
| Core Seeker vs Hunter | no dependence | no dependence | 0.0 exactly |
| Claimer vs Hunter | no dependence | no dependence | 0.0 exactly |

This holds identically across all 5 seeds for every matchup (these
specific cells are fully deterministic in this population; no seed
variation was observed in any of the seven). None of these seven cells is
survival-forced in this orientation (all 7 run the full 200-tick budget,
both entrants alive at the end) — confirmed directly, not assumed, in
`breakeven.json`.

**Interpretation:** `w_alive` and `w_kill` cannot move any of these seven
matchups by any amount, ever (§8's structural argument). `w_territory`'s
only "break-even" point is exactly zero — a full-population tie collapse,
not a competitive rebalancing (§9) — and every value on either side of
zero (for positive `w_territory`) reproduces the identical default
winner. There is no moderately-displaced or extreme-but-finite threshold
to report for any of these seven matchups; the honest answer is
"structurally unreachable within the existing three-weight model."

## 11. Multi-weight exploration (Phase 7)

Given §8's algebraic proof that `w_alive` and `w_kill` cancel out of every
non-forced comparison identically, a joint sweep should show zero
additional leverage from combining them with `w_territory`. This was
verified empirically, not just assumed:
`runs/v2_0_alpha3_scoring_sensitivity/multiweight.py` swept
`w_territory ∈ {0, 0.1, 0.25, 0.5, 1.0, 1.5, 2.0}` jointly against
`w_alive ∈ {0, 0.5, 1.0, 1.5, 2.0}` (25 cells) and separately against
`w_kill ∈ {0, 0.5, 1.0, 1.5, 2.0}` (25 cells), over the full 280-match
alpha population.

**Result:** in both 7×5 grids, every cell with `w_territory > 0` shows
`flipped_vs_default = 0`, for **every** tested `w_alive`/`w_kill` value —
confirming the joint space adds nothing beyond the one-dimensional result.
Only the `w_territory = 0` row shows any change (264 flips, all to ties),
identically regardless of `w_alive`/`w_kill`. No viability region — a
region where Reactive Core Defender or any other currently-losing agent
starts winning some previously-lost matches while others keep theirs — was
found anywhere in the 50-cell joint grid, nor is one algebraically
possible per §8.

## 12. Score-margin analysis (Phase 8)

Since winner-rank is provably insensitive to `w_alive`/`w_kill` and to the
*value* (only the zero-crossing) of `w_territory`, the governing task's
concern about a coarse win/tie/loss statistic hiding real movement is
directly investigated via raw and normalized score margin
(`runs/v2_0_alpha3_scoring_sensitivity/margin_analysis.py`).

**Non-forced matchups — margin scales exactly linearly with
`w_territory`, and only with `w_territory`** (seed 1, Reactive Core
Defender as subject/defender):

| Matchup | margin @ ×1.0 (default) | margin @ ×0.25 | margin @ ×0.05 | margin @ 0 (tie) |
|---|---:|---:|---:|---:|
| vs Core Seeker | −31 (−0.88%) | −7.75 (−0.66%) | −1.55 (−0.28%) | 0 |
| vs Claimer | −684 (−16.7%) | −171 (−12.9%) | −34.2 (−5.9%) | 0 |
| vs Hunter | −657 (−16.1%) | −164.25 (−12.4%) | −32.85 (−5.6%) | 0 |
| vs Core Defender | −39 (−0.98%) | −9.75 (−0.75%) | −1.95 (−0.34%) | 0 |

This is the exact shape of statement Phase 8 asks the analysis to be able
to make — e.g. **Reactive Defender remains a nominal loser against
Claimer at every positive `w_territory`, but the margin moves from −684 to
−34 as `w_territory` is scaled down to 5% of default** — but it also
shows the honest limit: the margin only ever *approaches* zero as
`w_territory → 0⁺`, asymptotically, never crossing it for any positive
weight (§8). The win/tie/loss statistic's "unchanged" verdict is
technically correct at every one of these points; margin analysis reveals
the graceful, monotonic approach the rank statistic cannot see, exactly
as alpha.2 §11 already flagged as a methodological gap.

**Forced (core-capture) matchups — margin genuinely depends on all three
weights, winner still fixed by survival:**

| Matchup (seed 1) | margin @ ×1.0 | margin @ ×2.0 | margin @ ×0 |
|---|---:|---:|---:|
| Core Defender vs Core Seeker | +21 (defender *ahead* on score) | +42 | 0 |
| Strider vs Core Seeker | +359 (victim ahead) | +718 | 0 |
| Hunter vs Core Seeker | +363 (victim ahead) | +726 | 0 |

**This is a striking, independently notable finding beyond what the
governing task anticipated:** in all three captured matchups sampled, the
*captured* entrant was still numerically ahead on score at the moment of
capture — Core Defender scored 940 vs. Core Seeker's 919; Strider scored
1,533 vs. 1,174; Hunter scored 1,554 vs. 1,191. `resolve_winner`'s
survival-first rule overrides this entirely: the sole survivor wins
regardless of how far behind on points it was. No reweighting of `alive`,
`kill`, or `territory` — the three terms `resolve_winner` would even look
at — can change this, because score is never consulted when only one
entrant survives (§4, §7). This closes off any possibility that a
"survival-adjusted" version of the *existing* three-weight model could
help these specific matchups; the mechanism that needs to change (if any)
would have to be `win_mode`/`resolve_winner` itself, not `Config.weights`
— explicitly out of this alpha's scope.

## 13. The one exception: Reactive Defender vs. Core Seeker under v1

Reactive Core Defender's only win anywhere in this 560-match corpus is
**against Core Seeker, under `bytefray-rules-1` (no core-capture
mechanic), in the orientation where Reactive Core Defender starts at
address 2048** — 5/5 seeds, by a 6-point margin (1,782 vs. 1,776). This is
a pure territorial-efficiency result: with no core to threaten, Core
Seeker's committed scan-then-burst behavior spends action budget on
non-claiming `READ`s and an unproductive `WRITE` burst, while Reactive
Core Defender's steady-state patrol (§ design in alpha.2) is close to
Claimer-efficient. This is a real, if narrow, data point that Reactive
Core Defender is not *unconditionally* the population's weakest agent —
it is weakest specifically where the core-capture mechanic exists and
Core Seeker is the opponent equipped to exploit it, i.e. under the exact
condition alpha.2 was designed to test.

## 14. Orientation effects (Phase 10)

All 16 survival-forced (core-captured) matches in this corpus occur in
the identical single orientation alpha.2 §10 already documented — Core
Seeker at address 2048, victim at address 0 — reproduced exactly here
(§ "forced" breakdown: `core_defender`×5, `strider`×5, `hunter`×5,
`wanderer`×1, attacker `core_seeker` in all 16, zero involving Reactive
Core Defender). Because §8's structural argument governs every non-forced
match regardless of orientation, and the forced matches are immune to
weights regardless of orientation, **orientation has no interaction
effect with scoring-weight sensitivity in this alpha** — the artifact
alpha.2 flagged is reproduced unchanged, not amplified or masked by any
tested weight configuration. This was not fixed here, per Phase 10's
explicit instruction.

## 15. Effect on Core Seeker, Claimer, and the other starters (Phase 5/9)

Because §8's tie applies to every agent in the population, not just the
defenders, **no agent's win/loss outcome against any opponent changes
under any tested single- or multi-weight configuration with
`w_territory > 0`** — Claimer (92.9%), Hunter (85.7%), Core Seeker
(51.4%), Strider (64.3%), Wanderer (54.3%), and Adaptive (30.0%) all hold
their exact default win rates across the entire tested space. The only
configuration that moves any of them is `w_territory = 0`, which drives
every one of them toward 0% (via mass ties, §9) rather than toward a more
even distribution. There is consequently no configuration in the tested
space, nor (per §8's proof) in the broader positive-weight space, where
Core Seeker's niche shrinks, Claimer's dominance softens, or any other
agent's relative standing shifts at all.

## 16. Candidate viability region (Phase 9)

**None exists within the legitimate (non-negative, semantically
meaningful) region of the existing three-weight model, for this
evaluation population.** This is not a negative result reached by failing
to find one after a search — §8 proves algebraically that the tested
space (and by the same argument, the entire untested positive-weight
space) cannot contain one, because the two dimensions (`alive`, `kill`)
that would need to trade off against `territory` to produce a graded
Pareto frontier are mathematically inert in every non-forced match in
this corpus. The only two "regions" outside the default are: (a)
`w_territory = 0`, a mass-tie collapse that helps no one and destroys the
existing competitive ordering for everyone including Claimer; (b)
`w_territory < 0`, a full ranking inversion with no meaningful
interpretation in this game's design (explicitly excluded by Phase 4).
Neither is a Pareto-style region — both are single degenerate points, not
regions, and neither leaves multiple strategies simultaneously viable.

## 17. Pathological regions (Phase 9)

`w_territory = 0` is the one pathological point found: it does not
promote any minority strategy, it flattens the entire non-forced
population to ties simultaneously, including previously-dominant Claimer.
This is recorded as a cautionary, not a candidate, finding.

## 18. Falsification-criteria assessment (Phase 13)

Every item on the governing task's "evidence against" list is met, in the
strongest form available:

- **"Reactive Defender requires extreme weight distortion before becoming
  relevant"** — stronger: it requires a value (`w_territory = 0`) that
  does not make it relevant at all (still 0/70), only degenerate.
- **"Any change that helps defense immediately breaks the rest of the
  field"** — the only weight change with any effect breaks the *entire*
  field simultaneously (mass ties), including agents having nothing to do
  with defense.
- **"No multi-strategy viability region exists"** — proven, not just
  observed absent, in §16.
- **"The current score components fundamentally cannot distinguish
  strategically desirable behavior"** — proven for `alive`/`kill` in this
  1-on-1 evaluation format specifically (§8): they are structurally
  incapable of discriminating between two entrants in any non-forced
  match under the current win-resolution rule, regardless of what
  "strategically desirable" would mean.
- **"Meaningful balance would require new scoring terms rather than
  reweighting existing ones"** — directly supported: no reweighting of
  the three existing terms can do anything except the two degenerate
  cases above.

None of the "evidence supporting a future scoring experiment" criteria
are met: no modest shift creates a defensive niche (none creates any
change at all, short of collapse); Reactive Defender does not improve
without universal-collapse side effects; no viable region exists to
report as "closer" or "gradual."

**Verdict: do not pursue a scoring-reweighting experiment on the existing
three-weight model in its current form.** The finding is not "the right
weights haven't been found yet" but "no weights, within this model and
this 1-on-1 evaluation format, can do the job" (§8, §16).

## 19. Suggested acceptance questions, answered directly (Phase 12)

1. Which weights most strongly reward unrestricted expansion? — `territory`
   is the *only* weight with any leverage over any outcome in this
   population; by elimination, it is also the only one capable of
   "rewarding" expansion at all.
2. Which term most strongly suppresses defensive play? — Same answer,
   `territory`, for the same reason: it is the only term that ever
   matters, so any suppression of defense necessarily routes through it.
3. Can Reactive Core Defender reach score parity with Core Seeker under a
   modest weight change? — **No.** Provably not under any weight change
   at all, modest or otherwise (§8, §10).
4. Parity with Claimer? — **No**, same proof.
5. Parity with Hunter? — **No**, same proof.
6. Does making defense viable make blind Core Defender too strong? —
   Moot; defense cannot be made viable via reweighting in this population.
7. Does rewarding survival reward passivity more than defense? — Not
   testable here: `weights.alive` never once affected an outcome in this
   corpus (§8), so this question cannot be answered from this evidence
   either way.
8. Does rewarding capture make Core Seeker dominant? — Not testable here
   either: every capture-involving match is already survival-forced,
   so `weights.kill` never once affected an outcome (§8).
9. Is there a region with 3-4 viable strategies? — **No** (§16).
10. How far is that region from defaults? — N/A; no such region exists.
11. Would reaching it look like a reasonable evolution or a redesign? —
    A redesign: per §18, the finding directly implicates the
    *win-resolution rule* (`resolve_winner`'s survival-first branch,
    §4/§12) and the 1-on-1 evaluation format itself, not just weight
    values — both out of this alpha's scope.
12. Can score-margin analysis see the alpha.2 improvement even when
    winner-rank says "unchanged"? — **Yes**, directly demonstrated in §12
    (margin narrows from −684 toward 0 as `w_territory` shrinks, and the
    capture-matchup margins show the captured entrant was often ahead on
    points despite losing by survival) — confirming alpha.2 §11's own
    prediction that a margin-based statistic would show real, otherwise
    invisible movement.

## 20. Unresolved questions (Phase 15 #26)

- **Is §8's tie a property of the 1-on-1 evaluation format specifically,
  or of Bytefray scoring in general?** Not resolved here, and this is the
  single most important open question this alpha raises. In a 3+-entrant
  match, `resolve_winner`'s single-survivor special case requires
  *all but one* entrant to be dead before it activates — two or more
  simultaneous survivors with genuinely different `alive_ticks` (one
  joined the "still alive" group later than another, having survived a
  third entrant's earlier attack) become possible, giving `weights.alive`
  a lever it structurally cannot have in this alpha's 1-on-1 matrix. This
  was out of scope here (the governing task fixed the matrix format) but
  is the most direct next experiment implied by this finding.
- Whether `weights.kill` could ever matter in *any* configuration of this
  engine, or whether it is structurally dead weight under
  `win_mode="score_fallback"` for as long as kills and terminal
  single-survivor states remain causally fused, is open.
- Whether a different `win_mode` (not explored, since Phase 4 scoped this
  alpha to `Config.weights` only) would change §8's conclusion is
  unknown — `win_mode="survival"` was not evaluated at all here, since
  changing `win_mode` is arguably a different lever than reweighting.
- `territory_bucket` (the 64-cell quantization granularity) was
  deliberately held fixed throughout (§6) because varying it is not
  offline-rescorable from the captured dataset (it would change
  `bucket_sum` itself, not just its weight) — whether a different bucket
  size changes anything is untested.

## 21. Recommendation (Phase 13/final report item 28)

**Do not pursue an isolated scoring-reweighting experiment on the
existing three-weight model as currently scoped.** The evidence is not
merely unfavorable, it is a closed-form proof that no such reweighting can
do anything for this evaluation population short of two degenerate,
unhelpful extremes. If Bytefray's v2 work wants to make defense (or any
other currently non-competitive strategic style) viable, the two paths
implied directly by this report's findings are: (a) test whether a
multi-entrant (3+) evaluation format gives `weights.alive`/`weights.kill`
genuine leverage that a 1-on-1 format structurally cannot (§20); or (b)
treat this as evidence that `resolve_winner`'s survival-first rule, not
`Config.weights`, is the actual lever controlling whether defense can ever
be rewarded — both are new-scope questions, not a continuation of
weight-tuning.

## 22. Regression qualification (Phase 16)

No production engine code was modified in this work — confirmed by `git
status`/`git diff` (§23). Every script in
`runs/v2_0_alpha3_scoring_sensitivity/` is a research driver, exactly like
alpha.1's and alpha.2's own `run_evaluation.py`, imported nothing new
into `engine/src/battle_engine/`, and is untracked scratch under the
existing `.gitignore` `runs/` entry.

