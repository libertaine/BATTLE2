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

**Status: implementation complete, not yet released.** See
`docs/V2_0_BETA2_PHASE3_MULTI_ENTRANT_ANALYSIS.md` for the full design
record and qualification report. Summary:

- a new, entrant-symmetric sibling analysis module
  (`evaluation_group_analysis.py`) — per-entrant outcome (winner/
  surviving-non-winner/eliminated, never collapsed to a flat win/loss),
  score/territory/kill metrics, capture attribution and a directed
  captor-to-victim interaction matrix, seat/layout/seed sensitivity — all
  computed with no candidate id as an input, so candidate designation is
  provably presentation-only (`candidate_focused_view`, pure selection);
- a real, previously-undiscovered defect fixed: `SubjectAggregate.score_
  differential_avg`/`territory_differential_avg` were silently computed
  for group cells as if the (nonexistent) single opponent's score were
  zero, producing a number that looked like a real differential but
  wasn't — now `None` for group scopes, unchanged for pairwise;
- a second real defect found via this phase's own characterization and
  fixed: capture-tick values were reported as the match's final tick
  unconditionally, which only equals a specific capture's own tick when
  that capture ended the match — at N >= 3 that is very often false (the
  match keeps running with two-plus entrants alive); capture *facts* and
  *attribution* stay accurate, only the untrustworthy tick value is now
  withheld;
- `evaluations show` (both live-CLI and historical-artifact paths) now
  presents real per-entrant/seat/layout/interaction group analysis in
  place of the "deferred" placeholder, gated behind the same opt-in
  `--no-behavior` real-I/O discipline behavior/capture already use;
- real characterization against three 3-entrant, 5-seed (90-cell) rosters,
  including a direct re-examination of Phase 2's own "Core Tracker 2/54"
  finding — the expanded sample shows a materially different, seat- and
  seed-sensitive rate, demonstrating the original 3-seed sample was too
  small to characterize it reliably;
- Designer integration deliberately not attempted this phase (deferred,
  scoped for a later follow-up) — the analysis/CLI/history layer was
  completed and characterized first, per the milestone's own guardrail
  against letting GUI work drive analysis architecture.

## Phase 4 — Strategic Characterization

**Status: implementation complete, not yet released.** See
`docs/V2_0_BETA2_PHASE4_STRATEGIC_CHARACTERIZATION.md` for the full
research record. Summary:

- an 11-roster, 990-cell pre-registered primary corpus (plus 3 pairwise
  1v1 controls) pointed Phase 3's analysis instrument at Phase 3's own
  open questions — Claimer's Matrix-A dominance, third-party/kingmaking
  effects, seat/layout/seed sensitivity, directed capture interactions,
  and pairwise-vs-group divergence;
- **Claimer's apparent dominance was matchup-specific, not universal**:
  its win rate ranges 36.7%-100% depending on roster composition,
  collapsing sharply whenever a dedicated search-based offense agent
  (Core Tracker/Core Seeker) is present — the same counter-strategy
  alpha.10/alpha.11 already established, confirmed still working under
  Beta2's own methodology at a larger sample;
- a real, reproducible kingmaking-like effect: a passive defensive third
  entrant wins 33-46% of matches purely by outlasting whichever of two
  active rivals a search agent eliminates, without attacking anything
  itself — and a real pairwise-vs-group divergence: Core Tracker beats
  both Claimer and Hunter individually in 1v1 but does not dominate
  either when facing them simultaneously;
- a real, consistent global seat bias (~18pp win-rate spread from seat A
  to seat C across the whole corpus, most plausibly last-write-wins-
  driven) was found and disclosed — real, but not large enough to
  overwhelm strategic differences, and already neutralized at the
  per-entrant level by the existing exhaustive-permutation methodology;
- a tick-budget methodology difference from alpha.11's own 1v1
  measurements was found and explained (not a defect — every within-
  corpus comparison in this phase used one consistent tick budget);
- no engine, scheduler, scoring, or agent code was changed — this was a
  pure characterization phase, and the one instrumentation audit
  performed found no defect.

**`STRATEGIC ASSESSMENT: PROCEED WITH DOCUMENTED CONCERNS`** — no
Ruleset revision is recommended before Beta2 qualification.

## Phase 4.1 — Pre-Qualification Review Remediation

**Status: complete.** See
`docs/V2_0_BETA2_PHASE4_1_PRE_QUALIFICATION_REMEDIATION.md` for the
recovery record and qualification evidence. An independent review found
five high-severity compatibility/correctness gaps after Phase 4. Phase 4.1
repaired group deep verification, self-play artifact health, conservative
multi-death capture timing, historical v1 schedule identity, group
comparison content identity, and duplicate/self-play presentation. It
also documented the deliberate start-aware Python match-identity
transition, retained v4/v5/v6 stored identities without a schema bump,
rejected pairwise orientation flags in group mode, and corrected the Phase
4 research prose/provenance boundary. The Phase 4 strategic assessment is
unchanged and its corpus did not require rerunning because no simulation
outcome or statistic used by that assessment changed.

## Phase 5 — Integrated Beta2 Qualification

**Status: complete; qualified for release, not published.** See
`docs/V2_0_BETA2_PHASE5_INTEGRATED_QUALIFICATION.md` for the evidence and
release decision. The integrated pass re-established v4/v5/v6 identity,
resume, verification, comparison, self-play, generic-N, pairwise, history,
and CLI behavior; built and installed an isolated wheel; and completed the
full test, Ruff, mypy, client, and diff-check gates. No production change
or release blocker was required or found. Phase 4's documented concerns
(roster-composition effects at larger scale, a mechanistic confirmation
of the seat-bias hypothesis, and further kingmaking/non-transitivity
search) carry forward as future research rather than release blockers.

**Release decision: QUALIFIED FOR V2.0.0-BETA2 RELEASE.** Publication,
including the package-version update, final release-artifact build, merge,
tag, push, and GitHub prerelease, remains a separate release-preparation
task.

---

Additional Beta2 phases beyond the five above are not pre-planned; if
evidence from a later phase's qualification suggests the remaining scope
needs a narrower or wider phase boundary than sketched here, that revision
happens explicitly, the same way every other milestone in this project has
been re-scoped from real qualification evidence rather than a fixed plan.
(Phase 2's own plan sketch originally allotted four phases after Phase 1;
Phase 2 absorbed the CLI-workflow scope originally earmarked for a
separate phase. Phase 3's own findings are what introduced this revision's
new Phase 4 — "Integrated Beta2 Qualification" moved to Phase 5 rather
than being dropped.)
