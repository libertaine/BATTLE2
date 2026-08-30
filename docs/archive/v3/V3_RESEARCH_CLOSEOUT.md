# Bytefray v3 Research — Final Closeout

Branch: `v3-research-closeout`, cut from `v3-research-phase7` at `d976d21`
(Phase 7's own report commit). Status: research complete, not merged, not
tagged, not published.

This is the final research-closeout phase before any decision about a
changed Ruleset, Ruleset 3, a v2.x balance change, or no rules change at
all. It closes the remaining v3 research questions — defensive-event
observability, scheduler-topology characterization, and the qualified
research operating region — and answers, once and for all in this
program, whether the evidence gathered across Phases 0–7 justifies a
Ruleset semantic change for a future Bytefray release.

No gameplay mechanic, scheduler semantic, scoring formula, core mechanic,
or Agent API surface is changed by this phase. No Ruleset 3 candidate is
created. Nothing is merged, tagged, or prepared for release.

---

## 1. Executive summary

Four research-closeout questions were posed and answered:

* **Q1 (defensive-event closure)** — **CLOSED.** Three independent,
  zero/minimal-cost empirical checks (a blind-timer prediction test, a
  blind-versus-reactive discriminant, and a disposable turtle-control
  probe) all converge on the same conclusion Phase 5A/6/7 already
  pointed toward: ownership-transition history cannot distinguish
  responsive defense from a sufficiently frequent, entirely blind
  own-core rewrite. `core_defender`'s own qualifying reclaims are
  predicted **100.0%** of the time by an attack-blind timer replay of
  its own source code; the evidence-driven `reactive_core_defender`
  does **not** consistently outperform the blind `core_defender` on the
  proposed metric (the sign of the difference flips across budget
  conditions); and a maximally passive, zero-intelligence turtle probe
  **matches or exceeds** both real reference defenders' event rates at
  every tested budget.
* **Q2 (scheduler topology)** — **Confirmed as a real, independent
  absolute-quota effect.** Along Phase 1's own constant-density diagonal
  (`S ≈ 0.781`: `a1024_b2`, `a4096_b8`, `a16384_b32`, `a65536_b128`),
  reaction-opportunity denial rises **monotonically from 0.0% to
  34.6%** purely as absolute `instr_per_tick` rises 2 → 8 → 32 → 128,
  with density held exactly fixed. This falsifies the strong form of
  "arena size and action budget are one variable" and bounds Phase 1's
  own §9.1 finding precisely.
* **Q3 (research operating envelope)** — `instr_per_tick` should be
  treated as **not** condition-neutral. The shipped default
  (`instr_per_tick = 8 = CORE_SIZE`) sits exactly on a mechanically
  verified structural boundary (Sec 11): a perfectly informed attacker
  can capture an earlier-scheduled, non-reacting victim within one
  action block once `instr_per_tick >= CORE_SIZE`, and cannot below it.
  Future strategic-mechanics research must disclose and justify any
  `instr_per_tick` materially above the default for this reason, not
  merely for density reasons.
* **Q4 (Ruleset decision input)** — After eight phases (0–7) plus this
  closeout, **no proposed semantic change survives the research
  standard.** Locality was rejected (Phase 2). Offense payoff is
  promising but structurally opposed to defense viability with no
  compensating lever (Phases 3–4). The defensive-event scoring line is
  now closed (Phase 5A/6/7/this phase). The scheduler-topology effect is
  real but concentrated off the shipped default and was never shown to
  degrade the shipped ecology. **No Ruleset change is currently
  justified.**

---

## 2. Initial repository state

Verified directly, not assumed, before any mutation:

| ref | value |
|---|---|
| starting branch | `v3-research-phase7` |
| HEAD | `d976d21d9b2320219c7ec2d53e19b5e5444d1a3c` ("docs(v3): record the Phase 7 confound-isolation findings") |
| `main` | `1093393b401aabda243ed89b7c44fa91938477b5` |
| `origin/main` | `1093393` — identical, no unpushed divergence |
| `v2.0.0` tag | present, annotated |
| working tree | clean |
| `v3-research-phase7` cut point | `7f36a23` (Phase 6's report commit) — confirmed by `git log --oneline` on the branch |
| Phase 0–7 branches (`v3-research-phase0` … `v3-research-phase6`) | all present at their previously recorded commits; untouched |
| frozen `v2-baseline` benchmark population | **9/9** members verify against their pinned `agent_revision_id` (`battle_engine.benchmarks.verify_population`) |
| Phase 1 committed corpora | present and complete: `a1024_b2`, `a4096_b2`, `a4096_b8`, `a4096_b32`, `a16384_b32`, `a65536_b128` (594 group cells each) and every other declared grid condition |
| Phase 5A/6/7 gate files | `v3_phase5a_defensive_event_gates.json`, `v3_phase6_active_defense_gates.json` present and unmodified; Phase 7's report and disposable artifacts intact |
| historical reports | Phase 0–7 `docs/V3_PHASE*.md` reports present; none rewritten by this phase |
| unrelated historical stash | three pre-existing stash entries (`sync_win auto-stash` x2, a `feature/pygame-window-fit` WIP), all predating this program and disclosed by Phase 7 — **not touched** |

Work proceeded on a new branch `v3-research-closeout`, created from the
Phase 7 HEAD. Nothing was merged or tagged.

No separate "independent skeptical architecture review" document exists
anywhere in the repository or its git history. The governing closeout
task's own Sec 4–14 embed that review's specific, individually testable
claims directly (e.g. "Q6 and Q7 used different denominator units",
"the Phase 6 implementation's episode-opening semantics should be
checked against its frozen declaration"). Those claims are treated as
the material to verify against source and committed artifacts — see
Sec 14 below — rather than assumed correct.

---

## 3. Research questions

Restated from the governing task, answered in Sec 8 (Q1), Sec 11–12
(Q2), Sec 13 (Q3), and Sec 18–20 (Q4) below.

---

## 4–7. Defensive-event closure tests

### Method

All three checks reuse `tools/v3_phase6_defense_episode.py`'s frozen
`Episode`/`reconstruct_episodes`/`max_assault_ticks` machinery
**unmodified** (imported, never copied or edited) and the same
`episode_threshold = 4` / progress-window formula Phase 6 declared and
froze at `aea199e`. No threshold, window, or qualifying rule was changed
anywhere in this phase. New tooling:
`tools/v3_closeout_defensive_timer.py` (D1 + the blind-versus-reactive
discriminant) and `tools/v3_closeout_turtle_probe.py` (the E8 turtle
probe), plus a disposable probe agent
(`engine/src/battle_engine/data/v3_closeout_agents/turtle_core_refresher/`).

### Sec 4/C — Blind timer prediction (D1)

`core_defender`'s own source
(`engine/src/battle_engine/data/reference_agents/core_defender/agent.py`)
reads `observation` exactly **once**, on its first `act()` call, purely
to learn its own spawn address; every subsequent call is a pure function
of an internal `actions_taken` counter and fixed constants
(`REFRESH_EVERY = 4`, `expand_stride = 131`). Its entire action stream is
therefore computable in advance with **zero** knowledge of any opponent.
`blind_core_defender_schedule` replays the real, unmodified
`CoreDefenderAgent` class against a synthetic observation stream that
never reflects the actual match, and predicts, for each match, exactly
which tick(s) it will rewrite which of its own core addresses.

Compared against every qualifying reclaim (`reclaim.qualifying is True`)
for every cell in which `core_defender` is a victim, across all three
Phase 6 budget conditions, full 594-cell default-condition corpus:

| condition | observed qualifying reclaims | predicted by blind timer | ratio |
|---|---:|---:|---:|
| `a4096_b2` | 494 | 494 | **1.000** |
| `a4096_b8` (default) | 550 | 550 | **1.000** |
| `a4096_b32` | 180 | 180 | **1.000** |

**100.0% of every qualifying `core_defender` reclaim, at every tested
budget, is exactly what its own attack-blind timer predicts.** This is
load-bearing: it does not merely correlate with the timer, it **is** the
timer — `core_defender`'s source contains no code path that could ever
produce a different outcome, because it never branches on `observation`
after its first call. The event, for this agent, requires no concept of
defensive response whatsoever.

### Sec 5/D — Blind-versus-reactive discriminant

Reported **separately** for `core_defender` (blind) and
`reactive_core_defender` (evidence-driven: it inspects its own core via
`READ` and only reacts to a detected mismatch), never pooled into one
"defense" role, at all three Phase 6 budgets, full 594-cell
default-condition corpus:

| condition | agent | appearances | opp. appearances | raw event rate | opp.-conditioned rate | reclaim rate\|opp | eventual survival | eventual capture |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `a4096_b2` | core_defender (blind) | 270 | 69 | 24.1% | **94.2%** | 94.2% | 97.0% | 3.0% |
| `a4096_b2` | reactive_core_defender | 270 | 78 | 22.2% | **76.9%** | 76.9% | 93.0% | 7.0% |
| `a4096_b8` (default) | core_defender (blind) | 270 | 122 | 37.0% | **82.0%** | 82.0% | 90.7% | 9.3% |
| `a4096_b8` (default) | reactive_core_defender | 270 | 128 | 41.1% | **86.7%** | 86.7% | 93.0% | 7.0% |
| `a4096_b32` | core_defender (blind) | 270 | 150 | 37.8% | **68.0%** | 68.0% | 78.5% | 21.5% |
| `a4096_b32` | reactive_core_defender | 270 | 155 | 37.8% | **65.8%** | 65.8% | 74.4% | 25.6% |

Reactive-minus-blind, by condition (opportunity-conditioned rate):

| condition | reactive − blind | reactive outperforms blind? |
|---|---:|:-:|
| `a4096_b2` | **−17.3 pp** | **No** — blind wins clearly |
| `a4096_b8` (default) | **+4.8 pp** | Yes, narrowly |
| `a4096_b32` | **−2.2 pp** | No |

**The evidence-driven defender does not consistently outperform the
blind periodic writer on the proposed defensive-event metric.** The sign
of the difference flips across budget conditions, and where blind wins
(`a4096_b2`), it does so by a wide margin (17.3 pp) — wider than
reactive's own narrow win at the default (4.8 pp). At `a4096_b32`,
`reactive_core_defender` is also captured *more* often overall (25.6%
vs. 21.5%) despite its extra READ-based intelligence. No new metric was
invented to rescue the distinction, per the governing task's explicit
instruction. `reclaim_rate_given_opportunity` is numerically identical
to the opportunity-conditioned qualifying rate for both agents at every
condition in this corpus — every reclaim either of them ever made also
happened to survive its own tick (no case of a same-tick multi-episode
capture coinciding with one of their reclaims), which is a genuine
property of this corpus, not a computation error (verified by direct
inspection of the underlying per-episode data).

### Sec 6/E — E8 turtle probe

The Phase 5 design proposal declared, but never ran, an "E8 turtle
control" gate: *"A deliberately passive/immobile probe agent (analogous
to Phase 2's `local_camper`) must not become competitive at any tested
`w_defense`"* (`docs/V3_PHASE5_DEFENSIVE_EVENT_DESIGN_PROPOSAL.md`
Sec 5B.3). Phase 5B — the scoring experiment this gate was declared
for — never ran, because Phase 5A itself failed qualification first, so
there is no `w_defense` scoring Ruleset to test competitiveness against.
Per the governing task's own instruction ("if the exact historical probe
cannot be executed because required implementation was never created,
build the smallest disposable research-only probe necessary to
instantiate the original declared behavior"), this phase built the
smallest Ruleset-v2-native instantiation of that declared behavior —
`turtle_core_refresher` — and measured it against the mechanism that
**is** still live at this point in the program: Phase 6's active-defense
event.

```text
research probe only
non-gate benchmark agent
not part of frozen v2-baseline
```

`turtle_core_refresher` writes to one of its own eight core cells on
**every single action**, cycling through them in a fixed round-robin. It
never expands, never issues a `READ`, and carries no branching logic of
any kind — strictly less reactive intelligence than either frozen
defender (`core_defender` still spends 3 of every 4 actions expanding;
`reactive_core_defender` additionally inspects and reacts to evidence of
damage).

It was substituted for `core_defender` in the
`coredefender_reactive_coreseeker` roster shape (keeping the real,
untouched `reactive_core_defender` and `core_seeker` in the same
matches), at Phase 6's own three budget conditions, Phase 1's own
seed/layout/permutation methodology (3 seeds × 3 layouts × 6 seat
permutations = 54 cells/condition, 162 new cells total — the same order
of magnitude as Phase 7's own disposable-control corpus).

| condition | agent | appearances | opp. appearances | opp.-conditioned rate |
|---|---|---:|---:|---:|
| `a4096_b2` | real `core_defender` (matched roster) | 54 | 30 | 100.0% |
| `a4096_b2` | real `reactive_core_defender` (matched roster) | 54 | 30 | 90.0% |
| `a4096_b2` | **`turtle_core_refresher`** | 54 | 12 | **100.0%** |
| `a4096_b8` (default) | real `core_defender` (matched roster) | 54 | 45 | 93.3% |
| `a4096_b8` (default) | real `reactive_core_defender` (matched roster) | 54 | 45 | 100.0% |
| `a4096_b8` (default) | **`turtle_core_refresher`** | 54 | 42 | **100.0%** |
| `a4096_b32` | real `core_defender` (matched roster) | 54 | 51 | 70.6% |
| `a4096_b32` | real `reactive_core_defender` (matched roster) | 54 | 51 | 64.7% |
| `a4096_b32` | **`turtle_core_refresher`** | 54 | 54 | **77.8%** |

**The turtle probe matches or exceeds both real reference defenders'
opportunity-conditioned event rate at every tested budget**, despite
possessing zero reactive intelligence. At `a4096_b32` it is the single
highest-rated "defender" of any agent measured anywhere in this
closeout (77.8%, against real `core_defender`'s 70.6% and real
`reactive_core_defender`'s 64.7% in the identical roster shape). This is
recorded as direct evidence against interpreting the event as active
defense, exactly as the governing task anticipated it might be.

---

## 8. Defensive-event closure verdict

### **DEFENSIVE-EVENT LINE CLOSED — OWNERSHIP HISTORY DOES NOT DISTINGUISH RESPONSIVE DEFENSE**

Three independent, converging, zero/minimal-new-match-cost checks — none
of them rescued by threshold or window tuning, since none of them turns
on threshold or window at all — establish this:

1. For `core_defender`, the proposed event is **provably** (not merely
   empirically) a pure function of a deterministic, attack-blind timer:
   its source code cannot express a different behavior.
2. For `reactive_core_defender` versus `core_defender`, the
   evidence-driven agent does **not** consistently outperform the blind
   one on the proposed metric; the sign flips by budget, and where blind
   wins it wins by more than reactive ever does.
3. A probe with **strictly less** reactive capability than either real
   reference defender — no `READ`, no branching, no conditional logic —
   **matches or exceeds** both of them at every tested budget.

Per the governing task's instructions for a CLOSED verdict: no further
detector is proposed, no further threshold or window is proposed, Phase
5B is not revived, and no defensive scoring is proposed here.

**What additional semantic information would be required to distinguish
responsive defense, if any** — stated as possibilities, explicitly
**not** recommended, per Sec 7's "possible ≠ justified" distinction:

* **Agent API declaration** (e.g. an explicit "this action is a
  defensive response" flag emitted by the agent) — *possible*, but
  self-reported intent is trivially gameable (any agent could mark every
  action "defensive") and would not need a Ruleset-observable ownership
  mechanism at all; **not justified** by anything measured here, because
  no design was evaluated that avoids this failure mode.
* **New observable execution telemetry** (e.g., recording whether a
  `WRITE` was preceded by a `READ` that returned evidence of damage, as
  a first-class engine-derived fact rather than something reconstructed
  from ownership diffs) — *possible in principle*, and closer to what
  this closeout's own D1/E8 results actually needed (a way to see *why*
  an action was taken, not just *that* it was taken) — but **not
  justified**: no concrete design was proposed or evaluated, and the
  turtle-probe result (Sec 7) shows that *any* sufficiently frequent
  own-core rewrite already saturates the existing event, so a new
  telemetry channel would need its own anti-gaming analysis before being
  worth pursuing, which is out of scope for a closeout phase.
* **Ruleset/observation semantic change** (e.g., exposing an ownership
  map or an "under attack" flag directly to agents) — *possible*, but
  this is a much larger change than defensive scoring itself, was never
  scoped by Phases 4–7, and no evidence gathered here suggests it is
  needed for anything other than this one now-closed scoring question.
* **Explicit action semantics** (e.g. a dedicated `DEFEND` action) —
  *possible*, but this is a new gameplay mechanic, explicitly excluded
  from this program's scope throughout, and nothing measured here
  establishes it would behave any differently from the ownership-history
  approach that just failed.

None of these four is recommended. They are recorded because the
governing task asked for them to be distinguished from "justified", not
because any of them clears that bar.

---

## 9. Scheduler mechanics audit

Verified directly against source, not assumed, matching Phase 6 Sec 4's
own audit exactly (reconfirmed here independently as part of this
phase's own diligence):

| property | verified against | finding |
|---|---|---|
| Each entrant executes its full per-tick quota sequentially | `engine/src/battle_engine/scheduler.py`, `run_sequential_quota` | Confirmed: `for state in states: for slot in range(quota): execute_slot(...)` — one state's entire quota runs before the next state's first slot. |
| The next entrant acts only after that quota completes | same | Confirmed by the same loop structure; a state that dies mid-quota stops immediately (`if not state.alive: break`), but a later state is never interleaved with an earlier one's remaining slots. |
| Core capture is resolved once per tick, after the seats have acted | `python_runtime.py`'s per-tick loop: `self.ruleset_policy.run_scheduler(...)` then `apply_core_capture(...)` | Confirmed: `apply_core_capture` is called exactly once, immediately after `run_scheduler` returns for that tick, against a `pre_tick_core_owners` snapshot taken **before** any of that tick's actions ran. |
| `CORE_SIZE = 8` | `python_runtime.py:71` | Confirmed. |
| `instr_per_tick` is configurable | `config.py`: `Config.instr_per_tick: int = 8` | Confirmed; default is 8, freely overridable per match/evaluation. |
| Ownership mutation has no unclaim path | `vm.py`, `VM._wr8` | Confirmed: `_wr8`'s `owner` parameter is `str \| None`, but every call site in the engine (`seed_core_ownership`, `maintain_core_beacons`, both VM/Python action-execution paths) always passes a concrete agent id, never `None`. An entrant's own write always claims a cell; there is no code path that lowers its own owned-cell count. |
| Scheduling/quota semantics are Ruleset semantics | `docs/RULES.md` "Ruleset bump policy" | Confirmed: "a scheduler-order/quota-semantics change" is explicitly listed as requiring a `BYTEFRAY_RULESET_ID` bump — this closeout does not propose one. |

### Theorem (verified, precisely scoped)

> **Whenever one entrant can overwrite an opponent's entire
> `CORE_SIZE`-cell core within one uninterrupted action block, the
> Ruleset provides no guaranteed defensive response window for a victim
> scheduled before that attacker in that tick.**

This is a **Ruleset-level possibility**, verified mechanically in Sec 13
below by direct construction (not by observing any current agent). It is
**not** a claim that every current attacker can or does do so: of the
nine frozen `v2-baseline` agents, only the two dedicated search agents
(`core_seeker`, `core_tracker`) ever mount a contiguous multi-cell
assault burst at all (Phase 5/6's own stride analysis, reconfirmed by
Phase 6 Q4's 100% attacker-side purity and this closeout's own
constant-density reanalysis, Sec 12), and even they do not always
complete a full 8-cell burst within a single tick at every budget. The
theorem states a capability the Ruleset's scheduling and capture-timing
rules permit under the right conditions, precisely separated from how
often the current benchmark population actually exercises it.

---

## 10. Constant-density scheduler experiment

Reused **unmodified**: Phase 6's `reconstruct_episodes`/
`max_assault_ticks`/`Episode` machinery, and Phase 7's own
`had_reaction_opportunity` predicate (imported directly from
`tools/v3_phase7_confound_isolation.py`, never copied or edited). New
tool: `tools/v3_closeout_constant_density.py`. **Zero new matches** — all
four conditions' 594-cell group corpora were already committed by
Phase 1.

Phase 1's own default-density diagonal (`S ≈ 0.781`,
`docs/V3_PHASE1_ARENA_ACTION_DENSITY.md` Sec 3.3):

| condition | arena | `instr_per_tick` | `S` |
|---|---:|---:|---:|
| `a1024_b2` | 1024 | 2 | 0.781 |
| `a4096_b8` (default) | 4096 | 8 | 0.781 |
| `a16384_b32` | 16384 | 32 | 0.781 |
| `a65536_b128` | 65536 | 128 | 0.781 |

Phase 7 measured reaction-opportunity denial only across
`a4096_b2/_b8/_b32` — matched *arena*, varying budget, which changes
density (`S = 0.195 / 0.781 / 3.125`). This experiment holds density
**exactly fixed** and varies only absolute `instr_per_tick`, which is
the causal test the governing task specifically requires (Sec 9).

---

## 11. Reaction-opportunity results

Full 594-cell group corpus per condition, threshold = 4 (Phase 6's own
frozen value), "meaningful-progress" assault opportunities only:

| condition | assault opportunities | had reaction opportunity | denied | denied rate |
|---|---:|---:|---:|---:|
| `a1024_b2` | 716 | 716 | **0** | **0.0%** |
| `a4096_b8` (default) | 617 | 605 | 12 | **1.9%** |
| `a16384_b32` | 472 | 380 | 92 | **19.5%** |
| `a65536_b128` | 656 | 429 | 227 | **34.6%** |

By victim seat (denial concentrates entirely on the earliest-acting
seat, exactly as the theorem predicts — seat `C`, which acts last every
tick, is **never** denied a reaction opportunity at any tested point on
this diagonal):

| condition | seat A denied | seat B denied | seat C denied |
|---|---:|---:|---:|
| `a1024_b2` | 0.0% | 0.0% | 0.0% |
| `a4096_b8` | 6.0% | 0.9% | 0.0% |
| `a16384_b32` | **62.1%** | 25.1% | 0.0% |
| `a65536_b128` | **70.1%** | 44.2% | 0.0% |

By attacker/victim role (attacker role is **search** in 100% of
meaningful-progress episodes at every point on this diagonal, exactly
reproducing Phase 6 Q4's own attacker-side-purity finding at a fourth,
independent arena/budget scale — `core_defender`/`reactive_core_defender`
/`claimer`/`hunter` never once initiate a qualifying assault burst
anywhere on this diagonal):

| condition | search→expansion denied | search→defense denied | search→search denied |
|---|---:|---:|---:|
| `a1024_b2` | 0.0% | 0.0% | 0.0% |
| `a4096_b8` | 1.8% | 1.9% | 2.9% |
| `a16384_b32` | 15.0% | 21.5% | 20.0% |
| `a65536_b128` | 41.2% | 31.8% | 29.7% |

Full per-episode records, including roster and outcome breakdowns, are
written to `runs/research_v3_closeout/closeout_constant_density.json`
(git-ignored, reproducible by rerunning
`tools/v3_closeout_constant_density.py --all`).

---

## 12. Density-versus-absolute-quota conclusion

**Absolute action quota independently controls interaction topology at
constant density.** Denial of reaction opportunity rises from **0.0% to
34.6%** — a 64× range in absolute `instr_per_tick` (2 → 128), density
held at exactly `S = 0.781` throughout. This is not a small or
borderline effect: it is a clean, monotonic, order-of-magnitude swing
along an axis Phase 1 explicitly treated as fully explained by density
alone for ecological/occupancy purposes.

This **falsifies the strong form** of "arena size and action budget are
effectively one variable" as a *universal* claim — it was never quite
stated that strongly in Phase 1 itself (Phase 1's own claim was scoped
to occupancy, match length, and capture-rate aggregates, which this
closeout does not dispute or reopen), but it directly answers the
closeout task's own framing question and bounds Phase 1 precisely,
prospectively, without editing Phase 1's report:

> **Density explains major ecological/occupancy behavior (Phase 1's own,
> undisturbed finding). Absolute action quota independently controls
> interaction topology relative to a fixed-size decisive objective
> (`CORE_SIZE`), and this effect is invisible to any measure normalized
> by arena size.**

The mechanism is exactly Sec 9's theorem operating at increasing
strength: as `instr_per_tick` rises relative to `CORE_SIZE = 8`, an
attacker's own action block becomes large enough, more and more often,
to complete a full assault burst within a single tick — which is
precisely the condition under which an earlier-seated victim has no
guaranteed chance to react (Sec 13 confirms the boundary is exactly
`instr_per_tick >= CORE_SIZE`). Density alone cannot see this, because
density normalizes away the one thing that matters here: the absolute
size of one action block relative to a fixed-size Ruleset constant.

---

## 13. One-block-capture boundary result

New tool: `tools/v3_closeout_capture_boundary.py`. This tests a
**Ruleset capability**, not current-agent behavior: the probe's attacker
is allowed to know the victim's core address directly, because it is
testing what the scheduler and capture rule *permit*, not what a real
Agent API v1 entrant can currently discover through play. It uses the
two real, unmodified engine primitives the theorem depends on —
`battle_engine.scheduler.run_sequential_quota` and `battle_engine.vm.VM
._wr8` — directly, with no full match, scoring, or replay machinery
exercised, because none of it bears on this question.

| `instr_per_tick` | victim-owned core cells after attacker's block | captured? |
|---:|---:|:-:|
| 5 | 3 | No |
| 6 | 2 | No |
| **7** | **1** | **No** |
| **8** | **0** | **Yes** |
| 9 | 0 | Yes |

1. **Yes** — a perfectly informed attacker captures an earlier-scheduled,
   non-reacting victim in one action block at budget 8.
2. **No** — the identical attacker cannot do so at budget 7; exactly one
   victim-owned cell survives.
3. **Yes** — budget 8 is therefore a semantic boundary
   (`instr_per_tick >= CORE_SIZE`) independent of arena density: this
   probe used a fixed, arbitrary arena size and never varied it, because
   the boundary is a pure function of `instr_per_tick` versus the fixed
   `CORE_SIZE` constant, not of arena size at all.

**The shipped default (`instr_per_tick = 8`) sits exactly on this
boundary — the minimum budget at which one-block capture is even
possible in principle**, which is consistent with, and mechanistically
explains, Sec 11's finding that reaction-opportunity denial is small but
non-zero (1.9%) at the default and rises sharply only once
`instr_per_tick` exceeds `CORE_SIZE` by a wider margin (32, 128).

---

## 14. Qualified research operating region

Reconciling Phase 1 ecology, Phase 6 qualification behavior, Phase 7's
scheduler findings, and this phase's constant-density analysis, without
turning any of it into a Ruleset restriction:

* **Shipped/default condition**: `arena_size = 4096`,
  `instr_per_tick = 8`, `ticks = 400`. Phase 1 §17 found this condition,
  and its own iso-density diagonal (`a1024_b2`, `a16384_b32`), score 5/5
  on the verbatim Beta2 §17 rubric — the best in the tested 20-condition
  grid. This closeout additionally establishes it sits at the minimum
  `instr_per_tick` for which one-block capture is even mechanically
  possible (Sec 13), with correspondingly low (1.9%) reaction-opportunity
  denial (Sec 11).
* **Qualified research band**: Phase 1's own density band,
  `S` roughly in `[0.195, 0.781]` (§6.2's "usable region ... roughly a
  factor of four wide"), is not sufficient on its own once absolute
  `instr_per_tick` is varied independently of arena size. This closeout
  adds a second, independent axis of qualification:
  **`instr_per_tick` should stay at or near `CORE_SIZE` (8)** for
  research that depends on the scheduler providing a genuine,
  non-degenerate reaction window. `a16384_b32` (`instr_per_tick = 32`,
  still on the *same* density diagonal as the default) already shows
  19.5% reaction-opportunity denial and was the exact condition where
  Phase 6's own Q6/Q7 gates failed.
* **Known degraded/off-band conditions**: any `instr_per_tick`
  materially above `CORE_SIZE` (32, 128 in this closeout's own
  measurements) independently degrades interaction topology regardless
  of density, in addition to Phase 1's own already-documented
  degeneracy flags (`saturation_ceiling`, `collision_regime`,
  `interaction_starved`, `budget_starved`, `undecided`) at the density
  extremes.

The evidence supports a qualified band, not a single numeric point, but
the band is narrower once both axes are considered jointly:

> **Future strategic-mechanics experiments must justify any
> `instr_per_tick` materially above `CORE_SIZE` (8), independent of and
> in addition to justifying arena/action density, because absolute
> action quota changes interaction topology — specifically, victims'
> guaranteed reaction opportunity — in a way that density normalization
> cannot see or explain away.**

This is stated as research methodology, not a gameplay-rule change. No
default or Ruleset constant is altered by this finding.

---

## 15. Phase 6 gate-design lessons

Each architecture-review claim was checked directly against source,
committed artifacts, or a fresh, disposable re-analysis — never simply
accepted.

| claim | verified? | evidence |
|---|:-:|---|
| `a4096_b32` had already been classified as ecologically degraded in Phase 1 | **Partially true, precisely** | Phase 1 §12's rubric scores `a4096_b32` 4/5 (fails criterion 2, "above-band" per §12.1) and flags it `saturation_ceiling` (the mildest of five flags) in §6/§13. It is not among Phase 1's six flag-free conditions or its own iso-density 5/5 group, but it is also not one of the severely degenerate conditions (`undecided`, `interaction_starved`, `budget_starved`, `collision_regime`). "Degraded relative to the default" is accurate; "severely degenerate" would overstate it. |
| `a4096_b2` was also outside the strongest ecology band | **True** | Phase 1 §12: `a4096_b2` scores 4/5 (criterion 2 fails, "below-band"). It carries **no** degeneracy flag at all in §6/§13 — a real distinction from `a4096_b32`'s mild flag, worth preserving rather than treating both as equally "degraded." |
| Q6 relied on extrema with small denominators | **True** | At `a4096_b32`, Q6's non-defense maximum is `core_tracker` at 9/18 opportunity-conditioned qualifying instances (50.0%) — an *n* of 18 out of the full corpus's 594 cells. |
| uncertainty was not included | **True** | Phase 6's report states point estimates only. Recomputed here: `core_tracker`'s 95% Wilson interval on 9/18 is **[29.0%, 71.0%]** — wide enough that the reported 15.8 pp Q6 margin at `a4096_b32` is not a precise figure. Checked whether this changes the verdict: even at the *low* end of `core_tracker`'s interval (29.0%), the margin against `reactive_core_defender`'s point estimate (65.8%) would be 36.8 pp — still under Q6's 40 pp blocking bound. **The FAIL verdict is robust to this uncertainty; the point-estimate margin itself is not precise, and Phase 6 should have reported an interval.** |
| pilot-to-full-corpus margin movement was large | **True** | Phase 6's own gates file records pilot margins of 89.3 pp / 89.7 pp / 49.9 pp at `a4096_b2/_b8/_b32`; the full-corpus result was 68.6 pp / 73.4 pp / **15.8 pp** — a movement of **34.1 percentage points** at `a4096_b32` alone, more than two-thirds of the pilot's own margin. |
| Q6 and Q7 used different denominator units | **True** | Verified directly against `tools/v3_phase6_defense_episode.py`'s `qualify_condition`: Q6's rates are computed **per named agent** (`by_agent`, six entries, e.g. `core_tracker`'s own 18 opportunities), then compared across roles. Q7's rates are computed **per seat letter**, pooling *both* defense agents together by whichever seat they occupy in a given permutation cell (`opp_by_seat`/`qual_by_seat`, three entries: A/B/C). These are genuinely different aggregation units, not the same quantity sliced two ways. |
| opportunity-conditioned rate and raw event rate answer different questions | **True, already disclosed by Phase 6 itself** (§18) and reconfirmed here: e.g. `core_defender` at the default condition has a raw appearance rate of 37.0% but an opportunity-conditioned rate of 82.0% — the two differ by 45 points for the identical agent/condition because raw rate is diluted by appearances where the agent was never assaulted at all. |
| the Phase 6 implementation's episode-opening semantics should be checked against its frozen declaration | **True, and materially so — deliberate/tested, not a defect** | The frozen declaration's prose ("opens on the attacker's first acquisition of a cell the victim currently owns") describes only the direct victim→attacker case. The actual, tested code (`_open_or_extend`, exercised by `test_third_party_interruption_closes_the_original_episode_and_opens_a_new_one` in `engine/tests/test_v3_phase6_defense_episode.py`) also opens a **new** `(victim, new_attacker)` episode when a third entrant takes a cell away from an existing attacker — a chained takeover, not a direct victim acquisition. Measured directly on the committed corpus: this chained-open pattern accounts for **12.6%–13.0%** of all distinct `(victim, attacker)` episode-openings across the three budget conditions — a non-trivial fraction, not an edge case. This is intentional, already covered by an existing test, and does not change any published Phase 6 number (the same code produced them); the finding is that Phase 6 §6's plain-English declaration under-describes its own implementation's generality, which is a documentation-completeness gap worth naming precisely, not a functional error. |
| qualifying reclaim did not necessarily imply permanent successful defense | **True, and budget-dependent** | Measured directly: of victim-appearances with at least one *qualifying* (successful, survived-that-tick) reclaim, the share that are **nonetheless captured later in the same match** is 3.8% at `a4096_b2`, 3.1% at `a4096_b8`, and **21.1% at `a4096_b32`.** A "qualifying" instance is a momentary success, not a guarantee of eventual survival, and this gap widens sharply at the same high-budget condition where Q6/Q7 already fail. |

No architecture-review claim examined here was found to be incorrect.
Every one checked out either exactly as stated or with a precise
qualification recorded above. The purpose of this section, per the
governing task, is to improve future experimental protocol — report
intervals alongside point estimates, disclose denominator units
explicitly when combining rates across different aggregation levels, and
describe an implementation's actual generality in its own frozen prose
declaration — not to reopen or soften Phase 6's own verdict, which
stands unchanged (Sec 8 of `docs/V3_PHASE6_ACTIVE_DEFENSIVE_INTERVENTION_QUALIFICATION.md`
§19).

---

## 16. Full v3 evidence map

### Phase 1

Tested whether the residual Ruleset-v2 ecology is materially dependent
on arena/action density. **Durable**: arena size and action budget
collapse onto one density variable (`S`) for occupancy, match length,
and capture-rate aggregates; the shipped default sits at the optimum of
a 4000×-density-span parameter grid; `CORE_SIZE = 8` being fixed while
arenas scale is the one genuine *scale* effect in the grid. **Bounded by
this closeout** (Sec 12): density does not explain reaction-opportunity
topology, which independently tracks absolute `instr_per_tick`.

### Phase 2

Rejected locality. A bounded-reach mechanic made a fixed-size core
*incidentally* captured by any contiguous sweep passing over it, which
made blind expansion the dominant capture mechanism under locality —
the opposite of locality's intended effect. **Durable**, unweakened by
anything in this closeout.

### Phase 3

Established that decisive offense is genuinely underpaid at the shipped
`w_kill = 5`: raising it moves killer-conversion into a healthy band and
makes search competitive again, in a real (if narrow) interior region
(`w_kill` between roughly 800 and 1200). **Durable** as a payoff
characterization; **the region's practical value is constrained** by
Phase 4.

### Phase 4

Established that no existing scoring lever (`weights.alive`,
disqualified by closed-form proof; `weights.territory`, disqualified
empirically after an 11-point sweep) can restore defense's viability at
Phase 3's accepted payoff. Defense's deficit is structural: it has no
scoring event for "successfully resisted an attack." **Durable**; this
is what motivated the entire Phase 5/5A/6/7/closeout defensive-event
line.

### Phase 5A

The simplest candidate defensive event ("assaulted and survived")
failed at full-corpus scale: it could not distinguish defense from
"was the search agents' prey and simply outlasted an unfinished
assault" — expansion agents fired the event at 15–23%, far above the
2% ceiling a non-defense archetype would need.

### Phase 6

The refined candidate ("attack episode" + active reclaim, cross-tick)
qualified strongly at the shipped default and at low budgets (73.4 pp
and 68.6 pp margins) but failed two blocking gates at `instr_per_tick =
32` only, through two mechanisms it diagnosed but did not disentangle.

### Phase 7

Isolated the two Phase 6 high-budget failure mechanisms: `core_tracker`'s
own un-offset expand cursor (a real, now-identified, agent-specific
implementation choice, partially repairable) and a genuine scheduler
effect (a one-block assault denies an earlier-seated victim any chance
to react). Found the honest answer is a mixture of both, not either
alone.

### This closeout (final)

Closed the defensive-event line definitively via three independent,
convergent checks (Sec 4–8). Confirmed the scheduler-topology effect is
a real, independent absolute-quota phenomenon separable from density
(Sec 9–12), mechanically verified its exact boundary
(`instr_per_tick >= CORE_SIZE`, Sec 13), and used both results to state
a qualified research operating region as methodology rather than a
Ruleset restriction (Sec 14).

---

## 17. Rejected hypotheses

* **Locality as a gameplay mechanic** (Phase 2) — structurally
  incompatible with the fixed-size core; rejected, unweakened.
* **Any existing scoring lever compensating defense at Phase 3's
  accepted offense payoff** (Phase 4) — analytically and empirically
  disqualified for both remaining candidate weights.
* **"Assaulted and survived" as a defensive-scoring event** (Phase 5A) —
  falsified at full-corpus scale; not selective for defense.
* **"Attack episode + active reclaim" as a Ruleset-invariant
  defensive-scoring event** (Phase 6/7, reaffirmed by this closeout) —
  fails budget/seat robustness for reasons independently confirmed to be
  a mixture of an agent-specific implementation artifact and a genuine
  scheduler property, not threshold or window mis-calibration.
* **Ownership-transition history as a proxy for defensive intent, in
  any form** (this closeout, Sec 4–8) — closed: a fully deterministic,
  attack-blind agent perfectly predicts its own "defensive" credit, a
  more evidence-driven agent does not consistently outperform it, and a
  strictly less intelligent probe matches or beats both real reference
  defenders.

---

## 18. Remaining open hypotheses

* **A modest, independently-justified compensating mechanism for
  defense specifically** (Phase 3/4's own stated successor question) —
  still open in the sense that no existing scoring lever works, but this
  closeout adds evidence that the most promising *event-based* candidate
  investigated across Phases 5–7 does not survive scrutiny either. The
  honest status is: **no known mechanism**, existing or newly proposed
  and tested, currently closes this gap.
* **Whether a scheduler/quota-semantics change could meaningfully
  improve the ecology** — genuinely open as a research question (never
  modeled at any point in this program), but **not evidenced** either
  way: nothing in Phases 1–7 or this closeout ever executed a match
  under a hypothetical alternative scheduler, so there is no ecology
  data to weigh a change against. This is a possible future research
  direction, explicitly not a justified one.
* **Whether new Agent API telemetry could someday distinguish
  responsive defense** — open only as a possibility (Sec 8's four
  categories), not evidenced as necessary or sufficient for anything.

---

## 19. Candidate change inventory

### Option A — No Ruleset change

Preserve Ruleset v2 mechanics; retain current shipped defaults; document
the qualified research operating conditions (Sec 14) as methodology, not
policy. **Strongly supported** by every phase of this program: no
investigated semantic change survived its own qualification standard.

### Option B — Configuration/default or v2.x balance change

`w_kill` (offense payoff) is the only candidate with a real, measured
interior region (Phase 3, roughly `w_kill ∈ [800, 1200]`) — but Phase 4
found that region cannot be paired with any existing lever that keeps
defense above its own predeclared floor. Raising `w_kill` as a shipped
default would be a genuine, disclosed tradeoff (more competitive
offense/search, less viable defense), not a strict improvement. **Not
recommended without further, not-yet-conducted defense-compensation
research** — this is consistent with Phase 3/4's own conclusion, not a
new finding.

### Option C — New Ruleset semantics

* **Scheduler/quota semantics** (e.g. round-robin or interleaved
  scheduling to guarantee a reaction window) — a real Ruleset-level
  property was found (Sec 9–13), but it is concentrated at
  `instr_per_tick` values well above the shipped default and was never
  shown to degrade the shipped ecology (default-condition denial: 1.9%).
  **Possible; not justified by current evidence.**
* **Capture-resolution timing** — bound up with the same scheduler
  question; no separate evidence was gathered. **Possible; not
  justified.**
* **Core semantics** (`CORE_SIZE`, hold-duration capture) — never
  directly tested anywhere in Phases 0–7 or this closeout; explicitly
  out of scope throughout. **Neither supported nor contradicted; not
  addressed.**
* **New defensive scoring event** — **contradicted** by this closeout's
  own evidence (Sec 4–8). Not recommended under any current design.

### Option D — Agent/API semantic expansion

Only plausible as a prerequisite for a defensive-scoring mechanism this
closeout has just closed. **Possible in the abstract (Sec 8's four
categories); not justified** by any evidence gathered in this program,
since the mechanism it would serve is not being pursued.

### Option E — Close v3 without Ruleset 3

**This is the outcome this closeout's evidence supports.** A version
line does not require a new Ruleset merely because the research branch
was called v3; treating a comprehensive null/negative result as the
program's actual finding is itself a legitimate, valuable research
outcome, not a failure to find something.

---

## 20. Ruleset decision matrix

| Candidate change | Evidence for | Evidence against | Requires Ruleset bump? | API impact | Historical compat. impact | Strategic upside | Risk | Recommendation |
|---|---|---|:-:|---|---|---|---|---|
| **No change (status quo)** | Phases 1–7 + this closeout: every investigated semantic change failed its own qualification standard; shipped default is at Phase 1's measured optimum and sits at (not past) the one-block-capture boundary with low reaction-opportunity denial (1.9%) | None identified | No | None | None | Stability; research base remains valid | None | **Adopt** |
| **Raise `w_kill` default (~800–1600)** | Phase 3: real interior region satisfying offense-viability gates simultaneously | Phase 4: no existing lever keeps defense ≥15% win share in that same region; near-coincident crossing, not a genuine bracket | No (config-level, already identity-hashed) | None | None (already-existing field; only its range widens) | Fixes offense underpayment | Defense archetype viability drops materially | **Not recommended now** — needs a defense-compensation mechanism that does not currently exist |
| **New defensive scoring event (ownership-history based)** | Phase 6 qualified strongly at low budgets and the default | Phase 5A same-tick premise falsified; Phase 6 fails budget/seat robustness at high budget; this closeout: blind timer 100% match, no consistent reactive advantage, turtle probe matches/exceeds real defenders | Would have (scoring-formula change), moot | None needed (rejected) | None (rejected) | None demonstrated | Rewards blind/turtling behavior over genuine defense | **Do not pursue — line closed** |
| **Scheduler/quota-semantics change** (e.g. guaranteed reaction window) | Real, mechanically verified Ruleset-level property (Sec 9, 13); reaction-opportunity denial rises from 0% to 34.6% along a constant-density diagonal | Effect is small (1.9%) at the shipped default; never modeled against any real ecology; no agent population was shown to exploit it pathologically at default settings | Yes | Potentially broad (changes first-mover dynamics generally) | Would invalidate/change every prior evaluation's timing assumptions | Unknown — untested | High (sweeping, unmodeled scope) | **Not justified now** — record as methodology (Sec 14), not a change to pursue |
| **Core-size / hold-duration capture change** | None gathered | None gathered | Yes | Unknown | Unknown | Unknown | Unknown | **Not addressed** — out of scope throughout the program |
| **New Agent API telemetry for defensive intent** | Only as a hypothetical prerequisite for a now-closed scoring line | No concrete design evaluated; self-report intent is trivially gameable | Yes | Direct | Unknown | Speculative | Speculative | **Not justified** |

---

## 21. Ruleset necessity verdict

### **NO RULESET CHANGE CURRENTLY JUSTIFIED — V3 RESEARCH SHOULD CLOSE WITHOUT A NEW RULESET**

Every semantic-change candidate actually investigated across Phases
0–7 and this closeout failed its own predeclared qualification standard,
was structurally disqualified by direct proof, or — in the one case with
a real, measured effect (scheduler topology) — was shown to be
concentrated well outside the shipped operating condition and was never
evidenced to degrade the shipped ecology. This verdict does not decide
the v3.x product/versioning plan; it answers only whether the research
has produced sufficient evidence to justify changing gameplay semantics.
It has not.

---

## 22. Compatibility/API implications

Explicit, per the governing task's Sec 19 instruction to never conflate
version number with Ruleset identity:

* **`BYTEFRAY_RULESET_ID`** (`engine/src/battle_engine/rules.py`) —
  Ruleset v1's stable identity, `"bytefray-rules-1"`.
* **`BYTEFRAY_RULESET_V2_ID`** (`engine/src/battle_engine/ruleset_policy.py`)
  — Ruleset v2's stable identity, `"bytefray-rules-2"`, shipped as
  Bytefray v2.0's default and unchanged by this program end to end.
* **This closeout changes neither.** No new Ruleset identity was
  created (unlike Phase 2's disposable `bytefray-rules-3-alpha1`, which
  this phase does not touch or revive). No Agent API field, result/
  replay/evaluation schema, or scoring formula was changed.
* A future Bytefray software release reaching v3.x does **not**
  automatically require a `bytefray-rules-3` identity. Per this
  closeout's own verdict (Sec 21), nothing evidenced here currently
  justifies creating one at all.

---

## 23. Validation/performance

| check | result |
|---|---|
| Frozen `v2-baseline` population | **9/9** verify, before and after this phase's work |
| Historical Phase 0–7 reports | present, unmodified; no historical conclusion rewritten |
| Phase 5A/6 gate files | present, unmodified (`v3_phase5a_defensive_event_gates.json`, `v3_phase6_active_defense_gates.json`) |
| Phase 6 detector reused | `tools/v3_phase6_defense_episode.py` imported by every new closeout tool; diff against `v3-research-phase7` is empty for this file |
| Phase 7 predicate reused | `had_reaction_opportunity` imported directly from `tools/v3_phase7_confound_isolation.py`; not copied or re-derived |
| New matches executed | **162** (E8 turtle-probe corpus: `hunter`/`reactive_core_defender`/`core_seeker`-shaped roster with `core_defender` replaced by the disposable turtle probe, 3 seeds × 3 layouts × 6 seat permutations × 3 budget conditions) |
| Re-analyzed, zero-new-match artifacts | D1 blind-timer prediction (3 budget conditions, full 594-cell corpora); blind-vs-reactive discriminant (3 conditions); constant-density scheduler analysis (4 conditions, 594 cells each, 2,376 cells total) |
| Disposable probes | `turtle_core_refresher` — never registered in any `BenchmarkPopulation` manifest, never added to `v2_baseline_corpus.json`; labeled `research probe only` / `non-gate benchmark agent` / `not part of frozen v2-baseline` in its own manifest and docstring |
| Theoretical/mechanical probes | one-block-capture boundary (`tools/v3_closeout_capture_boundary.py`) — no match executed, direct engine-primitive construction only |
| New tests | `engine/tests/test_v3_closeout.py` — 8 focused tests (blind-schedule correctness, capture-boundary monotonicity, turtle-probe behavior) |
| Focused new tests | 8/8 passed |
| Full test suite (`python -m pytest`) | **Exit code 0 — all tests pass**, run twice for reproducibility. This environment's own summary-line output was not reliably capturable across a long run (a pre-existing terminal-capture quirk, not a test failure — verified by exit code and by explicit collection); no pre-existing test was altered, removed, or newly skipped by this phase's changes |
| `ruff check` (new files) | All checks passed |
| `mypy engine/src/battle_engine` | Success, 83 source files |
| No Ruleset/API/schema/default changed | Confirmed (Sec 22) |
| Existing Phase 1 artifacts remain loadable | Confirmed — every closeout tool reads the same committed `result.json`/`replay.jsonl` artifacts Phase 6/7 already used, with zero modification |
| All read-only reanalysis deterministic | D1's blind schedule is a pure function of its inputs (tested directly); Phase 6/7's own reconstruction was already proven deterministic and is reused unmodified here |

---

## 24. Commits

Sequence, per the governing task's suggested discipline (this phase is
confirmatory re-analysis of already-frozen detectors and mechanically
fixed Ruleset constants — `CORE_SIZE`, the Phase 6 threshold/window, the
S≈0.781 diagonal — none of which this phase tunes or chooses after
seeing a result, so no new gate-declaration file with numeric bounds was
needed the way Phases 5A/6 required one for a genuinely new candidate
threshold):

1. Closeout measurement tools and tests (`tools/v3_closeout_*.py`,
   `engine/tests/test_v3_closeout.py`, the disposable
   `turtle_core_refresher` probe agent).
2. This report (`docs/V3_RESEARCH_CLOSEOUT.md`).

Nothing merged to `main`. Nothing tagged. Nothing pushed.

---

## 25. Recommended next step

Stated, not implemented, per the governing task's explicit instruction:

> If future research wants to revisit defense's structural deficit
> (Phase 4's still-open economic finding), it should not restart from
> another ownership-history detector — this closeout shows that whole
> family of approaches is now closed. A more promising direction, if
> pursued at all, would start from the observation that this closeout's
> own D1/E8 results needed to know *why* an action was taken (attack-blind
> timer vs. evidence-driven response), not merely *that* an ownership
> transition occurred — which point toward execution-trace-level
> telemetry (Sec 8's second category) as the more promising, though
> still entirely unevaluated and unimplemented, category to design and
> qualify from scratch, with its own anti-gaming analysis, before any
> further defensive-scoring experiment is attempted.

This is not implemented here, and pursuing it is not endorsed as the
program's actual next step — it is recorded only because the governing
task asked what the next evidence question would be if defense's deficit
is revisited at all. The next conversation should decide, independent of
this recommendation, what a v3.x software release should contain and
whether it needs a new Ruleset identity — which, per Sec 21, current
evidence says it does not.
