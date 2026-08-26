# Bytefray v3 Phase 4 — Defense Payoff Characterization

Branch: `v3-research-phase4`, cut from `v3-research-phase3` at `a941571`
immediately after the Phase 3 report. Status: research complete, not
merged, not tagged, not published.

Phase 3 found that raising `weights.kill` makes decisive offense
simultaneously competitive with expansion, but only in a region where
defense's win share falls below its own predeclared 15% floor (G5) — and
recommended, as its next research question, testing "whether a modest,
independently-justified compensating adjustment for defense specifically
... could hold G5 at the same weight that already satisfies G3/G4."

Phase 4 answers that question directly: it measures defense's economic
cost and strategic benefit first, then tests the one existing scoring
lever that measurement identifies as the sole remaining candidate,
holding Phase 3's accepted offense payoff (`w_kill = 1600`, Phase 3's K2)
fixed throughout. No Ruleset, Agent API, schema, or gameplay-mechanic
change was made or is proposed by this phase.

---

## 1. Initial state

| ref | value |
|---|---|
| starting branch | `v3-research-phase3` |
| HEAD | `a941571bcd0ca457143740118cb481482aa2ec84` |
| `v3-research-phase0/1/2/3` | unchanged |
| `main` / `origin/main` | `1093393` — identical |
| `v2.0.0` tag | unchanged |
| working tree | clean |
| frozen `v2-baseline` population | 9/9 |
| Phase 3's K2 corpus | present under `runs/research_v3_phase3/rescored/K2` |

Work proceeded on `v3-research-phase4`, cut from `a941571`.

---

## 2. Research question

> Fixing the offense payoff at Phase 3's accepted `w_kill = 1600`: what is
> defense's actual economic cost and strategic benefit, and can an
> existing scoring lever — other than `weights.kill`, held fixed — be
> independently justified to restore defense's win share above Phase 3's
> G5 floor (15%) without eroding the offense-coexistence gates (G3, G4)
> or the untouched §17 rubric?

A null result — no existing lever can do this — is a valid, informative
outcome, exactly as a null result was valid in Phase 2 and Phase 3.

---

## 3. Defense's measured economics (before any lever was chosen)

### 3.1 Economic cost: a fixed action-opportunity tax, confirmed empirically

Both defense archetypes' own source commits them to `REFRESH_EVERY = 4` —
nominally one action in four spent on non-claiming defensive upkeep
instead of expansion. This was confirmed against real committed replay
and result data for a representative undisturbed match
(`coredefender_reactive_coreseeker`, seed 1, spread layout), using the
method appropriate to each agent's own action shape:

| agent | measurement method | realized defensive-action fraction |
|---|---|---:|
| `core_defender` | address-classified `WRITE`s (every action is a WRITE; classifying by whether the address falls in its own 8-cell core separates the two) | **25.3%** (813/3208) |
| `reactive_core_defender` | `cpu_total - mem_writes` (its only non-`WRITE` action is a defensive `READ`, so this residual *is* its defensive cost exactly) | **26.4%** (844/3200) |

Both match the nominal 25% design cadence closely; the small excess is
`reactive_core_defender`'s one-time 8-action `SIGN` phase plus incidental
`ALERT`-phase repairs in this specific sampled match. **This tax is paid
unconditionally** (`core_defender`) or **essentially unconditionally**
(`reactive_core_defender`'s patrol `READ` fires on the same fixed
schedule regardless of whether anyone is attacking) — a defender in an
uncontested match pays the identical cost as one that successfully
repels five assaults.

### 3.2 Strategic benefit: denial, quantified at the fixed payoff

The benefit defense provides is not reflected in its own score at all —
it is the score an *attacker* forgoes. By construction of the scoring
formula (`score_kill` is the only term keyed to a capture event), a
successfully-repelled attack denies the attacker **exactly `w_kill` =
1,600 points** it would otherwise have earned. This is the mirror image
of Phase 3's own opportunity-cost framing, not a separate empirical
measurement: it follows directly from the formula once `w_kill` is fixed.

In the committed K0 corpus, the two defense archetypes appear in 540
roster-cells; **496 (91.9%) survive** (i.e., successfully deny an
attacker this benefit) and 44 (8.1%) are captured.

### 3.3 Structural sanity check: `weights.alive` is dead, reconfirmed directly

Alpha.5 §15 (`docs/V2_0_ALPHA5_MULTI_ENTRANT_SCORING_ACTIVATION.md`) proved
in closed form that whenever 2+ entrants are alive at match resolution,
their `alive_ticks` must be identical, because `resolve_termination` only
forces early termination at 0 or 1 entrants alive. That proof is
independent of `w_kill`'s value and of population — but it was
reconfirmed directly against this phase's own K2 corpus rather than
merely cited:

```text
cells with 2+ survivors checked: 494
mismatches:                        0
proof holds:                     true
```

**`weights.alive` therefore cannot differentiate any 2+-survivor
comparison in this corpus, at this or any `w_kill`.** It is analytically
and empirically disqualified as a candidate lever before any sweep of it
was run — mirroring Alpha.3's own precedent of using a closed-form proof
to avoid a wasted empirical sweep.

### 3.4 Is defense actually territory-poor? Measured, not assumed

The only remaining `Weights` field is `territory` (and its paired
`territory_bucket`, held fixed — bucket changes the scoring formula's
resolution more invasively than a weight does, and Phase 1/2 both flagged
it as a confound magnet). Whether raising it could help defense depends
on whether defense is actually territory-disadvantaged. Measured directly
at K2:

| agent | mean territory % |
|---|---:|
| claimer | 31.6% |
| core_seeker | 29.6% |
| core_defender | 29.5% |
| reactive_core_defender | 28.2% |
| hunter | 27.7% |
| core_tracker | 24.8% |

**Defense's territory deficit against the leading archetype is only
2–3 percentage points** — both defenders hold more territory than
`core_tracker` and close to `hunter`. Defense's problem is not that it
lacks territory; it is that the kill bonus (now 1,600 points) has become
large enough, relative to everyone's broadly similar territory totals, to
decide most captured matches regardless of territory standing.

---

## 4. Candidate lever selection

Given §3: `weights.kill` is fixed (the accepted offense payoff under
test); `weights.alive` is structurally and empirically dead;
`weights.territory` is the only remaining field, and its justification is
weak on the evidence (§3.4) — but not zero, since defense does hold
real, substantial territory. **`weights.territory` was selected as the
one lever to test**, precisely because it is the only candidate the
measurement does not immediately rule out, not because the measurement
predicted success.

---

## 5. Execution-invariance result

The identical architectural argument from Phase 3 §4 item 9 applies:
`scoring.ScoringPolicy.score_territory` only ever writes into the score
map, exactly like `score_kill`/`score_alive` — never read back into
gameplay. Confirmed empirically (not merely re-cited) on a smaller,
representative sample (6 real cells: two defense-containing group
rosters spanning a capture and a non-capture cell each, one negative
control, two pairwise controls), at `w_kill = 1600` fixed and
`w_territory ∈ {1, 5, 20}`:

```text
cells tested: 6
trajectory-invariant: 6/6
winner changed: 2/6 (both group capture cells; zero pairwise)
```

**Gameplay trajectory does not change with `w_territory` either.** Only
final scoring and winner resolution do.

---

## 6. Weight-plumbing implementation

Phase 4 needed real executions only for the validation sample above (via
`agent_test.test_agent`/`test_agents` directly, exactly as Phase 3's own
execution-invariance tool already did) — not a full product-facing
evaluation matrix — so the change is smaller than Phase 3's: no
`agent_evaluation.py`/`EvaluationRequest`/CLI change was needed.
`agent_test.py` gained `alive_weight`/`territory_weight` alongside the
existing `kill_weight`, factored through one shared `_resolved_weights`
helper: each of the three independently defaults to `None` (`Config()`'s
own shipped default, byte-identical to omission), and any subset
combines. 11 new tests (`test_v3_phase4_defense_payoff.py`) cover the
helper directly and end-to-end pairwise/group execution.

---

## 7. Offline-rescoring generalization

Phase 3's single-term shortcut (`new_score = old_score + kills * delta`)
only worked because exactly one weight moved. Phase 4 varies
`weights.territory` while holding `weights.kill` fixed, so the general
alpha.3 decomposition is needed:

```text
score = alive_ticks * w_alive + kills * w_kill + bucket_sum * w_territory
```

`bucket_sum` was recovered by algebraic inversion against each entrant's
*original* K0 (shipped-default) `score`/`alive_ticks`/`kills` — alpha.3's
own method, validated with its own two checks:

```text
entrants checked:  1,782  (594 committed K0 cells x 3 entrants)
integrality/reconstruction failures: 0
```

Cross-checked against Phase 3's own already-validated K2 corpus at
`(w_alive=1, w_kill=1600, w_territory=1)`: **54/54 exact agreement**
(score and winner) for a representative roster — the general rescorer
inherits Phase 3's own real-execution validation transitively at that
point, and §5 confirms the new axis (`w_territory`) independently.

---

## 8. Predeclared gates

Declared before any territory-weight result was inspected, directly
carrying forward Phase 3's own thresholds (D1 is literally Phase 3's G5;
D2/D3 are Phase 3's G3/G4, restated as constraints that must not be
undone):

* **D1** (primary target): defense aggregate win share ≥ 15%.
* **D2**: search/offense aggregate win share stays ≥ 25%.
* **D3**: killer-win-rate in capture matches stays in [45%, 65%].
* **D4**: §17 criterion 5 (no universal solution) still passes.
* **D6**: §17 criterion 2 (both halves) still passes.
* **D5**: pairwise negative control — no pairwise outcome changes with
  `w_territory`, for any positive value (alpha.3 §8's sign-invariance
  argument: a non-forced 1v1 winner depends only on the *sign* of the
  territory difference, invariant to which positive weight scales it —
  re-derived here for a lever alpha.3 never itself swept, and expected to
  hold for the identical algebraic reason).

**Verdict rule**: a "successful weight" must satisfy D1–D6
simultaneously. Failing that, whether an interior region exists that
comes close, and how wide it is, determines MODIFY vs ABANDON.

**Predeclared values**: `T0 = 1.0` (Phase 3's own K2, reused directly —
the reference), `T1 = 5.0` (moderate correction), `T2 = 20.0`
(large/saturating), spanning the same "dead zone / interior / saturation"
ladder logic Phase 3 used for `w_kill`.

---

## 9. Corpus methodology and control reproduction

Identical environment, population, and 11-roster/3-pair corpus as Phase
3. T0 reuses Phase 3's K2 rescored artifacts directly (zero new
artifacts); T1/T2 (and, after §10's interpolation, nine further points)
were built by exact rescoring of the same committed Phase 1
default-condition corpus, reusing `tools/v3_phase1_arena_action_grid.py`'s
`analyze_roster`/`analyze_pair` unmodified.

**T0 reproduces Phase 3's K2 exactly**: diffed field-by-field, 0
mismatches across all 11 rosters and 3 pairwise pairs (win_rate,
capture_caused, candidate_win_rate).

---

## 10. Results: raising `weights.territory` reverts the offense payoff faster than it helps defense

The predeclared three-point sweep (T0/T1/T2) already showed T1 and T2
**identical** to each other and to Phase 1/3's own pre-payoff-correction
K0/K1 numbers:

| condition | `w_territory` | D1 defend_win | D2 search_win | D3 killer_win_rate | §17 |
|---|---:|---:|---:|---:|---:|
| T0 (=K2) | 1.0 | 9.8% FAIL | 40.5% PASS | 63.6% PASS | 5/5 |
| T1 | 5.0 | 22.4% PASS | 24.1% FAIL | 23.5% FAIL | 5/5 |
| T2 | 20.0 | 22.4% PASS | 24.1% FAIL | 23.5% FAIL | 5/5 |

T1/T2 "fix" D1 only by **completely reverting** the ecology to its
pre-Phase-3 shape — search's win share and killer conversion both land
almost exactly on Phase 3's own K0/K1 dead-zone numbers. This is not
targeted compensation for defense; it is a wholesale undo of Phase 3's
finding, because raising `weights.territory` dilutes the (now large)
kill bonus's relative decisiveness for *everyone*, not specifically for
defense's benefit.

Because this did not resemble Phase 3's own kill-weight dose-response
(a smooth curve with a genuine, if narrow, interior region), eight further
points were interpolated to characterize the actual shape between T0 and
T1 before concluding — considerably more than Phase 3's own two-point
MODIFY allowance, justified here because the shape itself (a possible
near-miss crossing, not just a boundary) was the open question:

| `w_territory` | D1 defend_win | D2 search_win | D3 killer_win_rate | all three? |
|---:|---:|---:|---:|:-:|
| 1.00 | 9.8% FAIL | 40.5% PASS | 63.6% PASS | no |
| 1.50 | 11.1% FAIL | 36.6% PASS | 54.8% PASS | no |
| 1.60 | 14.8% FAIL (−0.2pp) | 32.5% PASS | 45.6% PASS | no |
| **1.62** | **15.2% PASS** | 32.1% PASS | **44.7% FAIL (−0.3pp)** | no |
| 1.65 | 15.7% PASS | 31.5% PASS | 43.3% FAIL | no |
| 1.70 | 16.5% PASS | 30.7% PASS | 41.5% FAIL | no |
| 1.75 | 17.2% PASS | 29.8% PASS | 39.6% FAIL | no |
| 2.00 | 19.4% PASS | 27.4% PASS | 33.6% FAIL | no |
| 3.00 | 22.2% PASS | 24.3% FAIL | 24.0% FAIL | no |
| 5.00 | 22.4% PASS | 24.1% FAIL | 23.5% FAIL | no |
| 20.00 | 22.4% PASS | 24.1% FAIL | 23.5% FAIL | no |

**D1 and D3 cross within 0.02 of each other** (D1 fails by 0.2pp at
`w_territory=1.60` and D3 fails by 0.3pp at `w_territory=1.62`) — a gap
narrower than this corpus's own sampling granularity (a 594-cell corpus
resolves rates to roughly ±1.85pp per roster before aggregation). **No
tested or interpolatable value satisfies D1, D2, and D3 together, and if
an exact crossing exists at all, it is a knife's edge far too narrow to
constitute a usable, defensible operating point** — nothing like Phase
3's own ~800-unit-wide interior region for `w_kill`.

§17's rubric (criteria 1–5) passed at every one of the 11 tested
territory weights; pairwise negative controls (D5) held at every one of
them too — **0 changes across all 3 pairs × 10 non-reference weights**,
confirming alpha.3's sign-invariance argument generalizes to this axis
exactly as predicted.

---

## 11. Compatibility and identity

Nothing was bumped. `weights.territory`/`weights.alive` were already
identity-bearing (the same `EffectiveConditions.weights`/
`canonical_match_id` reproducibility surfaces Phase 3 established for
`weights.kill`); omission remains byte-identical to the shipped default
(proven by the 11 new tests, §6); no Ruleset, Agent API, or schema axis
was touched.

---

## 12. Validation and performance

| check | result |
|---|---|
| Full test suite | 2,190 passed, 14 skipped, 0 failed (Phase 3's own final baseline was 2,179 passed — delta is exactly the 11 new tests) |
| `ruff check .` | All checks passed |
| `mypy engine/src/battle_engine` | Success, 81 source files |
| `mypy client/src/battle_client` | Success, 12 source files |
| Frozen `v2-baseline` population | 9/9 |
| T0 reproduces Phase 3's K2 | exact, 0 mismatches |
| Execution-invariance (territory axis) | 6/6 real-executed sampled cells trajectory-invariant |
| Rescoring cross-check vs. Phase 3's validated K2 | 54/54 exact agreement |
| Pairwise negative control | 0/30 changed across the full interpolation sweep |
| True executions | 6 (validation sample, x3 territory weights = 18 match runs) |
| Rescored cells | 11 territory-weight conditions x 594 group cells (T0 reused, 10 rescored) + pairwise `outcome` recomputation |
| Artifact discipline | no replay copied or regenerated for any rescored condition |

---

## 13. Phase 4 verdict

### **DEFENSE PAYOFF HYPOTHESIS NOT VALIDATED — NO EXISTING SCORING LEVER INDEPENDENTLY JUSTIFIED**

1. **Defense's economics are real and precisely characterized**: a
   confirmed ~25–26% unconditional action-opportunity tax, and a
   denial benefit worth exactly `w_kill` (1,600 points) per repelled
   attack that is real but entirely uncredited to the defender's own
   score — the model has no scoring event for "successfully resisted an
   attack," only for "successfully attacked."
2. **`weights.alive` is disqualified analytically and empirically**
   (§3.3): it cannot differentiate any 2+-survivor comparison, in this or
   any `w_kill` regime, by the same closed-form mechanism alpha.5
   established.
3. **`weights.territory` is disqualified empirically, having been given
   a fair and thorough test**: defense is not meaningfully
   territory-poor (§3.4), and raising the weight "helps" it only by
   diluting the offense payoff back toward its pre-Phase-3 state — D1
   and D3 (defense viability and killer conversion) are in near-perfect
   structural opposition under this lever, crossing within a gap
   (< 0.02 in weight-space) far too narrow to be a defensible, robust
   operating point, unlike Phase 3's own genuine (if imperfect) interior
   region for `w_kill`.
4. **No existing `Weights` field, other than `kill` (already used),
   can independently and robustly restore defense's viability while
   preserving Phase 3's offense-payoff finding.** This is a structural
   conclusion, of the same character as alpha.3's own "no weights,
   within this model, can do the job" finding for `reactive_core_defender`
   in 1v1 — now established for N=3 at Phase 3's accepted payoff.

**Why not MODIFY**: MODIFY presumes a real, characterizable interior
region worth narrowing further. Nine interpolation points already
characterized the full shape between T0 and T1; the result is a
near-coincident crossing far narrower than the corpus's own resolution,
not a genuine bracket. Further interpolation would not change this
conclusion, only chase decimal places.

**Why not ABANDON-by-default (i.e., why this took a real experiment)**:
the conclusion rests on evidence, not on the analytical prediction alone
— the analytical case for `weights.territory` was genuinely uncertain
before measurement (§3.4 found defense's territory deficit small enough
that a positive result was plausible), and the 11-point sweep is what
actually closed the question.

---

## 14. Recommended next research question

Stated, not implemented: defense's uncredited benefit (§3.2) is a
*denial* event with no scoring hook in the current model — structurally
analogous to how, before Phase 3, a *kill* event was scored but
underpaid. Unlike Phase 3's fix, which only needed to reweight an
*existing* event, giving defense a comparable lever would need a new
scoring event ("successfully resisted decisive damage to one's own
core") that the current three-term model has no slot for — which is a
new scoring formula, out of every phase's scope so far, not a
weight-reweighting question. Whether such a mechanism is worth
designing, and whether it can be added without the same kind of
compatibility cost Phase 2's locality mechanic required, is the next
question this phase justifies asking — explicitly not answered here.

---

## Files changed

| file | change |
|---|---|
| `engine/src/battle_engine/agent_test.py` | `alive_weight`/`territory_weight` alongside `kill_weight`, via shared `_resolved_weights` |
| `engine/tests/test_v3_phase4_defense_payoff.py` | **new** — 11 tests |
| `tools/v3_phase4_rescore.py` | **new** — general 3-term offline rescoring (bucket_sum decomposition) |
| `tools/v3_phase4_economics.py` | **new** — cost/benefit/alive-tie/territory-share measurement |
| `tools/v3_phase4_execution_invariance.py` | **new** — territory-axis trajectory-invariance check |
| `tools/v3_phase4_corpus.py` | **new** — territory-weight corpus builder + Phase 1 tooling reuse |
| `docs/V3_PHASE4_DEFENSE_PAYOFF_CHARACTERIZATION.md` | **new** — this report |

## Commits

| SHA | message |
|---|---|
| `6b3d8be` | feat(evaluation): generalize agent_test weight overrides to alive/territory |
| *(this report)* | docs(v3): record the Phase 4 defense payoff characterization findings |

Nothing merged to `main`, nothing tagged, nothing published.
