# Bytefray v2.0 Alpha — Ruleset v2 / Agent API v2 Research

This is the durable record of the first Bytefray v2.0 work: not an
implementation, but an evidence-based research and architecture-planning
pass over the mature v1.6 platform, answering one question — what should
Bytefray experimentally change in a future Ruleset v2 to create deeper
strategic behavior, and what is the smallest architecture/API evolution
required to test that while leaving Ruleset v1 and every historical
artifact exactly as they are?

No gameplay, Agent API, Ruleset, or schema code changed to produce this
document. Where a claim below needed verification against the real
implementation rather than a docstring, it is cited by file:line, and
where a v1.5/v1.6 phase doc's own forward-looking language turned out to
overstate what the code actually provides, this document says so
explicitly rather than repeating it.

## 1. Verified starting state

- `main` = `origin/main` = `v1.6-development` = `HEAD` =
  `5593d287f95a24996bb3b105befbc625a00795db`, working tree clean.
- The annotated tag `v1.6.0` (`git cat-file -p v1.6.0`) points at that
  identical commit — the tag, the branch, and `main` are the same object,
  not merely "close."
- `pyproject.toml` version `1.6.0`; `CHANGELOG.md`'s `[1.6.0]` entry dated
  2026-08-18 matches.
- No commits exist between the `v1.6.0` tag and `HEAD` in either
  direction (`git log v1.6.0..HEAD` and `git log HEAD..v1.6.0` are both
  empty) — this is not "close to the tag," it is the tagged commit.
- Baseline reproduced fresh in this session, editable install
  (`bytefray 1.6.0` from `D:\Projects\BATTLE2`), Python 3.11.9:
  **1474 tests: 1468 passed, 6 skipped, 0 failed, 0 errors** — matching
  the exact `1474 passed, 6 skipped` figure
  `docs/V1_6_PHASE6_INTEGRATED_QUALIFICATION.md` records as v1.6.0's own
  qualification baseline (line 29). `ruff check .`: all checks passed.
  `mypy engine/src/battle_engine`: no issues (65 source files). `mypy
  client/src/battle_client`: no issues (10 source files). This is strong
  evidence the checkout is exactly the same known-good state v1.6.0
  shipped from, not a drifted copy.
- No unrelated in-progress user work was found in the tree; nothing was
  stashed, discarded, or modified.

## 2. v1.6 architecture baseline — what the mature platform already provides

`NativeMatchService` (`match_service.py`) is the single canonical
execution boundary for every native match. It accepts a `MatchRequest`
(`config: Config`, `entrants: tuple[MatchEntrant, ...]`, `max_ticks`,
`replay_path`, plus Agent-Lab-only `trace_path`/`agent_call_timeout`) and
routes to `Kernel.run()` (VM) or `PythonEntrantController.run()`
(Python), homogeneous-only. Both paths converge on
`_finalize_native_artifacts`, which computes `match_id`/`result_id` and
writes canonical `replay.jsonl` (`battle2.replay` v3) and `result.json`
(`battle2.result` v1).

Eight independent compatibility axes are already established and must
not be conflated (`docs/COMPATIBILITY.md`): project version, Agent API
version, Ruleset identity, artifact schema versions (replay/result/
evaluation/trace/package, each independent), evaluation methodology
fields, agent revision identity, source fingerprint versions, and agent
package format. A gameplay-semantic change bumps exactly the Ruleset
identity (`BYTEFRAY_RULESET_ID`); nothing else needs to move with it.
This existing discipline is directly reusable for Ruleset v2 without
inventing a ninth axis.

Arena addressing is a single flat `pos % arena_size` wrap, verified
directly in `vm.py:38-46` (`_rd32`), `vm.py:48-73` (`_wr8`), and
`vm.py:86-91` (`load_code`); `python_runtime.py`'s `READ`/`WRITE` action
handling routes through the identical `VM._wr8`/`vm.arena[operand %
len(vm.arena)]` — there is no per-entrant origin, offset, or coordinate
space anywhere in either runtime today. Ownership is O(1)-maintained
(`vm.py:48-73`'s `ownership_counts` dict, the v1.4 optimization) rather
than rescanned, which matters for any future measurement that wants
per-tick territory data cheaply.

Empirically, and this is a load-bearing fact for Phase 3 below: v0.6.1's
own retuning notes, recorded in `CHANGELOG.md` (lines ~1000-1020),
found that under current Ruleset v1 scoring, unrestricted "claim as much
of the arena as fast as possible, and never stop" strategies are close to
dominant. Every attempt made during that release to trade raw expansion
for something else — reading before writing, patrolling and defending a
bounded region, pausing to specialize into distinct phases — measured
*worse* against an opponent that simply never stops expanding, because
such an opponent eventually sweeps the whole arena and, in the fixed
subject-then-opponent tick order, wins any cell it reaches after the
subject already claimed it. The project's own text names this "almost
certainly... a fact about the current scoring model," not a tuning
failure, and flags it for "whoever next considers richer Python match
modes or scoring variants" — i.e., exactly this task.

## 3. v1.5 evolution seams — what was actually prepared, and how far it actually goes

v1.5 ("Architecture Evolution Readiness") introduced four seams behind
the still-frozen `bytefray-rules-1` behavior. Verified directly against
the current source (not just the phase docs' own description of it):

### `RulesetPolicy` / `resolve_ruleset_policy` — a real but narrow dispatch point

`ruleset_policy.py:159-171`: `resolve_ruleset_policy` does one dict
lookup in `_RULESET_POLICIES` (`ruleset_policy.py:156`), a **one-entry**
map keyed only by the literal `BYTEFRAY_RULESET_ID`, and fails closed
(`UnknownRulesetError`) for anything else — this is directly tested
(`test_unknown_ruleset_id_fails_closed_...`). `RulesetPolicy` exposes
exactly two methods: `run_scheduler` (delegates to
`scheduler.run_sequential_quota`) and `resolve_termination` (a pure
alive-count/tick/max-tick function). Nothing else — **scoring
(`ScoringPolicy`) and winner resolution (`results.resolve_winner`) are
explicitly outside this seam**, confirmed by the Phase 4/5/6 docs'
own "architectural debt" sections. Critically, `match_service.py:874`
calls `resolve_ruleset_policy(BYTEFRAY_RULESET_ID)` with the **hardcoded
module constant** — `MatchRequest` has no `ruleset_id` field at all
today. So the dispatch mechanism is real (a second policy could be
registered), but nothing currently *reaches* it with anything other than
the frozen v1 identity; a caller cannot select an experimental Ruleset
through the public request shape as it exists now.

### `EntrantIdentity` — a pattern, not a one-to-many mechanism

`entrant_identity.py:17-46`: a frozen two-field (`agent_id`, `name`)
value object. Phase 5's own text is explicit that "there is structurally
no way to attach two execution states to one identity without also
constructing two separate `Agent`/`PythonEntrantState` objects — something
no code in this phase does or enables." It is a clean, small,
dependency-free value object other future identity concepts (a component
ID, say) could follow the *shape* of, but it does not itself unlock
multiple execution loci per entrant.

### `scheduler.run_sequential_quota` — genuinely reusable, incidentally

`scheduler.py:27-38`: a `Protocol`-typed, runtime-agnostic function over
any `states: Iterable[StateT]` (bound only to `alive: bool`) and an
`execute_slot(state, slot)` callback. It has no concept of "entrant" and
could mechanically be called on a flattened multi-component state list
without modification — but nothing in the surrounding architecture
produces such a list: `Kernel.spawn` and `PythonEntrantController.__init__`
each append exactly one execution state per `MatchRequest.entrants`
element, and scoring/statistics/termination are all keyed 1:1 by
`agent_id`. This scheduler function is a real, reusable seam for a
future multi-component scheme, but everything around it today assumes
exactly one execution locus per entrant.

### `arena_alignment_mode` — evaluation metadata, not an engine capability

`docs/ROADMAP.md` and `docs/COMPATIBILITY.md` both describe
`arena_alignment_mode` as an "extension point" for future translation
work. Verified directly: it is defined once, in `agent_evaluation.py:154`,
as `EVALUATION_ARENA_ALIGNMENT_MODE = "fixed"` — a hardcoded string
literal with exactly one value ever assigned, persisted into
`bytefray.evaluation` artifacts purely as a disclosure/identity field
(`agent_evaluation.py:857,2041,2470`) and used for evaluation-history
comparison alignment (`evaluation_history/comparison.py:249-258`). It is
never read by `vm.py`, `match_service.py`, or any runtime code, and no
translation/remapping logic exists anywhere in either runtime. It is an
honest label meaning "no translation happens today," not a stub with
branching logic behind it — the phase-doc language calling it an
"extension point" is true only in the narrow sense that a second string
value *could* be added to a comparison field, not that any mechanism
exists to act on it.

### One entrant already spawns at a fixed, shared address in the Python harness

A finding not called out by any prior phase doc, directly relevant to
Phase 3 below: `agent_test.py:351-356` (used by both `bytefray agents
test` and, through it, `bytefray agents evaluate`'s per-cell executor)
constructs every Python match with **both entrants starting at address
`0`** —
`MatchEntrant.python(TESTED_AGENT_SLOT, agent_id, 0, tested_spec)` and
`MatchEntrant.python(OPPONENT_SLOT, opponent_name, 0, opponent_spec)`.
Every Python-vs-Python evaluation ever run through the standard harness
has placed both competitors at the literal same starting point. This is
consistent with, and partly explains, the v0.6.1 "never stop expanding
dominates" finding above: there is no separation, discovery, or
positional asymmetry to exploit — the game reduces to an outward
footrace from one shared origin. `MatchEntrant.start` itself already
supports arbitrary distinct values (the VM CLI path already varies it);
the fixed-`0` behavior is specific to `agent_test.py`'s Python
construction, not a VM or engine limitation.

### v1.5 verdict, by future-direction candidate

| Candidate | What v1.5 already provides | What is fully unbuilt |
|---|---|---|
| (a) Arena/information-density | `RulesetPolicy` seam for swapping termination/scheduling rules under an equivalent shape; `Observation`/`MatchContext` are clean, isolable dataclasses | Any actual arena-translation/origin mechanism |
| (b) Multiple execution processes per entrant | `run_sequential_quota`'s incidental protocol-genericity | Everything else: one-state-per-entrant spawn loops, `EntrantIdentity` has no component axis, `derive_agent_seed`'s frozen 4-field formula, Agent API's single-`agent_id`-scoped `MatchContext`/`Observation`/one-`LoadedPythonAgent`-per-state |
| (c) Replication/deployment | Nothing — no phase doc or source file addresses spawning entrants mid-match or resource/reproduction mechanics | Everything |
| (d) Translation/placement | `region`/`start` are already cleanly separated as "resolved match input," not execution state (Phase 1 finding #5) | Any remapping/origin mechanism in either runtime; `docs/ROADMAP.md` itself already documents Python-side translation needs either an Agent API break or new shared runtime work |

## 4. v1.6 instrumentation — what can already measure a Ruleset v2 experiment

`EvaluationService` (`agent_evaluation.py`) is **not currently
Ruleset-agnostic in practice**, despite the dispatch seam existing one
layer down: `_execute_cell` always calls `test_agent(...)`
(`agent_evaluation.py:2213`), which hardcodes exactly two Python
entrants (`agent_test.py`) — no VM path, no N-way composition, and (per
§3) always places both at address 0. To run *any* matrix under a second
Ruleset identity, `NativeMatchService.run`'s hardcoded
`resolve_ruleset_policy(BYTEFRAY_RULESET_ID)` call and `MatchRequest`'s
missing `ruleset_id` field would need to change first — both small,
additive changes (§6 below), not a rewrite. The good news: the
matrix-building, checkpointing, and parallel-worker machinery above
`_execute_cell` never assumes anything about *what* one match computes,
only that it returns a `CellExecutionResult` — so once dispatch is
request-driven, the scheduling/statistics/behavior layers need little to
no change. `evaluations compare`'s condition-alignment key
(`evaluation_history/comparison.py:261-299`) already includes a
`rules_id` component and correctly refuses to align cells from two
different Rulesets as comparable rather than fabricating a verdict — this
part is genuinely forward-compatible today, not merely aspirational.

**Behavior-profile analytics** (`evaluation_behavior.py`, v1.6 Phase 5)
compute 11 dimensions per cell, all Tier-2 (derived from each cell's own
`result.json`, entrant-scoped, no per-tick structure): survival
fraction, write rates, three territory-percentage stats, territory
retention, territory spread, and three kill/death rates. Of these,
**`territory_retention` is the one dimension the project's own Phase 5
validation (its §14.1/§14.4) found actually separates a real strategic
difference (Adaptive's defend phase) that win rate alone hides** — it is
the single most useful existing metric for detecting "strategically
richer" behavior rather than "more operations." The others were
empirically uninformative for the current five-agent population.
Detecting genuine *coordination* (as opposed to more raw activity) needs
the still-unbuilt Tier-3 tier — per-tick `memory_diffs` traversal — which
is deferred for a real architectural reason, confirmed directly: `grep`
of `engine/src/battle_engine/` shows zero non-lazy imports of
`battle_client` outside one function-local import in `command.py:204`
(the `bytefray replay` CLI dispatch shim) and a string literal in
`launchers.py:140`; `battle_client` imports `battle_engine` in 8 files.
The incremental reconstruction Tier-3 metrics need
(`battle_client.session.ReplaySession`) genuinely lives on the wrong side
of that one-way boundary, so building it inside `battle_engine` (needed
for `evaluations show`, which must stay Pygame-free) is not simply
unstarted work — it would violate the acyclic dependency direction
`AGENTS.md` establishes. A future Tier-3 belongs in `battle_client`/
Designer, not `battle_engine`.

**What's already variable with zero new code**: only `ticks` and `seeds`
are pluggable through `agents evaluate`/presets today.
`EffectiveConditions`'s own constructor comment
(`agent_evaluation.py:268-269`) states plainly that `agent_test.py` gives
no per-cell override surface for anything but seed/ticks; `arena_size`,
`instr_per_tick`, `win_mode`, and `weights` all come from unconditional
`Config()` dataclass defaults (`agent_test.py:352`), and neither the
`evaluate` CLI parser nor the preset schema exposes them. **Hypothesis
(A), "arena/information-density change only," is therefore not free** —
it needs new configuration-threading plumbing (`EvaluationRequest` →
`test_agent` → `MatchRequest`) before a single cell can vary arena size
or instruction budget, even though, per `docs/RULES.md`'s bump policy,
none of that plumbing would require a Ruleset bump on its own.

## 5. Candidate comparison

| | (A) Arena/information-density | (B) Multiple execution processes | (C) Replication/deployment | (D) Richer offensive mechanics | (E) Translation/placement |
|---|---|---|---|---|---|
| Strategic novelty | Real but bounded — same mechanic, different scale | High if realized, but "coordination" is easy to claim and hard to prove | High if realized; high exploit surface | High — directly targets the documented "expansion dominates" finding | Real but orthogonal to *mechanic* richness — mostly a fairness/methodology question |
| Ruleset bump required? | **No** (`docs/RULES.md`'s bump policy explicitly excludes arena-size/tick/rate defaults) | Yes (scheduler/termination/scoring all touched) | Yes | Yes (mortality/ownership semantics change) | Normally no for VM (placement is `MatchEntrant.start`, already a configuration value); Python-side needs Agent API work regardless of Ruleset |
| Agent API impact | None | Needs a component ID — an incompatible v1 change, i.e. a v2 bump, since `MatchContext`/`Observation`/`AgentAction` all carry exactly one `agent_id` and `PythonEntrantState` holds exactly one `LoadedPythonAgent` | Needs spawn/deploy actions — new `ActionKind`, i.e. a v2 bump | None required for the minimal form (§6) — the entrant's own core address is already inferable from `Observation.pc` before any `JUMP`, since `PythonEntrantState.pc` is initialized to `entrant.start & 0xFFFFFFFF` (`python_runtime.py:569`) | Python-side needs either an Agent API break or new shared runtime work (`docs/ROADMAP.md` already documents this); VM-side is usable today |
| Architecture change | New config-threading in evaluation layer only | Scheduler + spawn loops + `EntrantIdentity` + Agent API, substantial | Entrant lifecycle beyond construction — currently doesn't exist at all | `MatchRequest.ruleset_id` field + one new tick-lifecycle check in `python_runtime.py`, structurally similar to existing VM kill attribution | Distinct-start-address support in the Python harness (small); real address remapping (large, deferred) |
| Exploit/trivial-solution risk | Low | Medium-high (coordination overhead vs. throughput multiplication is hard to force) | **High** — replication that isn't cost-bounded becomes a free multiplier by construction | Medium — mitigated by opponent-core location being genuinely unknown to the attacker (no opponent state in `Observation`), so "rush the core" requires exploration, not a lookup | Low |
| Determinism implications | None | Needs care (new interleaving) | Needs care (new spawn timing) | None (same tick-lifecycle position as existing kill attribution) | None |
| Measurable with v1.6 instrumentation as-is? | Partially — needs config plumbing first | No — needs new coordination-detection metrics, not built | No — needs new metrics | **Yes, mostly** — `territory_retention` plus survival/kill-rate deltas directly test the hypothesis; a new `core_captured` termination cause and kill-attribution path are additive | Partially — `arena_alignment_mode` is disclosure-only today |
| Prototypable without committing public v2 API? | Yes | No — the Agent API change is the thing being tested | No | **Yes** — stays behind an internal/experimental Ruleset ID, no Agent API version bump | Yes for VM; no for Python |
| Strongest argument against | Doesn't test a *mechanic* at all — it's a parameter study on the already-frozen v1 game, which may not deserve a "Ruleset v2" identity or a 2.0 alpha release at all | Least architecturally ready of all five candidates; committing to a component model now risks freezing a wrong shape before any evidence exists | No existing seam addresses entrant lifecycle; this is the largest single leap from current architecture | Only affects the Python runtime; VM already has native code-vulnerability, so this widens rather than closes the VM/Python semantic gap (arguably correct, since VM's mechanic is exactly what's being emulated) | The evidence for gameplay impact is already "mixed" per v0.9/v0.10's own dedicated study — this is documented, not hypothetical, and the Python-side blocker is already characterized as substantial, separately-scoped engineering |

## 6. Recommended first experimental slice: `v2.0.0-alpha.1` — Vulnerable Python Core

### Research question

Bytefray already has a real emergent-combat mechanic for the VM
runtime — self-modifying shared code plus last-writer kill attribution —
but explicitly does not for Python, where "Python entrants are not
vulnerable to arena code corruption" is recorded as a current limitation
(`docs/AGENT_API_V1.md`), and where the project's own evidence
(§2) shows unrestricted expansion is close to dominant with nothing to
meaningfully contest it. **Does giving a Python entrant's own spawn
region a real, environment-manipulation-based vulnerability — using only
the existing `READ`/`WRITE` action vocabulary, no new `ActionKind` —
produce measurably more diverse winning strategies than Ruleset v1's
pure territory-denial game, without simply rewarding more operations?**

### Hypothesis

Making expansion carry a real defensive risk (an exposed, capturable
core) makes patrol/defense/hybrid strategies competitive where §2's
evidence shows they are currently strictly dominated, increasing
strategy diversity among winning agents — measurable as a spread in
`territory_retention` and a new `core_captured`-attributed kill rate
that varies meaningfully across the existing starter roster, rather than
every agent converging on one "rush and never stop" shape regardless of
this change.

### Exact semantic difference from Ruleset v1

Applies to Python-vs-Python matches only (this is a deliberate,
disclosed asymmetry with the VM runtime, not an oversight — see
"Explicitly deferred" below):

1. Each Python entrant's **core** is a fixed-size window of `CORE_SIZE`
   bytes (a small constant, e.g. 8) starting at its own spawn address
   (`entrant.start`, mod `arena_size`) — the same address the entrant can
   already read from its own first `Observation.pc`, since
   `PythonEntrantState.pc` is initialized to `entrant.start` and nothing
   moves it before the first `act()` call. No `Observation`/
   `MatchContext` field changes.
2. Checked once per tick, at the same tick-lifecycle position the VM's
   kill attribution already occupies (after actions, before the existing
   termination check): if every byte of a living entrant's core is
   currently owned (last-writer, using the engine's existing ownership
   bookkeeping — no new tracking structure) by one single *other*
   entrant, the core-holder's entrant is marked dead with a new
   termination cause, `core_captured`, and the capturing entrant receives
   kill credit through the existing `score_kill` formula — the first time
   a Python death is attributed, exactly analogous to VM last-writer-at-
   PC attribution, and does not change `docs/RULES.md`'s documented "No
   Python kill attribution" default for ordinary `HALT`/forfeit deaths,
   which remain unattributed.
3. No new `ActionKind`, no change to `READ`/`WRITE` semantics, no change
   to arena addressing, no change to scoring *weights*. This is a
   mortality/ownership-semantics change — per `docs/RULES.md`'s bump
   policy, this genuinely requires a new Ruleset identity, unlike §5's
   candidate (A).

### Compatibility identity strategy

New identity `bytefray-rules-2-alpha1` (§7). `MatchRequest` gains one new
optional field, `ruleset_id: str | None = None`; `None` continues to
resolve to `BYTEFRAY_RULESET_ID` exactly as today (a strictly additive,
default-preserving change — every existing caller is unaffected).
`NativeMatchService.run` stops hardcoding the constant at its
`resolve_ruleset_policy` call site and instead reads
`request.ruleset_id or BYTEFRAY_RULESET_ID`. The experimental policy is
registered under its own explicit ID, never silently aliased to or from
`bytefray-rules-1`.

### Minimal architecture change

- `MatchRequest.ruleset_id: str | None = None` (additive).
- A second `RulesetPolicy`-shaped registration for
  `bytefray-rules-2-alpha1`, added to the dispatch table under its own
  key — `_RULESET_POLICIES` stays a finite, explicit, fail-closed map;
  nothing pattern-matches.
- One new per-tick check in `python_runtime.py`'s tick loop (both
  supervised and unsupervised controllers, mirroring how `apply_action`
  is already shared rather than duplicated) evaluating core ownership for
  living entrants and setting `alive = False` with the new termination
  cause on capture — the smallest form of this that doesn't touch
  `RulesetPolicy.resolve_termination`'s existing three-argument signature.
- **Distinct starting addresses.** §3 found `agent_test.py` hardcodes
  both Python entrants to start address `0`. A core mechanic is
  meaningless if both cores occupy the same cells from tick zero,
  so `agent_test.py`'s Python construction needs a second, small,
  additive change: accepting explicit (or engine-chosen, distinct)
  per-entrant start addresses instead of the hardcoded `0`/`0`. This is a
  configuration value, not a Ruleset concern (`docs/RULES.md`'s
  "Configuration values are not Ruleset identity" list already treats
  `MatchEntrant.start` analogously to seed for the VM path), so it can
  and should ship as a `bytefray-rules-1`-compatible harness improvement
  independent of the experimental Ruleset — useful on its own regardless
  of whether the core mechanic is ultimately adopted, and a prerequisite
  either way.
- `battle2.replay`/`battle2.result` gain one new additive
  `termination_reason` value, `"core_captured"` — no schema version
  bump, following the exact "safe explicit-default additive field"
  precedent `ruleset_id` itself already established.

### Experimental Agent API surface

None required for this alpha. The core address is inferable by any
agent today from its own first `Observation.pc`. Phase 8 records this as
a candidate for an explicit, documented field in a future Agent API v2
(rather than relying on an implementation coincidence), but that is a
robustness improvement for later, not a blocker for this experiment.

### Artifact/schema impact

Additive only, as above: one new `MatchRequest` field (not persisted),
one new termination-reason string value (schema-compatible, no version
bump), one new Ruleset identity string (an identity value, not a schema
change). No `battle2.replay`/`battle2.result`/`bytefray.evaluation`
schema version changes anywhere in this experiment.

### Evaluation matrix

- Two conditions: `bytefray-rules-1` (control) vs.
  `bytefray-rules-2-alpha1` (experimental core mechanic), all other
  `Config` values held at existing defaults (`arena_size=4096`,
  `instr_per_tick=8`, existing tick limit and weights) — deliberately not
  combined with candidate (A)'s arena/density variation in this first
  alpha, to keep one variable under test.
- Existing five-agent Python starter roster (Claimer, Strider, Hunter,
  Wanderer, Adaptive) — every pair, both orientations, both Ruleset
  conditions, the same seed set `agents evaluate` already uses by
  convention.
- Two new reference agents are needed, since none of the five existing
  starters were designed with core vulnerability in mind: (1) a **core
  defender** that stays near its own spawn address rather than
  dispersing (directly testing whether defense becomes viable where §2's
  evidence shows it currently is not), and (2) a **core seeker** that
  spends part of its budget scanning (`READ`) for concentrated foreign
  ownership near its own spawn radius before committing to an attack —
  deliberately *not* given the opponent's location for free, since
  `Observation` exposes no opponent state; finding the opponent's core is
  itself part of the strategy space this experiment is testing, and
  making it free would collapse the interesting question into a
  race-to-a-known-point degenerate case.

### Metrics

`territory_retention` (already validated as the one existing metric that
detects real strategic difference), survival fraction, the new
`core_captured` kill/death rate specifically (distinguishable from
ordinary `HALT`/forfeit in the existing per-entrant `termination_reason`
field), and win-rate deltas per matchup (Wilson intervals / exact sign
test, both already built in v1.6 Phase 4).

### Success criteria

Under `bytefray-rules-2-alpha1`, at least one previously-dominated
strategy type (the new core defender, or an existing agent retuned
toward defense) becomes competitive against the existing "never stop
expanding" baseline in a way it measurably is not under `bytefray-rules-1`
on the identical matchup/seed set, *and* the population's
`territory_retention` spread widens rather than collapsing to one shape.

### Rejection criteria

If every agent's optimal response converges on one new dominant strategy
(e.g., "rush toward the arena midpoint immediately, ignore your own
core") regardless of starting design, or if core capture never
meaningfully happens within the existing tick budget (agents simply
don't reach each other's cores before the match ends), the mechanic
should be rejected or substantially redesigned rather than iterated in
place — that is direct evidence the mechanic doesn't create the intended
tension, not a tuning nit.

### What would be learned even from a negative result

Either outcome is informative: a negative result would show that
Bytefray's territory-denial dynamic is robust to a *localized*
vulnerability and that richer strategic diversity needs a structurally
different lever (multiple execution processes, replication, or a
different mortality shape entirely) — narrowing candidates (B)/(C) from
"unexplored" to "worth the larger investment" with actual evidence,
rather than narrowing them on architecture-readiness alone as §5 does
today.

### Explicitly deferred (this alpha)

- No VM-side core mechanic (VM already has native code-vulnerability;
  extending this specific mechanic to VM is a separate, later question).
- No arena/information-density variation (candidate A) combined into the
  same alpha — kept as a separate, possibly Ruleset-v1-only follow-up.
- No multiple execution processes, no replication, no translation.
- No permanent `bytefray-rules-2` identity (§7).
- No Agent API v2 field additions (§8) — the experiment works entirely
  within Agent API v1's existing `Observation` surface.
- No Designer/GUI surfacing of the experimental Ruleset.

## 7. Ruleset compatibility model

`bytefray-rules-1` remains available and behaviorally frozen — nothing
in this plan touches `vm.py`, `scoring.py`, `results.py`, or any
existing `RulesetPolicy` behavior for the frozen ID. `resolve_ruleset_policy`
stays fail-closed: an unrecognized ID is rejected, never silently run as
v1. The experimental identity is spelled `bytefray-rules-2-alpha1` rather
than a bare `bytefray-rules-2`, matching the task's own suggested
convention and this document's own evidence: the core mechanic's exact
shape (window size, capture condition, whether partial/majority
ownership should count) is a design hypothesis to be tested, not a
matured contract, and freezing a permanent `bytefray-rules-2` before an
experiment has even run would repeat exactly the mistake
`docs/RULES.md`'s bump policy exists to prevent — encoding an unproven
guess as a durable compatibility promise. Old result/replay/evaluation
artifacts keep meaning exactly what they meant; no code path introduced
by this plan ever interprets a `bytefray-rules-1` artifact under
`bytefray-rules-2-alpha1` semantics or vice versa — the two remain
completely separate rows in every `resolve_result_ruleset`/
`resolve_replay_ruleset` decision, never aliased (the alias table in
`rules.py:62-64` records only genuine historical equivalences with git-
history evidence behind them; `bytefray-rules-2-alpha1` gets no entry).
Shared implementation stays acceptable exactly where semantics are
genuinely shared: `vm.py`, `scoring.py`, `results.resolve_winner`,
`statistics.py`, and the VM path are untouched and fully reused; only the
one new Python-side per-tick check and the new `RulesetPolicy`
registration are experiment-specific. No second engine is created.

## 8. Agent API v2 implications

**Not required for this alpha.** The experiment works entirely inside
Agent API v1's existing `Observation` (an entrant already has its own
spawn address via `pc` before any `JUMP`) and existing `ActionKind`
vocabulary (`READ`/`WRITE`, nothing new). This directly answers the
task's framing question: the first Ruleset-v2 experiment can, and should,
remain behind an internal/experimental interface, with zero Agent API
version bump.

What genuinely would require an eventual Agent API v2, based on what §3/
§5 found is actually missing (requirements, not speculative signatures):

- **Component identity.** `MatchContext`/`Observation`/`AgentAction` all
  carry exactly one `agent_id`; any real multiple-execution-process
  entrant (candidate B) needs a component axis threaded through all
  three, plus `derive_agent_seed`'s frozen four-field formula extended —
  an incompatible change by definition, since the formula is pinned by
  golden-vector tests specifically to prevent silent drift.
- **Deployment/spawn action.** Candidate (C) needs a new `ActionKind`
  that creates a new execution locus — genuinely new API surface, not an
  additive field.
- **Explicit spawn-origin field.** Not required functionally (§6 already
  works without it), but documenting `MatchContext.spawn_address` (or
  similar) explicitly, rather than leaving agents to infer it from
  `Observation.pc`'s initial value as an implementation detail, would be
  a reasonable, low-risk *additive* candidate for a future Agent API v2
  — worth doing once other v2 concepts justify a version bump anyway, not
  worth bumping the version for on its own.

Avoid speculative general-purpose APIs: no resource-budget system, no
entrant-shared-vs-component-local state model, and no observation
semantics for multiple components should be designed until candidate (B)
or (C) has actual evidence behind it, per §5's own finding that
committing to a component shape now would freeze a guess.

## 9. Artifact/replay/evaluation implications

This is an identity change, not a schema change, throughout:

- `battle2.replay`/`battle2.result`: one new additive `termination_reason`
  string value (`"core_captured"`); readers already tolerate unrecognized
  values in every other enum-shaped field in this codebase's established
  pattern, and no `SCHEMA_VERSION` bump is implied — this is the same
  category of change `ruleset_id` itself was (§2).
- `MatchRequest.ruleset_id`: a new, unpersisted request-shape field —
  not part of any wire schema at all.
- `bytefray.evaluation`: no schema change. `rules_compatibility_id`
  already threads through `EVALUATION_RULES_COMPATIBILITY_ID` per
  evaluation; an evaluation run under the experimental Ruleset would
  simply record `bytefray-rules-2-alpha1` there, and — already verified
  in §4 — `evaluation_history`'s comparison alignment already refuses to
  conflate two evaluations with different `rules_id`s rather than
  silently comparing across them. No new evaluation-methodology field is
  needed for this specific alpha (arena-alignment/orientation are
  unaffected by a mortality-rule change).
- `bytefray.agent_trace`/`bytefray.agent_package`: untouched — a trace
  records the Agent API boundary (unchanged here) and revision identity
  answers "what source" independent of "under what rules," exactly as
  `docs/RULES.md` already establishes for the existing axes.

## 10. Experimental plan summary

| | |
|---|---|
| Agents | Existing 5 Python starters + 2 new (core defender, core seeker) |
| Conditions | `bytefray-rules-1` vs. `bytefray-rules-2-alpha1`, `Config` otherwise at defaults |
| Placement | Distinct per-entrant start addresses (new, small harness change — see §6) instead of today's shared `0`/`0` |
| Seeds | Existing `agents evaluate` seed-set convention, both orientations |
| Arena size / ticks | Held at current defaults — not varied in this alpha |
| Metrics | `territory_retention`, survival fraction, `core_captured` kill/death rate, win-rate significance (existing Wilson/exact-sign-test machinery) |
| Comparison | `evaluations compare` across the two Ruleset conditions, relying on its existing (already-correct) refusal to conflate differing `rules_id`s |
| Falsification | One new dominant strategy emerges regardless of design, or captures never occur within the tick budget |

## 11. Explicitly deferred beyond this document

Everything the governing task named as out of scope remains out of
scope: no engine redesign, no implementation of every proposed
mechanic, no BFScript, no Pygame replacement, no Designer rewrite, no
Designer empty-state branding, no Replay HUD redesign, no web frontend,
no package registry, no signing/PKI, no Redcode/pMARS overhaul, no
deletion of Ruleset v1, no historical-artifact alteration, no schema
version bumps "because 2.x," and no alpha release publication. Candidates
(B) multiple execution processes and (C) replication remain research-
stage with no implementation or API committed; candidate (E) translation
remains deferred exactly as v0.9/v0.10 left it, with no new evidence
gathered in this pass to change that disposition. Candidate (A)
arena/information-density is real and low-risk but is not this alpha's
subject — see §6's "Explicitly deferred."
