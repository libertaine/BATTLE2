# Bytefray v2.0.0-alpha.7 — Spatial/Start-Position Characterization

A controlled placement experiment, not a mechanic, scoring, or agent-design
change. Alpha.6 converted Core Seeker's capture behavior from an empirical
observation into a predictive, closed-form model of its scan/assault
geometry, and closed with an explicit open question: is the offense/
defense dynamic alpha.1–alpha.6 repeatedly measured a general property of
Vulnerable Core, or an artifact of the one placement convention
(`0`/`arena_size//3`/`2*arena_size//3`/`arena_size//2`) every one of those
alphas used? This alpha answers that question by using alpha.6's own
validated model to predict, **before running the engine**, which
deliberately chosen core start addresses should be attackable or immune,
then executing only those pre-registered placements and comparing
prediction against reality. `CORE_SIZE`, arena size, tick/instruction
budget, scoring, winner semantics, and every reference/starter agent's
source are held byte-for-byte identical to alpha.1–alpha.6. **No
production code was changed anywhere in this alpha.** The only
experimental variable is deliberately selected fixed entrant start
addresses.

Branched from the verified alpha.6 baseline, commit `ff3132f` on
`v2.0-development` (`main` unchanged at
`5593d287f95a24996bb3b105befbc625a00795db` throughout).

## 1. Verified starting state (Phase 1)

- Branch: `v2.0-development`. HEAD at start: `ff3132f`. Working tree:
  clean. `main`: `5593d287...`, unchanged. Local branch contains six
  alpha-series commits beyond the prior origin lineage; nothing pushed.
- `origin/v2.0-development` was fetched and inspected directly: it now
  points at `151866c` ("docs: expand v2.x strategic complexity
  research"), which branches from `4659654` (the pre-alpha.2 lineage) —
  confirmed via `git merge-base --is-ancestor 151866c
  origin/v2.0-development` and `git log --oneline HEAD..origin/
  v2.0-development`, which shows `151866c` as the sole commit local
  history lacks. Local `v2.0-development` does **not** contain `151866c`.
  Per the governing task's explicit instruction, this alpha did not
  merge, rebase, cherry-pick, or otherwise reconcile with it — it is
  simply a different, unrelated branch off the same shared ancestor.
- `docs/V2_0_ALPHA5_MULTI_ENTRANT_SCORING_ACTIVATION.md` and
  `docs/V2_0_ALPHA6_CORE_SEEKER_TIMING.md` were read in full before any
  new work began.
- Read directly, not inferred: `core_seeker/agent.py`, `core_defender/
  agent.py`, `reactive_core_defender/agent.py`, `claimer/agent.py`,
  `hunter/agent.py` (all reference/starter agent sources this alpha's
  matchups use), `runs/v2_0_alpha6_core_seeker_timing/predict_timing.py`
  and `trace_match.py`, `runs/v2_0_alpha5_multi_entrant_scoring/
  run_evaluation.py`, `engine/src/battle_engine/python_runtime.py`'s
  `apply_core_capture` (needed mid-alpha to explain an unexpected
  capture pathway, §16).
- Lightweight alpha.6 harness sanity check (Phase 1 item 10), run before
  any new code was written: `predict_timing.py` reproduced its own
  documented `prediction_summary.json` output exactly (seat B `k=213`/
  address `1369`/tick 80, seat C `k=719`/tick 270, etc.), and
  `trace_match.validate_against_alpha5()` reproduced **6/6** exact
  matches (4 real captures + 2 non-capture controls, tick/victim/killer
  identical) — the same 6/6 result alpha.6's own document reports,
  confirming the harness this alpha extends is still exactly reproducible
  before extending it.
- Regression baseline reproduced exactly (§29 has the full table): pytest
  **1543 total / 1537 passed / 6 skipped / 0 failed**; alpha-focused
  suites 65/65; `test_ruleset_v1_equivalence.py` 8/8; Ruff clean
  repo-wide; mypy clean for both `engine` (69 files) and `client`
  (10 files).

## 2. Objective (Phase 0)

Use alpha.6's validated closed-form scan/assault-geometry model to
predict, offline, which deliberately chosen core start addresses should
be reachable or unreachable by Core Seeker's current fixed scan schedule
within the 200-tick budget — then execute only those pre-registered
placements and compare prediction against reality, testing two nested
questions: (1) does capture opportunity move with the core exactly as the
model predicts when start addresses are deliberately relocated, holding
every other mechanic/agent/weight/budget fixed; and (2) is the offense/
defense dynamic alpha.1–alpha.6 measured a general property of Vulnerable
Core, or an artifact of the one placement convention every prior alpha
reused.

## 3. Frozen mechanics (Phase 2/27)

Held fixed throughout, confirmed unchanged: `bytefray-rules-2-alpha1`,
`CORE_SIZE=8`, arena size 4096, `instr_per_tick=8`, max ticks 200, the
scoring equation and default weights, winner semantics, capture
semantics, core ownership seeding, Agent API v1, the scheduler, and every
reference/starter agent's source (`core_seeker`, `core_defender`,
`reactive_core_defender`, `claimer`, `hunter` — all read directly in
Phase 1, none modified). No new Ruleset ID was created. Confirmed at
completion: `git diff -- engine/src client/src` is empty (§29). The only
experimental variable is entrant start position.

## 4. Alpha.6's predictive model, reused not re-derived (Phase 3 intro)

Recapped from `docs/V2_0_ALPHA6_CORE_SEEKER_TIMING.md` (full detail
there): Core Seeker's scan cursor starts at `arena_size // 3 = 1365`,
advances by a fixed stride `1565` (coprime to 4096, so a full-period
permutation), one scan every 3rd action; a lock fires via an **echo**
(the same stale `last_read` value is re-checked and matches itself on
consecutive non-scan actions, not two genuinely independent hits) within
1–2 actions of any single foreign scan hit; a completed 16-action assault
episode delays the scan-index clock by exactly 2 ticks; scan addresses
are **absolute**, independent of Core Seeker's own spawn (it never reads
`observation.pc`). This alpha's own tooling (§5) reuses
`predict_timing.py`'s `scan_sequence`/`action_index_and_tick` functions
directly (imported, not reimplemented) so nothing about the underlying
geometry is re-derived a second time, only extended to arbitrary start
addresses.

## 5. Placement classifier methodology (Phase 3)

`runs/v2_0_alpha7_spatial_characterization/classify_positions.py` extends
alpha.6's model with:

- **A. Within-core opportunities**: every scan index `k` (up to the
  533-scan zero-delay budget) whose scanned address falls inside
  `[S, S+8)` for a hypothetical core start `S`, with action index,
  no-delay tick, and budget feasibility.
- **B. Window-containment opportunities**: every `k` whose resulting
  16-cell assault window (`[addr-4, addr+12)`) fully contains `[S, S+8)`
  even when the scanned address itself lies outside the core.
- **C. Content readiness**: closed-form "first tick this agent's own
  deterministic write schedule reaches address `X`" formulas, derived
  directly from each of `claimer`/`hunter`/`core_defender`/
  `reactive_core_defender`'s source, using modular-inverse arithmetic
  (every stride used by every one of these agents is odd, hence coprime
  to the power-of-two arena size). **Important, unplanned finding from
  building this**: no closed form can exactly predict real content
  readiness in a multi-entrant match, because `core_defender` and
  `reactive_core_defender` share `expand_stride=131` (already known from
  alpha.6 §13) and 131 is coprime to 4096, so *any* stride-131
  bystander's expand sweep completes a full ~21-lap period well inside
  the 1600-action budget and **repeatedly** re-tramples every other
  entrant's core, including a defender's own signed cells, triggering
  ALERT/repair excursions no formula of the *unconditional* schedule
  alone predicts (confirmed directly: attempting to validate the formula
  against alpha.6's own directly-traced fact — reactive_core_defender@0,
  address 1369 non-zero at tick 118 — the idealized formula predicts tick
  113, and no companion agent in the available pool gives a genuinely
  undisturbed control case to close that gap exactly). This is reported
  honestly in the tooling and in this document rather than hidden: the
  closed-form readiness functions are retained only as first-order,
  idealized-schedule estimates for candidate *screening*; real content
  readiness for every placement this alpha actually selected was
  established by direct trace execution (ground truth), exactly as
  alpha.6 itself did.
- **D. Delay robustness / classification**: `max_tolerable_false_
  positive_episodes = (1600 - action_index) // 16` for a core's earliest
  opportunity, feeding a four-way classification with thresholds fixed
  *before* any candidate was evaluated, calibrated against alpha.6's own
  measured historical margin (seat B's real captures used 39–43 of an
  available 60 tolerable episodes):
  - **unreachable**: no opportunity with no-delay tick ≤ 200 at all.
  - **fragile**: an opportunity exists but tolerates fewer than 10
    complete false-positive episodes.
  - **reachable**: tolerates ≥ 10 episodes.
  - **robust**: no-delay tick ≤ 100 *and* tolerates ≥ 40 episodes
    (matching the historical floor).

This module is reusable across arbitrary candidate placements (a single
`classify(start)` entry point), per the governing task's explicit
requirement.

## 6. Candidate-space method (Phase 4)

All 4096 possible core start addresses were classified offline (`python
classify_positions.py`, `placement_candidates.json`) — explicitly
permitted analytical exploration, not a prohibited broad engine sweep (no
match was executed during this step). Classification counts across the
full arena: **2760 robust, 856 reachable, 268 unreachable, 212 fragile**.
This offline classification was the *only* basis for selecting the four
placement conditions below; no candidate was chosen or adjusted after
viewing any engine outcome (confirmed by file mtimes, §11).

## 7. Placement safety constraints (Phase 5)

For every condition: all three 8-cell cores non-overlapping, no duplicate
starts, ordinary modulo-address wraparound. Minimum pairwise separation
(cells) per condition, computed and logged before execution:

| Condition | Min pairwise separation |
|---|---:|
| control | 1365 |
| cold | 1198 |
| hot | 967 |
| mixed | 1240 |

Historical thirds spacing is 1365; every condition stays within roughly
70–100% of that, none anywhere near "trivially adjacent" (CORE_SIZE=8).
HOT's 967 (vs. 1565/1565 for the other two gaps) is a direct, disclosed
consequence of choosing the three earliest-available robust within-core
opportunities in the whole arena — an intentional-geometry case the
governing task's Phase 5 explicitly allows ("unless the condition
intentionally studies geometry"), not an oversight.

## 8. Selected placements and their analytical rationale (Phase 6/7/13)

### Condition 0 — control (historical thirds)

`A=0, B=1365, C=2730` — byte-for-byte alpha.4/alpha.5's own convention.
Classifier: A robust (window-containment, `k=254`/addr `4094`, tick 96);
B robust (raw earliest is the degenerate `k=1` scan-cursor-start hit,
address 1365 itself, tick 1 — content-impossible this early, exactly as
alpha.6 §9 already excluded; the realistic pathway is the *next*
within-core hit, `k=213`/addr `1369`/tick 80); C **fragile** (only
`k=507`/window-containment/tick 191, tolerating 4 episodes — consistent
with, and a small refinement of, alpha.6 §12's "not achievable within
budget" verdict: technically not *zero-delay-impossible*, but so far
past the historical margin as to be practically unreachable, which is
exactly what alpha.4/alpha.5/alpha.6's 0/44 seat-C-victim record shows).

### Condition 1 — COLD

`A=83, B=1281, C=2635` — each independently the nearest-to-historical
address classified **unreachable** (zero within-core and zero
window-containment opportunities within the 533-scan zero-delay budget),
subject to a ≥80-cell minimum distance from every historical thirds
address (so this condition is not simply "seat A/B/C nudged by a few
cells," which would barely move the geometry). Distances from the
nearest historical anchor: 83 cells, 84 cells, 95 cells respectively.

### Condition 2 — HOT

`A=282, B=1846, C=3411` — each has an identical-shaped **robust**
within-core opportunity at no-delay tick 40–41 (`k=105`/addr `285`;
`k=106`/addr `1850`; `k=107`/addr `3415`), each tolerating 79–80 complete
false-positive episodes (exceeding seat B's own historically-*used*
39–43, and its historically-*available* 60) — deliberately **not** the
absolute-earliest (tick-2) candidates the classifier also surfaces near
these same addresses (a degenerate case even more extreme than control
seat B's own `k=1`, essentially impossible to content-supply that early
in *any* real matchup, and too close a repeat of the "instantly-signed"
edge case) — chosen instead to be substantially earlier than historical
seat B's realistic pathway (tick 80) while still falling well after the
match's opening ticks, giving bystanders real opportunity to have
written something nearby, mirroring the *texture* of the historical
mechanism rather than a maximally artificial edge case. All three were
also required to be ≥150 cells from every historical thirds address.

### Condition 3 — MIXED (optional, included)

`A=600` (robust, window-containment, `k=257`/addr `597`/tick 97,
tolerates 51 episodes), `B=2011` (reachable, window-containment,
`k=394`/addr `2010`/tick 148, tolerates 26 episodes), `C=3251`
(unreachable). Included because it directly tests whether capture
follows the predicted vulnerability *ordering* within one convention
(governing task Phase 7's own example shape), at negligible added
execution cost given the classifier and harness were already built.

## 9. Pre-registration (Phase 8)

`runs/v2_0_alpha7_spatial_characterization/build_predictions.py` writes
`placement_predictions.json` — file mtime **1787163167** — strictly
before `run_evaluation.py` writes `raw_matches.json` — file mtime
**1787163176**, 9 seconds later — confirming the required prediction-
before-execution ordering. `analysis_summary.json` (mtime 1787163398) was
generated afterward, purely from those two files, and neither predictions
file nor raw-match file was edited after the fact; no errata were needed
(every falsifiable claim held, §17).

## 10. Selected real-agent matchups (Phase 10)

The same three trios already present in alpha.5's own 10-trio matrix, so
the control condition is directly comparable bit-for-bit against
persisted alpha.5 results, not merely similar:

- **Class A** (expansion victim + offense + defender-style bystander):
  `(claimer, core_seeker, core_defender)`.
- **Class B** (defender-as-victim matchup): `(claimer, core_seeker,
  reactive_core_defender)`.
- **Class C** (non-defender bystander control): `(claimer, hunter,
  core_seeker)` — alpha.4/alpha.6's own third-party-interference pair.

## 11. Seat/permutation and seed methodology (Phase 11/12)

3 cyclic seat rotations per class per condition (alpha.5's own
`seat_rotations`, reused byte-for-byte: `(x,y,z)→(z,x,y)→(y,z,x)`), so
across the 3 rotations of any trio containing `core_seeker`, it occupies
each of that condition's 3 addresses exactly once — separating *which
agent* sits where (rotation) from *which address* a seat has (fixed per
condition), per the governing task's explicit Phase 11 distinction. A
dedicated fourth check (`phase18_spawn_independence_check`, §14) isolates
the same question further by holding the *victim's* address fixed and
swapping only which address `core_seeker` itself starts at, removing the
rotation's confound of moving the victim too.

One seed (`seed=1`) throughout: every agent in this pool (`claimer`,
`hunter`, `core_seeker`, `core_defender`, `reactive_core_defender`) was
already confirmed fully deterministic in alpha.4's RNG audit, re-confirmed
unchanged through alpha.6; a second seed would reproduce byte-for-byte
identical results, not additional evidence.

**Total engine executions**: 4 conditions × 3 classes × 3 rotations = 36
matches, plus 2 further matches for the Phase 18 spawn-independence check
= **38 real matches**, all run through
`runs/v2_0_alpha6_core_seeker_timing/trace_match.trace_match_custom`
(reused directly, not reimplemented — already cross-validated 6/6 exact
against real `NativeMatchService` execution in alpha.6 §6). Zero
infrastructure failures; all 38 matches ran to completion or termination
without error.

## 12. Control reproduction (Phase 13)

The control condition's two captures reproduce alpha.5's own persisted
`raw_matches.json` records **exactly**:

| Trio (seated) | This alpha (tick, victim, killer) | alpha.5 (tick) |
|---|---|---:|
| `(core_defender, claimer, core_seeker)` | 168, B, C | 168 |
| `(reactive_core_defender, claimer, core_seeker)` | 166, B, C | 166 |

Both also match alpha.6 §10's own documented table exactly. Seat C never
produced a capture (0/9 control matches) and seat A's geometrically
"robust" window-containment opportunity was never actually observed
firing in any of the 3 real control matches testing it (see §15's
necessary-vs-sufficient discussion) — both match alpha.5/alpha.6's own
already-published record precisely. The harness reproduces the historical
mechanics exactly; placement interpretation proceeds on that basis.

## 13. COLD results (Phase 14)

**Zero captures across all 9 COLD matches. Zero assault episodes ever
achieved full coverage of any of the three COLD cores, in any matchup, in
any rotation** — `observed_reachable_any_match` is `False` for all three
seats. Partial (non-covering) overlaps up to 4 of 8 cells were observed
occasionally (ordinary assault windows aimed elsewhere clipping a few
cells of a COLD core in passing), but never approached full coverage —
consistent with, not a contradiction of, "unreachable" (a claim
specifically about *full* coverage/capture being geometrically
impossible, not about zero incidental overlap ever occurring). This is
the strongest possible confirmation available: the primary COLD
prediction (§9's "zero geometrically valid Core Seeker core-covering
attack opportunities within budget") held in all 9 tested matchups with
no exceptions.

## 14. HOT results (Phase 15) and the Core-Seeker spawn-independence test (Phase 18)

**All three HOT seats achieved full (8/8-cell) assault-window coverage in
at least one matchup** — `observed_reachable_any_match` is `True` for A,
B, and C, confirming the geometric prediction across the board. Four real
captures occurred:

| Tick | Victim (seat, agent) | Killer | Matchup class |
|---:|---|---|---|
| 55 | A, `core_defender` | C (`core_seeker`) | classA |
| 55 | A, `reactive_core_defender` | C (`core_seeker`) | classB |
| 61 | B, `hunter` | C (`core_seeker`) | classC |
| 61 | B, `claimer` | A (`core_seeker`, rotated) | classC |

The tick-61 pair is a direct, in-corpus confirmation of Core Seeker's
own spawn-independence: in the second row, `core_seeker` itself occupies
seat A (address 282) instead of seat C, yet still strikes address 1850
(seat B's own trigger address) at the identical tick, because — as
alpha.6 established from source and as the dedicated check below
confirms — its scan schedule is absolute, not relative to its own spawn.

**Dedicated Phase 18 check**: holding the victim (`claimer`, address 282)
fixed, `core_seeker` was run once from seat B (address 1846) and once
from seat C (address 3411), third seat filled by `core_defender` in both.
**The two runs' scanned-address sequences are byte-for-byte identical
over the first 233 scans common to both** (`first_divergence_index:
null`) — moving Core Seeker's own spawn changed *nothing* about which
addresses it scans, only wall-clock/scheduler timing (the seat-C run
additionally captured `core_defender` at seat B, tick 57; the seat-B run
produced no capture, `core_defender` surviving at seat C). This is a
direct experimental confirmation of alpha.6's source-level finding, not a
re-assertion of it.

Seat C specifically never produced an actual capture in this compact set
(full coverage was observed once, with `core_defender` surviving via
reclaim race that time) — an honest, bounded result: seat C's geometric
reachability is confirmed, but this particular 9-match set never happened
to combine seat-C occupancy by a non-defender victim with a matchup where
the assault actually landed there. Not exhaustively re-tested further,
consistent with this alpha's compact-matchup-set discipline (Phase 10).

## 15. MIXED results (Phase 7)

One real capture: tick 47, victim seat A (`hunter`, address 600, the
"robust" seat), killer seat C (`claimer`, address 3251, the "unreachable"
seat). **This capture is not attributable to Core Seeker's assault
mechanism** — Core Seeker's own traced assault window at seat A never
exceeded 4-of-8-cell overlap in this match (never full coverage), and no
seat in any of the 9 MIXED matches ever showed full Core-Seeker-mediated
coverage (`observed_reachable_any_match` is `False` for all three MIXED
seats). Reading `python_runtime.apply_core_capture` directly resolved
this: capture is defined purely by **ownership** — "an entrant is
core-captured when it owns zero cells of its own fixed core region,"
checked once per tick, kill credit going to "whichever entrant's `WRITE`
caused the final ... cell to change owner," with **no reference to Core
Seeker or any specific attacker anywhere in that rule**. This means an
ordinary blind claiming sweep can capture another entrant's core purely
through incidental stride-arithmetic overlap, entirely independent of any
deliberate search-then-assault strategy — evidently what happened here:
Core Seeker's partial assault (4 cells) plus `claimer`'s own separate
blind sweep (whose stride-101 sequence, starting at address 0 regardless
of `claimer`'s own spawn, eventually reaches into `hunter`'s core region)
jointly reduced `hunter`'s ownership to zero by tick 47, with `claimer`'s
write credited as the final flip. This is a genuine, unplanned, directly-
evidenced finding (§18) distinct from anything the geometric classifier
models (which characterizes Core Seeker's own scan/assault geometry only)
— not exhaustively re-traced cell-by-cell beyond what the summary data
confirms (partial Seeker overlap + non-Seeker-attributed kill), consistent
with this alpha's compact-execution discipline.

Seat B (`reachable`, tick-148 pathway, only 26 tolerable episodes) never
fired in this set — plausible given its later, tighter window and this
compact set's small sample, not further investigated. Seat C
(`unreachable`) never produced any capture, matching prediction.

## 16. Reachability prediction accuracy (Phase 16)

Confusion matrix (`analysis_summary.json`), one cell per seat per
condition (12 seats total):

| | Observed reachable | Observed unreachable |
|---|---:|---:|
| **Predicted unreachable** | **0** | 4 |
| **Predicted possible** (robust/reachable/fragile) | 4 | 4 |

**Zero falsifications**: no seat the classifier called geometrically
impossible ever showed a covering assault window. The four "predicted
possible, observed unreachable" cells (control A and C, mixed A and B)
are expected, not contradictions — "possible" is a necessary-not-
sufficient claim (Phase 3C/9): it requires the *specific triggering scan
address* to hold foreign content when Core Seeker reaches it, a separate,
content-timing-dependent question the geometric classifier does not (and
was never meant to) answer. Control seat A is the clean illustration: its
own `robust` classification (window-containment, tick 96) never fired in
3 real control matches, exactly reproducing alpha.6 §12's own finding
that this pathway is real but content-dependent, not a model failure.

## 17. Timing prediction accuracy (Phase 16)

For the two seats with unambiguous, exactly-reproduced real captures
(control seat B): no-delay prediction tick 80 (`k=213`); observed real
captures at tick 166/168, a delay of 86–88 ticks (43–44 false-positive
episodes) — this is not new to this alpha (alpha.6 already explained it
exactly, §11 of that document) but is reproduced here unchanged by a
harness now generalized to arbitrary placements. For HOT seat A: no-delay
prediction tick 40; observed real captures at tick 55, a delay of 15
ticks (7–8 episodes) — well within the seat's own 79–80-episode
tolerance, and a *much* smaller absolute and relative delay than
historical seat B's, consistent with HOT's much earlier no-delay
opportunity leaving less match time for false-positive episodes to
accumulate before it. For HOT seat B: no-delay prediction tick 40;
observed real captures at tick 61, a delay of 21 ticks (10–11 episodes).

## 18. False-positive delay and assault-episode volume (Phase 16)

Across all 38 matches, total assault episodes per match ranged 52–58 and
total scans 226–256 — both consistent with alpha.6's own documented
"55–58 episodes per match" and "13.0% of the arena scanned at budget
limit" findings, showing the underlying scan/assault *cadence* is
unaffected by placement (as the model predicts — placement changes
*which* episode matters, not how many occur or how densely they're spent
in false positives).

## 19. Capture-prediction summary (Phase 16)

| Condition | Geometric prediction | Behavioral (capture) result |
|---|---|---|
| control | seat B robust (realistic), A robust (fragile-in-practice), C fragile | Exactly reproduces alpha.5/6: 2/9 captures, both seat B |
| cold | all unreachable | 0/9 captures, 0/9 any coverage — exact confirmation |
| hot | all robust | 4/9 captures across seats A and B (both defender and non-defender victims); seat C reachable but not captured in this set |
| mixed | A robust, B reachable, C unreachable | 1/9 captures, at seat A — but via ownership-overlap, not Core-Seeker assault (§15) |

## 20. Bystander/content effects (Phase 17)

Confirms and extends alpha.6 §13/§17: in control, the defender-style
bystander (`core_defender`/`reactive_core_defender`, shared
`expand_stride=131`) is what supplies seat B's trigger content early
enough; `claimer`/`hunter` alone (class C, no defender bystander) never
produced a capture in control, matching alpha.4/alpha.6 exactly. Under
HOT, by contrast, class C (`claimer`, `hunter`, `core_seeker` — **no**
defender-style bystander at all) *did* produce captures (tick 61, both
rotations) — because HOT's within-core pathway only needs *some* entrant
to have written into the *victim's own* core cells that early, and at
tick ~40–60 the victims' own ordinary blind sweeps (or Core Seeker's own
absolute-address expand fallthrough writes) can already have reached
their own nearby spawn region, without requiring the specific stride-131
defender coincidence control relied on. This is a genuine, evidence-based
qualification of alpha.6 §17's "content supply operates through exactly
one address" finding: that was true for *that* address under *that*
placement; the underlying mechanism (some entrant's ordinary writes must
reach the trigger address before the delayed scan) generalizes, but which
specific bystander or behavior supplies it is placement-dependent, not
fixed to the defender-stride coincidence alone.

## 21. Defender (Core Defender / Reactive Core Defender) results (Phase 17)

**Both defenders survived every control match** (0/6 defender-seat
captures across classes A/B's 6 control matches) — exactly reproducing
alpha.1–alpha.6's unbroken record. **Both were captured under HOT** (tick
55, seat A, in both the `core_defender` and `reactive_core_defender`
variants) — the first time in this entire alpha series either defender
has lost to Core Seeker in the compact-matchup corpus tested. Both
defenders survived when occupying HOT seat C in the same class A/B
matchups (window fully covered, reclaim race won) and the dedicated Phase
18 pair additionally shows `core_defender` surviving at seat C (seeker at
B) but dying at seat B (seeker at C, tick 57) — i.e. survival still
correlates with *which* seat the defender occupies relative to the
attacker under HOT, echoing alpha.6 §14/§18's seat-order-sensitive
reclaim-race finding, but the seat-A defeat is a genuine complication:
seat A is scheduled *before* seat C every tick (the same relative
"victim-before-attacker" ordering that let `core_defender` win the
historical race at seat B), yet it still lost here. The exact mechanism
was not fully re-traced to sub-tick granularity within this alpha's
scope (that would require replaying the precise interleaving of the
16-action assault burst's tick-boundary split against the defender's own
4-action refresh cadence) — reported honestly as an open refinement,
not resolved here (§26).

## 22. Claimer/Hunter results (Phase 17)

Both were real victims in control (as in alpha.4–alpha.6) and in HOT
(tick 61, both agents individually, in different rotations) — HOT is the
first placement where `hunter` specifically has been captured anywhere in
this alpha series (alpha.4/alpha.5's own corpus recorded only `claimer`
and `core_defender`-family captures). `claimer` was additionally the
*killer* of a capture in MIXED (§15) via ordinary ownership overlap, not
assault — the first time any agent other than `core_seeker` has been
recorded as a core-capture killer in this alpha series.

## 23. Whether the historical seat-B vulnerability relocated (Phase 19)

**Yes, directly confirmed.** Under HOT, real captures occurred at *both*
seat A and seat B — never at "seat B" as a labeled position independent
of geometry, but specifically at whichever seats the model identified as
early/robust for that condition. Combined with the control condition's
own reproduction (captures only ever at seat B, exactly as alpha.1–alpha.6
found) and COLD's zero captures regardless of any agent/rotation, this is
a clean three-way demonstration that vulnerability tracks the *geometry*
Core Seeker's fixed absolute schedule happens to reach, not any special
property of "being seat B." The historical seat-B-only pattern was a
placement-convention artifact, not an inherent property of the mechanism
— exactly the central hypothesis this alpha set out to test.

## 24. Placement effect size (Phase 17/Phase 20)

| Condition | Reachable seats (observed) | Real captures | Attack-window/core-overlap events (full) |
|---|---:|---:|---:|
| control | 1 of 3 | 2 of 9 matches | seat B only |
| cold | 0 of 3 | 0 of 9 matches | none |
| hot | 3 of 3 | 4 of 9 matches | seats A, B, C |
| mixed | 0 of 3 (via Seeker) | 1 of 9 matches (via ownership overlap) | none (via Seeker) |

Moving from COLD to HOT — the two conditions differing *only* in start
address, with identical agents, weights, seed, and scheduler — moves
observed Core-Seeker-mediated reachability from 0/3 seats to 3/3 seats
and real captures from 0/9 to 4/9 matches. This is a large, clean,
placement-attributable effect, not a subtle one.

## 25. Mechanic-vs-attacker generality (Phase 20)

Kept explicitly separate, per the governing task's own instruction:

- **Vulnerable Core mechanic**: more general than alpha.1–alpha.6's own
  framing suggested, and more general even than this alpha initially
  modeled. HOT shows ordinary Agent API behavior (`READ`/`WRITE` only)
  can capture cores at multiple different, deliberately-relocated
  addresses, not just the three historical ones. §15's MIXED finding
  shows the mechanic is broader still: **capture does not require Core
  Seeker's search-then-assault strategy at all** — the engine's
  ownership-only capture rule (`apply_core_capture`, confirmed by direct
  source reading) means any sufficiently-overlapping combination of
  ordinary blind sweeps can capture a core, attributed to whichever
  write happens to be the last one. Mechanic generality is now supported
  by direct evidence at four different address sets, not one.
- **Current Core Seeker (the attacker)**: still narrow in the specific
  sense alpha.6 characterized (a fixed, content-independent absolute
  schedule, no adaptive search), but this alpha shows that narrowness is
  about *timing/schedule*, not about being permanently tied to three
  fixed addresses — its realistic target set is "wherever its own fixed
  schedule happens to fall early enough with enough delay tolerance,"
  which COLD/HOT/MIXED show moves cleanly with deliberate placement. It
  remains an attacker that cannot search adaptively for a moved target it
  wasn't geometrically going to reach anyway (COLD proves this
  conclusively).

## 26. Implications for alpha.1 offense (Phase 21)

Strengthened, not merely preserved: alpha.1's original tick-140 capture is
no longer the *only* fixed-point evidence that Vulnerable Core offense
works through ordinary API calls — HOT's tick-55/61 captures at newly
chosen addresses, predicted analytically before execution, are
independent, address-diverse confirmation of the same underlying
mechanism, materially broadening the evidentiary base beyond "one
specific historical placement happened to work."

## 27. Implications for alpha.2 defense (Phase 21)

**Materially qualified, not simply reaffirmed.** Alpha.2's "reactive
defense reliably survives Core Seeker" conclusion held in every prior
alpha's tested population (and again here, in control) — but HOT shows
this is not timing-invariant: when the attack arrives at tick 55 instead
of tick 139–168, **both** `core_defender` and `reactive_core_defender`
were captured at seat A, the first losses either has recorded against
Core Seeker anywhere in this series. Alpha.2's own reclaim-race framing
(survival is a race against the attack's *actual* timing, not a fixed
property of "reactive vs. blind" defense) is confirmed as the right
general shape — but this alpha shows the race can be lost even under the
same relative seat-scheduling advantage that won it historically,
meaning attack-timing sensitivity is real and not yet fully characterized
at the sub-tick level (§21, an open item for a future alpha, not resolved
here).

## 28. Seat-C general territorial advantage (Phase 22/34)

Not investigated, per the governing task's explicit scope exclusion — no
incidental signal about it surfaced in this alpha's compact matchup set
either (this alpha's matches are far too few and too Core-Seeker-focused
to speak to ordinary territorial win-rate patterns). Remains fully open,
carried forward exactly as alpha.5/alpha.6 left it.

## 29. Falsification/success assessment (Phase 23)

**Model strongly supported**, meeting the governing task's own "strongly
supported" bar directly: COLD positions were unreachable exactly as
predicted (0/9 captures, 0 full-coverage events, zero exceptions); HOT
positions became attackable exactly as predicted (3/3 seats reached full
coverage, captures at two different seats); Core Seeker's own start does
not alter scan geometry (directly re-confirmed by dedicated experiment,
§14, not merely re-asserted from alpha.6); the historical seat-B
vulnerability relocated with the model-selected HOT positions (§23);
timing differences are explainable through measured false-positive delay
(§17). The one genuine open discrepancy — HOT seat A's defenders losing
despite favorable seat order (§21/§27) — is a *capture-outcome*
complication, not a geometry-model falsification: Core Seeker reached and
fully covered the predicted core exactly as predicted in that match; what
is not yet fully explained is the reclaim-race sub-mechanism, which the
governing task's own Phase 9 explicitly excludes from counting against
the geometric model ("do not count a failed capture as falsifying the
geometry model when Core Seeker correctly reaches/attacks the predicted
core but defense wins the reclaim race" — the symmetric case, an
*unexpected loss* of that race, is the same kind of question, not a
geometry failure).

## 30. Benchmark-quality reassessment (Phase 26 item 36)

Upgraded from alpha.6's **B** (narrow characterization fixture) toward a
more favorable position, though not fully to a general offense
benchmark: Core Seeker's *schedule* is still fixed and non-adaptive (it
cannot search for a target COLD proves it will never reach), but this
alpha shows that schedule interacts meaningfully and predictably with
*any* deliberately chosen placement, not just three historical addresses
— making it a legitimately useful fixture for a considerably broader
class of placement experiments than previously demonstrated, while still
not a general "can this defender survive an adaptive search" benchmark.

## 31. Vulnerable Core verdict (Phase 26 item 37)

Meaningfully strengthened. Alpha.1/alpha.4/alpha.6's qualified verdict
("mechanic viability established, generality as evidence weaker than
originally framed") gains real breadth here: genuine captures now exist
at addresses chosen by an independent predictive model rather than reused
convention, and — via §15's ownership-overlap discovery — the mechanic is
now known to be triggerable through **ordinary ambient claiming activity
alone**, with no dedicated attacker required at all. This is a stronger,
more general practical viability result than any prior alpha established,
while the *current bundled Core Seeker* remains, as before, one narrow
attacker among what is now known to be a broader space of ways the
mechanic can actually fire.

## 32. Recommended alpha.8 direction (Phase 24/26 item 38)

**A — Core Seeker redesign**, but reframed by this alpha's own evidence,
not a default retread: the model built in alpha.6 and validated further
here has demonstrated it can reliably steer where a fixed-schedule
searcher becomes dangerous; the natural next step is a **placement-
agnostic, non-privileged searcher** (still ordinary `READ`/`WRITE`, no
opponent-position privilege) that does not depend on which few absolute
addresses its own fixed schedule happens to pass near — directly closing
the "Current Core Seeker" narrowness this alpha and alpha.6 both
identify, while the "Mechanic general, attacker narrow" evidence pattern
(§25) is now strong enough to justify investing in a better attacker
rather than further characterizing the existing one. Not **B** (defender
timing) or **C** (seat-C territorial geometry): both remain legitimate,
evidence-supported next questions (§21/§27, §28), but neither is as
directly implied by this alpha's own central finding as attacker
generality is. Not **D**/**E**: Vulnerable Core's practical viability is
now better-evidenced than at any prior point in the series (§31).

## 33. Unresolved questions (Phase 26 item 39)

- The exact sub-tick mechanism behind HOT seat A's defender losses
  despite favorable seat-scheduling order (§21/§27) — requires replaying
  the precise interleaving of a 16-action assault burst's tick-boundary
  split against the defender's own refresh/patrol cadence, not done here.
- Whether HOT seat C would show a real (not just geometric) capture given
  a non-defender victim specifically at that seat in a matchup where the
  assault actually lands there — this alpha's compact 9-match HOT set
  didn't happen to combine those two conditions (§14).
- The exact cell-by-cell contribution split behind the MIXED ownership-
  overlap capture (§15) — confirmed as ownership-based and non-Seeker-
  attributed from the engine's own rule and the traced partial overlap,
  but not replayed to full byte-level attribution.
- MIXED seat B's `reachable` (26-tolerable-episode) prediction never
  fired in this compact set — plausibly a small-sample effect, not
  investigated further.
- Seat C's general territorial win-rate advantage (alpha.5 §24) remains
  fully open, out of this alpha's scope by design (§28).
- Whether a genuinely placement-agnostic searcher (the recommended
  alpha.8 direction) is achievable without opponent-position privilege
  under Agent API v1's current constraints — the natural next research
  question, not attempted here.

## 34. Regression qualification (Phase 28)

No production code was changed anywhere in this alpha — confirmed by an
empty `git diff -- engine/src client/src`. No new focused tests were
required (this alpha characterizes existing, unmodified mechanics and
agent source through research tooling only, exactly as alpha.6's own
Phase 13/24 precedent).

| Check | Result |
|---|---|
| Alpha-focused suites (alpha.1/1.1/2/4/4.1) | 65 / 65 passed |
| `test_ruleset_v1_equivalence.py` | 8 / 8 passed |
| Full `pytest` | **1537 passed, 6 skipped, 2 deselected** (1543 total passed+skipped, 0 failed) — unchanged, exactly reconciled |
| Ruff (repo-wide) | clean, 0 errors |
| mypy (`engine/src/battle_engine`) | clean, 69 files |
| mypy (`client/src/battle_client`) | clean, 10 files |
| `git diff --check` | clean |
| `git diff -- engine/src client/src` | empty |

## 35. Research artifacts (Phase 25)

`runs/v2_0_alpha7_spatial_characterization/`: `classify_positions.py`
(the reusable placement classifier, §5, extending alpha.6's imported
`predict_timing.py`), `build_predictions.py` (pre-registration, §9,
writes `placement_predictions.json` before any match executes),
`run_evaluation.py` (executes only the pre-registered placements via
alpha.6's own `trace_match_custom`, §11), `analyze.py` (post-execution
comparison only, §16). Outputs: `placement_candidates.json` (all 4096
addresses classified, §6), `placement_predictions.json`,
`raw_matches.json` (38 real matches' summarized trace/capture data —
per-match assault-episode and scan-hit summaries, not raw 1600-action
dumps, to keep the artifact a reasonable size), `analysis_summary.json`.
All gitignored under the existing `runs/` precedent (confirmed via `git
check-ignore -v`); this document is the durable, committed record.

## 36. Commit and final state (Phase 29)

Committed locally on `v2.0-development` only. No merge, rebase,
cherry-pick, tag, or push performed. `origin/v2.0-development`'s
unrelated commit `151866c` was left untouched, exactly as instructed.
