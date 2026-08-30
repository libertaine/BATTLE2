# Bytefray v3 Phase 5 — Defensive-Event Design Proposal

**Status: DESIGN PROPOSAL. Nothing here is implemented.** No Ruleset,
scoring formula, weight default, agent, or schema has been changed by this
document. It exists to define a candidate mechanism precisely enough that
a later phase can test it against criteria declared *before* results
exist, and to record the evidence that motivates it and the risks that
could sink it.

Predecessors: `docs/V3_PHASE3_OFFENSE_PAYOFF_CHARACTERIZATION.md` (offense
payoff, `PROMISING`), `docs/V3_PHASE4_DEFENSE_PAYOFF_CHARACTERIZATION.md`
(defense payoff, `NOT VALIDATED` for existing levers) and that report's
dated post-Phase-4 addendum, which carries the evidence summarized in §2
and states exactly what it does and does not correct.

---

## 1. Research question

> **Can a deterministic "prevented core capture" event reward active
> defense independently of passive survival, such that the Phase 3
> offense-payoff region retains viable offense while Phase 4's defense
> deficit is corrected without creating turtling, farming, or a new
> dominant strategy?**

This is a two-part question and Phase 5 is deliberately split along that
seam: whether the *event* can be defined and measured honestly (5A), and
only then whether *rewarding* it produces coexistence (5B).

---

## 2. Why this candidate, and what the evidence actually is

Phase 4 established the deficit precisely: defense pays a confirmed
~25–26% unconditional action-opportunity tax, and the benefit it
generates — denying an attacker a capture worth `w_kill` = 1,600 points at
Phase 3's payoff — accrues to nobody. The scoring model has an event for
"successfully attacked" and none for "successfully resisted."

Post-Phase-4 replay reconstruction (324 of 594 committed group cells at
the default condition; ownership replayed from `memory_diffs` from tick 0,
core anchors from tick-0 `pc`/`region`) tested three candidate event
shapes:

| candidate event | selective for defense? |
|---|---|
| core damaged, then recovered | **No** — 190/216 `core_defender` but also 147/162 `core_tracker`, 106/162 `claimer`; ~6–7 cycles/match. Measures absorbed incidental scratch. |
| reached the brink (≤1 cell) and survived | **No, inverted** — `core_seeker` 16.7%, `core_tracker` 11.1%, `core_defender` 6.0%. Would pay search most. |
| **lost ≥4 own core cells in one tick, survived the capture check** | **Yes** — see below |

Single-tick incursion concentration separates committed assault from
incidental scratch, because a blind sweeper's stride crosses a core at
most once per pass while a dedicated assault burst writes many
consecutive core cells inside one tick:

| agent | appearances | events (≥4-cell single-tick incursion, survived) | rate | max single-tick loss observed |
|---|---:|---:|---:|---:|
| `reactive_core_defender` | 162 | 109 | **67.3%** | 8 |
| `core_defender` | 162 | 97 | **59.9%** | 8 |
| `claimer` | 162 | 7 | 4.3% | 8 |
| `hunter` | 162 | 3 | 1.9% | 8 |
| `core_seeker` | 162 | 0 | **0.0%** | **2** |
| `core_tracker` | 162 | 0 | **0.0%** | **2** |

Across 324 search-agent appearances neither searcher ever lost ≥3 core
cells in a single tick. The candidate threshold of 4 therefore sits two
cells above the highest value ever observed for the archetype that must
not earn this event.

The most compelling cases are the `peak = 8` survivals (`core_defender` 7,
`reactive_core_defender` 12): an attacker took **all eight** core cells,
and the defender — scheduled later in the same tick — reclaimed at least
one before that tick's capture check. Those are literal prevented
captures, not a proxy inferred from a survival correlate.

### Why the separation exists (not merely that it does)

The threshold is not a curve fitted to the sample; there is a mechanical
reason concentrated incursions are the signature of a committed attack.
Every sweeping agent in the frozen population advances by a fixed stride
(Phase 1 §14.2: `claimer` 101, `core_defender`/`reactive_core_defender`
131, `core_seeker` 149, `core_tracker` 157, `hunter` dense 173) and gets
`instr_per_tick = 8` actions per tick. Eight writes at a stride ≥ 101 span
≥ 707 addresses, so **an 8-cell core window can contain at most one of
them.** No sweeper, however dense, can take two cells of the same core in
one tick.

Concentrated incursions therefore require an agent that deliberately
writes a *contiguous run* — and only the two search agents do:
`core_seeker` commits `ASSAULT_WINDOW = 16` consecutive writes on lock-on,
and `core_tracker` an `ASSAULT_ACTIONS`-action burst across the same
window. (`hunter`'s current implementation is a two-phase sparse→dense
*sweep* at stride 173, not the burst-on-contact scanner an earlier version
was; its own docstring records that change.)

This makes the candidate event mean something specific and defensible:
**survived a deliberate contiguous assault burst.** It also sets a real
limitation — the event's frequency is a function of *attacker* design, not
of defense quality, which is exactly the exposure that risk #4
(sub-threshold pacing, §6) describes.

---

## 3. Candidate event definition

> **Defensive success event**: an entrant loses at least **4** of its own
> core cells to opponent writes within a single tick, and still owns at
> least **1** core cell at that tick's capture check.

Four properties, each verified against current code rather than asserted:

1. **Deterministic, and already computed.** `apply_core_capture` already
   evaluates `owned_now = sum(1 for a in addrs if vm.writer[a] ==
   state.agent_id)` every tick for every living entrant, and
   `_snapshot_core_owners` already captures the pre-tick ownership tuple.
   Both halves of the event exist as engine state today.
2. **Replay-auditable by a third party.** The full per-tick ownership
   trajectory reconstructs from `memory_diffs` (`address`/`length`/
   `owner`) from tick 0, with core anchors from tick-0 `pc`/`region`
   (documented as `[start, start]` for Python entrants). This was
   performed against committed artifacts to produce §2, so auditability is
   demonstrated, not projected. **Known artifact nuance:** `start` is
   absent from persisted entrant metadata even when non-zero —
   `docs/COMPATIBILITY.md`'s statement about `start` refers to
   `canonical_match_id`'s hash payload, not the persisted artifact — so
   anchors must come from tick-0 `pc`/`region`.
3. **Structurally impossible to self-generate.** `vm._wr8` is the single
   ownership mutation path and always sets `writer[i] = owner`; there is
   no unclaim operation, and `maintain_core_beacons` explicitly restores
   *content* without ever restoring *ownership* ("no ownership is ever
   restored, `vm.ownership_counts` never changes"). An entrant therefore
   cannot lower its own core-owned count by any action available to it —
   writing to its own core *claims* the cell. The event's precondition
   always requires an opponent's write.
4. **Not passive survival.** An entrant never attacked never fires it.
   `core_seeker` survives 147/162 appearances and earns **zero** events.
   This is the property `weights.alive` structurally cannot have (Phase 4
   §3.3, alpha.5 §15).

### The threshold is a candidate, not a decision

The value 4 was **discovered from the corpus in §2** and must not be
promoted to a Ruleset constant on that basis. Phase 5 keeps the discovery
step and the test step separate:

```text
event-definition evidence  (Phase 4 addendum, §2 above)
        ↓
candidate threshold = 4    (discovered, provisional)
        ↓
robustness / false-positive characterization   (Phase 5A)
        ↓
predeclared scoring experiment                 (Phase 5B)
```

**The threshold must never be re-tuned against 5B's win-rate results.** If
5A shows 4 is wrong, 5A fixes it and re-declares before 5B runs; if 5B's
ecology results are disappointing, that is a finding about the mechanism,
never a licence to move the threshold.

---

## 4. Phase 5A — Defensive-event qualification (no scoring change)

Purpose: establish that the event is selective, robust, honest, and
reproducible **before** any score depends on it. 5A changes no scoring
formula, no Ruleset, no weight, and no default; it is pure measurement
over committed artifacts plus, where needed, real re-execution under the
existing shipped Ruleset.

Predeclared 5A gates:

* **Q1 — Selectivity at scale.** Across the **full 594-cell** default-condition
  group corpus (not the 324-cell sample), search-agent event rate ≤ 2% of
  appearances and defense-agent event rate ≥ 25%.
* **Q2 — Threshold margin.** The maximum single-tick own-core loss suffered
  by any search agent stays ≤ 2 (i.e. threshold − 2) across the full
  corpus. If a searcher ever reaches 3, the margin is one cell and the
  threshold must be re-derived and re-declared.
* **Q3 — Causal attribution and false positives.** Every event is traced to
  the opponent write(s) that caused it and classified as (a) a contiguous
  assault burst, (b) multiple independent sweepers coinciding on one core
  in one tick, or (c) anything else. §2's stride analysis predicts (a)
  should dominate and (b) should be rare-but-possible in 3-entrant play;
  (c) should be empty. Predeclared bound: ≥ 90% of defense events
  classified (a). A materially lower figure means the event measures
  coincidence rather than repelled aggression, which is a much weaker
  claim than this proposal makes and must be reported as such rather than
  absorbed.
* **Q4 — Frequency discipline.** Median events per event-bearing match ≤ 3,
  so the reward cannot be farmed by volume. (The rejected "any recovery"
  variant ran ~6–7/match; this bound is what distinguishes them.)
* **Q5 — Seat effects.** Per-seat event rates reported. Because the event
  can be satisfied by same-tick reclaim, it has a genuine scheduler-order
  component; 5A must show it is neutralized by the existing exhaustive
  seat-permutation methodology (Beta2 §11's disclosed property), not that
  it is absent.
* **Q6 — Determinism/reproducibility.** 100% of events reproduce bit-exactly
  from committed replays across independent reconstructions.
* **Q7 — Density robustness.** Re-measured at Phase 1's other density
  conditions. If the threshold only separates at `a4096_b8`, it is a
  property of one condition rather than of the mechanic, and that must be
  disclosed before 5B.
* **Q8 — Pairwise behaviour.** Measured on the 3 pairwise controls, where a
  capture ends the match outright: the event's meaning in 1v1 must be
  stated explicitly rather than assumed to transfer from group play.

**5A outcome rule**: all of Q1–Q8 satisfied → proceed to 5B with the
threshold frozen as declared. Any failure → either re-derive and re-declare
the definition within 5A, or report that no selective definition survives
qualification and stop. **Stopping at 5A with a null result is a valid,
publishable outcome**, exactly as Phase 2's and Phase 4's nulls were.

---

## 5. Phase 5B — Experimental scoring test (only if 5A passes)

Purpose: determine whether *rewarding* the qualified event produces
coexistence. This is the first phase in the v3 program that would change a
scoring formula, and it must be scoped accordingly.

### 5B.1 Compatibility cost, stated up front

Adding a fourth scoring event is a scoring-formula change. `docs/RULES.md`'s
own bump policy lists "a scoring formula change (survival, territory, or
kill)" as requiring a `BYTEFRAY_RULESET_ID` bump, so 5B **must** run under
a new, explicitly experimental Ruleset identity — following Phase 2's
`bytefray-rules-3-alpha1` precedent exactly: registered under its own key,
never aliased, absent from every product CLI's `--ruleset` choices,
constructed directly by the research driver. `bytefray-rules-2` semantics
must remain byte-identical, proven by execution, not argued.

Expected axes: **new Ruleset identity — yes.** Agent API — no (the event is
engine-side; agents receive nothing new). Result/replay schema — no (the
event is derivable from data already persisted; a new scoring *term* rides
in the existing `weights` dict and `score` map). Shipped defaults — **no
change proposed by 5B under any outcome.**

### 5B.2 Reward magnitude: derived, not tuned

Phase 4 §3.2 measured the denial benefit as exactly `w_kill` = 1,600
points — the score the attacker forgoes. That measurement, not a search
for a flattering result, sets the ladder. Predeclare exactly:

| condition | `w_defense` | rationale |
|---|---:|---|
| D0 | 0 | control — the event is measured and recorded but pays nothing, isolating the scoring change from the measurement change |
| D1 | 400 | ¼ of the denied value |
| D2 | 800 | ½ of the denied value |
| D3 | 1600 | full parity with what the defender denied the attacker |

`w_kill` stays fixed at 1600 (Phase 3's K2) and `w_alive`/`w_territory` at
their shipped defaults throughout, so 5B varies exactly one new term. **Do
not add values outside this ladder**; if the ladder brackets an interior
region, at most two interpolation points strictly inside the demonstrated
bracket may be added, and only under the same MODIFY discipline Phase 3
used.

D0 is load-bearing: it separates "the ecology changed because the event is
rewarded" from "the ecology changed because the experimental Ruleset
differs from `bytefray-rules-2` for some unintended reason." D0 must
reproduce Phase 3's K2 result exactly.

### 5B.3 Predeclared gates

Carried forward verbatim from Phase 3/4 so verdicts stay comparable:

* **E1** defense aggregate win share ≥ 15% (Phase 3 G5 / Phase 4 D1 — the
  deficit this phase exists to correct).
* **E2** search/offense aggregate win share ≥ 25% (Phase 3 G3 — offense must
  not be undone).
* **E3** killer-win-rate in capture matches in [45%, 65%] (Phase 3 G4).
* **E4** §17 criterion 5 passes — no archetype ≥ 90% across ≥ 2 dissimilar
  rosters.
* **E5** §17 criterion 2 passes, both halves.
* **E6** pairwise negative controls unchanged across all `w_defense` values.
* **E7** the full §17 rubric scores 5/5, using Phase 1's own functions
  unmodified.
* **E8 — turtle control.** A deliberately passive/immobile probe agent
  (analogous to Phase 2's `local_camper`) must **not** become competitive
  at any tested `w_defense`. This gate is what makes "no turtling
  exploit" a measured claim rather than an argument.
* **E9 — collusion red-team.** A declared adversarial probe pair (an
  attacker that repeatedly inflicts exactly-threshold incursions without
  finishing, paired with a repairing defender) must not out-earn ordinary
  play. If it does, a per-match event cap is required and must be
  declared before re-running.

E8's and E9's probes live **outside** the frozen `v2-baseline` population,
contribute nothing to §17 scoring, and are reported separately — Phase 3
Ruling 4's precedent — but unlike Phase 3's optional beacon probe they are
**mandatory and gating for the exploit criteria specifically.**

**GO** requires E1–E9. **MODIFY** if an interior region appears with one
gate failing at a boundary. **ABANDON** if offense/defense remain in
structural opposition, if turtling or farming emerges at every rewarding
value, or if the improvement is an artifact of the new Ruleset identity
rather than the reward (D0 diagnoses this).

### 5B.4 Explicitly out of scope for 5B

Changing any shipped default; promoting a stable `bytefray-rules-3`; core
geometry, `CORE_SIZE`, capture thresholds, hold-duration capture, locality,
movement, ATTACK, Agent API v2; modifying the frozen benchmark population;
re-tuning arena/action budget or the Phase 3 kill weight. A successful 5B
authorizes a *later* product/balance decision, never itself.

---

## 6. The four identified risks, and how Phase 5 addresses each

| risk | mechanism | where addressed |
|---|---|---|
| **Collusion farming** | A partner inflicts threshold incursions without finishing; the defender repairs and farms. Bounded by the attacker always being 4 writes from a 1,600-point kill it forgoes, and by exhaustive seat permutation punishing a sacrificing attacker's own win rate — but not closed. | 5A Q4 (frequency), 5B E9 (red-team probe), per-match cap if E9 fails |
| **Mandatory experimental Ruleset identity** | A fourth scoring event is a scoring-formula change per `docs/RULES.md`'s bump policy. | 5B.1 — new experimental identity, Phase 2 precedent, `bytefray-rules-2` proven byte-identical |
| **Seat-order dependence** | Same-tick reclaim requires acting after the attacker within the tick; Beta2 §11 documents seat order as a real disclosed property. | 5A Q5 — report per-seat rates and show permutation neutralizes them; disclose rather than eliminate |
| **Sub-threshold attack pacing** | An attacker can deny the reward by taking ≤3 cells/tick. This is a *feature* if it forces a real tradeoff (slower assault = more repair windows) and a *defect* if it makes the event trivially avoidable. | 5A Q3 (what actually causes events) and 5B — measure whether a paced attacker beats a committed one; report either way |

A fifth, noted for completeness: the event is **contest-contingent** — a
defender in a roster with no searcher earns nothing, because nothing
attacks it. Phase 1/3 already showed capture-caused ≈ 0 in search-free
rosters, so defense would remain uncompensated there. Whether that is
correct (defense has no job when unthreatened) or a residual gap is an
interpretive question 5B should state, not silently resolve.

---

## 7. What would make this proposal wrong

Recorded now, so it cannot be rationalized later:

* A searcher reaching a 3-cell single-tick loss anywhere in the full
  corpus would cut the threshold margin to one cell and undermine the
  clean separation §2 rests on.
* If Q3 shows a large share of defense events arise from two independent
  sweepers coinciding on one core in one tick rather than from a
  contiguous assault burst, the event measures bad luck rather than
  repelled aggression — a different and much weaker claim than this
  proposal makes, and one that would also make the event farmable by
  seating rather than by playing well.
* If the stride argument in §2 fails to hold for some agent (a stride
  smaller than `CORE_SIZE`, or an agent that writes contiguously without
  being a searcher), the "only committed attackers can trigger it"
  property is not general — it is a property of this particular frozen
  population, and any Ruleset built on it would be over-fitted to these
  nine agents.
* If the separation holds only at `a4096_b8` (Q7), the threshold is a
  property of one density condition, not of the mechanic.
* If D0 does not reproduce Phase 3's K2 exactly, the experimental Ruleset
  differs from `bytefray-rules-2` in some unintended way and no 5B result
  can be attributed to the reward.
* If E8's turtle probe becomes competitive, the mechanism has created
  precisely the exploit it was designed to avoid, and the correct outcome
  is ABANDON — not a search for a `w_defense` where the turtle happens to
  lose.

---

## 8. Recommended entry conditions for Phase 5A

1. Branch from the completed Phase 4 lineage; do not merge, tag, or publish.
2. Verify the frozen `v2-baseline` population 9/9 before measuring.
3. Reuse `tools/v3_phase1_ecology_rubric.py` and
   `tools/v3_phase1_arena_action_grid.py` functions unmodified for anything
   they already compute, per the precedent Phases 2–4 all followed.
4. Commit the 5A gate definitions **before** the full-corpus measurement
   runs, with `declared_before_interpretation: true`, exactly as Phase 2
   and Phase 3 committed theirs — so git history shows the ordering.
5. Treat a 5A null as a complete, reportable result. The event either
   qualifies or it does not; there is no obligation to reach 5B.
