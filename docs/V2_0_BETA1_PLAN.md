# Bytefray v2.0.0-beta1 — Ruleset v2 Integration Plan

This is the working plan for `v2.0.0-beta1`, the first beta task on
`v2.0-beta1-development` (branched from `v2.0-development`'s alpha-closeout
commit — see `docs/V2_0_ALPHA_RESEARCH_SUMMARY.md`). It records the
semantic contract this phase freezes and the phases that follow it. It is
not a roadmap duplicate — see `docs/ROADMAP.md` for shipped-milestone
history and `docs/V2_0_RULESET_V2_CANDIDATE.md` for the full evidence-backed
semantic definition this plan promotes.

The central transition this document exists to record:

> **Alpha research is now evidence history. `bytefray-rules-2` becomes the
> beta compatibility contract.**

## 1. Ruleset-v2 semantic contract frozen for beta1

Everything below is adopted **as validated by alpha.11**, not redesigned.
Where this section says "unchanged," it means byte-identical to
`bytefray-rules-2-alpha11` as documented in
`docs/V2_0_RULESET_V2_CANDIDATE.md`.

### Vulnerable Core

- `CORE_SIZE = 8`, contiguous cells, anchored at `entrant.start % arena_size`,
  ordinary arena wraparound.
- Ownership seeded at initialization (before any `reset()`/`act()`), routed
  through the same write path as every other arena write.
- Death when an entrant owns zero of its own core cells — deliberately
  "owns zero," not "one opponent owns all of it," so the rule stays
  well-defined for any entrant count.
- Checked once per tick, after that tick's entrant action blocks, before
  scoring.
- Attribution from the final ownership-removing write when unambiguous;
  otherwise unattributed, exactly like an ordinary Python halt/forfeit.
- `termination_reason = "core_captured"` — an additive value of the
  existing free-form field, no new enum member.

### Core observability

- `CORE_BEACON_BYTE = 0xCE`, a public Ruleset constant.
- Core cells are seeded non-zero (the beacon) instead of `0x00`.
- A living entrant's self-owned core cell may not remain blank at a tick
  boundary — maintenance restores exactly the blank (`0x00`) case, and
  nothing else.
- Maintenance never restores ownership, never repairs attacker damage, and
  never overwrites a defender's own non-zero signature.
- No privileged Agent API metadata of any kind — the footprint is reachable
  only through an ordinary `READ`.

### Territory

Unchanged from Ruleset v1: no decay, no expiry, no age score, no
maintenance tax. **Territory maintenance was considered as alpha.11's
Resolution B but was never entered, because Resolution A passed** — the
gate that would have opened Resolution B never opened. This is not deferred
work; it is a contingency a passing gate correctly bypassed.

### Scoring

Unchanged from Ruleset v1 in every weight and formula (`alive`, `kill`,
`territory`). Not tuned in beta1 — alpha.3 and alpha.5 already
closed-form-proved that reweighting the existing three-weight model cannot
solve the ecology problem structurally; alpha.11 resolved it with an
information rule instead.

### Scheduler

Retained: sequential, contiguous per-entrant action blocks, in spawn/request
order. Order is an accepted competitive factor (alpha.9/alpha.11), not a
defect — beta evaluation work (beta2) must balance it rather than sample it
once.

### Capture resolution

Retained: once per tick, after that tick's action blocks, before scoring.
Scheduler-order sensitivity in contested cells is an accepted gameplay
property, not deferred as unknown.

### Winner eligibility

Retained from alpha.4.1, via the single authoritative
`battle_engine.results.resolve_winner`: a dead entrant cannot win while any
entrant survives.

### Agent API

Retained: **Agent API v1**. There is no Agent API v2 in Bytefray 2.0 beta1
— alpha.1 through alpha.11 found no concrete need for one across deliberate
offense, reactive defense, blind defense, or placement-agnostic
reconnaissance.

### Python/VM boundary

Ruleset-v2 beta gameplay is **Python-runtime supported only**. The native
VM path is unchanged, continues to run `bytefray-rules-1`, and has no
Vulnerable Core / observability implementation — a VM match requested under
`bytefray-rules-2` dispatches successfully (the policy resolves) but the
mechanic is simply inert on that runtime, exactly as it already is for
`bytefray-rules-2-alpha1`/`-alpha11`. VM parity is explicitly deferred, not
implemented here.

### Multi-entrant

Ruleset semantics remain entrant-count generic (every rule above is
well-defined for any entrant count). Beta1 does not productize a 3+-entrant
CLI/evaluation/Designer workflow — that decision is deferred to beta2 (see
§3 below).

## 2. Fixed constants decision

For Bytefray 2.0 Ruleset v2:

```python
CORE_SIZE = 8
CORE_BEACON_BYTE = 0xCE
```

are **Ruleset constants**, part of the semantic identity of
`bytefray-rules-2`, not per-match user configuration. There is no CLI/config
knob for either. If a future experiment needs a different value for either
constant, that requires a new, distinct Ruleset semantic identity — changing
either value silently under the same `bytefray-rules-2` string would be
exactly the kind of undisclosed gameplay-semantic drift `docs/RULES.md`'s
bump policy exists to prevent.

## 3. Permanent Ruleset-v2 identity

`bytefray-rules-2` (`battle_engine.ruleset_policy.BYTEFRAY_RULESET_V2_ID`)
is now a real, permanently registered compatibility identity:

- `bytefray-rules-1` remains frozen and unchanged.
- `bytefray-rules-2-alpha1` remains executable with its exact historical
  (non-observable-core) semantics.
- `bytefray-rules-2-alpha11` remains executable with its exact historical
  semantics.
- `bytefray-rules-2` carries the same Vulnerable Core + Consistent Core
  Observability semantics as `bytefray-rules-2-alpha11`, because that is
  exactly the evidence being promoted — but it is registered under its own
  explicit key in `battle_engine.ruleset_policy._RULESET_POLICIES`, and
  `battle_engine.rules._RULESET_ALIASES` gains **no** entry aliasing it to
  or from `bytefray-rules-2-alpha11` (or anything else). The two identities
  share their behavioral implementation in `battle_engine.python_runtime`
  (there was no reason to duplicate the logic once the semantics were
  intentionally identical at promotion time) but are dispatched, hashed,
  and persisted as distinct identities throughout.
- Canonical match identity (`match_service.canonical_match_id`) already
  hashes `ruleset_id` as a first-class, sibling-to-`reproducibility` input —
  no new plumbing was required for a `bytefray-rules-2` match to receive a
  `match_id`/`result_id`/`replay_id` distinct from an otherwise-identical
  v1/alpha1/alpha11 match.
- `evaluation_history`'s existing `rules_id`-keyed comparison-alignment
  refusal already refuses to align cells across differing Ruleset
  identities, and `agent_evaluation`/`tournament_service`'s existing
  resume-mismatch checks already refuse to resume a cell whose recorded
  `ruleset_id` disagrees with what was requested — both mechanisms are
  generic over the identity string and required no beta1-specific code to
  cover the new identity correctly (see
  `engine/tests/test_ruleset_v2.py`'s resume/comparison tests, which
  exercise this directly).

See `engine/tests/test_ruleset_v2_promotion_equivalence.py` for the direct
proof that `bytefray-rules-2-alpha11` and `bytefray-rules-2` produce
identical semantic output (winner, scores, statistics, ownership, capture,
attribution, termination, replay content) for byte-identical inputs,
differing only in the identity fields that are expected to differ.

## 4. Core Tracker beta cleanup

Alpha.11 disclosed, and deliberately left unfixed for experimental
validity, a minor reference-agent inefficiency: Core Tracker could
encounter its **own** core beacon during its scan, classify it as foreign
(since the beacon differs from its own signature), and waste roughly 21
actions (1 scan hit + 4 probe reads + a 16-action assault burst) probing
and assaulting its own, already-owned cells.

Beta1 fixes this with a minimal, self-knowledge-only filter: Core Tracker
now remembers its own core anchor from its own `observation.pc` (exactly
the technique `expand_cursor` already used) and rejects any scan/probe hit
whose address falls inside its own `CORE_SIZE_HINT`-wide core region before
treating it as evidence. This is **self-filtering, not offensive
retuning** — no opponent coordinates, no ownership access, no
beacon-specific shortcut, no historical placement value, and no other
constant (search stride, probe offsets, confirmation threshold, assault
window/size) changed. See
`engine/src/battle_engine/data/reference_agents/core_tracker/agent.py`'s
own "Revision note (v2.0.0-beta1...)" docstring and
`engine/tests/test_v2_alpha8_core_tracker.py`'s "Self-core filtering"
section for the acceptance coverage: the agent's own core never triggers a
probe/assault; an external region carrying the identical beacon byte, just
outside the agent's own core, still does; the fix respects arena wrap; and
every pre-existing alpha.8/alpha.11 behavioral expectation continues to
pass unchanged (nothing in the existing suite depended on the
self-collision).

Core Tracker's beta1 role: a **Ruleset-v2 reference offense benchmark**,
not a claim of canonical optimal attack strategy. Claimer, Hunter, Core
Defender, and Reactive Core Defender remain important regression/reference
strategies. The historical Core Seeker remains a characterization fixture
(its fixed, placement-dependent scan schedule is the documented subject of
alpha.6/alpha.7, not a benchmark to keep improving) and is retained, not
removed.

## 5. Documentation delivered in this phase

- `docs/V2_0_ALPHA_RESEARCH_SUMMARY.md` — durable alpha-series synthesis,
  alpha research formally closed.
- `docs/ROADMAP.md` — replaced the stale "v2.x research boundary" framing
  with "v2.0 Alpha Research — Complete" plus the beta1–rc1 path.
- `docs/FUTURE_PLANS.md` — updated stale v2-related status language;
  territory maintenance/decay, Agent API v2, explicit `ATTACK`, and
  multiprocess/replication dispositions all now reflect the alpha evidence.
- `docs/COMPATIBILITY.md` — documents `bytefray-rules-2` as a beta candidate
  semantic identity, independent of Agent API version.
- `docs/RULES.md` / `docs/RULES_V2.md` — normative Ruleset-v2 documentation
  (see whichever structure the accompanying commit actually chose — check
  `docs/RULES.md`'s own top-of-file pointer if this plan and that document
  ever appear to disagree; the rules document is authoritative for its own
  structure).
- This document.

## 6. What beta1 explicitly does not do

Per the governing task's scope exclusions, none of the following belong to
this first beta task: evaluation methodology expansion, seed matrix
productization, placement matrix productization, 3-way evaluation or
Designer workflow, scheduler changes, capture-timing changes, scoring
changes, territory decay, core-size/beacon configuration, Agent API v2, VM
Ruleset-v2 mechanics, multiprocess agents, replication, an explicit
`ATTACK` opcode, translation/remapping, broad arena-size changes, Replay
Viewer HUD redesign, Designer visual redesign, installer changes, version
bump, beta packaging, tag, release, push, main merge, or origin
reconciliation.

## 7. Later beta1 phases

**Phase 1 (semantic identity) is complete** — this document's own subject:
the permanent `bytefray-rules-2` identity, Core Tracker beta cleanup, and
the documentation delivered in §5, all committed on
`v2.0-beta1-development`.

**Phase 2 (product execution integration) is complete** — see
[V2_0_BETA1_PHASE2_PRODUCT_EXECUTION.md](V2_0_BETA1_PHASE2_PRODUCT_EXECUTION.md)
for the full record. Summary: `--ruleset {bytefray-rules-1,bytefray-rules-2}`
is now explicit CLI surface on `bytefray run`/`agents test`/`tournament`,
defaulting to `bytefray-rules-1` when omitted; an authoritative, fail-closed
runtime-kind check on `RulesetPolicy`/`NativeMatchService.run` rejects any
VM entrant requested under permanent `bytefray-rules-2` before execution,
while `bytefray-rules-1` and the historical alpha identities keep their
exact prior VM behavior; `agents evaluate` remains implicitly v1-only, with
no accidental v2 evaluation exposed. No gameplay semantic changed; the
permanent-v2 promotion-equivalence corpus passes unmodified.

**Phase 3 (replay v2 semantics & status-model preparation) is complete** —
see [V2_0_BETA1_PHASE3_REPLAY_SEMANTICS.md](V2_0_BETA1_PHASE3_REPLAY_SEMANTICS.md)
for the full record. Summary: `battle_client.replay_status.
get_entrant_statuses` derives per-entrant alive/dead status, Ruleset-v2
core integrity/capture/attribution, and existing score/territory/kill
facts entirely from the already-canonical `battle2.replay` v3 artifact —
including each Python entrant's own core-anchor address, recovered from
tick-0 `memory_diffs` rather than added as a new persisted field. No
replay schema bump. Core integrity is derived strictly from reconstructed
ownership, never byte content. `battle_engine` source is untouched (empty
diff) — this phase changed only `battle_client` (one additive
`ReplaySession` method, one new domain module) and tests. HUD
rendering/layout is unchanged; the Phase-4 integration seam is documented,
not implemented.

**Phase 4 (Replay Viewer HUD separation) is complete** — see
[V2_0_BETA1_PHASE4_REPLAY_HUD.md](V2_0_BETA1_PHASE4_REPLAY_HUD.md) for the
full record. Summary: the interactive Pygame Replay Viewer's window is now
tiled into three non-overlapping bands — a top HUD band (match header + one
status card per entrant), an unobstructed middle arena band, and a bottom
footer band (playback/tick, a compact status/event message, controls, and
the relocated territory-history graph) — via the new, Pygame-free
`battle_client.hud_layout` module (geometry + text formatting, directly
testable without a window). Entrant status (alive/dead, Ruleset-v2 core
integrity/capture/attribution, score, territory, kills) is read entirely
from `battle_client.replay_status.get_entrant_statuses` (the Phase-3 status
model); the renderer derives no Ruleset semantics itself. Ruleset v1 shows
no core field; Ruleset v2 shows core integrity/capture/attribution with
score/territory/kills kept visually distinct from life state. The card row
is N-entrant generic (verified for two and three entrants, no two-slot
assumption). The default arena viewport size is unchanged
(`960x600`); only the total window grows by the two bands' fixed height
(`160px`) to make room for them. No gameplay, replay-schema, or evaluation
change — `engine/src/battle_engine` has an empty diff for this phase.
Agent Designer visual work remains explicitly deferred (not started this
phase — see that document's "Beta1 Phase-5 boundary" section).

### Phase 5 — Beta1 integrated qualification (next)

- Ruleset identity, v1 compatibility, v2 execution, reference agents, and
  replay/result integrity all qualified together.
- Wheel/frozen packaging paths qualified as appropriate.
- Beta release readiness assessment.

## 8. Boundaries to later beta/RC releases

### v2.0.0-beta2 — Evaluation & Multi-Entrant Methodology

Ruleset-v2 evaluation methodology (order/placement/seed balancing per
`docs/V2_0_RULESET_V2_CANDIDATE.md` §12's requirements), scheduler/order
balancing tooling, the multi-entrant evaluation/productization decision
(officially support 2-entrant and 3-entrant product/evaluation workflows if
qualification stays clean — recorded as a beta2 recommendation, not
implemented here or exposed in Phase 1), and core/capture metrics as
first-class evaluation outputs.

### v2.0.0-beta3 — Workflow & Compatibility Stabilization

Agent Designer and Replay Viewer v2 integration, CLI/workflow updates,
multi-entrant workflow if beta2 adopts it, historical-artifact
qualification, and packaging/user-workflow stabilization.

### v2.0.0-rc1 — Release Qualification

Release qualification only — no gameplay design work belongs here.

Additional beta releases beyond beta3/rc1 are evidence-driven only and are
not pre-planned.
