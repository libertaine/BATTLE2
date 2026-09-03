# Bytefray v4 Pre-RC Research — Spatial Identity and Evaluation Methodology

Research branch: `v4-pre-rc-research` (off `main`@`010c3f6b1cbfc7d63988f8ccfc2626aae7dcef99`, the
published `v4.0.0-alpha4` commit)
Rulesets under test: `bytefray-rules-4-alpha2` (unaltered), with
`bytefray-rules-4-alpha1` untouched throughout.

This report answers the two questions blocking a `v4.0.0-rc1` decision:

**A.** Does free/global reach undermine v4's spatial identity enough that freezing the current
Alpha2 gameplay semantics for 4.0 would be a mistake?

**B.** What should the stable v4 `agents evaluate` methodology be, now that the default v4 Ruleset
places entrant cores from the match seed rather than at fixed opposed addresses?

---

## A. Executive decision

| Gate | Decision |
|---|---|
| Current Alpha2 reach semantics suitable to freeze for 4.0? | **YES WITH LIMITATION** |
| Stable v4 evaluation methodology identified? | **YES** |
| Another gameplay alpha required? | **NO** |
| Another methodology alpha required? | **NO** |
| Ready to begin RC implementation/qualification? | **YES** — §J's release-blocking list *is* the RC implementation work, not a prerequisite to starting it |

**Question A in one paragraph.** Free reach is real and measurable, and in the arena band the
Ruleset was actually qualified in it is *not* the dominant strategy the Phase 5 limitation note
implied it might be. A controlled ladder of five probes that are byte-identical apart from declared
reach produces an **inverted-U** win curve at arenas 256/512/1024, not a monotone one: 3.4%
(reach 4), 19.3% (16), **35.4% (64)**, 34.6% (arena/4), 25.8% (arena/2, the legal maximum) —
maximum reach is beaten by mid reach, and the two rungs that win are the two that travel. The
mechanism is that reach's real function in Alpha2 is not "see more" but "see the enemy *before it
leaves its core*": a global-reach probe obtains an unambiguous read of the enemy core base on its
first callback in **52.1%** of matches, wins **49.5%** of those, and wins **0 of the 184** in which
it does not. That 52% is decided by the `K = 2` rotating scheduler, not by geometry. **The
documented limitation is a scale interaction:** at arena 4096 the same ladder straightens into a
monotone curve where maximum reach wins 54.7% against 2.3%, and Phase 4 and Phase 5 tested only
256/512/1024 — so the CLI and evaluation default arena of 4096 is a regime no v4 qualification has
ever covered, while the Agent Designer, the primary v4 surface, defaults to 512 and sits inside the
healthy band. The mitigation is a configuration and methodology choice, not a Ruleset change, which
is why no further gameplay alpha is warranted.

**Question B in one paragraph.** The current methodology samples the placement space at exactly
**two distinct separations** (1024 and 2048 cells at the default 4096 arena) and never produces an
engagement closer than a quarter of the arena; Alpha2's own placement rule produces 32 distinct
separations from 320 cells upward, 9.4% of them under 512 cells. The fix requires no new placement
algorithm, no new seed-derivation scheme, and no new identity system: evaluation should stop
imposing placement and let the Ruleset place, through the same
`placement.resolve_direct_match_starts` seam `bytefray run` already uses, over **8** deterministic
seeds with both orientations run over one fixed geometry, at a **pinned** arena size rather than an
inherited one. That is **0.53×** the match count of today's default v4 evaluation, and it is fully
reproducible, paired, and comparison-safe under the *existing* comparison gate — `comparison.py`
needs no change at all. The arena pin turned out to matter more than the placement rule it was
introduced to evaluate: the same seven agents, Ruleset, seeds and placement rule produce a
*different leaderboard* at 512 than at 4096 (a mid-reach mobile probe leads at 512; a global-reach
agent leads by 22 points at 4096), so the methodology must fix the arena and record it.
Separately, this investigation found a reproducible product defect:
`agents evaluate` on an Agent API v2 roster with an omitted `--ruleset` writes a `complete`,
`finished` artifact in which every cell failed (§F.6). That is release-blocking and is the reason
the RC gate above is conditional.

---

## B. Repository and environment baseline

Recorded before any work, and re-verified after (§L.5, §L.6).

| | |
|---|---|
| `HEAD` at start | `010c3f6b1cbfc7d63988f8ccfc2626aae7dcef99` |
| `origin/main` | `010c3f6b1cbfc7d63988f8ccfc2626aae7dcef99` (synchronized) |
| `v4.0.0-alpha4` | annotated tag `07a1bae30706c0110d16f5a879c24601bf66acb5` → commit `010c3f6b…` |
| Starting tree state | clean (`git status --short` empty) |
| Branch used | `v4-pre-rc-research`, created from `main` at `010c3f6b…` |
| OS | Windows 11 Pro 10.0.26120 |
| Python | 3.13.14 (`.venv/` at the repository root) |
| Research corpus root | `D:\Projects\Bytefray-research\v4-pre-rc-20260902\` (outside the product tree) |

`main`, `origin/main` and the `v4.0.0-alpha4` tag were identical at start and are unchanged. No
tag, release, branch merge, or push was performed.

**No product semantics were changed.** `git diff --stat v4.0.0-alpha4` is empty for every tracked
file: every addition in this phase is a new, untracked, research-only path under `tools/`
(§L.1). No `MatchRequest` field was added, no Ruleset identity or policy was touched, no golden
fixture or deterministic vector was re-blessed, and no historical report was edited.

---

## C. Prior evidence review

The Phase 4 study (~36,000 matches) and Phase 5 qualification (21,120 matches) were re-read in
full and their claims checked against the Alpha4 tree rather than assumed.

### C.1 What reproduces exactly

| Prior claim | Status at Alpha4 |
|---|---|
| Seeded placement removes the closed-form opposite-core exploit | **Confirmed** — `placement.seeded_seat_starts` is live; all eleven pinned vectors reproduce on this machine (e.g. `(2, 256, 0) → (82, 219)`, `(2, 512, 3) → (495, 387)`) |
| Round-robin removed the declaration-order advantage | **Confirmed** in source: `RulesetPolicy.process_selection == "round_robin"` for alpha2, `"priority"` for alpha1 |
| `hydra_alpha2` / `nemesis_alpha2` remain highly viable | **Confirmed and strengthened** — at the evaluation default arena (4096) they are the top two of a seven-agent roster at 88.8% and 66.9% (§G.1) |
| Reach is free | **Confirmed from source.** Declaration validation accepts any integer reach in `[1, arena_size − 1]` and applies no cost of any kind; `share` is validated independently; no `RulesetPolicy` axis references reach; a large-reach process is not itself more detectable, because visibility is computed from the *observer's* reach only (`ProcessMatchController._visible_enemy_anchors`) |
| `agents evaluate` excludes alpha2 | **Confirmed behaviourally** — argparse rejects it: `invalid choice: 'bytefray-rules-4-alpha2'` |

### C.2 What this study refines

Two Phase 5 statements are narrower than their wording suggests, and the difference matters for
the freeze decision.

**Phase 5 §K.1 — "reach buys information for free … an agent declaring `arena_size // 2` reach
detects the whole arena at tick 0 at zero cost."** The first half is exactly right. The
implication that this hands over the objective is not: detecting *anchors* is not the same as
detecting the *core*, and the two coincide only while the opponent is still standing on its start.
Measured, a maximum-reach probe gets an unambiguous core read on its first callback in 52.1% of
matches, not ~100% (§D.4). The reason is the scheduler: every such probe's first callback lands at
tick 1, and the entrant acting second in that tick already sees an opponent that has moved.

**Phase 5 §K.2 — "short-reach agents mostly never meet" (3.4% mutual contact).** This is a
property of the *shipped short-reach agents*, not of the Ruleset. In this study's short-reach-only
matchups (reach 4 and 16 probes, purpose-built to search) mutual contact is **100.0%**, with a
median first-mutual-contact tick of 10.5 (§D.6). Inspection of `v4_scout` shows why the shipped
figure is so low: when an enemy is visible but out of reach it falls through to
`MOVE(operand=self_reach)` — a fixed positive step that can move *away* from the target — and it
retains no memory of a sighting. The Ruleset supports local search; the bundled starters do not
perform it.

Neither refinement contradicts a Phase 4 or Phase 5 *experiment*; both narrow an inference drawn
in a closing discussion. The historical reports are left unedited.

### C.3 What was genuinely unanswered

* Whether a probe *designed* to exploit tick-0 co-location disclosure dominates. Neither
  `hydra_alpha2` nor `nemesis_alpha2` attempts it — both re-aim at the *current* nearest anchor on
  every sighting (`nemesis_alpha2._absorb_sighting` sets `target_confirmed = True` unconditionally),
  so neither latches the tick-0 core. The strongest shipped agents leave the exploit on the table.
* Whether reach advantage is arena-scale dependent, and specifically what happens at 4096 — the
  default arena for `agents evaluate` and therefore the size at which most product measurement
  actually happens. Phase 4 and Phase 5 both stopped at 1024.
* What a stable evaluation methodology should be. Phase 5 explicitly deferred this
  ("adopting alpha2 there needs a methodology decision this Ruleset change does not supply").

---

## D. Question A — spatial and reach research

### D.1 What healthy v4 spatial gameplay would look like

Stated before measuring, as hypotheses to test rather than conclusions. Alpha2 is healthy on this
axis to the extent that:

| # | Criterion | How it is measured here |
|---|---|---|
| H1 | Position sometimes affects decisions and outcomes | Win-rate spread across reach rungs; win rate conditional on first-callback disclosure |
| H2 | MOVE has strategic uses beyond cosmetic wandering | Anchor changes, total displacement, stationary fraction, correlated with win rate |
| H3 | Discovering an opponent sometimes requires behaviour, not just declaration-time reach | Actions before first sighting; first-callback core-disclosure rate by rung |
| H4 | Process specialisation offers something one omniscient process cannot trivially reproduce | `rp_pack` (scout+striker) and `rp_swarm` (dispersed trio) vs `rp_sentry` (global) |
| H5 | Local-vs-global strategies exhibit tradeoffs | Shape of the win curve over the reach ladder |
| H6 | Spatial uncertainty survives past tick 0 in meaningful parts of the ecology | Share of matches where max reach obtains no unambiguous core read |
| H7 | Multi-process entrants gain interesting choices, not just more endpoints | Dispersion metrics and win rate for `rp_swarm`/`rp_pack` |
| H8 | Matches are not overwhelmingly stalemated by localisation | Draw rate and tick-limit rate by reach class |
| H9 | No single simple reach strategy invalidates the rest of the spatial system | Whether any one rung dominates across arenas |

### D.2 The adversarial probe roster

Nine research-only probes, none promoted to `agents/` or the bundled starters, all using only
Agent API v2 surfaces and none given privileged information.

**The reach ladder** — five probes stamped from one template by
`tools/v4_pre_rc_generate_probes.py`, verified byte-identical apart from a single `REACH_MODE`
literal (the generator's `--check` mode re-verifies this on demand):

| Probe | Declared reach | Role in the design |
|---|---|---|
| `rp_seek_r4` | 4 | Local hunter — must search, barely wider than the 8-cell core |
| `rp_seek_r16` | 16 | Local hunter — two core widths |
| `rp_seek_r64` | 64 | Medium-reach mobile attacker — exactly Alpha2's minimum core separation |
| `rp_seek_rquarter` | `arena/4` | Wide but not global |
| `rp_seek_rhalf` | `arena/2` | Global sensor/writer — the legal maximum, covers every address |

Their targeting is **deliberately borrowed from the shipped, demonstrated-strong Alpha2 agents**
rather than invented: latch the nearest visible enemy anchor, sweep the ±7 window around it (the
`nemesis_alpha2._SIEGE_SPAN` value, wide enough to cover an 8-cell core wherever inside it the
sighting landed), WRITE window cells in reach and MOVE toward those that are not, abandon a lead
after three fruitless sweeps, and sweep the arena at `2 × reach` steps when nothing is known.
Approach speed is held at the engine's 64-cell MOVE clamp for every rung, so a short-reach probe is
not additionally penalised on travel speed in an experiment about sensing range. They carry no
defence: the ladder is a measurement of information acquisition and delivery, which is what reach
controls, not of repair economics.

**The archetypes** — four purpose-built designs plus the exploit probe:

| Probe | Shape | Question it isolates |
|---|---|---|
| `rp_oracle` | global `executioner` (0.875) + reach-8 `keeper` (0.125) | Does latching the *tick-0* sighting as the enemy core base — which co-location makes exact — dominate? |
| `rp_sentry` | global `siege` (0.75) + reach-8 `warden` (0.25), never relocates | The steelman: the strongest free-reach entrant the rules permit, so counterplay is tested against a good global strategy rather than a careless one |
| `rp_pack` | reach-32 `scout` (0.25, senses only) + reach-16 `striker` (0.75) | Does specialisation beat one omniscient process, given strictly less total information? (H4) |
| `rp_warden` | reach-8 `guard` (0.5, repairs) + reach-24 `stinger` (0.5, disrupts) | Is localised interference a viable answer, without core-racing? |
| `rp_swarm` | three reach-24 processes on different headings | Does *earned* dispersion create resilience and a sensor array? (H7) |

`rp_oracle` exists because neither shipped adapted agent attempts the exploit: both re-aim at the
current nearest anchor on every sighting, so neither latches the tick-0 core. Testing the concern
required building the agent nobody had built.

### D.3 Experimental design

Every match is one `NativeMatchService.run(MatchRequest)` under `bytefray-rules-4-alpha2`, with
both seats' starts omitted and resolved by `placement.resolve_direct_match_starts` exactly as
`bytefray run` resolves them. No research-only `MatchRequest` field exists, and nothing in the
engine was instrumented: every metric is reconstructed post hoc from the schema-4 replay and the
API-v2 agent trace the product already emits. The trace is what makes the information questions
answerable — each `decision_v2` record carries the exact `ObservationV2` the agent saw, so "how
many actions before this entrant had ever observed an enemy" is measured, not inferred.

| Experiment | Roster | Arenas | Seeds | Orientations | Matches |
|---|---|---|---|---|---|
| `ladder` | the 5 rungs, all pairs | 256, 512, 1024 | 0–15 | both | 960 |
| `ladder` (regime test) | the 5 rungs, all pairs | 4096 | 0–15 | both | 320 |
| `archetype` | 5 archetypes + 2 rungs + `hydra_alpha2`, `nemesis_alpha2`, `viper` | 256, 512, 1024 | 0–15 | both | 4,320 |
| `ladder_vs_ecology` | each rung × the shipped Alpha2 roster | 512 | 0–7 | both | 720 |

Tick budget 1000 throughout, matching Phase 4/Phase 5 so the numbers mean the same thing.
16 seeds × both seats × 3 arenas is the scale Phase 4 established as sufficient for effects of tens
of percentage points, and the effects below are of that size.

`ladder_vs_ecology` was **deliberately narrowed to arena 512 mid-study**, from a planned
3-arena/2,160-match sweep to a 1-arena/720-match one. Its role is corroboration — checking that the
ladder's ordering is a property of the game rather than of the probes playing each other — and
§G.1b independently supplies that check with real shipped agents at two arena scales and confidence
intervals. Spending a further ~90 minutes of runtime on a third corroboration that could not change
any disposition was not a good use of the budget, and 512 is the arena the report goes on to
recommend. The abandoned partial run was **not** used for any number in this report: a partial
sweep of this harness is pair-major, so it covers the first few pairs across all arenas and none of
the rest, which would be a biased sample. It is preserved unanalysed at
`raw_results/_abandoned_ladder_vs_ecology_3arena_partial.jsonl` rather than deleted.

### D.4 The controlled reach ladder: information is monotone, winning is not

960 matches, n = 384 per rung, arenas 256/512/1024 pooled. Median 5 ticks, tick-limit 44.8%,
draw 52.6%, mutual contact 84.7%.

| Rung | Declared reach | **Win rate** | 95% CI | Strict tick-0 core disclosure | Median actions before first sighting | Median tick of first enemy-core write | Anchor changes | Total displacement | Stationary ticks |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| `rp_seek_r4` | 4 | **3.4%** | [2.0, 5.7] | 0.0% | 32 | 4 | 685.6 | 5,433 | 10.4% |
| `rp_seek_r16` | 16 | **19.3%** | [15.6, 23.5] | 0.0% | 10 | 2 | 2.3 | 411 | 84.3% |
| `rp_seek_r64` | 64 | **35.4%** | [30.8, 40.3] | 1.3% | 3 | 2 | 42.1 | 20,373 | 81.2% |
| `rp_seek_rquarter` | arena/4 | **34.6%** | [30.0, 39.5] | 11.7% | 2 | 2 | 39.9 | 20,124 | 85.9% |
| `rp_seek_rhalf` | arena/2 | **25.8%** | [21.7, 30.4] | **52.1%** | 0 | 1 | 0.0 | 0 | 100.0% |

Two curves, and they point in different directions.

**Information is strictly monotone in reach**, exactly as the free-reach concern predicts. Median
actions taken before ever observing an enemy falls 32 → 10 → 3 → 2 → **0**; the first enemy-core
write lands at median tick 4 → 2 → 2 → 2 → **1**; and unambiguous tick-0 core disclosure rises
0% → 0% → 1.3% → 11.7% → **52.1%**. Buying reach buys information, at no cost, precisely as
alleged.

**Winning is not monotone.** The curve is an inverted U peaking at reach 64, and the legal maximum
(25.8%) is beaten by both mid-reach rungs and lands only 6.5 points above reach 16. Non-overlapping
confidence intervals separate `rp_seek_r64` [30.8, 40.3] from `rp_seek_rhalf` [21.7, 30.4]: this is
a real effect, not sampling noise.

**H2 and H5 hold clearly.** The two winning rungs are the two that travel: `rp_seek_r64` and
`rp_seek_rquarter` each relocate ~40 times for ~20,000 cells of displacement per match. The rung
that never moves at all (0 anchor changes, 100% stationary) does worse than both. Movement is not
cosmetic in this regime; it is what the winning strategies do.

### D.5 Why the maximum rung loses — and the arena-size regime where it stops losing

The trace answers this directly. Splitting each wide-reach rung's own matches by whether its very
first callback disclosed the enemy core:

| Rung | n disclosed | Win rate **when disclosed** | n not disclosed | Win rate **when not disclosed** |
|---|---:|---:|---:|---:|
| `rp_seek_rhalf` | 200 | 49.5% | 184 | **0.0%** |
| `rp_seek_rquarter` | 45 | 51.1% | 339 | 32.4% |
| `rp_seek_r64` | 5 | 80.0% | 379 | 34.8% |

A stationary global attacker that misses the tick-0 disclosure wins **zero of 184** matches. It
has bought perfect knowledge of where every enemy *anchor* is and no way to convert it, because it
has surrendered the ability to move and an anchor that has left its core is not the objective.

The disclosure is a coin flip for a structural reason, not a geometric one. `rp_seek_rhalf`'s first
callback lands at tick 1 in **384 of 384** matches, and the Alpha1/Alpha2 entrant scheduler is
`K = 2` chunked with a rotating start — so within tick 1 the entrant acting second already observes
an opponent that has moved. Disclosure is decided by scheduling order, and it is 52.1% at arenas
256/512/1024 and 52.3% at arena 4096: flat, because it never depended on distance at all.

**What does depend on arena size is the value of that disclosure**, and this is the study's most
release-relevant finding. Re-running the identical ladder at arena 4096:

| Rung | Reach | Win rate @ 256/512/1024 | **Win rate @ 4096** | Displacement @ 4096 | Median tick of first core write @ 4096 |
|---|---:|---:|---:|---:|---:|
| `rp_seek_r4` | 4 | 3.4% | 2.3% | 7,773 | 38 |
| `rp_seek_r16` | 16 | 19.3% | 14.8% | 3,143 | 10 |
| `rp_seek_r64` | 64 | **35.4%** | 16.4% | 90,134 | 5 |
| `rp_seek_rquarter` | arena/4 | 34.6% | 40.6% | 88,848 | 2 |
| `rp_seek_rhalf` | arena/2 | 25.8% | **54.7%** | 0 | 1 |

At 4096 the inverted U straightens into a **monotone increasing** curve, and maximum reach wins
outright at 54.7% against 2.3% for the smallest rung — a 52-point spread bought by one free
declaration. The mechanism is visible in the same table: the mid-reach rung's answer to a distant
sighting is to travel, and at 4096 that costs it 90,134 cells of displacement and delays its first
core write from tick 2 to tick 5, while the global rung still strikes at tick 1 without moving.

Within-arena breakdown of the smaller corpus shows the same gradient already forming:

| Rung | 256 | 512 | 1024 | 4096 |
|---|---:|---:|---:|---:|
| `rp_seek_r64` | 47.7% | 32.8% | 25.8% | 16.4% |
| `rp_seek_rquarter` | 47.7% | 30.5% | 25.8% | 40.6% |
| `rp_seek_rhalf` | 19.5% | 21.9% | 35.9% | **54.7%** |
| `rp_seek_r16` | 19.5% | 19.5% | 18.8% | 14.8% |
| `rp_seek_r4` | 3.1% | 2.3% | 4.7% | 2.3% |

**Which regime is the product's?** Both, on different surfaces:

| Surface | Default arena | Regime |
|---|---|---|
| Agent Designer Simple/Advanced — the primary v4 authoring and play surface | **512** (`app/services/engine_commands.py`'s `RunConfig.arena`) | healthy: inverted U, mid reach beats max reach, movement pays |
| `bytefray run` with `--arena` omitted | **4096** (`Config.arena_size`) | reach-dominated |
| `agents evaluate` with `--arena-size` omitted | **4096** | reach-dominated |

Phase 4 and Phase 5 both tested 256/512/1024 — so the entire shipped v4 gameplay evidence base
characterises the Designer's regime and **never tested the CLI/evaluation default arena at all**.
That is a real gap in the prior qualification, and it is what turns "free reach is a documented
limitation" into a decision with a concrete, non-Ruleset mitigation (§E, §H.1).

### D.6 Contact is not the problem — and it is not the solution either

Splitting the ladder corpus by reach class:

| Matchup class | n | Contact | **Mutual contact** | Draw | Tick-limit | Median ticks |
|---|---:|---:|---:|---:|---:|---:|
| Short-reach only (r4/r16) | 96 | 100.0% | **100.0%** | 99.0% | 99.0% | 1000 |
| Mixed | 576 | 95.5% | 82.6% | 56.6% | 54.0% | 1000 |
| Long-reach only (r64/rq/rh) | 288 | 93.4% | 83.7% | 29.2% | 8.3% | 3 |

Short-reach agents that are actually written to search find each other **every single time**, at a
median first-mutual-contact tick of 10.5. Phase 5's 3.4% figure measures the bundled starters, not
the Ruleset (§C.2). H3 and H6 hold: discovery genuinely requires behaviour at short reach, and
uncertainty survives well past tick 0 for most of the ecology.

But contact does not decide anything, and this is the deepest structural finding of the study:

| | n | Decided (not a draw) |
|---|---:|---:|
| Matches with ≥ 1 enemy-core write | 611 | **73.3%** |
| Matches with no enemy-core write | 349 | **2.0%** |

| Matchup class | Mutual contact | **Ever lands an enemy-core write** | Decided | Contact but no core write |
|---|---:|---:|---:|---:|
| Short-reach only | 100.0% | **4.2%** | 1.0% | **95.8%** |
| Mixed | 82.6% | 59.5% | 43.4% | 38.5% |
| Long-reach only | 83.7% | 91.7% | 70.8% | 1.7% |

**95.8% of short-reach-only matches are sustained mutual engagements in which neither side ever
touches the other's core.** The spatial game has two layers that barely connect: a *mobile contact*
layer, which is active, reciprocal and tactically busy, and a *static core* layer, which is the only
thing that decides matches. A roaming process's anchor is evidence of the enemy's presence but not
of its objective, because the core stays at the start address while the process leaves. Reach's
real function in Alpha2 is narrow and specific: it is the only way to observe the enemy *before it
separates from its core*.

This is why H8 is the criterion Alpha2 fails most clearly: localisation does not stalemate the game
by preventing contact, it stalemates it by making contact inconsequential.

### D.7 Counterplay: can local, specialised and dispersed designs beat a good global strategy?

4,320 matches, ten entrants (five archetypes, two ladder rungs, three shipped agents), 45 pairs,
arenas 256/512/1024, seeds 0–15, both orientations, n = 864 per entrant. Median 6 ticks,
tick-limit 19.3%, draw 16.5%.

| Entrant | Max reach | **Win rate** | 95% CI | Anchor changes | Displacement | Stationary | Strict tick-0 disclosure |
|---|---:|---:|---|---:|---:|---:|---:|
| `rp_oracle` (tick-0 exploiter) | arena/2 | **72.5%** | [69.4, 75.3] | 0.0 | 0 | 100.0% | 66.7% |
| `rp_seek_r64` (mid-reach mobile) | 64 | **64.0%** | [60.7, 67.1] | 1.6 | 268 | 84.0% | 1.9% |
| `rp_swarm` (dispersed trio) | 24 | **54.7%** | [51.4, 58.0] | 103.2 | 8,700 | 53.1% | 0.0% |
| `rp_seek_r16` (local) | 16 | 51.3% | [47.9, 54.6] | 2.7 | 308 | 82.8% | 0.0% |
| `rp_sentry` (global steelman) | arena/2 | **47.7%** | [44.4, 51.0] | 0.0 | 0 | 100.0% | 66.7% |
| `hydra_alpha2` (shipped) | arena/2 | 42.9% | [39.7, 46.3] | 6.5 | 536 | 68.0% | 72.2% |
| `nemesis_alpha2` (shipped) | arena/2 | 39.1% | [35.9, 42.4] | 0.0 | 0 | 100.0% | 66.7% |
| `rp_pack` (scout+striker) | 32 | 34.6% | [31.5, 37.8] | 193.4 | 34,869 | 27.6% | 0.0% |
| `viper` (shipped) | 10 | 10.5% | [8.7, 12.8] | 21.0 | 239 | 85.4% | 0.0% |
| `rp_warden` (pure defence) | 24 | **0.0%** | [0.0, 0.4] | 3.3 | 42 | 84.0% | 0.0% |

**The tick-0 exploit is real, it is the best strategy in the roster, and it does not dominate.**
`rp_oracle` — which never moves, never searches, and does nothing but overwrite the eight cells at
the first address it ever sees — tops the table at 72.5%. Its pairwise record shows exactly where
that comes from and where it stops:

| `rp_oracle` vs | W–L–D | Win% |
|---|---|---:|
| `rp_sentry` | 96–0–0 | **100%** |
| `viper` | 96–0–0 | 100% |
| `rp_warden` | 93–0–3 | 97% |
| `rp_pack` | 84–12–0 | 88% |
| `hydra_alpha2` | 62–34–0 | 65% |
| `rp_swarm` | 51–45–0 | 53% |
| `nemesis_alpha2` | 48–48–0 | **50%** |
| `rp_seek_r16` | 48–48–0 | **50%** |
| `rp_seek_r64` | 48–48–0 | **50%** |

Against three different opponents — a shipped global agent, a **reach-16 local** probe and a
reach-64 mobile probe — it is exactly 48–48. That is the 52% disclosure coin flip resolving to its
true value: whoever wins the tick-1 scheduling order lands its core strike first, and the reach
advantage buys nothing beyond it. A reach-16 entrant draws even with an omniscient one.

**Counterplay against a good global strategy is strong and comes from movement.** `rp_sentry` is
the strongest *conventional* free-reach design the rules permit — global sensing plus a dedicated
core-repair process, no wasted actions — and it finishes below the median at 47.7%, losing to:

| `rp_sentry` vs | W–L–D | Sentry win% |
|---|---|---:|
| `rp_seek_r64` | 33–59–4 | **34%** |
| `rp_swarm` | 39–49–8 | **41%** |
| `hydra_alpha2` | 21–75–0 | 22% |
| `nemesis_alpha2` | 0–96–0 | 0% |
| `rp_oracle` | 0–96–0 | 0% |

A reach-64 mobile probe beats it 59–33 and a dispersed reach-24 trio beats it 49–39. **H1, H2 and
H5 are satisfied here as clearly as anywhere in the study**: position and movement decide these
matchups, and the entrant with strictly more information loses them.

**H7 holds; H4 does not.** `rp_swarm` — three reach-24 processes that earn their separation by
fanning out, then converge on a sighting — reaches 54.7% and beats the global steelman, with the
highest movement figures of any winning entrant (103 anchor changes, 8,700 cells, only 53%
stationary). Dispersion is worth something. But `rp_pack`'s scout/striker split, the direct test of
"specialisation beats one omniscient process", finishes at 34.6% — **below** `rp_sentry` — despite
travelling four times as far. Its striker spends the match chasing fixes its scout generates, and a
sighting of a roaming process is exactly the information §D.6 shows to be inert. Specialisation
paid when it produced *separated sensors converging on a core* (`rp_swarm`) and did not pay when it
produced *a dedicated finder feeding a dedicated fighter* (`rp_pack`).

**Pure defence is not viable.** `rp_warden` — repair plus local disruption, never core-racing —
wins **0 of 864**. Localised interference delays opponents but cannot convert, which is §D.6's
disconnect seen from the defensive side.

**The shipped roster has real headroom.** `hydra_alpha2` (42.9%) and `nemesis_alpha2` (39.1%) sit
mid-table, beaten by four probes. Both obtain the tick-0 disclosure at the same ~67–72% rate as
`rp_oracle` and neither exploits it, because both re-aim at the current nearest anchor on every
sighting. This is evidence that the ladder rungs are competitive designs rather than strawmen, and
that Alpha2's strategy space is not close to solved.

### D.8 Cross-check: the ladder ordering against the shipped roster

720 matches, each ladder rung against all nine shipped Alpha2-era entrants, arena 512, seeds 0–7,
both orientations. This exists to rule out the possibility that §D.4's ordering is an artefact of
the probes playing only each other.

| Entrant | Reach | Win rate | 95% CI | Strict disclosure | Median actions before first sighting |
|---|---:|---:|---|---:|---:|
| `rp_seek_r64` | 64 | **67.4%** | [59.3, 74.5] | 0.0% | 4 |
| `rp_seek_rquarter` | 128 | 59.0% | [50.9, 66.7] | 28.5% | 1 |
| `rp_seek_rhalf` | 256 | **58.3%** | [50.2, 66.1] | 72.2% | 0 |
| `rp_seek_r16` | 16 | 56.9% | [48.8, 64.7] | 0.0% | 8 |
| `nemesis_alpha2` | 256 | 46.2% | [35.7, 57.1] | 63.7% | 0 |
| `hydra_alpha2` | 256 | 33.8% | [24.3, 44.6] | 63.7% | 0 |
| `rp_seek_r4` | 4 | 21.5% | [15.6, 28.9] | 0.0% | 41 |
| `v4_claimer` | 1 | 17.5% | [10.7, 27.3] | 0.0% | 16 |
| `viper` | 10 | 5.0% | [2.0, 12.2] | 0.0% | 20 |
| `local_hunter`, `v4_concentrated_attacker`, `v4_defender_scout`, `v4_local_defender`, `v4_scout` | 2–12 | 0.0% | [0.0, 4.6] | 0.0% | 23–88 |

**The ordering holds.** Reach 64 beats the legal maximum against real opponents too (67.4% vs
58.3%), so §D.4's inverted U is a property of the game, not of the probe family. Disclosure stays
strictly reach-gated (0% at reach ≤ 64, 28.5% at arena/4, 72.2% at arena/2), confirming again that
reach buys information monotonically while the win curve does not follow it.

Two further observations. **A reach-16 probe (56.9%) outperforms both shipped adapted agents**
(46.2% and 33.8%), and even the reach-4 rung (21.5%) beats `viper` and every zero-win starter — so
short-reach play is viable against the actual roster, not merely against other probes. And **five
of the nine shipped entrants win nothing at all** here, with median actions-before-first-sighting
of 23–88 against the probes' 0–8; §C.2's reading that the bundled starters do not search
effectively is visible directly in that column.

### D.9 Three representative matches

Every field below comes from the recorded corpus and each match is reproducible from the tuple
given (`tools/v4_pre_rc_reach_study.py`'s `build_request` is a pure function of it).

**A and B are the same pair, the same arena, the same seed — and differ only in orientation.**
Together they are the whole reach finding in two matches.

**A — `rp_seek_r4` vs `rp_seek_rhalf`, arena 256, seed 0, orientation `b_first`.** Starts
`(82, 219)`, separation 119; `rp_seek_rhalf`'s core at 82, `rp_seek_r4`'s at 219. `rp_seek_rhalf`
acts first in tick 1, and its visible set is exactly `[219]` — one address, its opponent's core
base, because that opponent has not yet moved. It never issues a MOVE. It writes eight enemy core
cells and the match ends at **tick 2** by `last_agent_standing`. Total distance travelled: 0.

**B — the identical pairing at orientation `a_first`.** Same seed, same starts, opposite acting
order. `rp_seek_r4` moves before `rp_seek_rhalf`'s first callback, so `rp_seek_rhalf`'s visible set
at tick 1 is `[98]` — a relocated process, not a core. From there it has perfect visibility of
every enemy anchor for 1,000 ticks, issues **0** MOVEs, lands **0** enemy-core writes, and the
match ends at the tick limit as a draw. Its opponent meanwhile lands **3,488** enemy-core writes
across 1,513 relocations and still cannot finish, because `rp_seek_rhalf` sits on its own core and
its ±7 attack window — aimed at the intruder camped there — overlaps that core, so every "attack"
re-establishes its own ownership of the cell it lands on (`vm._wr8(target, value, owner=...)` makes
the writer the owner, and core capture requires the defender to own *zero* of its eight cells).
Defence by counter-attack is emergent here, not designed.

**C — `rp_seek_r4` vs `rp_seek_r16`, arena 256, seed 0, orientation `a_first`.** Starts
`(82, 219)`. Neither ever obtains a tick-0 disclosure. They find each other at **tick 31** and
remain in contact for **996 of 1,000 ticks**. Combined enemy-core writes: **zero**. The match is a
tick-limit draw. This is §D.6's disconnect in a single record: sustained, reciprocal, entirely
inconsequential contact.

### D.10 Falsifying both interpretations

The task required testing the strongest version of each reading rather than assuming one.

**"Reach is just one legitimate strategic declaration."** This survives at arenas ≤ 1024 and fails
at 4096. Supporting it: the win curve is an inverted U (D.4); maximum reach costs a stationary
posture that is fatal without the tick-0 disclosure (0/184, D.5); movement and specialisation are
live, rewarded behaviours (D.4, D.7, D.8); and uncertainty survives past tick 0 in ~48% of matches even
against the maximum rung. Against it: at 4096 the curve is monotone and the global rung wins 54.7%
while never moving once.

**"Large reach collapses the information game, leaving MOVE and locality as secondary mechanics."**
This is *directionally* confirmed on the information axis and *refuted* on the outcome axis in the
qualified regime. Information genuinely is bought outright and monotonically (D.4). But in the
Designer's own arena the entrants that win are the ones that move, and the omniscient one is not
the best. The collapse is real at 4096 and not at 512.

The two readings are therefore not in conflict once the arena axis is added: **free reach buys
information unconditionally, but converting information into a win requires either movement or a
one-tick scheduling accident, and which of those dominates is a function of arena scale.**

---

## E. Question A decision

```text
ACCEPT WITH DOCUMENTED LIMITATION
```

### E.1 The hypotheses, scored

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| H1 | Position affects decisions and outcomes | **Holds** | `rp_seek_r64` beats the global steelman 59–33; global reach wins 49.5% with tick-0 disclosure and 0/184 without |
| H2 | MOVE has strategic uses beyond wandering | **Holds** | The two best ladder rungs are the two that travel; `rp_swarm` beats `rp_sentry` with 103 relocations per match |
| H3 | Discovery sometimes requires behaviour | **Holds** | Zero tick-0 disclosure below reach 64; median 32 actions before first sighting at reach 4 |
| H4 | Specialisation offers what one omniscient process cannot | **Fails** | `rp_pack` 34.6%, below `rp_sentry` 47.7%, despite 4× the displacement |
| H5 | Local-vs-global tradeoffs exist | **Holds** ≤1024, **fails** at 4096 | Inverted-U curve below 1024; monotone at 4096 |
| H6 | Spatial uncertainty survives past tick 0 | **Holds** | Maximum reach obtains no unambiguous core read in ~48% of matches, and 33% even by the looser partial measure |
| H7 | Multi-process entrants gain interesting choices | **Holds** | `rp_swarm` 54.7%, above both global designs it faces |
| H8 | Not overwhelmingly stalemated by localisation | **Fails** | 95.8% of short-reach-only matches are mutual engagements that never touch a core; 99% draw |
| H9 | No single simple reach strategy invalidates the rest | **Holds, narrowly** | `rp_oracle` leads at 72.5% but draws 50/50 with a reach-16 probe, a reach-64 probe and `nemesis_alpha2` |

Seven of nine hold. The two failures are real and are the substance of the documented limitation.

### E.2 Why this is not "do not freeze"

The task's bar is *a material design flaw we would regret freezing*, not *a theoretically better
game*. Against that bar:

* **Free reach is not a solved strategy.** The single best exploit of it available under the
  current rules — `rp_oracle`, purpose-built for this study because nothing shipped attempts it —
  reaches 72.5%, comparable to `nemesis_alpha2`'s own 74.3% in Phase 5's ecology. It is not a new
  tier, and it draws exactly even with a reach-16 probe.
* **The spatial mechanics are load-bearing where it counts.** Movement, mid reach and earned
  dispersion each beat the strongest stationary global design. An entrant with strictly *less*
  information wins those matchups.
* **The weaknesses are addressable without touching the Ruleset.** The dominant one (H5 at scale)
  is an *arena-size* interaction, and arena size is explicitly a configuration value rather than
  Ruleset identity (`docs/RULES.md`, "Configuration values are not Ruleset identity"). The Agent
  Designer already runs in the healthy band. Nothing here requires a new gameplay contract.
* **The cost of not freezing is high and concrete.** An Alpha5 would re-open Agent API v2 exposure,
  invalidate `hydra_alpha2`/`nemesis_alpha2` as tuned references, require a fresh paired ecology
  qualification, and delay a 4.0 whose gameplay contract is otherwise qualified, cross-platform
  pinned, and shipping cleanly.

### E.3 What is being accepted, stated plainly

Three properties become disclosed characteristics of Bytefray 4.0 rather than open questions:

1. **Reach is free and buys information monotonically.** Declaring `arena_size // 2` costs nothing
   and yields complete anchor visibility from the first callback. This is a deliberate,
   evidence-reviewed property, not an oversight.
2. **Tick-0 core disclosure is a ~52–67% coin flip decided by scheduling order.** Because processes
   still start co-located on their core and the entrant scheduler rotates, an entrant with global
   reach sometimes reads the opponent's core base exactly, before that opponent has moved. Whether
   it does is decided by which entrant acts first in tick 1.
3. **Contact and core capture are weakly connected layers.** Short-reach entrants find each other
   reliably (100% mutual contact when well written) but almost never convert (4.2% ever land a core
   write). Localised play produces engagement without decision.

### E.4 Ranked candidate directions for post-4.0 reach research

Recorded for a later phase and **deliberately not implemented, prototyped, or designed further
here**. Ranked by the size of the measured problem each addresses:

1. **Detection radius distinct from READ/WRITE reach.** The measured pathology is specifically that
   *sensing* is free and unbounded while *acting* is not; separating the two attacks it directly
   and leaves the offensive geometry alone. Highest expected value.
2. **Delayed or degraded initial visibility (e.g. anchors not reported on the first callback).**
   Targets property (2) exactly — the one-tick co-location window — at the smallest possible
   footprint, and would make the coin flip disappear without pricing reach at all.
3. **Reach cost or reach/share coupling.** The obvious economic fix, ranked below the two above
   because Phase 4 already measured a blunt reach *cap* as disarming rather than rebalancing
   (tick-limit rate 46.8% → 90.5%), and a cost is a softer version of the same lever.
4. **Narrowing the contact/core disconnect** (H8) — e.g. letting a core follow its entrant, or
   giving anchors more information. The largest design change and the least well-specified; it
   changes what Bytefray *is*, not just what reach costs.
5. **An information budget.** Most complex, least evidence behind it, listed last for completeness.

An Alpha5 investigating (1) or (2) would be a reasonable 4.1 research phase. It is not a 4.0
blocker.

---

## F. Question B — the current evaluation contract, reconstructed

Read from source at `010c3f6b…` and confirmed by running the real CLI.

### F.1 What an evaluation cell is

`agent_evaluation.build_matrix` generates the deterministic product
**subject × opponent × seed × placement × orientation**, in that nesting order, with iteration
order preserved exactly as requested (opponents and seeds are never re-sorted or deduplicated).
`subject` is the candidate, then the baseline when one is given. Each cell carries a
`schedule_id` (`stable_id("evaluation-cell", …)`), a `condition_fingerprint`, its own
`rules_compatibility_id`, and — under v2-family methodology — `placement_id`, `subject_start`,
`opponent_start`, `placement_index`.

Execution goes through `EvaluationService._execute_cell` → `agent_test.test_agent(...)`, the same
boundary `bytefray agents test` uses, with `agent_start` / `opponent_start` passed **explicitly**.

### F.2 Orientation

`ORIENTATION_CANDIDATE_FIRST` / `ORIENTATION_OPPONENT_FIRST`, both run by default
(`both_orientations = True`). `physical_slots_for_orientation` is the single authority mapping
evaluation role → physical slot; every field is stored from the *role* perspective regardless of
slot. Orientation swaps which agent occupies the always-first-acting slot **and** swaps the start
addresses with it: the subject always starts at `cell.subject_start` whichever slot it occupies.

### F.3 Seeds, and what a repeated match receives

Seeds come from `--seeds`/`--seed-range`, else a preset, else `STANDARD_V2_SEEDS = (1, 2, 3, 4, 5)`
for v2-family methodology, else `Config().seed` (1337). A repeated `(opponent, seed)` is preserved
as a genuinely distinct cell and disambiguated by `condition_occurrence_index` and by the matrix
`ordinal` inside `schedule_id`. **Each repetition of the same seed runs the identical match** —
the cell seed is the `Config.seed`, and per-entrant RNG is
`python_runtime.derive_agent_seed(match_seed, slot, agent_id, api_version)`, a SHA-256 of those
four inputs. There is no per-repetition seed jitter. Repetition therefore adds cells, not
information, unless the seeds themselves differ.

### F.4 How fixed placement is imposed

`standard_placements(arena_size)` returns three conditions derived mechanically as fractions of
the arena: `opposed` (0, N/2), `quarter` (0, N/4), `opposed-shifted` (N/4, 3N/4). These are
**passed to the match as explicit starts**, so `placement.resolve_direct_match_starts` — the seam
that would otherwise apply Alpha2's seeded layout — never fires. This is precisely why running
Alpha2 under today's methodology would be dishonest: the artifact would be labelled with a Ruleset
whose defining rule it suppressed.

The v1 methodology (omitted `--ruleset`, or explicit `bytefray-rules-1`) uses a single
`placement_id="fixed"` with both starts `0`.

Confirmed against a real artifact rather than read from source alone — a one-opponent, one-seed
`--ruleset bytefray-rules-4-alpha1` evaluation writes `matrix_size: 6`
(1 seed × 3 placements × 2 orientations), `arena_alignment_mode:
"ruleset_v2_standard_placements"`, `schema_version: 5`, and exactly these starts at the default
4096 arena:

| `placement_id` | `(subject_start, opponent_start)` | Circular separation |
|---|---|---:|
| `opposed` | `(0, 2048)` | 2048 |
| `opposed-shifted` | `(1024, 3072)` | 2048 |
| `quarter` | `(0, 1024)` | 1024 |

Three placements, **two** distinct separations. At the default five seeds that is 30 cells per
opponent, which is the baseline the §H.1 item 12 runtime comparison is against.

### F.5 Methodology identity, persisted fields, and comparison

| Concern | Mechanism |
|---|---|
| `rules_compatibility_id` | The request's *resolved* Ruleset, persisted top-level and per cell. It is a **gameplay** identity carried on the evaluation artifact, never an evaluation-methodology identity. |
| Methodology discriminator | Top-level `arena_alignment_mode`: `"fixed"` (v1), `"ruleset_v2_standard_placements"` (v2 1v1), `"ruleset_v2_group_standard_layouts"` (group). Also `orientation_mode`. |
| Which Ruleset selects which methodology | `_V2_METHODOLOGY_RULESET_IDS = {bytefray-rules-2, bytefray-rules-3-alpha1, bytefray-rules-4-alpha1}` — a finite, explicit set, never a prefix check. **`bytefray-rules-4-alpha1` is in it**, so a v4-alpha1 evaluation already runs the three standard placements and the five standard seeds. |
| `evaluation_id` | `stable_id("evaluation-v2", payload)` over identity_version, candidate/baseline/opponent identities, seeds, ticks, effective conditions, `rules_compatibility_id`, `arena_alignment_mode`, `orientation_mode`, and — for v2 methodology — the **resolved placement set itself**, not just its label. `workers` is deliberately excluded. |
| Schema / identity versions | 4 (v1), 5 (`SCHEMA_VERSION_V2`, v2 1v1), 6 (group). Resolved per request; a v1 request is byte-identical to every artifact ever written. |
| Comparison gate | `evaluation_history.comparison._condition_key` aligns two cells only on the full tuple `(opponent identity incl. `local_source_fingerprint`, seed, conditions fingerprint, rules id, arena_alignment_id, condition_occurrence_index, orientation, placement_id)`. Any `UNKNOWN` confidence returns `None` and the cell never aligns — **fails closed**. |
| Win rate / intervals | The persisted artifact stores raw counts only (`SubjectAggregate.wins/losses/ties`, `win_rate_display`). Wilson 95% intervals, the exact two-sided paired binomial test, and per-opponent/per-orientation breakdowns live in the derived, non-persisted `evaluation_analysis` layer. |
| Worker parallelism | `workers` is bounded subprocess parallelism over independent cells and is explicitly **not** part of `evaluation_id`. Cell results are pure functions of cell inputs, so determinism is worker-count independent. |
| Group vs pairwise | `--group` fields the whole roster as one N-entrant cell (seed × layout × seat assignment), requires `bytefray-rules-2`, and uses schema/identity 6. Orthogonal to this decision. |

### F.6 A reproducible defect found while reconstructing the contract

`agents evaluate` resolves an omitted `--ruleset` with
`resolve_omitted_ruleset_id(None, {"python"})` — the **kind-only** resolver, called with a
hardcoded literal — which always returns `bytefray-rules-2`. Every other product entry point
(`run`, `agents test`, `tournament`) was migrated to the metadata-aware
`resolve_omitted_ruleset_for_agents`, which reads the agent's declared API version.
`bytefray-rules-2` does not support Agent API v2.

Reproduced end to end on this machine:

```text
$ bytefray agents evaluate nemesis_alpha2 --opponents hydra_alpha2 --seeds 1 --ticks 50
failed cells:
  candidate=nemesis_alpha2 opponent=hydra_alpha2 seed=1 code=ruleset_agent_unsupported
    error=Ruleset 'bytefray-rules-2' does not support entrant metadata:
          A (python, Agent API 2), B (python, Agent API 2).
  ... (6 of 6 cells)
```

The resulting `evaluation.json` records `lifecycle_state: "finished"`, `complete: true`,
`rules_compatibility_id: "bytefray-rules-2"`, `arena_alignment_mode:
"ruleset_v2_standard_placements"`, six `failed` cells and `matches_played: 0`. It does not fail
fast, and it produces an artifact that a reader must inspect cell-by-cell to discover is empty.

This predates Alpha2: the line was introduced by `13798b4 fix: default Python CLI gameplay to
ruleset v2` (the v2.0.0-rc1 default-Ruleset fix), before Agent API v2 existed, and `agents
evaluate` was never migrated with its siblings. The coverage gap that let it ship is specific and
checkable: **every fixture agent in every `engine/tests/test_agent_evaluation*.py` module declares
`api_version: 1`**, so no evaluation test has ever executed an Agent API v2 roster; the sole
v4-related evaluation assertion checks the `--ruleset` help text
(`test_agent_evaluation_v2.py:171`). The only working v4 evaluation path today is the explicit
`--ruleset bytefray-rules-4-alpha1` (verified working); alpha2 is rejected at argparse, as designed.

**Scope: this is a CLI-only defect.** The Agent Designer is already protected, and by exactly the
mechanism the CLI is missing. `app/widgets/ruleset_combo.py` disables every option incompatible
with the selected entrants and replaces an incompatible current selection with
`best_designer_ruleset_for_agents(...)` — metadata-driven resolution over
`EVALUATION_RULESET_OPTIONS`, whose second entry is `bytefray-rules-4-alpha1`. An API-v2 agent
evaluated from the Designer therefore lands on alpha1 and runs. The fix for the CLI is to give it
the same metadata-driven resolution the GUI already performs, which is also what `run`,
`agents test` and `tournament` already do.

---

## G. Question B — placement, sample-size and orientation experiments

Corpus: 3,318 matches under `bytefray-rules-4-alpha2`, seven materially different archetypes (two
global multi-process attackers, a mid-reach mobile raider, a short-reach sweeper, a reach-1
claimer, a reach-2 turtle, one mid-reach probe), 21 pairs, both orientations, 200 ticks
(the evaluation CLI's own `DEFAULT_TICKS`), `instr_per_tick=8`.

* `fixed` @ arena 4096 — today's methodology applied to Alpha2: 3 `standard_placements` ×
  5 `STANDARD_V2_SEEDS` × 2 orientations = 630 matches.
* `seeded` @ arena 4096 — the candidate: placement from
  `placement.seeded_seat_starts(2, arena, seed)` over seeds 0–31, geometry bound to the seat,
  orientation swapping occupants = 1,344 matches.
* `seeded` @ arena 512 — the identical candidate design at the Agent Designer's own default arena,
  added after §D.5 showed the two arena scales are different games = 1,344 matches.

### G.1 The two conditions do not disagree about *who wins* — but they sample different games

| Agent | `fixed` win% (95% CI) | `seeded` win% (95% CI) |
|---|---|---|
| `hydra_alpha2` | 85.6% [79.7, 89.9] | 88.8% [85.3, 91.6] |
| `nemesis_alpha2` | 66.7% [59.5, 73.1] | 66.9% [62.1, 71.4] |
| `rp_seek_r64` | 63.3% [56.1, 70.0] | 61.5% [56.5, 66.2] |
| `viper` | 50.0% [42.8, 57.2] | 48.2% [43.2, 53.2] |
| `v4_claimer` | 50.0% [42.8, 57.2] | 45.3% [40.4, 50.3] |
| `v4_scout` | 0.0% [0.0, 2.1] | **2.6%** [1.4, 4.7] |
| `v4_local_defender` | 0.0% [0.0, 2.1] | 0.0% [0.0, 1.0] |

Across all 21 pairs the two conditions produce **zero verdict disagreements** and a mean absolute
score delta of only 0.033. Individual matchups move a lot more — `hydra_alpha2` vs `rp_seek_r64`
goes 0.17 → 0.41, and `v4_scout` vs `v4_claimer` goes 0.00 → 0.16 — but the direction holds.

**So the argument for changing the methodology is not that fixed placement gets the answer
wrong.** It is that fixed placement does not sample the game the Ruleset defines:

| | `fixed` | `seeded` |
|---|---|---|
| Distinct core separations sampled | **2** (1024, 2048) | **32** (320 … 2026) |
| Mean separation | 1707 | 1243 |
| Share of matches below 512-cell separation | **0.0%** | 9.4% |

Every `fixed` engagement is at a quarter or half of the arena. Alpha2's own rule permits anything
from 64 cells upward. The one place the difference is visible in an *outcome* is exactly where you
would predict: `v4_scout`, a reach-8 sweeper, records its only wins in the entire study under
seeded placement, because seeded placement is the only condition that ever starts it near enough
to matter.

An evaluation labelled `bytefray-rules-4-alpha2` that never produced a separation below a quarter
of the arena would be making a true statement about a game nobody plays.

### G.1b The arena size the methodology runs at changes the answer more than the placement rule does

Running the identical seeded design at the Agent Designer's own default arena (512) instead of the
inherited `Config.arena_size` (4096) does not merely shift the numbers — it reorders the roster:

| Agent | Max declared reach | `seeded` @ **4096** | `seeded` @ **512** |
|---|---|---:|---:|
| `hydra_alpha2` | arena/2 (global) | **88.8%** [85.3, 91.6] | 66.1% [61.3, 70.7] |
| `nemesis_alpha2` | arena/2 (global) | 66.9% [62.1, 71.4] | 65.6% [60.7, 70.2] |
| `rp_seek_r64` | 64 (mobile) | 61.5% [56.5, 66.2] | **76.0%** [71.5, 80.0] |
| `viper` | 10 | 48.2% [43.2, 53.2] | 19.5% [15.9, 23.8] |
| `v4_claimer` | 1 | 45.3% [40.4, 50.3] | 30.5% [26.1, 35.2] |
| `v4_scout` | 8 | 2.6% [1.4, 4.7] | **16.7%** [13.3, 20.7] |
| `v4_local_defender` | 2 | 0.0% [0.0, 1.0] | 0.0% [0.0, 1.0] |

At 4096 a global-reach agent tops the table by 22 points. At 512 the winner is the mid-reach mobile
probe, with the two global agents 10 points behind it and the short-reach sweeper recording six
times as many wins. Median match length falls from 152 ticks to 18. These are the same agents, the
same Ruleset, the same placement rule and the same seeds; only the arena differs, and it is the
single largest methodology lever found in this study — larger than the fixed-vs-seeded placement
change it was introduced to evaluate.

**The methodology must therefore pin an explicit arena size rather than inherit one**, and the
evidence points to a value inside the band the Ruleset was actually qualified in. Phase 4 and
Phase 5 characterised the v4 ecology at 256/512/1024 and never at 4096; the Agent Designer — the
primary surface on which v4 agents are authored and played — defaults to 512. Evaluating at 4096
would rank agents by a reach dominance that neither the qualification corpus nor the Designer's own
gameplay exhibits. **Recommendation: pin 512.** This is a decision a maintainer should ratify
explicitly (§J), because it is a methodology default with a permanent identity attached, not a
number this study can settle unilaterally.

### G.2 Sample size — where the conclusion stops moving

Seeds 0–31 were cut into disjoint consecutive blocks of size *k*; each block is an independent
"methodology run". Reported: how often two independent blocks disagree about who won a matchup,
and how far apart they put the subject's score.

| k (seeds) | matches per cell | blocks | flip @ 4096 | spread @ 4096 | flip @ 512 | spread @ 512 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 2 | 32 | 8.3% | 0.190 | 8.9% | 0.131 |
| 2 | 4 | 16 | 4.4% | 0.131 | 7.0% | 0.095 |
| 4 | 8 | 8 | 3.2% | 0.080 | 2.4% | 0.060 |
| **8** | **16** | **4** | **3.2%** | **0.054** | **0.0%** | **0.036** |
| 16 | 32 | 2 | 0.0% | 0.028 | 0.0% | 0.009 |

Roster **ranking** stability over the same blocks:

| k | identical full ranking @ 4096 | same top @ 4096 | identical full ranking @ 512 | same top @ 512 |
|---:|---:|---:|---:|---:|
| 1 | 27% | 100% | 35% | 65% |
| 2 | 24% | 100% | 36% | 77% |
| 4 | 75% | 100% | 46% | 100% |
| **8** | **100%** | **100%** | 33% | **100%** |
| 16 | 100% | 100% | 0% | 100% |

**k = 8 is the knee, on the metric that means something.** Pairwise verdict flip reaches 0.0% at
k = 8 at arena 512 and 3.2% at 4096 — and that residual is entirely one matchup,
`hydra_alpha2` vs `rp_seek_r64`, whose four block scores are 0.22 / 0.50 / 0.50 / 0.44. A matchup
whose true value *is* ≈ 0.5 will always "flip"; no sample size fixes that. Below k = 8 the flip
rate is 2–3× higher at both arenas and the score spread roughly doubles. k = 16 buys 0.018–0.027 of
spread for double the cost and does not change a single conclusion at either arena.

**A caveat on the identical-full-ranking column, stated because it looks like a contradiction.**
At arena 512 that metric *falls* with k, reaching 0% at k = 16. This is an artefact of the metric,
not instability in the methodology: at 512 the roster contains a near-exact tie
(`hydra_alpha2` 66.1% vs `nemesis_alpha2` 65.6% — half a percentage point apart), and a strict
all-seven-positions-identical test fails whenever any sample swaps those two, which a larger, more
precise sample does more reliably rather than less. Over the same blocks the *top* agent is
identical 100% of the time from k = 4 upward and every pairwise verdict is stable from k = 8. Where
a whole-ranking metric and a pairwise metric disagree, the pairwise one is the sound one; the
whole-ranking metric is reported here rather than dropped because suppressing it would hide a real
property of this roster.

This is the answer to the question the task posed: additional placements stop materially changing
the strategic conclusion at **8**, at both arena scales.

### G.3 Orientation and placement coupling

Alpha2 placement is *seat-ordered*: `seeded_seat_starts` returns addresses for seat 0 and seat 1,
and swapping which agent occupies which seat leaves the geometry fixed. That makes **Option 3
(paired: swap entrants over the same geometric placement)** available, and it is the right choice.

Measured over 672 (pair, seed) cells per arena where both orientations exist:

| Quantity | @ 4096 | @ 512 |
|---|---|---|
| Cells whose outcome changes on orientation alone | 55 / 672 (**8.2%**) | 75 / 672 (**11.2%**) |
| Mean absolute seat delta | 0.072 | 0.065 |
| Per-pair score s.d., **paired** orientations over one geometry | **0.0579** | **0.0455** |
| Per-pair score s.d., **unpaired** (each orientation draws its own placement) | 0.0609 | 0.0491 |

Two conclusions. First, seat still matters in 8–11% of cells, and *more* at the recommended arena
than at 4096, so both orientations remain mandatory — dropping one would reintroduce exactly the
first-mover bias v0.9 Phase 6 was built to remove. Second, pairing over one geometry is measurably
(if modestly) tighter than drawing an independent placement per orientation, at both arenas, and it
costs nothing. Deriving a fresh placement per orientation would confound seat effect with placement
effect while claiming to average the seat effect away — the specific failure the task warned about.

---

## H. Proposed stable v4 evaluation methodology

Working identity: **`ruleset_v4_seeded_placements`**.

### H.1 Specification

1. **Placement sampling algorithm.** None is invented. Evaluation stops passing explicit starts
   and instead passes `agent_start=None, opponent_start=None`, letting
   `agent_test._test_agent` resolve them through
   `placement.resolve_direct_match_starts(ruleset_id=<v4 ruleset>, arena_size, entrant_count=2,
   supplied_starts=[None, None], seed=<cell seed>)` — bit-for-bit the same call `bytefray run`
   makes. Geometry is therefore a pure function of `(arena_size, entrant_count, cell seed)` and is
   automatically bound to the physical seat.

2. **Number of placement samples.** **8**, as a new `STANDARD_V4_SEEDS = (1, 2, 3, 4, 5, 6, 7, 8)`
   default used only when the resolved methodology is v4-seeded and no explicit `--seeds`/
   `--seed-range`/preset selection is given (mirroring how `STANDARD_V2_SEEDS` is used today).
   Evidence: §G.2. The specific eight values are one deterministic choice among many; the *size* is
   what the evidence supports, and extending the existing 1..5 convention to 1..8 keeps the two
   readable side by side.

3. **Arena size — pinned, not inherited.** The methodology must fix an explicit arena size and
   record it (it already flows into `effective_conditions` and therefore into `evaluation_id`).
   **Recommendation: 512**, the Agent Designer's own default and the middle of the 256/512/1024 band
   Phase 4 and Phase 5 actually qualified. Inheriting `Config.arena_size` (4096) would evaluate in a
   regime no v4 qualification has ever covered and would reorder the roster around a reach dominance
   the Designer's gameplay does not exhibit (§G.1b, §D.5). This is the largest single methodology
   lever measured in this study, and it is the one item in the specification a maintainer should
   ratify explicitly rather than accept from a research report.

4. **Orientation treatment.** Both orientations, over the **same** seeded geometry (§G.3). Because
   placement resolution is seat-ordered and evaluation no longer supplies starts, this falls out of
   the existing `physical_slots_for_orientation` swap with no extra machinery: slot A always gets
   `seeded_seat_starts(...)[0]`, and orientation decides who sits in slot A.

5. **Deterministic seed derivation.** **No new derivation is required, and none should be added.**
   The cell seed is already a canonical, persisted, explicit input; `seeded_seat_starts` hashes it
   with SHA-256 over an ASCII payload domain-separated by the Ruleset identity. That is already
   free of worker-count, execution-order, `PYTHONHASHSEED`, and global-RNG dependence, and is
   already cross-platform pinned by eleven release-blocking vectors in
   `engine/tests/test_v4_alpha2_placement.py`. Introducing a second placement-seed formula keyed on
   candidate identity would be actively harmful: the candidate is excluded from the comparison
   alignment key by construction, so a candidate-dependent geometry would silently break paired
   comparison between two candidate revisions.
   *Disclosed coupling:* the cell seed also derives per-entrant agent RNG, so placement and agent
   RNG co-vary across samples. This is the production coupling, and evaluation should keep it —
   decoupling them would measure placements that agents never meet in real play.

6. **Methodology identity.** New `arena_alignment_mode` value `"ruleset_v4_seeded_placements"`,
   plus new `SCHEMA_VERSION_V4` / `IDENTITY_VERSION_V4` = **7**. A new `arena_alignment_mode` value
   alone *is* sufficient for comparison safety (§H.2), but it is not sufficient for reader honesty:
   at schema 5, `subject_start` means "a placement evaluation chose"; under this methodology it
   means "a placement the Ruleset derived". Reusing version 5 would overload an existing field with
   new provenance — the exact practice the project forbade in Beta2 Phase 3 §34. Versions 5 and 6
   each precedent an additive bump for an additive methodology with no historical artifact to
   preserve; this is the third.

7. **Persisted metadata.** Top-level `arena_alignment_mode`, `rules_compatibility_id`,
   `orientation_mode`, `seeds` (which now doubles as the placement sample set), and
   `schema_version`/`identity_version` 7. Per cell: `placement_id = f"seeded-{seed}"` and the
   **resolved** `subject_start`/`opponent_start`. Explicit starts must be persisted (they already
   are) *and* be exactly reconstructible from `cell.seed` — a test should assert the two agree, so
   the artifact is verifiable rather than merely self-consistent. `evaluation_id`'s payload should
   carry the methodology's *sample set* (the seeds and the resolved layout per seed) in the same
   place v2 methodology puts `placements`, so two different sample sets can never collide.

8. **Comparison compatibility rules.** **`comparison.py` needs no change.** `_condition_key`
   already includes `arena_alignment_id`, `cell.seed`, and `cell.placement.value`, so:
   a v4-seeded cell can never align with a v2-standard-placement cell (different alignment id);
   two v4-seeded cells align only at equal seed *and* equal `placement_id`; and any field whose
   confidence is `UNKNOWN` returns `None` and refuses to align. Two evaluations run at different
   sample counts (say seeds 1–8 vs 1–16) align on their shared prefix and report the remainder as
   unmatched rather than pooling them — already the correct behaviour.

9. **CLI implications.** Add the stable v4 Ruleset to `--ruleset` choices and to
   `EvaluationService._validate`'s allowed set. Default the seed set to `STANDARD_V4_SEEDS` when
   the resolved methodology is v4-seeded. Fix §F.6 by having `agents evaluate` call
   `resolve_omitted_ruleset_for_agents` with the resolved entrant specs, exactly as `run`/`test`/
   `tournament` do.
   Note this is *not* a repointing of an established command's default at a newer generation: an
   Agent API **v1** roster keeps resolving to `bytefray-rules-2` unchanged, because that is the
   first candidate that supports it. The only behaviour that changes is the API-v2 case, which
   today produces an artifact where every cell failed. Automatic selection stays in the resolution
   layer, driven by metadata the author already declared.

10. **Agent Designer implications.** The Evaluation dialog currently offers alpha1 only among the
   v4 alphas; it must offer the stable v4 Ruleset, and must not keep alpha1 as the evaluation
   default while Simple/Advanced matches run alpha2 — a user would otherwise evaluate under
   semantics different from the ones they played under.

11. **Historical compatibility.** Untouched. v1 artifacts (`"fixed"`, schema 4) and v2/group
    artifacts (schema 5/6) keep their exact interpretation; none of their hash payloads acquires or
    loses a key. Existing `bytefray-rules-4-alpha1` evaluations remain valid, honest records of
    alpha1-under-fixed-placement and stay comparable only with each other.

12. **Expected runtime multiplier.** Today's default v4 evaluation is
    `N opponents × 5 seeds × 3 placements × 2 orientations = 30N` matches. The proposal is
    `N × 8 seeds × 1 placement × 2 orientations = 16N`. That is **0.53×** in match count — the new
    methodology is *cheaper* than the current one, because the placement axis folds into the seed
    axis instead of multiplying it rather than being added to it. Per-match cost also falls if the
    pinned arena is 512: median match length in this corpus is 18 ticks at 512 against 152 at 4096,
    so the combined effect is a substantial net speed-up, not a regression. Agent Designer
    usability is improved by this change, not traded against it.

### H.2 Alternatives considered and rejected

| Option | Verdict |
|---|---|
| **1 — one seeded placement per orientation cell** | **Rejected.** 8.3% verdict flip, 0.190 mean score spread, and a full-roster ranking reproduced only 27% of the time (§G.2). Cheap and unusable. |
| **2 — small deterministic placement set (4 / 8 / 16)** | **Adopted at 8.** 4 reproduces the ranking only 75% of the time; 16 costs double for no change in any conclusion. |
| **3 — paired placement sampling** | **Adopted, as the orientation treatment.** "Paired" is well defined here precisely because Alpha2 placement is seat-ordered: the same geometry, occupants swapped (§G.3). |
| **4 — a superior design** | None found that survives the "understandable, reproducible, serializable" bar. A candidate-identity-keyed placement seed was considered and rejected in §H.1(4) as breaking paired comparison. |

### H.3 Classification: pre-RC stabilization, or another alpha?

**Pre-RC stabilization.** The work is: a new `arena_alignment_mode` constant, a new schema/identity
version pair, a standard seed constant, one branch in `build_matrix` that omits explicit starts,
one CLI resolver swap, a Designer option-list change, and tests. Its compatibility surface is
purely additive — no historical artifact is reinterpreted, no hash payload changes for any existing
methodology, and the comparison gate needs no modification at all. That is the same shape as
Beta2 Phase 1 (schema 5) and Phase 2 (schema 6), each of which shipped inside a release rather than
requiring its own alpha.

This classification is **not** based on diff size. It rests on three specific compatibility facts:
(i) `_condition_key` already fails closed on an unknown `arena_alignment_id`, so old and new
artifacts cannot be silently mixed; (ii) no existing `evaluation_id`, `schedule_id`, or
`condition_fingerprint` payload gains or loses a key; and (iii) the placement function being
adopted is already release-qualified with cross-platform pinned vectors.

The one genuine caution: this is a **permanent** methodology identity. Once `schema_version` 7 and
`ruleset_v4_seeded_placements` are written to a user's disk they must be honoured forever. The
sample size is the part worth being sure about, which is why §G.2 measures the knee rather than
picking a round number.

---

## I. Compatibility implications

| Axis | Consequence |
|---|---|
| Ruleset (`bytefray-rules-4-alpha1` / `-alpha2`) | **None.** No policy, identity, placement, scheduler, disruption, quota or scoring semantic is proposed for change. |
| Agent API v2 | **None.** No new observation field, action kind, or declaration rule. |
| `battle2.replay` schema 4 | **None.** |
| `battle2.result` schema | **None.** |
| `bytefray.agent_trace` schema 2 | **None.** Used read-only, post hoc. |
| `bytefray.evaluation` schema | **Additive**: new version 7 alongside 4/5/6; new `arena_alignment_mode` value. |
| Evaluation history / adapters | `v2_adapter` needs to accept schema 7 and read `placement_id`/`subject_start`/`opponent_start` from it exactly as it does at 5. |
| Evaluation comparison | **No change required.** The existing gate already separates methodologies and fails closed. |
| Historical v1 / v2 / group artifacts | Interpreted exactly as before; no key added to or removed from any existing hash payload. |
| CLI | `agents evaluate --ruleset` gains the v4 identity; omitted-`--ruleset` resolution is corrected for API-v2 rosters (API-v1 behaviour unchanged). |
| Agent Designer | Evaluation dialog gains the stable v4 Ruleset. |

---

## J. RC impact

### Release-blocking

Only items that genuinely prevent a responsible stable 4.0 contract.

1. **Fix `agents evaluate`'s omitted-`--ruleset` resolution for Agent API v2 rosters** (§F.6).
   Today the default invocation on a v4 agent writes a `complete`, `finished` artifact with every
   cell failed. Shipping 4.0 with the default evaluation path broken for the release's own agent
   generation is not defensible. Add the regression test that does not currently exist.

   **Sequencing note.** `resolve_omitted_ruleset_for_agents`'s default candidate order is
   `(bytefray-rules-2, bytefray-rules-4-alpha2, bytefray-rules-1)`, so simply swapping the resolver
   in makes an API-v2 roster resolve to **alpha2**, which `EvaluationService._validate` currently
   rejects — the fix and the methodology adoption would then have to land together. Two routes:
   * **Stopgap, independently shippable:** call the same resolver with evaluation's *own* candidate
     tuple ending at `bytefray-rules-4-alpha1`. An API-v2 roster then resolves to alpha1, which
     evaluation already accepts and which demonstrably works today (§F.6). Ruleset-v1 rosters are
     untouched. This closes the broken-default defect on its own.
   * **Full fix:** land items 2–4 and resolve to the stable v4 identity.

   Either is acceptable for the RC; only the second is acceptable for 4.0 stable, because the
   stopgap still evaluates v4 agents under a Ruleset nobody plays.
2. **Implement the stable v4 evaluation methodology** (§H). The default stable v4 Ruleset must have
   a deterministic, reproducible, honest evaluation path before 4.0 is called stable — the task's
   own stronger standard for Question B, and the reason `agents evaluate` currently accepts no v4
   Ruleset that anyone actually plays under.
3. **Ratify the pinned evaluation arena size** (§H.1 item 3). This report recommends **512** on the
   evidence in §G.1b and §D.5, but it is a permanent methodology constant that changes the
   leaderboard, and it should be an explicit maintainer decision rather than a value inherited from
   a research report. Leaving it at 4096 is a defensible choice *if made deliberately*, with the
   understanding that it evaluates in a regime no v4 qualification has covered.
4. **Decide and freeze the stable v4 Ruleset identity.** Everything above needs a name that is not
   `-alpha2` to bind to.
5. **Record the three accepted reach properties in the shipped v4 gameplay contract** (§E.3). The
   freeze decision is "accept with documented limitation"; if the limitation is not actually
   documented, the decision has not been carried out.

### RC qualification

6. Cross-platform reproduction of the new methodology's placement/identity on Linux, matching the
   discipline Phase 5 applied to `test_v4_alpha2_placement.py`'s eleven vectors.
7. A test asserting that each cell's persisted `subject_start`/`opponent_start` equal
   `seeded_seat_starts(2, arena, cell.seed)` — the artifact must be verifiable, not merely
   self-consistent.
8. Comparison-gate tests proving a v4-seeded cell never aligns with a v2-standard-placement cell,
   and that two v4-seeded evaluations at different sample counts align on the shared prefix only.
9. Documentation: `COMPATIBILITY.md` gains a v4 evaluation-methodology section; `RULES.md`'s bump
   policy note; CHANGELOG.
10. Windows GUI/manual qualification of the Designer evaluation dialog change.
11. An evaluation regression fixture using an **Agent API v2** roster. Every existing
    `test_agent_evaluation*.py` fixture declares `api_version: 1`, which is precisely why the §F.6
    defect was never caught.

### Post-4.0

12. Reach economics and the ranked alternatives in §E.4 — a detection radius distinct from
    READ/WRITE reach, delayed initial visibility, or a reach cost. Evidence-supported as
    *directions*, deliberately not designed here, and not urgent.
13. Improving the bundled short-reach starters, which do not perform local search well enough to
    represent the Ruleset's actual capability (§C.2). This is an agent-quality issue, not a rules
    issue.
14. Whether the disconnect between the mobile contact layer and the static core layer (§D.7) should
    be narrowed — e.g. by letting a core follow its entrant, or by making anchors carry more
    information. This is a genuine design question and squarely post-4.0.

---

## K. Limitations

Recorded because they are real and should shape what happens next, not because they change the
dispositions above.

1. **The reach ladder carries no defence.** Every rung is a single-process pure attacker, chosen so
   the ladder isolates information acquisition and delivery — the variable reach actually controls
   — rather than mixing it with repair economics. The consequence is that the ladder's absolute win
   rates and its 52.6% draw rate are not competitive standings; only the *ordering* between rungs
   is. The defended, specialised and dispersed designs are measured separately (§D.7), and the
   §G corpus uses real shipped agents throughout.

2. **The 4096 regime test is one arena, 16 seeds, 320 matches, and one probe family.** The effect
   it reports is large (54.7% vs 16.4% between adjacent rungs) and it is independently corroborated
   at the same scale by real shipped agents in §G.1b (`hydra_alpha2` 88.8% at 4096 against 66.1% at
   512). But no intermediate arena between 1024 and 4096 was tested, so where the inverted U
   straightens is unknown. If the pinned evaluation arena decision (§H.1 item 3) is contested, that is
   the experiment to run.

3. **Placement and agent RNG cannot be separated in this design, by choice.** The cell seed derives
   both the layout and each entrant's RNG (`derive_agent_seed`), so a placement sample also varies
   agent randomness. This is the production coupling and the methodology deliberately preserves it
   (§H.1 item 5), but it means this study cannot report how much of the residual variance at k = 8 is
   placement luck versus RNG luck.

4. **`first_callback_discloses_enemy_core` is a strict test.** It requires *every* anchor visible on
   the first callback to be an enemy core cell, so it measures unambiguous disclosure. Against the
   two-entrant rosters used here the strict and partial rates were identical in every experiment,
   because a two-entrant opponent's co-located processes collapse to a single visible address; with
   three or more entrants the two would diverge and only the partial rate would be meaningful.
   **No multi-entrant match was run in this study at all** — every experiment is 1v1. Alpha2
   placement is defined for any seat count and Phase 5 verified it for 2/3/4/8 seats, but the reach
   findings here should not be assumed to carry to group play.

5. **Only Agent API v2 Python entrants, only `bytefray-rules-4-alpha2`.** Alpha1 was not re-run;
   its behaviour is taken from Phase 5's paired corpus, which this study did not attempt to
   reproduce.

6. **No Linux qualification and no Windows GUI/manual qualification was performed.** Everything in
   this report ran on Windows 11, Python 3.13.14, headless. The cross-platform determinism claims
   quoted in §C.1 are Phase 5's, re-verified here only to the extent that the eleven pinned
   placement vectors reproduce on this machine.

7. **The evaluation-methodology corpus uses seven agents and 21 pairs.** A larger or differently
   shaped roster could move the k = 8 knee. The knee was measured at two arena scales and agreed at
   both, which is the strongest available evidence at this scale, but it is not a proof that 8
   suffices for every future roster — which is why §H.1(2) specifies the sample size as a
   methodology constant that a later phase may revisit with evidence rather than as a law.

8. **`ladder_vs_ecology` corroborates rather than establishes, and was narrowed to one arena.**
   It exists to check that the ladder's ordering is a property of the game and not of the probes
   playing themselves; the same check is independently available from §G.1b's shipped-agent
   ranking, which is what the conclusions actually rest on. It ran at arena 512 only (720 matches)
   rather than the planned three arenas — see §D.3 for the reasoning and for what happened to the
   abandoned partial sweep. Its arena-256 and arena-1024 cross-checks were therefore not performed.

9. **No fix was implemented for the §F.6 defect.** This is a research phase; the defect is reported
   with a reproduction, and remediation is listed as release-blocking work (§J.1), not performed
   here.

---

## L. Reproduction

### L.1 What was added

All research-only, all new files, none reachable from any product path. `git diff --stat
v4.0.0-alpha4` is empty for every tracked file.

```text
da6a8a212564e8f18966cb94f0a15d93f0881227ffe1210dc8857fd64c4e8a49  tools/v4_pre_rc_reach_study.py
cfeec4a5ffbdf99795c761602852008b981f35d17dee729ccd694b6259ee6884  tools/v4_pre_rc_eval_methodology_study.py
0e2e11bc51eadb45d190a49cd41db23d48614d8115ff3f3e4d4305cd5c283324  tools/v4_pre_rc_generate_probes.py
fb03d0bfe9bebfc5bddf2c3a75ae838a0df463ea5ca264a28ee8162a91355763  tools/v4_pre_rc_agents/_seeker_template.py
tools/v4_pre_rc_agents/agents/  rp_oracle/ rp_pack/ rp_sentry/ rp_swarm/ rp_warden/
tools/v4_pre_rc_agents/agents/  rp_seek_r4/ rp_seek_r16/ rp_seek_r64/ rp_seek_rquarter/ rp_seek_rhalf/
docs/research/v4/V4_PRE_RC_GAMEPLAY_EVALUATION_RESEARCH.md   (this report)
```

The probe directory is `tools/v4_pre_rc_agents/`, deliberately **not** the product `agents/`
catalogue, following the precedent `tools/v4_alpha2_ecology_agents/local_hunter` set in Phase 5.
No probe is discoverable by `bytefray agents`, selectable in the Designer, or referenced by
any CLI, evaluation, or tournament path; the harnesses reach them by passing an explicit root to
`agents.resolve_agent`.

### L.2 Commands

```bash
# Reach ladder (960 matches) and the arena-4096 regime test (320)
python tools/v4_pre_rc_reach_study.py run --experiment ladder \
    --arena-sizes 256 512 1024 --seeds 0-15 --ticks 1000 --trace \
    --output <root>/raw_results
python tools/v4_pre_rc_reach_study.py run --experiment ladder \
    --arena-sizes 4096 --seeds 0-15 --ticks 1000 --trace \
    --output <root>/raw_results_arena4096

# Counterplay (4,320) and cross-check against the shipped roster (2,160)
python tools/v4_pre_rc_reach_study.py run --experiment archetype \
    --arena-sizes 256 512 1024 --seeds 0-15 --ticks 1000 --trace --output <root>/raw_results
python tools/v4_pre_rc_reach_study.py run --experiment ladder_vs_ecology \
    --arena-sizes 256 512 1024 --seeds 0-7 --ticks 1000 --trace --output <root>/raw_results

python tools/v4_pre_rc_reach_study.py summarize --input <root>/raw_results \
    --output <root>/summaries

# Evaluation methodology: today's placement, the candidate, and the candidate at arena 512
python tools/v4_pre_rc_eval_methodology_study.py run --condition fixed  --output <root>/raw_results
python tools/v4_pre_rc_eval_methodology_study.py run --condition seeded --seeds 0-31 \
    --output <root>/raw_results
python tools/v4_pre_rc_eval_methodology_study.py run --condition seeded --seeds 0-31 \
    --arena-size 512 --output <root>/raw_results_arena512
python tools/v4_pre_rc_eval_methodology_study.py analyze --input <root>/raw_results \
    --output <root>/summaries

# Proof that the ladder rungs differ only in declared reach
python tools/v4_pre_rc_generate_probes.py --check
```

`run` is resumable: an already-recorded `(pair, arena, seed, orientation)` tuple is skipped, so an
interrupted sweep continues rather than duplicating work.

### L.2b Corpus size

| Experiment | Matches |
|---|---:|
| Question A · reach ladder (arenas 256/512/1024) | 960 |
| Question A · reach ladder (arena 4096 regime test) | 320 |
| Question A · archetype counterplay | 4,320 |
| Question A · ladder vs shipped roster (arena 512) | 720 |
| Question B · fixed placement (arena 4096) | 630 |
| Question B · seeded placement (arena 4096) | 1,344 |
| Question B · seeded placement (arena 512) | 1,344 |
| **Total contributing to the findings** | **9,638** |

A further 433 matches from the abandoned 3-arena `ladder_vs_ecology` sweep (§D.3) are preserved
unanalysed and contribute to nothing in this report. 7,760 of the 9,638 were run with `--trace`.

Every corpus was checked for integrity before analysis: 0 malformed records and 0 duplicate
`(pair, arena, seed, orientation)` keys across all files.

### L.3 Data locations

Research corpora live outside the product tree, following the Phase 4/Phase 5 convention:

```text
D:\Projects\Bytefray-research\v4-pre-rc-20260902\
    raw_results\              ladder.jsonl, archetype.jsonl, ladder_vs_ecology.jsonl,
                              eval_fixed.jsonl, eval_seeded.jsonl
    raw_results_arena4096\    ladder.jsonl
    raw_results_arena512\     eval_seeded.jsonl
    summaries\                ladder_summary.json, archetype_summary.json,
                              ladder_vs_ecology_summary.json, eval_methodology_summary.json
    summaries_arena4096\      ladder_summary.json
    summaries_arena512\       eval_methodology_summary.json
    logs\
```

One JSON record per match, carrying `experiment`, both agent ids, `arena_size`, `seed`,
`orientation`, the resolved `starts` and `core_bases`, outcome, termination reason, per-entrant
process declarations, replay-derived spatial metrics, and (where `--trace` was given)
trace-derived information metrics. Every `MatchRequest` is reconstructible from those fields
through the harness's own `build_request`.

Replays and traces are analysed and deleted per match rather than retained: at 1000 ticks and
eight actions per tick a single traced match writes on the order of 16,000 decision records, and
the study ran 7,760 traced matches.

### L.4 Probe legality and product isolation, verified

Both properties were checked behaviourally rather than asserted.

**Every probe is an ordinary Agent API v2 entrant.** Loading all ten through the product's own
`agent_api.load_python_agent` and calling `declare_processes()` at arena 512:

| Probe | API | Declarations `(id, reach, share)` |
|---|---:|---|
| `rp_oracle` | 2 | `(executioner, 256, 0.875)`, `(keeper, 8, 0.125)` |
| `rp_pack` | 2 | `(scout, 32, 0.25)`, `(striker, 16, 0.75)` |
| `rp_seek_r4` / `r16` / `r64` / `rquarter` / `rhalf` | 2 | `(seeker, 4 / 16 / 64 / 128 / 256, 1.0)` |
| `rp_sentry` | 2 | `(siege, 256, 0.75)`, `(warden, 8, 0.25)` |
| `rp_swarm` | 2 | `(alpha, 24, 0.375)`, `(beta, 24, 0.375)`, `(gamma, 24, 0.25)` |
| `rp_warden` | 2 | `(guard, 8, 0.5)`, `(stinger, 24, 0.5)` |

All declare integer reach inside `[1, arena_size − 1]`, unique process ids, and shares summing to
exactly 1.0 — the same constraints `ProcessMatchController` enforces for any user agent. None uses
an engine internal, a research seam, match metadata, or replay access.

**No probe is reachable from a product path.** `bytefray agents` (the product's own discovery
listing) returns 0 entries matching `rp_`; the probes live under `tools/v4_pre_rc_agents/` and are
reached only by passing that root explicitly to `agents.resolve_agent`, exactly as Phase 5's
`local_hunter` is.

### L.5 Environment and integrity

| | |
|---|---|
| OS | Windows 11 Pro 10.0.26120 |
| Python | 3.13.14 (`.venv/`) |
| Branch | `v4-pre-rc-research` |
| Base commit | `010c3f6b1cbfc7d63988f8ccfc2626aae7dcef99` (`v4.0.0-alpha4`) |

### L.6 Validation and integrity

All checks ran on Windows 11, Python 3.13.14, against the frozen research commit `7d74771`, with
the working tree clean. The research commit was made **before** the long suite run so that Git
durability exists independently of it.

| Check | Command | Result |
|---|---|---|
| Ruff | `ruff check .` | **All checks passed** |
| Engine mypy | `mypy engine/src/battle_engine` | **Success, 101 source files** |
| Client mypy | `mypy client/src/battle_client` | **Success, 15 source files** |
| Whitespace | `git diff --check` | clean |
| Full repository suite | `pytest --basetemp=.pytest-tmp/v4prerc-full3` | **2847 passed, 14 skipped, 2 deselected** in 280.01s |
| Designer GUI suite | `pytest -m gui tests/` | **250 passed, 6 deselected** in 33.63s |
| Ladder-rung identity | `tools/v4_pre_rc_generate_probes.py --check` | all 10 stamped files OK |
| Probe legality | product `load_python_agent` + `declare_processes()` | 10/10 legal (§L.5) |
| Product isolation | `bytefray agents` | 0 probes discoverable |

**Test-count reconciliation.** Phase 5 recorded 2623 passed / 14 skipped / 2 deselected; this run
records **2847** passed with the same 14 skips and 2 deselections. The +224 are the Alpha3 and
Alpha4 spectator-pipeline tests added between `v4.0.0-alpha2` and `v4.0.0-alpha4` (perspective
cam, spectator director, Fight Night, trace integration), not anything this phase added — **this
phase added no tests at all**, because it changed no product code. The GUI suite likewise moved
242 → 250 across the same two alphas. `mypy`'s file counts moved 95 → 101 (engine) and 12 → 15
(client) for the same reason.

**Working-tree integrity across the suite.** `HEAD`, `git status --short`, and SHA-256 digests of
eleven critical files (six production modules the study depends on, plus every research file) were
recorded immediately before the full suite and recomputed immediately after. `HEAD` was
`7d7477131317c2165093baddca389f90daca97bb` both times, the tree was clean both times, and **all
eleven digests matched exactly** — so the code that passed is the code preserved in Git.

**Not performed, and not claimed:** no Linux qualification, and no Windows manual/GUI qualification
beyond the headless `-m gui` suite (§K.6).
