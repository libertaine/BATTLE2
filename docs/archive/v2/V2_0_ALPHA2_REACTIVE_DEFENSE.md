# Bytefray v2.0.0-alpha.2 — Reactive Core Defense

This is the implementation and evaluation record for the second Bytefray
v2 experiment, testing **reactive core defense** as a candidate fix for
alpha.1's central negative finding: Core Defender, as originally
implemented, never improved its outcome against any opponent and lost
every matchup against the one opponent (Core Seeker) built specifically
to test it
([V2_0_ALPHA1_EVALUATION.md](V2_0_ALPHA1_EVALUATION.md) §9-10). This
document records what was actually built, what the controlled evaluation
actually measured, and an honest, falsifiable recommendation — not a
claim that reactive defense solves Bytefray's "expansion dominates"
tension in general.

Branched from the verified alpha.1 baseline, commit
`46596548a81d9cec01e1dc9279a4241a82395e5a` on `v2.0-development` (`main`
unchanged at the v1.6.0 baseline throughout this work). This document is
committed alongside the implementation; `git log` on `v2.0-development` is
the authoritative record of the exact commit this evaluation ran against.

`bytefray-rules-2-alpha1` is **not** promoted to a permanent Ruleset v2 by
this document. It remains an internal experimental identity.

## 1. Alpha.1 baseline (unchanged in this experiment)

Per the governing task, every alpha.1 mechanic parameter was held fixed:
`CORE_SIZE = 8`, `arena_size = 4096`, `instr_per_tick = 8`, 200-tick
budget, subject-at-`0`/opponent-at-`arena_size // 2` placement, spawn-time
core ownership seeding, capture semantics (owns zero core cells),
capture timing (after actions, before scoring), kill attribution, scoring,
Core Seeker's implementation, the `1,2,3,4,5` seed set, and the persisted
`bytefray-rules-2-alpha1` identity. No new experimental Ruleset ID was
created — this is the same rules experiment, testing a new entrant
strategy. `vm.py`, `scoring.py`, `results.py`, and `bytefray-rules-1` were
not touched.

## 2. Why the original Core Defender failed (Phase 3 analysis)

Direct inspection of `core_defender/agent.py` (unchanged by this work)
confirms it is a *timer*, not a *response*:

- It refreshes one of its 8 core cells every 4th action, cycling through
  all 8 in a fixed round-robin, **unconditionally** — whether or not that
  cell has been touched since it was last refreshed.
- It never issues a single `READ`. It has no way to *know* whether its
  core is intact, partially lost, or already gone; "defense" is a
  25%-of-actions tax paid at all times, attack or no attack.
- It cannot distinguish "refreshing a cell I already own" from "reclaiming
  a cell I just lost" — every refresh action costs the same regardless of
  whether it was needed.
- Its expansion path (the other 75% of actions) is an ordinary
  Claimer-style blind sweep — behaviorally, "defense" for this agent is
  indistinguishable in kind from ordinary claiming, just aimed at a fixed
  target set on a fixed clock.
- **Response latency, not lack of budget, was the specific failure
  mechanism.** A full defend cycle (touching all 8 cells once) takes 32
  actions = 4 ticks. Core Seeker's committed assault burst is 16 actions =
  2 ticks. Direct replay inspection of the alpha.1
  `core_defender` vs `core_seeker` matchup showed the burst landing across
  ticks 139-140 while the defender's own fixed-clock refresh, uncorrelated
  with the attack, touched unrelated cells at the wrong moments — it lost
  its whole core every single time, at the identical tick (140), across
  all 5 seeds (Core Seeker never reads `context.rng`, so it is fully
  deterministic given a fixed matchup/placement).

## 3. What an ordinary Python entrant can actually observe

Verified directly against `agent_api.py` and `python_runtime.py`, not
assumed: `Observation` carries exactly `tick`, `agent_id`, `pc`,
`register_a`, `register_p`, `zero_flag`, `last_read`, `alive` — no
ownership map, no opponent state of any kind. The *only* channel through
which an agent can learn what is currently stored anywhere in the arena is
a `READ`, which returns one raw byte **value**, not an owner
(`python_runtime.apply_action`: `READ` sets `state.last_read =
vm.arena[operand % len(vm.arena)]`; nothing about ownership is ever
exposed to Python code). This is the same constraint Core Seeker's own
`_looks_foreign` heuristic already works under from the attacker's side.

This means true reactive defense through Agent API v1 is possible, but
only as a **content-based proxy for ownership**, not a direct ownership
read: an agent that always knows what it last wrote to its own core can
treat *"the byte here no longer matches what I put here"* as evidence of
an external write. This is legitimate, ordinary-API evidence — but it is
provably imperfect: an opponent who happened to write the *exact* byte
this agent last wrote there would go undetected by content comparison
alone, since two different owners writing the identical value are
indistinguishable through `READ`. No mechanism exists in Agent API v1 to
close this gap; it is an inherent limitation of the interface, not an
implementation shortcoming. This is recorded as evidence for a possible
future Agent API v2 field (an explicit ownership-adjacent signal), not
implemented here per the governing task's scope exclusions.

## 4. Reactive Core Defender design

New reference agent, `reactive_core_defender`
(`battle_engine/data/reference_agents/reactive_core_defender/agent.py`),
added alongside (not replacing) the original `core_defender`, so direct
comparison remains possible. Deliberately excluded from
`battle_engine.starters.STARTER_AGENT_NAMES`, exactly like the other two
v2.0.0-alpha reference agents.

**No privileged information.** Structurally provable, not just claimed:
`Observation`'s dataclass fields (verified by
`test_observation_carries_no_opponent_state_the_agent_could_read`) contain
nothing about any other entrant. The agent's own core anchor is captured
from `observation.pc` on its first `act()` call — the same
already-established technique the original Core Defender uses, and the
same value the entrant's `pc` is already initialized to before any `JUMP`
(`python_runtime.PythonEntrantState.pc`'s construction). A dedicated test
(`test_behavior_before_any_damage_is_identical_regardless_of_opponent`)
confirms this agent's own core-directed action sequence is byte-identical
regardless of whether the opponent is idle or actively writing elsewhere
in the arena, before any damage occurs — nothing about a specific opponent
leaks into this agent's behavior.

Three phases:

- **SIGN** (one-time, first 8 actions only): claims every core cell with
  its own distinctive signature byte (`0xC7`), one cell per action. This
  establishes a known, agent-chosen baseline for content comparison
  instead of relying on the arena's shared untouched-default byte (`0`),
  which narrows (but per §3, does not close) the false-negative gap. Costs
  8 actions total out of a match's full budget (up to 1,600), not a
  recurring cost.
- **PATROL** (steady state): one action in every 4 (`REFRESH_EVERY`,
  chosen to match the original Core Defender's own defend cadence, so the
  two are directly comparable on "how often is a core-related action
  taken") is a `READ` at a rotating core-cell cursor, compared against
  this agent's own record of what it last wrote there. The other 3 of
  every 4 actions are an ordinary Claimer-style outward sweep starting
  just past the defended region. Unlike the original, a healthy core
  produces **zero** `WRITE`s to the core after the one-time SIGN pass —
  proven directly by `test_does_not_continuously_rewrite_a_healthy_core`
  (excluding the engine's own tick-0 `seed_core_ownership` step, which is
  not this agent's decision).
- **ALERT** (triggered the instant a mismatch is found): the damaged cell
  is repaired immediately (one `WRITE`), then every other core cell is
  checked in turn at full priority over expansion — one `READ` per cell,
  with a repair `WRITE` only for cells actually found mismatched, never a
  blind rewrite of cells with no evidence against them. Once a full pass
  confirms the core clean, this agent returns to PATROL.

A fixed round-robin patrol order was kept over a randomized one after a
direct, evidence-based A/B test (§8) — see that section for why the
"obvious" fix was reverted.

## 5. Acceptance tests (Phase 5)

`engine/tests/test_v2_alpha2_reactive_defender.py`, 15 tests, all passing.
Beyond ordinary Agent API v1 lifecycle and roster-exclusion checks, this
suite directly proves: no privileged information (structural field check +
behavioral opponent-independence check); expansion continues while the
core is healthy; zero ongoing core rewrites absent an attack; a single
damaged cell is detected and repaired through genuine PATROL-driven
detection (not incidentally by the one-time SIGN pass — an early version
of these tests initially, and incorrectly, credited SIGN's own
unconditional first pass for what looked like "detection," and was
corrected once traced against the real per-tick replay diffs); a fast
behavioral pivot follows detection; a fully-damaged core recovers when
attacked one cell at a time with realistic spacing; the agent returns to
ordinary expansion once damage is resolved; deterministic behavior given
identical input; correct repair when the core wraps the arena end; and no
alteration of Ruleset v1 semantics. Two acceptance-test iterations
(documented directly in the test file's own comments) were needed to
correct unrealistic timing assumptions — see §8 for the one design
correction those iterations actually motivated.

## 6. Pre-matrix (Phase 6) gate

Before the full matrix, a 6-cell, 5-seed pre-matrix
(`runs/v2_0_alpha2_evaluation/pre_matrix.py`,
`runs/v2_0_alpha2_evaluation/pre_matrix.json`) checked for an obviously
useless or pathological design:

| Matchup | Subject wins | Subject core-captured |
|---|---:|---:|
| Reactive Core Defender vs Core Seeker | 0/5 | **0/5** |
| Core Defender (original) vs Core Seeker | 0/5 | **5/5** |
| Claimer vs Core Seeker | 5/5 | 0/5 |
| Hunter vs Core Seeker | 0/5 | 5/5 |
| Reactive Core Defender vs Claimer | 0/5 | 0/5 |
| Reactive Core Defender vs Hunter | 0/5 | 0/5 |

Zero captures against Core Seeker, no universal dominance (still loses to
Claimer and Hunter, exactly as the original defender does) — this cleared
the gate to run the full matrix without further tuning.

## 7. Full evaluation matrix (Phase 7)

`runs/v2_0_alpha2_evaluation/run_evaluation.py`, executed directly through
`NativeMatchService` (the same production execution boundary every other
native match uses), reusing `battle_engine.evaluation_analysis`'s existing
Wilson-interval and exact-sign-test machinery unchanged.

- **Agents (8):** the five original Python starters (claimer, strider,
  hunter, wanderer, adaptive) + all **three** reference agents
  (`core_defender`, `core_seeker`, `reactive_core_defender`) — the
  original two alpha.1 reference agents are preserved unchanged alongside
  the new one.
- **Matchups:** every unordered pair, `C(8,2) = 28`, both orientations
  (56 ordered matchups) — the entrant playing "subject" always starts at
  `0`, "opponent" always at `2048`, identical to alpha.1's convention.
- **Seeds:** `1, 2, 3, 4, 5`, identical to alpha.1.
- **Conditions:** `bytefray-rules-1` (control) and
  `bytefray-rules-2-alpha1` (experimental), `Config` at the same defaults
  (`arena_size=4096`, `instr_per_tick=8`, `max_ticks=200`).
- **Total: 28 × 2 × 5 × 2 = 560 matches.** Completed in 38.0s, **0
  infrastructure failures** (no forfeits, no diagnostics, no crashes).
  Raw per-match records and the computed summary are in
  `runs/v2_0_alpha2_evaluation/{raw_matches,summary}.json` (untracked
  local scratch, per `.gitignore`'s existing `runs/` entry — this document
  is the durable, committed record).

## 8. The one design correction actually made, and the one that was reverted

Per the governing task's "one evidence-driven design correction is
acceptable if the first implementation contains a clear conceptual flaw"
allowance, exactly one correction was investigated, evidence-tested, and
then **reverted** rather than kept — recorded here in full because the
reasoning matters as much as the result.

While writing acceptance tests, a synthetic scripted attacker that wrote
all 8 core cells in the *same ascending order* the fixed patrol cursor
also visits, spread across several ticks, defeated the reactive defender
even though the attack was much slower than the patrol cadence: the
patrol cursor was always checking the cell the attacker had *just about
to* hit, or had *just* finished hitting a moment earlier in the same tick
— a "phase-matched" evasion. A randomized-patrol-order variant (reshuffled
each full pass, using this entrant's own seeded `MatchContext.rng`, so
determinism-per-seed is preserved) was built specifically to close this.

Directly A/B tested against the real, bundled Core Seeker (not the
synthetic attacker) across seeds 1-8, same fixed placement: the **fixed**
order survived 8/8 seeds; the **randomized** order survived only 4/8. The
randomization was reverted. The reasoning: no real Agent API v1 opponent
can ever observe this agent's internal inspection schedule — a `READ`
produces no signal visible to any other entrant, and `Observation` exposes
nothing about another entrant's actions — so the "phase-matched" attacker
is not constructible by any agent bound by the same API this experiment
is scoped to test; it required knowledge (this agent's exact internal
cursor phase) no ordinary opponent could obtain. Fixing a threat model
unreachable through the governing API, at a measured cost to performance
against the actual opponent under test, would have been tuning against a
benchmark artifact rather than a real weakness. This is recorded directly
in the shipped agent's own docstring (`_reshuffle_patrol_order` is not
present in the final code; the docstring explains why) so a future
session does not rediscover and re-revert the same thing.

## 9. Primary result: Reactive Defender vs Core Seeker

10 cells per defender (5 seeds × 2 orientations: defender-as-subject@0 and
defender-as-opponent@2048).

| Defender | Core-captured | Survived | Wilson 95% (capture) |
|---|---:|---:|---|
| Core Defender (original) | 5/10 | 5/10 | [23.7%, 76.3%] |
| Reactive Core Defender | **0/10** | **10/10** | [0.0%, 27.8%] |

Zero overlap in the *observed* proportions (0 vs 5 of the same n=10), and
the finding is fully deterministic and reproducible (Core Seeker never
reads `context.rng`, so every seed converges on the identical outcome
within an orientation) — but with only 10 cells per defender the Wilson
intervals are wide and technically overlap at their boundary; this is
reported as a clean, reproducible, mechanistically-explained directional
result, not as a large-sample statistical certainty. A separate,
seed-only acceptance check
(`test_survives_core_seeker_where_the_original_defender_never_did`, seeds
1-8, defender-as-subject orientation) independently confirms 8/8 survival
in the harder of the two orientations (§10).

**Termination:** every one of the original defender's 5 losses in the
vulnerable orientation was `core_captured` at the identical tick (140),
matching alpha.1 exactly. The reactive defender's matches against Core
Seeker all ran the full 200-tick budget (`tick_limit`) in both
orientations — it never lost the race outright, it simply never won on
raw score either (§11).

## 10. Orientation sensitivity — an important, previously under-reported finding

Core Seeker's own success rate against **every** victim in this matrix is
completely orientation-dependent, not just placement-neutral behavioral
skill:

| Victim | Seeker as subject (@0), victim @2048 | Seeker as opponent (@2048), victim @0 |
|---|---:|---:|
| strider | 0/5 captured | 5/5 captured |
| hunter | 0/5 captured | 5/5 captured |
| wanderer | 0/5 captured | 1/5 captured |
| core_defender (original) | 0/5 captured | 5/5 captured |
| reactive_core_defender | 0/5 captured | 0/5 captured |

Every single capture in this entire 560-match matrix occurred with Core
Seeker at address `2048` and the victim at address `0` — never the
reverse. This is a fixed-address artifact of Core Seeker's own
implementation, not a mechanic property: `CoreSeekerAgent.reset` seeds
`scan_cursor = context.arena_size // 3` and a fixed `scan_stride`
regardless of the entrant's own start address, so Seeker's absolute scan
schedule over the arena is identical no matter which role it plays —
whether it happens to reach a core sitting at address `0` versus address
`2048` within the 200-tick budget is a fact about that fixed schedule
relative to those two fixed points, not about "finding cores" in general.
Alpha.1's own report already reflected this same structure implicitly
(every capture count is phrased as "(5/5 seeds)" for one specific
orientation, never "10/10"), but did not call it out explicitly. It is
called out explicitly here because it directly qualifies §9's headline
number: **the Reactive Defender's 0/10 result includes the one
orientation that reliably captures every other tested victim** — this is
the most important single fact supporting that the improvement is real
defensive behavior, not a benefit of an easier placement. It is not
evidence that Core Seeker "can't" capture a core at address 2048 in
general; it is evidence that it does not, specifically, within this fixed
harness's placement convention and tick budget.

## 11. Does reactive defense create a real tradeoff, or a free upgrade?

This is the central question, and the full matrix gives a nuanced, honest
answer.

**General-population competitiveness — nearly cost-neutral relative to
blind defense, but both remain globally non-competitive.** Against the
five original starters (claimer, strider, hunter, wanderer, adaptive),
both defenders lose every single matchup, both orientations, all seeds:
**0/10 wins each**, for both the original and the reactive defender. Score
margins are close between the two designs (reactive trails the original
by roughly 40-90 points / 2-4% per matchup — e.g. vs claimer: original
-615, reactive -684; vs strider: -2047 vs -2069; vs hunter: -618 vs -657;
vs wanderer: -565 vs -613; vs adaptive: -473 vs -558) — a small, consistent
efficiency gap, not a new liability. The most likely mechanical cause: the
original defender's blind refresh is always a `WRITE` (which claims
territory even when wastefully re-claiming an already-owned cell),
whereas the reactive defender's steady-state `READ`-based patrol claims
**zero** territory by construction — the same fraction of budget is
diverted from expansion in both designs, but the original's diverted
budget still contributes to score while the reactive design's does not.

**Reactive Core Defender never wins a single match in this entire
matrix — 0/70 across both rulesets.** This must be stated plainly, not
minimized: defense (of either kind) remains completely non-competitive by
raw win rate in this ruleset/scoring regime, exactly reconfirming the
architecture document's own pre-alpha finding (§2 of
[V2_0_ALPHA_ARCHITECTURE.md](V2_0_ALPHA_ARCHITECTURE.md)) that
unrestricted expansion is close to dominant. Alpha.2 does not change that
underlying fact and was not scoped to. What alpha.2 *does* change is
narrower and real: **given that an entrant has already chosen to defend
its core, doing so reactively instead of blindly is a strict improvement**
— same general-population cost, zero core-capture vulnerability instead
of a 50%-of-vulnerable-orientation capture rate.

**The existing win/loss-rank paired statistic cannot see this
improvement.** The exact-sign-test machinery classifies outcomes only as
`improved`/`regressed`/`unchanged` by win > tie > loss rank. Because
Reactive Core Defender's win/loss outcome is identical (`loss`) under both
`bytefray-rules-1` and `bytefray-rules-2-alpha1` in all 35 of its paired
cells (it never wins under either), every one of its cells classifies as
`unchanged` — the paired test reports **zero signal** for the one agent
whose behavior most meaningfully changed. The real improvement is visible
only in `termination_reason` (never `core_captured`, vs. the original's
5/10) and in score margin (a near-even race, -31 points, against Core
Seeker specifically, instead of an outright capture). This is an honest
methodological limitation of the existing rank-based paired statistic when
applied to an agent whose baseline win rate is already zero — not a defect
in the reactive design, but worth carrying forward: a future evaluation of
any zero-baseline defensive strategy should not rely on the paired
win-rank test alone.

**No universal dominance.** Confirmed directly — 0/70 overall win rate is
about as far from "universally dominant" as a design can be.

## 12. Reactive Defender vs Claimer / vs Hunter (explicit matchups requested)

| Matchup | Wins | Core-captured (either side) | Score margin (subject role) |
|---|---:|---:|---|
| Reactive Core Defender vs Claimer | 0/10 | 0/10 | -684 (1700 vs 2384) |
| Reactive Core Defender vs Hunter | 0/10 | 0/10 | -657 (1714 vs 2371) |

Both are clear, uncontested losses on raw score — Claimer and Hunter's
unrestricted expansion is untouched by the core mechanic (neither has ever
been core-captured, in alpha.1 or here) and neither is threatened by the
reactive defender's own design, which does not attack. This is the
expected shape of "specialization, not dominance": the reactive defender
trades a chance at beating pure-expansion strategies (a trade the original
defender already made and lost) for immunity to the one strategy in this
population that specifically hunted cores.

## 13. Reactive Defender vs original Core Defender (direct head-to-head)

Both orientations, all 5 seeds, fully deterministic (neither design uses
`context.rng` for anything that varies the outcome): the original Core
Defender beats the Reactive Core Defender **10/10**, by an identical
39-point margin regardless of orientation (2005 vs 1966). The original's
always-`WRITE` refresh generates slightly more raw territory than the
reactive design's `READ`-heavy patrol (§11) — in a matchup where neither
agent is attacking the other's core (neither design seeks), the pure
territorial-efficiency question is won by the design that never spends
actions on non-claiming inspection. This is a real, honestly-reported cost
of switching to content-based reactive inspection, small in magnitude
(39 of ~2,000 points, under 2%) but consistent.

## 14. Territory retention, score effects, match duration

`territory_retention` (`last / max`) is **identical between the original
and reactive defenders in this population**, and identical between
rulesets for each: `core_defender` = 0.8808 (both v1 and alpha),
`reactive_core_defender` = 0.9325 (both v1 and alpha) — reactive actually
retains more of its own peak territory on average, though this is
dominated by the many non-Seeker matchups where neither design ever loses
already-claimed ground, exactly matching alpha.1's own finding that this
metric does not widen or spread differently under the alpha condition for
this population. It is not a differentiator here, consistent with, not
contradicting, alpha.1.

Mean match duration: `bytefray-rules-1` matches always run the full 200
ticks (`tick_limit`, 100% of 280 cells). Under `bytefray-rules-2-alpha1`,
mean ticks run = 197.3 (264/280 = 94.3% still resolve by `tick_limit`,
16/280 = 5.7% end via `core_captured`, mean tick-of-capture = 153.5,
capture ticks observed: 140 for all `core_defender` captures, 156 for the
single `wanderer` capture, 160 for both `strider` and `hunter` captures —
each deterministic per victim across all 5 seeds).

## 15. Alpha.1 subset reproducibility (Phase 10)

The 420-match subset of this run restricted to the original seven alpha.1
agents (excluding `reactive_core_defender` on both sides of every cell)
reproduces alpha.1's own findings exactly:

- 420 cells (210 v1 + 210 alpha), matching alpha.1's total exactly.
- Core-capture rate: 16/210 = 7.619...%, matching alpha.1's reported 7.6%
  exactly.
- Capture victim distribution: strider (5/5 seeds), hunter (5/5 seeds),
  wanderer (1/5 seeds), core_defender (5/5 seeds) — attacker `core_seeker`
  in all 16 cases — byte-for-byte identical to alpha.1 §6.
- Paired exact-sign test: **0 improved, 22 regressed, 188 unchanged**,
  exact two-sided p = 4.76837158203125×10⁻⁷, direction `favors_baseline`
  — matching alpha.1's reported "0 improved, 22 regressed, 188 unchanged,
  p≈4.8×10⁻⁷" exactly.
- Claimer's own outcome is untouched by adding the new agent (still never
  core-captured; its regressions are still the same score-margin effect,
  §16).

No divergence was found. Adding `reactive_core_defender` contributed
**zero** additional regressed cells to the paired comparison (22 in the
420-cell subset, still exactly 22 in the full 560-cell superset) — every
one of the 140 newly-added cells classifies as `unchanged` by the win-rank
test (§11 explains why for the defender's own matches specifically; the
other new cells simply don't shift any existing agent's win/loss outcome).

## 16. Core-seeding score-margin side effect (Phase 11) — tracked, not fixed

Verified present, unchanged, and fully explaining the same 6 non-capture
regressed cells alpha.1 documented:

- `claimer` vs `hunter`, all 5 seeds: score `2281` (v1) → `2294` (alpha),
  flipping `win` → `loss` — identical to alpha.1's reported values.
- `wanderer` vs `adaptive`, seed 4 only: `2183` → `2193`, flipping `win` →
  `loss`; seeds 1, 2, 3, 5 unaffected (`2205→2219`, `2203→2210`,
  `2220→2234`, `2209→2223`, all still `win`) — identical to alpha.1.

This is `seed_core_ownership`'s mutual 8-cell head start (§2 of
[V2_0_ALPHA1_EVALUATION.md](V2_0_ALPHA1_EVALUATION.md)), not touched by
this experiment, and confirmed here to interact identically regardless of
which agents are added to the population. No new instance of this effect
was found anywhere in `reactive_core_defender`'s own 70 alpha-condition
cells — it never wins under either ruleset, so there is no win-to-loss
score-margin flip for it to exhibit. This remains a known, deliberate,
mutually-applied experimental side effect, not a correctness defect, per
the governing task's instruction to track rather than fix it in this
phase.

## 17. Exploits and pathologies considered

- **No self-overwrite loop.** The ALERT phase is bounded (at most 8 repair
  actions per triggered episode) and always terminates back to PATROL;
  confirmed directly by the acceptance suite and by every full-matrix
  match completing without a diagnostic.
- **No trivializing exploit found against the reactive design.** Nothing
  in this evaluation produced a "the reactive defender secretly wins
  everything" or "the reactive defender can be tricked into permanent
  self-overwrite" result.
- **The one real, understood limitation is §3's content-vs-ownership
  gap** (an opponent writing the exact expected byte evades detection) —
  not observed as exploited by the actual bundled Core Seeker (its
  signature, `0x5E`, never coincides with the defender's `0xC7`), but a
  documented, inherent Agent API v1 limitation, not a design flaw.
- **The reverted randomized-patrol variant (§8) is itself a documented,
  considered-and-rejected pathology-avoidance attempt** — worth keeping
  visible so a future session does not treat "randomize the patrol" as a
  free improvement without re-discovering the same A/B evidence.
- **Zero infrastructure pathologies**: 0/560 matches forfeited, crashed,
  or produced a diagnostic; 0/560 matches ended in a tie.

## 18. Success/rejection criteria assessment (Phase 9 of the governing task)

**Evidence supporting continuation, present:**

- Materially lower core-capture rate against Core Seeker: 0/10 vs the
  original's 5/10 on an identical seed/orientation set, including the one
  orientation that captures every other tested victim (§9-10).
- Reproducible across seeds (deterministic; identical outcome each seed
  within an orientation) — though not yet tested across a wider seed set
  or against seed-dependent opponents, since Core Seeker itself carries no
  seed sensitivity to test against (§17 of alpha.1's own unresolved
  questions already flagged this).
- A measurable cost is present (0/70 win rate, same magnitude as the
  original's own pre-existing cost) — the mechanism does not eliminate the
  cost of defending, it just makes the defense that gets bought with that
  cost actually work.
- No universal dominance (0/70 overall win rate is unambiguous on this).
- Clear behavioral differentiation from blind refresh, demonstrated
  directly (proactive `READ`-based patrol, bounded `WRITE`-based repair
  only on evidence) rather than merely inferred from outcomes.

**Evidence against, or requiring qualification:**

- Reactive Core Defender never wins a single match in this population,
  under either ruleset — "improves survival" must not be read as
  "improves competitiveness" or "makes defense a viable path to
  winning." It does not, in this population.
- The existing paired win-rank statistic is blind to the improvement
  (§11) — future alpha work evaluating any currently-zero-win-rate
  strategy needs a metric more sensitive than win/tie/loss rank.
- Orientation sensitivity is severe for the underlying mechanic's only
  successful attacker (Core Seeker), and this is a placement/harness
  artifact, not a property of "vulnerable core" in the abstract (§10).
- Sample size for the headline capture-rate comparison is small (n=10 per
  defender); Wilson intervals are wide and technically overlap at the
  boundary, even though the observed proportions (0 vs 5) are clean and
  fully deterministic.

**Rejection-criteria checks:** reactive defense did not become universally
dominant (opposite: 0/70 wins); Core Seeker was not "unbeatable by any
legitimate reactive defense" — it was beaten (avoided) reliably; defender
success did not depend on Core Seeker's exact source (§8's reverted
correction shows the design generalizes past a synthetic re-derivation of
Seeker-like behavior, not a memorized counter to one implementation);
results tracked deterministic mechanics (tick-of-capture, orientation),
not seed artifacts; no self-overwrite collapse occurred.

## 19. Recommendation

**Continue Vulnerable Core into further, still-narrow work — a qualified
"A," not an unqualified endorsement.**

Alpha.2's specific research question — *can a reactive defender materially
improve survival against Core Seeker without sacrificing so much general
performance that defense is globally inferior, relative to the blind
defense alternative alpha.1 already tried* — is answered **yes**, with
direct, reproducible, mechanistically-understood evidence, not merely a
favorable aggregate statistic. Reactive defense is a strict improvement
over blind defense at the one thing defense is for (retaining the core),
at a cost within a few percent of what blind defense already paid.

Alpha.2 does **not** answer, and was not scoped to answer, whether
*defense of any kind* can become globally competitive with unrestricted
expansion in Bytefray's current scoring model — the evidence here
reconfirms, rather than resolves, the v0.6.1-era finding that unrestricted
expansion is close to dominant. That is a scoring/incentive question, not
a detection/reaction question, and per the governing task's own framing,
it is explicitly out of scope for this experiment.

## 20. Unresolved questions

- Would reactive defense's advantage hold against a *different* seeker
  strategy (e.g., one that probes multiple candidate addresses
  concurrently, or one that writes value `0` specifically to defeat
  content-based detection per §3's documented gap)? Not tested — Core
  Seeker's implementation was held fixed per the governing task.
- Does the orientation sensitivity found in §10 mean a wider set of start
  addresses (not just `0`/`2048`) would show a meaningfully different
  capture-rate picture for Core Seeker in general? Not tested — start
  placement was held fixed per the governing task.
- Could a metric more sensitive than win/tie/loss rank (e.g., a
  score-margin-based paired statistic) make the reactive defender's real
  improvement visible to the existing automated comparison tooling,
  rather than requiring manual termination-reason/score inspection as this
  document had to do?
- The content-vs-ownership detection gap (§3) is real but unexploited by
  the current bundled Core Seeker; whether it matters depends entirely on
  future opponent designs, not on anything alpha.2 itself can resolve.

## 21. Recommended next Bytefray v2 prompt

Given that alpha.2 shows reactive defense removes the core-capture cost of
defending without adding a new one, but that defense of any kind remains
globally non-competitive in this population, the most direct
evidence-driven next step is **not** a further defender redesign (alpha.2
already demonstrated one clean, evidence-driven improvement and correctly
declined a second one when the evidence didn't support it, §8) but a
narrowly scoped **alpha.3** that holds the reactive defender, Core Seeker,
and all alpha.1/alpha.2 mechanics exactly fixed and instead asks whether
existing `Config`-level scoring weights (not new formulas — the existing
`weights` already threaded through `ScoringPolicy`) can be *measured*
(not yet tuned) for how close territory-versus-survival tension would need
to shift before defense stops being globally dominated — a measurement
pass to scope a future, separately-authorized scoring experiment, not a
mechanic change in itself.
