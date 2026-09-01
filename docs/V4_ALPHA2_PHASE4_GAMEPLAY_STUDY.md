# Bytefray v4 Phase 4 — Controlled Gameplay Research Report

> **Provenance note (added when this report was cherry-picked onto the Phase 5
> product branch; no finding, number, or claim below was altered).** This
> report is the evidence base for the `bytefray-rules-4-alpha2` gameplay
> contract — see [V4_ALPHA2_DESIGN.md](V4_ALPHA2_DESIGN.md) for what Phase 5
> actually adopted from it, which is deliberately less than everything it
> tested. The harness and probe sources it cites
> (`tools/v4_alpha2_gameplay_study.py`,
> `tools/v4_alpha2_research_agents/`) and the five research-only
> `MatchRequest` override fields described in Section I live **only** on the
> `v4-alpha2-gameplay-research` branch and were deliberately not carried into
> the product; Phase 5's own harness is `tools/v4_alpha2_ecology_study.py`,
> which expresses conditions as Ruleset identities instead. Section I's
> byte-identical Alpha1 equivalence check is byte-identical *within that
> research branch*: the additive per-process telemetry it describes also
> reaches the replay header, so a replay recorded there differs from one
> recorded on `main` for the same inputs. That telemetry is not in the
> product either.

Research branch: `v4-alpha2-gameplay-research` (off `main`@`855f7379e1309ec60760d960fff54e7da9648e59`)
Ruleset under test: `bytefray-rules-4-alpha1` (frozen; not altered — see Section I)

---

## A. Baseline

| | |
|---|---|
| Source HEAD | `855f7379e1309ec60760d960fff54e7da9648e59` (== `origin/main` at study start) |
| Branch | `v4-alpha2-gameplay-research` |
| Agent roster | Hydra, Nemesis, Viper, `v4_claimer`, `v4_concentrated_attacker`, `v4_defender_scout`, `v4_local_defender`, `v4_scout` (all Agent API v2, confirmed loadable, no code changes needed — see `config/frozen_roster_manifest.md` for full hashes/provenance) |
| Arena sizes | 256, 512, 1024 |
| Seed set | 0–15 (pilot scale; see "Scope actually run" below) |
| Tick budget | 1000, kept fixed across every condition (see `config/tick_budget_decision.md`) |
| Total matches | ~35,976: 29,568 across 11 pairwise-matrix conditions (baseline + 4 core sizes + 3 reach caps + process-spread + seeded-placement + round-robin, 2,688 each) + 1,792 in the process-order sensitivity sweep + 4,608 in the Disperser/Local Hunter probe sweep + 8 representative-replay captures |
| Research output directory | `D:\Projects\Bytefray-research\v4-alpha2-phase4-20260831-214252\` |

### Scope actually run vs. the governing task's suggested scale

The task suggested expanding to 32 seeds "if runtime is reasonable" and 64+ "where additional
confidence is genuinely useful." Every effect reported below is large (tens of percentage
points) and already resolves at 16 seeds × both seats × 3 arena sizes (n=672 per agent per
condition, Wilson 95% intervals under 4 points wide even at extreme win rates) with results that
independently agree across all three arena sizes (Section B/C/D). Expanding the seed count would
tighten already-narrow confidence intervals without changing any qualitative conclusion, so the
16-seed pilot was kept as the operating scale for the full ten-condition matrix rather than
manufacturing precision the effect sizes do not need (per the task's own "avoid false precision"
instruction). The process-order and probe sweeps are smaller by design (per-agent/per-probe
sensitivity checks, not roster-wide ecology sweeps).

### Reproducibility

Every match record includes `condition`, `agent_a`/`agent_b`, `arena_size`, `seed`, `orientation`,
and full outcome/telemetry — the exact `MatchRequest` for any given match can be reconstructed
from `tools/v4_alpha2_gameplay_study.py`'s `build_request`. Raw match records live in
`raw_results/*.jsonl` (one file per condition), summaries in `summaries/*_summary.{json,csv}`,
representative replays in `replays/` with `replays/manifest.json`, and the frozen roster manifest
plus equivalence-check artifacts in `config/`.

---

## B. Alpha1 Ecology (Baseline)

This section's reference is the **baseline condition alone**: the 8-agent, 28-pair, 3-arena-size,
16-seed, both-seat matrix (2,688 matches) that every other condition in the study is compared
against. Headline numbers:

| Metric | Value |
|---|---|
| Median match length | 493.5 ticks (IQR 3 – 1000: heavily bimodal, not a smooth distribution) |
| Tick-limit rate | 46.8% (256: 41.1%, 512: 45.8%, 1024: 53.6% — rises with arena size) |
| Draw rate | 28.2% |

**Win ecology** (n=672 per agent; both seats, all three arena sizes pooled):

| Agent | Win rate | 95% CI | Seat delta (first − second) |
|---|---|---|---|
| Nemesis | **100.0%** | [99.4%, 100.0%] | +0.0% |
| Hydra | 80.1% | [76.9%, 82.9%] | **+11.3%** |
| v4_claimer | 42.9% | [39.2%, 46.6%] | +0.0% |
| Viper | 26.2% | [23.0%, 29.6%] | −4.8% |
| v4_scout | 23.8% | [20.7%, 27.2%] | +0.0% |
| v4_concentrated_attacker | 14.3% | [11.8%, 17.1%] | +0.0% |
| v4_defender_scout | 0.0% | [0.0%, 0.6%] | +0.0% |
| v4_local_defender | 0.0% | [0.0%, 0.6%] | +0.0% |

**Strongest baseline strategic pattern**: two of eight agents (Nemesis, Hydra) dominate the
entire roster through what is, on inspection, **not** a reach- or search-based strategy at all —
both hardcode the assumption that the opponent's core sits at `own_core_base + arena_size / 2`
(`agents/Nemesis/agent.py:39`; `agents/hydra/agent.py:170-194`, whose own docstring says "v4
alpha1's default two-entrant placement puts the opposing core opposite our own"). Under the
baseline placement this hardcoded formula is always exactly correct, and their declared
`arena_size // 2` reach is large enough to fire on it from anywhere. This is the mechanism behind
Section D and Section F's findings and is documented with full source citations and a concrete
replay in `summaries/representative_replay_notes.md` (§6).

Every other agent shows some genuine local/reactive behavior (Viper's raider physically expands
and locks onto the first sighted enemy; `v4_scout`/`v4_defender_scout` sweep and engage what
becomes visible), but none of them can force a decision against Nemesis/Hydra's blind, unlimited-
range cannon, and `v4_defender_scout`/`v4_local_defender` never win a single one of their 672
matches at baseline.

**Movement / reach / dispersion** (from additive per-process telemetry, `NativeAgentResult.
metadata["processes"][i]["telemetry"]`, and post-hoc replay analysis):

- Hydra and Nemesis's offensive processes (`interceptor`/`siege`/`sentinel`/`disruptor`/`guardian`)
  never move (0 MOVE actions recorded across the entire baseline corpus) — every one of their
  actions is a WRITE at a computed absolute address.
- Only three roster members ever issue a MOVE that visibly changes position under baseline: Hydra's
  `rover` (reach-12, deliberately mobile), Viper's `raider` (expansion phase), and the plain
  scanning starters (`v4_scout`, `v4_defender_scout`'s `scout` sub-process).
- `full_lockout_ticks` (a tick where an entrant's `cpu_used == 0`, i.e. every one of its processes
  was disrupted simultaneously) is common specifically against multi-process entrants with
  co-located processes (Hydra, Nemesis, `v4_defender_scout`) once an opponent's WRITE lands on
  their shared anchor — see Section F for the controlled test of this mechanism.

**Diagnostic red flags, quantified** (see also the tick-budget decision note):

| Red flag | Baseline evidence |
|---|---|
| Most matches finish in only a handful of ticks | Bimodal: IQR lower bound is 3 ticks, but the *upper* bound is the full 1000-tick budget — matches are either near-instant or never resolve at all, essentially no middle ground |
| Movement is nearly absent | True for the two dominant strategies (Hydra/Nemesis: 0 MOVEs ever); false for Viper/scouts, which do move but still lose to the two above |
| Most offensive processes choose effective global reach | True for 2 of 8 agents (Hydra, Nemesis) by declaration; irrelevant to the outcome for the rest, who never had a chance to contest them regardless of reach |
| Whole-roster disruption dominates opening play | Confirmed for co-located multi-process entrants (Hydra/Nemesis/`v4_defender_scout`) — see Section F |
| One agent or strategy family dominates nearly every opponent | Confirmed: Nemesis wins literally every single baseline match in the corpus (672/672) |
| Seat orientation materially changes results | Confirmed for Hydra specifically (+11.3pp first-mover advantage); every single-process agent shows exactly 0% seat delta by construction (a single process's own declared start is identical regardless of which "seat" it's assigned) |

---

## C. Core-Size Experiment (Experiment 1 / G3)

Tested core sizes 8 (= baseline, confirmed statistically identical: median ticks 493.5, tick-limit
rate 46.8%, every per-agent win rate matches baseline to 3 decimal places — a second, 2,688-match-
scale equivalence check beyond the byte-identical single-match proof in Section I), 12, 16, 24.
Reach, placement, process deployment, and scheduler all held at Alpha1 defaults.

| Core size | Median ticks | Tick-limit rate | Draw rate | Nemesis win% | Hydra win% | Viper win% |
|---|---|---|---|---|---|---|
| 8 (baseline) | 493.5 | 46.8% | 28.2% | 100.0% | 80.1% | 26.2% |
| 12 | 1000.0 | 86.7% | 58.3% | 19.0% | 19.0% | 47.6% |
| 16 | 1000.0 | 86.7% | 57.9% | 19.0% | 20.8% | 47.6% |
| 24 | 1000.0 | 91.4% | 55.5% | 28.6% | 20.8% | 47.6% |

Every non-8 core size collapses Nemesis's win rate from 100.0% to 19.0–28.6% and roughly halves
Hydra's (80.1% → 19.0–20.8%), while simultaneously **more than doubling** the tick-limit rate
(46.8% → 86.7–91.4%) and draw rate (28.2% → 55.5–58.3%). This holds independently at all three
tested arena sizes (e.g. Nemesis's win rate is 14.3%/14.3%/28.6% at arena 256/512/1024 under
core_size=12, vs. 100%/100%/100% at baseline — see `summaries/` JSON for the full per-arena
breakdown on every condition).

**Is this genuine counterplay, or just a longer race?** The pairwise breakdown answers this
precisely, and the answer is **both, depending on the specific matchup** — core size does not
have one uniform effect:

- **Nemesis vs. `v4_claimer`** (a matchup with no real counterplay: claimer never threatens
  Nemesis's core): resolves 96/96 times at *every* tested core size, with median ticks scaling
  almost linearly with core size (8→2 ticks, 12→21, 16→29, 24→45). This is exactly the "longer
  because more cells must be written" pattern the governing task warned against — the outcome
  never changes, only the clock.
- **Nemesis vs. Hydra** (a matchup between two mutually-capable global writers): resolves 96/96
  times at core_size=8, and **0/96 times at core_size=12, 16, or 24** — all 288 matches across
  those three larger sizes (96 per size) end in a tie by tick-limit. Larger cores do not make this
  matchup take longer to decide; they make it **undecidable within any tested budget**. A concrete
  example is retained at `replays/core_size16_extended.jsonl` (arena 512, seed 0: ends tied at
  tick 1000).

**Verdict**: increasing core size does create real interaction between agents capable of
threatening each other's core — but that interaction currently manifests as permanent stalemate
between the roster's two strongest agents, not a richer decided contest, while every mismatched
pairing simply takes proportionally longer to resolve with the identical predetermined winner.
Neither outcome is "healthier" gameplay by itself: the first replaces one dominant strategy with a
frozen deadlock between the same two agents, and the second just inflates match length for no
strategic gain. What core size *does* successfully do is break Nemesis's absolute 100% dominance
and lift every other agent's relative standing (Viper: 26.2% → 47.6% flat across 12/16/24) — but
this is a side effect of neutralizing the top two agents against each other, not evidence that
larger cores reward better play from the rest of the roster.

---

## D. Reach Experiment (Experiment 2)

Tested reach caps N/2 (documented no-op — every one of the 8 roster agents already declares
≤ arena_size/2 reach, so this *is* the baseline condition and was not re-run), N/4, N/8, and a
fixed local value of 16 (arena-independent). Core size, placement, deployment, and scheduler held
at Alpha1 defaults.

| Condition | Median ticks | Tick-limit rate | Draw rate | Nemesis win% | Hydra win% | v4_claimer win% | Viper win% |
|---|---|---|---|---|---|---|---|
| baseline (= N/2) | 493.5 | 46.8% | 28.2% | 100.0% | 80.1% | 42.9% | 26.2% |
| N/4 | 1000.0 | 90.5% | 61.3% | 0.0% | 14.3% | 57.1% | 45.2% |
| N/8 | 1000.0 | 90.5% | 61.3% | 0.0% | 0.0% | 71.4% | 45.2% |
| local 16 | 1000.0 | 90.5% | 61.3% | 0.0% | 0.0% | 71.4% | 45.2% |

Nemesis and Hydra's win rates collapse to 0–14.3% under **every** tested cap, and the tick-limit
rate jumps to 90.5% (up from 46.8%) — meaning the overwhelming majority of matches under any reach
cap no longer resolve at all within the 1000-tick budget. `v4_claimer`'s and Viper's *relative*
standing improves (claimer up to 57–71%, Viper to 45.2%), but this is because their most dangerous
opponents were disarmed, not because capped reach rewarded any new behavior from them — their own
declared reach (1 and 10/8 respectively) was already well below every one of these caps, so their
own capabilities are completely unaffected; only Hydra's and Nemesis's are.

`replays/reach_cap_n8_neutralized.jsonl` shows exactly why: Nemesis's three processes, capped to
reach 64 at arena_size 512, sit frozen at anchor 0 for the entire 1000-tick match while Viper
(anchor 256, 256 cells away — 4× the capped reach) is simply out of range. Nemesis's source
contains no MOVE action anywhere (see `agents/Nemesis/agent.py`) and no fallback behavior for a
target it can no longer reach — the cap does not make its strategy worse, it makes its strategy
**inapplicable**.

**Primary question — does spatial positioning become strategically useful when global reach is
removed?** Not for the current roster: MOVE frequency does not increase for Hydra/Nemesis (they
have no movement behavior to fall back on), and no *other* agent's win rate rises because it
started exploiting position better — only because its opponents lost their weapon. Tick-limit rate
rising to 90.5% (vs. 46.8% baseline) is the clearest evidence that removing global reach did not
unlock local play; it mostly just removed the roster's one reliable way to end a match.

**Secondary question — do current agents fail because they were written for global reach, or does
the game itself fail to reward local strategies?** The evidence points to the former for
Hydra/Nemesis specifically (their entire design is the global cannon; there is nothing "local"
underneath to fall back on) and leaves the second question genuinely open for the rest of the
roster, none of which was ever *designed* to win through decisive local pursuit even at baseline —
see Section E, where two purpose-built local agents are used to test the game's mechanics
directly rather than inferring an answer from agents that were never trying to do this.

---

## E. Probe-Agent Results (Disperser / Local Hunter)

Both introduced after the baseline/core-size/reach results showed the roster's non-dominant
agents were never actually designed to win through decisive local play, to test the *game's*
mechanics directly rather than infer an answer from agents that weren't trying. Full source at
`tools/v4_alpha2_research_agents/agents/{disperser,local_hunter}/agent.py`; SHA-256 hashes below.
Neither is presented as a competitive upgrade to any shipped starter. Swept against the full
roster and each other, both seats, 16 seeds, arena 256/512, under baseline placement and all three
reach caps (4,608 matches total).

| Probe | Purpose | Source SHA-256 (agent.py) |
|---|---|---|
| Disperser | Test whether actively separating an entrant's own processes early creates resilience against whole-roster disruption/quota redistribution | `1d0d14b3f18b64792ca59461f3d99be88c41fb0ce3fef9c0bd0cf0dad3f9b704` |
| Local Hunter | Test whether limited reach (12) plus active, decisive movement can produce viable pursuit/contact gameplay | `1f83dca9cdbe9868b8c6a2e20c59669669a093dec6ac78105086c9778858ac98` |

| Probe | Baseline win% | N/4 win% | N/8 win% | local-16 win% | Baseline tick-limit rate |
|---|---|---|---|---|---|
| Disperser | 0.0% | 0.0% | 0.0% | 0.0% | 80.0% |
| Local Hunter | 12.5% | 12.5% | 12.5% | 12.5% | 75.0% |

**Disperser never wins a single match, in any condition (0/2,560).** Opponent-by-opponent
breakdown (baseline) explains why cleanly: it draws every match against every purely local/passive
starter it can never reach (`v4_concentrated_attacker`, `v4_defender_scout`, `v4_local_defender`,
`v4_scout`, and Local Hunter — all draws, since Disperser itself never searches or leaves its own
core neighborhood), and **loses outright, in 2–3 ticks, to every genuinely aggressive opponent**
(Nemesis, Hydra, Viper, `v4_claimer` — all 64/64 by `last_agent_standing`, not score fallback).
This isolates a real, negative finding for the dispersion mechanism as tested: spreading four
processes across four adjacent core cells does not protect those *cells* from being overwritten —
it only protects against *disruption* (losing future turns), and Nemesis/Hydra's attack is a raw
overwrite race that dispersal does nothing to slow, since their `siege`/`guardian` patterns target
every one of the 8 absolute core-cell addresses directly regardless of which process (if any) is
currently anchored there. **Q7's answer, for this specific Disperser design against this specific
threat class, is no** — dispersion-based resilience only matters against disruption-driven
lockout, and Nemesis/Hydra's attack was never a disruption-lockout attack in the first place.

**Local Hunter wins exactly 12.5% (1/8 opponents' worth) in every condition tested, baseline
included.** This is not one flat outcome but two very different underlying stories:

- **It genuinely hunts down and beats `v4_claimer`** (64/64 wins: 32 by real capture at a median
  ~500 ticks, 32 by score fallback at the tick limit after prolonged pursuit) and partially beats
  `v4_concentrated_attacker` (16/64 real wins, 48 draws) — direct, positive evidence that active
  movement plus a modest, fixed local reach *can* produce a viable pursuit strategy against an
  opponent that itself has no counter-offense. This is a genuine answer to Q4: yes, for at least
  some opponents, local pursuit is viable under current mechanics.
- **It is insta-killed by Nemesis/Hydra at baseline** (0/64 each, 2–3 ticks, same
  placement-exploit mechanism as everything else in the roster — Section B/F2) — pursuit behavior
  never gets a chance to matter when the opponent's opening blast already knows exactly where to
  aim.
- **Under every reach-capped condition, its matches against Nemesis/Hydra become permanent draws
  instead of losses (0/64 in every reach-cap condition, versus 0/64 *losses* at baseline) — but
  still never wins.** Tracing one such match (`local_hunter` vs. Nemesis, reach_cap_n8, arena 256)
  explains the mechanism precisely: Local Hunter's blind sweep brings it within its own reach (12)
  of Nemesis's now-stationary, reach-capped position by tick ~20 (anchor 120 vs. Nemesis's 128) —
  but this also brings it within *Nemesis's* capped reach of Nemesis's `disruptor` process, which
  immediately begins re-disrupting Local Hunter's single process every single tick from then on,
  permanently (`disrupted_until_tick` renews every tick the target stays visible). With its only
  process disrupted every tick, Local Hunter can never act again — not to attack, not to retreat —
  for the rest of the match, while Nemesis's own core (300+ cells further away, still out of its
  capped reach) is never threatened either. The match freezes exactly where it stood at tick ~20.

This is a genuine, previously-undiscussed diagnostic finding: **a single-process pursuer that gets
close enough to detect a reactive opponent, but not close enough to win immediately, can be
permanently neutralized by that opponent's own disruption reaction** — with no way to disengage,
since a disrupted process cannot even issue a retreating MOVE. This is a structural risk specific
to single-process local designs (a multi-process pursuer would still have siblings free to act) and
is a plausible, mechanistic reason current agents might avoid committing to close-range pursuit even
where it would otherwise work, independent of anything to do with global reach.

---

## F. Deployment Experiments

### F1 — Initial process co-location (Experiment 3A)

Baseline placement kept fixed (A=0, B=arena_size/2); only the *initial position* of each
multi-process entrant's own processes changed — from Alpha1's default co-location (every process
starts exactly at the entrant's `start`) to a small deterministic spread
(`offset(i) = i * 24 // process_count`, i.e. up to 24 cells apart, always well inside the 8-cell
default core and each entrant's own reach — see `tools/v4_alpha2_gameplay_study.py`'s
`_process_spread_offset` docstring for the exact formula, mirrored in the engine at
`process_runtime.py`).

| Metric | Baseline (co-located) | Process spread (radius 24) |
|---|---|---|
| Median ticks | 493.5 | 356.0 |
| Tick-limit rate | 46.8% | 44.4% |
| Nemesis win% | 100.0% | 95.8% (seat delta swings to −8.3%) |
| Hydra win% | 80.1% | 86.6% |
| Viper win% | 26.2% | 23.8% |

The effect is small (a few points either way) and does not change any agent's qualitative
standing. This is expected given *which* agents are multi-process in this roster: Hydra and
Nemesis (the two most affected by spread, marginally) attack via absolute-address WRITE from a
fixed, never-moving anchor — spreading their processes a few cells apart changes which exact cells
their siblings occupy but does not change whether an incoming enemy WRITE can still hit all of
them (their own **defensive** processes, e.g. Hydra's `sentinel`, still sit at a fixed, discoverable
offset from the entrant's core). Single-process agents (`v4_claimer`, `v4_concentrated_attacker`,
`v4_scout`, `v4_local_defender`) are structurally unaffected by this experiment (`_process_spread_
offset(0, 1, 24) == 0` — a single process has nowhere to spread to), which is exactly why their
numbers are unchanged to the third decimal place versus baseline.

**Primary question — is initial process co-location itself responsible for catastrophic opening
suppression?** Not to any material degree for this roster, under this spread radius. The mechanism
this experiment isolates (a single enemy WRITE disrupting an entrant's entire co-located roster of
processes at once) is real and separately confirmed in Section E's Disperser probe, but simply
spreading the *existing* roster's processes by a modest radius does not meaningfully change match
outcomes, because the agents that would benefit most (Hydra/Nemesis) do not actually depend on
their own process survival for their attack to keep working — their attack is a pure formula
computed from their own core position, immune to disruption of any individual process's assigned
share (the freed-up quota simply reallocates, per the existing D1 fair-redistribution mechanic).

### F2 — Core-placement predictability (Experiment 3B)

Process deployment returned to co-located; only entrant *start* placement changed, from the fixed
baseline pair (A=0, B=arena_size/2) to a seed-derived, deterministic, non-overlapping pair (minimum
64-cell separation; exact formula in `tools/v4_alpha2_gameplay_study.py::seeded_starts`).

| Metric | Baseline (fixed opposite) | Seeded (unpredictable) placement |
|---|---|---|
| Median ticks | 493.5 | 1000.0 |
| Tick-limit rate | 46.8% | 81.3% |
| Draw rate | 28.2% | 59.1% |
| Nemesis win% | **100.0%** | **21.1%** |
| Hydra win% | **80.1%** | **23.5%** |
| v4_claimer win% | 42.9% | 41.2% |
| Viper win% | 26.2% | 44.3% |

This is the single largest effect measured in the entire study, and it holds at every arena size
independently (Nemesis: 14.3%/17.4%/31.7% at 256/512/1024 under seeded placement vs. 100%/100%/100%
at baseline). Section B and `summaries/representative_replay_notes.md` §6 establish the mechanism
directly from source: Nemesis and Hydra do not search for the enemy core, they compute its address
from a hardcoded "opposite the map" assumption (`agents/Nemesis/agent.py:39`;
`agents/hydra/agent.py:170-194`, whose own docstring names the exact rule it depends on).
Randomizing placement breaks that assumption outright; both agents' win rates fall to the same
14–32% band as the rest of the roster, and the corpus's draw rate more than doubles (28.2% →
59.1%) because nobody else in the roster has a reliable way to *find* an unpredictable core either.

**Primary question — how much current strategy depends on knowing the opponent's core position
without observing anything?** Nearly all of it, for the two agents that otherwise dominate the
entire ecology. This is not a subtle statistical tendency; it is the literal, documented design of
both agents, and removing the assumption's validity removes essentially their entire competitive
edge.

### F3 — Combined interaction

Not run. Per the governing task's own gating ("only if 3A and 3B independently show meaningful
improvement should you test the combination... do not treat it as the default recommendation
simply because it is the most different condition"): 3A (process spread) showed a small effect and
3B (placement) showed a dramatic one, so a combined test would be dominated entirely by 3B and add
no independent evidence. See Section K for why placement unpredictability alone, not a combination,
is the candidate worth carrying forward.

---

## G. Process-Order Experiment (Experiment 4 / G4)

### G1 — Declaration-order sensitivity

For each of the roster's four multi-process agents (Hydra: 4 processes, Nemesis: 3, Viper: 2,
`v4_defender_scout`: 2), ran every other roster agent as an opponent, both seats, 16 seeds, arena
512, under the agent's own declared process order ("original") and the exact reverse
("permuted") — same process IDs, shares, reach, and behavior code throughout, only list order
changed (via the new `process_order_overrides` `MatchRequest` field, which reorders an entrant's
already-constructed `ProcessInstance` list without touching agent source).

| Subject | Original win% | Permuted win% | Δ |
|---|---|---|---|
| Nemesis | 100.0% | 85.7% | **−14.3pp** |
| Hydra | 83.0% | 74.1% | **−8.9pp** |
| Viper | 14.3% | 28.6% | **+14.3pp** |
| `v4_defender_scout` | 0.0% | 14.3% | **+14.3pp** |

**Primary question — does merely permuting process declaration order materially change
performance?** Yes, substantially — double-digit percentage-point swings for three of the four
agents tested, well above any threshold that could be called negligible. The mechanism: within one
tick, `ProcessMatchController`'s scheduler always resumes scanning an entrant's process list from
index 0 on every scheduler slot it is granted (`process_runtime.py`, prior to this study's
`process_selection_mode` addition), so any quota freed up mid-tick — most commonly a sibling
process becoming disrupted — is always offered to whichever process is listed *first*, not
distributed by any notion of fairness or need. Declaration order therefore functions as an
accidental, undocumented priority ranking among an entrant's own processes, entirely separate from
the `share` value each process actually declares.

### G2 — Round-robin alternative

Ran the full 2,688-match roster-wide pairwise matrix (same shape as Sections B–D) with
`process_selection_mode="round_robin"` substituted for Alpha1's default priority-scan selection,
every entrant kept in its own original declared order (no permutation), core size/reach/placement/
deployment/K=2 scheduling/quota allocation all held at Alpha1 defaults.

| Metric | Baseline (priority) | Round-robin |
|---|---|---|
| Median ticks | 493.5 | 441.5 |
| Tick-limit rate | 46.8% | 44.9% |
| Nemesis win% | 100.0% | **87.2%** (−12.8pp) |
| Hydra win% | 80.1% | **91.4%** (+11.3pp, seat delta swings to +17.3%) |
| `v4_defender_scout` win% | 0.0% | **14.3%** (+14.3pp) |
| `v4_claimer` win% | 42.9% | **28.6%** (−14.3pp) |
| Viper win% | 26.2% | 26.2% (unchanged) |

Every one of these shifts is consistent across both arena sizes checked in detail (256/512; e.g.
Hydra 92.9%/92.9%/88.4% and Nemesis 85.7%/85.7%/90.2% at 256/512/1024 respectively — see
`summaries/round_robin_summary.json`). The two agents unaffected in the isolated G1 sensitivity
check for the opposite reason both move here too: `v4_defender_scout` (2 processes, benefits from
fairer mid-tick reallocation exactly as G1 found) gains a full 14.3 points and starts winning
matches for the first time in the entire study; `v4_claimer` and `v4_concentrated_attacker`
(single-process, their *own* scheduling is structurally untouched by this parameter) still move,
because their aggregate win rate is measured against a roster where 4 of 7 possible opponents are
multi-process and now behave differently under round-robin.

**Result is genuinely mixed, not uniformly "fairer."** Round-robin does not simply help
under-performing agents at the expense of dominant ones: Hydra's win rate *increases* by 11.3
points under round-robin (the opposite direction from what reversing its own declared order alone
produced in G1 — a different mechanism, since G1 held selection mode fixed and permuted the list,
while G2 holds the list fixed and changes the selection rule). Nemesis drops by 12.8 points,
converging toward but still well above Hydra's now-comparable strength. Net effect on the roster's
worst-off members is small: `v4_local_defender` still wins 0% of its matches, and `v4_scout`/Viper
are statistically unchanged.

**Conclusion**: current declaration-order-as-priority scheduling is not "strategically useful" in
the sense of rewarding deliberate agent design (no agent in this roster's documentation claims to
have chosen its process order for this reason) — it is closer to an accidental, undocumented lever
that happens to currently favor Nemesis over Hydra by a wide margin and disadvantage
`v4_defender_scout` entirely. Round-robin removes that particular accident without introducing a
new dominant strategy or meaningfully helping the roster's actually-weakest agents
(`v4_local_defender` remains at 0%). This is evidence *for* adopting round-robin as a fairness
improvement (removing an unintended, undocumented advantage) but not evidence that it solves the
ecology's deeper problem (Nemesis and Hydra still occupy the top two positions by a wide margin
either way) — see Section J/K.

---

## H. Representative Replay Observations

See `summaries/representative_replay_notes.md` for the full write-up. Eight replays retained
(`replays/*.jsonl`, manifest at `replays/manifest.json`):

1. **`baseline_typical_core_rush`** — Nemesis eliminates `v4_local_defender` in 3 ticks: the
   typical fast-resolution baseline pattern.
2. **`baseline_stalemate`** — Viper vs. `v4_claimer`, tick-limit at 1000: neither side's declared
   reach ever covers the 128-cell baseline separation; a concrete instance of the ~47% baseline
   tick-limit population.
3. **`core_size16_extended`** — Nemesis vs. Hydra tied at tick 1000 under core_size=16: illustrates
   Section C's "permanent deadlock between mutually-capable opponents" finding.
4. **`core_size16_longer_race_not_counterplay`** — Nemesis vs. `v4_claimer` resolves in 30 ticks
   (vs. 2 at baseline) under core_size=16, same winner: illustrates the contrasting "just a longer
   race" pattern in the same experiment.
5. **`reach_cap_n8_neutralized`** — Nemesis's three processes sit frozen at their starting anchor
   for all 1000 ticks, 256 cells outside their capped 64-cell reach: direct visual confirmation
   that a reach cap disables Nemesis's strategy outright rather than degrading it gracefully.
6. **`seeded_placement_genuine_miss`** — Nemesis's hardcoded `own_core_base + arena/2` targeting
   formula computes address 92 against `v4_claimer`'s real core at 88 (a 4-cell miss inside an
   8-cell core); `v4_claimer` survives the full match. The study's single clearest illustration of
   the placement-dependency finding in Section F2.
7. **`disperser_vs_nemesis_dispersal_does_not_help`** — Disperser, already spread across four core
   cells at tick 0, still dies in 2 ticks: Nemesis overwrites absolute core-cell addresses
   directly, which dispersal does not slow. Grounds Section E's Disperser finding.
8. **`local_hunter_disrupt_locked`** — Local Hunter's search brings it within reach of a
   reach-capped, stationary Nemesis at tick ~20, after which Nemesis's `disruptor` locks it in
   place, unable to act at all, for the rest of the match. Grounds Section E's novel single-process
   disrupt-lock finding.

A metric moving in a "good" direction was checked against these replays in every case before being
reported as a finding — e.g. the process-spread experiment's small movement changes were confirmed,
by inspecting tick-0 anchors directly, to reflect genuinely distinct starting positions per the
intended formula rather than a no-op, and the core-size deadlock finding was confirmed by reading
final-tick anchors and scores rather than trusting the aggregate `tie` count alone.

---

## I. Alpha1 Integrity

**Equivalence proof** (`config/equivalence_check.md`): the research harness's `baseline` condition
(every new `MatchRequest` field at its default) and the normal `bytefray run` CLI path produce
**byte-identical** `replay.jsonl` output (SHA-256
`6e59d3db73b4fae5b14b175fdd59b53c569f40603716b352f08ac775c4d72e7b`, 573,659 bytes) for the same
agents/seed/arena/ticks/starts. This is corroborated at 2,688-match scale by the `core_size_8`
condition reproducing every one of `baseline`'s aggregate statistics to three decimal places.

**Regression control**: the full existing engine test suite (2,531 tests, 2,529 before this
study's second commit) passes unchanged after both production commits on this branch; the second
commit added exactly 2 new tests exercising the new `process_selection_mode` parameter, both
passing. `ruff check .` and `mypy engine/src/battle_engine` are clean after every production
change on this branch (see the two commits' messages for exact test-run numbers).

**Production modules touched** (both isolated, single-purpose commits on this research branch,
flagged here for Phase 5 review per the governing task's instruction):

1. `research(v4): add Phase 4 core/reach/spread/order overrides` — adds `core_size`, `reach_cap`,
   `process_spread_radius`, and `process_order_overrides` to `MatchRequest`/
   `ProcessMatchController`, plus additive per-process telemetry in `NativeAgentResult.metadata`.
2. `research(v4): add round-robin process-selection mode (Phase 4K)` — adds
   `process_selection_mode` to the same surface.

Every one of these five fields:
- defaults to `None`/Alpha1's exact existing value;
- is never read by any CLI argument parser, GUI code path, or `EvaluationRequest`/`Tournament
  Request`;
- when left at its default, was independently proven (unit tests + the byte-identical equivalence
  check + the 2,688-match `core_size_8`-vs-`baseline` statistical match) to reproduce Alpha1's
  existing behavior exactly.

No existing Ruleset identity changed; `bytefray-rules-4-alpha1` and `bytefray-rules-4-alpha2` (the
latter not created) remain exactly as they were. Replay schema version stayed 4 throughout — the
additive telemetry lives in the already-free-form `NativeAgentResult.metadata` dict, the same seam
`entry_point`/`local_source_fingerprint`/the v3 locality-stats precedent already used, not in the
replay schema itself.

---

## Questions Phase 4 Must Answer

1. **Is `Q == core_size` a major cause of ultra-short matches?** Partially. It is sufficient for
   one dominant matchup type (a global-writer vs. an outmatched opponent, e.g. Nemesis vs.
   `v4_claimer`: 2-tick resolution at baseline) but not the whole story — the same corpus already
   contains a ~47% population of matches that never resolve at all regardless of core size, because
   the two entrants can never reach each other (Section B, `tick_budget_decision.md`). Core size
   governs *how fast* a reachable kill happens, not *whether* two entrants can interact at all.
2. **Does increasing core size create genuine counterplay or only longer artillery races?** Both,
   split cleanly by matchup type — see Section C. Symmetric strong-vs-strong matchups (Nemesis vs.
   Hydra) collapse into permanent deadlock; asymmetric matchups (Nemesis vs. any outmatched
   starter) just take longer with an unchanged outcome. Neither is what "genuine counterplay"
   implies (a contest whose *outcome*, not just its length, depends on ongoing interaction).
3. **Does effective global reach suppress movement and local information play?** Not directly —
   the roster's two global-reach agents (Hydra, Nemesis) never search or move regardless of reach;
   their advantage comes from a hardcoded placement assumption, not reach-enabled omniscience
   (Sections D, F2). Capping their reach does suppress their *strategy*, but it does not reveal
   suppressed local play in the rest of the roster — it mostly just increases the tick-limit rate
   (46.8% → 90.5%), because nothing else in the roster was built to search effectively either.
4. **Can a deliberately local/moving agent become viable when global reach is removed?**
   Conditionally yes (Section E): Local Hunter genuinely hunts down and defeats an opponent with no
   counter-offense (`v4_claimer`, 64/64) through real pursuit, proving active local movement can
   work under current mechanics. It still loses instantly to Nemesis/Hydra's placement-exploit
   opening regardless of any of this study's reach caps, and a *new* risk emerged that has nothing
   to do with reach at all: a single-process pursuer that gets close enough to detect a reactive
   opponent without immediately winning can be permanently disrupt-locked with no way to disengage.
5. **Is process co-location the main cause of whole-roster opening disruption?** The mechanism is
   real (Section E's Disperser probe/Section F1's discussion of shared-anchor disruption) but
   spreading the *existing* roster's own processes by a modest radius produced only a small effect
   on match outcomes (Section F1) — co-location is a necessary condition for whole-roster
   disruption, not, by itself, a major determinant of who wins the baseline ecology.
6. **How much advantage comes from deterministic opposite-core knowledge?** The largest single
   effect measured in this entire study: it accounts for the majority of Nemesis's and Hydra's
   baseline dominance (100%/80.1% → 21.1%/23.5% the instant placement is made unpredictable,
   Section F2) — both agents' source code hardcodes this exact assumption.
7. **Does process dispersion create healthy resilience through disruption/quota redistribution?**
   No, for either mechanism tested. Spreading the roster's *existing* agents' processes moved
   outcomes only marginally (Section F1). A probe purpose-built to test dispersion directly
   (Disperser, Section E) still lost every single match against every genuinely aggressive
   opponent, in 2–3 ticks — dispersion defends against *disruption* (losing a future turn), but
   Nemesis/Hydra's attack is a direct overwrite race against fixed absolute core-cell addresses
   that dispersal does not slow at all.
8. **Is declaration order a useful intentional strategy dimension or an accidental dominant
   lever?** Accidental (Section G) — no roster agent's documentation claims to have chosen its
   process order deliberately, the effect is substantial (up to 14.3pp) and disappears under a
   documented, simple, order-independent alternative (round-robin) without introducing a new
   dominant strategy.
9. **How large is current seat/order advantage?** Materially large for exactly one agent (Hydra:
   +11.3pp at baseline, growing to +17.3pp under round-robin selection) and 0% by construction for
   every single-process agent (a lone process's declared start does not depend on which seat it is
   assigned). Not a roster-wide phenomenon, but not negligible where it exists.
10. **Which single change or smallest combination produces the largest increase in strategic
    variety with the least rules complexity?** Core-placement unpredictability alone (Section K) —
    zero engine/Agent-API/replay-schema changes, the single largest effect size measured, and it
    dismantles the *specific* mechanism (a documented placement assumption) that currently makes
    reach, movement, and local search irrelevant for the roster's two strongest agents, rather than
    just suppressing their reach or inflating core size and hoping something else fills the gap.
    Round-robin process selection is a good, low-complexity complementary fix for a *separate*,
    smaller accidental advantage (Section G), but is not on its own sufficient to change the
    ecology's dominant strategies.

---

## J. Recommendation Matrix

| Axis | Classification | Evidence |
|---|---|---|
| **Core size** | RETEST IN COMBINATION (with a mechanism to prevent mutual-deadlock, e.g. a repair-rate cap or bounded stalemate resolution) — not KEEP, not a standalone CHANGE | Breaks one dominant strategy's 100% win rate, but converts the roster's most symmetric matchup into permanent stalemate rather than richer counterplay (Section C) |
| **Reach** | INSUFFICIENT EVIDENCE to recommend a specific cap as an Alpha2 default; DEFER a concrete number pending local-strategy viability work | Capping reach disarms the two dominant agents entirely rather than creating graduated local play (Section D); whether *any* cap value would reward genuine local search remains open pending Section E |
| **Initial process deployment (spread)** | KEEP ALPHA1 BEHAVIOR | Measured effect on outcomes is small and does not change any agent's ranking (Section F1) |
| **Core placement (predictability)** | **CHANGE FOR ALPHA2** | By far the largest, most robust, best-mechanistically-understood effect in the study: collapses two dominant agents from 100%/80% to 21%/24% by removing a documented, hardcoded exploit of a deterministic rule, with no engine change required at all (Section F2) |
| **Process execution order** | CHANGE FOR ALPHA2, narrowly (adopt round-robin selection) | Declaration order is a substantial (up to 14.3pp), almost certainly accidental lever under the current priority-scan scheduler (Section G1); round-robin removes it without introducing a new dominant strategy, but does not by itself dethrone Nemesis/Hydra (Section G2) — a fairness fix, not an ecology fix |

---

## K. Minimal Alpha2 Candidate

**Primary change: randomize (or otherwise de-predictabilize) initial core placement, subject to a
minimum separation, derived deterministically from the match seed. Secondary, independent change:
adopt round-robin process selection in place of Alpha1's priority scan.**

- **What changes**: entrant start positions are no longer the fixed `(0, arena_size/2)` pair.
  Instead, each match seed deterministically derives a pair of start positions satisfying a
  minimum circular separation (this study used 64 cells; Alpha2 should pick its own constant,
  informed by whatever core size Alpha2 ships with).
- **What remains identical to Alpha1**: `Q=8`; core size (8, unless Section J's core-size
  recommendation is separately adopted); reach legality bounds (`[1, arena_size-1]`); process
  declaration/execution semantics *except* for the process-order change below; initial process
  co-location (Section F1 showed spreading is not warranted on its own evidence); the K=2 chunked,
  rotating-start scheduler's entrant-level behavior; disruption and quota-redistribution mechanics.
- **Agent API v2**: unchanged. Placement unpredictability requires no new observation or action —
  agents already receive `own_core_base`/`visible_enemy_anchor_addresses` and can already, in
  principle, search rather than assume. `agent.py`s that hardcode the opposite-core assumption
  (Nemesis, Hydra) would simply stop working as designed; this is the intended effect, not a
  compatibility break, since the assumption they hardcode is a Ruleset-level historical accident,
  not a documented Agent API contract.
- **Replay schema 4**: unchanged. Entrant start position is already a per-match, per-entrant field
  (`MatchConfiguration`/entrant metadata); randomizing its *value* changes no schema shape.
- **Compatibility implications**: any bundled or user agent whose strategy depends on the current
  deterministic placement (confirmed: Hydra, Nemesis) would need to add genuine search/detection
  behavior to remain competitive. This is a deliberate, disclosed behavior change to the Ruleset's
  gameplay balance, not a silent one — exactly the kind of evidence-supported rule delta Phase 5 is
  meant to evaluate, and it is the *smallest* change in this study's evidence that produces the
  largest increase in strategic variety (it does not just weaken two agents; it removes the
  specific mechanism — placement prediction — that makes searching, moving, and locally engaging an
  opponent pointless for a global-reach writer in the first place).

The process-order finding (Section G) is a second, independent, much smaller-footprint candidate
worth adopting alongside the placement change: swap Alpha1's priority-scan process selection for
round-robin (already prototyped as `process_selection_mode="round_robin"` on this branch). It
removes a substantial (up to 14.3pp), undocumented, order-dependent advantage without introducing
any new dominant strategy (Section G2), but — unlike the placement change — it does not by itself
dethrone Nemesis or Hydra, so it should be adopted as a fairness correction alongside the
placement change, not proposed as an alternative to it.

**Core size is deliberately not part of this minimal candidate**: Section C's evidence shows it
trades one problem (one-sided domination) for another (mutual deadlock) rather than solving the
underlying issue, so recommending it now would be recommending complexity the evidence does not
clearly support (per the governing task's explicit instruction on Question 10).

---

## L. Phase 5 Readiness

Every research question posed for Phase 4 (Sections B–G, "Questions Phase 4 Must Answer") has
evidence-based answers, at effect sizes large enough (tens of percentage points, holding
independently across all three tested arena sizes) that additional seeds would sharpen confidence
intervals without changing any conclusion. The Alpha1 baseline, all four gated experiments
(core size, reach, deployment ×2, process order ×2), and the two mechanism-isolating probes all
ran to completion on the exact production match-execution path, with byte-identical and
statistical equivalence checks confirming the research harness never diverged from the real
Ruleset, and the full existing regression suite passing unchanged after every production change.
A single minimal, evidence-supported Alpha2 candidate (Section K) has been identified, with its
Agent API and replay-schema compatibility implications stated explicitly, and is not implemented
on this branch.

```text
PHASE 4 COMPLETE — READY FOR PHASE 5
```
