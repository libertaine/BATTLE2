# Bytefray v2.0.0-beta2 — Evaluation & Multi-Entrant Methodology Plan

This is the working plan for `v2.0.0-beta2`, on `v2.0-beta2-development`
(branched from `main` at the exact post-`v2.0.0-beta1`-release commit — see
`docs/V2_0_BETA2_PHASE1_EVALUATION_METHODOLOGY.md` §1–2 for the verified
branch lineage). It is not a roadmap duplicate — see `docs/ROADMAP.md` for
shipped-milestone history and `docs/V2_0_BETA1_PLAN.md` for the prior
milestone this one builds on.

Beta1 froze Ruleset v2's gameplay semantics and integrated it into
supported execution/product boundaries, but deliberately left `agents
evaluate` v1-only, with no scheduler-order/placement/seed balancing and no
capture-aware evaluation output. Beta2 closes that gap:

> Beta2 evaluates the game. It does not change the game.

No gameplay, Agent API, or Ruleset-v2 semantic change belongs anywhere in
this milestone.

## Phase 1 — Ruleset-v2 1v1 Evaluation Methodology

**Status: implementation complete, not yet released.** See
`docs/V2_0_BETA2_PHASE1_EVALUATION_METHODOLOGY.md` for the full design
record and qualification report. Summary:

- explicit `agents evaluate --ruleset {bytefray-rules-1,bytefray-rules-2}`,
  with the historical v1 methodology preserved byte-for-byte when omitted
  or explicitly `bytefray-rules-1`;
- a standard, mechanically-derived 1v1 placement set (three deterministic
  conditions, expressed as fractions of arena size) for v2 methodology;
- a standard 5-seed default (`1, 2, 3, 4, 5`) for v2, matching alpha.10/
  alpha.11's own convention, always overridable;
- scheduler-order balancing (already present via entrant orientation)
  disclosed explicitly for v2 and kept structurally distinct from
  placement;
- every gameplay-relevant dimension (Ruleset, order, placement, seed,
  ticks) entering canonical evaluation/schedule identity, with v1 identity
  provably unchanged throughout;
- an additive, request-methodology-resolved schema/identity version
  (`SCHEMA_VERSION_V2`/`IDENTITY_VERSION_V2` = 5), never touching v1's
  existing `4`;
- capture/core interaction as a new, independent evidence category
  (`battle_engine.evaluation_capture`), kept structurally separate from
  win/loss/score/behavior;
- resume/comparison fail closed across any methodology change, using the
  existing architecture's own identity-driven gating — no new gating code
  was needed once identity was correct;
- real methodology characterization against Claimer/Hunter/Core Defender/
  Core Tracker/Reactive Core Defender, reproducing alpha.9/alpha.10's
  scheduler-order effect through the shipped product path for the first
  time.

This phase is 1v1 only. It does not implement multi-entrant evaluation —
see Phase 2 below and the Phase 1 report's §24/§29 for the identified
extension seam and explicit non-goals.

## Phase 2 — Multi-Entrant Evaluation Model

**Status: planned, not started.** Purpose: extend the condition/identity
model Phase 1 built to a generic N-entrant representation, without
discarding Phase 1's work.

- generic seat/permutation identity, replacing Phase 1's 1v1-named
  `EvaluationPlacement`/`orientation` vocabulary where a true seat model is
  needed, while keeping every identity/schema/resume/comparison mechanism
  Phase 1 built (already entrant-count-agnostic in its hashing/versioning
  design);
- 3-entrant (and, if evidence warrants, N-entrant) schedule identity and
  scheduler-order permutation generation, informed directly by alpha.11
  §12's 84% permutation-sensitivity finding in contested trios;
- winner/placement semantics for more than two entrants (survivor-only
  eligibility, alpha.4.1, already retained and unconditional on entrant
  count);
- a generic cell/result representation that a 1v1 evaluation can still
  degrade to cleanly, so Phase 1's existing 1v1 methodology remains a
  supported special case, not a separate code path.

## Phase 3 — Multi-Entrant Product Execution / Evaluation Workflow

**Status: planned, not started.** Purpose: turn Phase 2's model into a
supported product workflow.

- CLI support for a 2/3-entrant `agents evaluate` invocation;
- preset support for multi-entrant opponent/seat configuration;
- `evaluations list`/`show` presentation for multi-entrant artifacts.

## Phase 4 — Evaluation Presentation / Designer Compatibility

**Status: planned, not started.** Purpose: Designer/history/compare
presentation for multi-entrant evaluation and capture/core evidence,
without a broad Beta3 Designer-workflow redesign (Beta3 owns that).

- Designer evaluation-history/results consumers correctly disclose
  multi-entrant methodology, mirroring Phase 1's "minimal compatibility
  presentation adaptation" precedent rather than new complex controls;
- capture/core display integration in the Designer results view.

## Phase 5 — Integrated Beta2 Qualification

**Status: planned, not started.** Purpose: an integrated regression/
qualification pass across every Beta2 phase together, mirroring Beta1's
own Phase 5 — full test suite, Ruff, mypy, `git diff --check`, a real
source-tree smoke, and (if packaging modules changed) an isolated-wheel
smoke. No new feature work belongs in this phase.

---

Additional Beta2 phases beyond the five above are not pre-planned; if
evidence from Phase 2/3 qualification suggests the multi-entrant scope
needs a narrower or wider phase boundary than sketched here, that revision
happens explicitly, the same way every other milestone in this project has
been re-scoped from real qualification evidence rather than a fixed plan.
