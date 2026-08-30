# Bytefray v2.0.0-alpha.10 — Strategic Ecology Validation

The planned conclusion of the v2.0 alpha research sequence. Alphas 1–9
each validated one mechanic or agent design in isolation: Vulnerable Core
capture is real (alpha.1), ordinary Agent API v1 defense can survive it
(alpha.2), 1v1 score reweighting is structurally insufficient (alpha.3),
the engine is natively N-entrant (alpha.4/4.1), the historical Core Seeker
was a narrow, placement-dependent fixture (alpha.6/7), a placement-agnostic
offense benchmark (`core_tracker`) exists and generalizes (alpha.8), and
defense is real but scheduler-order-sensitive with no proven Reactive
advantage in a single-seed matched corpus (alpha.9). This alpha asks
whether those pieces interact as a strategically meaningful **ecology**:
expansion, generalized offense, and defense, together, not validated one
at a time. `CORE_SIZE`, arena size, tick/instruction budget, scoring and
its weights, winner semantics, the scheduler, capture-check timing, Agent
API v1, and all five primary agents' source (`claimer`, `hunter`,
`core_tracker`, `core_defender`, `reactive_core_defender`) plus the
historical `core_seeker` fixture are held byte-for-byte identical
throughout. **No production engine/client code, and no agent source, was
changed anywhere in this alpha.**

Branched from the verified alpha.9 baseline, commit `f1dce52` on
`v2.0-development` (`main` unchanged at
`5593d287f95a24996bb3b105befbc625a00795db` throughout).

## 1. Verified starting state (Phase 1)

- Branch: `v2.0-development`. HEAD at start: `f1dce52`. Working tree:
  clean. `main`: `5593d287...`, unchanged.
- `origin/v2.0-development` still points at unrelated `151866c` ("docs:
  expand v2.x strategic complexity research"), a sibling of local history
  branching from `4659654`, confirmed via `git merge-base --is-ancestor
  151866c HEAD` (non-ancestor) and `git log --oneline
  origin/v2.0-development`. Not merged, rebased, cherry-picked, or
  otherwise reconciled anywhere in this alpha.
- `docs/V2_0_ALPHA8_PLACEMENT_AGNOSTIC_OFFENSE.md` and
  `docs/V2_0_ALPHA9_DEFENSE_ROBUSTNESS.md` were read in full before any
  new work began, together with the full alpha.1–alpha.7 findings already
  summarized in the governing research prompt.
- Read directly, not inferred: `claimer/agent.py`, `hunter/agent.py`,
  `core_tracker/agent.py`, `core_defender/agent.py`,
  `reactive_core_defender/agent.py` (all five, in full, including every
  docstring's own design rationale); `battle_engine/results.py`'s
  `resolve_winner` (the one authoritative winner-resolution
  implementation, reused directly rather than re-implemented);
  `runs/v2_0_alpha9_defense_robustness/trace_match_v9.py`/
  `run_defense_matrix.py` (the dual/multi-slot trace harness and its own
  six historical-reproduction assertions, reused unmodified); `runs/
  v2_0_alpha7_spatial_characterization/run_evaluation.py`'s `core_cells`;
  `runs/v2_0_alpha8_placement_agnostic_offense/held_out_placements.py`
  (the held-out placement generation formula and its output).
- Regression baseline, measured directly on this machine before any
  alpha.10 file existed: full `pytest` collects **1562** tests; running
  them gives **1556 passed, 6 skipped, 2 deselected, 0 failed** —
  **identical**, not merely close, to alpha.9's own freshly-measured
  pre-alpha.9 figure (§1/§32 of that document). No further test-count
  drift this session; the small drift alpha.7/8/9 already found and
  declined to chase further remains exactly where alpha.9 left it, with
  no new discrepancy introduced. Ruff (`engine client`): clean. mypy
  (`engine/src/battle_engine`, `client/src/battle_client`): clean, 70 and
  10 files respectively — identical file counts to alpha.9.

## 2. Alpha.10 objective (governing question)

> Do expansion, generalized offense, and defense form a strategically
> meaningful ecology under the current experimental Ruleset v2 mechanics,
> or is the outcome still primarily determined by one dominant strategy,
> placement geometry, or scheduler order?

## 3. Frozen mechanics (Phase 2)

Held fixed throughout, confirmed unchanged: `bytefray-rules-2-alpha1`,
`CORE_SIZE = 8`, core ownership seeding, the capture rule and its
once-per-tick, post-action-block attribution mechanism, arena size 4096,
`instr_per_tick = 8`, the 200-tick budget, scoring and its weights,
survivor winner eligibility (`resolve_winner`, reused directly, not
re-derived), the scheduler, Agent API v1, the Python runtime, and all six
agents' source (five primary + the historical `core_seeker` fixture).
Confirmed at completion (§41): `git diff -- engine/src client/src` is
empty.

## 4. Entering findings, recapped from alpha.1–alpha.9

Vulnerable Core capture is real and demonstrated by two structurally
different, non-privileged attackers, across every placement condition
tested, including one (COLD) the historical attacker can never reach at
all (alpha.6–alpha.8). Search quality (`core_tracker`'s placement
generality) and kill power are experimentally separable, and neither
attacker is universally superior (alpha.8). Ordinary Agent API v1 defense
survives real attacks 87.5% of the time in alpha.9's own 32-cell matched
corpus, but that survival is **scheduler-order-sensitive** — order alone
flipped 25% of alpha.9's matched (condition, attacker, defender) cells —
and Reactive Core Defender showed **no matched win/loss advantage** over
blind Core Defender in that single-seed corpus, despite genuinely faster
detection/repair. Alpha.9 explicitly recommended alpha.10 (i) not assume
Reactive dominates, (ii) treat scheduler order as a first-class
experimental variable, and (iii) keep `core_tracker`/`core_seeker` as
structurally distinct attackers. All three are followed directly below.

## 5. Pre-registered hypotheses (Phase 3)

Written to `runs/v2_0_alpha10_strategic_ecology/hypotheses.md` before any
match executed; not rewritten after seeing results. Full text there;
summarized:

- **H1** — `core_tracker` creates meaningful pressure against undefended
  expanders but does not universally beat them on score.
- **H2** — at least one defender materially reduces capture risk relative
  to undefended expansion. Reactive is not required to beat blind.
- **H3** — expansion benefits from a defender's unrewarded action spend
  when no attacker is present.
- **H4** — a third expansion-focused entrant sometimes exploits
  offense/defense opportunity cost and wins.
- **H5** — no single agent dominates across role, 1v1/3-way, placement,
  scheduler order, and seed.
- **H6** — scheduler order matters but is not the whole game.

## 6. Success definition (Phase 4)

Fixed before results: role-specific strengths, visible opportunity costs,
matchup identity, and conditional (not deterministic-counter-class)
advantage — not a perfect rock-paper-scissors cycle, and not "territory
always wins" either. Full text in `hypotheses.md`.

## 7. Agent pool and role definitions

| Agent | Role | Status |
|---|---|---|
| `claimer` | expansion | primary |
| `hunter` | expansion | primary |
| `core_tracker` | offense (generalized, RNG-anchored) | primary |
| `core_defender` | defense (blind periodic) | primary |
| `reactive_core_defender` | defense (reactive, evidence-driven) | primary |
| `core_seeker` | offense (historical, fixed-schedule) | fixture only, small separate subset (§32) |

All five primary agents' source was re-read in full this alpha (§1); none
were modified. `claimer`/`hunter` never issue `READ` — every action is a
`WRITE` (confirmed directly from source), so their own "information
action fraction" is 0% by construction, not an artifact of instrumentation.

## 8. Seed audit (Phase 5)

`core_tracker.reset` draws its scan cursor's starting point from
`context.rng.randrange(context.arena_size)` (confirmed directly from
source, matching alpha.8 §9's own characterization) — every other
field/stride is fixed. No other primary or fixture agent consumes
`context.rng` for anything that affects its own behavior (`claimer`/
`hunter`/`core_defender`/`reactive_core_defender` all capture `context.rng`
in `reset` but never call it). Consequence, confirmed by this alpha's own
seed-sensitivity results (§18/§27): every matrix cell **not** containing
`core_tracker` is exactly reproducible at any seed, so running it more
than once at seed 1 would be pseudo-replication, not new evidence. Every
cell **containing** `core_tracker` uses the full seed set
`{1, 2, 3, 4, 5}`, per `hypotheses.md`'s pre-registered default.

## 9. Placement set (Phase 6)

Reused byte-for-byte from alpha.7/alpha.9, never retyped independently:

| Condition | A | B | C |
|---|---:|---:|---:|
| `control` | 0 | 1365 | 2730 |
| `hot` | 282 | 1846 | 3411 |
| `cold` | 83 | 1281 | 2635 |
| `heldout_even_eighths` | 512 | 1536 | 2560 |

## 10. Harness fidelity check (Phase 6 gate)

Before any new match ran, alpha.9's own six historical-reproduction
assertions (`run_defense_matrix.historical_reproductions`, imported and
called unmodified) were re-executed and asserted exact:
**6/6 reproduced exactly** (`runs/v2_0_alpha10_strategic_ecology/
run_matrix.py`'s own `harness_fidelity_check`, which the driver runs and
asserts before proceeding to any alpha.10-specific match). Confirms the
imported `trace_match_v9` dual-trace harness this alpha reuses byte-for-
byte is unchanged and correctly wired.

## 11. 1v1 matrix design and execution count (Phase 7)

All `C(5,2) = 10` unordered pairs of the five primary agents. Each entrant
occupies condition seat `A` or `C` — seat `B` deliberately unused for the
1v1 matrix, to avoid re-anchoring on the historical seat-B-victim
convention alpha.7 already showed was a placement artifact, not an
inherent property. Two scheduler orders per cell: the entrant list is
reversed between the two runs while each agent's own `(slot, address)`
assignment stays fixed — list order is scheduling order, independent of
address, the same construction alpha.9's harness already establishes.
6 pairs without `core_tracker` run once (seed 1); the 4 pairs with
`core_tracker` run across all 5 seeds. **208 1v1 matches**
(6 × 4 placements × 2 orders × 1 seed = 48; 4 × 4 placements × 2 orders ×
5 seeds = 160), **zero infrastructure failures**, 6.92s wall time.

## 12. Pairwise outcome matrix (Phase 9)

| Pair | Win rate | Capture rate | Mean margin | Order flip | Placement invariance |
|---|---|---:|---:|---:|---:|
| claimer vs hunter | claimer 87.5% / hunter 12.5% | 0% | — | 25% | 50% |
| claimer vs core_tracker | claimer 100% | 0% | — | 0% | 100% |
| claimer vs core_defender | claimer 100% | 0% | — | 0% | 100% |
| claimer vs reactive_core_defender | claimer 100% | 0% | — | 0% | 100% |
| hunter vs core_tracker | hunter 100% | 0% | — | 0% | 100% |
| hunter vs core_defender | hunter 100% | 0% | — | 0% | 100% |
| hunter vs reactive_core_defender | hunter 100% | 0% | — | 0% | 100% |
| core_tracker vs core_defender | core_defender 72.5% / core_tracker 27.5% | 28% | — | **55%** | 50% |
| core_tracker vs reactive_core_defender | reactive 87.5% / core_tracker 12.5% | 12% | — | 25% | 70% |
| core_defender vs reactive_core_defender | core_defender 75% / reactive 25% | 0% | — | 0% | 0% |

(Full per-pair margin/score figures in `analysis_summary.json`'s
`pairwise_1v1`.) The single most striking row: **every 1v1 matchup
between an expansion agent (`claimer`/`hunter`) and any of the other three
agents is won 100% of the time by the expansion agent, at every placement,
every scheduler order, and (where applicable) every seed** — with a 0%
capture rate against expansion in every one of these 128 matches (6
non-`core_tracker` cells × ... plus the 80 `core_tracker`-vs-expansion
cells). This is the central, load-bearing fact this alpha's own evidence
produced and is discussed at length in §22–§29 below.

## 13. Role comparisons (Phase 8)

- **Expansion vs expansion** (`claimer` vs `hunter`): claimer wins 87.5%
  (7/8), hunter 12.5% (1/8) — a real, if secondary, asymmetry (`claimer`'s
  fixed-origin dense sweep out-territories `hunter`'s sparse-then-dense
  strategy slightly more often than not in this corpus), order-sensitive
  in 25% of matched cells, placement-sensitive in 50%.
- **Expansion vs offense**: `claimer`/`hunter` beat `core_tracker` 100% of
  the time, 0% capture rate, fully order- and placement-invariant.
- **Offense vs defense**: the corpus's most contested, most sensitive
  matchup class — see §12 rows 8–9 and §17.
- **Expansion vs defense**: `claimer`/`hunter` beat both defenders 100% of
  the time, 0% capture rate (defenders never attack), fully order- and
  placement-invariant.
- **Defense vs defense** (no attacker present): `core_defender` beats
  `reactive_core_defender` 75%/25%, 0% capture rate, fully order-invariant
  but placement-**sensitive** (0% invariance — the winner changes across
  every one of the 4 placement conditions tested, i.e. which defender
  wins this matchup depends on placement every single time in this small,
  8-cell sample). `reactive_core_defender`'s own steady-state cost
  (§7/§20's read-heavy, expansion-displacing patrol cycle) evidently loses
  it a small, placement-dependent amount of territory against
  `core_defender`'s pure-write cadence when no attacker rewards either
  one's vigilance — consistent with alpha.9 §20's own 2–4% score-gap
  finding, now shown to occasionally flip the head-to-head winner.

## 14. 1v1 scheduler-order sensitivity (Phase 10)

Global: **104 matched cells, 17 winner flips (16.3%)**, 16 capture flips.
By matchup class:

| Class | Matched cells | Winner flips | Flip rate |
|---|---:|---:|---:|
| expansion vs expansion | 4 | 1 | 25% |
| expansion vs offense | 40 | 0 | **0%** |
| offense vs defense | 40 | 16 | **40%** |
| expansion vs defense | 16 | 0 | **0%** |
| defense vs defense | 4 | 0 | 0% |

Scheduler order is **not a global phenomenon** in this corpus — it is
almost entirely concentrated in the offense-vs-defense matchup class,
where it is a real, large effect (40% of matched cells, higher than
alpha.9's own 25% figure measured on a narrower, single-seed corpus).
Every cell in which expansion participates is **completely** order-
invariant (0% flip in both expansion-vs-offense and expansion-vs-defense),
directly relevant to §29's verdict: expansion's dominance is not a
scheduler artifact.

## 15. 1v1 placement sensitivity (Phase 11)

Global: 52 matched cells (grouped by scheduler order × seed, compared
across the 4 conditions), **78.8% placement-invariant**. Placement-
sensitive matchups: `claimer` vs `hunter`, `core_tracker` vs
`core_defender`, `core_tracker` vs `reactive_core_defender`,
`core_defender` vs `reactive_core_defender` — every placement-sensitive
matchup involves either the expansion-vs-expansion asymmetry or offense/
defense specifically. Placement-invariant matchups: every expansion-vs-
offense and expansion-vs-defense cell (100% invariant in both), the same
pattern §14 already shows for scheduler order. The introduction of
`core_tracker` (placement-agnostic by design, alpha.8) does **not**
eliminate placement sensitivity from the matchups where it matters most
(against the two defenders) — it relocates *where* that sensitivity
concentrates, from "does the historical attacker's fixed schedule happen
to reach this placement at all" (alpha.6/7's finding) to "does this
match's RNG-seeded scan anchor happen to find and confirm the target
before the tick budget runs out" (§18).

## 16. Seed sensitivity (Phase 12)

For the four `core_tracker`-involving 1v1 pairs, matched by (scheduler
order, condition), comparing outcomes across the 5 seeds:

| Pair | Matched cells | Winner-change rate | Mean margin range across seed |
|---|---:|---:|---:|
| claimer vs core_tracker | 8 | **0%** | 18.1 |
| hunter vs core_tracker | 8 | **0%** | 37.5 |
| core_tracker vs core_defender | 8 | **50%** | 125.6 |
| core_tracker vs reactive_core_defender | 8 | **37.5%** | 97.9 |

Seed sensitivity tracks exactly where the matchup is actually contested:
zero winner changes across seed against expansion (claimer/hunter win
regardless of which region `core_tracker`'s RNG anchor happens to land
in), but real, substantial seed sensitivity against both defenders — whether
`core_tracker`'s scan anchor lands somewhere that lets it confirm and
assault the defender's core before the match ends is genuinely
seed-dependent. Per the governing task's own Phase 12 framing, this reads
as **healthy strategic variation, not instability**: it is concentrated
precisely in the one matchup class where search quality is the deciding
factor, and produces zero spurious variation in matchups whose outcome is
already structurally determined.

## 17. Matched blind-vs-reactive defender comparison (refines alpha.9)

Alpha.9 found, in its own single-seed (seed 1), 32-cell matched corpus,
**no** win/loss survival difference between `core_defender` and
`reactive_core_defender` (16/16 identical matched outcomes). This alpha's
own `core_tracker`-vs-defender 1v1 cells (§11) span the full 5-seed set at
the same 4 placements × 2 orders, giving 40 directly matched
(condition, seed, order) cells for each defender type. Comparing survival
cell-by-cell:

| | Count |
|---|---:|
| Both survive | 29 |
| Both captured | 5 |
| Blind survives, Reactive captured | **0** |
| Reactive survives, Blind captured | **6** |

**Reactive Core Defender survives strictly more often than blind Core
Defender in this matched comparison — 6 cells favor Reactive, zero favor
blind** (87.5% vs 72.5% overall survival, §12). This is a genuine, new
refinement of alpha.9, not a contradiction of it: alpha.9's own six flip
cells were characterized at seed 1 only; a spot check of this alpha's own
seed-1 subset (same 8 matched cells, this alpha's own A/C seat convention)
already shows 2 of alpha.9's own "identical outcome" cells resolving
differently here (`control`/`second_listed_first` and
`hot`/`second_listed_first`: blind captured, Reactive survives) — a direct
consequence of using a different (but equally legitimate, per §11's own
"seat B unused" design) seat convention, not evidence against alpha.9's
own exact seed-1/seat-B-convention results, which this alpha does not
re-test. The broader, genuinely new finding stands on its own 5-seed
evidence: **once real RNG sampling of `core_tracker`'s scan anchor is
introduced, Reactive Core Defender shows a real, one-directional (never
reversed) matched-cell survival advantage over blind Core Defender against
this alpha's own primary offense benchmark.** Single-seed matched
comparisons (alpha.9's own design, appropriate at the time `core_tracker`'s
RNG dependence had only just been discovered, alpha.8 §9) understate this;
alpha.10's own Phase 5 seed-set requirement is precisely why it surfaces
here and did not there.

## 18. 3-way trio design and execution count (Phases 13–15)

Eight trios (the governing task's own stratified minimum, not the full
`C(5,3) = 10` — documented as the deliberate choice in `hypotheses.md`
before execution): four offense-vs-one-defender-plus-one-expander trios,
two-expanders-plus-offense, two-expanders-plus-each-defender, and
offense-vs-both-defenders. Each trio's three members are assigned fixed
condition seats in listed order (first → A, second → B, third → C),
identical across all six permutations at a given condition/seed — this
separates strategy identity, spatial address, and execution order (Phase
14): only the *scheduling list order* varies across permutations; no
agent's own address ever moves. All six permutations used (not three
cyclic rotations), so every strategy appears first, middle, and last.
Six `core_tracker`-containing trios run the full 5-seed set; two
(`claimer`/`hunter` + one defender, no `core_tracker`) run once. **768
3-way matches** (720 + 48), **zero infrastructure failures**, 39.79s wall
time.

## 19. 3-way trio results (Phase 16)

| Trio | Win rate | Capture rate | Permutation sensitivity |
|---|---|---:|---:|
| claimer + core_tracker + core_defender | claimer 95% / core_defender 5% | 21% | 15% |
| hunter + core_tracker + core_defender | hunter 88.3% / core_defender 11.7% | 25% | 30% |
| claimer + core_tracker + reactive_core_defender | claimer 95% / reactive 5% | 18% | 15% |
| hunter + core_tracker + reactive_core_defender | hunter 87.5% / reactive 11.7% / core_tracker 0.8% | 30% | 35% |
| claimer + hunter + core_tracker | claimer 60.8% / hunter 35% / no-winner 4.2% | 8% | 65% |
| claimer + hunter + core_defender | claimer 75% / hunter 20.8% / no-winner 4.2% | **0%** | 50% |
| claimer + hunter + reactive_core_defender | claimer 75% / hunter 20.8% / no-winner 4.2% | **0%** | 75% |
| core_tracker + core_defender + reactive_core_defender | core_defender 50% / reactive 46.7% / core_tracker 3.3% | 22% | 45% |

Reading these against Phase 16's own role questions:

- **Does offense create opportunities for expansion?** Yes, structurally:
  offense reliably (18–30% of matches) captures the *defender*, not the
  expander, in the four offense+defender+expander trios (§20's victim
  breakdown), removing a competitor and leaving the expander with an
  easier score comparison.
- **Does defense protect itself while sacrificing too much territory?**
  Both defenders lose the vast majority of these trios (5–11.7% win rate)
  even accounting for their own real survival rate — consistent with
  §17's finding that surviving `core_tracker` does not by itself win the
  broader territorial race against an active expander.
- **Can offense kill one entrant but lose to the third?** Yes, repeatedly
  — the modal outcome in all four offense+defender+expander trios.
- **Can defense survive offense and then beat the expander?** Rare —
  defenders win only 5–11.7% of these trios, and (§20) even the expander's
  own occasional captures do not flip this pattern in the defenders'
  favor.
- **Can the expander ignore both and win?** Overwhelmingly yes — 87.5–95%
  of the four offense+defender+expander trios, directly bearing on §29's
  verdict.
- **Do blind incidental captures occur?** Not observed in this corpus —
  see §21.

## 20. Third-party effects (Phase 17)

Capture-victim breakdown within the four offense+defender+expander trios
(`raw_matches_3way.json`, victims counted per trio, 120 matches each):

| Trio | Expander captured | Defender captured |
|---|---:|---:|
| claimer + core_tracker + core_defender | claimer: 6 | core_defender: 19 |
| hunter + core_tracker + core_defender | hunter: 14 | core_defender: 16 |
| claimer + core_tracker + reactive_core_defender | claimer: 6 | reactive: 16 |
| hunter + core_tracker + reactive_core_defender | hunter: 15 | reactive: 22 |

Defenders absorb roughly half-to-most of `core_tracker`'s captures in
every trio, but the expander is *not* immune — 6–15 captures per 120-match
trio. The precise mechanism, checked directly: `hunter`'s own loss rate in
the `hunter`/`core_tracker`/`core_defender` trio (11.7%) equals `hunter`'s
own capture count in that trio *exactly* (14/120 = 11.7%) — every single
time `hunter` survives this trio, `hunter` wins it; every single time
`hunter` is captured, `core_defender` (never `core_tracker`) wins the
resulting two-survivor score comparison, since `core_tracker` has spent a
large fraction of its own budget on search (§24) while `core_defender`
spent its non-defensive budget on ordinary expansion. This is a genuinely
healthy, disclosed ecology mechanism, not a null result: **expansion wins
when it survives (the common case) and loses cleanly to whichever
defender survives alongside it (not to the attacker) on the rarer
occasions it does not.**

## 21. Incidental capture and kill attribution (Phase 22/25)

Across the entire 976-match 1v1 + 3-way corpus: **168 total capture
events, all 168 credited to `core_tracker`**. Zero captures were credited
to `claimer`, `hunter`, `core_defender`, or `reactive_core_defender` as
killer — no incidental blind-overlap captures were observed anywhere in
this corpus (distinct from alpha.7's own MIXED-condition ownership-overlap
finding and alpha.9 §25's two incidental `claimer`-bystander captures,
neither of which recur here because this alpha's placement set omits the
MIXED condition and its 1v1 matrix places `claimer`/`hunter` only as
direct competitors, not passive bystanders next to an active defender-vs-
attacker pair). **No kill-stealing** (a second attacker finishing a first
attacker's damage) was structurally possible in this corpus: `core_seeker`
is never present simultaneously with `core_tracker` in any primary-ecology
match (§7's design; the small `core_seeker` subset, §32, never includes
`core_tracker`), so at most one genuinely offense-capable entrant is ever
present in any given match. This is a disclosed scope boundary, not a
finding that kill-stealing cannot occur under this ruleset generally
(alpha.9 §18's own three-way both-attackers matches already showed a
capture with one specific killer credited among two present attackers).

## 22. 3-way scheduler/permutation sensitivity (Phase 14 analysis)

Global: **128 matched cells, 46 sensitive (35.9%)** — a permutation is
"sensitive" if the winner differs across any of the six permutations at a
matched (condition, seed) cell. Substantially higher than the 1v1 global
figure (16.3%, §14), and higher than alpha.9's own 25% single-defender-
matchup figure — three-way play multiplies the number of ways a scheduling
list order can realign which entrant's action block lands last in a
decisive tick (§9 of alpha.9's own mechanism explanation, now observed
operating across a genuinely larger corpus). Per-trio range: 15%
(offense+defender+`claimer`, where `claimer`'s own dominance is order-
invariant regardless of what happens between the other two) to 75%
(`claimer`+`hunter`+reactive defender, where two structurally similar
expansion-weighted agents compete closely enough that scheduling order
alone frequently decides the narrow remainder). This directly answers
§29's H6 question at the 3-way scale: order sensitivity is real and
larger than alpha.9's own narrower estimate, but it is **not** globally
dominant — the two trios with the highest permutation sensitivity (65%,
75%) are exactly the two/three where the underlying win margin between the
top two contenders is already narrow on other grounds (§19), consistent
with §14's own 1v1 finding that order sensitivity concentrates where a
matchup is otherwise closely contested, not where one strategy already
dominates.

## 23. Action economics (Phase 18)

| Agent | Expansion fraction | Information fraction | Own-core defense fraction | Opponent-core offense fraction |
|---|---:|---:|---:|---:|
| `claimer` | 99.4% | 0.0% | 0.2% | 0.4% |
| `hunter` | 99.4% | 0.0% | 0.2% | 0.4% |
| `core_tracker` | 67.6% | 31.7% | 0.2% | 0.5% |
| `core_defender` | 74.6% | 0.0% | 25.1% | 0.2% |
| `reactive_core_defender` | 72.4% | 26.1% | 1.2% | 0.2% |

(`claimer`/`hunter`'s own tiny 0.2–0.4% "own-core"/"opponent-core"
fractions are not deliberate — every action either agent takes is an
ordinary blind `WRITE`; these are the small fraction of sweep addresses
that happen to fall inside *some* entrant's core region by pure
coincidence, exactly the "content readiness" pathway alpha.6 §13 first
identified, now quantified directly rather than merely described.)
`core_defender`'s 25.1% matches its documented `REFRESH_EVERY = 4`
unconditional cadence exactly. `reactive_core_defender`'s 26.1%
information (read) fraction plus its far smaller 1.2% own-core-write
fraction directly reproduces alpha.9 §7's already-documented "~20x fewer
core-directed writes, paid for with a steady read stream instead"
finding, now measured across this alpha's much larger, seed-varied
corpus. `core_tracker`'s 31.7% information fraction is real, substantial,
and — critically — produces zero benefit against `claimer`/`hunter`
(§12): against undefended, non-signing expansion, every one of those
reads is spent looking for content that structurally never appears.

## 24. Territory economics (Phase 19)

| Agent | Mean score | Mean alive ticks |
|---|---:|---:|
| `claimer` | 2184.3 | 197.3 |
| `hunter` | 2148.8 | 194.1 |
| `core_tracker` | 1406.4 | 197.9 |
| `core_defender` | 1505.2 | 184.5 |
| `reactive_core_defender` | 1521.9 | 182.6 |

Averaged across this corpus's full mix of 1v1 and 3-way matches:
`claimer`/`hunter` score roughly 40–55% higher than any of the other three
agents, directly reflecting §23's action-economics gap (nearly 100%
expansion throughput vs. 68–75% for the other three). `core_tracker`'s
mean score is the lowest of the five despite the highest mean alive-ticks
(197.9 — it is rarely killed itself, since it spends little time near any
opponent's confirmed-hostile core and neither `claimer`/`hunter` nor
either defender ever deliberately attacks it) — its search cost is a pure,
disclosed score tax with no corresponding survival benefit in this corpus.
This directly answers Phase 19's own question 4 ("does the territory
economy explain most winners even when capture mechanics matter"): **yes,
for the large majority of this corpus** — §12/§19 already show capture
mechanics deciding outcomes only in the offense-vs-defense matchup class
and the four offense+defender+expander trios' internal contest for second
place; territory alone decides essentially everything else, including
every single expansion-involved matchup.

## 25. Capture economics (Phase 20)

Across the full 976-match 1v1 + 3-way corpus: **165/976 matches (16.9%)
had at least one capture**, 168 total capture events, all 168 credited to
`core_tracker` (§21). Captures suffered by agent: `core_defender` 57,
`reactive_core_defender` 60, `hunter` 37, `claimer` 14 — the two defenders
together account for 117/168 (69.6%) of all captures suffered despite
being present in far fewer of this corpus's matches than `claimer`/
`hunter` are. Capture tick distribution: mean 88.2, median 84, range 5–198
— far wider than either historical attacker's own narrow, delay-dominated
cluster (`core_seeker`'s historical control cluster: tick 159–168, alpha.6
§11; `core_tracker`'s own alpha.8 three-way-matrix range: 27–196),
consistent with a genuinely seed/placement/scheduler-varied corpus rather
than a narrow repeated condition. By placement condition: `control` 58,
`cold` 47, `heldout_even_eighths` 43, `hot` 20 — notably, **`hot` produced
the *fewest* captures of the four conditions** in this corpus, the
opposite of its role in every prior alpha (alpha.7 defined HOT
specifically around `core_seeker`'s own fixed, early-tick reachability;
`core_tracker`'s RNG-anchored search has no structural reason to find HOT
any more favorable than any other condition, and this alpha's own data
shows it does not) — direct, quantitative confirmation that `core_tracker`
further decouples the historical placement-vulnerability categories from
any placement-agnostic attacker, extending alpha.7/alpha.8's own finding
one step further.

## 26. Deliberate vs. incidental captures

Every one of the 168 captures in this corpus is classified deliberate
(§21: 100% credited to `core_tracker`, the corpus's only offense-capable
entrant present in any primary-ecology match), reproducing alpha.8 §24's
own finding ("every one of `core_tracker`'s captures in this corpus was
attributable to its own deliberate search-then-assault sequence") at
roughly 14x the scale (168 vs. 6 captures in alpha.8's own three-way
matrix). No genuinely incidental (non-offense-agent-credited) capture
occurred anywhere in this alpha's 976-match corpus.

## 27. Defense niche test (Phase 21)

Neither defender uniformly reduces capture risk relative to undefended
expansion — the opposite is closer to true in this corpus (§12: 0%
capture rate against `claimer`/`hunter`, 12–28% capture rate against the
two defenders, discussed at length in §29). Both defenders' real niche is
narrower and more specific: **survival against a genuinely capable,
search-based attacker specifically** (72.5–87.5% 1v1 survival against
`core_tracker`, §12/§17), where the alternative is not "no defense" but
"no attacker capable of exploiting the absence" — a niche this corpus
shows is real (defenders are not economically useless: §24 shows they
retain competitive, if not expansion-competitive, scores) but narrower
than "generally reduces capture risk." Comparing the two defenders
directly: Reactive shows a genuine, one-directional matched-cell survival
advantage over blind against `core_tracker` (§17, new this alpha), is
statistically tied with blind when both face `core_tracker` simultaneously
with no expander present (trio 8, §19: 50%/46.7%), and loses to blind
head-to-head with no attacker present (§13: 75%/25%, `defense vs defense`).
Reactive's niche is specifically **survival under real attack**; blind's
niche is specifically **economic efficiency when survival is not actually
contested**.

## 28. Offense niche test (Phase 22)

`core_tracker` creates real, substantial, seed-and-placement-sensitive
capture pressure specifically against agents that write recognizable
content into their own core (both defenders: 12–28% 1v1 capture rate,
§12) — a real niche, not a token result. Against agents that never write
into their own core at all (`claimer`/`hunter`), it produces **zero**
capture pressure in this alpha's own 1v1 seat convention (§12) and only
modest pressure (5–12.5% capture rate) once a defender's own presence is
also in the match (§20's 3-way trios), and even there it essentially never
wins the resulting match itself (§19: 0–0.8% win rate against expansion
in every 3-way trio tested). Its search cost (§23: 31.7% of its own
action budget) buys real, disclosed, and non-trivial pressure against one
class of opponent (content-bearing defenders) and effectively nothing
against the other (content-free expanders) — search quality and target
vulnerability remain separable, exactly as alpha.8 §20 first established,
now shown to be the dominant factor determining whether specialized
offense pays for itself at all.

## 29. Expansion niche test (Phase 23) — the central finding

`claimer`/`hunter` win **100% of every 1v1 matchup tested against
`core_tracker` and both defenders** (§12), and **87.5–95% of every
offense+defender+expansion 3-way trio tested** (§19), fully robust to
scheduler order (§14: 0% flip rate in every expansion-involved 1v1 class)
and fully robust to placement (§15: 100% invariance in every expansion-
involved 1v1 class). This is precisely the outcome Phase 23's own
falsification criterion warns about: *"If Claimer/Hunter still win nearly
everything regardless of capture pressure, the original v2 problem
remains unresolved."* Read plainly, unresolved is the correct
characterization for this specific corpus. The mitigating, disclosed
nuance (§20): expansion is not *literally* immune to capture pressure in
3-way play (6–15 captures per 120-match trio), and when it is captured it
loses cleanly, not to the attacker but to whichever defender happens to
survive alongside it — a real, if narrow, strategic mechanism, not a null
result. But the dominant pattern across this alpha's full corpus is that
expansion wins because it is captured rarely and, when not captured, its
raw territorial efficiency (§23/§24: essentially 100% of its own action
budget spent claiming territory, vs. 68–75% for every other agent) simply
outscores everything else regardless of scheduler order or placement.

## 30. Strategy dominance analysis (Phase 24)

| Agent | 1v1 win rate | 3-way win rate | Combined |
|---|---:|---:|---:|
| `claimer` | 98.4% | 82.6% | **84.7%** |
| `hunter` | 89.1% | 64.5% | 67.8% |
| `core_defender` | 54.7% | 20.8% | 25.7% |
| `reactive_core_defender` | 57.8% | 19.8% | 25.2% |
| `core_tracker` | 10.0% | 0.7% | **2.4%** |

Per Phase 24's own guidance ("a strategy is concerningly dominant if it
performs strongly across all major contexts, not merely because the
matrix contains favorable matchups"): `claimer` clears that bar directly —
strong in 1v1 (98.4%) *and* 3-way (82.6%), invariant to scheduler order
and placement in every expansion-involved cell (§14/§15), and its win rate
does not depend on which of the two available placement/order confounds
happen to favor it (§14 shows exactly 0% order flip in every expansion
matchup class). `hunter` is a close second by the same standard, and
loses more often specifically *to* `claimer` (§13) rather than to any
offense/defense agent. `core_tracker` is the clearest opposite case:
concerningly *weak* across all major contexts (10% 1v1, 0.7% 3-way),
consistent with §28's niche finding that its search cost pays off in
capture pressure against a narrow opponent class without translating into
match wins even there.

## 31. Scheduler-order dominance decision gate (Phase 25)

- Fraction of matched 1v1 cells whose winner changes solely with order:
  **16.3% globally**, **40% within offense-vs-defense specifically**, 0%
  in every expansion-involved class (§14).
- Fraction of matched 3-way cells: **35.9% globally** (§22), concentrated
  in trios where the top-two contenders are already closely matched on
  other grounds.
- Matchup class most affected: **offense vs. defense**, both 1v1 and
  3-way — directly consistent with, and a further escalation of, alpha.9's
  own central finding (25% single-defender-matchup figure there vs. 40%
  here on a larger, seed-varied corpus).
- Is last-action advantage systematic? Not globally — every expansion-
  involved matchup is completely order-invariant (§14/§15), so scheduler
  order cannot be said to predict outcomes globally "as well as or better
  than strategy" (the governing task's own "Dominant/beta-blocking"
  threshold). Its effect is real, large, and specific to one matchup
  class, not diffuse across the whole corpus.

**Classification: Moderate**, with an explicit escalation flag for the
next roadmap review — alpha.9 already found this deserved flagging at
25%; this alpha's own larger, seed-varied corpus finds the effect *larger*
(40% within the same matchup class) than alpha.9's own narrower estimate,
not smaller. Per Phase 25's own instruction: **explicitly flagged for the
post-alpha roadmap review before Ruleset v2 is frozen**, specifically
scoped to the offense-vs-defense capture-check/scheduling interaction, not
the engine's scheduler semantics generally.

## 32. Placement-dominance decision gate (Phase 26)

Placement sensitivity is **not** eliminated by `core_tracker`'s own
placement-agnostic design (§15: 78.8% global 1v1 invariance, i.e. real,
non-trivial sensitivity remains in 21.2% of matched cells), but it is
**fully absent** from every expansion-involved matchup (100% invariant,
§15) and concentrated specifically in the offense-vs-defense and
expansion-vs-expansion matchup classes. This is the same "relocated, not
eliminated" pattern §15 already describes in more depth: `core_tracker`
demonstrably decouples capture pressure from the *historical* fixed-
attacker placement categories (§25's own `hot` finding — no longer the
most dangerous condition), but placement/seed jointly still determine
*whether a specific match's search happens to succeed* within the
offense/defense matchup specifically. **Classification: Low-to-Moderate**,
concentrated in the same matchup class as §31's scheduler finding, not
diffuse — this alpha's own generalized offense benchmark supports
continuing to relax placement dependence as a design direction, without
having eliminated it.

## 33. Seed/RNG decision gate (Phase 27)

`core_tracker`'s RNG-driven scan anchor produces **zero** winner-changing
variance in every matchup where the outcome is already structurally
determined (0% seed-driven winner change against `claimer`/`hunter`,
§16), and real, substantial (37.5–50%) seed-driven winner change
specifically in the two matchups where search quality genuinely decides
the outcome (`core_tracker` vs. either defender, §16). This is the
governing task's own "useful diversity, manageable variance" case, not
"excessive match instability" — variance is concentrated exactly where
genuine strategic uncertainty exists and absent everywhere else. **A
single-seed evaluation methodology is demonstrably insufficient** for any
future evaluation involving `core_tracker` specifically (§17's own
refinement of alpha.9 is a direct, concrete instance of this: alpha.9's
single-seed matched comparison found no Reactive-vs-blind difference;
this alpha's 5-seed comparison finds a real, one-directional one) — a
concrete, evidence-backed recommendation for beta evaluation methodology,
not a request to remove randomness.

## 34. Score-system observation (Phase 28, observation only)

In this corpus, final winner selection is driven by:

- **Survival eligibility** (the `len(alive) == 1` override) in essentially
  every match with a capture where the capturing agent is `core_tracker`
  facing a lone defender (1v1 offense-vs-defense cells, §12) — capture
  directly determines the winner in those cells.
- **Territory score** in the overwhelming majority of the remaining
  corpus — every expansion-involved match (§29), every defense-vs-defense
  match with no attacker present (§13), and the modal outcome of every
  3-way trio once a capture removes one competitor but leaves two
  survivors to be scored (§20).
- **Kills** never independently determine a winner in this ruleset's own
  score-fallback mode beyond the survivor-eligibility override already
  described — no cell in this corpus shows a lower-territory, higher-kill
  entrant winning on a kills term (consistent with alpha.3's own
  already-established finding that kills have limited direct score
  leverage; this alpha does not reopen that scoring-weight question, per
  Phase 28's explicit instruction).

No scoring change is proposed or evaluated here. This observation is
reported for the next roadmap/beta-planning review's own use, per Phase 28.

## 35. Historical `core_seeker` fixture subset (Phase 31)

A small, clearly separate reference subset — `core_seeker` vs. each of the
five primary agents, `control` placement only, seed 1, **5 matches**, zero
infrastructure failures — reported for historical continuity only, never
folded into the primary ecology verdict:

| Opponent | Winner | Capture |
|---|---|---|
| `claimer` | `claimer` | no |
| `hunter` | `hunter` | no |
| `core_tracker` | `core_seeker` | no |
| `core_defender` | `core_defender` | no |
| `reactive_core_defender` | `reactive_core_defender` | no |

Zero captures in this small subset — consistent with alpha.6's own
finding that `core_seeker`'s control-condition capture pathway requires
its own specific late-game timing (tick 159–168) and the historical
seat-B address, neither of which this alpha's A/C-only 1v1 seat convention
reproduces. `core_seeker` beats `core_tracker` on score here (both attack,
neither captures, `core_seeker`'s own fixed schedule happens to spend
fewer actions searching than `core_tracker`'s does in this specific
single-seed cell) but loses to both defenders and both expanders — broadly
consistent with, and not contradicting, this alpha's own primary-ecology
findings.

## 36. Supported hypotheses

- **H3 (expansion benefits from unrewarded defense spend)** — strongly
  supported, cleanly: defenders never win a two-expander trio (§19: 0%),
  and lose every 1v1 to expansion (§12: 0%).
- **H4 (third-party opportunity-cost exploitation)** — supported, but the
  magnitude exceeds the hypothesis's own "sometimes, not always" framing:
  the expander wins 87.5–95% of the relevant trios (§19), not merely
  "sometimes."
- **H6 (scheduler influential but not the whole game)** — supported: real,
  large, and specifically located (offense-vs-defense, §14/§22/§31), not
  globally dominant.

## 37. Falsified/qualified hypotheses

- **H1 (offense creates meaningful pressure against undefended
  expanders)** — **falsified in 1v1** (§12: 0% capture rate against
  `claimer`/`hunter`) and only weakly supported in 3-way (§20: 5–12.5%
  capture rate, 0–0.8% resulting win rate). This alpha's own 1v1 seat
  convention (A/C only, §11) is a disclosed, unresolved confound — whether
  a different seat assignment would change this finding is not settled
  here (§39).
- **H2 (defense reduces capture risk relative to undefended expansion)**
  — **falsified as literally stated**: both defenders are captured *far
  more* often (12–28% 1v1, §12) than the two truly undefended agents
  (0%, §12) in this corpus, because defending requires writing
  recognizable content, which is exactly what makes a core detectable to
  a confirmation-based search (§27) — the same "content readiness"
  mechanism alpha.6 first identified, now shown to work *against* the
  defenders' own choice to maintain visible content. A fairer
  counterfactual (an agent that never writes into its own core and is
  never repaired, vs. one that does) was not tested here (§39).
- **H5 (no universal solution)** — **largely falsified**: `claimer`
  clears the governing task's own "concerningly dominant" bar directly
  (§30 — strong in both 1v1 and 3-way, order- and placement-invariant in
  every matchup it participates in). This is the central, sobering
  finding this alpha's evidence produced.

## 38. Full ecology verdict (Phase 29)

**C — mechanics work individually but ecology remains weak**, specifically
the "territory still dominates everything" sub-case the governing task's
own Phase 29 anticipates, **with real, disclosed qualifications that keep
this from being a blanket failure**:

1. Territory-based expansion (`claimer` especially) is not merely
   favored — it is close to a universal solution across every context this
   alpha tested (§30), the same "original v2 problem" alpha.3 first
   identified in 1v1 score reweighting, now shown to persist even with a
   genuinely N-entrant engine (alpha.4), a placement-agnostic offense
   benchmark (alpha.8), and real, working defense (alpha.9) all present
   together.
2. This is **not** a scheduler-order artifact — every expansion-involved
   matchup is completely order- and placement-invariant (§14/§15/§29) —
   nor a placement artifact for the same reason. Expansion's dominance is
   a genuine efficiency result under the current scoring weights and
   200-tick budget, not a confound this alpha's own design introduced.
3. Within the specific offense-vs-defense matchup class, genuine strategic
   richness exists: real seed sensitivity (§16), real order sensitivity
   (§14/§31), real placement sensitivity (§15/§32), a genuine niche
   distinction between the two defenders (§17/§27), and a real, disclosed
   opportunity-cost story for the attacker (§23/§28). The ecology concern
   this alpha's evidence raises is concentrated specifically in "how does
   anything compete with pure blind expansion," not "every mechanic tested
   across nine prior alphas is degenerate."
4. Defense's core niche is real but narrower than originally framed by H2:
   survival under genuine attack specifically, not general capture-risk
   reduction relative to doing nothing (§27/§37).

## 39. Beta-blocking structural issues (Phase 30 evidence handoff)

**What requires resolution before Ruleset v2 can freeze:**

- **Expansion's near-universal dominance** (§29/§38) — the central,
  beta-blocking finding. Whether this calls for scoring-weight changes,
  a different action-budget/tick-budget balance, a stronger offense/
  defense mechanic, or a deliberate design acceptance that expansion
  should be the strategically dominant baseline is a roadmap-level
  decision, explicitly out of this alpha's own scope (Phase 28's "do not
  reopen weight tuning" instruction, followed throughout).
- **Scheduler/capture-check timing sensitivity within offense-vs-defense**
  (§31) — real, larger in this alpha's own corpus than alpha.9's earlier
  estimate (40% vs. 25%), and specifically flagged, as alpha.9 already
  recommended, for review before any capture-timing-adjacent Ruleset v2
  decision is frozen.
- **Evaluation methodology for any `core_tracker`-involving future
  research** — a single-seed matched comparison is demonstrably
  insufficient (§17/§33); any future alpha, beta-planning experiment, or
  tournament design that includes `core_tracker` should use a genuine
  seed set, not seed 1 alone.

## 40. Evidence-ready Ruleset-v2 candidates (Phase 30 evidence handoff)

**What appears ready to carry toward Ruleset v2 beta consideration:**

- **Vulnerable Core** as a mechanic — real, demonstrated, non-privileged
  capture across every placement condition tested across ten alphas, most
  recently at 976-match scale here (§25/§26), with a real and now better-
  understood niche (§27/§28) rather than a broken or purely cosmetic
  mechanic.
- **Survivor-only winner eligibility** (`resolve_winner`, alpha.4.1) —
  used directly, unmodified, in every one of this alpha's 981 matches with
  zero unexpected behavior; the winner-resolution semantics this alpha
  observed (§34) match the documented design exactly.
- **Agent API v1 sufficiency** — every one of this alpha's five primary
  agents, including the newest (`core_tracker`, alpha.8), operates
  entirely within Agent API v1's existing `READ`/`WRITE`/`context.rng`
  surface; no gap in the API was identified by this alpha's own broader
  ecology matrix.
- **N-entrant capability** — 768 genuine 3-entrant matches across 8 trios
  and all 6 permutations each, zero infrastructure failures, real
  third-party effects observed and characterized (§20).
- **`core_tracker` as the standing offense benchmark** for any future
  research or evaluation work — placement-agnostic, seed-genuine, real
  discriminating power against content-bearing opponents (§28).

## 41. Unresolved research/design questions (Phase 30 evidence handoff)

- Whether this alpha's own 1v1 seat convention (A/C only, seat B unused,
  §11) materially understates `core_tracker`'s pressure against
  `claimer`/`hunter` relative to a convention that places offense at seat
  B or varies the seat assignment independently of role — not tested here
  (§37's H1 discussion).
- Whether a fairer "undefended but content-bearing" baseline (an agent
  that signs its core once but never repairs it) would show defense's
  true marginal capture-risk-reduction benefit more cleanly than the
  `claimer`/`hunter` comparison this alpha used (§37's H2 discussion).
- The general closed-form condition for scheduler-order sensitivity
  (alpha.9's own unresolved question, §29 of that document) remains open;
  this alpha quantifies its scale (§31) but does not derive a predictive
  formula.
- Whether the specific 40%/35.9% order-sensitivity figures (§31) are
  stable under a larger placement or trio sample than this alpha's own
  compact, stratified design used.
- Seat C's general territorial win-rate advantage (alpha.5 §24, still
  unresolved through alpha.6–alpha.9) remains fully open and orthogonal to
  this alpha's own A/C-only 1v1 convention.

## 42. Deferred v2.x ideas (Phase 30 evidence handoff, not decided here)

Per the governing task's own explicit scope exclusions: Agent API v2,
`ATTACK` action, replication, translation, multi-process agents, VM
parity timing, broader arena-size experiments, GUI/HUD track, packaging/
release work. None of these were touched, evaluated, or newly motivated by
this alpha; listed here only because the governing task requests this
section be present for the next roadmap review's own convenience.

## 43. Research artifacts (Phase 32)

`runs/v2_0_alpha10_strategic_ecology/` (gitignored under the existing
`runs/` precedent, consistent with every prior alpha): `hypotheses.md`
(pre-registration, written and frozen before any match ran, §5),
`run_matrix.py` (the 1v1 + 3-way + historical-fixture-subset driver, reuses
`trace_match_v9`/`core_cells` directly, writes `raw_matches_1v1.json`/
`raw_matches_3way.json`/`raw_matches_fixture.json`/`run_meta.json`),
`analyze.py` (pure post-processing, no match execution, writes
`analysis_summary.json`). No full per-action replay collection is
persisted — only bounded per-match summary records (winner, score,
margin, capture events, per-entrant action-economics counts), per the
governing task's own "avoid huge replay collections" instruction.

## 44. Documentation

This document. Cross-references `docs/V2_0_ALPHA7_SPATIAL_
CHARACTERIZATION.md`, `docs/V2_0_ALPHA8_PLACEMENT_AGNOSTIC_OFFENSE.md`,
and `docs/V2_0_ALPHA9_DEFENSE_ROBUSTNESS.md` throughout rather than
restating their own findings in full.

## 45. Regression qualification (Phase 34)

| Check | Result |
|---|---|
| Alpha-focused suites (alpha.1/2/4/4.1/8) + `test_ruleset_v2_alpha1.py` + `test_ruleset_v1_equivalence.py` | **92 / 92 passed** |
| Full `pytest` (this machine, alpha.10 applied — docs-only tracked change) | **1556 passed, 6 skipped, 2 deselected, 0 failed** (1562 selected) |
| Full `pytest` (this machine, verified alpha.10 starting baseline, §1) | **1556 passed, 6 skipped, 2 deselected, 0 failed** (1562 selected) — identical, since alpha.10 makes no tracked source change |
| Ruff (`engine client` — the tracked, shipped source) | clean, 0 errors |
| Ruff (repo-wide, including gitignored `runs/` research scripts) | pre-existing drift unrelated to this alpha — see note below |
| mypy (`engine/src/battle_engine`) | clean, 70 files |
| mypy (`client/src/battle_client`) | clean, 10 files |
| `git diff --check` | clean |
| `git diff -- engine/src client/src` | empty |

**Ruff repo-wide note**: `ruff check .` (the exact invocation AGENTS.md
documents) reports `RUF100`/`PERF102` findings inside `runs/` — but this
alpha's own two new scripts were cleaned to be ruff-clean directly (`ruff
check runs/v2_0_alpha10_strategic_ecology/*.py` passes with zero errors);
the remaining repo-wide findings are entirely inside **other alphas'
already-existing, gitignored, never-committed research scripts**
(confirmed directly: `runs/v2_0_alpha9_defense_robustness/trace_match_v9.py`,
untouched by this alpha, already triggers the identical `RUF100`/`F841`
class of finding before any alpha.10 file existed). `runs/` is fully
gitignored (`git check-ignore -v` confirmed for every affected file) and
was never part of any prior alpha's own committed regression claim in
practice — this reads as a `ruff` version/default-ruleset drift since
alpha.9 was written (E402 is no longer an active rule in this
environment, so alpha.6–alpha.9's own `# noqa: E402` comments now report
as unused), not a regression this alpha introduced. Consistent with the
governing task's own explicit test-count-drift precedent: measured
directly, confirmed pre-existing via the untouched alpha.9 script, and not
chased further.

**Baseline reconciliation**: this alpha's own freshly-measured starting
full-suite result (§1: 1562 selected, 1556 passed, 6 skipped, 2
deselected, 0 failed) is **identical** to its own freshly-measured ending
result above — the cleanest possible reconciliation, with no drift to
explain in either direction, consistent with zero tracked source files
having changed anywhere in this alpha.

## 46. Commit and final state (Phase 35)

Committed locally on `v2.0-development` only. No merge, rebase,
cherry-pick, tag, or push performed. `origin/v2.0-development`'s unrelated
commit `151866c` left untouched throughout. The only tracked change is
this document (`docs/V2_0_ALPHA10_STRATEGIC_ECOLOGY.md`) — no source,
test, or config file was modified; `runs/v2_0_alpha10_strategic_ecology/`
remains gitignored, matching every prior alpha's own precedent.

## 47. Evidence handoff for the roadmap/beta-planning review

This alpha series (alpha.1–alpha.10) has established: Vulnerable Core
capture is real and reproducible under non-privileged agents (alpha.1,
6–8); ordinary Agent API v1 defense is real, though scheduler-order-
sensitive, with no proven general Reactive-over-blind advantage in a
single-seed matched design and a real, if modest, one in a multi-seed one
(alpha.2, 9, this alpha's own §17); the engine is genuinely N-entrant with
correct survivor-only winner semantics (alpha.4/4.1); and — the finding
this alpha's own evidence adds — **the combination of all of the above
still leaves blind territorial expansion close to a universal solution**,
not because of a scheduler or placement artifact, but as a direct,
disclosed consequence of the current scoring/action-economy balance
(§23/§24/§29/§38). The next planning phase's central open question,
directly downstream of this alpha's own evidence, is whether Ruleset v2
should proceed toward beta with that property accepted as a deliberate
design baseline, or whether it should be treated as the one remaining
mechanic-level question this ten-alpha series leaves open before a beta
freeze. This alpha does not answer that question — it is out of scope by
design (Phase 28/30) — but its own evidence (§12, §19, §29, §30, §38) is
offered as the most direct, load-bearing input to it.
