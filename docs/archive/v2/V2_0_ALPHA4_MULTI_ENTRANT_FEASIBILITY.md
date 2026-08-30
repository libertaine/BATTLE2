# Bytefray v2.0.0-alpha.4 — Multi-Entrant Feasibility

This is an architecture-feasibility and small-scale measurement pass, not a
mechanic or scoring change. It asks whether moving from Bytefray's
exclusively-tested 2-entrant match format to 3 or more independent entrants
naturally activates the `alive`/`kill` scoring dimensions that
[V2_0_ALPHA3_SCORING_SENSITIVITY.md](V2_0_ALPHA3_SCORING_SENSITIVITY.md) §8
proved are **mathematically dormant in every 1-on-1 match under the current
engine** — a structural consequence of `resolve_winner`'s single-survivor
rule, not a tuning artifact. No scoring weight, mechanic, or permanent
Ruleset is changed here. `CORE_SIZE`, arena size, tick/instruction budget,
scoring weights, Core Seeker, Reactive Core Defender, Core Defender, and
every existing starter are held byte-for-byte identical to alpha.1–alpha.3.

Branched from the verified alpha.3 baseline, commit
`ac9d05fa9cb5019341b458163e6dca4d8514a027` on `v2.0-development` (`main`
unchanged at the v1.6.0 baseline throughout). No new Ruleset ID was created;
`bytefray-rules-2-alpha1` is reused exactly as alpha.1–alpha.3 left it.

## 1. Verified starting state (Phase 1)

Confirmed directly, not assumed:

- Branch: `v2.0-development`.
- HEAD at start of this work: `ac9d05fa9cb5019341b458163e6dca4d8514a027`.
- Working tree: clean.
- `main`: `5593d287f95a24996bb3b105befbc625a00795db`, unchanged.
- Local branch was 2 commits ahead of `origin/v2.0-development`; nothing
  pushed.
- All four prior v2 alpha documents
  (`V2_0_ALPHA_ARCHITECTURE.md`, `V2_0_ALPHA1_EVALUATION.md`,
  `V2_0_ALPHA2_REACTIVE_DEFENSE.md`, `V2_0_ALPHA3_SCORING_SENSITIVITY.md`)
  were read in full before any code was written.
- `match_service.py`, `results.py`, `ruleset_policy.py`, `scheduler.py`,
  `scoring.py`, `statistics.py`, `python_runtime.py`, `supervised_runtime.py`,
  `match.py`, `agent_test.py`, `reference_agents.py`, and the reference
  agents' own source (`core_seeker/agent.py`,
  `reactive_core_defender/agent.py`) were read directly, not inferred from
  documentation alone.
- Regression baseline reproduced exactly as documented:
  pytest **1521 total / 1515 passed / 6 skipped / 0 failed**; Ruleset-v1
  equivalence 8/8; alpha-focused suites 43/43; Ruff clean repo-wide; mypy
  clean for both `engine` (69 files) and `client` (10 files).

## 2. Research question

> Does moving from 2 entrants to 3+ entrants naturally activate Bytefray's
> existing `alive` and `kill` scoring dimensions, creating strategic
> distinctions that 1v1 structurally suppresses?

More precisely, per alpha.3 §20's own unresolved question: in a 3-entrant
match, `resolve_winner`'s single-survivor special case requires *all but
one* entrant to be dead before it activates. With two survivors, two or
more entrants can have genuinely different `alive_ticks`/`kills` and the
match still falls through to ordinary score comparison — a state that is
architecturally *impossible* in a 2-entrant match, where any single death
immediately drops the alive count to exactly one and forces an
unconditional survival-based win before score is ever consulted.

## 3. Architecture audit (Phase 2)

Every layer of the execution stack was read directly against source, not
assumed from its docstrings. Result: **the entire native match execution,
scoring, statistics, termination, and core-capture stack is already
N-entrant-generic — already N-entrant safe, not merely theoretically so.**

| Component | File:function | Classification |
|---|---|---|
| `MatchEntrant`/`MatchRequest` | `match_service.py` | Already N-entrant safe — `entrants: tuple[MatchEntrant, ...]`, no fixed arity anywhere |
| `NativeMatchService.run` | `match_service.py:867-921` | Already N-entrant safe — validates kinds/uniqueness over the whole tuple; `entrants[0].kind` samples one representative kind only (valid because matches are homogeneous by construction), not a pair assumption |
| `canonical_match_id`/`_finalize_native_artifacts` | `match_service.py:576-798` | Already N-entrant safe — loops over `request.entrants`/`result.agents` with no length check |
| VM spawn loop | `match_service.py:839-845` (`_run_vm_match`) | Already N-entrant safe — `for entrant in request.entrants: kernel.spawn(...)` |
| VM tick loop | `match.py` (`MatchRunner.run`/`_execute_agents`/`_attribute_deaths`) | Already N-entrant safe — every loop is `for agent in state.agents` |
| Python tick loop (unsupervised) | `python_runtime.py` (`PythonEntrantController`) | Already N-entrant safe — `for slot, entrant in enumerate(entrants)` at construction, `for state in self.states` throughout |
| Python tick loop (supervised) | `supervised_runtime.py` | Already N-entrant safe — identical shape, `for state in self.states` |
| Scheduler | `scheduler.py:run_sequential_quota` | Already N-entrant safe — `Iterable[StateT]`, no arity assumption at all, by design (see its own module docstring) |
| Scoring | `scoring.py:ScoringPolicy` | Already N-entrant safe — every method is `for agent in agents` |
| Statistics | `statistics.py:StatisticsCollector` | Already N-entrant safe — same shape |
| Winner resolution | `results.py:resolve_winner` | Already N-entrant safe — operates on `Sequence[HasAgentIdentity]`; the single-survivor branch is `len(alive) == 1`, a general N-aware condition, not a pair check |
| Termination policy | `ruleset_policy.py:RulesetPolicy.resolve_termination` | Already N-entrant safe — takes only `alive_count`/`tick`/`max_ticks` as three integers, no entrant-count-specific branching |
| Core-capture mechanic | `python_runtime.py:apply_core_capture`/`_attribute_core_capture`/`_snapshot_core_owners`/`seed_core_ownership` | Already N-entrant safe — explicitly designed for N per alpha.1's own source comment ("owns zero core cells... deliberately... not one opponent owns all of it, so the rule stays well-defined if Bytefray ever supports more than two entrants") and `_attribute_core_capture`'s general tick-diff replay, verified below to correctly attribute across two independent, uncoordinated attackers |
| Replay/result schema | `replay.py`/`result_model.py` | Already N-entrant safe — `entrants`/`agents` are variable-length tuples throughout |

**The one explicit 2-entrant limitation found** is in the CLI/harness layer,
not the engine: `agent_test.py`'s `test_agent()` hardcodes exactly two
`MatchEntrant`s (`TESTED_AGENT_SLOT = "A"`, `OPPONENT_SLOT = "B"`), used by
`bytefray agents test` and, through it, `agent_evaluation._execute_cell`.
This was already known and documented in
[V2_0_ALPHA_ARCHITECTURE.md](V2_0_ALPHA_ARCHITECTURE.md) §3/§4 as a
harness-only fact, not an engine limitation. Critically, alpha.1/alpha.2/
alpha.3's own `run_evaluation.py` research drivers already bypass this
harness entirely, constructing `MatchEntrant`/`MatchRequest` tuples directly
and calling `NativeMatchService().run(...)` — the exact same production
execution boundary every other native match uses, just without going
through the 2-entrant-only CLI convenience wrapper. This alpha's own
research driver (§9 below) follows the identical precedent, extended to
three entrants.

**Classification: no accidental 2-entrant assumption was found anywhere in
the engine.** `agent_test.py`'s hardcoding is an explicit, intentional
2-entrant convenience shape for a CLI tool whose whole contract
(`--opponent`, `A_score`/`B_score` in `summary.json`, etc.) is inherently
binary by design — not evidence the engine cannot support more.

## 4. Winner/termination semantics with 3 entrants (Phase 3)

Read directly from source before writing any test, then verified
empirically (§8):

1. **The match continues after one of three entrants dies.**
   `RulesetPolicy.resolve_termination` only forces early termination at
   `alive_count == 0` (`ALL_AGENTS_DEAD`) or `alive_count == 1`
   (`LAST_AGENT_STANDING`). With 3 entrants and one death, `alive_count == 2`
   — neither condition — so the match runs on toward the tick limit exactly
   like an ordinary 2-survivor match would.
2. `resolve_winner` does **not** prematurely declare a winner at
   `alive_count == 2`: its only special case is `len(alive) == 1`.
3. There **is** a "one survivor remains" condition (`alive_count == 1`), but
   with 3 entrants it requires **two** deaths, not one — the direct N=3
   generalization of the 2-entrant rule (verified by
   `test_one_survivor_forces_win_regardless_of_score`).
4. No hardcoded "one death ends the match" assumption exists anywhere;
   `resolve_termination` only ever compares against `0` and `1`.
5. Tick-limit resolution:
   - **3 survivors**: ordinary score comparison across all three (verified,
     `test_three_alive_at_tick_limit_winner_decided_by_score`).
   - **2 survivors**: ordinary score comparison across **all three
     entrants, including the dead one** — the single-survivor override does
     not apply (`len(alive) == 2 != 1`). See §7's central finding.
   - **1 survivor**: forced win for the survivor, `LAST_AGENT_STANDING`,
     score never consulted — but this state is reached only after two
     deaths, not one.
6. Kills and deaths are counted correctly per entrant
   (`StatisticsCollector`/`ScoringPolicy` are unconditionally N-generic;
   verified directly in every test below).
7. Score comparison at tick-limit resolution runs across **every entrant
   passed to `resolve_winner`**, dead or alive — there is no alive-only
   filter in the score-fallback branch. Only the `len(alive) == 1` branch is
   alive-gated.
8. **Eliminated entrants can absolutely affect (and even determine) the
   final ranking** — see §7.
9. Tie handling is N-way safe: `resolve_winner`'s tie check
   (`top[0][1] > top[1][1]`) only compares the top two by score regardless
   of population size, and correctly returns `""` (`"tie"` at the
   `NativeMatchResult` layer) when they're equal, verified with 3 tied
   entrants (`test_three_way_tie_when_all_scores_equal`).

## 5. Core-capture semantics with 3 entrants (Phase 4)

Verified both by direct source reading and by dedicated tests (§8):

- **Correct victim, correct attribution, uninvolved third entrant
  unaffected**: `test_three_way_core_capture_basic_attribution_and_bystander_unaffected`
  — a bystander entrant with no relation to the attacker/victim pair keeps
  acting normally, accrues its own territory, and is never credited or
  debited by the other two's fight.
- **Attribution when multiple attackers independently contribute in the
  same tick** — an interaction with no 2-entrant analogue, since a
  2-entrant match can only ever have one possible attacker:
  `test_three_way_core_capture_attribution_credits_the_entrant_that_completes_it`
  has two independent attackers each remove exactly half of a victim's
  8-cell core in the same tick. `_attribute_core_capture` replays that
  tick's diffs in true scheduler order (entrant order in the `entrants`
  tuple); the attacker whose write happens to take the *last* remaining
  cell gets sole kill credit, even though the other attacker contributed
  identically. This is a genuine **kill-stealing** dynamic, confirmed both
  in a controlled scripted test and later in real reference-agent play
  (§9's match 8/11 pair, §12).
- **Match continuation when more than one entrant remains after a
  capture**: both the basic and multi-attacker tests run to the full tick
  limit after the capture — the match does not end merely because one of
  three entrants died.
- No change to the capture *semantic itself* ("owns zero cells of its own
  core") was needed or made — alpha.1 already phrased it in an
  N-entrant-compatible form specifically so this would hold (§2 of
  [V2_0_ALPHA1_EVALUATION.md](V2_0_ALPHA1_EVALUATION.md)), and this alpha
  confirms that design choice was correct.
- **A previously-undocumented side effect, found while designing the 3-way
  bystander test**: `seed_core_ownership` runs unconditionally for *every*
  entrant under `bytefray-rules-2-alpha1`, not only ones cast as a
  "victim" — a bystander with no involvement in any fight still starts with
  8 pre-owned core cells that count toward its own territory score. This
  is the same core-seeding side effect alpha.1 §6/§8 already documented for
  the 2-entrant case, now confirmed to apply identically, and uniformly, to
  every entrant regardless of role in a 3-entrant match.

## 6. New Ruleset ID decision (Phase 5)

**No new Ruleset ID was created.** `bytefray-rules-2-alpha1` is reused
exactly as alpha.1–alpha.3 left it — this alpha varies only the *entrant
count* passed to the existing, unmodified engine and ruleset, not any game
rule. Both the focused tests (§8) and the exploratory matrix (§9) also
include one explicit 3-entrant `bytefray-rules-1` control
(`test_three_entrant_match_runs_under_ruleset_v1_unchanged`) confirming
N-entrant support is a general engine property, not something gated behind
the experimental Ruleset. `bytefray-rules-2-alpha1` was used for the
primary experiment only because it is the one mechanism in this engine that
can eliminate a Python entrant deterministically and repeatably before the
tick limit — necessary to actually exercise the "one dies, others continue"
condition this alpha studies, not because eliminating entrants requires it
in general (an ordinary `HALT` under Ruleset v1 works identically, and is
exactly what several focused tests below use).

## 7. The central structural finding: dead entrants can win 3-entrant matches

This is the single most important finding of this alpha, established first
analytically from §4's source reading, then proven with a deterministic
scripted test, then **confirmed in real, unscripted reference-agent
gameplay** (§9).

With exactly two of three entrants alive at the tick limit,
`resolve_winner`'s survival override (`len(alive) == 1`) never fires, so the
match falls through to ordinary score comparison across **all** entrants —
including the dead one. `ScoringPolicy.score_territory` has no alive gate
(confirmed directly, and already noted for the 2-entrant case in
[V2_0_ALPHA3_SCORING_SENSITIVITY.md](V2_0_ALPHA3_SCORING_SENSITIVITY.md) §4),
so a dead entrant's previously-claimed territory keeps contributing to its
score every remaining tick after death, exactly as if it were still alive
and expanding.

`test_two_alive_at_tick_limit_dead_entrant_can_still_win_by_score` proves
this in a fully controlled, deterministic scenario: an entrant claims 32
cells over 4 ticks, then halts. Two NOP entrants survive the full 10-tick
budget. The dead entrant's score (276, dominated by 32 owned cells accruing
every remaining tick) exceeds both survivors' scores (10 each) by a wide
margin — **the dead entrant is declared the match winner.**

This is not a contrived-only result. The real 12-match exploratory matrix
(§9) produced two core captures, and **in both, the engine's actual
`result.winner` field named the entrant that had just been core-captured**
— not the entrant that captured it, and not the bystander. This directly
answers Phase 3's question #9 ("can eliminated entrants still affect result
ranking?"): yes, dramatically — an eliminated entrant can be crowned the
outright winner of a match it did not survive.

This is a genuinely new, N>2-only structural consequence, not a bug and not
a regression: in a 2-entrant match, any single death immediately forces
`alive_count == 1` and an unconditional survivor win
([V2_0_ALPHA3_SCORING_SENSITIVITY.md](V2_0_ALPHA3_SCORING_SENSITIVITY.md)
§8), so a dead entrant winning on points is architecturally impossible
there. With three (or more) entrants, it is not merely possible — this
alpha found it happening in a small, otherwise ordinary sample of real
strategic play, not an edge case that had to be engineered to appear.

## 8. Deterministic 3-way start placement (Phase 6)

No existing N-way placement convention was found in the engine (`start` is
an arbitrary per-entrant configuration value; alpha.1–alpha.3's own
convention — subject at `0`, opponent at `arena_size // 2` — is itself just
a research-driver choice, not an engine default). Per the governing task,
this alpha adopts the direct 3-way generalization: deterministic thirds of
the arena.

For the default `arena_size = 4096`:

| Seat | Start address |
|---|---:|
| A | `0` |
| B | `1365` (`4096 // 3`) |
| C | `2730` (`(2 * 4096) // 3`) |

`CORE_SIZE = 8` cores at these three addresses (`[0,8)`, `[1365,1373)`,
`[2730,2738)`) do not overlap, so no pathological shared-core spawn
condition (alpha.1 §2's one unattributable edge case) occurs at this
placement. No spawn-position sweep was performed, per the governing task's
explicit exclusion — only this one fixed layout was used throughout.

## 9. Focused characterization tests (Phase 7)

`engine/tests/test_v2_alpha4_multi_entrant.py`, 10 tests, all passing (0
production code changes). Covers, with deterministic scripted agents
mirroring `test_ruleset_v2_alpha1.py`'s established pattern:

1. `test_three_entrants_all_load_and_act_and_own_territory` — execution:
   three Python entrants load, all receive turns, deterministic scheduling,
   ownership accounting includes all three.
2. `test_match_continues_after_one_of_three_is_eliminated` — **the critical
   acceptance test**: B halts on its first action; the match runs the full
   10-tick budget regardless (`termination_reason == "tick_limit"`, not
   `last_agent_standing`), and final `alive_ticks` is `{A: 10, B: 0, C: 10}`
   — genuinely divergent, not merely "not identical."
3. `test_three_way_core_capture_basic_attribution_and_bystander_unaffected`
   — correct victim/attacker, bystander provably unaffected, match
   continues to the tick limit after the capture.
4. `test_three_way_core_capture_attribution_credits_the_entrant_that_completes_it`
   — two independent attackers, kill credited only to whichever completes
   the capture (§5's kill-stealing finding).
5. `test_three_alive_at_tick_limit_winner_decided_by_score` — 3 survivors,
   ordinary N-way score comparison.
6. `test_two_alive_at_tick_limit_dead_entrant_can_still_win_by_score` — 2
   survivors, §7's central finding, deterministically reproduced.
7. `test_one_survivor_forces_win_regardless_of_score` — 1 survivor (via two
   deaths), forced win regardless of the dead entrants' scores.
8. `test_three_way_tie_when_all_scores_equal` — N-way tie handling.
9. `test_replay_and_result_artifacts_represent_all_three_entrants` —
   replay header, tick-zero snapshot, and `result.json` all correctly carry
   all three entrant IDs and the resolved Ruleset identity.
10. `test_three_entrant_match_runs_under_ruleset_v1_unchanged` — N-entrant
    support is not gated behind the experimental Ruleset.

**Proof of unequal `alive_ticks`**: test 2 above, `{A: 10, B: 0, C: 10}`.

**Proof of unequal `kills`**: test 4 above, one attacker credited with 1
kill, the other with 0, for functionally identical contribution.

Both proofs persist into final, ordinary `NativeAgentResult`/`result.json`
data — no special instrumentation was needed to observe them.

## 10. Case classification (Phase 8)

**Case A — the engine already supports 3 entrants.** No production code
was changed anywhere in this alpha. `git diff -- engine/src/battle_engine`
is empty. Every finding above was obtained by exercising the existing,
unmodified engine through its existing public execution boundary
(`NativeMatchService`), exactly as alpha.1–alpha.3's own research drivers
already did for two entrants.

## 11. Proof experiment (Phase 9)

§9's focused test suite already constitutes the required scripted proof:
test 2 demonstrates divergent `alive_ticks` with continued play after an
elimination; test 4 demonstrates divergent `kills`. Both are deterministic,
reproducible, and use the exact production execution path. The core
hypothesis was **not falsified** — proceeding to the exploratory matrix was
therefore justified.

## 12. Exploratory 3-way matrix (Phase 10)

`runs/v2_0_alpha4_multi_entrant/run_evaluation.py`, executed directly
through `NativeMatchService`.

- **Agents (4):** `claimer`, `hunter` (existing Ruleset-v1 starters),
  `core_seeker`, `reactive_core_defender` (v2.0.0-alpha reference agents) —
  the governing task's recommended set, without the optional fifth agent
  (kept deliberately minimal per the governing task's "compact but
  strategically diverse" instruction).
- **Determinism confirmed, not assumed, before choosing the seed set**:
  direct source inspection found `claimer` never calls any method on
  `context.rng` (its own reset comment says so explicitly: "unused by this
  strategy"), and `hunter` stores `context.rng` but never calls a method on
  it either — both are fully deterministic in practice. `core_seeker` and
  `reactive_core_defender` were already documented as RNG-independent in
  alpha.1/alpha.2. **All four agents in this matrix are therefore fully
  deterministic given a fixed matchup/placement** — a second seed would
  reproduce byte-for-byte identical results, so exactly **one seed** (`1`)
  was used throughout, per the governing task's explicit instruction not to
  manufacture pseudo-replication once determinism is proven.
- **Trios:** every unordered 3-agent combination, `C(4,3) = 4`.
- **Seat rotations:** 3 cyclic assignments per trio (each agent occupies
  each of the three start slots exactly once across the three rotations) —
  the governing task's stated minimum.
- **Placement:** the deterministic thirds from §8 (`0`, `1365`, `2730`).
- **Ruleset:** `bytefray-rules-2-alpha1`. **Config:** unchanged defaults
  throughout (`arena_size=4096`, `instr_per_tick=8`, `max_ticks=200`,
  default `Config().weights`) — never varied, per the governing task's
  Phase 11.
- **Total: 4 trios × 3 rotations × 1 seed = 12 matches.** Completed in
  ~1.2s, 0 infrastructure failures.

Raw per-match records: `runs/v2_0_alpha4_multi_entrant/raw_matches.json`.
Phase 12/13 analysis: `runs/v2_0_alpha4_multi_entrant/analyze.py` →
`analysis_summary.json` (both untracked local scratch, per the existing
`runs/` `.gitignore` precedent established in alpha.1–alpha.3 — this
document is the durable, committed record).

## 13. Alive/kill activation statistics (Phase 12)

| Metric | Result |
|---|---:|
| Matches with a core capture | 2 / 12 (16.7%) |
| Matches with divergent `alive_ticks` among the three entrants | 2 / 12 (16.7%) — the same 2 |
| Matches with divergent `kills` | 2 / 12 (16.7%) — the same 2 |
| Matches where the eventual match winner was dead at match end | **2 / 12 (16.7%)** — both capture matches |

**Every match with a capture shows both `alive_ticks` and `kills`
divergence** — the raw metrics genuinely activate exactly when the
mechanism predicted they would (§4/§7), never independently of a capture,
consistent with §4's structural argument that only a death can produce
divergence in this population.

**Kill-differentiation persistence**: in both capture matches, the
attacking entrant (`core_seeker` in both cases) remained alive and in
competition afterward (`alive: true` through the tick limit in both), and
the credited kill (+5 points) is a real, exact, persisted field in the
final `result.json` — not a transient mid-match event.

## 14. Score decomposition and counterfactual rankings (Phase 13)

For all 12 matches, `bucket_sum` was recovered per entrant by the same
exact algebraic inversion alpha.3 §6 validated
(`bucket_sum = (score - alive_ticks·1.0 - kills·5.0) / 1.0`, using the
confirmed-unchanged default weights) — pure arithmetic over already-exact
recorded fields, no re-execution. Five counterfactual rankings were then
computed per match: default (full score), territory-only, territory+alive,
territory+kills, alive+kills.

| Measurement | Result |
|---|---:|
| Matches where default ranking's top entrant differs from territory-only's | **0 / 12** |
| Matches where the *full* default order differs from the *full* territory-only order | **0 / 12** |
| Matches where adding `alive` changes the top-ranked entrant (relative to territory-only) | **0 / 12** |
| Matches where adding `kills` changes the top-ranked entrant | **0 / 12** |
| Matches where both matter | **0 / 12** |

**This is the sharpest, most important quantitative result of this alpha.**
Raw activation (§13) is unambiguous and repeatable: `alive_ticks` and
`kills` do numerically diverge, and they do so exactly when the
architecture predicts. But **functional activation — those differences
actually changing which entrant tops the ranking — was not observed in this
12-match sample, not even once, including in the two matches that actually
had a capture.** In both capture matches, territory alone already
determines the identical ranking the full default score produces; the
killer's `+5` kill bonus and the up to ~41-tick `alive_ticks` gap are both
dwarfed by the multi-hundred-point territorial lead the (eventually dead)
victim had already accumulated before dying.

This does **not** repeat alpha.3 §8's algebraic proof — that proof was
specific to the 2-entrant, single-death-forces-termination structure and
does not apply here; this alpha's result is an **empirical observation over
a deliberately small sample**, not a closed-form impossibility result. It
is entirely plausible that an earlier capture (leaving more remaining ticks
for a territorial gap to close, or for a killer's accumulated `alive`/`kill`
lead to compound) would show a different outcome — both captures in this
matrix happened late (tick 159 and tick 165 of 200), leaving only 35-41
ticks for anything to change after the fact. This is flagged explicitly as
an open question in §20, not glossed over.

## 15. Strategic questions, answered directly (Phase 14)

1. **Does eliminating one opponent while another remains produce real kill
   differentiation?** Yes — confirmed in both real captures and the
   scripted proof.
2. **Does early elimination produce real alive-time differentiation?**
   Yes, mechanically identical to (1) — but "early" did not occur in this
   sample; both real captures were late (tick ~160/200).
3. **Do those differences affect scores materially?** In absolute terms,
   yes (kill: +5; alive_ticks gap: up to ~41 points at default weight 1.0).
   Relative to the territorial gaps observed (several hundred points), no.
4. **Do they affect winner/ranking under default weights?** No — §14,
   0/12.
5. **Does Reactive Core Defender gain any meaningful value from longer
   survival?** It survived every one of its 6 matches (100%, never
   captured — consistent with alpha.2's finding against this exact
   opponent), but never won a single match either — survival did not
   translate into competitiveness, exactly reconfirming alpha.2 §11's
   finding in the 3-way format.
6. **Does Core Seeker gain meaningful value from actual kills?** It scored
   2 kills across its 9 matches but won 0/12 — the kill bonus did not move
   it into contention, consistent with alpha.1/alpha.3's finding that
   Core Seeker's own overall win rate is not primarily kill-driven.
7. **Does Claimer gain a third-party expansion advantage while other
   entrants fight?** Not clearly demonstrated in this sample: the
   bystander in both capture matches was `reactive_core_defender`, whose
   own strategy trades expansion for defense — it remained the lowest
   scorer in both capture matches rather than capitalizing on the fight.
   Whether a more aggressive bystander (e.g. a second unrestricted
   expander) would show a clearer "free expansion while others fight"
   effect is untested here and is flagged as an open question (§20).
8. **Does Hunter exploit or suffer from the richer interaction?** Hunter
   won the most matches overall (6/12) and was also core-captured once (in
   the one seat found vulnerable, §16) — no unique interaction pattern
   beyond the general seat-sensitivity finding below.
9. **Does any strategy become an obvious 3-way solution?** No — the same
   relative ordering as alpha.1–alpha.3 held (Claimer/Hunter strong,
   Core Seeker/Reactive Defender weak by raw win rate); no new dominant
   strategy emerged.
10. **Does 3-way competition introduce strategic effects absent from every
    1v1 experiment so far?** Yes, directly: (a) match continuation past an
    elimination (§4), (b) a dead entrant winning the match outright (§7),
    (c) a seat-dependent capture geometry with no 2-entrant analogue (§16),
    and (d) a third-party interference effect where the identity of an
    uninvolved bystander changed whether an otherwise-identical
    attacker/victim pairing succeeded (§16).

## 16. Third-party effects, seat sensitivity, and one new emergent finding (Phase 15/20)

**Seat sensitivity, directly analogous to alpha.2 §10's orientation finding,
now in 3-way form**: both real captures in this matrix occurred with
`core_seeker` at seat **C** (`2730`) and the victim at seat **B**
(`1365`) — never with the victim at seat A. This tracks
`CoreSeekerAgent.reset`'s fixed absolute scan schedule
(`scan_cursor = arena_size // 3 = 1365` on the very first scan, regardless
of the seeker's own start address) landing exactly on seat B's core
address rather than seat A's, mirroring exactly how alpha.2 found Core
Seeker's fixed schedule made captures orientation-dependent rather than a
property of "finding cores" in general.

Win counts by seat across the 12 matches: A = 3, B = 3, C = 5, tie = 1 —
seat C won somewhat more often in this small sample; not concluded to be
significant at n=12, flagged for a larger future matrix rather than
over-interpreted here.

**A new finding with no 1v1 analogue: a third entrant's ordinary activity
can determine whether an unrelated capture succeeds.** Directly verified,
not inferred: with `core_seeker` fixed at seat C and `hunter` fixed at seat
B (identical attacker, identical victim, identical seats), the capture
**succeeded when `reactive_core_defender` occupied seat A, and failed when
`claimer` occupied seat A instead** — the only variable that changed
between the two matches was which agent held the third seat.

```
seeker@C, third(A)=claimer,                  victim(B)=hunter   -> captured=False
seeker@C, third(A)=reactive_core_defender,    victim(B)=claimer  -> captured=True
seeker@C, third(A)=reactive_core_defender,    victim(B)=hunter   -> captured=True
```

Both agents that were fixed at C (`core_seeker`) and at B are fully
deterministic given the arena's byte contents, and Core Seeker's detection
heuristic works purely off arena *content* (`_looks_foreign`), not entrant
identity or position. The most direct explanation, not independently
re-verified by replay tracing in this alpha: Claimer's own wide,
fast-expanding sweep from seat A plausibly overwrites cells along Core
Seeker's scan/expand trajectory before it reaches them, altering what Core
Seeker reads and interfering with its foreign-detection or assault-anchor
logic — an effect Reactive Core Defender's much more conservative sweep
does not produce. This is recorded as an interesting, genuine strategic
consequence of N>2 play — a form of **incidental, uncoordinated
interference**, not kingmaking (no agent here is "helping" another on
purpose) and not an implementation defect (nothing malfunctioned; the
mechanism is exactly the same content-based detection alpha.2 §3 already
documented). It is not resolved further in this alpha, consistent with the
governing task's instruction not to immediately "fix" emergent behavior.

**Other effects explicitly checked for and not found in this sample**: no
kingmaking (no agent's presence deterministically handed a win to a
specific other agent independent of its own play), no target-selection
artifact beyond the seat-C-attacks-seat-B pattern already explained, and no
scheduler-order pathology beyond the already-documented, expected
last-writer-wins tick-diff replay (§5).

## 17. Artifact/replay/result compatibility (Phase 21 item 10)

Fully verified by
`test_replay_and_result_artifacts_represent_all_three_entrants`: the replay
header's `entrants` tuple, the tick-zero snapshot's `agents`, and the
persisted `result.json`'s `entrants` list all correctly contain exactly the
three participating entrant IDs, and both the replay header's and result
envelope's `ruleset_id` correctly record the resolved identity
(`bytefray-rules-2-alpha1` when requested). No schema version bump was
needed or made — the existing variable-length `entrants`/`agents`
structures already accommodated three entrants with zero changes.

## 18. 1v1 compatibility (Phase 22)

No production code was changed anywhere in this alpha (§10), so no 1v1
regression is possible by construction. This was verified, not merely
assumed — see §19 for the full regression run.

## 19. Regression qualification (Phase 22)

| Check | Result |
|---|---|
| New 3-entrant focused tests | 10 / 10 passed |
| `test_ruleset_v2_alpha1.py` (alpha.1) | 19 / 19 passed |
| `test_v2_alpha1_reference_agents.py` (alpha.1) | 9 / 9 passed |
| `test_v2_alpha2_reactive_defender.py` (alpha.2) | 15 / 15 passed |
| `test_ruleset_v1_equivalence.py` | 8 / 8 passed |
| `test_ruleset_policy.py` | passed |
| `test_evaluation_history_comparison.py` | passed |
| Full `pytest` | **1531 total / 1525 passed / 6 skipped / 0 failed** (1521/1515/6/0 baseline + this alpha's 10 new tests, all passing) |
| Ruff (repo-wide) | clean, 0 errors |
| mypy (`engine/src/battle_engine`) | clean, 69 files |
| mypy (`client/src/battle_client`) | clean, 10 files |
| `git diff -- engine/src client/src` | empty (no production code changed) |

## 20. Unresolved questions (Phase 21 item 47)

- Would an **earlier** capture (rather than the tick ~160/200 timing
  observed in both real captures here) leave enough remaining ticks for
  `alive`/`kill` to actually change a ranking that territory alone would
  otherwise decide? Not tested — would require either a larger matrix or a
  deliberately weaker/slower Core Defender-style victim to force an earlier
  capture, both out of this alpha's deliberately limited scope.
- Does a more aggressive (rather than defensive) third-party bystander show
  a clearer "free expansion while two others fight" effect than
  Reactive Core Defender did in this sample (§15 item 7)? Not tested.
- Is the seat-C-favors-capture pattern (§16) a genuine property of this
  specific 3-way placement's interaction with Core Seeker's fixed scan
  schedule, or would it invert/disappear under a different (still
  deterministic, still non-swept) 3-way layout? Not tested — placement was
  held fixed throughout, per the governing task.
- Would a 4th or 5th entrant change any of these findings qualitatively
  (e.g. do multiple simultaneous captures become likely, testing whether
  `_attribute_core_capture`'s "more than one entrant captured in the same
  tick" case — architecturally supported, per §3's audit — actually
  materializes in real play)? Explicitly out of scope for this alpha (the
  governing task scoped this to "3 or more," and 3 was sufficient to answer
  the core question).
- The third-party interference effect (§16) was observed but not traced to
  a specific mechanism via replay inspection; a definitive causal
  explanation (rather than the plausible one offered) is open.

## 21. Success/rejection assessment (Phase 17)

Evidence supporting continuation, present:

- An entrant can be eliminated while play continues (§4, directly proven).
- `alive_ticks` genuinely diverges (§9/§13, both scripted and real play).
- `kills` genuinely diverges (§9/§13, both scripted and real play).
- No severe architecture pathology appeared — zero production code changes
  were needed, and 0/12 exploratory matches had an infrastructure failure.
- 1v1 behavior is unaffected by construction (§18).
- Strategically distinct, genuinely new behavior emerged (§7's dead-winner
  finding, §16's third-party interference finding) — not previously
  observable in any 1v1 experiment.

Evidence against, present and not minimized:

- **The existing default score never once used the newly-activated
  `alive`/`kill` divergence to change a ranking outcome in this sample**
  (§14, 0/12 on every counterfactual-ranking measure). Raw activation is
  real; functional activation was not observed.
- Reactive Core Defender still received no competitive value from surviving
  every match (§15 item 5) — exactly reconfirming alpha.2's finding, now in
  the 3-way format.
- Seat/placement sensitivity persists and, if anything, is now compounded
  by a genuine third-party interference effect (§16) not present at all in
  1v1 play.

**Verdict: qualified positive, not an unqualified "yes."** The core
architectural half of the hypothesis is unambiguously confirmed: 3-entrant
play is fully supported by the existing engine with zero production
changes, elimination-with-continuation is real, and `alive`/`kill`
genuinely stop being mathematically inert once one entrant can die while
two others remain. The *scoring-relevance* half of the hypothesis —
whether that newly-real divergence actually **matters** to competitive
outcomes under the existing default weights — is **not yet demonstrated**
in this deliberately small (12-match) sample, though it was not falsified
either: the sample size is too small, and both observed captures happened
too late in the match, to distinguish "structurally can't matter" from
"didn't happen to matter in these 12 matches." This is honestly reported as
an open, not a closed, question — unlike alpha.3's algebraic proof, nothing
here rules out a larger sample (or a placement/timing more favorable to
early captures) showing real ranking-changing leverage.

## 22. Recommendation

**Continue multi-entrant work, but as a targeted measurement question, not
a scoring-tuning pass** (per the governing task's Phase 18 exclusion, still
respected here). The single most direct next step implied by this alpha's
own evidence is a **larger, still-controlled 3-way matrix specifically
designed to produce earlier captures** (e.g. deliberately including a
weaker/slower defender-style victim, or measuring at a range of capture
timings rather than relying on incidental timing from a small agent set) to
determine whether §14's "0/12, always" result is a real ceiling on
`alive`/`kill`'s influence in this scoring model, or an artifact of this
sample's specific (late) capture timings. Do not vary weights in that
follow-up either — the question is still "does the existing model ever use
this activated dimension," not "what weight would make it matter."

## 23. Recommended next Bytefray v2 alpha prompt

Given this alpha's own finding — raw activation of `alive`/`kill` is real
and reproducible in 3-way play, but this sample never observed it changing
an actual ranking — the most direct evidence-driven next step is
**alpha.5**, scoped narrowly to: hold every mechanic and Ruleset identical
(no new weights, no new Ruleset, no arena/placement sweep beyond what
alpha.4 already fixed), and specifically construct a modest 3-way matrix
(still not full-scale) engineered to produce captures earlier in the match
(varied timing, not varied weights or mechanics) to determine whether
`alive`/`kill` can ever change a default-weighted ranking outcome in *any*
3-entrant configuration this engine supports — closing alpha.4's central
open question (§20 item 1) before any future work considers whether
`Config.weights` deserves revisiting in a multi-entrant context at all.
