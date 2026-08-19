# Bytefray v2.0.0-alpha.8 — Placement-Agnostic Core Offense Benchmark

A reference-agent design alpha, not a mechanic, scoring, or engine change.
alpha.6 (docs/V2_0_ALPHA6_CORE_SEEKER_TIMING.md) characterized Core
Seeker's real scan/assault mechanism exactly (a fixed absolute schedule,
an echo-lock rather than genuine two-hit confirmation) and alpha.7
(docs/V2_0_ALPHA7_SPATIAL_CHARACTERIZATION.md) proved, by deliberately
relocating core placements, that the historical seat-B-only vulnerability
pattern was an artifact of one placement convention, not an inherent
property of Vulnerable Core — but also proved Core Seeker's own fixed
schedule is geometrically incapable of reaching some placements at all
(the COLD condition: 0/9 matches, 0 partial-covering assault windows,
zero exceptions). alpha.7 recommended, as its own central conclusion, a
placement-agnostic, non-privileged searcher as the natural next step. This
alpha designs, implements, and evaluates exactly that: **Core Tracker**, a
new reference agent that discovers and pressures cores using only ordinary
Agent API v1 `READ`/`WRITE`, no opponent-position privilege, and a scan
geometry that is a function of the match seed rather than of `arena_size`
alone. `CORE_SIZE`, arena size, tick/instruction budget, scoring, winner
semantics, and every existing reference/starter agent's source — including
`core_seeker` itself — are held byte-for-byte identical. **No production
engine/client code was changed anywhere in this alpha.**

Branched from the verified alpha.7 baseline, commit `7244823` on
`v2.0-development` (`main` unchanged at
`5593d287f95a24996bb3b105befbc625a00795db` throughout).

## 1. Verified starting state (Phase 1)

- Branch: `v2.0-development`. HEAD at start: `7244823`. Working tree:
  clean. `main`: `5593d287...`, unchanged.
- `origin`'s unrelated `151866c` ("docs: expand v2.x strategic complexity
  research") was confirmed still a sibling of local history — branches
  from `4659654` (the pre-alpha.2 lineage), not an ancestor of the local
  `v2.0-development` HEAD (`git merge-base --is-ancestor 151866c HEAD`
  exits 1) — and, per the governing task's explicit instruction, was not
  merged, rebased, cherry-picked, or otherwise reconciled at any point in
  this alpha.
- `docs/V2_0_ALPHA6_CORE_SEEKER_TIMING.md` and
  `docs/V2_0_ALPHA7_SPATIAL_CHARACTERIZATION.md` were read in full before
  any new work began.
- Read directly, not inferred: `core_seeker/agent.py`, `core_defender/
  agent.py`, `reactive_core_defender/agent.py`, `claimer/agent.py`,
  `hunter/agent.py`, `agent_api.py` (`Observation`/`MatchContext`/
  `AgentAction`/`load_python_agent`), `reference_agents.py` (the
  reference-agent registration mechanism), `python_runtime.py`
  (`CORE_SIZE`, `core_addresses`, `seed_core_ownership`,
  `apply_core_capture`, `apply_action`'s `READ`/`WRITE` handling — confirmed
  directly that `WRITE` never touches `state.last_read`, only `READ` does,
  and that it is never cleared otherwise), `runs/v2_0_alpha6_core_seeker_
  timing/trace_match.py` (the production-code-reusing trace harness) and
  `runs/v2_0_alpha7_spatial_characterization/classify_positions.py`/
  `run_evaluation.py` (the placement classifier and its four pre-registered
  conditions).
- Lightweight baseline/reference-agent sanity suite (Phase 1 item 10), run
  before any new code was written: the existing alpha-focused suites
  (`test_v2_alpha1_reference_agents.py`,
  `test_v2_alpha2_reactive_defender.py`,
  `test_v2_alpha4_multi_entrant.py`,
  `test_v2_alpha4_1_winner_semantics.py`, `test_ruleset_v2_alpha1.py`) and
  `test_ruleset_v1_equivalence.py` all passed unchanged, confirming the
  repository state this alpha builds on matches what alpha.7 left it in.
- Regression baseline, measured directly on this machine before any change
  (§34 has the full account of a small pre-existing, alpha.8-unrelated
  discrepancy against the governing task's own documented figures):
  `pytest --collect-only` on the unmodified alpha.7 HEAD (verified via
  `git stash` before any alpha.8 file existed) collects **1541** tests;
  running them gives **1535 passed, 6 skipped, 0 failed** on this machine
  right now. Alpha-focused suites and Ruleset v1 equivalence: all passing,
  unchanged. Ruff: clean repo-wide. mypy: clean for both `engine`
  (69 files) and `client` (10 files).

## 2. Alpha.8 objective (Phase 0)

> Can an ordinary Bytefray agent discover and attack vulnerable cores
> across substantially different placements without knowing opponent
> starts, core locations, ownership, or hidden state?

Design, implement, and evaluate a new placement-agnostic, non-privileged
core-search attacker using only the existing Agent API v1 — a reference/
research-agent redesign, not a change to Vulnerable Core mechanics. The
goal is a legitimate general offensive benchmark whose performance depends
on discovering meaningful arena structure, not tournament-win-rate
optimization.

## 3. Frozen mechanics (Phase 2)

Held fixed throughout, confirmed unchanged: `bytefray-rules-2-alpha1`,
`CORE_SIZE = 8`, core ownership seeding, capture semantics/timing/kill
attribution, arena size 4096, `instr_per_tick = 8`, the 200-tick match
budget, scoring and its weights, winner eligibility, the scheduler, Agent
API v1, the Python runtime, replay/result semantics, and — critically —
`core_seeker/agent.py` itself, byte-for-byte unchanged (confirmed at
completion, §32: `git diff -- engine/src/battle_engine/data/
reference_agents/core_seeker` is empty). No new Ruleset ID was created.
The only tracked production/reference change is an **addition**: a new
experimental reference agent alongside the existing ones.

## 4. Name and separation (Phase 3)

The new agent is named **`core_tracker`** (chosen over `adaptive_core_
seeker`/`core_hunter` specifically to avoid colliding, in name or
implication, with the existing `core_seeker` reference agent or the
`hunter` starter agent already in this package — "tracker" signals its
actual mechanism, sustained evidence-following, without suggesting it
replaces or is a variant of either). It lives at
`engine/src/battle_engine/data/reference_agents/core_tracker/`
(`agent.py` + `agent.yaml`), the same manifest-plus-`agent.py` shape every
other reference/starter agent in this package uses, and is registered by
adding `"core_tracker"` to `REFERENCE_AGENT_NAMES` in
`reference_agents.py` — the same additive mechanism alpha.2 used to add
`reactive_core_defender` alongside `core_defender` without disturbing the
original. `core_tracker` is deliberately **not** added to
`battle_engine.starters.STARTER_AGENT_NAMES` (confirmed by a dedicated
test, §26) — it is a research/reference agent, not a promotion to
Bytefray's permanent default roster, exactly matching every other agent in
`REFERENCE_AGENT_NAMES`'s existing treatment.

## 5. Agent API information constraints (Phase 4)

`core_tracker` uses exactly the same information sources every other
reference/starter agent in this package already documents using:

**Used:**
- `observation.pc` (read once, on the first `act()` call, to seed its own
  `expand_cursor` — the same technique `core_defender`/
  `reactive_core_defender` already use for their own core address).
- `observation.last_read` (consumed exactly once per outstanding `READ`,
  see §8).
- ordinary `READ`/`WRITE` `AgentAction`s.
- own persistent instance state (`mode`, cursors, candidate/probe
  bookkeeping).
- `context.arena_size`.
- `context.rng` (a `random.Random` instance `MatchContext` already
  supplies to every agent; explicitly permitted by the governing task's
  own Phase 4 list) — used once, at `reset`, to seed the scan cursor's
  starting point (§9).

**Not used, and structurally unavailable even if it wanted to be** (the
same guarantee every other reference agent's own tests already assert,
re-asserted here for this agent specifically,
`test_observation_carries_no_opponent_state_the_agent_could_read`):
opponent start addresses, opponent core locations, the ownership map,
opponent identity or strategy name, opponent internal state, replay
history, capture notifications beyond what `Observation` already exposes,
direct arena or engine object access, privileged ruleset callbacks, or
inspection of any loaded opponent source. `CORE_SIZE` is used only as
public ruleset knowledge (`CORE_SIZE_HINT = 8` in source) — the identical
distinction `core_defender/agent.py`'s own docstring already draws for its
`DEFENDED_RADIUS`, reused here rather than re-argued. No historical
control/COLD/HOT/MIXED coordinate is hardcoded anywhere in source,
verified directly (§26,
`test_source_does_not_hardcode_alpha7_placement_addresses`).

## 6. The actual search problem (Phase 5)

`Observation` exposes no ownership map — the only way to learn anything
about the arena is a `READ` returning one raw byte. A single foreign-
looking byte (non-zero, not this agent's own signature) is very weak
evidence: it could be one incidental cell from any ordinary entrant's
blind sweep passing through, nowhere near that entrant's actual core. This
is not a solvable ambiguity — no non-privileged agent can turn a byte
value into an ownership fact. What the search problem actually is: **build
enough spatial, evidence-based confidence in a compact region before
spending a burst of writes there**, distinguishing (per the governing
task's own framing) isolated foreign writes from a genuine spatial
cluster, without ever literally detecting ownership. A second, equally
important structural fact discovered while implementing this — not merely
asserted, confirmed directly by reading `python_runtime.seed_core_
ownership` (§1): an entrant's core cells are seeded with **ownership** at
tick zero via a real `WRITE` of **value `0`** — so an opponent's own core
cell that nothing has ever rewritten is byte-for-byte indistinguishable
from ordinary untouched arena, to any reader, always. This is the same
"content readiness" constraint alpha.6 §13/17 already discovered governs
Core Seeker's one real success pathway; `core_tracker` does not, and
cannot, remove it — it only changes which addresses get a chance to
benefit from it (§7).

## 7. Candidate search designs considered (Phase 7)

Three shapes were evaluated (a fourth, "moving-window reconnaissance," was
judged to already be subsumed by the chosen design's on-demand probe step
rather than a genuinely separate mechanism, so it was not built as one):

**A. Low-discrepancy broad scan + spatial clustering** (closest to Core
Seeker's own existing design: wait for two independently-hit addresses
within a fixed radius). Rejected as the primary mechanism: without an
explicit "a pending read result is consumed exactly once" rule, this shape
reliably degenerates into re-checking the same stale `last_read` against
itself — precisely Core Seeker's own documented defect (alpha.6 §4), not
a hypothetical risk. The underlying *coverage* idea (an equidistributed
scan sequence) is still used (§9); the *confirmation* half of this design
is not.

**B. Coarse-to-fine search** (sparse global scan; on a foreign hit, probe
a small number of nearby addresses before committing). **Selected.**
False-positive rate and detection latency are both governed by an
explicit, inspectable confirmation rule (§10) rather than an accidental
implementation quirk, and the probe step is cheap (a handful of actions)
relative to a full assault burst, giving a real, disclosed opportunity-cost
story (§13, §21).

**C. Multi-probe confirmation** (record candidates, require genuinely
separate observations rather than relying on stale `last_read`). Not
selected as the *primary* design, but its core correctness requirement —
genuinely distinct evidence, never a reinterpreted stale read — is a
mandatory property of whichever design is chosen (governing task Phase 8),
so it is folded into (B)'s probe step directly rather than built as a
separate temporal-persistence mechanism. A temporal variant (re-read the
*same* address at two different times, instead of nearby addresses) was
considered and rejected: for a stationary opponent core, a second read of
the identical address carries no more information than a spatial probe
does, while costing strictly more elapsed time before a decision.

**D. Moving-window reconnaissance** (continuous background probing
interleaved with expansion at all times). Not adopted as a standalone,
permanently-running mechanism — (B)'s probe step already *is* a bounded,
on-demand version of this idea, triggered only when there is already a
reason to look closer, without paying its cost when there is no evidence
yet.

## 8. Selected design: coarse-to-fine search with genuine confirmation (Phase 6/7)

A three-state machine (`self.mode`):

- **`scan`** (default): one action in every `SCAN_EVERY = 3` is a `READ`
  at a slowly advancing scan cursor (§9); the other two are an ordinary
  outward claiming `WRITE` — the same one-in-three investigative rate Core
  Seeker's own design already uses, kept identical for direct opportunity-
  cost comparability (§21).
- **`probe`**: entered the instant a coarse-scan `READ` returns a foreign-
  looking byte. Issues `PROBE_OFFSETS = (-8, -4, 4, 8)` — four further
  dedicated `READ`s at fixed offsets around the original hit, sized around
  `CORE_SIZE_HINT = 8` so the probed span comfortably brackets a plausible
  core position relative to an uncertain hit offset within it. If at least
  `CONFIRM_MIN_HITS = 2` of the probed observations (the original hit plus
  at least one probe) come back foreign, the candidate is confirmed and
  this agent commits to `assault`; otherwise it is abandoned and ordinary
  scanning resumes immediately from exactly where it left off.
- **`assault`**: a fixed `ASSAULT_ACTIONS = 16`-action `WRITE` burst across
  an `ASSAULT_WINDOW = 16`-wide window, centered on the **midpoint of the
  confirmed offsets** (not just the raw first hit) — the one real accuracy
  advantage coarse-to-fine buys over committing to the very first address
  that looked foreign.

## 9. Why the scan geometry uses RNG, not a fixed convention (Phase 6)

Core Seeker's scan sequence is a pure function of `arena_size` alone,
identical in every match forever — exactly what gives it the fixed,
permanently reproducible blind-spot set alpha.7's COLD condition exposed.
`core_tracker` keeps the same *quality* of sequence (a stride coprime to
the arena size, chosen from an equidistribution-friendly irrational,
`sqrt(2) - 1 ≈ 0.4142135624` — deliberately a third constant, distinct
from both Core Seeker's own `0.381966011` and Hunter's
`0.618033988749895`, so this is a structurally different sequence, not a
re-tuned copy) but draws its **starting cursor** from `context.rng` at
`reset`. The stride itself is deliberately left fixed rather than also
randomized: a stride picked without the equidistribution property could
have poor spread by chance, while randomizing only the anchor keeps the
proven spread quality and still makes the reachable/unreachable set a
function of the match seed, not of `arena_size` alone. This is still fully
deterministic and reproducible for a fixed seed
(`test_deterministic_given_identical_seed_and_input_sequence`,
`test_scan_geometry_is_independent_of_own_spawn_position`), exactly like
every other agent in this package that seeds anything from `context.rng`.

## 10. Stale-read/echo-lock prevention (Phase 8)

`observation.last_read` reflects whichever `READ` most recently completed
and is never cleared between actions (confirmed directly from
`python_runtime.apply_action`, §1) — the exact mechanism alpha.6 §4 found
turns Core Seeker's own two-hit design intent into a near-automatic
one-hit lock. `core_tracker` avoids this class of bug structurally: every
`READ` it issues immediately records the address it is waiting on in
`self._pending_read_addr`; the very next `act()` call consumes
`observation.last_read` as the result for that one specific address and
clears the pending marker *before* doing anything else, so a given read
result is interpreted exactly once, in whichever mode this agent happens
to be in when it arrives. Proven directly by three focused tests
(§26): `test_last_read_is_ignored_unless_a_read_is_actually_pending` (an
`observation.last_read` value supplied before any `READ` was ever issued
has zero effect), `test_assault_burst_ignores_last_read_entirely` (a
16-action assault burst, driven with a garbage `last_read` value on every
call, is completely unaffected), and `test_a_scan_hit_alone_does_not_
trigger_an_assault` (a single isolated foreign byte, with realistic
`last_read` persistence exactly as production behaves, never assaults).

## 11. Search sequence/coverage (Phase 11 of the report outline)

Within the 1,600-action budget, `core_tracker` spends roughly the same
one-in-three-actions coarse-scan rate as Core Seeker (measured directly:
an average of 256.4 coarse-scan `READ`s per match across the full
three-way matrix, §19, vs. Core Seeker's 236.7 — comparable order of
magnitude, ~13% direct-scan arena coverage in the worst case, the same
hard budget ceiling every non-privileged design under this action budget
faces, disclosed rather than hidden). What differs is not raw coverage
volume but *which* addresses that budget reaches: because the scan
anchor is seeded from the match's own RNG rather than a fixed
`arena_size`-only convention, the specific ~13% slice reached is a
function of the seed, not a permanently fixed set of addresses.

## 12. Candidate clustering rule (Phase 12 of the report outline)

A candidate is created the instant a coarse-scan `READ` returns a
foreign-looking byte (§8). It is confirmed, and only then assaulted, if at
least one of the four bounded probe offsets around it also returns
foreign content — genuinely separate evidence, never a re-interpretation
of the same read (§10). Measured directly across the full three-way
matrix (§19): of 3,192 candidates investigated, 2,021 (63.3%) were
confirmed and assaulted and 1,155 (36.7%) were correctly abandoned as
false positives — real, substantial discrimination, not a rubber stamp.
The rate varies exactly as the underlying mechanism predicts: against
Claimer/Hunter (which never sign or actively rewrite their own core) the
pre-matrix confirmation rate is 7.4%–28.1%; against Core Defender/Reactive
Core Defender (which do) it is 50.0%–72.2% (§22, full table).

## 13. Assault rule and opportunity cost (Phase 13 of the report outline / Phase 6)

The assault window is centered on the midpoint of the confirmed evidence
offsets, width 16, one write per cell, 16 actions — sized identically to
Core Seeker's own `ASSAULT_WINDOW`/`ASSAULT_ACTIONS` for direct
comparability. Measured directly across the full three-way matrix (§19):
`core_tracker` spent an average of **557.9** actions per match on assault
bursts and **235.7** on probe `READ`s (a cost Core Seeker has none of, by
design) — vs. Core Seeker's **832.9** assault actions per match and zero
probe actions. `core_tracker` spent more of its budget on ordinary
expansion (**549.9** actions/match average vs. Core Seeker's **474.5**).
This is a genuine, unplanned, and favorable finding, not merely "search
has some cost": Core Seeker's echo-lock commits a *full* 16-action burst
to essentially every single foreign hit it ever sees (55–58 assault
episodes per match, the large majority false positives, per alpha.6 §5),
so *its* false positives are expensive; `core_tracker`'s false positives
cost only the original scan read plus up to four cheap probe reads (about
five actions) before being abandoned, so *more* of its total budget ends
up available for ordinary territorial expansion despite spending real,
measurable actions on investigation. Search is strategically costly for
both agents, but differently shaped: Core Seeker pays mostly in wasted
full-size assault commitments, `core_tracker` pays mostly in a larger
number of cheap, mostly-correct-to-abandon investigations.

## 14. Focused tests (Phase 26)

`engine/tests/test_v2_alpha8_core_tracker.py`, **19 tests, all passing**:
Agent API v1 lifecycle/registration (contract satisfaction, reference-list
registration, starter-roster exclusion, `Observation` field-shape
guarantee, no-hardcoded-address source scan); echo-lock prevention (3
tests, §10); confirmation/clustering synthetic fixtures (compact region
triggers a fully-covering assault; the same fixture moved to a different
address; a fixture wrapping the arena boundary; a decoy-then-true-region
scenario proving search is never permanently derailed; search resumption
after both a completed and an abandoned candidate); placement/spawn
independence (scan geometry proven identical across two different own-
spawn positions for a fixed seed, while expansion legitimately differs;
two different seeds proven to scan materially different regions;
determinism given an identical seed and input sequence); and three
end-to-end `NativeMatchService` tests (a full match without forfeiting, a
real capture of Core Defender across up to 16 seeds — mirroring Core
Seeker's own acceptance-test pattern exactly — and clean operation under
Ruleset v1). `test_v2_alpha1_reference_agents.py`'s existing
`REFERENCE_AGENT_NAMES`/starter-roster assertions were updated additively
(the same pattern alpha.2 already established when it added
`reactive_core_defender`), not replaced.

## 15. One design correction considered, and not used (Phase 12/Phase 16 of the report outline)

The governing task permits at most one evidence-driven correction after
the pre-matrix. None was needed: the pre-matrix (§16) immediately produced
the intended qualitative signal (full-core-covering assaults, including in
the COLD condition, with a real capture already appearing there) without
any indication of a conceptual defect (no confirmation-window impossible
to satisfy, no off-by-one assault center, no failure to resume search).
The initial `PROBE_OFFSETS`/`CONFIRM_MIN_HITS` choice was kept unchanged
from first implementation through the full three-way matrix.

## 16. Pre-matrix (Phase 16)

`core_tracker` vs. each of Claimer, Hunter, Core Defender, Reactive Core
Defender individually (2-entrant, victim@seat A, `core_tracker`@seat C —
the same seating convention this repository's own `core_seeker` acceptance
test already uses), at one historical placement (control), one alpha.7
COLD placement, and one held-out placement (`heldout_even_eighths`, §17) —
12 matches total, zero infrastructure failures:

| Condition | Opponent | Assault episodes | Full-covering episodes | Capture |
|---|---|---:|---:|---|
| control | claimer | 6 | 0 | — |
| control | hunter | 16 | 0 | — |
| control | core_defender | 26 | 0 | — |
| control | reactive_core_defender | 25 | 0 | — |
| cold | claimer | 5 | 0 | — |
| cold | hunter | 14 | 0 | — |
| **cold** | **core_defender** | **1** | **1** | **A←C @ tick 27** |
| cold | reactive_core_defender | 27 | 2 | — (reclaim race won) |
| heldout_even_eighths | claimer | 5 | 0 | — |
| heldout_even_eighths | hunter | 16 | 0 | — |
| heldout_even_eighths | core_defender | 26 | 1 | A←C @ tick 196 |
| heldout_even_eighths | reactive_core_defender | 26 | 1 | — (reclaim race won) |

The critical result: a real, fully-attributed capture in the **COLD**
condition — the exact placement alpha.7 established Core Seeker's own
fixed schedule can *never* reach (0/9 matches, 0 partial-covering
episodes, zero exceptions, alpha.7 §13). This qualified the design for the
full matrix without requiring the one permitted correction.

## 17. Held-out placement generation method (Phase 15)

Two conditions, generated by documented formula, recorded in
`runs/v2_0_alpha8_placement_agnostic_offense/held_out_placements.py`
**before** any `core_tracker` match was run against either — mirroring
alpha.7's own prediction-before-execution discipline:

- **`heldout_even_eighths`** — "one roughly evenly-spaced placement": the
  odd eighths of the arena, `(2k-1) * arena_size // 8` for `k = 1, 2, 3`,
  sorted ascending. Deliberately not quarters (which would coincide with
  the legacy alpha.1/alpha.2 1v1 convention's own address `2048`).
- **`heldout_pi_digits`** — "one irregular but non-overlapping placement":
  the first three non-overlapping 4-digit chunks of π's decimal expansion
  (after "3."), each reduced modulo `arena_size`, sorted ascending — an
  arithmetic sequence with no periodic structure at all, so its three gaps
  are unrelated to one another by construction.

Neither condition was selected or adjusted based on any predicted or
observed outcome for either attacker (verified by construction — the
formulas above are the entire selection procedure, with no post-hoc
filtering step). As informational, post-hoc context only (computed *after*
the addresses were already fixed, using alpha.7's own unmodified
classifier purely to describe what Core Seeker's own existing geometric
model already predicts there — not part of selection): both conditions
classify as substantially "robust"/"reachable" for Core Seeker's own
existing schedule (§20 has the exact breakdown), meaning these held-out
placements are, honestly, non-adversarial to the historical control — a
fair, uncherry-picked pair of "ordinary" new placements, not a second COLD
condition.

## 18. Exact held-out positions

| Condition | A | B | C |
|---|---:|---:|---:|
| `heldout_even_eighths` | 512 | 1536 | 2560 |
| `heldout_pi_digits` | 1073 | 1415 | 3589 |

## 19. Three-way matrix (Phase 17)

Both attackers (`core_seeker`, `core_tracker`), all six placement
conditions (alpha.7's four in-sample conditions plus the two held-out
conditions above), the same three matchup classes alpha.5/alpha.7 already
established (A: `claimer`+attacker+`core_defender`; B: `claimer`+attacker+
`reactive_core_defender`; C: `claimer`+`hunter`+attacker), 3 cyclic seat
rotations each, seed 1 throughout (every agent in this pool, including
`core_tracker`, is deterministic given a fixed seed — confirmed directly,
§14) — **108 matches** (2 × 6 × 3 × 3), all run through a small, disclosed
extension of alpha.6's own `trace_match_custom` harness
(`runs/v2_0_alpha8_placement_agnostic_offense/run_evaluation_v8.py`; see
that file's own docstring for exactly why a thin, additive wrapper was
needed rather than editing alpha.6's own committed script — its hardcoded
reference-agent name set predates `core_tracker`'s existence, and the
actual simulation logic, `_run_traced`, is imported and reused completely
unmodified). Plus the 12-match pre-matrix (§16). **Zero infrastructure
failures across all 120 matches.** Total wall time for the 108-match
three-way matrix: 4.08 seconds.

## 20. Placement sensitivity: old Seeker vs. new attacker (Phase 19)

The central comparison, per condition, over the 9 matches (3 classes × 3
rotations) each attacker played at each placement:

| Condition | Core Seeker: ≥1 full-covering assault? | Core Seeker captures | Core Tracker: ≥1 full-covering assault? | Core Tracker captures |
|---|---|---:|---|---:|
| control | yes (seat B) | 2 | **yes** (seats A, B) | 1 |
| **cold** | **no** | **0** | **yes** (seat C) | 0 (full coverage; defender won the reclaim race in this corpus — see §16 for the 2-entrant pairing where it *did* capture) |
| hot | yes (seats A, B, C) | 4 | yes (seats A, B, C) | 1 |
| mixed | no (only via ownership overlap, not Seeker's own assault) | 1 (ownership overlap) | **yes** (seats A, B) | 3 |
| heldout_even_eighths | yes (seat C) | 1 | yes (seat A) | 0 |
| heldout_pi_digits | yes (seat C) | 2 | yes (seat C) | 1 |
| **Conditions with ≥1 full-covering assault** | **4 / 6** | — | **6 / 6** | — |
| **Total captures (three-way matrix)** | — | **10** | — | **6** |

**Core Seeker: full-core-covering assaults in 4/6 conditions, zero in
COLD.** **Core Tracker: full-core-covering assaults in 6/6 conditions,
including COLD and MIXED — the two conditions where Core Seeker's own
assault mechanism produces no genuine covering window at all.** This is
the direct, quantitative confirmation of this alpha's central hypothesis:
placement sensitivity is materially lower for the new attacker,
demonstrated on conditions selected by mechanical formula, not chosen
after seeing which one would make the comparison look best (the COLD
condition is alpha.7's own, reused unmodified; the two held-out conditions
were, if anything, mildly *favorable* to Core Seeker by informational
classification, §17, so this is not a result manufactured by adversarial
condition selection).

Core Tracker's own total capture count (6, plus 2 more in the
pre-matrix — 8 total) is lower than Core Seeker's (10) in this specific
compact corpus. This is reported honestly, not minimized: Core Tracker
achieves *pressure* (full coverage) far more broadly, but full coverage
does not guarantee capture — the reclaim race (alpha.6 §14/§21) still
governs whether an assault actually finishes the job, and Core Defender/
Reactive Core Defender still win that race often against the new attacker
too (§23). Search quality and kill power are genuinely separate
questions here, exactly as the governing task's own Phase 20 anticipated.

## 21. Worst-placement performance (Phase 19)

Core Seeker's worst placement is COLD: 0/6 seats ever showed a covering
assault window, 0/9 matches captured, by construction (COLD's three
addresses were specifically selected in alpha.7 as the nearest-to-
historical addresses classified geometrically unreachable). Core Tracker's
worst placements, by capture count, are COLD and heldout_even_eighths (0
captures each in the three-way matrix) — but both still show real,
attributable full-core-covering assault pressure (COLD: seat C, both
`core_defender` occurrences reaching full 8/8 coverage, §16 additionally
showing an actual capture in the simpler 2-entrant pairing;
heldout_even_eighths: seat A, one occurrence). No placement tested left
Core Tracker with zero search-quality signal at all — a materially
different worst case than Core Seeker's COLD result.

## 22. Confirmation quality by opponent type (Phase 20/21)

From the pre-matrix (§16), directly measured:

| Opponent | Candidates investigated | Confirmed & assaulted | Confirmation rate |
|---|---:|---:|---:|
| claimer | 65–68 | 5 | 7.4%–7.7% |
| hunter | 57–59 | 14–16 | 23.7%–28.1% |
| core_defender | 2–36 | 1–26 | 50.0%–72.2% |
| reactive_core_defender | 37–40 | 25–27 | 67.5%–67.6% |

This tracks the underlying mechanism exactly (§6): Claimer/Hunter never
sign or defend their own core, so most of their core cells stay at the
seeded value `0` (indistinguishable from untouched arena) for long
stretches, and confirmation correctly fails most of the time; Core
Defender/Reactive Core Defender actively write recognizable content across
their whole core, and confirmation succeeds much more often. This is
direct, quantitative evidence that `core_tracker`'s search step is doing
real discriminating work tied to actual content, not simply committing to
assault on autopilot.

## 23. Core Defender / Reactive Core Defender results (Phase 17/22)

| Attacker | Defender | Occurrences | Captured | Survived |
|---|---|---:|---:|---:|
| core_seeker | core_defender | 18 | 1 | 17 |
| core_seeker | reactive_core_defender | 18 | 1 | 17 |
| core_tracker | core_defender | 18 | **0** | **18** |
| core_tracker | reactive_core_defender | 18 | **2** | 16 |

Core Defender survived every occurrence against `core_tracker` in the
three-way matrix (0/18), despite `core_tracker` achieving *more*
full-covering assaults against it across more conditions than Core Seeker
did (§16, §20) — direct, unambiguous evidence that discovery and kill
power are separate (§20). Reactive Core Defender, by contrast, was
captured twice by `core_tracker` (control @ tick 189, hot @ tick 103) —
notably, **captured in the control condition**, the one placement where no
defender of either kind has ever been captured anywhere in alphas 1
through 7 of this research series (alpha.1–alpha.7's unbroken record was
0/N control-condition defender captures). This is a genuinely new,
specific finding this alpha's own broader search geometry produced, not a
re-observation of an existing pattern.

## 24. Claimer/Hunter incidental capture findings and specialized-vs-blind comparison (Phase 21)

Across the three-way matrix, both attackers' captures were classified by
whether the credited killer was the attacker itself (search-mediated) or
a different entrant (incidental, e.g. alpha.7's own MIXED ownership-
overlap finding, §15 of that document):

| Attacker | Total captures | Claimer/Hunter victims | Search-mediated | Incidental (blind overlap) |
|---|---:|---:|---:|---:|
| core_seeker | 10 | 8 | 7 | 1 (the MIXED condition's known ownership-overlap capture) |
| core_tracker | 6 | 4 | **4** | **0** |

Every one of `core_tracker`'s captures in this corpus was attributable to
its own deliberate search-then-assault sequence, not incidental blind
overlap — direct evidence that specialized offense is buying something
real here, not merely riding along on ordinary expansion's own incidental
capture rate. `claimer`/`hunter` themselves were never observed
incidentally capturing anything in this corpus (as opposed to being
captured) — consistent with alpha.4/alpha.5/alpha.6/alpha.7's own
established finding that blind sweeps rarely produce captures at all,
Vulnerable Core's ownership-overlap pathway notwithstanding.

## 25. Defense timing findings (Phase 22)

Capture ticks observed for `core_tracker`: cold pre-matrix @ 27,
heldout_even_eighths pre-matrix @ 196, control @ 189, hot @ 103, mixed @
117 (×2), mixed @ 122, heldout_pi_digits @ 129 — a materially wider spread
(27 through 196) than Core Seeker's own historical cluster (tick 159–168
in control, per alpha.6 §11, with HOT moving it earlier to 55–61, alpha.7
§17). This is consistent with the governing task's own Phase 22 question:
a more placement-agnostic attacker does produce a wider distribution of
attack timing than the old fixed-schedule attacker's narrow, delay-
dominated cluster — though this alpha does not attempt the sub-tick
reclaim-race mechanism alpha.7 §21/§27 left open (out of scope here, §33).

## 26. Territory/score opportunity cost (Phase 6/13, repeated for the report outline)

See §13 for the full account: `core_tracker` spends more total actions on
ordinary expansion on average (549.9/match) than Core Seeker (474.5/match)
despite also spending a real, measurable 235.7 actions/match on probe
reads Core Seeker has no equivalent of — because its false positives are
individually much cheaper (≈5 actions to investigate-and-abandon vs. Core
Seeker's full 16-action commitment to nearly every hit). Search has a
real, disclosed cost for both agents; it is shaped differently, not simply
"more" or "less."

## 27. Dominance assessment (Phase 23)

`core_tracker` does not dominate this corpus: Core Defender survived every
occurrence against it (§23); Claimer and Hunter were captured at a lower
absolute rate than under Core Seeker in this specific compact corpus
(§20); its total capture count (8 across pre-matrix + three-way matrix) is
lower than Core Seeker's (10) despite reaching full coverage in more
conditions. This is the "qualified support" shape the governing task's own
Phase 24 anticipates as a legitimate, non-manufactured outcome — broader
placement generality with a real, disclosed opportunity cost and no
universal win rate — not the "new attacker dominates everything" bad-sign
pattern.

## 28. Held-out generalization assessment (Phase 24)

Both held-out conditions, generated mechanically and without reference to
either attacker's design (§17), show `core_tracker` achieving full-core-
covering assaults (§20: seat A at heldout_even_eighths, seat C at
heldout_pi_digits, the latter with a real capture). Because these
conditions were, if anything, mildly favorable to Core Seeker's own
existing geometry too (informational classification, §17), they are not
by themselves as sharp a differentiator as COLD — but they are exactly
the right kind of unbiased check: `core_tracker` performs comparably well
on them without having been designed around their specific addresses,
which is the generalization property this alpha set out to demonstrate.
Combined with the COLD result (§16, §20 — the one condition Core Seeker
provably cannot reach at all, where `core_tracker` both achieves full
coverage in the three-way matrix and a real capture in the 2-entrant
pre-matrix), the generalization evidence is strong.

## 29. Is the new agent a valid general offense benchmark? (Phase 24)

Yes, with the qualifications this alpha's own evidence supports directly:
it discovers and pressures cores across every placement condition tested,
including the one placement provably unreachable by the prior benchmark
and two mechanically-generated conditions selected before any of its own
results were known; it operates through ordinary `READ`/`WRITE` only, with
no privileged information (§5); it has no stale-read echo defect (§10,
proven by three dedicated tests); its confirmation step measurably
discriminates real content from noise (§12, §22); it pays a real,
measurable, differently-shaped opportunity cost rather than searching for
free (§13, §26); it does not dominate — defenders sometimes still win
(§23, §27); and specialized search-based offense demonstrably outperforms
blind incidental capture in this corpus (§24). It is not a "solved"
attacker and should not be read as one: Claimer/Hunter's low confirmation
rate (§22) and Core Defender's clean 0/18 survival against it (§23) are
real, disclosed limitations, not results to explain away.

## 30. Implications for Vulnerable Core (Phase 24, mechanic-level)

Strengthens, rather than revises, alpha.7's own already-strengthened
verdict (that alpha's §31): genuine core capture is now demonstrated
through a *second*, structurally different, non-privileged attacker,
including at the one placement (COLD) the *original* attacker could never
reach at all — direct evidence that Vulnerable Core's practical
offense/defense dynamic is a property of the mechanic and the available
information, not an artifact specific to Core Seeker's own particular
fixed schedule. No mechanic-level concern is raised by this alpha (the
"Mechanic concern" falsification tier, governing task Phase 24, does not
apply): a legitimate placement-agnostic searcher does generate meaningful
pressure across every placement tested.

## 31. alpha.1–alpha.7 conclusions preserved/refined (Phase 24)

All preserved; two refined with new, specific evidence:

- Alpha.6/alpha.7's characterization of Core Seeker itself (a legitimate,
  narrow, fully-traceable characterization fixture, not a general offense
  benchmark) is now sharpened by direct contrast rather than merely
  reasserted: this alpha shows concretely what a *broader* design looks
  like and by how much placement sensitivity actually differs (4/6 vs.
  6/6 conditions with covering assaults, §20).
- Alpha.2's "reactive defense reliably survives Core Seeker" finding, and
  alpha.7's own qualification of it (survival is a timing-sensitive
  reclaim race, not a fixed property, alpha.7 §21/§27), both gain a new
  data point: Reactive Core Defender's first-ever **control-condition**
  loss (§23) shows the reclaim race can be lost even in the one placement
  every prior alpha found it always won, once the attacker's own timing
  distribution (§25) is no longer tied to Core Seeker's narrow, late,
  delay-dominated schedule.

## 32. Falsification/success verdict (Phase 24)

**Strong support**, against the governing task's own bar: the new attacker
finds and attacks cores across control, COLD, HOT, MIXED, and both
held-out placements (§20); it operates only through ordinary API reads/
writes (§5); it has no stale-read echo bug (§10); placement sensitivity is
materially lower than Core Seeker's (4/6 → 6/6 conditions with any
covering assault, and specifically succeeding at the one condition Core
Seeker cannot reach at all, §20); search has a real, measurable action/
territory cost (§13, §26); defenders sometimes survive (Core Defender:
18/18 against this attacker, §23); expansion strategies remain viable
(Claimer/Hunter were still only rarely captured, §20, §24); and
specialized offense outperforms blind incidental capture without becoming
universal (§24, §27). None of the "Reject/redesign" tier's conditions
apply: performance is not tied to fixed absolute regions (§9, §20); the
held-out placements did not fail (§28); confirmation clustering works and
discriminates real content from noise, not everywhere but meaningfully
(§12, §22); false positives do not dominate the budget (§13, §26); it does
not require privileged information (§5); and it is not "Core Seeker with
a different stride" — it is a structurally different confirmation and
scan-anchoring mechanism (§8–§10), independently verified not to overfit
alpha.7's own positions (§17, §26, §28).

## 33. Unresolved questions (Phase 24)

- The exact sub-tick reclaim-race mechanism behind Core Defender's clean
  0/18 survival against `core_tracker`, and behind the specific control-
  condition loss Reactive Core Defender suffered at tick 189 (§23) — would
  require replaying the precise interleaving of this agent's assault burst
  against the defender's own refresh/patrol cadence, not done here,
  exactly the kind of question alpha.7 §21/§27 already left open for a
  future, separately-scoped defense-timing alpha.
- Whether a different `PROBE_OFFSETS`/`CONFIRM_MIN_HITS` choice would
  shift the confirmation-rate/false-positive tradeoff meaningfully — not
  explored, per the governing task's own "do not iteratively tune against
  tournament results" instruction (§15).
- Seat C's general territorial win-rate advantage (alpha.5 §24, carried
  forward unresolved through alpha.6/alpha.7) remains fully open — out of
  this alpha's scope by design, and this alpha's compact, offense-focused
  corpus does not speak to it either.
- Whether `core_tracker`'s lower total capture count in this specific
  compact corpus (8 vs. Core Seeker's 10, §20) would persist, invert, or
  converge across a larger, more varied real-agent population — this
  alpha's own discipline (a moderate, stratified matrix, not an exhaustive
  sweep) does not attempt to answer that by itself.

## 34. Baseline reconciliation note (Phase 31)

Directly measured on this machine, via `git stash`, immediately before any
alpha.8 file existed: `pytest --collect-only` on the unmodified alpha.7
HEAD (`7244823`) collects **1541** tests (post `-m "not gui"` filtering);
running them gives **1535 passed, 6 skipped, 0 failed**. The governing
task's own documented alpha.7 baseline states **1543 total / 1537 passed /
6 skipped**, a 2-test gap from what this machine measures right now on the
identical, unmodified commit. This gap **predates alpha.8 and is not
caused by any change in this alpha** — confirmed directly, not assumed, by
stashing every alpha.8 file and re-collecting before restoring them; the
same 2-test gap is present with or without alpha.8's changes. With
alpha.8's changes restored: `pytest --collect-only` collects **1560**
tests — an exact **+19** relative to this machine's own freshly-measured
pre-alpha.8 baseline, matching `test_v2_alpha8_core_tracker.py`'s 19 tests
precisely, with zero tests removed or altered in count. Full run with
alpha.8's changes: **1554 passed, 6 skipped, 0 failed** (1560 total). This
is reported honestly rather than silently reconciled against the
documented figure: the delta this alpha is responsible for is unambiguous
(+19, 0 regressions) regardless of the small pre-existing baseline
discrepancy, whose root cause (environmental, session-to-session, or some
other pre-existing factor) was not investigated further as out of this
alpha's scope.

## 35. Regression qualification (Phase 31)

| Check | Result |
|---|---|
| `test_v2_alpha8_core_tracker.py` (new, focused) | **19 / 19 passed** |
| Alpha-focused suites (alpha.1/1.1/2/4/4.1) | passing, unchanged |
| `test_ruleset_v1_equivalence.py` | passing, unchanged |
| Full `pytest` (this machine, alpha.8 applied) | **1554 passed, 6 skipped, 0 failed** (1560 total) |
| Full `pytest` (this machine, alpha.8 stashed out — pre-alpha.8 baseline) | 1535 passed, 6 skipped, 0 failed (1541 total) |
| Net effect of alpha.8 | **+19 passed, 0 skipped change, 0 failed, 0 regressions** |
| Ruff (repo-wide) | clean, 0 errors |
| mypy (`engine/src/battle_engine`) | clean, **70 files** (was 69) |
| mypy (`client/src/battle_client`) | clean, 10 files |
| `git diff -- engine/src/battle_engine/data/reference_agents/core_seeker` | empty (byte-for-byte unchanged) |

No unexplained failures. The only discrepancy found (§34) was actively
investigated (via `git stash` differential, not assumed) and shown to
predate this alpha's own changes entirely.

## 36. Research artifacts (Phase 30)

`runs/v2_0_alpha8_placement_agnostic_offense/` (gitignored under the
existing `runs/` precedent, confirmed via `git check-ignore -v`; this
document is the durable, committed record): `held_out_placements.py`
(§17's generator, also writes `held_out_placements.json`),
`run_evaluation_v8.py` (the pre-matrix + three-way matrix driver, §16/§19,
reusing alpha.6's `_run_traced` directly and alpha.7's `seat_rotations`/
`core_cells`/`extract_scan_events`/`extract_assault_episodes`/
`overlap_report` directly, also writes `raw_matches.json`), `analyze.py`
(pure post-processing of `raw_matches.json`, no match execution, also
writes `analysis_summary.json`).

## 37. Recommended alpha.9 direction (Phase 25)

**A — Defense robustness.** This alpha's own evidence points here directly
and specifically, more than to any other listed option: `core_tracker`
produces a materially wider, less-predictable distribution of attack
timing and placement than Core Seeker ever did (§20, §25), and that wider
distribution already found a genuinely new defensive failure mode this
series had never observed before — Reactive Core Defender losing in the
**control condition** (§23, §31), the one placement its reclaim race has
won in every prior alpha. Not **B** (offense refinement): this alpha found
no single, well-defined conceptual limitation worth an isolated follow-up
correction (§15) — the design qualified on its first pre-matrix pass, and
its remaining known limitation (low confirmation rate against undefended
opponents, §22) is an honest reflection of the underlying information
constraint (§6), not a fixable implementation gap. Not **C** (broader
Ruleset v2 mechanics): offense/defense interaction is now demonstrated
more thoroughly than at any prior point in this series (two structurally
different attackers, six placement conditions, real capture and real
survival evidence for both), and moving to broader mechanics now would
leave the freshly-discovered control-condition defender loss (§23)
uninvestigated for no evidentiary reason. Not **D** (core/scoring
redesign): nothing in this alpha's results suggests a deeper strategic
problem with Vulnerable Core itself — if anything, §30 strengthens its
viability further. Not **E** (seat-C territorial geometry): still a
legitimate open question (§33) but no more directly implied by this
alpha's own central finding than **A** is.

## 38. Commit and final state (Phase 32)

Committed locally on `v2.0-development` only. No merge, rebase, cherry-
pick, tag, or push performed. `origin`'s unrelated commit `151866c` was
left untouched throughout, exactly as instructed.
