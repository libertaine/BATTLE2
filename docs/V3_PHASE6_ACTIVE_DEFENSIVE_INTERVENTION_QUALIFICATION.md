# Bytefray v3 Phase 6 — Active Defensive Intervention Qualification

Branch: `v3-research-phase6`, cut from `v3-research-phase5` at `ac79fd6`.
Status: research complete, not merged, not tagged, not published.

Phase 6 qualifies a new hypothesis, not the one Phase 5A rejected: instead of
measuring whether a defender was *assaulted and survived* (falsified at
full-corpus scale, `docs/V3_PHASE5A_DEFENSIVE_EVENT_QUALIFICATION.md`), it
asks whether Bytefray's existing mechanics contain a reproducible,
attacker-agnostic, cross-tick event meaning **an opponent mounted a real
core assault, and the victim actively countered it**. It changes no
scoring, weight, Ruleset, agent, or Agent API, and executes no match: every
figure below is reconstructed from committed Phase 1 replay artifacts.

Gates were declared and committed at `aea199e`
(`engine/src/battle_engine/data/benchmarks/v3_phase6_active_defense_gates.json`,
`declared_before_interpretation: true`) **before** this harness ran against
the full 594-cell corpus or any budget condition beyond the 4-roster pilot
sample used to select the candidate's shape. Git history shows that
ordering. No gate was weakened afterwards.

---

## 1. Initial state

| ref | value |
|---|---|
| starting branch | `v3-research-phase5` |
| HEAD | `ac79fd679fefc86b74cd854aae2be79e3f1fa8c7` |
| `v3-research-phase0`..`phase5` | unchanged (`51a39e8`, `0f07425`, `753a602`, `a941571`, `27676a3`, `ac79fd6`) |
| `main` / `origin/main` | `1093393` — identical, no unpushed divergence |
| `v2.0.0` tag | annotated `5c525ce`, unchanged |
| working tree | clean |
| frozen `v2-baseline` population | **9/9** members verify |
| Phase 1 committed corpus | present under `runs/research_v3_phase1/main/results/{a4096_b2,a4096_b8,a4096_b32}/{group,pairwise}` |
| Phase 5A gate/result commits | `8bbaad6` (gates), `ac79fd6` (qualification + report) — both intact |

Work proceeded on a new branch `v3-research-phase6` cut from `ac79fd6`.

---

## 2. Historical question — why Phase 5A was rejected

Phase 5A's candidate event was: *an entrant loses ≥4 of its own core cells
to opponent writes within one tick and still owns ≥1 cell at the capture
check.* Its own mechanical prediction (stride > `CORE_SIZE` ⇒ a sweeper
lands at most one write per core per tick) held with zero exceptions. But
the event itself measured **"was assaulted and survived,"** not
**"defended."** Across the exhaustive 594-cell corpus:

* Expansion agents (`claimer`, `hunter`) registered the event at 15.1%/22.8%
  — nowhere near the ≤2% a non-defense archetype would need — because they
  are the search agents' primary prey and often simply outlast an
  unfinished assault.
* Search agents registered it at 4.2%/4.8%, entirely from the one roster
  containing two searchers (`hunter_coretracker_coreseeker`), which had been
  absent from the earlier 324-cell sample.
* The event went **completely inert** at `a1024_b2` (low action budget): an
  attacker cannot concentrate a burst into one tick when it only has 2
  actions per tick.

Phase 5A's own post-hoc §6 found that requiring the victim to *actively
reclaim* a cell in the same tick restored near-perfect selectivity (search
0.0%, expansion ≤1.1%, defense 21.5–24.8%), but that measurement was
same-tick only, unvalidated at low action budgets, explicitly not
load-bearing for the verdict, and — Phase 5A's own words — "must not be
treated as settled."

---

## 3. New hypothesis

> Can Bytefray identify an actual attack → defensive counteraction
> sequence, rather than merely rewarding an entrant for being attacked and
> surviving — as a **cross-tick** event whose meaning does not collapse at
> low action budgets the way Phase 5A's same-tick event did?

The candidate is an **attack episode** (state-transition based, no
wall-clock window governs its continuity) plus an **active-reclaim**
qualification requiring the victim to write back a cell the episode's
attacker holds, before capture, after the episode has made **meaningful
hostile progress** — itself defined by a mechanically-derived window, not
an arbitrary one (§6–§7).

---

## 4. Mechanics audit (Phase 6A)

Verified directly against `engine/src/battle_engine/python_runtime.py`,
`vm.py`, `scheduler.py`, and `replay.py` — not assumed:

| question | finding |
|---|---|
| Core ownership representation | `VM.writer: list[str \| None]`, one authoritative owner per address, mutated only through `VM._wr8`. |
| Ownership transition recoverability | Fully recoverable from `TickSnapshot.memory_diffs` (`address`/`length`/`owner`), which mirror `vm.tick_diffs` exactly. |
| Capture-check timing | `apply_core_capture` runs exactly once per tick, after **every** seat's actions that tick, against a pre-tick ownership snapshot (`_snapshot_core_owners`). |
| Per-entrant scheduling order | `scheduler.run_sequential_quota`: **sequential-quota**, not round-robin — each seat completes its *entire* action quota before the next seat acts, once per tick, in fixed match order. |
| Memory-diff ordering | `vm.tick_diffs` is in true chronological write order within a tick (adjacent same-owner writes coalesce into one diff; anything else starts a new diff) — confirmed by reading `VM._wr8` directly, not merely cited from `_attribute_core_capture`'s docstring. |
| Attacker identity per transition | Always recoverable: `diff.owner` is the acting entrant's `agent_id` for every transition. |
| Victim reclaim identity | Always recoverable the same way — a write with `owner == victim_home` is unambiguous. |
| Third-party interruption | Representable: any address's owner can change to a third entrant regardless of who held it before; the detector tracks this explicitly (`third_party_takeover`). |
| Self-reduction of own core | **Impossible.** `VM._wr8` has no unclaim operation; an entrant's own write to any address always *claims* it. This is the structural basis for Q2 (self-farming). |
| Core-anchor recovery from replay | Tick-0 `pc` equals `core_start` for every Python entrant (no action has executed by the time tick 0 is published) — reused unmodified from Phase 4/5A. Still the only persisted recovery path; `entrant.start` itself is not separately persisted. |

**One audit finding revises a Phase 5A claim.** Phase 5A's mechanical
ceiling — "a sweeper lands at most one write per core per tick because its
stride exceeds `CORE_SIZE`" — implicitly assumed actions-per-tick low enough
that a single tick cannot contain more than one full stride-cycle across a
core window. That assumption holds at every condition Phase 5A tested
(`instr_per_tick` ≤ 8) but **does not hold in general** at
`instr_per_tick = 32`: several reference agents get enough actions in one
tick to complete, or nearly complete, a full arena lap, which reopens the
possibility of an agent's own sweep touching the same core more than once
within a short span. This finding is load-bearing for §11's verdict.

---

## 5. Candidate definitions considered

Per Phase 6B/6C, before freezing anything:

| candidate | verdict |
|---|---|
| **Unbounded episode** (opens on any hostile acquisition, closes only on capture / full reclaim / full third-party takeover, "meaningful progress" = raw cumulative cell count) | **Rejected in pilot.** A blind expansion sweeper (`core_defender`'s own outward sweep is Claimer-shaped) can lap the whole arena repeatedly over a 400-tick match and accumulate 4–5 cells from an undefended search-agent victim's core one incidental touch at a time — zero deliberate assault, full "meaningful progress." Measured directly: at the 4-roster pilot sample, `core_defender`/`reactive_core_defender` registered as **attacker** in 850 episodes against search victims, entirely incidental. |
| **Same-tick only** (Phase 5A's own shape, R1/R2 "any reclaim") | Already falsified at low action budgets by Phase 5A itself; not re-tested here except as the `test_same_tick_burst_and_reclaim_still_works` backward-compatibility case. |
| **R1 — any reclaim, any episode, unbounded** | Rejected for the same reason as the unbounded episode above (R1 is what the unbounded episode measures). |
| **R2 — reclaim of a cell currently owned by the assault's own attacker** | This is what the frozen design already requires structurally (an episode is keyed by `(victim, attacker)`, so a reclaim can only be recorded against the attacker who actually holds that cell) — folded into the frozen candidate rather than tested as a separate variant. |
| **R3 — reclaim during an ongoing episode, windowed to meaningful progress** | **Frozen candidate** (§6). |
| **R4 — net reversal (attacker's ownership declines after progress)** | Not separately tested: R3's `cells_taken` bookkeeping already tracks this exactly (a reclaim is definitionally a decline in the attacker's held-cell count), so R4 adds no distinguishing power over R3 for this population. |

The smallest definition that survived pilot inspection was **R3 with a
mechanically-derived progress window**, not R1/R2/R4.

---

## 6. Frozen attack-episode definition

> An **attack episode** is a maximal, uninterrupted sequence of hostile
> core-cell acquisitions by one attacker against one victim's core.
>
> * **Opens** on the attacker's first acquisition of a cell the victim
>   currently owns.
> * **Extends** on further acquisitions of the victim's cells by the same
>   attacker (whether in the same tick or a later one).
> * **Closes** when the attacker's currently-held cells from this episode
>   reach zero — via full **victim reclaim**, full **third-party
>   takeover**, or **victim capture** — or remains open to `match_end`.

No tick-count window governs the episode's *continuity*. Two different
attackers against the same victim are tracked as two independent episodes
(keyed by `(victim, attacker)`); a third entrant taking a cell from an
open episode's attacker closes that cell's membership without crediting the
victim.

---

## 7. Why the temporal boundary is not arbitrary

A window **is** used, but only to decide whether an episode's progress
counts as *meaningful hostile progress* rather than incidental contact —
not to decide the episode's own open/extend/close lifecycle (§6).

```text
meaningful_progress_windowed(threshold, window):
    the episode's cumulative distinct-cell count reaches `threshold`
    within `window` ticks of the episode's own start_tick
```

`window` is derived from `ASSAULT_WINDOW = 16` — `core_seeker` and
`core_tracker`'s own published consecutive-`WRITE` burst-width constant
(`engine/src/battle_engine/data/reference_agents/{core_seeker,core_tracker}/agent.py`)
— and the match's action budget:

```text
window(action_budget) = ceil(ASSAULT_WINDOW / action_budget) + 1
```

The `+1` slack tick accounts for a burst that starts mid-quota. This
formula is fixed **before** any exhaustive result and applied identically
at every `action_budget` encountered — it is not chosen per-condition to
hit a target rate. Values used: `window(2) = 9`, `window(8) = 3`,
`window(32) = 2`.

**Why it is needed at all** (the pilot finding that justifies it): with an
unbounded episode, the 4-roster pilot showed `core_defender` and
`reactive_core_defender`'s *own* blind expansion sweeps (§5) registering as
"attacker" against search-role victims in 850 episodes, purely from
incidental arena-wide sweep contact. Applying the window collapsed this to
**zero** — at every one of the three tested budgets (`a4096_b2/_b8/_b32`),
100% of windowed "meaningful progress" episodes had a search-role attacker,
both in the pilot and in the full exhaustive corpus (§13, Q4).

---

## 8. Replay auditability

Two independent checks, both against the full default-condition corpus
(594 cells) unless noted:

1. **Determinism.** Two independent reconstruction passes over the same
   committed replays produce a bit-identical SHA-256 digest over every
   episode's identifying fields (victim, attacker, start/end tick, end
   reason, cumulative cells, reclaim ticks, qualification):
   `ecd3db1018bc263d418aab67e1873a8763de8bd8edfcb77087e6e578441f4da4` on
   both passes.
2. **Independent capture attribution.** The detector maintains its own
   parallel per-victim owned-cell counter and records which write brought
   it from one to zero (`derived_captured_by`) — computed *without* reading
   the engine's own `kill`/`death` events — and compares it against the
   engine's own recorded killer (`captured_by`) for every captured victim.
   Agreement was **100% at every tested condition**:

| condition | agreement |
|---|---:|
| `a4096_b2` group | 229/229 |
| `a4096_b8` group | 417/417 |
| `a4096_b32` group | 832/832 |
| pairwise (all three budgets) | 68/68 |

No artifact deficiency was found: every field the detector needs is
already persisted in committed replay/result artifacts.

---

## 9. Self-farming analysis (Phase 6E)

**Structural, not just empirical.** An episode can only open when
`new_owner != victim_home` (§4: an entrant's own write always claims, never
unclaims), so a `(victim, victim)` episode is unreachable by construction.
Verified as a corpus-wide invariant scan: **0 self-farm violations** across
every condition and every episode (structural check `Q1`/`Q2`, §13).

---

## 10. Collusion / repeat analysis (Phase 6E)

Median qualifying instances per victim-appearance stayed at **1–2** across
every condition, p95 at **2–3**, maximum observed **5** (at `a4096_b32`,
the weakest condition). None approached the predeclared cap-trigger (p95 >
10). **No per-match cap is required** at the measured scale; a per-episode
spam pattern (attacker repeatedly inflicting exactly-threshold incursions
without finishing, paired with a repairing defender) was not observed as an
outlier in the `(attacker, victim)` distribution.

---

## 11. Predeclared gates

Committed at `aea199e`, before this section's numbers existed. See
`engine/src/battle_engine/data/benchmarks/v3_phase6_active_defense_gates.json`
for the full text; summarized here with the measured full-corpus result.

| gate | bound | `a4096_b2` | `a4096_b8` (default) | `a4096_b32` | verdict |
|---|---|---|---|---|---|
| Q1 mechanical validity | 100% | 100% | 100% | 100% | **PASS** |
| Q2 self-farming | 0 violations | 0 | 0 | 0 | **PASS** |
| Q3 attacker attribution | 100% unambiguous | 100% | 100% | 100% | **PASS** |
| Q4 sweep false positive (attacker side) | ≤5% non-search share | 0.0% | 0.0% | 0.0% | **PASS** |
| Q5 role selectivity, default only | defense ≥60%, non-defense ≤15% | n/a | defense min 82.0%, non-defense max 8.6% | n/a | **PASS** |
| Q6 budget-robustness margin | ≥40pp at every budget | 68.6pp | 73.4pp | **15.8pp** | **FAIL at b32** |
| Q7 seat robustness (defense) | spread ≤40pp | 13.0pp | 30.6pp (disclosure-triggered, >25pp) | **64.9pp** | **FAIL at b32** |
| Q8 frequency discipline | median ≤3 | 1 | 1 | 2 | **PASS** |
| Q9 topology coverage | ≤50% one roster | 28.6% | 33.3% | 32.1% | **PASS** |
| Q_determinism | 100% | — | 100% (594/594) | — | **PASS** |

**Two of ten blocking gates fail, both only at `a4096_b32`, both traced to
the same underlying mechanism** (§14). Per the predeclared decision rule,
the "revise" clause is scoped only to threshold/window-choice artifacts;
§14 shows this failure is neither, so revision is not invoked.

---

## 12. Full-corpus selectivity

All 594 default-condition (`a4096_b8`) group cells (11 rosters × 54),
threshold = 4:

| agent | role | appearances | opportunities | qualifying | opportunity-conditioned rate |
|---|---|---:|---:|---:|---:|
| `core_defender` | defense | 270 | 122 | 100 | **82.0%** |
| `reactive_core_defender` | defense | 270 | 128 | 111 | **86.7%** |
| `hunter` | expansion | 378 | 116 | 10 | 8.6% |
| `claimer` | expansion | 378 | 89 | 4 | 4.5% |
| `core_seeker` | search | 216 | 16 | 1 | 6.2% |
| `core_tracker` | search | 270 | 18 | 0 | 0.0% |

Margin at the default condition: **73.4 percentage points** between the
weaker defender and the stronger non-defense archetype — an order of
magnitude cleaner separation than Phase 5A's same-tick event ever achieved
at any threshold (Phase 5A's own best case, post-hoc and same-tick only,
was defense 21.5–24.8% vs. expansion ≤1.1%, a **~20pp** margin; this
candidate's default-condition margin is more than **3.5×** that, using a
denominator that actually accounts for assault opportunity).

Full-corpus threshold sensitivity (C1), default condition, showing
threshold 4 is not uniquely magic — 2 through 5 behave almost identically,
consistent with Phase 5A's own C1 disclosure norm:

| threshold | defense min opp. rate | search max opp. rate | expansion max opp. rate |
|---:|---:|---:|---:|
| 2 | 80.5% | 6.2% | 10.6% |
| 3 | 80.2% | 6.2% | 8.5% |
| **4** | **82.0%** | **6.2%** | **8.6%** |
| 5 | 80.9% | 6.2% | 8.6% |
| 6 | 79.6% | 0.0% | 3.6% |

---

## 13. Per-agent results

See §12 (default condition) and §15 (budget conditions) — reported
together rather than duplicated, since the per-agent breakdown *is* the
budget-robustness table.

---

## 14. Per-roster / topology results

Phase 5A's own failure mode was one roster (`hunter_coretracker_coreseeker`,
the only one with two searchers) carrying 100% of its counterevidence,
hidden by a 6-of-11-roster sample. Phase 6's exhaustive run covers all 11
rosters; the non-defense qualifying instances are **not** concentrated in
one roster at any budget:

| condition | non-defense qualifying total | max single roster's share |
|---|---:|---:|
| `a4096_b2` | 7 | 28.6% (`claimer_coretracker_hunter`) |
| `a4096_b8` | 15 | 33.3% (`claimer_coretracker_hunter`) |
| `a4096_b32` | 56 | 32.1% (`claimer_coreseeker_hunter`) |

At `a4096_b32`, the residual is spread across six of the eleven rosters
(`claimer_coreseeker_hunter` 18, `hunter_coretracker_coreseeker` 15,
`reactive_hunter_coreseeker` 12, `claimer_coretracker_hunter` 7,
`hunter_coretracker_coredefender` 3, `claimer_coretracker_reactive` 1) —
diffuse, not concentrated in the two-searcher roster the way Phase 5A's
counterevidence was. Q9 passes at every budget for the group corpus.

Pairwise (no defense agent present, so every qualifying instance there is
by construction non-defense — Phase 5A's own C4 precedent):
`hunter_vs_coretracker_400` carries the overwhelming majority of pairwise
qualifying instances at every budget (3/3 at b8, 5/6 at b32); `claimer`
essentially never qualifies (0/8 at b2/b8, 1/8 at b32). §16 explains why.

---

## 15. Budget robustness (Phase 6F)

Matched arena (4096), varying only `instr_per_tick` (2 / 8 / 32):

| agent | role | b2 opp. rate | b8 opp. rate | b32 opp. rate |
|---|---|---:|---:|---:|
| `core_defender` | defense | 94.2% | 82.0% | 68.0% |
| `reactive_core_defender` | defense | 76.9% | 86.7% | 65.8% |
| `hunter` | expansion | 4.7% | 8.6% | 19.5% |
| `claimer` | expansion | 3.4% | 4.5% | 7.7% |
| `core_seeker` | search | 8.3% | 6.2% | 4.3% |
| `core_tracker` | search | 0.0% | 0.0% | **50.0%** |

At `a4096_b2` (the condition where Phase 5A's own event went **completely
inert**), this candidate is not just alive but shows the *widest* margin of
any tested budget (68.6pp) — directly answering Phase 6's primary question:
the cross-tick design is not action-budget-inert the way the same-tick
event was.

At `a4096_b32`, selectivity degrades. `core_tracker` is the whole story:
9 of its 18 opportunities qualify (50.0%), and every one traces to the
same mechanism, verified directly against source and against one concrete
replay:

`core_tracker`'s outward "expand" sweep cursor is initialized to its own
core_start with **no offset** —
`self.expand_cursor = observation.pc % self.arena_size` — unlike
`core_defender`, which deliberately starts its own expansion sweep at
`core_start + DEFENDED_RADIUS` specifically "so the defended cells and the
expansion sweep never fight over the same ground" (`core_defender/agent.py`
docstring). `core_tracker` has no such offset, and `SCAN_EVERY = 3` means
its very first action (`actions_taken=1`, `1 % 3 != 0`) is always an
"expand" write landing exactly on its own `core_start + 0` — a routine
territorial claim with zero defensive intent.

Confirmed against the actual replay for
`hunter_coretracker_coreseeker/0006` (seat B = `core_tracker`, core_start
1365): tick 1's diffs are `(1361, 16, "A")` — `core_seeker`'s full
16-address `ASSAULT_WINDOW` burst, covering `core_tracker`'s entire 8-cell
core — immediately followed, in the same tick, by `(1365, 1, "B")`:
`core_tracker`'s own first action, landing precisely on its own
`core_start`. That single incidental self-write satisfies the reclaim
clause. `core_seeker`'s own cursor, by contrast, starts at fixed address 0
(not at its own `core_start`), so this artifact affects `core_tracker`
specifically and far more reliably than it affects any other agent — which
is exactly why `core_seeker`'s own opportunity-conditioned rate *stays low*
(4.3%) at the same budget while `core_tracker`'s does not.

A smaller, more diffuse version of the same class of artifact (routine
sweep coincidentally re-crossing one's own core, this time via genuine
full-arena-lap return rather than a guaranteed first-action hit) explains
`hunter`'s rise from 4.7%/8.6% to 19.5% and `claimer`'s smaller rise from
3.4%/4.5% to 7.7% across the same budget range: higher `instr_per_tick`
shortens the time for any sweeping agent's outward cursor to lap the whole
arena and cross its own core again.

**Q4's attacker-side purity (§7) held at 100% across every budget,
including `a4096_b32`.** This confound is entirely on the *reclaim* side —
who the victim happens to be, not who the attacker is — and does not
undermine the episode/attacker-acquisition half of the design.

---

## 16. Seat-order effects (Phase 6I)

Decomposed by opportunity-conditioned qualifying rate, defense victims
only, by seat:

| condition | seat A | seat B | seat C | spread |
|---|---:|---:|---:|---:|
| `a4096_b2` | 78.4% | 91.4% | 79.7% | 13.0pp |
| `a4096_b8` | 69.4% | 90.2% | 100.0% | 30.6pp |
| `a4096_b32` | **35.1%** | 72.4% | **100.0%** | **64.9pp** |

At `a4096_b2`/`a4096_b8`, the cross-tick design visibly reduces "victim
acts last" dependence relative to Phase 5A's own same-tick figure (19.5pp
at full-corpus scale) — `a4096_b2`'s 13.0pp spread is smaller, and even the
worst-off seat at the default condition (A, 69.4%) still qualifies more
than two-thirds of the time.

At `a4096_b32` this reverses sharply. Broken down by outcome (seat A,
defense victims, meaningful-progress opportunities): **80 of 151** end in
`captured` (not qualifying), 18 end in `match_end` without ever reclaiming,
and only 53 (35.1%) reach `reclaimed_all`. Seat C, by contrast, reaches
`reclaimed_all` in **all 211 of 211** of its opportunities — zero captures.

The mechanism: at high action budgets, a genuine assault can complete
within a single tick (§15's `core_seeker` example took all 8 of a victim's
cells in tick 1 alone). When that happens, the cross-tick advantage this
design exists to provide — letting an early-seated victim react on a
*later* tick — never gets a chance to operate, because the victim is
captured before it has a second turn. This reintroduces exactly the
same-tick "acts last" dependency Phase 6 was designed to reduce, but only
when the assault itself is fast enough to fit inside the window the victim
would otherwise have used to react across ticks.

---

## 17. False positives / false negatives

**False positives** (non-defense qualifying instances): 15 at the default
condition (§12), rising to 56 at `a4096_b32` (§15's `core_tracker`
artifact accounts for the great majority of the increase). Zero at any
budget trace to genuine sustained defensive behavior by a non-defense
archetype; every inspected case traces to either (a) `core_tracker`'s
expand-cursor artifact, (b) a smaller-magnitude version of the same
mechanism in `hunter`/`claimer`, or (c) — in the small residual not
individually inspected — plausibly the same class of incidental contact.

**False negatives**: not separately quantifiable without a ground truth
outside this detector's own definition, but two structural properties bound
the risk: (1) every closed episode's `end_reason` (`reclaimed_all` /
`third_party_takeover` / `captured` / `match_end`) is recorded regardless
of qualification, so a defender that successfully repels an assault but
whose progress never reaches `meaningful_progress_windowed` is visible in
the data as a non-qualifying `reclaimed_all` episode, not silently dropped;
(2) §8's determinism/auditability checks rule out a reconstruction bug as
a source of missed events.

---

## 18. Event frequency conditioned on assault opportunity

This is the primary selectivity metric throughout (§11 `decision_rule`):
opportunity-conditioned rate, not raw appearance rate, because a defender
never assaulted cannot demonstrate defense — Phase 5A's own falsified
premise measured raw appearance rate and could not distinguish "never
attacked" from "attacked and did nothing." Every table in §12–§16 already
reports this denominator; raw appearance rates (for reference, default
condition) were far smaller and less informative: `core_defender` 37.0% of
all appearances, `reactive_core_defender` 41.1%, `hunter` 2.6%, `claimer`
1.1%, both searchers ≤0.5% — directionally identical but far less legible
about *why* the rate differs by role.

---

## 19. Qualification verdict

### **ACTIVE DEFENSIVE EVENT NOT QUALIFIED — DEFENSIVE-SCORING THESIS WEAKENED**

Q6 (budget-robustness margin) and Q7 (seat robustness) — both blocking —
fail at `a4096_b32`. Per the predeclared decision rule, the "revise"
clause is available only for a threshold-or-window-choice artifact; §15's
diagnosis (an agent-specific expand-cursor initialization choice, plus a
genuine collapse of the cross-tick reclaim advantage when assaults complete
within one tick) is neither, so revision is not invoked, and the failure is
reported as a null result rather than rescued.

This is a **budget-dependence** failure in the sense the governing task's
own interpretation rules anticipate, and it is materially different in
character from Phase 5A's failure:

* Phase 5A's event was wrong **everywhere it fired** — it measured passive
  survival at every budget it could fire at, and went inert (fired nowhere)
  at low budgets.
* Phase 6's event is well-defined, highly selective (73.4pp margin), and
  **improves** on Phase 5A's own low-budget inertness (widest margin of any
  tested condition, 68.6pp, at `a4096_b2`) at the shipped default and at
  low action budgets. It specifically degrades at `a4096_b32` — a non-
  default, high-density condition — through two independently diagnosed,
  non-arbitrary mechanisms rather than a conflation present in the concept
  itself.

Because Q6/Q7 are declared blocking gates and both fail, the predeclared
rule does not permit a QUALIFIED verdict regardless of how well-explained
the failure is — invoking a softer verdict here would be exactly the
"rescue it after the result" the governing task forbids.

---

## 20. Recommended next research question

Stated, not implemented:

> Both diagnosed high-budget failure mechanisms are properties of the
> **reference agent population's own implementation choices**
> (`core_tracker`'s un-offset expand cursor; the general relationship
> between sweep speed and own-core lap-return time), not of the episode/
> reclaim event definition itself. A successor phase could ask whether the
> same candidate definition, re-qualified against a population where every
> sweeping agent's own expansion is deliberately offset past its own core
> (mirroring `core_defender`'s existing precedent), passes Q6/Q7 at
> `a4096_b32` without any change to the detector — which would relocate
> this finding from "the event is budget-dependent" to "the frozen
> population's `core_tracker` has an incidental self-claim bug unrelated to
> defense," a materially different and more actionable conclusion. That
> reclassification is not tested here and must not be assumed.

---

## Files changed

| file | change |
|---|---|
| `tools/v3_phase6_defense_episode.py` | **new** — episode reconstruction, qualification, pilot, and determinism tooling (measurement only) |
| `engine/tests/test_v3_phase6_defense_episode.py` | **new** — 15 focused tests |
| `engine/src/battle_engine/data/benchmarks/v3_phase6_active_defense_gates.json` | **new** — gates, declared at `aea199e` before the exhaustive run |
| `docs/V3_PHASE6_ACTIVE_DEFENSIVE_INTERVENTION_QUALIFICATION.md` | **new** — this report |

## Validation

| check | result |
|---|---|
| Gates predate results | `aea199e` precedes this report's commit; `declared_before_interpretation: true` |
| Scoring / Ruleset / Agent API / defaults changed | **none** |
| Matches executed | **none** — committed artifacts only |
| Corpus | 594 group cells × 3 budget conditions + 54 pairwise cells × 3 budget conditions |
| Determinism | identical SHA-256 digest over two independent passes, full default-condition corpus |
| Replay-auditability cross-check | 100% agreement (1,546/1,546) between independent capture attribution and engine events, across every tested condition |
| Frozen `v2-baseline` population | 9/9 |
| Full test suite | passing (see commit) |
| `ruff check` / `mypy` | clean |

Nothing merged to `main`, nothing tagged, nothing published.
