# Bytefray v2.0.0-alpha.9 — Defense Robustness Under Generalized Offense

A defense-characterization alpha, not a mechanic, scoring, agent-redesign, or
engine change. Alpha.8 (docs/V2_0_ALPHA8_PLACEMENT_AGNOSTIC_OFFENSE.md) built
`core_tracker`, a placement-agnostic, non-privileged offense benchmark, and
found — as an unplanned, genuinely new result — Reactive Core Defender's
first-ever **control-condition** loss anywhere in this research series
(§23/§37 of that document), directly contradicting the informal prior
narrative "Reactive Defender survives Core Seeker." This alpha asks the
question alpha.8 explicitly left open: **is Reactive Core Defender's
historical advantage over blind Core Defender a general property, or was it
an artifact of Core Seeker's own narrow, late, delay-dominated attack
timing?** `CORE_SIZE`, arena size, tick/instruction budget, scoring, winner
semantics, the scheduler, and every reference/starter agent's source
(`core_seeker`, `core_tracker`, `core_defender`, `reactive_core_defender`,
`claimer`, `hunter`) are held byte-for-byte identical throughout. **No
production engine/client code was changed anywhere in this alpha**, and
**neither defender was redesigned** (governing task Phase 24's explicit
exclusion).

Branched from the verified alpha.8 baseline, commit `a17fb8f` on
`v2.0-development` (`main` unchanged at
`5593d287f95a24996bb3b105befbc625a00795db` throughout).

## 1. Verified starting state (Phase 1)

- Branch: `v2.0-development`. HEAD at start: `a17fb8f`. Working tree: clean.
  `main`: `5593d287...`, unchanged.
- `origin/v2.0-development` was fetched and inspected directly
  (`git merge-base --is-ancestor 151866c HEAD` exits non-zero, i.e. "not an
  ancestor"): it still points at unrelated `151866c` ("docs: expand v2.x
  strategic complexity research"), branching from `4659654` (the pre-alpha.2
  lineage). Per the governing task's explicit instruction, this alpha did
  not merge, rebase, cherry-pick, reset onto, or otherwise reconcile with
  it anywhere.
- `docs/V2_0_ALPHA2_REACTIVE_DEFENSE.md`,
  `docs/V2_0_ALPHA6_CORE_SEEKER_TIMING.md`,
  `docs/V2_0_ALPHA7_SPATIAL_CHARACTERIZATION.md`, and
  `docs/V2_0_ALPHA8_PLACEMENT_AGNOSTIC_OFFENSE.md` were read in full before
  any new work began.
- Read directly, not inferred: `core_seeker/agent.py`, `core_tracker/
  agent.py`, `core_defender/agent.py`, `reactive_core_defender/agent.py`
  (all four, in full, including every docstring's own design rationale);
  `python_runtime.py`'s `apply_core_capture`/`_attribute_core_capture`/
  `_snapshot_core_owners`/`seed_core_ownership`/`core_addresses` (confirming
  the exact capture-check timing and attribution mechanism this alpha's own
  harness reuses); `runs/v2_0_alpha6_core_seeker_timing/trace_match.py`
  (the production-code-reusing trace harness pattern this alpha extends);
  `runs/v2_0_alpha7_spatial_characterization/run_evaluation.py` (`core_cells`
  /`extract_assault_episodes`/`overlap_report`/`seat_rotations`, reused
  directly, not retyped); `runs/v2_0_alpha8_placement_agnostic_offense/
  run_evaluation_v8.py`/`held_out_placements.py` (the additive-extension
  precedent this alpha's own harness follows, and the exact held-out
  addresses reused byte-for-byte).
- Regression baseline, measured directly on this machine before any alpha.9
  file existed (§32 has the full reconciliation): the alpha-focused suites
  (`test_v2_alpha1_reference_agents.py`, `test_v2_alpha2_reactive_
  defender.py`, `test_v2_alpha4_multi_entrant.py`,
  `test_v2_alpha4_1_winner_semantics.py`, `test_v2_alpha8_core_tracker.py`,
  `test_ruleset_v2_alpha1.py`) plus `test_ruleset_v1_equivalence.py` all
  passed unchanged (92/92). Full suite: **1562 collected (1556 passed, 6
  skipped, 2 deselected), 0 failed** — a further +2 drift from the governing
  task's own documented alpha.8 baseline (1560/1554/6), on the identical,
  unmodified `a17fb8f` HEAD with a clean tree. This is the same class of
  small, session-to-session collection drift alpha.7/alpha.8 already found
  and explicitly declined to chase further (§32).

## 2. Alpha.9 objective (Phase 0)

> Does Bytefray's existing information-driven defense retain a meaningful
> survival advantage across generalized attack timing and placement, and
> does that advantage cost enough expansion to create a genuine strategic
> tradeoff?

Characterize, not redesign, `core_defender`'s and `reactive_core_defender`'s
robustness against both `core_seeker` (the historical, fixed-schedule
control) and `core_tracker` (alpha.8's placement-agnostic benchmark), across
varied placement and scheduler order, using a trace harness that observes
both attacker and defender simultaneously.

## 3. Frozen mechanics (Phase 2)

Held fixed throughout, confirmed unchanged: `bytefray-rules-2-alpha1`,
`CORE_SIZE=8`, core ownership seeding, the capture rule and its attribution
mechanism, arena size 4096, `instr_per_tick=8`, the 200-tick budget,
scoring and its weights, survivor winner eligibility, the scheduler, Agent
API v1, the Python runtime, and all four reference agents' source. No new
Ruleset ID was created. Confirmed at completion (§32):
`git diff -- engine/src client/src` is empty.

## 4. Entering findings, recapped from alpha.8 (§1 above has the full detail)

Core capture has now been demonstrated by two structurally different,
non-privileged attackers, across six placement conditions, including one
(COLD) the historical attacker can never reach at all. Search quality and
kill power are experimentally separable: `core_tracker` achieves
full-core-covering assaults far more broadly than `core_seeker` but has a
*lower* total capture count in alpha.8's own compact corpus. Reactive Core
Defender lost in the control condition for the first time in this entire
series (§23/§31 of alpha.8), against `core_tracker` specifically — the
single fact motivating this alpha.

## 5. The defense hypothesis (Phase 3)

Stated precisely, per the governing task's own framing, and falsifiable:

> Reactive observation-driven repair should provide a survival advantage
> over blind periodic refresh across a wider distribution of legitimate
> attack timings, but that advantage may disappear when attack onset,
> burst timing, or scheduler ordering falls outside its repair latency
> envelope.

Not assumed to be true. §19's matched comparison tests it directly.

## 6. Core Defender action economics (Phase 4)

Read directly from `core_defender/agent.py` (unchanged): unconditional
`REFRESH_EVERY=4` cadence — exactly 1 of every 4 actions rewrites one of
its 8 core cells in fixed round-robin order (`defend_index`), regardless of
whether that cell has been touched. It never issues a `READ` — it has no
way to know whether its core is intact. A full defend cycle (touching all 8
cells once) takes 32 actions = 4 ticks. Measured directly across this
alpha's own 16-match primary matrix (§21): **372.2 core-directed writes and
1109.3 expansion writes per match on average**, 0 reads — every "defensive"
action is a `WRITE`, whether or not it was needed.

## 7. Reactive Core Defender action economics (Phase 4)

Read directly from `reactive_core_defender/agent.py` (unchanged): a
one-time 8-action SIGN pass, then steady-state PATROL — 1 of every 4
actions is a `READ` at a rotating core-cell cursor, compared against this
agent's own record of what it last wrote there; the other 3 expand. A
mismatch triggers immediate ALERT: the damaged cell is repaired the *same*
action the mismatch is confirmed (`_begin_repair` fires synchronously
inside the `act()` call that consumes the mismatched `READ` result — zero
elapsed actions between detection and the first repair write), then every
other core cell is checked in turn before returning to PATROL. Measured
directly (§21): **18.4 core-directed writes, 387.9 reads, and 1075.1
expansion writes per match on average** — roughly 20x fewer core-directed
writes than Core Defender, paid for with a steady stream of reads instead.
**1.2% of patrol reads ever find a mismatch** (67 of 5,738 across the 16
reactive-defender primary-matrix matches, §22) — the other 98.8% are the
real, measurable cost of maintaining vigilance, not a wasted action in the
sense of an incorrect repair (this design never writes a repair without a
genuine mismatch, confirmed directly from source and reconfirmed by this
alpha's own trace data — zero false-positive *repairs* were observed).

## 8. Attack timing buckets (Phase 5)

Pre-defined before any result was examined, per the governing task's own
suggested partition (the 200-tick budget in fifths):

| Bucket | Ticks |
|---|---|
| very_early | 1–40 |
| early | 41–80 |
| mid | 81–120 |
| late | 121–160 |
| very_late | 161–200 |

## 9. Trace harness methodology (Phase 7)

`runs/v2_0_alpha9_defense_robustness/trace_match_v9.py`: a small, disclosed,
additive extension of alpha.6's own `_run_traced` (not an edit to that
prior alpha's committed script — the same precedent alpha.8 already
established for the identical reason: alpha.6's own `REFERENCE_NAMES` set
predates agents/questions this alpha needs). Reuses the same real,
unmodified production pieces directly: `battle_engine.python_runtime.VM`/
`apply_action`/`seed_core_ownership`/`apply_core_capture`/
`PythonEntrantState`, `battle_engine.agent_api`'s `Observation`/
`MatchContext`/`load_python_agent`, `battle_engine.ruleset_policy.
resolve_ruleset_policy`, `battle_engine.scoring.ScoringPolicy`,
`battle_engine.statistics.StatisticsCollector`. Extended with exactly three
things, all ordinary attribute access or read-only inspection of state the
engine already maintains, none of it a production or agent-source change:

1. **Dual (or arbitrary-set) tracing** — every prior harness in this series
   traces exactly one named entrant slot; this alpha needs the attacker's
   *and* the defender's own state from the same single execution, to see
   how they interleave in real time. `trace_slots` accepts any set of
   slots; each traced action is tagged by slot in one combined,
   real-execution-order list.
2. **A generic, agent-agnostic state snapshot** (`_snapshot_agent_state`) —
   the union of every instrument-relevant public attribute across all four
   agents this alpha studies (attacker fields: `mode`/`scan_cursor`/
   `assault_cursor`/`assault_remaining`/...; defender fields:
   `defend_index`/`phase`/`patrol_cursor`/`alert_queue`/...), read via
   ordinary `getattr(inst, attr, None)` — a missing attribute on a given
   agent simply reads back `None`.
3. **Per-sub-tick ownership snapshots** — governing task Phase 7's explicit
   request for "core ownership count after each entrant's action block":
   after *every* entrant's own 8-action quota completes (not merely once
   per full tick), every living entrant's own core-ownership *count*
   (0..8) is recorded, keyed by `(tick, acting_agent)`. This is what makes
   §16's exact scheduler-order mechanism directly observable rather than
   inferred.

Entrant **scheduling order** is controlled purely by the order of the
`entrants` list passed in — confirmed directly from `scheduler.
run_sequential_quota`/`ruleset_policy.RulesetPolicy.run_scheduler`
(alpha.6 Sec 2: outer loop over entrants in list order, inner loop over the
full quota, no per-slot interleaving) and made an explicit, independently
variable parameter here (governing task Phase 12's own "research-only
construction that separates start address from entrant ordering, without
changing engine semantics").

**Cross-validation (Phase 6, required before any new interpretation):**
before building the new matrix, this harness was checked against six
independent, already-documented results — two more than alpha.6's own 6/6
bar, all exact:

| Case | Expected | Reproduced |
|---|---|---|
| Control: `core_defender`@B survives `core_seeker`@C | no capture | ✅ |
| Legacy: `reactive_core_defender`@0 survives `core_seeker`@2048 | no capture (0/10 historically) | ✅ |
| Legacy: `core_defender`@0 captured by `core_seeker`@2048 | tick 140 | ✅ exact |
| HOT: `core_defender`@A captured by `core_seeker`@C | tick 55 | ✅ exact |
| Control: `reactive_core_defender`@A captured by `core_tracker`@C | tick 189 | ✅ exact |
| COLD (2-entrant): `core_defender`@A captured by `core_tracker`@C | tick 27 | ✅ exact |

All six reproduce tick, victim, and killer exactly. `run_defense_matrix.py`
asserts all six before proceeding to any new match.

## 10. Robustness metrics (Phase 8)

Reported separately, never as one composite score: **survival**
(captured/not), **damage resistance** (minimum core ownership reached,
cells lost at the worst point), **recovery** (repair latency, whether
ownership returns to 8/8), **attack tolerance** (assault episodes launched
against the defender's core), and **opportunity cost** (reads,
core-directed writes, expansion writes, score).

## 11. Placements (Phase 9)

Reused byte-for-byte from their originating alphas, never retyped
independently: historical **control** (`0, 1365, 2730`, alpha.1/4/5),
alpha.7 **HOT** (`282, 1846, 3411`), alpha.7 **COLD** (`83, 1281, 2635`),
and alpha.8's held-out **`heldout_even_eighths`** (`512, 1536, 2560`).

## 12. Attackers and defenders (Phase 10/11)

Attackers: `core_seeker` (historical control), `core_tracker`
(placement-agnostic benchmark) — both byte-for-byte unchanged. Defenders:
`core_defender` (blind), `reactive_core_defender` (reactive) — both
byte-for-byte unchanged. `claimer`/`hunter` used as bystander/undefended
control, never as primary attack benchmarks.

## 13. Historical control reproductions (Phase 6)

Detailed in §9 — all six exact, zero drift. Proceeding to new
interpretation is warranted per the governing task's own gate.

## 14. Experiment matrix design and size (Phase 20)

Exactly the governing task's own suggested shape,
2 attackers × 2 defenders × 4 placements × 2 scheduler orders = **32**
primary matched cases, using one fixed seating convention per condition so
that scheduler order is the *only* variable that changes between the two
runs of an otherwise-identical cell (defender always at the condition's
`B` address, attacker always at `C`, `claimer` bystander always at `A`):

- `defender_before_attacker`: entrant list `[defender@B, claimer@A,
  attacker@C]` (defender's action block executes first every tick).
- `attacker_before_defender`: entrant list `[attacker@C, claimer@A,
  defender@B]` (attacker's action block executes first every tick).

Plus: **6** historical reproductions (§9), **8** undefended controls
(`hunter` at the defender's own address, no defender present, one per
condition × attacker — §17), and **8** three-way validation matches (4 with
a `hunter` bystander instead of `claimer`, 4 with both attackers present
simultaneously alongside one defender — §24). **Total: 54 matches**, all
run through the harness above, **zero infrastructure failures**, wall time
2.50s.

## 15. Attack-timing distribution observed (Phase 13/22)

Across the 32-cell primary matrix, exactly **4 defender captures**
occurred (§19), at only two distinct ticks: **57** (HOT, `core_seeker`,
×2 — both defender types) and **106** (COLD, `core_tracker`, ×2 — both
defender types). Bucketed: 0 very_early, 2 early (tick 57), 2 mid (tick
106), 0 late, 0 very_late. This is a small sample (n=4) — reported as
exactly what it is, not extrapolated into a general timing-frequency claim.
Every one of these four captures occurred under `defender_before_attacker`
scheduling; zero occurred under `attacker_before_defender` (§16).

## 16. Scheduler-order experiment: exact mechanism (Phase 12)

**The single most important finding in this alpha.** Holding placement,
agents, and addresses exactly fixed and varying only entrant list order:
**4 of 16 matched (condition, attacker, defender) cells (25%) flip their
survival outcome purely from scheduler order**, and in every one of those
four, `defender_before_attacker` → captured, `attacker_before_defender` →
survived:

| Condition | Attacker | Defender | defender-first | attacker-first |
|---|---|---|---|---|
| hot | core_seeker | core_defender | captured @57 | survives (min 0, reclaimed) |
| hot | core_seeker | reactive_core_defender | captured @57 | survives (min 0, reclaimed) |
| cold | core_tracker | core_defender | captured @106 | survives (min 0, reclaimed) |
| cold | core_tracker | reactive_core_defender | captured @106 | survives (min 2) |

The exact action-level mechanism, read directly from the per-sub-tick
ownership trace (§24 has the full narrative for the COLD case):
`apply_core_capture` checks ownership **once per tick, after every
entrant's action block for that tick has run**. If the entrant scheduled
*last* in a tick is the one whose own action would restore a core cell,
that restoration happens *before* the tick-end check, so a core that
touched zero ownership **between** two entrants' action blocks earlier the
same tick survives. If the entrant scheduled last is the *attacker*, its
final zeroing write stands at the tick-end check with the defender given no
further chance to react until the next tick — but by then the game already
recorded a kill. Concretely, in the COLD/`core_tracker`/`core_defender`
case: `defender_before_attacker` — the defender's own action block for
tick 106 completes at 6/8 owned, then `core_tracker`'s block that same tick
takes the last two cells to 0/8, and the tick ends there → captured.
`attacker_before_defender` — `core_tracker`'s block for tick 106 runs
*first*; ownership *does* touch 0 mid-tick in the raw sub-tick trace, but
`core_defender`'s own action block for that same tick (which still runs,
since capture is a once-per-tick check, not applied mid-tick) reclaims
before the tick ends → survives. **This directly, mechanistically resolves
alpha.7's own left-open question** (§21/§27/§33 of that document): HOT seat
A's defender loss "despite favorable seat order" was not a mysterious
exception — seat A being scheduled *before* seat C (the historical
alpha.7 default ordering) is exactly this alpha's `defender_before_attacker`
case, which this alpha now shows is the *unsafe* order whenever the
attack's completing write lands in the same tick the defender has already
finished acting.

**This result must not be over-generalized as "acting first is always
unsafe."** In the *other* 12 of 16 matched cells (75%), including the
historical control condition (both attackers, both defenders,
`defender_before_attacker` — the exact convention under which
alpha.1–alpha.8 already documented seat B surviving `core_seeker`
repeatedly), order made **no** difference to the win/loss outcome at all.
Alpha.6 §14's own control-seat-B mechanism (the defender's per-tick refresh
completing before the attacker's same-tick assault actions, across
*multiple* ticks of one assault episode) is reproduced unchanged here and
is a *different* alignment than the single-tick race that decided the four
HOT/COLD flips. The correct general lesson, consistent with the governing
task's own Phase 15 hope: **survival is better explained by which entrant's
action block is scheduled last relative to the specific tick the critical
zeroing write lands in, than by a fixed "first is safe/unsafe" rule** —
order is a real, quantified input to that alignment, not a standalone
predictor.

## 17. Undefended controls: does the attack ever reach a meaningful target? (Phase 11)

`hunter` placed at the defender's own seat/address, no defender present:

| Condition | Attacker | `hunter` captured | Defended capture rate (4 occurrences) |
|---|---|---|---:|
| control | core_seeker | no | 0/4 |
| control | core_tracker | no | 0/4 |
| hot | core_seeker | **yes** (tick 61) | 2/4 |
| hot | core_tracker | no | 0/4 |
| cold | core_seeker | no | 0/4 |
| cold | core_tracker | no | 2/4 |
| heldout_even_eighths | core_seeker | no | 0/4 |
| heldout_even_eighths | core_tracker | no | 0/4 |

The one case where an undefended victim *and* a defended one both fall to
the same attacker/condition (HOT/`core_seeker`) confirms the attack reaches
a genuinely dangerous target there regardless of who occupies it —
consistent with alpha.7's own HOT finding that `hunter` specifically is a
real victim at this placement. Everywhere else, the defended captures (COLD/
`core_tracker`) occur at a placement where the *undefended* control
survives — direct evidence that in the COLD/`core_tracker` cells, capture is
not simply "the attack was going to land regardless of defense" (the
governing task's own Phase 11 distinction): it is specifically the
scheduler-order race of §16 that determines the outcome, not a target that
was doomed either way.

## 18. Three-way validation (Phase 21)

**`hunter` bystander instead of `claimer`** (control/HOT, both defenders,
`core_tracker` attacker, 4 matches): zero captures in all four — the
bystander's own identity did not change the primary matrix's own
control/HOT `core_tracker` outcome (both already showed no defender capture
in §19's matched table).

**Both attackers present simultaneously** (`core_seeker`@A,
`core_tracker`@C, one defender@B, control/HOT, both defenders, 4 matches):
control shows zero captures for either defender. **HOT shows the defender
captured in both cases, at tick 55, with `core_seeker` (seat A) credited as
killer** — `core_tracker` (seat C) did not get the kill even though it is
also present and actively assaulting. This is the same tick-55 HOT
mechanism §9/§16 already characterize for `core_seeker` alone (its schedule
is absolute and spawn-independent, so occupying seat A instead of seat C
does not change which addresses it reaches — alpha.7 §14 already
established this directly).

## 19. Survival results and the matched Reactive-vs-blind comparison (Phase 17/23)

| Defender | Occurrences | Captured | Survived | Survival rate |
|---|---:|---:|---:|---:|
| `core_defender` | 16 | 2 | 14 | 87.5% |
| `reactive_core_defender` | 16 | 2 | 14 | **87.5%** |

**Identical.** Broken down by attacker, both defenders show the identical
1/8 capture rate against `core_seeker` and 1/8 against `core_tracker`.
Critically, this is not merely the same *aggregate* rate — matching cell by
cell (same condition, same attacker, same scheduler order), **all 16 of 16
matched cells show the identical capture/survival outcome for both
defender types** (`reactive_advantage: "same_outcome"` in every case, §21
of the raw analysis). Both defenders die in exactly the same four
(condition, attacker, order) cells, at the identical tick (57 or 106) each
time.

**This directly answers the governing task's own secondary question: in
this matched, placement-agnostic, order-varied design, Reactive Core
Defender does *not* retain a measurable win/loss survival advantage over
blind Core Defender.** The margin in the two near-miss cells that *didn't*
flip to capture is mixed, not consistently in Reactive's favor: in
COLD/`core_tracker`/`attacker_before_defender`, Reactive's minimum
ownership (2) was better than blind's (0, reclaimed from the brink); in
`heldout_even_eighths`/`core_seeker`/`attacker_before_defender`, it was
*worse* (2 vs. blind's 4). Reactive's real, measured advantage remains
exactly what alpha.2 originally found and this alpha reconfirms under a far
wider timing/placement distribution: **detection and repair latency are
genuinely fast** (§7 — same-action repair once a mismatch is found,
0–4-tick detection-to-repair in every matched cell where detection
occurred before capture) — but that speed only matters when the scheduler
order gives the defender a chance to use it before the tick-end capture
check. When it does not (§16's four flip cells), reaction speed of *any*
magnitude cannot help, and blind and reactive defense fail identically.

## 20. Opportunity cost (Phase 8/17/26)

| Defender | Avg core-directed writes/match | Avg expand writes/match | Avg reads/match | Avg score (control, `core_seeker`) |
|---|---:|---:|---:|---:|
| `core_defender` | 372.2 | 1109.3 | 0.0 | 1580–1585 |
| `reactive_core_defender` | 18.4 | 1075.1 | 387.9 | 1520–1546 |

Total action budget spent is nearly identical between the two designs
(≈1481 actions/match each), but shaped very differently — Core Defender
spends its "defense" budget almost entirely on `WRITE`s (which claim
territory as a side effect even when redundant), Reactive spends most of
it on `READ`s (which claim nothing). This reproduces, under a far wider
placement/timing distribution than alpha.2's original 2-cell comparison,
the same small, consistent score gap alpha.2 found: Reactive trails blind
by roughly 40–60 points (2–4%) in every matched cell where neither is
captured — the efficiency cost of content-based inspection over
unconditional rewriting is real, small, and stable across this alpha's
much broader corpus.

## 21. False-positive defensive work (Phase 18)

Across the 16 `reactive_core_defender` primary-matrix matches: **5,738
total patrol reads, of which 67 (1.2%) found a genuine mismatch** and
5,663 (98.8%) found the core cell exactly as expected. Every one of the 67
detected mismatches triggered exactly one repair write — **zero
false-positive *repairs*** were observed (this design never writes to a
cell it has no read-evidence against, confirmed directly from source and
reconfirmed by this alpha's own trace data). One representative mismatch
(HOT, `core_seeker` attacker, tick 21) was traced to source: the mismatched
cell (`core_start+6`) was written by an entrant *other* than the attacker
under study before `core_seeker`'s own first core-directed write (tick 57)
— i.e., the defender correctly detected and repaired genuine incidental
foreign content from ordinary ambient activity, not a bug and not a wasted
action, but a reminder that "first detection" is not always "detection of
the attacker being characterized." The dominant cost of reactive defense is
therefore accurately described as **information cost** (98.8% of patrol
reads are, correctly, no-ops), not wasted or incorrect action.

## 22. Detection and repair latency (Phase 13/28/29)

For every matched cell where the attacker's own core-directed write
happened before the defender was captured, Reactive Core Defender's
detection-to-repair latency was **0–4 ticks** (repair itself is always the
*same action* as detection once a mismatch is confirmed — §7). Core
Defender has no detection concept at all; its own "repair after attack"
latency in the response-timing data is really "ticks until the next
already-scheduled unconditional refresh happens to land on the damaged
cell," which is frequently 0 by coincidence of its own fixed 4-action
cadence, not a reaction. This distinction — genuine low-latency response
vs. incidentally-fast blind refresh — is real and measured, but §19
already shows it does not translate into a different win/loss outcome once
scheduler order is adverse.

## 23. Old Core Seeker vs. Core Tracker as attackers (Phase 19)

Both attackers achieved exactly 1 capture out of 8 occurrences against
each defender type in the primary matrix — perfectly symmetric at this
grain. But *where* they succeed differs exactly as alpha.7/alpha.8 already
characterized: `core_seeker` captures at HOT (tick 57, its fixed schedule's
early within-core opportunity, alpha.7 §9), `core_tracker` captures at
COLD (tick 106, the one placement `core_seeker`'s fixed schedule can never
reach at all, alpha.7 §13/alpha.8 §16). Neither attacker is dominant over
the other in this matrix; each has a distinct, geometry-determined
success case, reconfirming alpha.8's own "search quality and kill power
are separable, and neither attacker is universally superior" finding
(alpha.8 §27) under a defense-focused lens.

## 24. Representative cell-level traces (Phase 16)

**Capture** — COLD, `core_tracker`, `core_defender`,
`defender_before_attacker`:

```text
tick 105 core_tracker: 8 -> 6
tick 106 core_defender: 6 -> 6   (defender's own block: no reclaim this tick)
tick 106 core_tracker: 6 -> 0 CAPTURE
```

**Survival, identical placement/agents, only order flipped** —
`attacker_before_defender`:

```text
tick 105 core_tracker: 8 -> 8   (no damage yet)
tick 106 core_tracker: 8 -> 8   (defender's own tick-106 block already
                                  reclaims before this block runs)
```

(ownership never leaves 8/8 in this specific narrated window in the
attacker-first order, because `core_defender`'s own scheduled refresh for
the affected cell happens to already precede the attacker's tick-106 block
in this specific run — the general mechanism, §16, is that whichever
action block is *last* in the decisive tick determines the tick-end
reading, not that damage never occurs under this order.)

**HOT seat-A loss, `core_seeker`, `core_defender`, resolving alpha.7's own
open question**:

```text
tick 54 core_seeker: 8 -> 6
tick 55 core_defender: 6 -> 6   (defender's own block: no reclaim this tick)
tick 55 core_seeker: 6 -> 0 CAPTURE
```

Same shape as the COLD capture above — `core_defender`'s own tick-55
action block does not touch the two already-lost cells (its fixed
round-robin defend_index was elsewhere in its cycle at that moment),
`core_seeker`'s block runs last and finishes the capture.

## 25. Incidental capture and kill attribution (Phase 22)

Two incidental captures were observed in the primary matrix, both of the
`claimer` **bystander** (seat A, not the defender under study), both by
`core_tracker` at the control condition: `defender_before_attacker` with
`core_defender` present — tick 191; with `reactive_core_defender` present —
tick 181. Both are address-determined, not agent-identity-determined:
address `0` (seat A's address in the control convention) is exactly the
same address alpha.8 §23 found `core_tracker` captures `reactive_core_
defender` at, in *that* alpha's own seating (where a defender occupied
seat A instead of `claimer`). This is a direct, second confirmation of
alpha.7 §23's finding, now generalized one step further: **vulnerability
tracks address/geometry; it does not depend on which specific agent
(defender or ordinary expander) happens to occupy that address.** No
kill-stealing (a deliberate attacker damaging a core that a third party
then finishes) was observed in this alpha's own corpus — every capture's
killer was the entrant whose own assault produced the final zeroing write,
confirmed directly from `capture_events`' own `killer` field in every case
above.

## 26. Strategic-niche assessment (Phase 23)

1. **Does either defender materially increase survival relative to
   undefended expansion?** Mixed, condition-dependent — §17 shows one case
   (COLD/`core_tracker`) where the *undefended* control survives but the
   *defended* cells split 2/4 captured; and one case (HOT/`core_seeker`)
   where both undefended and defended victims are captured. Defense is not
   a uniform improvement over undefended expansion in this corpus.
2. **Is Reactive consistently more robust than blind Core Defender?** **No**
   — §19's matched comparison shows identical win/loss outcomes in 16/16
   cells.
3. **Is the survival benefit large enough to justify lost expansion?**
   Reactive's real benefit (fast detection/repair, §22) does not change
   win/loss outcomes in this corpus, while it costs 2–4% of raw score
   (§20) relative to blind defense — in this specific matched design, no.
4. **Does defense work against both attackers?** Both defenders survive
   87.5% of matched occurrences against each attacker — real, substantial,
   symmetric protection relative to a naive "any specialized attacker
   always wins" prior, but not universal.
5. **Does it work across placements?** Yes in control/HOT-`core_tracker`/
   heldout; no in HOT-`core_seeker` and COLD-`core_tracker` specifically
   under adverse scheduler order.
6. **Does it depend excessively on scheduler order?** **Yes, and this is
   the central finding of this alpha** — order alone flips the outcome in
   25% of matched cells, more than placement or attacker choice
   individually predicts in this dataset.
7. **Does timing create genuine attacker/defender matchup variation?**
   Yes — §23's exactly-symmetric-but-differently-located capture pattern.
8. **Can defense avoid being a universally losing strategy?** Yes — 87.5%
   survival for both types is a real, substantial floor, not a token
   result.

## 27. Falsification/success verdict (Phase 25)

**Qualified support**, the governing task's own middle tier, not the
strong-support tier: defense works (87.5% survival, both types, both
attackers) and is a genuine, disclosed-cost tradeoff (§20) — but it is
**highly scheduler-order-sensitive** (§16), and **Reactive's advantage
over blind defense, measured the honest way (matched cells, not aggregate
rates), is not present in this corpus's win/loss outcomes** (§19). Per the
governing task's own Phase 25 guidance for this tier: defense remains
strategically useful evidence, but alpha.10 must account for both
limitations directly rather than assuming "reactive beats blind" or
"defense reliably survives" as settled priors.

## 28. Recommended alpha.10 design (Phase 26)

The governing task's own preferred direction — strategic ecology
validation (expansion vs. generalized offense vs. defense, 1v1 and 3-way)
— remains the right next step, refined by this alpha's own two central
findings:

- Do not seed alpha.10's defender population with an assumption that
  Reactive dominates blind defense; if both are included, report their
  outcomes separately rather than treating Reactive as "the" defense
  representative.
- Scheduler order (which entrant is scheduled last in the decisive tick)
  should be treated as a first-class experimental variable in alpha.10's
  own match construction, not a fixed background convention — §16 shows it
  can outweigh both placement and attacker choice for a single matched
  cell's outcome.
- `core_tracker` and `core_seeker` both belong in the ecology as
  structurally distinct attackers (§23) — neither should stand in for the
  other.

## 29. Unresolved questions

- The general closed-form condition for "which entrant's action block is
  scheduled last in the specific tick the critical zeroing write lands in"
  as a function of assault-episode length, defender refresh/patrol cadence,
  and placement geometry jointly — this alpha traced and explained the
  mechanism directly in three representative cases (§16/§24) but did not
  derive a general predictive formula the way alpha.6/alpha.7 did for
  `core_seeker`'s own scan timing; a natural, narrowly-scoped follow-up.
- Whether a larger corpus (more placements, more seat/order combinations)
  would change the exact 25% order-flip rate found here — this alpha's own
  54-match, stratified corpus (consistent with every prior alpha's
  discipline) was not designed to estimate that rate precisely, only to
  establish that it is real and non-trivial.
- Whether Reactive's real detection/repair-speed advantage (§22) would
  show up as a *survival* advantage under a within-tick-finer scheduling
  model than this Ruleset's own once-per-tick capture check — out of
  scope, since the capture check's own once-per-tick timing is a frozen
  mechanic property (§3), not a harness artifact.
- Seat C's general territorial win-rate advantage (alpha.5 §24) remains
  fully open, unrelated to this alpha's own scope.

## 30. Research artifacts (Phase 28)

`runs/v2_0_alpha9_defense_robustness/` (gitignored under the existing
`runs/` precedent, consistent with every prior alpha): `trace_match_v9.py`
(the dual/multi-slot trace harness, §9), `run_defense_matrix.py` (historical
reproductions + primary matrix + undefended controls + three-way
validation, §14, writes `raw_matches.json`), `analyze.py` (pure
post-processing — survival/timing/scheduler-order/matched-comparison/
opportunity-cost/false-positive/response-timing summaries plus the
representative cell-level traces, writes `analysis_summary.json`). This
document is the durable, committed record.

## 31. Tests (Phase 29)

No production or agent source was changed anywhere in this alpha (§3), and
no correctness defect was found — the scheduler-order behavior (§16) is a
direct, disclosed consequence of the documented once-per-tick capture-check
timing (§3 of alpha.1's own architecture, confirmed unchanged here), not a
bug. Per the governing task's own Phase 29 guidance, no new tests were
added; the existing 92-test alpha-focused suite continues to pass unchanged
(§1, §32).

## 32. Regression qualification (Phase 30)

| Check | Result |
|---|---|
| Alpha-focused suites (alpha.1/2/4/4.1/8) + `test_ruleset_v2_alpha1.py` + `test_ruleset_v1_equivalence.py` | **92 / 92 passed** |
| Full `pytest` (this machine, alpha.9 applied — docs-only change) | **1556 passed, 6 skipped, 2 deselected, 0 failed** (1562 selected) |
| Full `pytest` (this machine, pre-alpha.9, identical `a17fb8f` HEAD) | **1556 passed, 6 skipped, 2 deselected, 0 failed** (1562 selected) — identical, since alpha.9 makes no source change |
| Ruff (repo-wide) | clean, 0 errors |
| mypy (`engine/src/battle_engine`) | clean, 70 files |
| mypy (`client/src/battle_client`) | clean, 10 files |
| `git diff --check` | clean |
| `git diff -- engine/src client/src` | empty |

**Baseline reconciliation note**, following alpha.7 §34/alpha.8 §34's own
precedent of measuring directly rather than assuming: this machine's
freshly-measured pre-alpha.9 full-suite result (1562 selected: 1556 passed,
6 skipped, 2 deselected, 0 failed) is **+2 passed** relative to the
governing task's own documented alpha.8-completion baseline (1560
selected: 1554 passed, 6 skipped). This is on the identical, unmodified
`a17fb8f` HEAD with a clean working tree — i.e., not caused by any change
in this alpha, the same class of small session-to-session collection drift
alpha.7/alpha.8 already found and were explicitly instructed not to chase
further in alpha.9 unless it indicated an actual regression (it does not:
0 failed, both before and after this alpha's own docs-only change, and the
counts are identical before/after within this session). Not investigated
further, per the governing task's own explicit instruction.

## 33. Commit and final state (Phase 31)

Committed locally on `v2.0-development` only. No merge, rebase,
cherry-pick, tag, or push performed. `origin/v2.0-development`'s unrelated
commit `151866c` was left untouched throughout. The only tracked change is
this document (`docs/V2_0_ALPHA9_DEFENSE_ROBUSTNESS.md`) — no source,
test, or config file was modified; `runs/v2_0_alpha9_defense_robustness/`
remains gitignored, matching every prior alpha's own precedent.
