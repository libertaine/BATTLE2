# Bytefray Ruleset v2 (Beta) Reference

This document defines **Ruleset v2** (`bytefray-rules-2`), the beta
gameplay-semantics identity introduced in `v2.0.0-beta1`. It describes the
beta game as it plays today — how a match differs from Ruleset v1 and what
stays the same — not how the research that produced it was conducted. For
that evidence trail, see `docs/V2_0_ALPHA_RESEARCH_SUMMARY.md` and
`docs/V2_0_RULESET_V2_CANDIDATE.md`.

`docs/RULES.md` remains the frozen, unmodified Ruleset v1 reference. This
document does not replace it and does not repeat material that is genuinely
unchanged in more detail than necessary — where a rule is identical to
Ruleset v1, this document says so and points back to `docs/RULES.md` rather
than duplicating the explanation.

**Status: beta candidate semantic identity**, not yet claimed permanently
immutable. See `docs/COMPATIBILITY.md`'s "Ruleset v2 (beta)" section for
what that status does and does not promise.

## What makes v2 different from v1, in one paragraph

Ruleset v2 adds exactly one new mechanic on top of everything Ruleset v1
already does: each entrant has a small, fixed **core** region of its own
arena territory, and an entrant dies if it ever loses ownership of every
cell in that core. To make that mechanic a genuine strategic contest rather
than a coin flip on whether anyone happens to notice a core exists, v2 also
guarantees that a living entrant's own core is never *silently* blank —
without granting any privileged information, changing what any action does,
or making a core any harder to destroy. Everything else — scoring,
scheduling, winner resolution, the Agent API, arena addressing — is
unchanged from Ruleset v1.

## How is a core placed?

Every entrant's core is a fixed window of `CORE_SIZE = 8` contiguous arena
bytes, beginning at `entrant.start % arena_size` (the same `MatchEntrant.start`
value Ruleset v1 already uses as a plain placement configuration value — see
`docs/RULES.md`'s "Placement" note). The window uses the arena's ordinary
`pos % arena_size` wraparound addressing, identical to every other access.

- The core is fixed at match construction and never moves — unlike an
  entrant's own `pc`, which its actions can relocate.
- It is **not** derived from program size, write count, or any
  entrant-controlled property.
- `CORE_SIZE` is a fixed Ruleset constant (`battle_engine.python_runtime.CORE_SIZE`),
  not per-match configuration — see "Fixed constants" below.
- Ownership of all eight cells is established for the owning entrant at
  match initialization, before any `reset()`/`act()` call, through the
  engine's ordinary write path — this is the Python-runtime equivalent of
  the VM's own spawn-time code-loading ownership.

## How is a core observed?

> Every cell of a living entrant's core that is currently owned by that
> entrant holds a non-zero byte at every tick boundary.

This is realized as two rules:

1. **Seeding.** A core's cells are seeded with the public constant
   `CORE_BEACON_BYTE = 0xCE` (`battle_engine.python_runtime.CORE_BEACON_BYTE`)
   instead of the arena's ordinary untouched-default `0`.
2. **Maintenance.** At the end of every tick — after that tick's capture
   check, before scoring — any cell of a *living* entrant's own core that
   entrant **still owns** and whose content has gone blank (`0x00`) is
   rewritten back to the beacon, attributed to that same owner.

What this does and does not mean, precisely:

- It does **not** mean any entrant is told where any other entrant's core
  is. `CORE_BEACON_BYTE` is public Ruleset knowledge — on the same footing
  as `CORE_SIZE` — not privileged information about a specific opponent.
  Discovering a core still costs ordinary `READ` actions against addresses
  the searcher chose itself.
- It does **not** repair anything an attacker has done. Maintenance only
  ever touches cells the owner **already owns**, and only ever restores
  `0x00` — never a non-zero byte. An attacker's write is never reverted, no
  ownership is ever restored, and a defender's own signature byte (from its
  own `READ`-then-compare repair logic, for instance) is never overwritten
  by maintenance.
- It does **not** require any agent to recognize the beacon value. Any
  content-based search that already treats "non-zero and not mine" as
  worth investigating observes the beacon for free — no agent needed to
  change to benefit.
- The footprint exists **independent of the owner's own behavior** — an
  entrant that never writes to its own core is exactly as observable as one
  that actively defends it. This is the specific defect Ruleset v2 closes
  relative to `bytefray-rules-2-alpha1`, where a core seeded at `0` was
  indistinguishable from untouched arena, making an undefended core
  invisible and a defended one findable *because* it was defended.

## How is a core damaged, and when does capture happen?

Damage is nothing new: any entrant's ordinary `WRITE` to any address
already contests ownership under Ruleset v1's arbitrary-read/write rule
(`docs/RULES.md`'s "Arbitrary READ/WRITE"). A core cell is exactly as
ordinary an arena byte as any other for this purpose — writing to it, like
writing anywhere else, simply claims it.

**Capture.** An entrant is core-captured when it owns **zero** cells of its
own core — deliberately "owns zero," not "one opponent owns all of it," so
the rule stays well-defined for any entrant count, and reduces naturally to
complete displacement in the two-entrant case.

**Timing.** Checked once per tick, immediately after that tick's entrant
action blocks and before scoring — a captured entrant receives no
alive/territory credit for the tick it dies on, and gets no extra turn,
exactly matching Ruleset v1's ordinary `HALT` timing.

**Attribution.** Kill credit goes to whichever entrant's `WRITE` took the
final owner-held core cell that tick, when that is unambiguously
determinable from the tick's actual write order; otherwise the death is
unattributed, exactly like an ordinary Python halt/forfeit under Ruleset
v1. This is the **only** Python mortality attribution Ruleset v2 adds —
`termination_reason = "core_captured"` is an additive value of the
existing free-form field, not a new enum member, and Ruleset v1's own kill
attribution (VM-only) is untouched.

**Observability is not invulnerability.** Nothing about the observability
rule makes a core harder to destroy. A core is exactly as killable under
Ruleset v2 as under `bytefray-rules-2-alpha1` — observability changes
*whether an attacker can find a core*, never *whether a found core can be
taken*.

## What does order mean?

Scheduling is unchanged from Ruleset v1: sequential, per-entrant action
blocks in spawn/request order (`docs/RULES.md`'s "Scheduling order"). Under
Ruleset v2 this matters more than it did under v1 in one concrete way:
because capture is checked once per tick after all of that tick's action
blocks, an entrant scheduled later in a tick where a core changes hands can
act on information a same-tick earlier entrant could not yet see, and
whichever entrant's write happens to land last in a contested tick decides
attribution. **This is deliberately retained, not changed** — it is treated
as a real, disclosed competitive property (the same kind of first-mover
advantage Ruleset v1 already documents), not a defect. It does create an
obligation for how Ruleset v2 matches should be *evaluated* — an evaluation
must balance scheduler order rather than sample it once — but that is a
beta2 methodology concern (see `docs/V2_0_BETA1_PLAN.md`), not a Ruleset v2
gameplay rule.

## What remains unchanged?

Everything not named above, without exception:

- **Arena.** Same circular, mutable byte array; same ownership-as-most-recent-writer
  model; same arbitrary-read/write rule. See `docs/RULES.md`'s "Arena" and
  "Ownership".
- **Territory.** No decay, no expiry, no maintenance cost, no scoring-age
  term. Ownership is permanent until overwritten, exactly as in Ruleset v1.
- **Scoring.** Identical default weights and formulas (`alive`, `kill`,
  `territory`) — see `docs/RULES.md`'s "Scoring". The only behavioral
  change is that the kill formula's precondition can now actually be met in
  a Python match, via core capture; no weight or formula changed.
- **Winner resolution.** The single authoritative
  `battle_engine.results.resolve_winner`, unmodified: a dead entrant cannot
  win while any entrant survives; otherwise the unique highest score wins
  under `score`/`score_fallback`, or there is no winner under `survival`
  ties.
- **Seed.** Same mechanism and derivation as Ruleset v1
  (`docs/AGENT_API_V1.md`'s frozen entrant-seed formula) — unchanged, only
  more strategically important now that a search-based reference agent
  (Core Tracker) consumes `context.rng`.
- **Multi-entrant behavior.** The native match/scheduling stack is already
  entrant-count generic; every rule in this document is written to be
  well-defined for any entrant count. Not a required product workflow in
  beta1 — see `docs/V2_0_BETA1_PLAN.md`.

## Which runtime is supported?

**Python-runtime only.** Vulnerable Core and core observability are
implemented only in `battle_engine.python_runtime`/`supervised_runtime`,
which have no VM equivalent. As of `v2.0.0-beta1` Phase 2, this is enforced
as a product execution-compatibility boundary, not merely a fact about
where the mechanic happens to be implemented: **a match requested under
`bytefray-rules-2` with any VM entrant is rejected before any entrant
executes**, with a typed, actionable error naming the Ruleset and pointing
to `bytefray-rules-1` for VM play — see
`docs/V2_0_BETA1_PHASE2_PRODUCT_EXECUTION.md`. Bytefray never dispatches a
VM entrant under this identity and silently runs a core-less game; it fails
closed instead. VM parity is not claimed and is not part of this beta.

This restriction applies only to the permanent `bytefray-rules-2` identity.
The historical experimental identities `bytefray-rules-2-alpha1` and
`bytefray-rules-2-alpha11` keep their original behavior unchanged for
historical-artifact compatibility: they still dispatch successfully on a VM
entrant, with the core mechanic simply inert (scheduling/termination
identical to Ruleset v1, no Vulnerable Core semantics). This alpha-only
carve-out exists so that no already-executed historical alpha match's
behavior is retroactively altered by a beta-era product decision — it is
not evidence that VM play is, or was ever, a supported way to exercise
Ruleset v2's actual gameplay.

## Does the Agent API change?

**No.** Agent API v1 is unchanged and is the supported Python programming
contract for both Ruleset v1 and Ruleset v2 — the same loading/lifecycle
contract, the same `Observation`/`AgentAction` shape, the same deterministic
RNG derivation. `Observation`/`MatchContext` continue to expose nothing
about any other entrant: no identity, no position, no core address, no
ownership, no score. An agent written against `docs/AGENT_API_V1.md` runs
unmodified under either Ruleset — the only difference is what the shared
arena does around it. See `docs/COMPATIBILITY.md`'s "Ruleset v2 (beta)"
section for the independent-axes statement this follows from.

## Fixed constants

```python
CORE_SIZE = 8
CORE_BEACON_BYTE = 0xCE
```

Both are **Ruleset constants** — part of `bytefray-rules-2`'s semantic
identity, not per-match configuration, and there is no CLI/config knob for
either. A future experiment that needs a different value for either
constant requires its own, distinct Ruleset identity — see
`docs/V2_0_BETA1_PLAN.md`'s "Fixed constants decision".

## Ruleset identity and history

`bytefray-rules-2` is registered in
`battle_engine.ruleset_policy._RULESET_POLICIES` under its own explicit
key, alongside — never aliased to or from — `bytefray-rules-1`,
`bytefray-rules-2-alpha1`, and `bytefray-rules-2-alpha11`. It shares its
exact behavioral implementation with `bytefray-rules-2-alpha11` (the
evidence being promoted is intentionally identical to what alpha.11
validated), but dispatches, hashes into `canonical_match_id`, and persists
as a fully distinct identity — see `docs/COMPATIBILITY.md` for the full
persistence/comparison/resume behavior this implies.

`bytefray-rules-2-alpha1` and `bytefray-rules-2-alpha11` remain executable,
historical, uncorrected evidence records of the research that produced this
Ruleset — see `docs/V2_0_ALPHA_RESEARCH_SUMMARY.md` for how they got here.
This document describes the beta game; the alpha reports describe how it
was found.
