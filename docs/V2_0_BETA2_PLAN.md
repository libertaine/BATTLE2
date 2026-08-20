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

**Status: implementation complete, not yet released.** See
`docs/V2_0_BETA2_PHASE2_MULTI_ENTRANT_EVALUATION.md` for the full design
record and qualification report. Summary:

- a generic entrant/seat/permutation/layout model (`EvaluationSeatAssignment`,
  `seat_label`, `enumerate_seat_assignments`, `EvaluationLayout`,
  `standard_layouts`), replacing 1v1-only vocabulary where a true seat
  model is needed, while leaving Phase 1's `EvaluationPlacement`/
  `orientation` (1v1) path completely untouched;
- real 3-entrant evaluation shipped through the existing `agents evaluate`
  CLI (`--group`, reusing `candidate_id`/`--opponents`/`--ruleset`/
  `--seeds` unchanged) — this phase delivered further than originally
  scoped, absorbing what the prior plan sketch called "Phase 3" CLI work,
  since it turned out to require no separate CLI surface;
- exhaustive seat-permutation scheduling for N=3 (6 permutations), informed
  directly by alpha.11's 84% 3-way permutation-sensitivity finding, with a
  disclosed (not solved) scaling boundary for larger N;
- winner semantics fully reused from the engine's own already-N-generic
  `resolve_winner` (survivor-only eligibility, alpha.4.1) — no second
  winner-resolution algorithm was written;
- a third additive schema/identity version (`SCHEMA_VERSION_V2_GROUP`/
  `IDENTITY_VERSION_V2_GROUP` = 6), leaving v1 (4) and Phase 1's pairwise v2
  (5) completely unchanged;
- resume/comparison fail closed across roster/seat/layout/methodology
  changes, again via the existing identity-driven gating with no new
  gating code;
- a genuine Phase 1 defect (an evaluation-history health-check rehash that
  never matched Phase 1's own identity payload, producing a false
  `planned_identity_inconsistent` on every 1v1-v2 artifact) was discovered
  during this phase's own characterization and fixed, with regression
  coverage;
- real characterization against two 3-entrant rosters (closing Phase 1's
  disclosed Hunter-coverage gap) and a self-play (duplicate-agent) roster,
  proving the architecture executes correctly through the real engine
  boundary, not just schedule generation.

Multi-entrant behavior/capture aggregate analysis is deliberately deferred
— see Phase 3 below.

## Phase 3 — Multi-Entrant Analysis & Strategic Metrics

**Status: planned, not started.** Purpose: proper N-entrant behavior/
capture aggregate analysis, building on Phase 2's roster/seat/layout
identity rather than Phase 1's 1v1-shaped `evaluation_behavior.py`/
`evaluation_capture.py` internals (both currently resolve a cell's subject
via a 2-value orientation-to-slot mapping, meaningless for a group cell
whose subject seat varies per cell — Phase 2 explicitly guards this rather
than computing wrong data, deferring the real fix here).

- per-seat-aware Tier-2 result.json readers for `evaluation_behavior`/
  `evaluation_capture`, replacing the orientation-based slot resolution
  with `EvaluationCell.subject_seat`;
- multi-entrant capture/behavior aggregate reporting in both the live CLI
  and `evaluations show`, replacing the current "deferred" disclosure;
- Designer evaluation-history/results consumers correctly disclose
  multi-entrant methodology, mirroring Phase 1/2's "minimal compatibility
  presentation adaptation" precedent rather than new complex controls;
- evidence-driven evaluation of whether exhaustive N! seat-permutation
  scheduling needs a balanced/rotation policy alternative before N grows
  past 3 (Phase 2 §3/§17's disclosed, unsolved scaling boundary).

## Phase 4 — Integrated Beta2 Qualification

**Status: planned, not started.** Purpose: an integrated regression/
qualification pass across every Beta2 phase together, mirroring Beta1's
own Phase 5 — full test suite, Ruff, mypy, `git diff --check`, a real
source-tree smoke, and (if packaging modules changed) an isolated-wheel
smoke. No new feature work belongs in this phase.

---

Additional Beta2 phases beyond the four above are not pre-planned; if
evidence from Phase 3 qualification suggests the multi-entrant analysis
scope needs a narrower or wider phase boundary than sketched here, that
revision happens explicitly, the same way every other milestone in this
project has been re-scoped from real qualification evidence rather than a
fixed plan. (Phase 2's own plan sketch originally allotted four phases
after Phase 1; Phase 2 absorbed the CLI-workflow scope originally
earmarked for a separate phase, so this revision reflects what was
actually built, not a re-guess.)
