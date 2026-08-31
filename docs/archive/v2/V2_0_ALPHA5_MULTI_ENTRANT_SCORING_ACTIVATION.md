# Bytefray v2.0.0-alpha.5 — Multi-Entrant Scoring Activation

This is a measurement pass, not a mechanic or scoring change. It asks the
question alpha.4 and alpha.4.1 both left open: now that multi-entrant play
lets one entrant die while others continue (alpha.4), and dead entrants can
no longer win a match while any entrant survives (alpha.4.1), do Bytefray's
existing `alive`/`kill` scoring terms ever materially change **which
surviving entrant wins**? `CORE_SIZE`, arena size, tick/instruction budget,
scoring weights, `resolve_winner`, every mechanic, and every existing
starter/reference agent are held byte-for-byte identical to
alpha.1–alpha.4.1. No new Ruleset ID is introduced.

Branched from the verified alpha.4.1 baseline, commit
`c748f407c470e5124d4ceffd0bdda93ae1455f8f` on `v2.0-development` (`main`
unchanged at `5593d287f95a24996bb3b105befbc625a00795db` throughout).

## 1. Verified starting state (Phase 1)

Confirmed directly, not assumed:

- Branch: `v2.0-development`.
- HEAD at start of this work: `c748f407c470e5124d4ceffd0bdda93ae1455f8f`.
- Working tree: clean.
- `main`: `5593d287f95a24996bb3b105befbc625a00795db`, unchanged.
- Local branch was 4 commits ahead of `origin/v2.0-development`; nothing
  pushed.
- `docs/V2_0_ALPHA4_MULTI_ENTRANT_FEASIBILITY.md`,
  `docs/V2_0_ALPHA4_1_WINNER_SEMANTICS.md`, and
  `docs/V2_0_ALPHA3_SCORING_SENSITIVITY.md` were read in full before any
  code was written.
- `results.py` (`resolve_winner`), `scoring.py` (`ScoringPolicy`),
  `config.py` (`Config`/`Weights` defaults), `python_runtime.py`
  (`apply_core_capture`, `CORE_SIZE`, the tick loop's `events`/replay
  publication), `replay.py` (`iter_replay`, `KillDeathEvent`,
  `TickSnapshot`), `test_v2_alpha4_multi_entrant.py`,
  `test_v2_alpha4_1_winner_semantics.py`, and
  `runs/v2_0_alpha4_multi_entrant/run_evaluation.py`/`analyze.py` were all
  read directly, not inferred from documentation alone.
- Every reference/starter agent under consideration
  (`core_seeker/agent.py`, `core_defender/agent.py`,
  `reactive_core_defender/agent.py`, `claimer/agent.py`, `hunter/agent.py`)
  was read directly, line by line, before designing the matrix.
- Regression baseline reproduced exactly as documented: pytest **1543
  total / 1537 passed / 6 skipped / 0 failed**; alpha-focused suites
  112/112; Ruff clean repo-wide; mypy clean for both `engine` (69 files)
  and `client` (10 files).

## 2. Central question

> Now that multi-entrant play creates unequal survival and kill statistics
> and dead entrants cannot win, do Bytefray's existing `alive` and `kill`
> scoring terms ever materially change which surviving entrant wins under
> the default rules?

## 3. Unchanged mechanics (Phase 2)

Not modified anywhere in this work, confirmed by an empty
`git diff -- engine/src client/src`: `CORE_SIZE=8`
(`python_runtime.py:68`), `arena_size=4096`, `instr_per_tick=8`,
`resolve_winner`'s survivor-eligibility rule (`results.py:44-84`), core
ownership seeding, core-capture attribution, kill attribution, Agent API
v1, the scheduler, `bytefray-rules-2-alpha1`'s identity, and every
reference/starter agent's own source. No new Ruleset ID was created.

## 4. Unchanged score weights (Phase 2)

`Config().weights` (`config.py:11-16`), read directly, never varied:

```
alive:            1.0   (points / tick alive)
kill:              5.0   (points / kill event)
territory:         1.0   (points / bucket / tick)
territory_bucket:  64    (cells / bucket)
```

`score = alive_ticks * weights.alive + kills * weights.kill + bucket_sum *
weights.territory`, where `bucket_sum` accumulates `cells_owned // 64` every
tick (`scoring.py`'s `score_alive`/`score_kill`/`score_territory`).

## 5. Alpha.4 baseline reproduction (Phase 3)

`runs/v2_0_alpha4_multi_entrant/run_evaluation.py` was rerun fresh, byte-
for-byte unmodified, at this alpha's starting commit. All 12 matches
reproduced the exact winners, terminations, and tick counts already on
disk. The two known capture matches were checked field-by-field against
`docs/V2_0_ALPHA4_1_WINNER_SEMANTICS.md` §10's documented table and matched
exactly:

| Match | A (`reactive_core_defender`) | B (victim, dead) | C (`core_seeker`, winner) |
|---|---|---|---|
| `(reactive_core_defender, claimer, core_seeker)` | score 1530.0, alive | `claimer`, score 2021.0, `core_captured` | score 1733.0, 1 kill |
| `(reactive_core_defender, hunter, core_seeker)` | score 1540.0, alive | `hunter`, score 1991.0, `core_captured` | score 1725.0, 1 kill |

No dead entrant wins; `core_seeker` (the higher-scoring survivor) wins
both, exactly as alpha.4.1 established. This is a direct, executed
reproduction, not a re-read of the prior report — the governing task's
Phase 3 requirement is satisfied before any expansion.

## 6. Files changed (Phase 24 item 3)

- Added: `runs/v2_0_alpha5_multi_entrant_scoring/run_evaluation.py`,
  `runs/v2_0_alpha5_multi_entrant_scoring/analyze.py`,
  `runs/v2_0_alpha5_multi_entrant_scoring/raw_matches.json`,
  `runs/v2_0_alpha5_multi_entrant_scoring/analysis_summary.json` (all
  under the existing `runs/` `.gitignore` precedent — local scratch, not
  part of this commit; this document is the durable record).
- Added: this document.
- **No production code was changed anywhere in this alpha** — confirmed by
  an empty `git diff -- engine/src client/src` (Phase 26/27 below). No
  correctness defect was found that required a fix.

## 7. Matrix design (Phases 4–7)

### 7.1 Agent pool: 5, up from alpha.4's 4

`claimer`, `hunter` (Ruleset-v1 starters), `core_seeker`,
`reactive_core_defender`, and **`core_defender`** (new to this alpha) — all
five v2.0.0-alpha reference/starter agents whose own source was read
directly and confirmed to never call a method on `context.rng` (each
`reset()` stores it with an explicit "unused by this strategy" comment).

`core_defender` was added for a specific, mechanism-grounded reason, not
picked arbitrarily: alpha.3 §14 already found it is the single most
reliably captured entrant against `core_seeker` in 1v1 play (5/5 seeds,
versus `reactive_core_defender`'s 0/70). Reading its source
(`core_defender/agent.py:68-84`) directly confirms why its footprint
differs from `claimer`/`hunter`: it unconditionally re-`WRITE`s one of its
own `DEFENDED_RADIUS=8` core cells every `REFRESH_EVERY=4`th action, so by
its own 4th action every match, its own core region already contains a
foreign-looking (non-zero, non-`core_seeker`-signature) byte — far earlier
than `claimer`/`hunter`, whose blind sweeps only touch their own spawn
region incidentally, if a stride happens to land there at all within 200
ticks. This is choosing an existing, already-published reference agent for
its own already-documented behavior — not privileged information handed to
`core_seeker`, not a change to its scan algorithm, and not a hardcoded
sacrificial victim (`core_defender` actively defends; alpha.1–alpha.3
already found it is simply less effective at defending than
`reactive_core_defender`).

**Excluded, with reasons**: `strider` shares `claimer`'s blind-sweep,
no-core-defense footprint (its only addition is "skip cells I already
own"), so it would not exercise a materially different capture-timing
mechanism. `wanderer`'s alpha.3 capture rate against `core_seeker` was only
1/5 — the weakest signal of any tested victim for this alpha's specific
"produce more/earlier captures" objective, versus 5/5 for
`core_defender`/`strider`/`hunter`. `adaptive` was excluded to keep the
matrix moderate and interpretable (governing task Phase 6); neither it nor
`wanderer`/`strider` received the RNG determinism audit performed on the
five agents actually used, since none of the three is used here.

### 7.2 Trios and rotations

Every unordered 3-agent combination of the 5-agent pool,
`C(5,3) = 10` (alpha.4: `C(4,3) = 4`), each run through 3 cyclic seat
rotations (each agent occupies each of the three start slots exactly once
across the three rotations) — byte-for-byte the same `seat_rotations()`
shape alpha.4 used. **Total: 10 × 3 × 1 seed = 30 matches** (alpha.4: 12).

This systematic enumeration — not hand-picked matchups — already contains
every trio class the governing task's Phase 6 asked for as a literal
subset:

| Required class | Trio (subset of the 10) |
|---|---|
| Expansion + offense + defense | `{claimer, core_seeker, reactive_core_defender}` |
| Strong expansion + offense + another combat-capable strategy | `{hunter, core_seeker, claimer}` |
| Blind vs. reactive defense with offense present | `{core_defender, reactive_core_defender, core_seeker}` |
| Third-party interference | `{core_seeker, hunter, claimer}` and `{core_seeker, hunter, reactive_core_defender}` — the exact pair alpha.4 §16 found diverges on capture success |

3 cyclic rotations (not all 6 permutations) were used, with the same
justification alpha.4 itself established and re-verified for this pool: at
most one offense-capable agent (`core_seeker`) exists in any trio drawn
from these 5, so no match in this matrix can ever have two simultaneous
attackers on the same core in the same tick — the only scenario
(`_attribute_core_capture`'s tick-diff replay order) where the 3 permutations
omitted by cyclic rotation could produce a materially different outcome
beyond seat/geometry effects. 3 cyclic rotations already cover every seat
position each agent can occupy, which is the axis this alpha needed to
vary.

### 7.3 Placement

Deterministic thirds of the 4096-cell arena — seat A = `0`, seat B =
`1365`, seat C = `2730` — reused byte-for-byte from alpha.4's own
convention. No position sweep was performed.

### 7.4 Config

`bytefray-rules-2-alpha1`, `arena_size=4096`, `instr_per_tick=8`,
`max_ticks=200`, default `Config().weights` — identical to alpha.4
throughout, never varied.

## 8. Seed relevance (Phase 5)

All five agents in `AGENTS` were confirmed, by direct source reading (not
assumed), to never call a method on `context.rng` in `act()`. This
includes `core_defender`, the one agent new to this alpha's pool — its
`reset()` at `core_defender/agent.py:59` stores `self.rng = context.rng`
with the identical "unused by this strategy, but always available" comment
already verified true for the other four in alpha.4. **All five agents are
therefore fully deterministic given a fixed matchup/placement**: a second
seed would reproduce byte-for-byte identical results for all 30 matches.
Exactly one seed (`1`) was used throughout — using additional seeds here
would be pseudo-replication, not additional evidence, per the governing
task's explicit instruction.

**Number of unique behavioral conditions: 30** (one per trio × rotation).
**Number of raw executions: 30.** **Results repeated deterministically:
none skipped or deduplicated** — every one of the 30 conditions is a
distinct matchup/seat assignment, so no executions were pseudo-replicated
within this design; the pseudo-replication risk that was avoided is
*additional seeds*, not additional trios/rotations.

## 9. Exact execution count and infrastructure failures (Phase 24 items 10–11)

**30 matches, 0 infrastructure failures**, completed in 3.20s. Every match
terminated via `tick_limit` (`ticks_run=200` in all 30) — no
`last_agent_standing` termination occurred anywhere in this corpus (the
maximum simultaneous eliminations observed in any single match was 1 out
of 3 entrants, never 2).

## 10. Elimination timing (Phases 8, 10)

Tick buckets were fixed **before** execution, against the 200-tick budget:
early = elimination tick in `[1, 66]` (`200 // 3`); mid = `[67, 133]`
(`(2 * 200) // 3`); late = `[134, 200]`.

| Bucket | Count |
|---|---:|
| Early | 0 |
| Mid | 0 |
| Late | **4** |

**Total eliminations: 4 of 30 matches (13.3%)**, up from alpha.4's 2/12
(16.7%) in raw count terms (4 vs. 2) but at essentially **identical
timing**: ticks 160, 166, 168, 160 here versus alpha.4's 159 and 165. All 4
are core captures; **no other death cause occurred anywhere in this
corpus.**

### 10.1 Why the deliberate `core_defender` lever did not produce earlier captures

This is the single most important negative-but-informative finding of this
alpha's design phase, and it is reported honestly rather than
re-engineered to fit the hypothesis. `core_defender` was included
specifically because it marks its own core region with foreign-looking
content by tick 4 — far earlier than `claimer`/`hunter` incidentally would.
Despite this, **`core_defender` was never captured in any of its 18
appearances in this matrix** (0/18; see §14 below), and the 4 captures that
did occur were still victims `claimer`/`hunter`, at essentially the same
tick range alpha.4 already observed.

Direct source analysis of `core_seeker/agent.py` explains why: detection
requires **two** scan hits within `LOCK_RADIUS=12` of each other
(`_within_lock_radius`), not merely one hit landing on foreign content.
`core_seeker`'s scan cursor advances by a fixed, golden-ratio-derived
stride (`scan_stride ≈ 1565`) that visits a *different* address on every
scan (`gcd(1565, 4096) = 1`, a full 4096-address period) — so getting two
hits within 12 of each other depends on the scan sequence's own
equidistribution/near-return structure, a property of `core_seeker`'s
fixed schedule alone, **not on whether the region being scanned is
"marked early" or "marked late."** Once *any* two nearby addresses happen
to both contain non-zero, non-`core_seeker` content at the moment they are
each read, a lock (and capture) follows — regardless of how long that
content had already been sitting there. `core_defender`'s early
self-marking made its core region "capturable" from tick 4 onward, but
never actually improved the odds of the scan sequence's own close-return
event landing there specifically, because that event's timing is
governed by `core_seeker`'s scan geometry, not by target readiness.

This directly answers a question alpha.4 §20 left open ("would an earlier
capture happen with a weaker/slower victim?") — **no evidence for that
was found here**: victim vulnerability (as measured by 1v1 capture rate)
did not translate into earlier or more frequent 3-way captures in this
matrix. What *did* increase was the raw capture count (4 vs. 2), because
adding a fifth agent added more trios in which `core_seeker` could occupy
seat C against *some* eligible victim, not because any victim was captured
faster.

## 11. Alive/kill differentiation (Phase 10)

| Metric | Result |
|---|---:|
| Matches with a core capture | 4 / 30 (13.3%) |
| Matches with divergent `alive_ticks` | 4 / 30 — the same 4 |
| Matches with divergent `kills` | 4 / 30 — the same 4 |
| Entrants earning ≥1 kill | 4 (one per capture match — `core_seeker` every time) |
| Entrants earning ≥2 kills (multi-kill) | 0 |

Identical structural pattern to alpha.4: raw activation occurs exactly
when, and only when, a capture occurs.

## 12. Score decomposition (Phase 9/16)

`bucket_sum` was computed and validated **twice** per agent per match, not
merely inferred: (1) algebraic inversion
(`bucket_sum = (score − alive_ticks·1.0 − kills·5.0) / 1.0`), and (2) a
runtime assertion inside `run_evaluation.py` that reconstructing
`alive_ticks·1.0 + kills·5.0 + bucket_sum·1.0` reproduces the recorded
`score` to within `1e-6`, and that `bucket_sum ≥ 0`, for all 90
(30 matches × 3 agents) records — **zero mismatches, zero negative
values.**

`tick_of_elimination` and `killer` were **not** inferred from
`alive_ticks` — they were read a second, independent, exact way, directly
from the engine's own replay: `python_runtime.py`'s `apply_core_capture`
appends a `{"type": "kill"/"death", "victim":…, "by":…}` engine event into
that tick's `events` list, which `PythonEntrantController.run` publishes
via `replay.publish_tick(tick, …, events)`. `run_evaluation.py`'s
`extract_elimination_events` reads this back with the production
`battle_engine.replay.iter_replay` reader, matching each `TickSnapshot`'s
own `tick` and `KillDeathEvent.killer`/`.victim` fields exactly.

## 13. Matches with 2+ survivors at resolution (Phase 24 item 17)

**30 / 30.** No match in this corpus ever reached a `last_agent_standing`
resolution (which would require 2 of 3 entrants to die) — every match had
either all 3 entrants alive (26 matches) or exactly 2 (the 4 capture
matches) at the tick limit. `single_survivor_matches = 0` — the
governing task's "score dimensions cannot affect first place by
definition" case did not occur in this matrix.

## 14. Territory-only vs. full-score survivor winner comparison (Phases 11, 21)

Restricted, for the first time in this alpha line, to `eligible_slots` —
`resolve_winner`'s actual eligibility set (alive entrants when any exist,
per `results.py:44-84`), not alpha.4's own `analyze.py`, which ranked the
full entrant set including dead ones. Every one of this alpha's 30
counterfactual computations was cross-validated against the engine's own
`result.winner` and matched exactly, 30/30 — direct proof the
survivor-only reimplementation is faithful to production `resolve_winner`
behavior, not merely believed to be.

| Measurement | Result |
|---|---:|
| Matches where the survivor-restricted full-score winner differs from the survivor-restricted territory-only winner | **0 / 30** |
| Matches where adding `alive` changes the survivor-only top rank | **0 / 30** |
| Matches where adding `kills` changes the survivor-only top rank | **0 / 30** |
| Matches requiring both `alive` and `kills` together to change the top rank | **0 / 30** |
| Engine cross-validation failures (survivor-only reimplementation vs. real `result.winner`) | **0 / 30** |

## 15. A new structural proof: `alive_ticks` can never differentiate survivors (Phase 12)

This is the sharpest new result of this alpha, extending alpha.3 §8's
1v1 proof to the general N-entrant, tick-limit case. `RulesetPolicy.
resolve_termination` only forces early termination at `alive_count == 0`
or `alive_count == 1` (unchanged since alpha.4 §4). Therefore: **whenever
2 or more entrants are alive at the moment `resolve_winner`'s score
comparison actually runs, the match necessarily ran the full
`max_ticks` budget with all of them alive throughout** — by definition, a
"survivor" that only counts as alive at match end without having been
alive continuously would have been eliminated (and thus excluded from
`eligible`) already. Consequently every survivor's `alive_ticks` at
resolution time is **provably, structurally identical** — all equal to
`ticks_run` — whenever 2+ survivors exist.

This was verified empirically over the full corpus, not just asserted:
`analyze.py`'s structural check confirms **`alive_ticks` was exactly tied
among the eligible survivor set in all 30 of 30 matches** (including the 4
capture matches — the two survivors in each were both alive to the tick
limit at `alive_ticks=200`, only the dead victim differed). Since adding a
constant offset (equal `alive_ticks × weights.alive` for every eligible
entrant) never changes a ranking, **`weights.alive` has zero
winner-selection leverage among survivors in *any* tick-limit-resolved
multi-entrant match under the current termination rule — not an artifact
of this sample, a closed-form consequence of `resolve_termination`'s own
two thresholds.** This directly answers, in the negative and with proof
rather than a sample-limited "0/30," the `alive` half of alpha.4.1 §17's
open question.

`kills`, by contrast, is event-based, not time-based, and **is not**
subject to this proof: two survivors can genuinely end a match with
different kill counts (one attacked and eliminated the third entrant; the
other did not). This is exactly what happened in all 4 capture matches
here — `kills` is therefore the only one of the two dimensions with any
structural possibility of mattering among survivors in this scoring model.

## 16. Exact contribution analysis and margin leverage (Phase 12)

For the 4 real capture matches, the surviving `core_seeker`'s territory
lead over the surviving bystander, versus its `+5` kill bonus:

| Match | Bystander | Territory margin | Kill margin | Kill as % of total margin |
|---|---|---:|---:|---:|
| `(reactive_core_defender, claimer, core_seeker)` | `reactive_core_defender` | 198.0 | 5.0 | 2.46% |
| `(core_defender, claimer, core_seeker)` | `core_defender` | 118.0 | 5.0 | 4.07% |
| `(reactive_core_defender, hunter, core_seeker)` | `reactive_core_defender` | 180.0 | 5.0 | 2.70% |
| `(core_defender, hunter, core_seeker)` | `core_defender` | 115.0 | 5.0 | 4.17% |

In every one of the 4 captures, `core_seeker` was **already the
territorial leader among survivors before the kill bonus is even added** —
the kill contributes 2.5%–4.2% of an already-decisive margin, never the
deciding factor. **Classification: "Activated but weak."** Raw activation
of `kills` is real and repeatable (4/30, exact and exclusively
capture-driven), but territory margins consistently swamp it by roughly
24×–40× in this corpus. This is a sharper, quantified version of alpha.4
§14's qualitative finding ("dwarfed by the territorial lead"), now
expressed as an exact percentage across 4 real cases instead of 2.

## 17. Break-even analysis (Phase 13)

**No qualifying case exists in this corpus.** The governing task's
break-even scenario (a survivor loses despite better `alive_ticks` or
`kills` than the actual winner) requires a survivor who is
*both* behind on final score *and* ahead on `alive_ticks` or `kills`. In
every one of the 4 capture matches, the entrant credited with the kill
(`core_seeker`) was **also** the entrant already leading on territory —
not a coincidence: `core_seeker` is the only offense-capable agent in this
pool, and its own steady `expand_stride=149` outward sweep accrues
territory throughout the full match exactly like every other agent's
sweep, uninterrupted by the assault burst (`ASSAULT_WINDOW=16` actions is
a small fraction of a 200-tick budget). There is consequently no
"nearly-there" survivor in this data to compute a break-even weight for —
this is reported as an honest absence, not a gap in method (§16's `w_alive`
structural proof independently guarantees no `alive`-side case could exist
either).

## 18. Core Seeker findings (Phase 14)

| Metric | Value |
|---|---:|
| Matches played | 18 |
| Wins | 4 / 18 (22.2%) |
| Times captured | 0 / 18 |
| Total kills | 4 (one per capture) |
| Win rate by seat | A: 0/6, B: 0/6, **C: 4/6** |

`core_seeker` never wins from seat A or B — its only 4 wins are exactly
its 4 captures, all occurring with it seated at C (address `2730`), the
seat whose scan-cursor start (`arena_size // 3 = 1365`, seat B's address)
gives it first-scan proximity to seat B specifically (alpha.4 §16's
already-documented seat-C-favors-capture pattern, reproduced unchanged in
this larger corpus: 4/4 captures again seat C attacking seat B). In every
one of its 4 wins, `core_seeker` survives, earns the kill, **and** is
already the territorial leader among survivors (§16) — it does not
"sacrifice" territory for the kill; it wins on both dimensions
simultaneously. It never once loses to the third entrant after a
successful capture in this corpus (unlike alpha.4 §15 item 7's open
question about this exact scenario) — but this corpus's only bystanders in
capture matches were `reactive_core_defender`/`core_defender`, both weak
territorial accumulators (§20 below); whether a stronger bystander
(`claimer`/`hunter`) would out-accumulate `core_seeker` during the ~160+
ticks before a capture remains untested, since `claimer`/`hunter` never
co-occur as the *bystander* in any of this corpus's 4 captures (both were
always the *victim* when present with `core_seeker`@C).

## 19. Reactive Core Defender findings (Phase 15)

| Metric | Value |
|---|---:|
| Matches played | 18 |
| Wins | **0 / 18 (0.0%)** |
| Times captured | 0 / 18 |
| Survival rate | 18 / 18 (100%) |

Exactly reconfirms alpha.2 §11 and alpha.4 §15 item 5, now a third time, in
a richer format with more opponents: 100% survival, 0% competitiveness.
Never captured (its reactive detect-and-repair design continues to work
exactly as alpha.2 designed it to), but perfect survival translates into
zero wins — the `alive` dimension it never loses (§15's structural proof:
it cannot even theoretically gain a winner-selection edge from surviving
when 2+ others also survive) offers it no path to competitiveness whatsoever,
and its expansion output is consistently the weakest among survivors in
every trio it appears in (its win rate is 0% against every single opponent
combination tested, including trios with no `core_seeker` at all — the
loss is about territorial output, not about the defensive mechanic
specifically).

## 20. Claimer findings — free-rider question (Phase 16)

| Metric | Value |
|---|---:|
| Matches played | 18 |
| Wins | 11 / 18 (61.1%) |
| Times captured | 2 / 18 (both by `core_seeker`@C) |
| Win rate by seat | A: 5/6, B: 1/6, C: 5/6 |

`claimer` remains the strongest single agent in this corpus by raw win
rate, consistent with every prior alpha. The specific "free-rider" pattern
the governing task asked about (Claimer profiting from *two other*
entrants fighting each other while it expands undisturbed) **could not be
exercised by this matrix's design**: `core_seeker` is the only
offense-capable agent in the 5-agent pool, so every capture in this corpus
is necessarily a `core_seeker`-vs-victim pair with a single bystander, not
a fight between two non-`claimer` entrants that `claimer` could sit out.
In the 2 matches where `claimer` itself is the victim, it loses outright
(captured, ineligible to win); in matches where `claimer` is the
bystander to a `core_seeker` capture of `hunter`, `claimer` still does not
win those specific matches (`core_seeker` does, §18) — so no evidence of
`claimer` free-riding off combat toward a win was found, positive or
negative, in this corpus. `claimer`'s dominance is attributable entirely
to raw territorial efficiency (unconditional, uninterrupted `WRITE`
coverage), identical to every 1v1 finding since alpha.1 — not to any
combat-adjacent dynamic. Its one clear weakness is seat B (1/6 wins) —
exactly the seat `core_seeker`'s fixed scan geometry targets.

## 21. Hunter and Core Defender findings (Phase 17)

**Hunter:**

| Metric | Value |
|---|---:|
| Matches played | 18 |
| Wins | 11 / 18 (61.1%) — tied with `claimer` |
| Times captured | 2 / 18 (both by `core_seeker`@C) |
| Win rate by seat | A: 3/6, B: 2/6, **C: 6/6 (100%)** |

`hunter` matches `claimer`'s overall win rate exactly but shows a more
extreme seat effect — undefeated from seat C, markedly weaker from A, and
weakest (like `claimer`) from the capture-exposed seat B. `hunter`'s
sparse-then-dense two-phase sweep (§7.1's docstring) does not show a
qualitatively new 3-way dynamic beyond what alpha.4 already found — it
remains a strong, `claimer`-comparable expander.

**Core Defender (blind, new to this alpha):**

| Metric | Value |
|---|---:|
| Matches played | 18 |
| Wins | 3 / 18 (16.7%) |
| Times captured | **0 / 18** |
| Win rate by seat | A: 1/6, B: 1/6, C: 1/6 (flat) |

Despite being included specifically as a theoretically easier `core_seeker`
target (§10.1), `core_defender` was **never captured** in this matrix and
posts a nonzero (if modest) win rate, flat across all three seats — no
seat sensitivity of its own, unlike every other agent in this corpus. It
substantially outperforms `reactive_core_defender` (16.7% vs. 0.0%) despite
`reactive_core_defender`'s strictly superior 1v1 defensive record
(alpha.2/alpha.3) — in this 3-way format, where neither defender was ever
actually attacked, the determining factor was ordinary territorial output,
not defensive quality, and `core_defender`'s specific matchups in this
corpus happened to be more favorable.

## 22. Third-party effects (Phase 18)

Reproducing and extending alpha.4 §16's finding with `core_seeker` fixed at
seat C across all 6 trios containing it:

| Seeker@C | Victim@B | Third@A | Captured? |
|---|---|---|---|
| `core_seeker` | `hunter` | `claimer` | **False** |
| `core_seeker` | `claimer` | `reactive_core_defender` | True |
| `core_seeker` | `claimer` | `core_defender` | True |
| `core_seeker` | `hunter` | `reactive_core_defender` | True |
| `core_seeker` | `hunter` | `core_defender` | True |
| `core_seeker` | `core_defender` | `reactive_core_defender` | **False** (no capture at all — B is `core_defender`, never captured, §21) |

`claimer` as third-party bystander is again the only tested condition that
**blocks** an otherwise-successful `core_seeker`→`hunter` capture — exactly
alpha.4 §16's finding, now additionally shown to hold with `core_defender`
as an alternative attempted victim too (both `reactive_core_defender` and
`core_defender` as bystanders let captures of `claimer`/`hunter` through).
This strengthens alpha.4's tentative explanation: it is specifically the
two defender-style agents' comparatively small, slow expansion footprint
that fails to interfere with `core_seeker`'s scan/expand trajectory, versus
`claimer`'s fast, wide, unconditional sweep. **A gap in this corpus**: no
data point exists for `hunter` as third-party bystander with `core_seeker`
at C (in every trio containing both `hunter` and `core_seeker`, the cyclic
rotation that places `core_seeker` at C happens to also place `hunter` at
B, never A) — flagged as unresolved (§29).

**No kill-stealing was observable in this design** (unlike alpha.4 §5):
with at most one offense-capable agent per trio, no match here can have
two independent attackers contributing to the same capture in the same
tick — a deliberate consequence of this alpha's agent-pool choice, not a
new finding.

## 23. Free-rider and kill-stealing summary (Phase 24 items 30–31)

- **Free-rider**: not demonstrated, positively or negatively — this
  matrix's single-attacker design could not exercise the "two others fight,
  third profits" scenario (§20).
- **Kill-stealing**: not applicable to this matrix's design (§22) —
  already thoroughly characterized in alpha.4 §5 and not re-tested here.

## 24. Seat sensitivity (Phase 19)

| Seat | Matches | Wins | Captured | Kills |
|---|---:|---:|---:|---:|
| A (`0`) | 30 | 9 | 0 | 0 |
| B (`1365`) | 30 | 4 | **4** | 0 |
| C (`2730`) | 30 | **16** | 0 | **4** |

Seat B is the exclusive site of every capture in this corpus (4/4); seat C
accounts for both every kill (4/4, all `core_seeker`) and a disproportionate
majority of wins (16/30, 53%, versus A's 9/30 and B's 4/30). Per-agent
seat breakdowns (§18/§20/§21) show this is not uniform across strategies —
`core_defender` is seat-flat (1/6/1/6/1/6), while `core_seeker`,
`claimer`, and `hunter` all show a strong seat-C preference and a seat-B
penalty. **Seat C's advantage is not fully explained by the capture
mechanic alone**: `hunter` wins 6/6 from seat C including in trios with no
`core_seeker` present at all, indicating an independent geometric/territorial
advantage to that specific address under this arena/stride configuration,
not solely a function of who else is in the match. This is flagged as an
open question (§29), consistent with the governing task's instruction not
to run a position sweep to resolve it in this alpha.

## 25. Deterministic vs. stochastic replication handling (Phase 24 item 32)

All 5 agents confirmed deterministic (§8); all 30 conditions are unique
trio/rotation combinations, none repeated. No statistical testing
(Wilson intervals, exact tests) was applied to this corpus — per the
governing task's Phase 20, these are appropriate only for stochastic
conditions or genuine paired-replication structure, neither of which
exists here. All reported figures are exact counts, exact margins, and one
closed-form structural proof (§15), not estimates.

## 26. Pathologies/exploits (Phase 24 item 33)

None found beyond what alpha.4 already documented (seat-dependent capture
geometry, third-party interference via incidental content overwriting).
No new exploit, scheduler-order pathology, or kingmaking pattern was
observed. The one new observation — seat C's win-rate advantage extending
to matches without `core_seeker` (§24) — is recorded as an open geometric
question, not a pathology, since no mechanic or scoring rule is implicated.

## 27. Is `alive` now competitively meaningful? (Phase 24 item 34)

**No — and provably not, by construction, not merely by this sample.**
§15's structural proof shows `weights.alive` has zero winner-selection
leverage among 2+ survivors in any tick-limit-resolved multi-entrant match
under the current termination rule. This closes alpha.4.1 §17's open
question for `alive` definitively within this scoring/termination model.

## 28. Are `kills` now competitively meaningful? (Phase 24 item 35)

**Real but weak, and never decisive in this corpus.** `kills` genuinely
diverges among survivors (4/30, exact, exclusively capture-driven,
unaffected by the structural constraint that closes off `alive`) and is
not subject to §15's impossibility proof. But its contribution (2.5%–4.2%
of the winning margin, §16) never once changed a survivor-only ranking
(0/30, §14), and in every case where it applied, it reinforced an
already-existing territorial lead rather than overturning one (§17). No
break-even case existed to quantify how far away "mattering" would be.

## 29. Does territory still determine effectively everything? (Phase 24 item 36)

**Yes.** 30/30 matches: the survivor-restricted full-score winner equals
the survivor-restricted territory-only winner. This is the identical
qualitative conclusion alpha.3 §8 reached for 1v1 and alpha.4 §14 reached
for the raw-score ranking in 3-way play, now additionally confirmed for
the *correct*, survivor-restricted question alpha.4.1 introduced — with a
larger sample (30 vs. 12), a wider agent pool (5 vs. 4), more real captures
(4 vs. 2), and one structural (not merely empirical) proof for `alive`.

## 30. Did multiple strategic niches emerge? (Phase 24 item 37)

Partially, and not new relative to alpha.1–alpha.4: `claimer`/`hunter`
remain co-dominant, near-identical unrestricted expanders (61.1% each);
`core_seeker` occupies a real but narrow niche (22.2%, entirely seat-C- and
capture-dependent); `core_defender` shows modest, seat-flat competitiveness
(16.7%) without ever successfully defending against anything (it was
simply never attacked); `reactive_core_defender` remains entirely
non-competitive (0%) despite perfect survival. No agent in this corpus
occupies a niche driven by `alive`/`kill` score leverage specifically —
every observed win, including `core_seeker`'s, is explainable by territory
alone (§14/§16).

## 31. Unresolved questions (Phase 24 / final report item 51)

- Whether `hunter` as third-party bystander (rather than victim) with
  `core_seeker`@C shows the same claimer-blocks/defender-doesn't pattern
  is untested — no trio/rotation in this corpus produced that specific
  seat assignment (§22).
- Seat C's win-rate advantage independent of `core_seeker`'s presence
  (`hunter` 6/6 from C including in `core_seeker`-free trios, §24) is
  unexplained — a geometric/stride-interaction question, not a scoring
  question, deliberately not investigated further here per the governing
  task's no-position-sweep constraint.
- Whether a stronger (rather than weaker) bystander during a `core_seeker`
  capture would out-accumulate `core_seeker` before the capture completes
  remains untested — `claimer`/`hunter` never appear as the *bystander* in
  any of this corpus's 4 real captures (§18).
- Whether captures can ever occur earlier than tick ~160 under any
  legitimate (non-mechanic-changing) lever remains open — §10.1's finding
  is that victim vulnerability does not appear to be that lever; whether
  a different legitimate lever exists (e.g., a 4th or 5th live entrant
  changing scan-sequence dynamics) is unexplored and would require
  mechanics this alpha was scoped not to touch.
- The free-rider and kill-stealing questions remain open in the specific
  sense the governing task posed them (§23) — this matrix's single-
  attacker-agent design could not exercise either.

## 32. Success/rejection verdict (Phase 21/22)

Evidence supporting continuation toward alpha.6, checked against the
governing task's Phase 21 list:

- `alive` contribution changes which survivor wins — **not demonstrated;
  now proven structurally impossible under the current termination rule**
  (§15, §27).
- `kill` contribution changes which survivor wins — **not demonstrated**
  in 30/30 matches (§14, §28).
- `alive` + `kill` jointly change survivor winner — **not demonstrated**
  (§14).
- Terms substantially narrow survivor margins in a repeatable way even
  when not flipping them — **partially**: `kills` reliably contributes a
  small (2.5%–4.2%), consistent fraction of the margin whenever a capture
  occurs (§16), but this is a narrow, capture-gated effect, not a general
  narrowing across the corpus (26/30 non-capture matches show 0%
  alive/kill contribution to the margin by construction).
- Core Seeker gains meaningful but non-dominant reward from elimination —
  **yes, modestly**: win rate rose from 0/12 (alpha.4) to 4/18 within this
  corpus's `core_seeker`-containing matches, entirely attributable to the
  alpha.4.1 eligibility fix correctly crediting it as the higher-scoring
  survivor, not to `kill`/`alive` weight leverage (§18).
- Reactive Defender gains measurable benefit from extended survival —
  **no** (§19, and now provably impossible per §15).
- Claimer gains third-party expansion advantage but does not trivially
  dominate every trio — **inconclusive**, design could not test the
  specific free-rider scenario (§20, §23); Claimer's 61.1% is not
  domination of every trio but is not shown to be capped by combat
  dynamics either.
- Multiple strategic styles obtain distinct niches — **partially** (§30).
- Activated score dimensions show enough leverage to justify a later
  controlled weight experiment — **no** (§14, §16, §17).

Evidence against, present and not minimized:

- **`alive` is now proven, not merely observed, to have zero
  winner-selection leverage among survivors in this scoring/termination
  model** (§15) — a stronger, more general negative result than either
  alpha.3 or alpha.4 established.
- `kills` never once changed a ranking across 30 matches, and its margin
  contribution (2.5%–4.2%) is dwarfed by territory by roughly 24×–40× in
  every case it applied (§16).
- No break-even case existed to even quantify "how close" kills came to
  mattering in a losing scenario (§17) — the one agent that ever earns a
  kill in this pool is also always already winning on territory.
- Deliberately selecting a more historically vulnerable victim
  (`core_defender`) did not produce earlier captures — capture timing
  appears governed by `core_seeker`'s own fixed scan geometry, not victim
  choice (§10.1), narrowing the space of legitimate future levers for
  "earlier captures" considerably.
- Territory alone determines 30/30 survivor-restricted winners (§29) —
  identical in kind to alpha.3's 1v1 finding and alpha.4's raw-ranking
  finding, now confirmed a third time for the specific eligibility-correct
  question.

**Verdict: rejection — do not proceed to existing-score reweighting.**
This is a stronger conclusion than alpha.4's "qualified positive, not yet
demonstrated": alpha.4 left open whether a larger sample or earlier
captures might eventually show `alive`/`kill` leverage. This alpha
specifically targeted both (2.5× the matches, a victim chosen for
historically higher vulnerability) and found neither raised leverage
above zero — and additionally established a closed-form proof that
`alive` cannot ever have such leverage under the current termination rule,
regardless of sample size or agent selection. `kills` remains technically
"activatable" but is not shown to be within reach of mattering at any
scale tested so far.

## 33. Recommendation (Phase 23)

**C. Do not pursue existing-score reweighting.** Per the governing task's
Phase 23 criteria: territory remains overwhelmingly decisive despite
genuine, real `kills` variation (§28–29); the one structural avenue that
could have given `alive` leverage is now proven closed, not merely
untested (§15); and the one concrete lever tried for producing more
favorable `kill`-side evidence (a more historically vulnerable victim) did
not change the outcome's magnitude, only its raw frequency (§10.1, §16).
This is not "the right sample hasn't been found yet" — alpha.3 proved it
for 1v1, alpha.4 raised it as an open question for raw ranking, and this
alpha closes the `alive` half definitively and finds no positive signal
for the `kill` half at 2.5× alpha.4's scale.

If Bytefray v2 work wants to pursue scoring or format changes that make
`alive`/`kill` matter, the direct implications of this alpha's findings
are: (a) the termination rule itself (`resolve_termination`'s
0/1-alive-only early-stop condition), not `Config.weights`, is the actual
structural gate on `alive` ever mattering — reweighting cannot route
around a proof; (b) `kills`' current `+5` weight is 24×–40× too small
relative to the territory margins this agent population produces to be
competitively relevant, which is a `Config.weights`-addressable question
in principle, but one this alpha was explicitly scoped not to answer by
actually varying weights.

## 34. Regression qualification (Phase 27)

| Check | Result |
|---|---|
| `test_v2_alpha4_multi_entrant.py` | 10 / 10 passed |
| `test_v2_alpha4_1_winner_semantics.py` | 12 / 12 passed |
| `test_ruleset_v1_equivalence.py` | 8 / 8 passed |
| Alpha-focused suites (`test_v2_alpha1_reference_agents.py`,
  `test_v2_alpha2_reactive_defender.py`, `test_ruleset_v2_alpha1.py`,
  `test_v2_alpha4_multi_entrant.py`, `test_v2_alpha4_1_winner_semantics.py`) | 65 / 65 passed |
| Full `pytest` | **1543 total / 1537 passed / 6 skipped / 0 failed** — unchanged from the alpha.4.1 baseline, exactly reconciled |
| Ruff (repo-wide) | clean, 0 errors |
| mypy (`engine/src/battle_engine`) | clean, 69 files |
| mypy (`client/src/battle_client`) | clean, 10 files |
| `git diff --check` | clean, no whitespace errors |
| `git diff -- engine/src client/src` | empty — no production code changed |

No new tests were added: no correctness defect was found in this alpha
(Phase 26), so none was required.

## 35. Alpha.6 recommendation (Phase 23/24 item 35)

**Do not proceed to alpha.6 scoring sensitivity as originally envisioned**
(varying `alive`/`kill` weights in the multi-entrant format). This alpha's
own evidence — a structural proof closing `alive` entirely, and `kills`
showing no leverage at 2.5× scale with a deliberately more-vulnerable
victim — does not meet the governing task's Phase 23 bar for "A." It also
does not cleanly fit "B" (more multi-entrant measurement): this alpha
specifically tried the two most direct levers available (bigger corpus,
weaker victim) and found no movement, not a sparse-but-present signal.

If any further Bytefray v2 work in this direction is pursued, the most
directly evidenced next step is **not** a weight experiment but a
targeted investigation of `core_seeker`'s scan-timing behavior itself
(§10.1) — understanding why captures cluster so tightly around tick
~160–168 regardless of victim choice would be a prerequisite for any
future claim that "earlier captures" is achievable through legitimate,
non-mechanic-changing agent/matrix selection at all. That is a
characterization question about an existing reference agent's already-
published behavior, not a scoring or mechanics change, and is explicitly
out of this alpha's own scope.
