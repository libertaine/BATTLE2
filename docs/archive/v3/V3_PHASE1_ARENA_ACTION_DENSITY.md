# Bytefray v3 Phase 1 — Arena / Action-Density Characterization

Branch: `v3-research-phase1`, cut from `v3-research-phase0` at `51a39e8`
immediately after the Phase 0 report. Status: research complete, not
merged, not tagged, not published.

Phase 1 is **research, not feature implementation**. No locality, movement,
multiple loci, Agent API v2, replication, fog of war, new scoring, or
Ruleset-3 mechanic was implemented, and none was needed. No gameplay,
Ruleset, Agent API, or schema contract changed — see §16.

---

## 1. Initial state

Verified before any change:

| ref | value |
|---|---|
| starting branch | `v3-research-phase0` |
| HEAD | `51a39e86e720f2806981bcd35fda4e4ba6234c00` |
| Phase 0 commits present | `2370033`, `253fccb`, `063111c`, `ebe72a1`, `51a39e8` |
| `main` | `1093393` — unchanged, identical to `origin/main` |
| `v2.0.0` tag | annotated, still targets `965d2f6` |
| working tree | clean |
| frozen benchmark population | 9/9 members verify against their pinned `agent_revision_id` |

Historical v1/v2 branches and tags are untouched. Work proceeded on a new
branch `v3-research-phase1` cut from `51a39e8`. Nothing was merged or
tagged.

---

## 2. Research question

> **Is the residual Ruleset-v2 ecology materially dependent on arena/action
> density, or is its structure robust across reasonable parameter regions?**

Phase 1 must be able to weaken or eliminate the standing v3 thesis
("locality first; multiplicity gated behind locality"). A parameter region
that produces a materially richer ecology is a successful Phase 1 result
even though it would delay locality; so is a clean null.

---

## 3. Experimental design

### 3.1 The two axes are not independent, and the design says so

Phase 0 §12 measured the default arena at 81–98% claimed and warned that
raising the action budget alone would measure a territory ceiling. Phase 1
therefore treats arena size and action budget as one plane, indexed by a
dimensionless ratio:

```text
S = configured sweeps per entrant   = (instr_per_tick x ticks) / arena_size
P = configured aggregate pressure   = entrants x S
```

At the Ruleset-v2 defaults (arena 4096, budget 8, 400 ticks, 3 entrants),
`S = 0.781` and `P = 2.34`.

The grid is laid out so that several (arena, budget) pairs share an
identical `S` while their absolute arena size differs by up to 64x. Those
**constant-density diagonals** are the design's central instrument: they
hold action density fixed and vary only absolute scale, which is what
separates a *density* effect from a *scale* effect. Without them, "budget
32 behaves differently from budget 8" and "arena 16384 behaves differently
from arena 4096" would be two unfalsifiable one-dimensional stories.

### 3.2 Pilot (Phase 1D)

A deliberately cheap, discardable pilot ran first: 18 candidate conditions
x 2 rosters x 1 seed x 3 layouts x 6 seat permutations = 648 cells, 69.8 s,
0.47 GB. It is committed as the `pilot` stage of the grid definition so the
design decisions below are inspectable, not asserted.

Its job was to bound the reasonable region before the main grid was
declared. What it found:

| pilot observation | consequence for the main grid |
|---|---|
| No condition was rejected; arenas from 64 to 65536 all ran with 3 entrants. | The evaluation service's own bound (`2 x entrants x (CORE_SIZE+1)` = 54) is the only hard floor; 64 and 128 are legal. |
| Arena 64 and 128 produced mean match lengths of 14–18 ticks in the offense-heavy roster with near-total mortality. | A small-arena "collision regime" exists and must be represented in the main grid rather than asserted from pilot data. Arena 128 was promoted; arena 64 was not (it adds nothing 128 does not already show, and sits within a factor of 1.2 of the hard floor). |
| Along `S = 0.781`, summed final occupancy was 83.1 / 83.8 / 84.2 / 73.2% at arenas 1024 / 4096 / 16384 / 65536. | The constant-density diagonal is real and worth resolving fully; the main grid completes it with four points. |
| Budget 1 at arena 4096 (`S = 0.098`) was a strict continuation of the budget-2 trend, with `claimer` at 88.9% versus 83.3%. | Budget 1 was **not** promoted: it shows no new structure and sits below the declared lower bound of a quarter of the default. The `S` range it probed is covered by `a65536_b2` (`S = 0.012`) instead. |
| Mean realized ticks was 400 (no truncation at all) in every large-arena / low-budget condition. | Ticks are held at 400 for every condition — see §3.4. |
| Cost scaled sub-linearly in budget because high-density matches end early; the worst cell cost ~0.37 s and ~4.4 MB. | A 20-condition main grid at 3 seeds is affordable without pruning artifacts. |

Pilot results are **not** counted as evidence anywhere in this report
except where their conditions were deliberately promoted into the main
grid.

### 3.3 The declared main grid (Phase 1P)

Declared in
[`v3_phase1_arena_action_grid.json`](../../../engine/src/battle_engine/data/benchmarks/v3_phase1_arena_action_grid.json)
**before** any main-grid result was inspected, with
`declared_before_interpretation: true`, a per-axis rationale on every
value, and this stopping criterion:

> The reasonable parameter region is `arena_size` in [128, 65536] (powers of
> two, a 512x span bounded below by the standard-layout non-overlap
> requirement and above at 16x the default) crossed with `instr_per_tick` in
> [2, 128] (a quarter of the default to 16x it), giving configured density
> `S` in [0.012, 50] — roughly a 4000x span, from a condition where almost
> nothing is claimed to one where the arena is filled fifty times over.
> Phase 1 stops once these conditions are measured. No condition outside
> this region is added afterwards to rescue or overturn a result.

That criterion was respected: exactly the 20 declared conditions were run,
and nothing was added afterwards.

|                 | budget 2 | budget 8 | budget 32 | budget 128 |
|---|---:|---:|---:|---:|
| **arena 128**   | S=6.250  | S=25.00  | S=100.0   | — |
| **arena 256**   | S=3.125  | S=12.50  | S=50.00   | — |
| **arena 1024**  | S=0.781  | S=3.125  | S=12.50   | — |
| **arena 4096**  | S=0.195  | **S=0.781 (default)** | S=3.125 | S=12.50 |
| **arena 16384** | S=0.049  | S=0.195  | S=0.781   | — |
| **arena 65536** | S=0.012  | S=0.049  | S=0.195   | S=0.781 |

Constant-density diagonals present in the grid:

| S | conditions | arena span |
|---:|---|---:|
| 0.049 | `a16384_b2`, `a65536_b8` | 4x |
| 0.195 | `a4096_b2`, `a16384_b8`, `a65536_b32` | 16x |
| **0.781 (default density)** | `a1024_b2`, **`a4096_b8`**, `a16384_b32`, `a65536_b128` | **64x** |
| 3.125 | `a256_b2`, `a1024_b8`, `a4096_b32` | 16x |
| 12.5 | `a256_b8`, `a1024_b32`, `a4096_b128` | 16x |

Why each axis value, in short: every arena is a power of two so the study
measures a game parameter rather than `wanderer`'s coprime-stride
assumption (Phase 0 §12); 128 is the smallest arena that clears the layout
bound with margin; 4096 is the default and the Phase 0 control anchor;
65536 is 16x default and the declared ceiling. Budgets 2/8/32 are a
quarter, one, and four times the default at every arena; budget 128 is
added only at 4096 and 65536, because those two complete the `S = 12.5` and
`S = 0.781` diagonals — the pilot showed the >=99%-occupancy region is flat,
so extending budget 128 everywhere would only re-measure a ceiling.

### 3.4 Ticks held constant, and why that is not a quiet choice

`ticks = 400` at every condition. Phase 1E warns against quietly raising
ticks for large arenas. The evidence says none is warranted: mean realized
ticks is **400, 400, 399, 397, 396** at the five lowest-density conditions
— that is, large arenas are not being truncated at all. Truncation appears
only in *high*-density conditions (mean 189 ticks at `a4096_b128`), where
early core capture is the effect under study rather than a measurement
artifact. Raising ticks for large arenas would have changed `S` — the
variable under test — while claiming to protect it.

### 3.5 Corpus

Each condition runs the Phase 0 control corpus's own rosters and pairs, at
3 seeds instead of 5:

- **Group**: all 11 Phase 0 rosters x 3 seeds x 3 standard layouts x 6 seat
  permutations = **54 cells per roster, 594 per condition**. All eleven
  rosters are kept because §17 criterion 1 is scored by enumerating which
  agent leads each tested roster; a sampled subset could not be scored
  against the rubric verbatim.
- **Pairwise**: the three 400-tick controls x 3 seeds x 3 standard
  placements x 2 entrant orientations = **18 cells per pair, 54 per
  condition**. These supply criterion 2's counter-strategy evidence and
  criterion 4's pairwise-vs-group divergence at every condition. Beta2's
  three 200-tick variants are its own tick-budget finding, held constant
  here rather than re-measured per condition.

**Total: 648 cells per condition, 12,960 cells across the grid**, plus 1170
control-corpus cells and 648 pilot cells.

Three seeds rather than five is the one reduction from Phase 0's design,
and it is validated rather than assumed — see §5.

---

## 4. Density measures (Phase 1F)

Configured and realized are reported side by side everywhere, because they
are not the same number.

| measure | definition | what it does and does not capture |
|---|---|---|
| `S`, configured sweeps per entrant | `(instr_per_tick x ticks) / arena_size` | An upper bound on how many times one entrant could visit every cell. Assumes one action ~ one cell claimed, which a `READ` violates. Ignores early termination entirely. |
| `P`, configured aggregate pressure | `entrants x S` | Same, summed over entrants. Valid today because each entrant has one independent fixed budget. |
| configured scan coverage | `S / 3` | Both search agents spend exactly 1 action in 3 on a `READ` (`SCAN_EVERY = 3`, identical in both by design), so this is the fraction of the arena a searcher can inspect at all. |
| **realized actions per cell** | `sum(cpu_total) / arena_size` | No modelling assumption. `cpu_total` is already recorded per entrant in every `result.json`; nothing new was instrumented. Accounts for early termination. |

Realized never equals configured, and the gap is itself informative:

| condition | configured P | realized | realized / configured |
|---|---:|---:|---:|
| `a65536_b2` | 0.04 | 0.035 | 0.96 |
| `a4096_b8` (default) | 2.34 | 1.921 | 0.82 |
| `a65536_b128` | 2.34 | 1.567 | 0.67 |
| `a4096_b128` | 37.50 | 13.580 | 0.36 |
| `a128_b32` | 300.00 | 139.769 | 0.47 |

At low density essentially every configured action is spent; at high
density a third to two thirds of the nominal budget is never used because
entrants die first. Any analysis that treated configured budget as the
independent variable at high density would be measuring something that did
not happen. All conclusions below are stated against configured `S` for
labelling but were checked against realized density, which is monotone in
`S` throughout.

**What neither measure captures**, and it matters for §9: both are
*normalized* by arena size, so they say nothing about the *absolute* action
count. Two conditions on the same diagonal have identical `S` but budgets
differing by 16x, and some agent costs — a probe read, an assault burst —
are fixed absolute constants sized by the fixed 8-cell core. That
distinction turns out to be the sharpest finding in the phase.

---

## 5. Control reproduction

Three independent checks, strongest last.

**(a) The Phase 0 corpus still reproduces from the repository alone.** A
fresh 1170-cell run of `tools/v3_phase0_baseline_corpus.py` into a clean
directory reproduces all 25 published Beta2 group rates at **0.0 pp** and
all 6 pairwise controls to rounding, exactly as Phase 0 recorded. 54.3 s at
4 workers.

**(b) The grid's default condition is cell-for-cell the control.**
`594/594` default-condition cells match the corresponding Phase 0 control
cells on `match_id`, `outcome`, and both scores. The two evaluations carry
different `evaluation_id`s — correctly, because the seed set is
identity-bearing and 3 seeds is not 5 — but every match the grid actually
executed at the default is the identical executed match the control ran.
The three-seed reduction is a strict subset of the control, not a different
experiment.

**(c) Aggregates agree.** Comparing the grid's 3-seed default against the
5-seed control across all 33 roster/agent rates: 20 are identical to
0.0 pp, and the largest single difference is **8.5 pp**
(`core_defender` in `hunter_coretracker_coredefender`, 46.3% vs 37.8%),
well inside a 54-cell Wilson interval. Mean absolute difference 1.6 pp.

---

## 6. Main results

Full per-condition table. `sat%` is mean summed final territory across all
seats; `captures` is the fraction of entrant slots that ended
`core_captured`.

| condition | arena | budget | S | P | realized | sat% | ticks | captures | flags |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `a128_b2` | 128 | 2 | 6.250 | 18.75 | 9.763 | 96.1 | 249 | 42.8% | saturation_ceiling, undecided |
| `a128_b8` | 128 | 8 | 25.000 | 75.00 | 36.294 | 97.9 | 240 | 41.4% | collision_regime, saturation_ceiling, undecided |
| `a128_b32` | 128 | 32 | 100.000 | 300.00 | 139.769 | 98.4 | 235 | 40.7% | collision_regime, saturation_ceiling |
| `a256_b2` | 256 | 2 | 3.125 | 9.38 | 5.554 | 92.0 | 283 | 41.8% | saturation_ceiling |
| `a256_b8` | 256 | 8 | 12.500 | 37.50 | 17.152 | 93.4 | 224 | 44.7% | collision_regime, saturation_ceiling |
| `a256_b32` | 256 | 32 | 50.000 | 150.00 | 64.416 | 93.6 | 213 | 43.0% | collision_regime, saturation_ceiling |
| `a1024_b2` | 1024 | 2 | 0.781 | 2.34 | 1.869 | 84.0 | 360 | 23.8% | — |
| `a1024_b8` | 1024 | 8 | 3.125 | 9.38 | 5.662 | 90.8 | 282 | 38.8% | saturation_ceiling |
| `a1024_b32` | 1024 | 32 | 12.500 | 37.50 | 17.012 | 90.8 | 216 | 43.6% | collision_regime, saturation_ceiling |
| `a4096_b2` | 4096 | 2 | 0.195 | 0.59 | 0.536 | 38.3 | 397 | 12.9% | — |
| **`a4096_b8`** | **4096** | **8** | **0.781** | **2.34** | **1.921** | **86.0** | **370** | **23.4%** | **— (default)** |
| `a4096_b32` | 4096 | 32 | 3.125 | 9.38 | 4.903 | 90.1 | 255 | 46.7% | saturation_ceiling |
| `a4096_b128` | 4096 | 128 | 12.500 | 37.50 | 13.580 | 90.8 | 189 | 51.0% | collision_regime, saturation_ceiling |
| `a16384_b2` | 16384 | 2 | 0.049 | 0.15 | 0.140 | 11.3 | 400 | 5.4% | interaction_starved |
| `a16384_b8` | 16384 | 8 | 0.195 | 0.59 | 0.542 | 38.4 | 396 | 12.0% | interaction_starved |
| `a16384_b32` | 16384 | 32 | 0.781 | 2.34 | 1.897 | 84.4 | 363 | 22.5% | — |
| `a65536_b2` | 65536 | 2 | 0.012 | 0.04 | 0.035 | 2.9 | 400 | 4.3% | budget_starved, interaction_starved |
| `a65536_b8` | 65536 | 8 | 0.049 | 0.15 | 0.139 | 11.1 | 399 | 7.9% | interaction_starved |
| `a65536_b32` | 65536 | 32 | 0.195 | 0.59 | 0.501 | 35.7 | 381 | 21.1% | — |
| `a65536_b128` | 65536 | 128 | 0.781 | 2.34 | 1.567 | 72.9 | 304 | 32.6% | — |

### 6.1 The grid collapses onto density, not onto scale

Occupancy is a function of `P` alone, to within a few points, across a
512x range of arena size:

| P | conditions | measured sat% |
|---:|---|---|
| 0.04 | `a65536_b2` | 2.9 |
| 0.15 | `a16384_b2`, `a65536_b8` | 11.3, 11.1 |
| 0.59 | `a4096_b2`, `a16384_b8`, `a65536_b32` | 38.3, 38.4, 35.7 |
| 2.34 | `a1024_b2`, `a4096_b8`, `a16384_b32`, `a65536_b128` | 84.0, 86.0, 84.4, 72.9 |
| 9.38 | `a256_b2`, `a1024_b8`, `a4096_b32` | 92.0, 90.8, 90.1 |
| 37.5 | `a256_b8`, `a1024_b32`, `a4096_b128` | 93.4, 90.8, 90.8 |

The values track `1 - e^(-P)` closely (predicted 3.9 / 13.9 / 44.5 / 90.4%
for the first four rows) until early termination starts truncating the high
end. This is the clean quantitative statement of Phase 0 §12's warning:
**arena size and action budget are not two knobs; they are one.**

### 6.2 The usable region is a narrow density band

Reading the flags column: 14 of 20 conditions carry at least one degeneracy
flag (§13). **Six carry none at all** — `a1024_b2`, `a4096_b2`,
`a4096_b8`, `a16384_b32`, `a65536_b32`, `a65536_b128` — and two more
(`a256_b2`, `a1024_b8`) carry only `saturation_ceiling`, the mildest flag.

Every single unflagged condition has `S` in {0.195, 0.781}. The usable
region of a 4000x configured-density span is a band roughly a factor of
four wide, spanning four different arena sizes, and the shipped
default sits inside it.

---

## 7. Ranking perturbation (Phase 1I)

Two readings, because either alone would mislead.

*Pairwise relationship reversals* ask whether the sign of the win-rate
difference between two roster members flipped versus the default. *Strict*
reversals additionally require the two agents' Wilson intervals to be
disjoint at **both** conditions — a flip between two agents who were
already statistically indistinguishable at the default is not evidence.
Because the default ecology is full of near-ties (44.4 vs 45.6, 50.0 vs
50.0), that test is very demanding. *Rates moved* is the complementary
absolute measure: how many single-agent rates have a Wilson interval
disjoint from their own default interval — which catches a 50 pp move that
reverses nothing because the agent was already ahead.

| condition | S | leader changes | pairwise reversals | strict | rates moved | mean abs move | largest single move |
|---|---:|---:|---:|---:|---:|---:|---|
| `a128_b2` | 6.250 | 3/11 | 4/33 | 0 | 8/33 | 14.4pp | hunter in `claimer_hunter_reactive` -56pp |
| `a128_b8` | 25.000 | 5/11 | 5/33 | 0 | 6/33 | 12.2pp | hunter in `claimer_hunter_reactive` -56pp |
| `a128_b32` | 100.000 | 4/11 | 6/33 | 0 | 4/33 | 12.6pp | claimer in `claimer_coredefender_reactive` -50pp |
| `a256_b2` | 3.125 | 5/11 | 8/33 | 1 | 10/33 | 17.5pp | claimer in `claimer_hunter_reactive` +56pp |
| `a256_b8` | 12.500 | 5/11 | 8/33 | 0 | 9/33 | 15.7pp | hunter in `claimer_hunter_reactive` -56pp |
| `a256_b32` | 50.000 | 4/11 | 4/33 | 0 | 3/33 | 9.8pp | core_seeker in `coredefender_reactive_coreseeker` +28pp |
| `a1024_b2` | **0.781** | 4/11 | 5/33 | 0 | **4/33** | **10.0pp** | hunter in `claimer_hunter_reactive` -50pp |
| `a1024_b8` | 3.125 | 9/11 | 12/33 | 0 | 3/33 | 9.6pp | hunter in `claimer_hunter_reactive` -28pp |
| `a1024_b32` | 12.500 | 7/11 | 8/33 | 0 | 5/33 | 10.7pp | core_defender in `hunter_coretracker_coredefender` -24pp |
| `a4096_b2` | 0.195 | 4/11 | 4/33 | 0 | 8/33 | 15.9pp | hunter in `claimer_hunter_coredefender` -44pp |
| **`a4096_b8`** | **0.781** | 0/11 | 0/33 | 0 | 0/33 | 0.0pp | — (reference) |
| `a4096_b32` | 3.125 | 6/11 | 7/33 | 0 | 11/33 | 17.3pp | core_seeker in `claimer_coreseeker_hunter` +56pp |
| `a4096_b128` | 12.500 | 4/11 | 6/33 | 0 | 10/33 | 18.3pp | core_seeker in `claimer_coreseeker_hunter` +50pp |
| `a16384_b2` | 0.049 | 4/11 | 5/33 | 1 | **20/33** | **26.3pp** | hunter in `claimer_hunter_reactive` -56pp |
| `a16384_b8` | 0.195 | 4/11 | 5/33 | 0 | 11/33 | 17.2pp | core_seeker in `reactive_hunter_coreseeker` -39pp |
| `a16384_b32` | **0.781** | 3/11 | 4/33 | 1 | **3/33** | **8.9pp** | core_seeker in `reactive_hunter_coreseeker` -50pp |
| `a65536_b2` | 0.012 | 6/11 | 6/33 | 1 | 16/33 | 24.6pp | hunter in `hunter_coretracker_coredefender` +56pp |
| `a65536_b8` | 0.049 | 5/11 | 6/33 | 1 | 16/33 | 19.9pp | core_seeker in `reactive_hunter_coreseeker` -50pp |
| `a65536_b32` | 0.195 | 4/11 | 6/33 | 0 | **1/33** | **7.4pp** | claimer in `claimer_coreseeker_hunter` -22pp |
| `a65536_b128` | **0.781** | 6/11 | 10/33 | 1 | 8/33 | 16.4pp | core_seeker in `claimer_coreseeker_hunter` +78pp |

**Two conclusions.**

First, **no condition anywhere in the grid produces more than one
statistically robust pairwise reversal.** Leader changes look frequent
(3–9 of 11 rosters) and raw reversals reach 36%, but almost all of it lives
inside the uncertainty the default itself already carries.

Second, **the least-perturbed conditions are exactly the constant-density
diagonal.** `a16384_b32` moves 3 of 33 rates (mean 8.9 pp) and `a1024_b2`
moves 4 of 33 (mean 10.0 pp) — despite arenas 4x smaller and 4x larger than
the default. The most-perturbed are the ultra-low-density conditions
`a16384_b2` (20/33, mean 26.3 pp) and `a65536_b2` (16/33, mean 24.6 pp).
Holding density fixed across a 16x arena range changes the ecology less
than a single step down the density axis does. That is a direct measurement
of scale invariance, and it is the answer to Phase 1's framing question at
the level of raw outcomes: **the ecology is a function of density, not of
arena size.**

---

## 8. Pairwise versus group divergence (Phase 1K)

The v2 property that 1v1 strength does not predict group strength survives
everywhere, and is not weakened by any parameter region.

| condition | claimer vs core_tracker (1v1) | hunter vs core_tracker (1v1) | claimer vs hunter (1v1) | max abs(group − pairwise) |
|---|---:|---:|---:|---:|
| `a4096_b2` | 83.3% | 83.3% | 66.7% | 50.0 pp |
| **`a4096_b8`** | **33.3%** | **22.2%** | **66.7%** | **29.6 pp** |
| `a4096_b32` | 27.8% | 27.8% | 50.0% | 33.3 pp |
| `a16384_b32` | 38.9% | 33.3% | 50.0% | 11.1 pp |
| `a65536_b2` | 94.4% | 94.4% | 16.7% | 50.0 pp |
| `a65536_b128` | 16.7% | 16.7% | 50.0% | 50.0 pp |

The divergence is 11–69 pp at every one of the 20 conditions; it never
collapses toward "group outcome = repeated 1v1". Parameter tuning does not
turn this game into independent pairwise strength, which would have been
the clearest sign of *lost* depth.

The 1v1 column also carries the single most legible density effect in the
phase: `claimer` beats `core_tracker` **94.4%** of the time at
`a65536_b2` and loses **16.7%–33.3%** at the default and above. Search's
1v1 advantage over blind expansion is not a fixed property of the two
agents; it is bought with action density.

---

## 9. Search / offense effects (Phase 1L)

This is where the phase's sharpest structure appears. `search` is
`core_seeker` + `core_tracker`; `expansion` is `claimer` + `hunter`;
`caused` is the capture-caused rate. Hunter is counted as expansion, per
Phase 0 §10.3's correction of Beta2's archetype table.

| condition | S | search win | expand win | defend win | search caused | expand caused | defend caused |
|---|---:|---:|---:|---:|---:|---:|---:|
| `a65536_b2` | 0.012 | 2.7% | **67.3%** | 13.3% | 15.6% | 0.0% | 0.0% |
| `a16384_b2` | 0.049 | 2.9% | **64.9%** | 15.0% | 19.5% | 0.0% | 0.0% |
| `a65536_b8` | 0.049 | 4.1% | **63.9%** | 16.7% | 28.0% | 0.0% | 0.0% |
| `a16384_b8` | 0.195 | 8.2% | **58.7%** | 20.4% | 34.8% | 0.0% | 0.0% |
| `a4096_b2` | 0.195 | 9.1% | **57.1%** | 20.0% | 41.8% | 0.0% | 0.0% |
| `a65536_b32` | 0.195 | 24.9% | **48.4%** | 19.8% | 37.0% | 0.0% | 0.0% |
| `a1024_b2` | 0.781 | 27.2% | **45.0%** | 22.0% | 39.9% | 1.3% | 3.0% |
| **`a4096_b8`** | **0.781** | **24.1%** | **47.1%** | **22.4%** | **38.9%** | **2.9%** | **1.1%** |
| `a16384_b32` | 0.781 | 19.3% | **48.1%** | 25.2% | 36.6% | 1.9% | 1.3% |
| `a65536_b128` | 0.781 | **53.5%** | 32.9% | 15.7% | 28.2% | 0.3% | 1.1% |
| `a1024_b8` | 3.125 | 30.2% | **42.6%** | 22.6% | 5.1% | 8.7% | 9.6% |
| `a256_b2` | 3.125 | 39.3% | 36.8% | 23.1% | 10.1% | 9.0% | 9.4% |
| `a4096_b32` | 3.125 | **44.0%** | 36.0% | 20.0% | 5.6% | 13.1% | 11.5% |
| `a256_b8` | 12.500 | 32.1% | **37.6%** | 27.4% | 2.5% | 11.6% | 13.9% |
| `a1024_b32` | 12.500 | 32.9% | **43.4%** | 19.6% | 1.9% | 9.5% | 11.1% |
| `a4096_b128` | 12.500 | **40.1%** | 34.0% | 26.3% | 0.0% | 15.6% | 13.5% |
| `a128_b2` | 6.250 | 32.7% | 29.5% | 24.3% | 2.1% | 9.5% | 13.9% |
| `a128_b8` | 25.000 | 20.8% | **36.5%** | 25.2% | 0.0% | 16.5% | 16.7% |
| `a256_b32` | 50.000 | 25.9% | **48.4%** | 16.7% | 0.0% | 14.6% | 13.7% |
| `a128_b32` | 100.000 | 26.1% | **43.5%** | 19.4% | 0.0% | 19.7% | 13.1% |

Answering Phase 1L's five questions directly.

**1. Does larger arena make search relatively better or worse?** At
constant density, better — but only through absolute budget. Compare the
three `S = 0.195` conditions: search wins 9.1% at arena 4096, 8.2% at
16384, and **24.9%** at 65536. Same density, same occupancy (38.3 / 38.4 /
35.7%), 6x the search win rate. §9.1 explains why.

**2. Does lower action density make search more expensive?** Decisively
yes, and this is the opposite of the intuition that a roomier arena helps
the searcher. Search win rate falls monotonically **as `S` falls**: 24.1%
at the default, 9.1% at `S = 0.195`, 2.7% at `S = 0.012`, while expansion
climbs the other way to 67.3%. A searcher that cannot afford to scan is
simply a worse expander.

**3. Is there a region where search becomes competitively meaningful
without becoming trivial omniscience?** Two candidates, and **neither
survives inspection** — see §9.2.

**4. Does search remain strategically important through caused rates even
where its win rate is low?** Yes, and strikingly so, but only below
`S ~ 1`. At `S <= 0.781` search holds 15.6–41.8% caused while expansion and
defense hold **0.0–3.0%** — search is the *only* thing capturing cores. At
`S >= 3.125` that inverts completely: search caused collapses to 0.0–10.1%
and expansion caused rises to 8.7–19.7%.

**5. Does expansion's advantage shrink because saturation becomes harder?**
No. Expansion's advantage shrinks when saturation becomes *easier*
(higher density), not harder. At the low-density end, where saturation is
hardest, expansion is at its most dominant (67.3%).

### 9.1 The mechanism: a fixed-size core in an arena of any size

`S` normalizes by arena size, so the constant-density diagonal holds the
*relative* geometry fixed. What it does not hold fixed is the **absolute**
action count: `instr_per_tick x ticks = S x arena_size`. At `S = 0.195` an
entrant gets 800 actions in a 4096 arena and 12,800 in a 65536 arena.

Search's unit of work is priced in absolute actions, not in fractions of
the arena, because `CORE_SIZE = 8` is a fixed Ruleset constant. One
`core_tracker` investigation costs 4 probe `READ`s plus a 16-action assault
burst — 20 actions, whatever the arena is. With an 800-action budget that
is 2.5% of everything the agent will ever do, so it can afford two or three
investigations per match. With 12,800 actions it is 0.16%, and it can
afford forty.

That is why search improves along a constant-density diagonal, and it is
the one genuine *scale* effect in the grid. It is not a spatial effect at
all — it is an artifact of a fixed-size target in a scalable arena.

### 9.2 Where search wins, it wins for the wrong reason

Two regions put search ahead of expansion. Both are worse ecologies, not
better ones, and they fail in opposite directions.

**`a4096_b32` (S = 3.125): search wins without searching.** Search 44.0%
versus expansion 36.0% — a reversal of the headline v2 result. But search
caused is **5.6%** while expansion caused is **13.1%**: blind expansion is
now the dominant core-captor. At this density everyone's sweep incidentally
overwrites everyone's core, so the searchers are winning by surviving a
mutual-destruction regime, not by finding anything. §17 criterion 2's
counter-strategy — "dedicated search defeats blind expansion" — is gone;
what remains is attrition that happens to favour the agents that write
least.

**`a65536_b128` (S = 0.781, 16x default arena): search wins too well.**
Here the mechanism *is* intact — search caused 28.2% versus expansion 0.3%
— and search takes 53.5%. But `core_seeker` now wins **100.0%** of
`claimer_coreseeker_hunter` and **100.0%** of `reactive_hunter_coreseeker`,
two dissimilar rosters. §17 criterion 5 fails: search has become the simple
universal solution that expansion was accused of being.

The finding this points at is more useful than either region: **Ruleset v2
has one dominant axis at a time, and density only chooses which one.** The
v2 problem is not that expansion is too strong in particular.

---

## 10. Arena saturation (Phase 1M)

Measured from final per-entrant `territory_pct_last`, already
arena-normalized in every `result.json`, so it compares directly across
arena sizes. No trajectory reconstruction was implemented; only
final/aggregate occupancy is used, and the tick-by-tick shape of the
approach to saturation is therefore **not** measured. That limitation is
accepted rather than worked around, because reconstructing it would mean
reading replays from research tooling and crossing the engine/client
boundary Phase 0 was careful to respect.

Occupancy is a pure function of `P` (§6.1). Time to termination falls
monotonically as density rises: 400 ticks at `P <= 0.15`, 370 at the
default, 189 at `a4096_b128`. Capture rate per entrant slot rises with
density from 4.3% to 51.0%.

The question Phase 1M asks — *are apparently different strategic results
merely a consequence of whether the arena reaches saturation?* — has a
qualified answer: **largely yes for outcome magnitudes, and no for the
mechanism.** Saturation explains occupancy and match length completely. But
the transition that actually matters strategically — search losing its
monopoly on core capture between `S = 0.781` and `S = 3.125` — happens
between two conditions whose occupancy differs by only 4 points (86.0% vs
90.1%). Saturation is not the mediating variable there; the number of
*redundant* sweeps past saturation is.

### 10.1 A scoring confound on the arena axis, found and quantified

`Weights.territory_bucket = 64` is a fixed configuration constant and
`alive = 1.0` per tick. Territory scores `floor(owned_cells / 64)` per
tick. Since the bucket does not scale with the arena, changing arena size
silently re-weights the scoring function:

| arena | buckets available | survival's share of `claimer`'s score |
|---:|---:|---:|
| 128 | 2 | 56.2% |
| 256 | 4 | 49.0% |
| 1024 | 16 | 19.1% |
| 4096 | 64 | 7.4% |
| 16384 | 256 | 4.6% |
| 65536 | 1024 | 1.3% |

At arena 128 the effect is total rather than gradual: three entrants
sharing 128 cells each hold 25–54 cells, so `floor(owned / 64) = 0` for
everyone and the territory term contributes **exactly zero**. Every
entrant scores precisely 400 (its alive ticks) and every match is a
three-way tie — the `undecided` flag in §6.

**Consequence for interpretation**: arena size is *not* a pure spatial
variable under Ruleset-v2's default weights. A small-arena result partly
measures a shift toward survival scoring. This is recorded as a finding,
not corrected: `territory_bucket` is per-match configuration
(`docs/RULES.md` is explicit that a default-value change is not a Ruleset
change), but it is not exposed as a controlled evaluation variable, and
Phase 1 must not add a third variable mid-experiment. It is already
persisted in every artifact's `effective_conditions.weights`, so the
confound is fully recoverable from the record. See §17 for the follow-up
question this justifies.

---

## 11. Context sensitivity (Phase 1J)

Maximum within-roster win-rate range on each axis, in percentage points:

| condition | seat | layout | seed | roster-specific? |
|---|---:|---:|---:|---|
| `a128_b2` | 66.7 | 83.3 | 61.1 | all three |
| `a256_b2` | 83.3 | 50.0 | 38.9 | all three |
| `a1024_b2` | 66.7 | 50.0 | 33.3 | all three |
| **`a4096_b8`** | **100.0** | **33.3** | **27.8** | **all three** |
| `a4096_b32` | 83.3 | 66.7 | 33.3 | all three |
| `a16384_b2` | 44.4 | 33.3 | 16.7 | all three |
| `a16384_b32` | 100.0 | 33.3 | 22.2 | all three |
| `a65536_b2` | 83.3 | 33.3 | 11.1 | all three |
| `a65536_b32` | 83.3 | 66.7 | 38.9 | all three |
| `a65536_b128` | 100.0 | 38.9 | 33.3 | all three |

(Full 20-row table in the analysis artifact.)

Every axis is non-zero at every condition, and at every condition the
per-roster maxima differ from one another — the patterns stay
roster-specific rather than universal, which is what §17 criterion 3
actually requires.

Phase 1J's descriptive extension: **does a parameter region increase or
reduce sensitivity?** Seed sensitivity is the informative axis, because
seed is the only axis the agents themselves consume (`core_tracker` draws
its scan anchor from `context.rng`). It falls from 27.8 pp at the default
to **11.1 pp** at `a65536_b2` and `a65536_b8`, and 16.7 pp at
`a16384_b2` — the regime where search cannot afford to scan, so the one
seed-dependent behaviour in the corpus stops mattering. Low density does
not merely shift the balance; it removes a source of variety. Conversely no
region increases sensitivity meaningfully above the default: the maximum
seed range anywhere is 61.1 pp at `a128_b2`, a condition where most matches
are ties, and the best non-degenerate value is 38.9 pp at `a65536_b32`.

**Does the best strategy change across conditions?** Yes — `claimer`,
`hunter`, `core_defender`, `reactive_core_defender`, `core_seeker`, and
`core_tracker` each lead at least one roster somewhere, and 3–9 of 11
roster leaders change relative to the default at every non-default
condition. But §7 shows almost none of that is beyond uncertainty, and §9.2
shows that where a genuine change occurs, it replaces one dominant
archetype with another rather than balancing them.

---

## 12. Beta2 Phase 4 §17 ecology rubric

The five criteria are used **verbatim** from
[docs/V2_0_BETA2_PHASE4_STRATEGIC_CHARACTERIZATION.md](../v2/V2_0_BETA2_PHASE4_STRATEGIC_CHARACTERIZATION.md)
§17. No replacement rubric was created; the supplementary measurements
above are reported alongside, never in place of, the five criteria.

Operationalization, stated so the scores are auditable:

1. **Multiple viable archetypes** — count of distinct agents holding the
   highest raw win rate in at least one tested roster. Ties count as leads
   for every tied agent, which is how §17 itself counts them
   ("`reactive_hunter_coreseeker` tied at 50.0%"). Passes at >= 2.
2. **Counter-strategies** — requires *both* halves of §17's own sentence:
   dedicated search must actually defeat blind expansion (an expansion
   agent below 50% in a 1v1 against `core_tracker`) **and** search must be
   the reason cores fall (highest capture-caused rate belongs to a search
   agent).
3. **Context-sensitivity** — all three of seat, layout and seed materially
   affect outcomes, in roster-specific rather than universal patterns.
4. **Multi-agent-specific behavior** — kingmaking (highest-caused agent is
   not the winner while a low-caused third collects) or pairwise-vs-group
   divergence >= 10 pp.
5. **No simple universal solution** — no single agent at >= 90% in two or
   more rosters outside the declared negative control. "Broadly across
   dissimilar rosters" requires more than one roster.

| condition | S | C1 (leaders) | C2 | C3 | C4 | C5 | passed |
|---|---:|---|---|---|---|---|---:|
| `a128_b2` | 6.250 | PASS (6) | **FAIL** | PASS | PASS | PASS | 4/5 |
| `a128_b8` | 25.000 | PASS (4) | **FAIL** | PASS | PASS | PASS | 4/5 |
| `a128_b32` | 100.000 | PASS (3) | **FAIL** | PASS | PASS | PASS | 4/5 |
| `a256_b2` | 3.125 | PASS (5) | PASS | PASS | PASS | **FAIL** | 4/5 |
| `a256_b8` | 12.500 | PASS (5) | **FAIL** | PASS | PASS | **FAIL** | 3/5 |
| `a256_b32` | 50.000 | PASS (5) | **FAIL** | PASS | PASS | PASS | 4/5 |
| `a1024_b2` | **0.781** | PASS (6) | PASS | PASS | PASS | PASS | **5/5** |
| `a1024_b8` | 3.125 | PASS (6) | **FAIL** | PASS | PASS | PASS | 4/5 |
| `a1024_b32` | 12.500 | PASS (4) | **FAIL** | PASS | PASS | PASS | 4/5 |
| `a4096_b2` | 0.195 | PASS (3) | **FAIL** | PASS | PASS | PASS | 4/5 |
| **`a4096_b8`** | **0.781** | PASS (4) | PASS | PASS | PASS | PASS | **5/5** |
| `a4096_b32` | 3.125 | PASS (5) | **FAIL** | PASS | PASS | PASS | 4/5 |
| `a4096_b128` | 12.500 | PASS (6) | **FAIL** | PASS | PASS | PASS | 4/5 |
| `a16384_b2` | 0.049 | PASS (3) | **FAIL** | PASS | PASS | **FAIL** | 3/5 |
| `a16384_b8` | 0.195 | PASS (3) | **FAIL** | PASS | PASS | PASS | 4/5 |
| `a16384_b32` | **0.781** | PASS (5) | PASS | PASS | PASS | PASS | **5/5** |
| `a65536_b2` | 0.012 | PASS (3) | **FAIL** | PASS | PASS | **FAIL** | 3/5 |
| `a65536_b8` | 0.049 | PASS (3) | **FAIL** | PASS | PASS | PASS | 4/5 |
| `a65536_b32` | 0.195 | PASS (4) | PASS | PASS | PASS | PASS | **5/5** |
| `a65536_b128` | **0.781** | PASS (6) | PASS | PASS | PASS | **FAIL** | 4/5 |

### 12.1 Reading the scores

**No condition in the grid scores better than the shipped default.** Four
conditions score 5/5: `a4096_b8` (the default), `a1024_b2` and `a16384_b32`
(the same density at 4x smaller and 4x larger arenas), and `a65536_b32`
(one density step down at 16x the arena). Three of the four are the
default's own iso-density diagonal.

**Criterion 1 never fails**, at 3–6 distinct leading agents. The default's
count is 4, reproducing Phase 0 §9's corrected four-of-six exactly.
Criterion 1 is not discriminating: even the tie-degenerate arena-128
conditions "pass" it, because a tie counts as a lead for all three
entrants. Criterion 1 measures whether outcomes are spread, not whether
strategy causes them.

**Criteria 3 and 4 never fail either.** Context sensitivity and
multi-agent-specific behaviour are robust properties of the game across the
whole reasonable region. Notably the kingmaking mechanism check reproduces
at every single condition: remove the search agent from
`claimer_coretracker_coredefender` or `claimer_coretracker_reactive`, and
the passive third's win rate drops to **0.0%** in **39 of the 40**
roster/condition pairs (5.6% in the fortieth, `a128_b32`). An actual
elimination event is required to open the door, everywhere. What changes is
*who the kingmaker is* — the agent with the highest caused rate in those
rosters is `core_tracker` at `S <= 0.781` and `claimer` itself at
`S >= 3.125`.

**Criterion 2 is the discriminating one, and it fails in two opposite
ways.**

- *Below the band* (`a4096_b2`, `a16384_b2`, `a16384_b8`, `a65536_b2`,
  `a65536_b8`): search still owns capture attribution completely (caused
  0.44–0.67 versus **0.00** for every non-search agent, at all five) but no
  longer wins the matchup — `claimer` beats `core_tracker` 66.7–94.4% in
  1v1. The mechanism survives; the outcome does not.
- *Above the band* (`a1024_b8`, `a1024_b32`, `a4096_b32`, `a4096_b128`,
  `a256_b8`, `a256_b32`, all three arena-128 conditions): search no longer
  owns the mechanism — non-search caused (0.35–0.83) exceeds search caused
  (0.00–0.22) at every one of the nine. Six of them still win the matchup
  (claimer 22.2–44.4%), so the outcome survives and the mechanism does not;
  at `a128_b32` (claimer 88.9%) and `a256_b32` (50.0%, no advantage either
  way) **both** halves have gone.

Criterion 2 holds only where both halves hold: `S` between roughly 0.2 and
0.8, plus one small-arena outlier (`a256_b2`) that fails criterion 5
instead.

**Criterion 5 fails at both extremes, with different culprits.** At
ultra-low density `claimer` reaches 90.7–96.3% in three rosters and
`hunter` 90.7–96.3% in a fourth. At `a256_b2`/`a256_b8` `claimer` reaches
94.4–100% in two rosters. At `a65536_b128` the universal solution is
`core_seeker` at 100% in two rosters. Every failure is a single archetype
running away with the game; only the identity of the archetype changes.

---

## 13. Degenerate regions (Phase 1O-C)

Five descriptive flags, applied per roster and reported per condition.
They are screening labels, never a verdict on their own.

| flag | definition | conditions |
|---|---|---|
| `saturation_ceiling` | mean final occupancy >= 99%: every strategy fills the arena | all of `a128_*`, `a256_*`, `a1024_b8`, `a1024_b32`, `a4096_b32`, `a4096_b128` |
| `collision_regime` | captures occur and the mean match ends within a tenth of the tick budget | `a128_b8`, `a128_b32`, `a256_b8`, `a256_b32`, `a1024_b32`, `a4096_b128` |
| `undecided` | over half the cells produce no winner at all | `a128_b2`, `a128_b8` |
| `interaction_starved` | a roster containing a dedicated search agent still produced no core capture in any cell | `a16384_b2`, `a16384_b8`, `a65536_b2`, `a65536_b8` |
| `budget_starved` | mean final occupancy < 5% | `a65536_b2` |

The two ends of the grid are degenerate for opposite and unrelated reasons.

**The small-arena end fails on scoring resolution, not on space.** At arena
128 no entrant ever accumulates a single 64-cell territory bucket, so the
territory term is identically zero, every score equals the alive-tick
count, and every match is a three-way tie (§10.1). This is a property of
the fixed `territory_bucket = 64` meeting a small arena — it would occur at
any density. Arena 256 is the boundary case: four buckets exist, so the
score function has four levels of resolution for three entrants.

**The large-arena/low-budget end fails on non-interaction.** At
`a65536_b2` the three entrants together claim 2.9% of the arena and the
searchers never find anything; matches run the full 400 ticks and are
decided by who swept fastest. This is exactly Phase 1O-C's "apparent
balance comes from agents failing to interact" — except it is not even
balanced, because it is where `claimer` is most dominant.

**Fourteen of twenty conditions carry at least one flag.** The parameter
space is not *mostly* degenerate — six conditions carry no flag at all and
two more carry only the mildest one, and that band behaves well — but the
usable region is bounded far more tightly than a 4000x density span
suggests.

---

## 14. Agent arena-size awareness (Phase 1Q)

Phase 1Q instructed that the frozen agents experience changed environments
without modification or new information, and that arena-size ignorance be
recorded as evidence if it produced pathological behaviour. It did not,
and the reason is a correction to the Phase 0 report.

### 14.1 Correction: the agents are told the arena size

Phase 0 §17 records as a Phase 1 constraint:

> **`Observation` does not expose arena size.** An agent cannot currently
> adapt its stride to a varied arena.

The first sentence is literally true; **the inference in the second is
not.** Arena size is not exposed on `Observation`, but it is exposed on
`MatchContext`, which every agent receives once in `reset()`:

```python
@dataclass(frozen=True)
class MatchContext:
    agent_id: str
    seed: int
    arena_size: int
    tick_limit: int
    action_budget: int
    rng: random.Random
```

`python_runtime` builds it directly from the match config
(`arena_size=config.arena_size`, `tick_limit=max_ticks`,
`action_budget=config.instr_per_tick`), so all three Phase 1 variables are
visible to agents at reset. **All nine frozen benchmark agents already read
`context.arena_size`**, and `adaptive` additionally reads
`context.tick_limit`. None reads `action_budget`.

Since arena size is immutable for the life of a match, `reset()` is the
only place it is needed. There is no adaptation an agent is prevented from
making. Per Phase 0's own discipline for the Beta2 defects it found, this
is recorded here with its evidence rather than corrected in the Phase 0
document.

### 14.2 What is genuinely fixed, and whether it mattered

Some agent constants really are absolute rather than arena-relative:
`claimer`'s stride 101, `strider`'s and `core_defender`'s 131, `hunter`'s
dense stride 173, `core_seeker`'s 149, `core_tracker`'s 157, `adaptive`'s
149/197. All are odd, and every arena in the grid is a power of two, so
each remains coprime with the arena and a full sweep still visits every
cell exactly once. Absolute strides change the *order* of visitation, not
the coverage per action. `wanderer`'s documented power-of-two assumption
(Phase 0 §12) is likewise never violated, and `wanderer` is not in the
ecology core in any case.

The one constant that genuinely does not scale, and genuinely does matter,
is not an agent's: it is `CORE_SIZE = 8`, a Ruleset constant. §9.1 shows
this is the mechanism behind the only real scale effect in the grid.
`core_tracker`'s `PROBE_OFFSETS` and `ASSAULT_WINDOW` are sized around it
correctly; the asymmetry is between a fixed-size target and a scalable
arena, not between an agent and its environment.

**Conclusion for Phase 1Q**: agent arena-size ignorance did not materially
affect any conclusion, because it does not exist. No Agent API change is
warranted or recommended. What might warrant a future experiment is the
opposite question — whether an agent *should* be able to scale its
investigation cost with the arena — but that is a mechanic question, not an
API one.

---

## 15. Performance

| measure | value |
|---|---|
| grid cells executed | **12,960** (20 conditions x 648) |
| evaluations | 280 |
| workers | 4 |
| total wall clock | **1090.5 s (18.2 min)** |
| mean per condition | 54.5 s |
| cheapest / costliest condition | `a4096_b2` 26.2 s / `a65536_b128` 224.9 s |
| total artifacts | **12.73 GB** |
| mean `replay.jsonl` per cell | 231 KB (`a128_b2`) to 4762 KB (`a65536_b128`) |
| failed or drifted cells | **0** (no non-zero exit anywhere) |
| pilot | 648 cells, 69.8 s, 0.47 GB |
| control reproduction | 1170 cells, 54.3 s, 0.63 GB |

Against Phase 0's reference (1170 cells, 69.1 s, 651 MB): per-cell cost at
the default condition is unchanged, and the grid's extra cost comes almost
entirely from the two budget-128 conditions. Replay volume scales with
`instr_per_tick x realized ticks`, not with arena size, and remains the
dominant artifact cost exactly as Phase 0 predicted. Nothing was optimized;
no region presented a blocker.

---

## 16. Compatibility

**Nothing changed.**

| axis | changed? | reasoning |
|---|---|---|
| Ruleset identity (`bytefray-rules-2`) | **No** | Only `arena_size` and `instr_per_tick` varied, both already documented as per-match configuration rather than Ruleset identity. No gameplay semantic was touched. |
| Agent API version | **No** | No `Observation`, `MatchContext`, or `AgentAction` field changed. Agents receive exactly the information they already received. |
| Benchmark agent source | **No** | All 9 members verify against their pinned `agent_revision_id`. |
| Result / replay / evaluation schema | **No** | No production module was modified at all. |
| Evaluation methodology identity | **No** | The 20 conditions produce 20 distinct `evaluation_id`s because `effective_conditions` was already identity-bearing before Phase 0; the default condition's identity is byte-identical to the omitted-parameter identity. |
| Scoring, winner resolution, scheduler | **No** | Untouched. |

Production code changed: **none**. Phase 1 added two research tools, one
committed grid definition (package data, discovered by the existing
`data/**/*` glob), and one test module. `git diff --stat` against the
Phase 0 branch shows no file under `engine/src/battle_engine/*.py`,
`client/`, or `app/`.

One deliberate non-change is worth recording. `EntrantCellRecord` does not
carry `cpu_total`, which Phase 1F requires. Widening it would have changed
the JSON shape of `evaluation-history show --json`'s `group_analysis` block
for one experiment's benefit. The Phase 1 tool reads `cpu_total` from
`result.json` itself instead — research tooling absorbing the cost rather
than a production surface absorbing a schema change.

### 16.1 Validation (Phase 1T)

Run at `a65536_b128` — 16x the default arena and 16x the default budget, so
that anything milder is covered a fortiori:

| check | result |
|---|---|
| Repeated identical conditions reproduce deterministically | **PASS** — two independent runs, identical `evaluation_id` and identical `match_id`/`result_id`/outcome/both scores across all 36 cells |
| Serial and parallel execution agree | **PASS** — `--workers 1` identical to `--workers 4` |
| Resume over a completed non-default evaluation changes nothing | **PASS** — no `resumed_result_mismatch`, no corrupted cells |
| Explicit defaults identical to omitting the parameters | **PASS** — both resolve to the same `evaluation_id` |
| Every grid condition has a distinct evaluation identity | **PASS** — 20 conditions, 20 distinct ids |
| The default grid condition matches the omitted-parameter identity | **PASS** |
| The grid's default condition reproduces the Phase 0 control corpus | **PASS** — 594/594 cells identical |
| Phase 0 control corpus reproduces from scratch | **PASS** — 25/25 group rates at 0.0 pp, 6/6 pairwise to rounding |
| Historical artifacts still load | **PASS** — 34 `evaluation.json` artifacts (13 at schema v5, 21 at v6) through `adapt_any`, 0 failures |
| Full test suite (`python -m pytest`) | **1995 passed, 14 skipped, 2 deselected** in 259.9 s. Phase 0's measured baseline was 1972 passed with the same 14/2 — so the delta is exactly the 23 new tests, with no pre-existing test altered |
| Focused Phase 0 + Phase 1 tests | 59 passed (20 conditions + 16 benchmark + 23 grid) |
| `ruff check .` | All checks passed |
| `mypy engine/src/battle_engine` | Success, 75 source files |
| `mypy client/src/battle_client` | Success, 12 source files |

No Phase 0 identity guarantee was weakened.

---

## 17. Phase 1 disposition

### **STRUCTURAL LIMITATION SUPPORTED — READY FOR LOCALITY RESEARCH**

The evidence, in the order it forces the conclusion:

1. **Arena size and action budget are one variable, not two.** Occupancy,
   match length, capture rate and every strategic aggregate are functions
   of configured density `P`, not of arena size. Holding density fixed
   across a 64x arena range leaves the ecology essentially unchanged
   (`a16384_b32`: 3 of 33 rates moved, mean 8.9 pp; `a1024_b2`: 4 of 33,
   mean 10.0 pp).

2. **No parameter region improves the ecology.** Four conditions score 5/5
   on the verbatim §17 rubric; three of them are the default's own
   iso-density diagonal and the fourth is one density step away. The
   shipped default is already at the optimum of the tested space.

3. **Tuning changes magnitudes, not relationships.** Across 20 conditions
   and 660 pairwise relationship comparisons (33 per condition), **no
   condition produced more than one statistically robust reversal.**
   Leader changes are frequent (3–9 of 11 rosters) but live inside the
   uncertainty the default already carries.

4. **Where a real strategic change does occur, it degrades the ecology.**
   Both regions that put search ahead of expansion fail the rubric — one
   because expansion has taken over core capture and search is merely
   surviving attrition (`a4096_b32`), the other because search has become a
   universal solution (`a65536_b128`). The v2 limitation is not "expansion
   is too strong": it is that the game supports **one dominant axis at a
   time**, and density only selects which.

5. **Both extremes are degenerate, for unrelated reasons** — scoring
   resolution collapses at and below arena 256 (§10.1, §13), and
   interaction disappears below `S ~ 0.05` in the other direction. Fourteen
   of twenty conditions carry a degeneracy flag.

This is not Outcome C. The parameter space is not *mostly* degenerate: a
genuine, well-behaved band exists — six conditions with no degeneracy flag
at all, spread across four arena sizes from 1024 to 65536 — and it
reproduces the published v2 ecology faithfully. That is precisely what
makes the result a structural finding rather than a measurement failure:
reasonable tuning works fine, and what it produces is the same game.

Nor is it Outcome A. Nothing found here justifies changing a default or
delaying structural research; the default is already the best point tested.

**A note on what would have changed this verdict.** A region showing
several archetypes viable *simultaneously*, with search competitive through
its own mechanism and without any agent approaching 90% across dissimilar
rosters, would have been Outcome A. `a65536_b128` came closest — search
kept its mechanism there (caused 28.2% vs expansion 0.3%) — and failed on
exactly one criterion, criterion 5, because `core_seeker` swept two
rosters at 100%. That is a real near-miss and it is recorded as one, not
rounded away.

---

## 18. Phase 2 recommendation

Phase 2 is not designed or implemented here.

**Locality research remains justified, and the v3 thesis does not need
modification.** Phase 1 was capable of weakening it and did not: parameter
tuning across a 512x arena range and a 64x budget range reproduces the same
strategic structure, and the two regions where the structure genuinely
changes are worse rather than richer.

**Concrete facts Phase 2 may now assume:**

1. The strategic ecology is a function of **configured density**
   `S = (instr_per_tick x ticks) / arena_size`, not of arena size. Arena
   size is not an independent lever, and a Phase 2 design that varies it
   without holding `S` in mind will confound itself.
2. The default condition (`arena 4096`, `budget 8`, `400 ticks`) is at or
   adjacent to the optimum of the tested parameter space on the §17 rubric.
   It is the right baseline for a structural experiment; no re-tuning is
   owed first.
3. The §17 rubric's discriminating criterion is **criterion 2**, and it has
   two independently failable halves — search must win the matchup *and*
   own the capture mechanism. Criteria 1, 3 and 4 pass everywhere and are
   not useful discriminators on their own.
4. Ruleset v2 supports **one dominant strategic axis at a time**. Any
   Phase 2 mechanic should be evaluated on whether it makes two axes
   simultaneously viable, not on whether it raises a particular agent's
   win rate.
5. `CORE_SIZE = 8` is a fixed target in an arena of arbitrary size, and
   §9.1 shows this is the source of the only genuine scale effect measured.
   A locality mechanic changes exactly this relationship, which is a real
   argument for it rather than a restatement of the thesis.
6. Agents already observe `arena_size`, `tick_limit` and `action_budget`
   via `MatchContext` (§14). No Agent API change is needed to let an agent
   adapt to a changed environment.

**Unresolved experimental constraints:**

- `Weights.territory_bucket = 64` does not scale with the arena, so arena
  size silently re-weights scoring toward survival as it shrinks (§10.1).
  It is per-match configuration and fully persisted, but it is not an
  exposed evaluation variable. Any future experiment that varies arena size
  across more than about one order of magnitude should either hold
  buckets-per-arena constant or disclose the confound.
- Only final/aggregate occupancy is available without crossing the
  engine/client boundary. The *approach* to saturation is unmeasured, and
  §10 shows that is where the interesting transition lives.

**The next evidence question Phase 1 justifies** — stated, not
implemented:

> Does a bounded-locality mechanic make two strategic axes viable at the
> same time — specifically, can it hold §17 criterion 2 (search both wins
> the matchup and owns the capture mechanism) across a density range wider
> than the factor-of-four band Ruleset v2 supports, without any single
> archetype reaching 90% across dissimilar rosters?

That is the question Phase 1 could not answer by tuning, and it is the
first thing a locality prototype should be measured against.
