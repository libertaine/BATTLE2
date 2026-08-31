# Bytefray v2.0.0-alpha.1 — Vulnerable Core: Implementation & Evaluation

This is the implementation and evaluation record for the first Bytefray
v2 experimental ruleset, `bytefray-rules-2-alpha1` ("Vulnerable Core"),
built on top of the research/architecture pass recorded in
[V2_0_ALPHA_ARCHITECTURE.md](V2_0_ALPHA_ARCHITECTURE.md). It records what
was actually implemented, what the controlled evaluation actually
measured, and an honest, falsifiable recommendation — not a claim that
the mechanic is finished or should ship.

Branched from the verified v1.6.0 baseline
(`5593d287f95a24996bb3b105befbc625a00795db` — `main` = `origin/main` =
`v1.6-development` = the `v1.6.0` tag) on the `v2.0-development` branch,
one commit ahead of that baseline (the architecture-only documentation
commit). This document is committed alongside the implementation itself;
`git log` on `v2.0-development` is the authoritative record of the exact
commit this evaluation ran against.

## 1. Ruleset identity and compatibility

- New identity: **`bytefray-rules-2-alpha1`** (`BYTEFRAY_RULESET_V2_ALPHA1_ID`
  in `ruleset_policy.py`) — never `bytefray-rules-2`, and never aliased to
  or from `bytefray-rules-1` anywhere (`rules.py`'s `_RULESET_ALIASES`
  table has no entry for it).
- `bytefray-rules-1` (`BYTEFRAY_RULESET_ID`) is untouched: `vm.py`,
  `scoring.py`, `results.py`, `ruleset_policy.RULESET_V1`, and every
  existing call site that never sets `MatchRequest.ruleset_id` continue to
  resolve to it exactly as before this alpha existed.
- `MatchRequest.ruleset_id: str | None = None` is the one new selector
  (`match_service.py`). `None` resolves to `BYTEFRAY_RULESET_ID`
  (`_resolve_ruleset_id`), so every existing caller is unaffected.
  `NativeMatchService.run` resolves this once and dispatches through the
  existing fail-closed `resolve_ruleset_policy` seam — an unrecognized ID
  (including a bare `bytefray-rules-2` typo) raises `UnknownRulesetError`
  rather than silently running as v1.
- **Persistence-identity gap found and fixed.** Before this work,
  `canonical_match_id` and `_finalize_native_artifacts` both hard-coded
  `BYTEFRAY_RULESET_ID` into the replay header's and result envelope's
  `ruleset_id` fields and into the `match_id`/`result_id` hash payload,
  *regardless of what `MatchRequest.ruleset_id` actually was* — so an
  alpha match's persisted artifacts would have silently masqueraded as
  Ruleset v1. Both now use the same resolved identity the dispatch call
  used (`_resolve_ruleset_id`), so an alpha match's `replay.jsonl` header,
  `result.json` envelope, and `match_id`/`result_id` all correctly record
  `bytefray-rules-2-alpha1`, and two otherwise-identical inputs run under
  the two different Rulesets now hash to different `match_id`/`result_id`
  values (`test_alpha_and_v1_produce_different_match_identity_for_equivalent_inputs`).
  `evaluation_history/comparison.py`'s existing `_rules_id`-based alignment
  refusal (pre-existing, `EVALUATION_RULES_COMPATIBILITY_ID`-driven) already
  refuses to align cells across differing `rules_id`s; a focused test
  (`test_v2_alpha1_rules_id_never_aligns_against_v1`) proves this covers the
  literal alpha identity too. `agent_evaluation.EvaluationService` itself was
  not threaded with `ruleset_id` (see §7, Scope decisions) — no real alpha
  evaluation summary can be produced through that CLI pipeline yet, so this
  is a guard against a future extension, not a currently-reachable path.

## 2. Core geometry

```
core = [entrant.start % arena_size, entrant.start % arena_size + CORE_SIZE) mod arena_size
```

`CORE_SIZE = 8` (`python_runtime.CORE_SIZE`), a fixed module constant, not
threaded through `Config` (per the governing task's instruction not to make
it configurable for this alpha). Chosen, not computed: Python entrants
place no code in the arena at all (unlike the VM path, which has a real
per-entrant code footprint via `VM.load_code` to reason a size against), so
there was no existing "footprint" to size a core from in the first place.
Against the default `arena_size = 4096`, 8 cells is 0.2% of the arena —
small enough to be a genuine localized target an opponent must actually
find and fully overwrite, not a proxy for general territorial dominance,
while still being more than one cell so a single incidental write can't
end a match by accident. `core_addresses()` uses ordinary `pos % arena_size`
wrap, verified to wrap correctly across the arena boundary
(`test_core_addresses_wraps_across_arena_end`).

**Core-capture semantic** (Phase 4's definition, used exactly as given):
a living Python entrant is core-captured when it owns **zero** cells of
its own core region — not "one opponent owns 100% of it" — so the rule
stays well-defined for more than two entrants, and reduces naturally to
complete displacement in the two-entrant case.

**A necessary implementation detail beyond the architecture doc's own
description, forced by the semantics above:** Python entrants never place
code in the arena, so "owns zero cells" would be *vacuously true before
tick one* without an explicit spawn-time step — the mechanic would capture
every entrant on its first check, before any `act()` call ever ran.
`seed_core_ownership()` establishes each entrant's ownership of its own
core at construction time (routed through `VM._wr8`, exactly like any
other write, so it appears in tick zero's replay diffs precisely as
`VM.load_code` already does for the VM path) — the Python-runtime
equivalent of the VM's own code-placement-establishes-ownership behavior.
Only called under `bytefray-rules-2-alpha1`; a Ruleset-v1 Python match's
tick-zero `memory_diffs` stay empty exactly as before.

**Check timing and lifecycle:** checked once per tick, immediately after
that tick's actions execute and before scoring — so a captured entrant
receives no alive/territory credit for the tick it dies on, exactly
matching existing Python `HALT` semantics, and no hidden extra turn.
Confirmed by `test_full_capture_within_one_tick_kills_immediately_with_attribution`
and `test_deterministic_capture_timing_spreads_across_ticks` (capture lands
on the exact tick the last core cell flips, whether that's tick 1 with a
high per-tick budget or tick 8 with a budget of one core-cell write per
tick).

**Kill attribution:** credited to whichever entrant's `WRITE` caused the
final defender-owned core cell to change owner *this tick*, found by
replaying that tick's `vm.tick_diffs` restricted to the core's addresses,
starting from a pre-action snapshot of who owned each core cell before
that tick's actions ran (`_attribute_core_capture`) — unambiguous by
construction, since diffs replay in true execution order and only one
write can be "the write that took the last cell." The one edge case where
attribution genuinely cannot be determined — two entrants spawned with
fully overlapping cores, so the second entrant's spawn-time seeding
overwrites the first's core ownership before tick one even begins — is
recorded as an unattributed death (no kill credit invented), covered by
`test_capture_attribution_unattributed_when_core_already_lost_before_the_tick`.
This is a pathological, non-recommended configuration (see §3's
placement rule, which keeps the evaluation matrix's cores far apart), not
a state normal play reaches.

**No new termination-reason value was needed.** `"core_captured"` is a new
value of the existing per-entrant `termination_reason` string field
(`PythonEntrantState.entrant_termination`, already a free-form string
accepting `"normal_halt"`/`"forfeit"`) — exactly parallel to how a VM kill
never introduces a new *match-level* `TerminationReason`. The match-level
enum (`ALL_AGENTS_DEAD`/`LAST_AGENT_STANDING`/`TICK_LIMIT`) and
`RulesetPolicy.resolve_termination`'s three-argument signature are
untouched; a core-captured entrant's death simply feeds into the existing
alive-count-based termination decision exactly like any other death.

**VM untouched.** No change to `vm.py`, `core.py`, `match.py`, `scoring.py`,
or `results.py` — the mechanic is Python-runtime-only
(`python_runtime.py`/`supervised_runtime.py`), per the governing task.

## 3. Start placement

`agent_test.test_agent()` gained three additive, default-preserving
parameters: `ruleset_id: str | None = None`, `agent_start: int = 0`,
`opponent_start: int = 0`. Every existing caller (the `bytefray agents
test` CLI, `agent_evaluation._execute_cell`, every pre-existing test) sees
byte-for-byte unchanged behavior — both entrants still constructed at the
literal shared address `0`, under the frozen v1 identity
(`test_agent_test_default_start_placement_is_unchanged`).

For the alpha evaluation matrix (and any future alpha caller), placement
is: **subject at `0`, opponent at `arena_size // 2`** — for the default
`arena_size = 4096`, that's `0` and `2048`. This is not an invented
convention: it is the exact placement the VM path's own
`test_ruleset_v1_golden_equivalence` two-way fixture already uses
(`_vm_default_two_way_request`: `"A"` at `0`, `"B"` at `2048`), and the
same slot-times-2048 pattern `_python_starter_request` already uses for
its own two-entrant fixture. Reused, not reinvented.

## 4. Reference agents

Two new experimental/reference agents, packaged like a starter agent
(manifest + `agent.py`) but loaded from a dedicated
`battle_engine/data/reference_agents/` resource root via
`reference_agents.reference_agent_spec()`, mirroring
`agent_test._reference_opponent_spec`'s own "loaded from a resource, never
added to the writable/discoverable catalog" pattern. Deliberately **not**
added to `battle_engine.starters.STARTER_AGENT_NAMES` — they exist to
evaluate one experimental Ruleset, not to join Bytefray's permanent
default roster shown to every user regardless of which Ruleset they run.

- **Core Defender** (`core_defender`): every 4th action refreshes one cell
  of its own core (cycling through all 8), the other 3 of every 4 are an
  ordinary Claimer-style blind sweep starting just past its own core. Its
  own core anchor is captured from `observation.pc` on the first `act()`
  call (never given for free — the same value the entrant's own `pc` is
  already initialized to before any `JUMP`).
- **Core Seeker** (`core_seeker`): 1 action in 3 is a `READ` at a slowly
  advancing scan cursor; a byte that is neither the arena's untouched
  default (`0`) nor the seeker's own signature is treated as
  "foreign-looking." Two foreign-looking hits within `LOCK_RADIUS` (12) of
  each other trigger a committed 16-action `WRITE` burst centered on the
  detected cluster; the other 2 of every 3 non-burst actions are an
  ordinary outward claiming sweep. Never given the opponent's position —
  `Observation` exposes none, so there is nothing to read even if it
  wanted to.

Both load through the real Agent API v1 contract
(`load_python_agent`) and run full matches without forfeiting under both
Rulesets (`test_v2_alpha1_reference_agents.py`). Core Seeker was directly
observed locating and capturing Core Defender's core in real play (not
just scripted isolation tests) at tick 140 of a 200-tick match, seed 1
(`test_core_seeker_can_locate_and_capture_core_defenders_core`).

## 5. Focused tests (Phase 8)

`test_ruleset_v2_alpha1.py` (19 tests) and `test_v2_alpha1_reference_agents.py`
(9 tests) cover: Ruleset dispatch and unknown-ID fail-closed behavior,
`MatchRequest.ruleset_id`'s default and propagation, fixed core geometry
including arena wrap, core ownership seeding/accounting, full and gradual
capture, no premature capture, deterministic capture timing, kill
attribution (including the one unattributable edge case), core wrapping
across the arena end, ownership changing away and back before completing
capture, an entrant writing into its own core never self-capturing, the
"captures all but one cell then the final cell flips" progression,
matches terminating for another valid reason (`HALT`) before any capture,
self-match support, Ruleset-v1 Python matches never core-capturing even
when fully overwritten by the identical scripted attack, distinct-start
support via `agent_test.py`, and replay/result Ruleset-identity
persistence for both conditions. `test_ruleset_policy.py` and
`test_evaluation_history_comparison.py` each gained a small number of
additional focused tests for the dispatch registration and the
comparison-machinery non-conflation guard respectively.

One pre-existing, unrelated `test_reference_agents.py` (VM
`builtins.registry` instruction fixtures) already occupied that filename;
the new reference-agent tests live in `test_v2_alpha1_reference_agents.py`
instead, and the pre-existing file is untouched.

## 6. Evaluation matrix

- **Agents:** the five existing Python starters (claimer, strider, hunter,
  wanderer, adaptive) plus the two new reference agents (core_defender,
  core_seeker) — 7 agents.
- **Matchups:** every unordered pair (21), both orientations (42 ordered
  matchups); the entrant playing the "subject" role of a given ordered
  matchup always starts at `0`, the "opponent" role always at `2048`
  (§3). No self-play matchups in the matrix (self-match support is
  covered separately as a focused unit test, §5).
- **Seeds:** `1, 2, 3, 4, 5` — the exact example seed set used throughout
  `README.md`/`docs/AGENT_LAB.md`.
- **Conditions:** `bytefray-rules-1` (control) and `bytefray-rules-2-alpha1`
  (experimental), `Config` otherwise at defaults (`arena_size=4096`,
  `instr_per_tick=8`) and the existing `agents test`/`evaluate` tick
  budget (`200`) — no arena-size/information-density variation combined
  into this alpha, per the governing task.
- **Total:** 42 matchups × 5 seeds × 2 conditions = **420 matches**, run
  directly through `NativeMatchService` (the same production execution
  boundary every other native match uses) by
  `runs/v2_0_alpha1_evaluation/run_evaluation.py`. Completed in ~48s.
  Statistics reuse the existing `battle_engine.evaluation_analysis` Wilson
  interval and exact-sign-test machinery unchanged; no new statistical
  framework was written. Raw per-match records and the computed summary
  are in `runs/v2_0_alpha1_evaluation/{raw_matches,summary}.json`
  (untracked local scratch, per `.gitignore`'s existing `runs/` entry and
  the same precedent `runs/research_v0.9`/`runs/research_v0.10` already
  established — this document is the durable, committed record).

### Termination distribution

| Ruleset | tick_limit | last_agent_standing | all_agents_dead |
|---|---|---|---|
| `bytefray-rules-1` | 210 (100%) | 0 | 0 |
| `bytefray-rules-2-alpha1` | 194 (92.4%) | 16 (7.6%) | 0 |

Zero core captures occurred under `bytefray-rules-1` (expected — the
mechanic does not exist there; `test_v1_python_matches_never_core_capture_even_when_fully_overwritten`
already proves this at the unit level with the identical scripted attack
that *does* capture under the alpha condition). Under the alpha condition,
**7.6% of matches (16/210) ended via core capture** — a real, meaningful,
bounded frequency: neither "almost never" nor "collapses ordinary play."
92.4% of alpha matches still terminated by the ordinary historical
mechanism (`tick_limit`), directly answering Phase 9's Q8.

### Core-capture rate by entrant and matchup (Q7)

Every one of the 16 captures has **Core Seeker as the capturing entrant**
and one of the following as the victim: strider (5/5 seeds), hunter (5/5
seeds), core_defender (5/5 seeds), wanderer (1/5 seeds). **Zero captures
were ever caused by an ordinary blind-expansion strategy** (Claimer,
Strider, Hunter, Wanderer, Adaptive, or Core Defender's own outward-sweep
portion) acting as the attacker — including Claimer, which was never
core-captured a single time across all 30 of its alpha-condition matches,
and never captured an opponent either.

This has a clean mechanical explanation, not a placement artifact
(confirmed directly: captures track the *agent playing Core Seeker*, not
which position — `0` or `2048` — an agent happened to occupy that match):
`instr_per_tick=8` and `max_ticks=200` give each entrant at most 1,600
actions for the whole match, against an `arena_size` of 4,096 — a coprime
blind sweep needs up to the full 4,096 steps to guarantee visiting every
address in a specific fixed 8-cell window at least once, so **an ordinary
undirected sweep has a real chance of never fully covering any one
particular small window within this budget at all.** Core Seeker's
directed `READ`-then-commit design reliably converges once it finds
something instead of relying on blind coverage, which is exactly why it
is the only strategy in this population that ever captures anything.

### Win-rate deltas (v1 → alpha1), with Wilson 95% intervals

| Agent | v1 win rate (n=30) | alpha1 win rate (n=30) | alpha1 core-captured rate |
|---|---|---|---|
| claimer | 100.0% [88.6%, 100%] | 83.3% [66.4%, 92.7%] | 0.0% |
| strider | 66.7% [48.8%, 80.8%] | 50.0% [33.2%, 66.8%] | 16.7% |
| hunter | 83.3% [66.4%, 92.7%] | 66.7% [48.8%, 80.8%] | 16.7% |
| wanderer | 50.0% [33.2%, 66.8%] | 43.3% [27.4%, 60.8%] | 3.3% |
| adaptive | 16.7% [7.3%, 33.6%] | 16.7% [7.3%, 33.6%] | 0.0% |
| core_defender | 16.7% [7.3%, 33.6%] | 0.0% [0%, 11.4%] | 16.7% |
| core_seeker | 16.7% [7.3%, 33.6%] | 16.7% [7.3%, 33.6%] | 0.0% |

Every win-rate drop is fully explained by one of two mechanisms, verified
directly against the raw per-match records:

1. **Direct capture losses**, one-for-one against the capture counts above
   (strider: 5 captures → 5 fewer wins; hunter: 5 → 5; core_defender: 5 →
   5; wanderer: 1 of its 2 regressions).
2. **A small, symmetric score-margin effect from core-seeding itself.**
   `seed_core_ownership` gives each entrant 8 pre-owned cells at tick zero
   that do not exist under Ruleset v1 — a deliberate, necessary,
   *mutually* applied consequence of the capture mechanic needing
   something to capture (§2), not a bug. At sufficiently close raw score
   margins (`claimer` vs `hunter`, all 5 seeds: `2281` → `2294`; `wanderer`
   vs `adaptive`, seed 4: `2183` → `2193`), this shifts which side of a
   `territory_bucket`-quantized `score_fallback` comparison an entrant
   lands on, flipping a `win` to a `loss` with **no capture event
   involved at all**. This accounts for exactly 6 of the 22 total
   regressed pairs (claimer's entire 5-win drop, plus 1 of wanderer's 2).

The paired exact-sign test (`bytefray-rules-2-alpha1` vs `bytefray-rules-1`,
matched by identical subject/opponent/seed, `improved`/`regressed` per the
existing `win > tie > loss` `classify()` convention) over all 210 paired
cells: **0 improved, 22 regressed, 188 unchanged** (exact two-sided
p ≈ 4.8×10⁻⁷, direction `favors_baseline`). No subject's outcome ever got
*better* under the alpha condition for the identical matchup/seed — every
change was a strict downgrade, whether capture-caused or
score-margin-caused.

### Territory retention (Q6)

`territory_retention` (`last / max`) means were effectively unchanged
between conditions for every agent (claimer/strider/hunter/wanderer/
core_seeker: ≈1.0 in both; adaptive: ≈0.990 in both, consistent with
v1.6 Phase 5's own finding that Adaptive's defend phase is the one
existing behavior this dimension actually detects; core_defender: exactly
0.8609 in both). Verified directly, not just from the aggregate: Core
Defender's territory is **monotonically non-decreasing right up to the
tick of its own death** in every one of its 5 captured matches, in both
conditions (`last == max` at tick 140 under the alpha condition, and at
tick 200 under the v1 control for the same seeds) — because Core Seeker's
attack is narrowly targeted at the 8-cell core specifically and never
contests Core Defender's other ~740-1,000 claimed cells. The retention
dimension does **not** widen or spread differently under the alpha
condition in this population — it does not detect anything new here.

## 7. Significant matchup results

- **`core_defender` vs `core_seeker` (all 5 seeds): Core Defender is
  captured in every single seed**, at the identical tick (140) each time
  — Core Seeker's design is fully deterministic (it never reads
  `context.rng`), so seed only affects which starter *other* agents do,
  not this specific matchup. Core Defender's one-quarter-of-actions
  refresh rate did not withstand Core Seeker's committed 16-action burst.
- **`core_defender`'s win rate against its 5 non-seeker opponents was
  identical between conditions** (0 wins in both) — its reduced expansion
  rate (spent partly on defense that only ever mattered against one
  specific opponent) did not pay for itself, and did not cost it anything
  either, against opponents that were never going to threaten its core in
  the first place.
- **`claimer` (the historically dominant unrestricted-expansion strategy)
  was never core-captured once across 30 alpha-condition matches**, and
  its only losses under the alpha condition are the score-margin effect
  above, not the mechanic itself. The mechanic does not spontaneously
  check unrestricted expansion — only a purpose-built search strategy
  does.

## 8. Unexpected behaviors and exploits considered

- **The score-margin side effect of core-seeding** (§6) was not
  anticipated by the architecture document and was found only by directly
  auditing the "regressed but not core-captured" cells. It is small (6 of
  210 paired cells, always in the direction the mutual 8-cell head start
  would predict) and symmetric (both entrants receive it identically), so
  it was not treated as a flaw requiring a design change — but it means
  `bytefray-rules-2-alpha1` is not *purely* "v1 plus a capture check"; it
  also grants a tiny simultaneous territorial head start as a forced
  consequence of the capture mechanic needing something to capture.
  Documented here rather than corrected, per the governing task's
  "avoid...an uncontrolled balance campaign" guidance for a first alpha.
- **No exploit found that trivializes the mechanic.** Nothing in this
  evaluation found a "rush the core" degenerate strategy, a permanent
  self-overwrite loop, or a placement-dependent (rather than
  behavior-dependent) capture pattern — captures tracked exactly which
  agent was playing Core Seeker, never which arena position it occupied.
- **Core Seeker is fully seed-independent in this implementation** (it
  never uses `context.rng`) — its identical-tick captures across all 5
  seeds in the same matchup is expected, not a bug, but means this
  particular 5-seed sample undercounts genuine seed-driven variance for
  that agent specifically; a wider seed set would mainly add resolution
  to the *other* five agents' matches.

## 9. Success/rejection criteria assessment

**Evidence supporting continuation**, present:
- Core captures occur at a measurable, nontrivial, bounded frequency
  (7.6%) without collapsing ordinary match play (92.4% still resolve by
  tick limit as before).
- No single trivial strategy simply replaces unrestricted expansion —
  quite the opposite: blind expansion essentially cannot capture a fixed
  8-cell core within the existing tick budget at all; only a genuinely
  different (search-then-commit) strategy shape does.
- Capture events are behavior-driven and deterministically attributable,
  not placement- or seed-artifact-driven.

**Evidence supporting continuation**, absent or weak in this run:
- **No viable defensive counter-strategy was demonstrated.** Core
  Defender, as implemented and tuned, never improved its outcome against
  any opponent and lost every single matchup against the one opponent
  that could find it — the central research question ("does a real,
  localized vulnerability make defense/patrol competitive where it is
  currently dominated?") is **not yet answered affirmatively**.
- `territory_retention`'s population spread does not widen under the
  alpha condition in this population — the metric that v1.6 Phase 5 found
  most informative for strategic differentiation shows no new signal here.
- Historically dominant unrestricted expansion (Claimer) remains
  essentially untouched (never captured once) — the mechanic checks
  expansion only when a specific counter-strategy exists to find it, not
  as a structural property of exposure itself at this `CORE_SIZE`/tick
  budget.

**Rejection-criteria checks, all clear:** captures are neither
vanishingly rare nor overwhelming; no single dominant strategy emerged
across the *whole* population (Core Seeker's own overall win rate is
unchanged at 16.7% — finding and capturing a core does not by itself win
matches under `score_fallback` scoring, since seeking time is time not
spent claiming territory); no self-overwrite-loop degenerate defense was
observed (though none succeeded either); results track agent behavior,
not arbitrary placement; implementation complexity was proportionate
(additive fields, one shared per-tick check function, no new engine,
no VM changes, no schema bump).

## 10. Recommendation

**Modify in alpha.2 / further isolated tuning — not an unqualified
continue, and not a rejection.**

The mechanic itself is mechanically sound, additive, well-isolated,
V1-compatible, and produces real, attributable, bounded-frequency
capture events driven by genuine strategic behavior. It successfully
demonstrates that a *search* strategy is a viable new dimension the
game did not have before (Core Seeker never won more often overall, but
reliably achieved something no blind-expansion agent could). It does
**not yet** demonstrate that *defense* is a viable dimension, and it does
**not yet** meaningfully check the historically dominant unrestricted-
expansion strategy in general play — Claimer's win rate barely moved,
and never through an actual capture. Both of those are exactly what this
alpha's own research question was about, so this is a genuine, if
partial, negative result on the primary hypothesis, not a tuning nit to
wave away.

Candidate directions for an alpha.2, none implemented here (per the
governing task's "avoid an uncontrolled balance campaign" instruction —
this is a list of falsifiable next steps, not a re-tuning pass):

- Retune Core Defender's refresh ratio/timing (currently 1-in-4 actions,
  cycling all 8 cells every 4 ticks) against Core Seeker's specific
  16-action commit burst, to see whether *any* pure-refresh defense can
  win, or whether defense structurally needs a different shape (e.g.
  reacting to detected intrusion rather than blind cycling).
  - Re-examine whether `CORE_SIZE = 8` and the existing 200-tick/
  8-instruction-per-tick budget are the right regime — the same
  arithmetic that makes Core Seeker's find-then-commit approach work
  (blind sweeps can't reliably cover a small fixed window in 1,600
  actions against a 4,096-cell arena) also means *incidental* capture by
  ordinary play is structurally rare, which may be exactly why
  unrestricted expansion isn't checked by the mechanic on its own.
- A wider seed set for the non-Seeker matchups (Core Seeker's own
  determinism means 5 seeds already saturate its contribution to the
  sample).

## 11. Unresolved questions

- Would a Core Defender that *reacts* to detected intrusion (rather than
  blindly cycling its core) fare differently against Core Seeker? Not
  tested — would itself need a detection mechanism symmetric to Core
  Seeker's, which starts to blur the "simple, interpretable reference
  agent" line Phase 7 asks for.
- Does a larger `CORE_SIZE` (a bigger, easier-to-hit target) make
  *incidental* capture by ordinary expansion meaningfully more common, or
  does it just make Core Seeker's job easier without changing whether
  blind expansion alone ever threatens a core? Deliberately not explored
  in this alpha (`CORE_SIZE` was fixed, not swept, per the governing
  task).
- The 6-case score-margin side effect of core-seeding (§6/§8) was
  characterized but not eliminated; whether a future alpha should seed
  differently (e.g. a value that doesn't interact with
  `territory_bucket`-quantized scoring at all) is open.

## 12. Recommended next Bytefray v2 prompt

Given this alpha's own finding — that unrestricted expansion is checked
only by a dedicated *search* strategy, and that a straightforward
*defense* strategy did not yet pay for itself — the most direct
evidence-driven next step is **not** a new mechanic, but a narrowly
scoped **alpha.2** that varies only Core Defender's design (and/or
`CORE_SIZE`/budget) against the exact same Core Seeker, matrix, and
statistical methodology already built here, to determine whether *any*
pure-defense shape can make the "expansion vs. defense vs. search"
three-way tension the original hypothesis wanted actually materialize —
before considering whether Vulnerable Core, in some form, is worth
carrying into a permanent Ruleset v2.
