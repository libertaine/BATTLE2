# Bytefray v3 Phase 5A — Defensive-Event Qualification

Branch: `v3-research-phase5`, cut from `v3-research-phase4` at `27676a3`.
Status: research complete, not merged, not tagged, not published.

Phase 5A qualifies the candidate defensive-success event proposed in
`docs/V3_PHASE5_DEFENSIVE_EVENT_DESIGN_PROPOSAL.md` **before** any score
depends on it. It changes no scoring, weight, Ruleset, agent, or default,
and executes no match: every figure is reconstructed from committed Phase 1
artifacts.

Gates were declared and committed at `8bbaad6`
(`engine/src/battle_engine/data/benchmarks/v3_phase5a_defensive_event_gates.json`,
`declared_before_interpretation: true`) **before** this harness ran against
anything beyond the 324-cell sample already reported in the Phase 4
addendum. Git history shows that ordering. No gate was weakened afterwards.

---

## 1. Verdict

### **DEFENSIVE EVENT NOT QUALIFIED — SELECTIVITY PREMISE FALSIFIED AT FULL-CORPUS SCALE**

Two of six blocking gates fail, and the failure is **not** a
threshold-choice artifact. Per the predeclared decision rule, Phase 5B
does not run.

| gate | bound | measured | result |
|---|---|---|---|
| Q1 search event rate | ≤ 2% | **4.81%** | **FAIL** |
| Q2 defense event rate | ≥ 25% | 40.4% | PASS |
| Q3 threshold margin (search max single-tick loss) | ≤ 2 | **8** | **FAIL** |
| Q4 burst attribution | ≥ 90% | **100.0%** (0 coincidence of 358) | PASS |
| Q5 frequency discipline | median ≤ 3 | median 1, p95 3, max 3 | PASS (no cap needed) |
| Q6 determinism | 100% | identical digest over two passes | PASS |
| *mechanical ceiling prediction* | 0 violations | **0 violations** | **HOLDS** |

Measured over the full 594-cell default-condition group corpus (11 rosters
× 54), versus the 324-cell 6-roster sample the Phase 4 addendum reported.

---

## 2. What was confirmed: the mechanical prediction, completely

The prediction declared in the gates file held without exception:

* **Zero ceiling violations.** No tick anywhere showed a victim losing more
  than `entrant_count − 1` core cells without at least one opponent having
  written a contiguous run — exactly as the stride geometry predicts.
* **100% burst attribution (Q4).** All 358 defense events were caused by a
  single opponent taking ≥ 2 core cells in one tick. **Zero** arose from
  two sweepers coincidentally landing one cell each.
* **Only searchers ever inflict a burst.** Across the entire corpus, every
  qualifying incursion was inflicted by `core_seeker` or `core_tracker` —
  never by `claimer`, `hunter`, or either defender. The stride argument
  (every stride > `CORE_SIZE`, so a sweeper lands at most one write per
  core per tick) is empirically exact.
* **The N=2 ceiling holds too.** In the pairwise controls, `core_tracker`'s
  maximum single-tick own-core loss is **1** — precisely the predicted
  `entrant_count − 1` = 1.

So the event *is* a deterministic, replay-auditable, non-self-generable
detector of a committed contiguous assault. That part of the proposal
survives intact and is the phase's durable positive result.

---

## 3. What was falsified: that the event is *defense*-specific

The event detects **"was subjected to a committed assault and survived."**
That is not the same property as "defended," and the full corpus separates
the two.

| agent | role | appearances | events | rate | max single-tick loss |
|---|---|---:|---:|---:|---:|
| `reactive_core_defender` | defense | 270 | 119 | **44.1%** | 8 |
| `core_defender` | defense | 270 | 109 | **40.4%** | 8 |
| `hunter` | expansion | 378 | 86 | **22.8%** | 8 |
| `claimer` | expansion | 378 | 57 | **15.1%** | 8 |
| `core_tracker` | search | 270 | 13 | **4.81%** | 8 |
| `core_seeker` | search | 216 | 9 | **4.17%** | 8 |

Two distinct reasons the premise broke, both invisible in the 324-cell
sample:

**(a) Searchers burst each other.** All 22 search-victim events come from
exactly one roster — `hunter_coretracker_coreseeker`, the only roster in
which two search agents coexist. That roster was absent from the sample.
When two searchers share an arena they assault each other, so a searcher
earns "defensive" credit for surviving another searcher's burst.

| roster | search | expansion | defense |
|---|---:|---:|---:|
| `hunter_coretracker_coreseeker` | **22** | 29 | 0 |
| `coredefender_reactive_coreseeker` | 0 | 0 | 150 |
| `reactive_hunter_coreseeker` | 0 | 12 | 72 |
| `hunter_coretracker_coredefender` | 0 | 12 | 48 |
| `claimer_coretracker_coredefender` | 0 | 17 | 45 |
| `claimer_coretracker_reactive` | 0 | 16 | 43 |
| `claimer_coreseeker_hunter` | 0 | 33 | 0 |
| `claimer_coretracker_hunter` | 0 | 24 | 0 |

**(b) Expansion agents are the searchers' primary prey.** `claimer` and
`hunter` are exactly who `core_seeker`/`core_tracker` hunt, so they absorb
bursts constantly and often survive them. At 15.1% and 22.8% they are
nowhere near the ≤2% a non-defense archetype would need for the event to
mean "defense." Defense's advantage over `hunter` is only **1.8×**, not the
effectively-infinite separation the sample implied.

Rewarding this event would therefore pay expansion agents substantially —
the archetype Phase 3 and Phase 4 both found needs no help — and would
partially re-dilute the very correction Phase 5 exists to protect.

---

## 4. Why no threshold rescues it (C1)

| threshold | max search rate | min defense rate | max expansion rate | events | burst share |
|---:|---:|---:|---:|---:|---:|
| 2 | 12.04% | 49.6% | 37.0% | 879 | 92.9% |
| 3 | 6.48% | 41.9% | 29.6% | 651 | 100.0% |
| **4** | **4.81%** | **40.4%** | **22.8%** | **523** | **100.0%** |
| 5 | 4.07% | 31.1% | 14.8% | 334 | 100.0% |
| 6 | 2.22% | 22.6% | 6.9% | 220 | 100.0% |

**No threshold in 2–6 satisfies Q1 and Q2 simultaneously.** Raising it
degrades both: at 6, search is still 2.22% (> 2%) while defense has fallen
to 22.6% (< 25%). The predeclared "revise" clause permits re-deriving the
*threshold* once — but the characterization shows the threshold is not the
problem, so invoking it would be a way of avoiding the finding rather than
responding to it.

Threshold 2 is also the only value where burst attribution drops below
100% (92.9%), exactly as the mechanical prediction requires: at N=3 two
sweepers can coincidentally reach 2, but never 3.

---

## 5. Other required characterizations

**C2 — seat creation versus survival.** Both mechanisms are real and they
are separable:

| seat | defense appearances | qualifying incursions created | creation/appearance | survived given incursion |
|---|---:|---:|---:|---:|
| A | 180 | 113 | 0.628 | 80.5% |
| B | 180 | 125 | 0.694 | 92.8% |
| C | 180 | 151 | 0.839 | **100.0%** |

Creation rises with seat order (later seats are burst more often) and
survival rises to certainty at seat C — which acts last within a tick and
can therefore always reclaim before the capture check. The survival spread
is **19.5 pp**, below the predeclared 25 pp scheduler-artifact disclosure
trigger, but the monotone A→C pattern is unmistakable and is the same
last-writer-wins property Beta2 §11 already documents. Exhaustive seat
permutation would neutralize it in aggregate; it would remain a real
per-cell advantage.

**C3 — density robustness: the event is a property of action budget, not
just of the mechanic.** At `a1024_b2` (budget 2), the event **never fires
at all** — zero events for every agent, with maximum single-tick losses of
2–3. With only 2 actions per tick, a 16-write assault burst spans eight
ticks and can never concentrate ≥4 cells into one. The disclosure trigger
declared for C3 is therefore **fired**: the event's existence depends on
`instr_per_tick` being large enough for a burst to land inside a single
tick. Any Ruleset built on it would silently become inert at low action
budgets. The larger-arena conditions were not run: the primary failure is
diagnosed to roster composition and prey selection (§3), both of which are
present at every density, so density variation cannot rescue a structural
FAIL — that scoping decision is disclosed rather than presented as full
coverage.

**C4 — pairwise meaning.** The three pairwise controls contain no defense
agent, so Q2/Q4 are **not applicable** there rather than failed (the
harness prints FAIL mechanically; the corpus, not the event, is why). What
the pairwise data does establish is the N=2 ceiling: `core_tracker`'s
maximum single-tick own-core loss is 1, exactly `entrant_count − 1`, and
`claimer`/`hunter` register 25.0%/13.9% event rates as `core_tracker`'s
victims. In 1v1 the event is purely an "assault survivor" marker with no
defensive content at all.

---

## 6. Post-hoc: a successor definition that would restore selectivity

**This section is exploratory and explicitly did not influence §1's
verdict.** It was measured after the gates had already failed, and is
recorded because it determines whether a successor phase is worth
declaring at all.

The failure in §3 is that "survived a burst" is passive — it can be
satisfied by an entrant that did nothing, because the attacker simply did
not finish. Requiring the victim to have **actively reclaimed** at least
one core cell in the same tick changes what is measured, because only an
agent that writes to its *own* core can reclaim — and `claimer`, `hunter`,
`core_seeker` and `core_tracker` all sweep outward from `core_start +
CORE_SIZE` and never deliberately write their own core.

| agent | role | survived-only rate | **+ active reclaim** |
|---|---|---:|---:|
| `core_defender` | defense | 40.4% | **24.8%** |
| `reactive_core_defender` | defense | 44.1% | **21.5%** |
| `claimer` | expansion | 15.1% | **1.1%** |
| `hunter` | expansion | 22.8% | **0.0%** |
| `core_seeker` | search | 4.2% | **0.0%** |
| `core_tracker` | search | 4.8% | **0.0%** |

Selectivity becomes near-perfect: search 0.0%, expansion ≤1.1% (`claimer`'s
residual 4 cells are its stride incidentally wrapping onto its own core),
defense 21.5–24.8%. The reclaim requirement is as mechanically grounded as
the stride argument — it is a direct behavioural signature of defending
rather than of being targeted.

**But it would fail the inherited Q2 bound.** Both defenders land *below*
≥ 25%. A successor phase must therefore re-derive its bounds from the
mechanism rather than inheriting Phase 5A's — and specifically must not
lower Q2 to 20% because that is what the measurement happened to produce.
Deriving a defensible bound before measuring is the whole point of the
declaration discipline; a successor that starts by fitting its gate to this
table has learned nothing from this phase.

---

## 7. What this phase establishes

1. **The mechanical grounding is real and exact.** Stride geometry
   determines who can inflict a concentrated incursion, the ceiling
   prediction held at both N=3 and N=2 with zero violations, and burst
   attribution is 100%. This is a durable result independent of the
   verdict.
2. **"Survived an assault" is not "defended."** The distinction is
   quantitative and large: expansion agents trigger the event at 15–23%
   because they are the searchers' prey, and searchers trigger it at ~5%
   because they attack each other.
3. **A 324-cell sample drawn from 6 of 11 rosters was not
   representative.** The single roster containing two searchers carried
   100% of the counter-evidence. Sampling a corpus by roster rather than
   exhaustively is what hid it, and that is worth remembering for any
   future phase that samples.
4. **The event's existence is action-budget dependent** (C3): it cannot
   fire where a burst cannot land inside one tick.
5. **Requiring active reclaim is the promising successor**, on post-hoc
   evidence, and needs its own declaration with independently derived
   bounds.

---

## 8. Recommended next step

Stated, not implemented, and deliberately **not** framed as an automatic
continuation:

> Declare a successor qualification phase around the *active-reclaim*
> event — "lost ≥ T own core cells to a single opponent's contiguous write
> run in one tick, and reclaimed ≥ 1 of them by the entrant's own write" —
> deriving its selectivity and frequency bounds from the mechanism before
> measuring, and characterizing the action-budget dependence (C3) as a
> first-class condition of the definition rather than a footnote.

Whether that is worth doing is a judgement call, not a foregone one. Phase
5A's own result is that the simpler event does not qualify, and the
program's discipline is that a null is a complete outcome.

---

## Files changed

| file | change |
|---|---|
| `engine/src/battle_engine/data/benchmarks/v3_phase5a_defensive_event_gates.json` | **new** — gates, declared at `8bbaad6` before measurement |
| `tools/v3_phase5a_qualification.py` | **new** — qualification harness (measurement only) |
| `docs/V3_PHASE5A_DEFENSIVE_EVENT_QUALIFICATION.md` | **new** — this report |

## Validation

| check | result |
|---|---|
| Gates predate results | `8bbaad6` precedes this report's commit; `declared_before_interpretation: true` |
| Scoring / Ruleset / defaults changed | **none** |
| Matches executed | **none** — committed artifacts only |
| Corpus | 594 group cells (primary) + 594 (`a1024_b2`) + 54 pairwise |
| Q6 determinism | identical SHA-256 over 523 events across two independent passes |
| Frozen `v2-baseline` population | 9/9 |
| `ruff check` / `mypy` | clean |

Nothing merged to `main`, nothing tagged, nothing published.
