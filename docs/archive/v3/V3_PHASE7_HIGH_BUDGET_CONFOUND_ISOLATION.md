# Bytefray v3 Phase 7 -- High-Budget Defensive-Event Confound Isolation

Branch: `v3-research-phase7`, cut from `v3-research-phase6` at `7f36a23`.
Status: research complete, not merged, not tagged, not published.

Phase 6 qualified a cross-tick "attack episode" active-defense event and
found it fails two blocking gates -- Q6 (budget-robustness margin) and Q7
(seat robustness) -- at `instr_per_tick=32` only, through two mechanisms it
diagnosed but explicitly declined to disentangle further
(`docs/V3_PHASE6_ACTIVE_DEFENSIVE_INTERVENTION_QUALIFICATION.md` Sec 15,
16, 20): `core_tracker`'s own un-offset `expand_cursor` inflating its
opportunity-conditioned rate to 50.0%, and a genuine collapse of the
cross-tick reclaim advantage when an assault completes inside one action
block. Phase 7 answers the one causal question those two findings left
open, and only that question. It changes no threshold, no window, and no
qualifying rule -- the frozen Phase 6 detector
(`tools/v3_phase6_defense_episode.py`) is imported and reused verbatim
throughout, never copied or edited.

---

## 1. The question

> Is Phase 6's high-budget failure primarily an artifact of
> `core_tracker`'s incidental self-core expansion behavior (**H1: agent
> confound**), or is it an unavoidable consequence of Bytefray's
> sequential-quota scheduler when an assault fits inside one entrant's
> action block (**H2: scheduler/budget limitation**)?

* **H1 (agent confound).** Offset `core_tracker`'s expansion cursor past
  its own core (mirroring `core_defender`'s own existing precedent) →
  Q6/Q7 recover at `a4096_b32` → the detector may still be viable.
* **H2 (scheduler/budget limitation).** Offsetting the tracker does not
  materially repair `a4096_b32` → a one-block assault fundamentally
  removes the victim's opportunity to react → the event is not a
  Ruleset-wide invariant, regardless of which agents populate the corpus.

Per the governing task, this phase does not alter the frozen `v2-baseline`
benchmark to test H1. It uses a **disposable control agent**, staged
separately and never registered in any `BenchmarkPopulation` manifest, and
runs only the small number of new matches needed to compare it against the
real, untouched `core_tracker`.

---

## 2. Initial state

| ref | value |
|---|---|
| starting branch | `v3-research-phase6` |
| HEAD | `7f36a2364...` (Phase 6's report commit) |
| `v3-research-phase0`..`phase6` | unchanged |
| `main` / `origin/main` | identical, no unpushed divergence |
| frozen `v2-baseline` population | **9/9** members verify (re-checked after this phase's work, Sec 11) |
| Phase 1 committed corpus | read-only throughout; not one committed file under `runs/research_v3_phase1` is modified |
| Phase 6 gates/detector | `v3_phase6_active_defense_gates.json` and `tools/v3_phase6_defense_episode.py`, both imported unmodified |

Work proceeded on a new branch `v3-research-phase7` cut from `7f36a23`.

---

## 3. Design: two parts, matched to the two hypotheses

**Part A tests H2 without touching any agent.** It re-analyzes the same
committed Phase 1 replays Phase 6 already used, adding one new derived
predicate on top of the frozen `Episode` reconstruction:
`had_reaction_opportunity` (`tools/v3_phase7_confound_isolation.py`). No
match is executed for Part A.

**Part B tests H1.** It stages `core_tracker_offset`
(`engine/src/battle_engine/data/v3_phase7_agents/core_tracker_offset`) -- a
byte-for-byte copy of the real, frozen `core_tracker` reference agent with
**exactly one line changed** -- into a disposable run directory, and
re-executes only the one roster where `core_tracker` is ever the victim of
a genuine search-role assault. Everything else about the real
`core_tracker`, `v2_baseline_corpus.json`, and every other committed
Phase 0-6 artifact is untouched.

### 3.1 Why only one roster needs new matches

Of the 11 group rosters and 3 pairwise pairs in the frozen `v2-baseline`
corpus, `core_tracker` appears in five group rosters and two pairs. Q4
(Phase 6 Sec 13) measured **100% attacker-side purity** for "meaningful
progress" episodes at every budget: only a search-role agent (`core_seeker`
or `core_tracker`) ever produces one. `core_tracker`'s self-reclaim
artifact can only manifest when *it* is genuinely assaulted by a second
search-role agent -- and exactly one roster contains that combination:

| roster | second search agent present? |
|---|---|
| `claimer_coretracker_coredefender` | no |
| `claimer_coretracker_reactive` | no |
| `claimer_coretracker_hunter` | no |
| `hunter_coretracker_coredefender` | no |
| **`hunter_coretracker_coreseeker`** | **yes -- `core_seeker`** |
| `claimer_vs_coretracker_400/200` (pairwise) | no |
| `hunter_vs_coretracker_400/200` (pairwise) | no |

`hunter_coretracker_coreseeker` is also the exact roster Phase 6 Sec 15
used for its own concrete-replay diagnosis, so this is not a new selection
-- it is the same diagnostic roster, re-run with one agent swapped.

### 3.2 The disposable control agent

`core_tracker_offset`'s only behavioral change from real `core_tracker`:

```python
# real core_tracker/agent.py, line 317:
self.expand_cursor = observation.pc % self.arena_size

# core_tracker_offset/agent.py:
self.own_core_start = observation.pc % self.arena_size
self.expand_cursor = (self.own_core_start + CORE_SIZE_HINT) % self.arena_size
```

This mirrors `core_defender/agent.py`'s own existing precedent
(`expand_cursor = core_start + DEFENDED_RADIUS`) exactly, in that agent's
own words: "so the defended cells and the expansion sweep never fight over
the same ground." Nothing else -- scan cadence, probe/assault logic, RNG
usage, signature, cost profile -- is touched, so any measured behavioral
difference is attributable to this one line. `engine/tests/
test_v3_phase7_confound_isolation.py` verifies directly (against the real,
loaded agent instances, not a description of them) that: the offset is
exactly `CORE_SIZE_HINT`; the agent's very first action never lands inside
its own core; and every other action the two agents take, given identical
observations, is identical except for the fixed address offset on expand
writes.

The agent is staged by a plain file copy into the run's disposable
`agents/` directory (`_stage_offset_agent` in
`tools/v3_phase7_confound_isolation.py`) -- never through
`stage_population`, never added to any `BenchmarkPopulation` JSON. Re-
verified directly (Sec 11): `v2-baseline` still verifies 9/9 after this
phase's work, and `core_tracker_offset` shares no agent id with any frozen
population member.

### 3.3 New matches executed

Matched exactly to Phase 1's own default arena/tick/seed methodology, so
the new corpus differs from the frozen `hunter_coretracker_coreseeker`
cells only in the one substituted agent:

| parameter | value |
|---|---|
| roster | `hunter`, `core_tracker_offset`, `core_seeker` |
| conditions | `a4096_b2`, `a4096_b8`, `a4096_b32` (Phase 6's own three budget conditions) |
| arena size | 4096 (unchanged) |
| ticks | 400 (unchanged) |
| seeds | 1, 2, 3 (unchanged) |
| seat permutations x layouts | 6 x 3 = 18 per seed -> 54 cells per condition (unchanged shape) |
| **new cells executed** | **3 x 54 = 162** |
| execution path | the production `battle_engine.agent_evaluation` CLI, in-process identical invocation shape to `tools/v3_phase1_arena_action_grid.py` |
| output | `runs/research_v3_phase7/results/<condition>/group/hunter_coretracker_coreseeker_offset_control/` |

---

## 4. Part A results: does the scheduler deny victims a chance to react?

`had_reaction_opportunity(episode)` is grounded directly in facts Phase 6
already audited against source (`scheduler.run_sequential_quota`,
`apply_core_capture`'s once-per-tick-after-every-seat timing, and a
committed `result.json`'s own `reproducibility.entrant_order` confirming
seat labels A/B/C **are** the fixed match order): an episode that does not
end in capture was trivially never denied a chance; an episode spanning
more than one tick always gives the victim at least one action block
before the attacker's next tick, regardless of seat order; a single-tick
episode gives the victim a chance if and only if its seat is scheduled
*after* the attacker's that tick.

Computed over the full, unmodified 594-cell default-condition corpus (and
its `a4096_b2`/`a4096_b32` counterparts) -- no new matches:

| condition | defense P(had opportunity) | defense event rate \| opportunity | defense seat spread, unconditional | defense seat spread, given opportunity to act |
|---|---:|---:|---:|---:|
| `a4096_b2` | 100.0% | 83.6% | 13.0pp | 13.0pp |
| `a4096_b8` | 98.1% | 89.2% | 30.6pp | 27.2pp |
| `a4096_b32` | **76.1%** | 95.6% | **64.9pp** | **25.4pp** |

The unconditional spread column reproduces Phase 6's own published
figures exactly (13.0pp / 30.6pp / 64.9pp), which is a determinism/
correctness cross-check on this phase's own reconstruction, not a new
finding on its own.

**The decisive result is the last column.** At `a4096_b32`, one in four
defense-role "meaningful progress" opportunities give the victim **no
scheduling chance at all** to react before capture (P(had opportunity)
drops from ~100% at b2/b8 to 76.1%) -- a real, growing, budget-driven
mechanical effect, not a modeling artifact. Once episodes with no chance to
act are excluded, the seat spread collapses from **64.9pp to 25.4pp** --
under Q7's 40pp blocking bound, and only just above its 25pp disclosure
trigger. **Most, but not all, of Q7's own seat-spread failure at
`a4096_b32` is explained by the scheduler mechanically denying an
earlier-seated victim any opportunity to respond**, not by defense being
inherently seat-fragile once given a chance.

The residual 25.4pp is concentrated entirely in seat A: even conditioned
on having a chance, seat A's qualifying rate is 74.6% against 100% for
seats B and C (Sec 15's breakdown). A plausible mechanism, consistent with
-- but not separately verified beyond -- the same audited scheduling
facts: seat A acts *first* every tick, so even when it does reclaim a
cell, an attacker (or third party) acting later that same tick can retake
it before the capture check runs, which the frozen detector's own
`victim_survived_tick` rule (Phase 6's design, unmodified here) correctly
records as non-qualifying. If so, this residual is *also* a scheduler
property, not an agent-population artifact -- but this phase does not
independently confirm that specific mechanism the way it does the primary
opportunity-denial effect, and it is reported as an interpretation, not a
measured result.

The general (all-roles) `capture_rate_by_victim_seat` at `a4096_b32`
corroborates the same direction outside the defense-only Q7 metric: seat A
58.1%, seat B 48.3%, seat C 28.6% -- monotonically favoring later-acting
seats, exactly as the scheduling mechanism predicts, across every role, not
only defenders.

Full per-condition breakdown, including expansion/search roles and the
attacker-victim seat capture matrix:
`runs/research_v3_phase7/phase7_opportunity_report.json`.

---

## 5. Part B results: does offsetting `core_tracker` repair Q6?

| metric (`a4096_b32`) | real `core_tracker` | `core_tracker_offset` |
|---|---:|---:|
| opportunity appearances (of 54 cells) | 18 | 35 |
| qualifying appearances | 9 | 12 |
| opportunity-conditioned qualifying rate | **50.0%** | **34.3%** |
| same-tick, own-first-action reclaims | **9** | **0** |

The specific artifact Phase 6 Sec 15 diagnosed by direct replay inspection
-- the victim's very first action, on the episode's own opening tick,
landing exactly on its own `core_start + 0` -- is **completely eliminated**
by the one-line fix: 9 occurrences at `a4096_b32` with the real agent, 0
with the offset control, confirming the fix targets the mechanism it was
built for.

| condition | Q6 margin, original corpus | Q6 margin, offset tracker substituted | Q6 bound |
|---|---:|---:|---:|
| `a4096_b2` | 68.6pp | 57.6pp | 40pp |
| `a4096_b8` | 73.3pp | 49.7pp | 40pp |
| `a4096_b32` | **15.8pp** | **31.5pp** | **40pp** |

At `a4096_b2`/`a4096_b8` the substituted margin is *lower* than the
original -- expected and not concerning, because real `core_tracker`
registered a 0.0% rate at both budgets (matching Phase 6's own published
figures exactly) while the offset control shows a real, nonzero rate at
every budget (19.4%/32.3%/34.3%), so replacing 0.0% with a nonzero number
mechanically tightens the margin at the budgets where the gate was never in
danger. Both conditions still clear the 40pp bound by a wide margin either
way.

**At `a4096_b32`, the margin roughly doubles (15.8pp -> 31.5pp) but stays
under the declared 40pp blocking bound.** Q6 would still fail at this
budget after the fix, materially less severely, but not enough to pass.

### 5.1 Why the offset control's own rate does not collapse to near-zero

The offset control's opportunity-appearance count nearly doubles at every
budget (16->31, 18->31, 18->35). This is consistent with, not contrary to,
the fix working as intended: the real agent's guaranteed same-tick self-
touch sometimes interrupted an attacker's own progress-accumulation before
it reached the windowed threshold at all, undercounting genuine assault
opportunities; removing that interruption lets more real assaults reach
"meaningful progress" and be counted. Among this larger, more genuine
opportunity set, the offset control still qualifies 19-34% of the time --
not near-zero the way `core_seeker`'s own rate stays (4.3%-8.3% across the
same three budgets, Phase 6 Sec 15). `same_tick_own_first_action_reclaims
= 0` confirms none of these remaining qualifying instances are the specific
artifact this control fixes; they are later, non-first-action reclaims.
Phase 6 Sec 15's own closing paragraph already named the likely broader
cause: at high `instr_per_tick`, *any* sweeping agent's outward cursor can
lap the whole arena and cross back over its own core within the
progress-tracking window, and it measured a smaller-magnitude version of
exactly this in `hunter` (4.7%->19.5%) and `claimer` (3.4%->7.7%) across
the same budget range -- agents with no self-reclaim bug at all. This
phase's control was built to fix one specific, guaranteed, first-action
artifact; it was not designed to, and does not, address that broader,
population-wide property, which is unchanged here and remains open.

Full per-condition numbers, including appearance/opportunity counts at
every budget: `runs/research_v3_phase7/phase7_compare_report.json`.

---

## 6. Q7 under the offset-corrected roster

`core_tracker` is never a defense-role agent, and Q7's seat-spread
computation is restricted to defense-role victims by the frozen detector's
own `ROLE_OF` mapping -- `core_tracker`'s identity cannot mechanically
enter that computation at all. Predicted null effect, confirmed directly:
substituting the offset-corrected roster's data leaves Q7's defense seat
spread at `a4096_b32` unchanged, 64.9pp, identical to the original corpus
(Sec 5's table, `q7_defense_seat_spread_original`, reported at every
condition precisely to make this an explicit check rather than an assumed
one). Q7's own failure has nothing to do with which search agent
`core_tracker` is; Sec 4 already located its explanation elsewhere.

---

## 7. Interpretation: neither H1 nor H2 cleanly, and why that is still decisive

* **H1 (agent confound) is partially confirmed, not fully.** The specific,
  concretely-diagnosed bug is real, mechanically isolated to one line, and
  fixing it in isolation measurably repairs roughly half of Q6's margin
  gap at `a4096_b32` (15.8pp -> 31.5pp against a 40pp bound) while
  completely eliminating the exact artifact instance Phase 6 identified by
  direct replay inspection (9 -> 0). It does not, by itself, restore Q6 to
  a passing state, because a second, broader, population-wide mechanism --
  any sweeping search agent's cursor eventually re-crossing its own core at
  high action-budget, already visible in `hunter`/`claimer` at smaller
  magnitude -- remains untouched and unaddressed by this narrow control.
* **H2 (scheduler/budget limitation) is substantially confirmed for Q7,
  not for Q6.** Q7's own 64.9pp seat-spread failure is, for the majority of
  its magnitude, a direct, mechanically-audited consequence of Bytefray's
  sequential-quota scheduler denying an earlier-seated victim any chance to
  react when an assault completes inside one action block -- true
  regardless of which agents populate the corpus, confirmed by Sec 4's
  agent-independent reanalysis and by Sec 6's direct check that offsetting
  `core_tracker` leaves Q7 completely unchanged. A smaller residual
  (25.4pp of the 64.9pp) survives even after removing the pure
  opportunity-denial cases, plausibly -- but not independently confirmed
  here -- for the same scheduler-structural reason (an early seat's own
  reclaim being vulnerable to same-tick override).

The honest joint answer is a mixture, not an exclusive disjunction: **Q7's
failure is predominantly a scheduler property; Q6's failure is partly one
agent's now-isolated implementation bug and partly a different,
broader, population-wide artifact this phase did not attempt to fix.**
This is exactly the kind of result Sec 1's governing question anticipated
as possible and asked to be measured rather than assumed either way.

---

## 8. What this does, and does not, change about Phase 6's verdict

**Phase 6's verdict stands: ACTIVE DEFENSIVE EVENT NOT QUALIFIED.** Both
Q6 and Q7, as originally declared and frozen, still fail their exact
numeric bounds at `a4096_b32` against the real, unmodified `v2-baseline`
population -- this phase changes no gate, no threshold, and no window, and
does not re-run Phase 6's own qualification against a substituted
population (that would require replacing `core_tracker` in the frozen
corpus, which Sec 3 deliberately does not do). Per Phase 6's own
predeclared decision rule, "revise" is available only for a threshold-or-
window-choice artifact; both of this phase's findings are agent-population
and scheduler-structural, exactly the category Phase 6 Sec 19 already
excluded from that clause, so revision remains not invoked.

What changes is causal attribution, which is what Phase 7 was scoped to
produce: Phase 6 Sec 20 left open whether reclassifying its own finding
from "the event is budget-dependent" to "the frozen population has an
incidental self-claim bug unrelated to defense" was possible, and
explicitly said that reclassification "is not tested here and must not be
assumed." Phase 7 tested it directly: the reclassification is **partially**
correct (a real, now-fixed, agent-specific bug does exist, and repairs
roughly half the Q6 gap) but is **not fully** correct (the remaining gap is
a different, broader, still-unaddressed population property, and Q7's
failure was never primarily about `core_tracker` at all). A clean partial
result is reported as exactly that, per the standing research-integrity
rule that a null or partial result is a success of the method, not
something to soften.

---

## 9. What Phase 7 deliberately did not do

* Did not modify `hunter` or `claimer`'s own expand-cursor initialization
  to test whether fixing the broader "any sweeper can re-lap its own core"
  property (Sec 5.1) would close the remaining Q6 gap -- that would mean
  touching multiple reference agents' behavior at once, conflating two
  separable causal questions, and is explicitly the kind of broader,
  population-wide intervention Phase 6 Sec 20 scoped to "a successor
  phase," not this one.
* Did not re-run Phase 6's own full qualification pipeline against a
  population with `core_tracker` replaced -- only the one diagnostic
  roster needed to isolate the question was re-executed (Sec 3.1), per the
  governing task's own "run only enough new matches" instruction.
* Did not propose, weaken, or re-derive any threshold, window, or scoring
  change. No score, weight, Ruleset identity, agent (other than the
  disposable control), Agent API field, or default is altered anywhere in
  this phase.
* Did not pursue a scoring-payoff experiment for the active-defense event.
  Per the governing task, that question stays closed until (if ever) a
  successor phase resolves the remaining Q6 population-wide artifact on
  its own terms.

---

## 10. Files changed

| file | change |
|---|---|
| `engine/src/battle_engine/data/v3_phase7_agents/core_tracker_offset/agent.py` | **new** -- disposable control agent, one line different from real `core_tracker` |
| `engine/src/battle_engine/data/v3_phase7_agents/core_tracker_offset/agent.yaml` | **new** -- manifest, never registered in any `BenchmarkPopulation` |
| `tools/v3_phase7_confound_isolation.py` | **new** -- Part A/B driver and analysis, imports the frozen Phase 6 detector unmodified |
| `engine/tests/test_v3_phase7_confound_isolation.py` | **new** -- 7 focused tests (agent mechanics + reaction-opportunity predicate) |
| `docs/V3_PHASE7_HIGH_BUDGET_CONFOUND_ISOLATION.md` | **new** -- this report |
| `runs/research_v3_phase7/` | **local, git-ignored, not committed** -- 162 new match cells (`results/`) plus the two JSON analysis reports, exactly like every other `runs/research_v3_phaseN/` corpus in this program; reproducible by rerunning `tools/v3_phase7_confound_isolation.py run` |

No file under `runs/research_v3_phase1` through `runs/research_v3_phase6`,
`engine/src/battle_engine/data/reference_agents/`, or
`engine/src/battle_engine/data/benchmarks/v2_baseline_corpus.json` is
touched.

---

## 11. Validation

| check | result |
|---|---|
| Gates / detector unchanged | `tools/v3_phase6_defense_episode.py` imported, never edited; diff against `v3-research-phase6` is empty for this file |
| Scoring / Ruleset / Agent API / defaults changed | **none** |
| Frozen `v2_baseline_corpus.json` / `v2-baseline` population changed | **none** -- re-verified 9/9 after this phase's work |
| Matches executed | 162 new cells, one roster (`hunter_coretracker_coreseeker`), three budget conditions, one substituted agent |
| Offset agent's intended behavioral difference | verified directly against the loaded, running agent instances (`engine/tests/test_v3_phase7_confound_isolation.py`), not merely asserted |
| Diagnosed artifact elimination | 9 -> 0 same-tick own-first-action reclaims at `a4096_b32`, measured directly from the new corpus |
| Reproduction of Phase 6's own published figures | exact: unconditional defense seat spreads (13.0pp/30.6pp/64.9pp), `core_tracker`'s original 0.0%/0.0%/50.0% rates, and its 9-instance same-tick artifact count all reproduce from independent reconstruction |
| Full test suite | passing (`python -m pytest`, 0 failures) |
| `ruff check` / `mypy` | clean on every new file |

Nothing merged to `main`, nothing tagged, nothing published.
