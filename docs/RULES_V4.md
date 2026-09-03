# Bytefray Ruleset v4 Reference

This document defines **Ruleset v4** (`bytefray-rules-4`), the permanent
gameplay-semantics identity introduced in `v4.0.0-rc1` Phase 2 and stable as
of that promotion. It describes the game as it plays today under Agent API
v2 — how a match differs from Ruleset v1/v2 and what stays the same — not
how the research that produced it was conducted. For that evidence trail,
see [V4_ALPHA1_DESIGN.md](V4_ALPHA1_DESIGN.md) (the frozen scheduler/
process/disruption/observation freeze this Ruleset inherits unchanged),
[V4_ALPHA2_DESIGN.md](V4_ALPHA2_DESIGN.md) (the two gameplay changes this
Ruleset was promoted from, unmodified), and
[docs/research/v4/V4_PRE_RC_GAMEPLAY_EVALUATION_RESEARCH.md](research/v4/V4_PRE_RC_GAMEPLAY_EVALUATION_RESEARCH.md)
(the pre-RC study that concluded no further gameplay alpha was needed).

`docs/RULES.md`/`docs/RULES_V2.md` remain the frozen, unmodified Ruleset
v1/v2 references. This document does not replace either and does not repeat
material that is genuinely unrelated in more detail than necessary.

**Status: permanent, stable semantic identity** as of `v4.0.0-rc1` Phase 2.
See `docs/COMPATIBILITY.md`'s "Ruleset v4" section for what that status does
and does not promise, and for the release-blocking equivalence corpus
(`engine/tests/test_v4_stable_ruleset_equivalence.py`) that proves this
Ruleset is gameplay-identical to `bytefray-rules-4-alpha2`, not merely
declared to be.

## What makes v4 different from v1/v2, in one paragraph

Ruleset v4 replaces v1/v2's single-actor-per-entrant model with a
**spatial multi-process** one: each entrant declares a fixed roster of one
or more independent *processes*, each with its own address in the arena
(its "anchor") and its own declared circular *reach*. An entrant's total
per-tick action budget (`Q = 8`) is shared across its own processes by
declared proportion (`share`), handed out to eligible processes in
rotation. `READ`/`WRITE` act only within a process's own reach of its own
anchor; `MOVE` relocates a process's anchor. A live enemy `WRITE` landing
exactly on a process's anchor disrupts it for the remainder of that tick.
Everything else — scoring, entrant-level scheduling order, winner
resolution, the arena's own read/write/ownership rules — is unchanged from
v1/v2's shared foundation.

## What is the Agent API?

**Agent API v2** — a wholly separate programming contract from Agent API
v1 (v1/v2's contract), documented in full in
[AGENT_API_V2.md](AGENT_API_V2.md): `reset(context)`,
`declare_processes()`, `act(observation)`, `ProcessDeclaration`,
`MatchContextV2`, `ObservationV2`, `ActionKindV2`. Agent API v2 is itself
stable as of this same promotion (see AGENT_API_V2.md's own framing) and is
shared, unmodified, by all three v4 Ruleset identities — an agent written
against it loads and runs identically under `bytefray-rules-4`,
`bytefray-rules-4-alpha2`, and `bytefray-rules-4-alpha1`.

## How is a core placed?

Every entrant's core is derived from the match seed, subject to a minimum
circular separation of 64 cells between any two entrant core bases
(`ALPHA2_MIN_CORE_SEPARATION`, clamped down only when the arena is too
crowded to fit it — see `battle_engine.placement.seeded_seat_starts`). This
is **not** an evenly-spaced fixed layout: `enemy_core_base = own_core_base +
arena_size // 2` is not a generally valid formula under this Ruleset —
an opponent's core address must be found, not computed. Placement is
resolved through the same production seam (`placement.
resolve_direct_match_starts`) every direct match (`bytefray run`) and every
stable-v4 evaluation cell resolves through; there is no second,
evaluation-only or Designer-only placement implementation.

This is unchanged from `bytefray-rules-4-alpha2`, byte-for-byte: the
seed-derived draw's own domain-separation constant is a fixed string, never
parameterized by which of the three v4 Ruleset identities is executing, so
identical `(seed, arena_size, entrant_count)` inputs produce identical
resolved addresses under all three. `bytefray-rules-4-alpha1` instead uses
an evenly-spaced fixed seat layout anchored at address 0 — unchanged,
frozen, and unaffected by this Ruleset's existence.

## How does an entrant's action budget work?

Each entrant declares a fixed roster of one or more processes before tick
0 (`declare_processes()`), each with a `share` of the entrant's total
`Q = 8` per-tick budget; shares are converted to integer per-tick
allocations by deterministic largest-remainder rounding, with stable
process-ID tie-breaking. Action slots within one entrant are then handed
out to its own eligible processes **in rotation** — not by declared-list
priority — so declaration order does not act as an undocumented priority
ranking separate from each process's declared share. When disruption makes
a process ineligible, its share is redistributed among the entrant's other
eligible positive-share processes, preserving the entrant's total budget
whenever any of its processes remains eligible.

This round-robin selection (and the redistribution rule around it) is
unchanged from `bytefray-rules-4-alpha2`. `bytefray-rules-4-alpha1` instead
scans an entrant's declared process list from index 0 on every action
slot — a real behavioral difference between the alphas, carried unmodified
into this Ruleset from alpha2's side of it.

## How does READ/WRITE/MOVE work?

Unchanged from both v4 alphas: `READ` and `WRITE` take an **absolute**
arena address, legal only within the acting process's own circular
`reach` of its own current anchor; `MOVE` takes a **signed relative**
delta from the acting process's anchor, clamped to `[-64, 64]` and wrapped
circularly. Reach is declared per process at `[1, arena_size - 1]`
(uncapped) and costs nothing. A legal enemy `WRITE` landing exactly on a
live process's anchor disrupts every enemy process co-located there for
the remainder of that tick (`D = 1`); disrupted processes are eligible
again the following tick. There is no explicit attack, recovery, or
disruption action — disruption is an emergent consequence of an ordinary
`WRITE`.

## What does entrant-level scheduling mean?

Deterministic `K = 2` chunked scheduling with the starting seat rotating
by tick against immutable original seat order (`battle_engine.scheduler.
run_chunked_quota`, `scheduler_chunk_size=2`, `scheduler_rotate_start=True`)
— identical across all three v4 identities. Multiple processes never
multiply an entrant's own `Q = 8` total; scheduling decides which
*entrant* acts, process selection (above) decides which of that entrant's
*own* processes spends the slot.

## What remains unchanged?

Everything not named above, without exception, and identical across all
three v4 identities:

- **Core size.** `CORE_SIZE = 8`, the same fixed constant Ruleset v2
  already uses (`battle_engine.python_runtime.CORE_SIZE`) — not per-match
  configuration.
- **Initial process co-location.** Every declared process starts
  co-located at its entrant's own core base; remote deployment is earned
  with `MOVE`.
- **The visibility contract, the WRITE information boundary, and temporal
  provenance** — the enemy-anchor observation contract documented in full
  in [AGENT_API_V2.md](AGENT_API_V2.md).
- **Quota allocation** (largest-remainder rounding, stable tie-breaking) —
  only *selection order* differs from alpha1, never allocation itself.
- **Scoring, winner resolution.** The same `battle_engine.results.
  resolve_winner` and default weights (`alive`/`kill`/`territory`) every
  other Ruleset uses.
- **Replay schema 4 and the result schema** — see
  [REPLAY_SCHEMA.md](REPLAY_SCHEMA.md), now documented as the stable v4
  replay contract.
- **Every alpha1 deferral**: no dynamic spawning, no resources, no
  probabilistic fog of war, no `SCAN`/`ATTACK`/`DISRUPT` action, no reach
  cap, no larger cores.

## Which runtime is supported?

**Python-runtime only, Agent API v2 only.** `bytefray-rules-4`'s
`RulesetPolicy` declares `supported_runtime_kinds ==
frozenset({"python"})` and `supported_python_api_versions ==
frozenset({2})` — copied verbatim from `bytefray-rules-4-alpha2`'s own
policy fields, not re-derived. A VM/blob entrant, or a Python entrant
declaring Agent API v1, is rejected (`RulesetRuntimeUnsupportedError`/
`RulesetAgentUnsupportedError`) before any entrant executes and before any
replay/result artifact is written — identical to both alphas' existing
enforcement.

## Fixed constants

```python
CORE_SIZE = 8
Q = 8                          # entrant per-tick action budget
ALPHA2_MIN_CORE_SEPARATION = 64  # minimum circular core-base separation
MOVE clamp = [-64, 64]
D = 1                          # disruption duration, in ticks
```

Every constant above is a **Ruleset constant** — part of `bytefray-rules-4`'s
semantic identity, not per-match configuration, and there is no CLI/config
knob for any of them. Arena size, tick limit, and action-budget-per-tick
(`instr_per_tick`) remain ordinary per-match configuration values, not
Ruleset identity — see `docs/RULES.md`'s "Configuration values are not
Ruleset identity".

## Ruleset identity and history

`bytefray-rules-4` is registered in `battle_engine.ruleset_policy.
_RULESET_POLICIES` under its own explicit key, alongside — never aliased
to or from — `bytefray-rules-4-alpha1` and `bytefray-rules-4-alpha2`. It
shares its exact behavioral implementation with `bytefray-rules-4-alpha2`
(the evidence being promoted is intentionally identical to what alpha2
qualified, per the pre-RC research program's finding that no further
gameplay alpha was warranted), but dispatches, hashes into
`canonical_match_id`, and persists as a fully distinct identity — see
`docs/COMPATIBILITY.md` for the full persistence/comparison/resume
behavior this implies.

`bytefray-rules-4-alpha1` and `bytefray-rules-4-alpha2` remain executable,
historical, unedited evidence records of the research that produced this
Ruleset — see [V4_ALPHA1_DESIGN.md](V4_ALPHA1_DESIGN.md),
[V4_ALPHA2_DESIGN.md](V4_ALPHA2_DESIGN.md), and
[docs/research/v4/](research/v4/) for how they got here. This document
describes the stable game; the alpha designs and research reports describe
how it was found.
