# Bytefray v2.0.0-alpha.4.1 — Winner-Semantics Hardening

This is a targeted correctness pass, not a mechanic or scoring change: it
implements the smallest fix necessary to enforce the invariant

> **An entrant that is dead at the end of a match cannot win, regardless of
> accumulated score.**

as the natural N-entrant extension of Bytefray's existing 1v1 semantics,
where a surviving entrant already defeats a dead one regardless of score.
`CORE_SIZE`, arena size, tick/instruction budget, scoring weights, every
mechanic, and every existing starter/reference agent are held byte-for-byte
identical to alpha.1–alpha.4. No new Ruleset ID is introduced (§9).

Branched from the verified alpha.4 baseline, commit
`c9ad2b8c6a126db8a6931aec2a4bc789a8ea546b` on `v2.0-development` (`main`
unchanged at `5593d287f95a24996bb3b105befbc625a00795db` throughout).

## 1. Verified starting state (Phase 1)

Confirmed directly, not assumed:

- Branch: `v2.0-development`.
- HEAD at start of this work: `c9ad2b8c6a126db8a6931aec2a4bc789a8ea546b`.
- Working tree: clean.
- `main`: `5593d287f95a24996bb3b105befbc625a00795db`, unchanged.
- Local branch was 3 commits ahead of `origin/v2.0-development`; nothing
  pushed.
- `docs/V2_0_ALPHA4_MULTI_ENTRANT_FEASIBILITY.md`, `results.py`
  (winner resolution), `ruleset_policy.py` (termination policy and its own
  module docstring on winner-resolution ownership), `scoring.py`,
  `test_v2_alpha4_multi_entrant.py`, and `test_match_services.py`'s existing
  `resolve_winner` unit test were all read directly before any code was
  changed.
- Regression baseline reproduced exactly as documented: pytest **1531
  total / 1525 passed / 6 skipped / 0 failed**; Ruleset-v1 equivalence 8/8;
  Ruff clean repo-wide; mypy clean for both `engine` (69 files) and
  `client` (10 files).

## 2. The alpha.4 discovery (recap)

alpha.4 found that with exactly two of three entrants alive at the tick
limit, `resolve_winner`'s single-survivor override (`len(alive) == 1`)
never fires, so the match fell through to ordinary score comparison across
**all** entrants, including dead ones. `ScoringPolicy.score_territory` has
no alive gate, so a dead entrant's previously-claimed territory kept
contributing every remaining tick after its own death. In alpha.4's real
12-match exploratory matrix, this happened in both matches that produced a
core capture: the engine's actual `result.winner` named the entrant that
had just been core-captured, not either of the two entrants that survived
to the end.

## 3. Pre-fix `resolve_winner` behavior (Phase 2)

Read directly from `engine/src/battle_engine/results.py` before any change:

```python
def resolve_winner(agents, score, win_mode) -> str:
    alive = [agent.agent_id for agent in agents if agent.alive]
    mode = (win_mode or "score_fallback").lower()
    if len(alive) == 1:
        return alive[0]
    if mode == "survival":
        return ""
    if score:
        top = sorted(score.items(), key=lambda item: (-item[1], item[0]))
        if len(top) == 1 or top[0][1] > top[1][1]:
            return top[0][0]
    return ""
```

Characterized exactly, per entrant count:

**1v1**: with only two entrants, any single death immediately produces
`len(alive) == 1`, forcing the survivor to win before score is ever
consulted. Both alive → ordinary 2-way score comparison. Both dead is not
reachable in practice (Ruleset v1 always has at least one entrant standing
or reaches the tick limit with both alive), but is representable: `score`
comparison runs over both dead entrants. Ties return `""`.

**3 entrants**: 3 alive → ordinary 3-way score comparison, no filtering.
2 alive / 1 dead → `len(alive) == 2 != 1`, override does not fire; score
comparison runs over **all three**, so the dead entrant's score can win
outright — this is the bug. 1 alive / 2 dead → override fires
(`len(alive) == 1`), forced win regardless of score. 0 alive (representable
via a scripted all-HALT scenario) → falls through to full 3-way score
comparison. Ties among survivors were not actually survivor-scoped: a tie
check only ever compared the top two *scores* in the full list, so a
non-tied dead entrant with the single highest score could still defeat a
genuine tie between two survivors (this exact shape is now covered by
`test_three_entrants_surviving_tie_unaffected_by_dead_entrants_score`).

**N entrants**: `resolve_winner` already operated on `Sequence[
HasAgentIdentity]` with no arity assumption anywhere — the bug was never a
3-entrant special case, it was a property of the score-fallback branch at
any entrant count above 2 (confirmed post-fix with a dedicated 4-entrant
test, §7).

## 4. Architecture location and ruleset scope (Phase 6)

`battle_engine.results.resolve_winner` is the **one authoritative
winner-resolution implementation**, called identically by all three
runtimes regardless of Ruleset ID:

- VM: `core.py:141` (`Kernel.run`)
- Unsupervised Python: `python_runtime.py:1001`
- Supervised Python: `supervised_runtime.py:445`

`ruleset_policy.py`'s own module docstring is explicit that this is
deliberate: *"Scheduling and match termination decision/reason...have a
single shared implementation... Scoring, statistics, and winner resolution
are not yet Ruleset-policy-owned."* `RulesetPolicy` exposes only
`run_scheduler`/`resolve_termination`; it has no method related to winner
resolution, and nothing routes `resolve_winner` through it for either
`RULESET_V1` or `RULESET_V2_ALPHA1`.

**Conclusion: winner eligibility is universal, shared engine semantics, not
Ruleset-specific semantics.** The governing task's own guidance applies
directly here: *"If existing winner semantics are intentionally shared
engine invariants, a generic N-entrant correction may be cleaner."* The fix
is therefore made once, in `results.resolve_winner`, and applies
identically under Ruleset v1 and `bytefray-rules-2-alpha1` alike — not
routed through `RulesetPolicy`, and no new seam was added to it.

## 5. The survivor-eligibility rule (Phase 3)

```python
def resolve_winner(agents, score, win_mode) -> str:
    alive = [agent.agent_id for agent in agents if agent.alive]
    mode = (win_mode or "score_fallback").lower()
    if len(alive) == 1:
        return alive[0]
    if mode == "survival":
        return ""
    eligible = set(alive) if alive else {agent.agent_id for agent in agents}
    if score:
        top = sorted(
            (item for item in score.items() if item[0] in eligible),
            key=lambda item: (-item[1], item[0]),
        )
        if top and (len(top) == 1 or top[0][1] > top[1][1]):
            return top[0][0]
    return ""
```

- **Exactly one entrant alive**: unchanged — that entrant wins outright,
  before score is ever consulted. This branch is untouched by the fix.
- **Two or more entrants alive**: `eligible` is exactly the alive set.
  Score comparison (and its existing tie rule — top two scores equal
  returns `""`) runs only across `eligible`. A dead entrant's score is
  never inspected by this branch, no matter how high.
- **Zero entrants alive**: `eligible` falls back to every entrant, dead or
  alive — byte-for-byte the same behavior as before this fix. See §6 for
  why.

This is a five-line change with no new branch, no new mode, and no new
data. It generalizes the exact same "survival beats score" principle the
single-survivor override already encoded, to the case where more than one
entrant survives.

## 6. The zero-survivor case (Phase 3)

Deliberately **not** given its own special rule. The task distinguishes
"dead entrants cannot win when survivors exist" from "dead entrants can
never be returned as winner under any circumstances," and only the former
is the governing invariant. With zero survivors there is, by definition, no
survivor to prefer — inventing a new all-dead-specific tiebreak would be
unmotivated by any source evidence and outside this alpha's scope. The
existing, unmodified fallback (ordinary score comparison across the full
entrant set) is reused exactly as it already behaved pre-fix. Verified by
`test_1v1_both_dead_falls_back_to_full_score_comparison` and
`test_three_entrants_zero_survivors_falls_back_to_full_score_comparison`.

## 7. Focused tests (Phase 7)

`engine/tests/test_v2_alpha4_1_winner_semantics.py`, 12 tests, all passing:

| Test | Scenario | Result |
|---|---|---|
| `test_1v1_both_alive_score_decides` | 1v1, both alive, score differs | higher score wins |
| `test_1v1_both_alive_score_tie` | 1v1, both alive, tied | `""` |
| `test_1v1_one_dead_survivor_wins_regardless_of_score` | 1v1, one dead with a far higher score | alive entrant wins (both modes) |
| `test_1v1_both_dead_falls_back_to_full_score_comparison` | 1v1, both dead | full-set score comparison, incl. tie |
| `test_1v1_survival_mode_never_uses_score_between_two_survivors` | 1v1, `survival` mode, both alive | `""` |
| `test_three_entrants_one_dead_survivor_wins_despite_lower_score` | A alive 100, B alive 90, C dead 1000 | `A` |
| `test_three_entrants_two_dead_lone_survivor_forced_win` | A alive 1, B dead 1000, C dead 2000 | `A` |
| `test_three_entrants_multiple_survivors_dead_entrant_excluded` | A alive 100, B alive 200, C dead 1000 | `B` |
| `test_three_entrants_surviving_tie_unaffected_by_dead_entrants_score` | A alive 200, B alive 200, C dead 1000 | `""` (tie) |
| `test_three_entrants_zero_survivors_falls_back_to_full_score_comparison` | all three dead | full-set comparison, incl. tie |
| `test_four_entrants_two_alive_two_dead_highest_surviving_score_wins` | A alive 50, B alive 80, C dead 500, D dead 300 | `B` |
| `test_realistic_three_way_core_capture_dead_victim_with_highest_score_does_not_win` | full `NativeMatchService` match, §8 | `B` (survivor), not the dead victim |

`test_match_services.py::test_winner_resolution_preserves_survival_score_fallback_and_ties`
(pre-existing, unmodified) continues to pass unchanged — direct proof the
1v1 branch was untouched.

## 8. N-entrant genericity (Phase 7)

`test_four_entrants_two_alive_two_dead_highest_surviving_score_wins` proves
the fix is genuinely N-generic, not a 3-entrant special case: with two
dead entrants each individually outscoring both survivors (500 and 300
vs. 50 and 80), the higher-scoring survivor (`B`, 80) still wins. The
implementation itself contains no entrant-count branching at all — `alive`,
`eligible`, and the score comparison are all computed generically over
`Sequence[HasAgentIdentity]`/`ScoreMap`, exactly as the pre-fix code already
was (per alpha.4 §3's own audit).

## 9. Core-capture integration test (Phase 8)

`test_realistic_three_way_core_capture_dead_victim_with_highest_score_does_not_win`
reproduces the actual alpha.4 failure mode end-to-end through
`NativeMatchService` under `bytefray-rules-2-alpha1`: a victim claims 40
cells of territory over 5 ticks, is then core-captured by an attacker that
deliberately waits until the victim has something worth taking (mirroring
the ~tick-160-of-200 late-capture timing alpha.4's own real matches had),
while a bystander plays on unaffected. Verified directly:

- The victim is genuinely dead (`alive is False`,
  `termination_reason == "core_captured"`, `deaths == 1`).
- The attacker's kill attribution is correct (`kills == 1`).
- Both survivors remain alive to the match's normal termination
  (`termination_reason.value == "tick_limit"`, `ticks_run == 20`).
- The dead victim's score is preserved, unmutated, and genuinely the
  highest of the three (`victim.score > attacker.score` and
  `victim.score > bystander.score`) — not a near-tie, since its 40
  claimed cells keep scoring every tick after death exactly as alpha.4
  documented.
- The winner is **not** the dead victim (`result.winner != "A"`), and is
  in fact the attacker (`result.winner == "B"`), the higher-scoring of the
  two actual survivors.

## 10. Re-evaluating the two real alpha.4 dead-winner matches (Phase 9)

Both located in `runs/v2_0_alpha4_multi_entrant/raw_matches.json`
(pre-fix copy preserved at `raw_matches_before_alpha4_1.json`, same
directory — local research scratch, gitignored, not part of this commit).
Re-run with identical agents, seed (`1`), start positions (`0`/`1365`/
`2730`), ruleset (`bytefray-rules-2-alpha1`), and config (unchanged
defaults) — only the corrected `resolve_winner` differs.

### Match 1 — `(reactive_core_defender@A, claimer@B, core_seeker@C)`

| | Before | After |
|---|---|---|
| Winner | `claimer` (dead, `score=2021.0`) | `core_seeker` (`score=1733.0`) |
| A (`reactive_core_defender`) | alive, `score=1530.0` | unchanged |
| B (`claimer`) | dead (`core_captured`), `score=2021.0` | unchanged |
| C (`core_seeker`) | alive, `score=1733.0`, 1 kill | unchanged |

### Match 2 — `(reactive_core_defender@A, hunter@B, core_seeker@C)`

| | Before | After |
|---|---|---|
| Winner | `hunter` (dead, `score=1991.0`) | `core_seeker` (`score=1725.0`) |
| A (`reactive_core_defender`) | alive, `score=1540.0` | unchanged |
| B (`hunter`) | dead (`core_captured`), `score=1991.0` | unchanged |
| C (`core_seeker`) | alive, `score=1725.0`, 1 kill | unchanged |

In both matches, `core_seeker` (the attacker, seat C) had the higher score
of the two actual survivors, so it is the corrected winner. Scores,
survival, capture events, and kill attribution are verified byte-identical
between the before/after runs (see §11) — winner eligibility is the only
thing that changed.

## 11. 12-match matrix rerun (Phase 10)

Rerun with `runs/v2_0_alpha4_multi_entrant/run_evaluation.py`, identical
agents/trios/rotations/seed/placement/ruleset/config to alpha.4. Diffed
programmatically field-by-field against the preserved pre-fix output:

- **Exactly 2 of 12 winners changed** — the two matches in §10, both
  `dead-entrant → surviving-attacker`.
- **Every non-winner field is byte-identical** between before and after,
  for all 12 matches: `alive`, `score`, `alive_ticks`, `kills`, `deaths`,
  `territory_last`, `territory_max`, `territory_avg`, `termination_reason`,
  `bucket_sum`, `ticks_run`, `match_termination_reason`,
  `alive_count_at_end`. Confirmed by an exact dict-equality diff over both
  JSON files with the winner fields excluded — zero unexpected
  differences.
- alive_ticks divergence: **2/12 before, 2/12 after** (unchanged).
- kills divergence: **2/12 before, 2/12 after** (unchanged).
- Capture count: **2/12 before, 2/12 after** (unchanged).
- Territory/score metrics: unchanged (previous bullet).
- Seat effects: unchanged — both captures still involve `core_seeker` at
  seat C attacking seat B, exactly as alpha.4 §16 documented; nothing in
  this fix touches placement, scheduling, or targeting.
- `matches_where_dead_entrant_won`: **2 → 0**. This is the single intended
  effect of the fix, confirmed at the full-matrix level, not just in the
  two hand-verified matches above.

## 12. Revised scoring-activation conclusion (Phase 11)

alpha.4 §14 found, using `analyze.py`'s raw-score rank ordering (which
ranks **every** entrant, dead or alive, purely by numeric score — a
different question from winner eligibility): adding `alive`/`kills` to
`territory`-only never changed which entrant had the *top raw score*,
0/12 either way. Rerunning that same raw-score analysis after the fix
reproduces **exactly the same 0/12 result**, because `analyze.py`'s ranking
was never routed through `resolve_winner` and this fix changes nothing
about score computation.

The important refinement is distinguishing three previously-conflated
questions, per the governing task's Phase 11:

- **Score contribution** — does `alive`/`kills` numerically change an
  entrant's score? Yes, in both capture matches (unchanged by this fix).
- **Raw score ranking** — does that change which entrant has the single
  highest score? No, 0/12, in either the before or after run (unchanged by
  this fix — `analyze.py`'s counterfactual rankings are score-only and
  eligibility-blind by design).
- **Winner eligibility** — does that change who the match actually
  declares as winner? **This is exactly what changed**: in both capture
  matches, the entrant with the top raw score was dead, so pre-fix it won
  the match; post-fix it is excluded from eligibility and the
  higher-scoring survivor wins instead.

alpha.4's original finding — "raw activation is real, but never observed
changing the top of the raw-score ranking in this 12-match sample" —
**remains true and is unaffected by this fix**, because that finding was
always about raw score ranking, which this fix does not touch. What alpha.4
did *not* separately ask, and which this alpha now answers, is "does
survivor-restricted eligibility ever change who wins" — and the answer is
yes, in exactly the 2 matches where the raw-score leader happened to be
dead.

## 13. The strongest argument against survivor eligibility (Phase 13)

The most direct alternative: an entrant that accumulated overwhelming
territory or kills before dying could arguably deserve to win on total
performance — territory claimed is territory claimed, whether or not the
claimant is still standing at the final bell.

Weighed against Bytefray's existing semantics, this does not hold up:

- **It would contradict existing 1v1 behavior.** In every 1v1 match today,
  a single death forces `len(alive) == 1` and the survivor wins
  unconditionally — a dead entrant with a dominant score already cannot win
  a 1v1 match. Allowing it at 3+ entrants would make winner semantics
  depend on entrant count in a way with no principled justification; the
  governing task's framing of this as "the natural N-entrant extension of
  existing 1v1 semantics" is the correct one.
- **Core capture would lose its strategic weight.** If a captured entrant
  could still win the match outright, the mechanic's actual in-match
  consequence (elimination) would be cosmetic relative to the win
  condition — precisely alpha.4 §7's finding, twice, in real gameplay.
- **It removes an agent's incentive to survive.** An agent that has
  already secured a large territorial lead would have no reason to defend
  its core at all under the old rule; a rational agent could treat capture
  as a non-event. Survivor eligibility restores "stay alive" as materially
  meaningful strategy, not merely a statistics footnote.
- **It is unintuitive to users.** A leaderboard or match summary naming a
  visibly-dead entrant "the winner" over two entrants still standing reads
  as a bug, not a feature, to anyone unfamiliar with the score-fallback
  internals — exactly how this was originally surfaced, as an
  unanticipated consequence rather than an intended design outcome.
- **Agents optimizing the ruleset would not expect it.** Nothing in the
  agent-facing API or documentation currently signals that dying is
  compatible with winning; an agent author has every reason to assume
  survival matters, and the pre-fix behavior silently violated that
  assumption only once a third entrant was introduced.

No technical or game-design reason was found to prefer the alternative.
Survivor eligibility is adopted as specified by the governing task.

## 14. Ruleset/artifact identity decision (Phase 14)

**No new Ruleset ID is introduced.** Reasoning:

- Winner resolution is not part of any Ruleset's persisted identity or
  mechanic contract (§4) — it is explicitly documented, in
  `ruleset_policy.py` itself, as not yet Ruleset-policy-owned, shared
  identically across `bytefray-rules-1` and `bytefray-rules-2-alpha1`.
  This fix therefore changes a cross-cutting engine invariant uniformly,
  not one Ruleset's mechanic.
- It is not a semantics change specific to `bytefray-rules-2-alpha1`: the
  identical fix applies to `bytefray-rules-1` matches too (unobservable
  there in practice only because the 1v1/all-standard-Ruleset harness never
  runs more than 2 entrants through it today — the 3-entrant-under-v1 test
  `test_three_entrant_match_runs_under_ruleset_v1_unchanged` in alpha.4's
  own suite confirms N-entrant execution is already a general engine
  capability, not gated behind the experimental Ruleset).
  `docs/RULES.md`'s bump policy exists to protect a Ruleset ID's *mechanic*
  contract; this change alters no mechanic at all.
- The only persisted research artifacts affected
  (`runs/v2_0_alpha4_multi_entrant/*.json`) are explicitly untracked local
  scratch output, per the `.gitignore` precedent alpha.1–alpha.4 already
  established, not canonical or committed results — this document is the
  durable record, and it states the before/after values textually (§10),
  so no dual-identity scheme is needed to keep old and new results
  distinguishable.
- The governing task is explicit: do not create a new ID "merely because
  alpha.4.1 exists" — only if persisted match semantics genuinely require
  distinguishing old vs. corrected behavior by identity. They do not here;
  this document does that job in prose.

`bytefray-rules-2-alpha1` is reused exactly as alpha.1–alpha.4 left it.

## 15. Regression qualification (Phase 16)

| Check | Result |
|---|---|
| New winner-semantics tests (`test_v2_alpha4_1_winner_semantics.py`) | 12 / 12 passed |
| `test_v2_alpha4_multi_entrant.py` (updated) | 10 / 10 passed |
| `test_match_services.py` (incl. pre-existing `resolve_winner` unit test, unmodified) | 8 / 8 passed |
| `test_ruleset_v1_equivalence.py` | 8 / 8 passed |
| `test_ruleset_v2_alpha1.py` | 19 / 19 passed |
| `test_v2_alpha1_reference_agents.py` | 9 / 9 passed |
| `test_v2_alpha2_reactive_defender.py` | 15 / 15 passed |
| `test_ruleset_policy.py` | 20 / 20 passed |
| `test_evaluation_history_comparison.py` | 41 / 41 passed |
| Full `pytest` | **1543 total / 1537 passed / 6 skipped / 0 failed** (1531 baseline + 12 new tests, all passing; 2 `gui`-marked tests deselected as always, per `pytest.ini`'s `-m "not gui"`) |
| Ruff (repo-wide) | clean, 0 errors |
| mypy (`engine/src/battle_engine`) | clean, 69 files |
| mypy (`client/src/battle_client`) | clean, 10 files |
| `git diff --check` | clean, no whitespace errors |
| `git diff` scope | exactly 2 files changed (`results.py`, `test_v2_alpha4_multi_entrant.py`), 1 file added (`test_v2_alpha4_1_winner_semantics.py`) |

1v1 compatibility is proven twice over: algebraically (§5 — with only 2
entrants, `eligible` can only ever equal `alive` in full, or fall back to
the full set when both are dead; the single-survivor short-circuit is hit
before the new code ever runs when exactly one is alive), and empirically
(`test_winner_resolution_preserves_survival_score_fallback_and_ties`
unmodified and passing, plus 8/8 Ruleset-v1 equivalence).

## 16. Full-ranking question (Phase 12/21)

Not addressed and not required here. Existing result structures expose
only a single `winner` field (plus per-agent `score`/`alive`/statistics),
not a full finishing order, and the governing task's minimum required
behavior — "dead entrant cannot win if any entrant survives" — does not
need one. Whether the engine will eventually need an explicit
finishing-order model (e.g., survivors ranked by score, eliminated entrants
ranked below survivors and ordered by elimination timing and/or score) is
deferred as an open question, unchanged from how alpha.4 left it. Nothing
in this fix forecloses or presupposes that future design.

## 17. Deferred questions carried forward

Unchanged from alpha.4 §20, still open: earlier-capture timing effects on
`alive`/`kill` activation, a more aggressive third-party bystander's
effect, whether the seat-C-favors-capture pattern generalizes to other
placements, and behavior at 4+ live entrants in real (non-scripted) play.
This alpha adds one narrower one: with survivor eligibility now enforced,
does `alive`/`kill` divergence ever change **which of two survivors** wins,
as opposed to whether it ever topped the full raw-score ranking (§12)? Not
tested here — the 12-match sample's two capture matches both had the
attacker also being the higher-scoring survivor by territory alone, so
this narrower question was not exercised either way.

## 18. Recommendation for alpha.5

Continue exactly the direction alpha.4 §22/§23 already recommended — a
modest, still-controlled 3-way matrix engineered to produce **earlier**
captures (varied timing only, not weights or mechanics) — with one
refinement made possible by this alpha: measure the counterfactual
rankings (§12) **restricted to the survivor subset**, not the full
entrant set, since that is now the metric that actually corresponds to
`resolve_winner`'s real behavior. The original open question — "can
`alive`/`kill` ever change a default-weighted ranking outcome" — should now
be asked specifically as "can `alive`/`kill` ever change *which survivor*
wins," since §12 established that is a materially different question from
"changes the raw-score leader." Do not implement full placement/ranking
(§16) unless a concrete need surfaces; do not vary scoring weights.

## 19. Recommended next Bytefray v2 alpha prompt

**alpha.5**, scoped to: hold every mechanic, Ruleset identity, and scoring
weight identical to alpha.1–alpha.4.1; construct a modest 3-way matrix
(still not full-scale) specifically engineered to produce core captures
earlier in the match (varied timing only); and evaluate, using the
now-corrected survivor-eligibility winner resolution, whether `alive`/
`kill` divergence can ever change which of two or more *surviving*
entrants wins a default-weighted match — closing both alpha.4's original
open question and alpha.4.1's §17 refinement of it before any future work
considers whether `Config.weights` deserves revisiting in a multi-entrant
context at all.
