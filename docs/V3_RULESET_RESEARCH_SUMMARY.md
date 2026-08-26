# Bytefray v3 Ruleset Research — Summary and Index

This is the navigation entry point for the v3 gameplay-research program. It
does not duplicate the program's evidence — that lives in the ten reports it
links to — and it is not itself a source of findings; every claim below is
sourced to a specific report section. If this summary and a linked report
ever disagree, the linked report is authoritative and this document is
wrong and should be fixed.

The program is **closed**. Its conclusion:

> **NO RULESET CHANGE CURRENTLY JUSTIFIED — V3 RESEARCH SHOULD CLOSE WITHOUT
> A NEW RULESET.**
> — [V3_RESEARCH_CLOSEOUT.md](V3_RESEARCH_CLOSEOUT.md) Sec 21

Bytefray v3.0 software development proceeds on `bytefray-rules-2`
unchanged. See "Why no Ruleset 3 was created" below and
[V3_PRODUCT_SCOPE.md](V3_PRODUCT_SCOPE.md) for what that means for the
product cycle.

---

## 1. Why the research was undertaken

Bytefray 2.0 shipped `bytefray-rules-2` (the Vulnerable Core mechanic) after
an eleven-experiment alpha program
([V2_0_ALPHA_RESEARCH_SUMMARY.md](V2_0_ALPHA_RESEARCH_SUMMARY.md)) and a
beta/RC qualification cycle. The v2 strategic-ecology characterization
([V2_0_BETA2_PHASE4_STRATEGIC_CHARACTERIZATION.md](V2_0_BETA2_PHASE4_STRATEGIC_CHARACTERIZATION.md))
found a real but bounded limitation: dedicated search offense is the only
effective counter to blind territorial expansion, and that counter-strategy
relationship holds only in a narrow region of the game's parameter space.
The v3 program was chartered to test, with predeclared hypotheses and
gated evidence rather than intuition, whether that limitation could be
resolved — through locality, through payoff rebalancing, or through a new
defensive-scoring mechanism — before any new Ruleset work was undertaken.

## 2. Ruleset-v2 baseline

`bytefray-rules-2` (Vulnerable Core) is unchanged by this program from its
`v2.0.0` shipped state. See [RULES_V2.md](RULES_V2.md) for the full gameplay
contract. The program's own Phase 0 re-verified the shipped ecology exactly
before varying anything — see §3 below.

## 3. Research-phase index

Every report is committed only on the `v3-research-closeout` branch lineage
(and, individually, on each `v3-research-phaseN` branch) — see
[V3_PRODUCT_SCOPE.md](V3_PRODUCT_SCOPE.md)'s compatibility section for why
`v3.0-development` was branched from that lineage rather than from `main`.

| Phase | Question | Verdict | Report |
|---|---|---|---|
| 0 | Can later phases be trusted to measure what they claim? | **PASS** — infrastructure and a reproduced control established | [V3_PHASE0_RESEARCH_BASELINE.md](V3_PHASE0_RESEARCH_BASELINE.md) |
| 1 | Is the residual v2 ecology dependent on arena/action density? | **Structural limitation supported** — density is the one binding variable; the shipped default is already near-optimal | [V3_PHASE1_ARENA_ACTION_DENSITY.md](V3_PHASE1_ARENA_ACTION_DENSITY.md) |
| 2 | Can bounded locality make two strategic axes viable together? | **NOT VALIDATED** — abandon the locality thesis | [V3_PHASE2_LOCALITY_FEASIBILITY.md](V3_PHASE2_LOCALITY_FEASIBILITY.md) |
| 3 | Is decisive offense underpaid relative to its cost? | **PROMISING, narrow follow-up required** — a real interior region exists but collides with defense's floor | [V3_PHASE3_OFFENSE_PAYOFF_CHARACTERIZATION.md](V3_PHASE3_OFFENSE_PAYOFF_CHARACTERIZATION.md) |
| 4 | Can an existing scoring lever restore defense's viability at Phase 3's accepted payoff? | **NOT VALIDATED** — no existing `Weights` field can do it | [V3_PHASE4_DEFENSE_PAYOFF_CHARACTERIZATION.md](V3_PHASE4_DEFENSE_PAYOFF_CHARACTERIZATION.md) (+ [dated addendum](V3_PHASE4_DEFENSE_PAYOFF_CHARACTERIZATION.md#addendum--2026-08-25-post-phase-4)) |
| 5 | (Design proposal only — nothing implemented) | n/a | [V3_PHASE5_DEFENSIVE_EVENT_DESIGN_PROPOSAL.md](V3_PHASE5_DEFENSIVE_EVENT_DESIGN_PROPOSAL.md) |
| 5A | Does "assaulted and survived" qualify as a selective defensive-scoring event? | **NOT QUALIFIED** — falsified at full-corpus scale | [V3_PHASE5A_DEFENSIVE_EVENT_QUALIFICATION.md](V3_PHASE5A_DEFENSIVE_EVENT_QUALIFICATION.md) |
| 6 | Does a cross-tick "attack episode + active reclaim" event qualify instead? | **NOT QUALIFIED** — two blocking gates fail at high action budget | [V3_PHASE6_ACTIVE_DEFENSIVE_INTERVENTION_QUALIFICATION.md](V3_PHASE6_ACTIVE_DEFENSIVE_INTERVENTION_QUALIFICATION.md) |
| 7 | Is Phase 6's high-budget failure an agent-population artifact or a scheduler limitation? | **Mixed, decisively so** — Q7 is mostly scheduler-caused; Q6 is partly an isolated agent bug, partly a broader unaddressed artifact | [V3_PHASE7_HIGH_BUDGET_CONFOUND_ISOLATION.md](V3_PHASE7_HIGH_BUDGET_CONFOUND_ISOLATION.md) |
| Closeout | Does the cumulative evidence justify a new Ruleset? | **NO** | [V3_RESEARCH_CLOSEOUT.md](V3_RESEARCH_CLOSEOUT.md) |

## 4. Major rejected hypotheses

* **Bounded locality** (Phase 2). A fixed-reach movement/addressing mechanic
  was implemented behind an explicitly non-stable Ruleset identity
  (`bytefray-rules-3-alpha1`) and measured against matched controls. It
  produced the opposite of its intended effect: bounding reach forces
  contiguous claiming, which incidentally captures the fixed-size core, so
  blind expansion became the *dominant* core-capture mechanism and the two
  strategic axes merged instead of coexisting.
* **"Assaulted and survived" as a defensive-scoring event** (Phase 5A). A
  same-tick, ownership-history-based event looked selective in a 324-cell
  sample but was falsified at full-corpus (594-cell) scale: expansion
  agents (the search agents' usual prey) triggered it at 15–23%, far above
  the ≤2% a non-defense archetype would need.
* **"Attack episode + active reclaim" as a Ruleset-invariant defensive
  event** (Phase 6, reaffirmed by Phase 7 and the closeout). A cross-tick
  successor event qualified strongly at the shipped default and at low
  action budgets, but failed two blocking robustness gates at
  `instr_per_tick = 32`, for reasons independently confirmed to be a
  mixture of one agent's implementation artifact and a genuine scheduler
  property.
* **Ownership-transition history as a proxy for defensive intent, in any
  form** (the closeout, Sec 4–8). Closed definitively: a fully
  deterministic, attack-blind agent (`core_defender`) perfectly predicts
  its own "defensive" credit; the evidence-driven `reactive_core_defender`
  does not consistently outperform it; and a strictly less intelligent,
  zero-branching turtle probe matches or exceeds both real reference
  defenders at every tested budget.
* **`weights.alive` and `weights.territory` as compensation levers for
  defense** (Phase 4). `weights.alive` is disqualified by a closed-form
  proof (no 2+-survivor comparison can ever depend on it, per Alpha.5's own
  argument). `weights.territory` was given an 11-point sweep and found to
  "fix" defense's win share only by diluting Phase 3's offense correction
  back toward its pre-correction state — the two effects cross within a
  gap narrower than the corpus's own sampling resolution.

## 5. Durable findings

* **Arena size and action budget are one variable, not two**, for
  occupancy, match length, capture rate, and strategic-outcome magnitude —
  a dimensionless configured density `S = (instr_per_tick × ticks) /
  arena_size` explains them, verified across a 4000×-density-span,
  20-condition grid (Phase 1).
* **The shipped default (`arena_size=4096`, `instr_per_tick=8`,
  `ticks=400`) sits at or adjacent to the optimum of the tested parameter
  space** on the verbatim Beta2 §17 ecology rubric — no tested region scores
  better (Phase 1).
* **Offense payoff has a real, if narrow, interior region** (`w_kill`
  roughly 800–1200) where decisive offense becomes simultaneously
  competitive with expansion — but that region is the same region where
  defense's win share falls below its own predeclared floor, so it cannot
  be adopted without a compensating defense mechanism that does not
  currently exist (Phase 3, Phase 4).
* **Defense's deficit is structural, not a tuning gap.** It pays a
  confirmed ~25–26% unconditional action-opportunity tax and generates a
  real, precisely quantifiable denial benefit (worth exactly `w_kill` per
  repelled attack) that is entirely uncredited to the defender's own score
  — the three-term scoring model has an event for "successfully attacked"
  and none for "successfully resisted" (Phase 4).
* **Ownership-transition history cannot distinguish responsive defense
  from a sufficiently frequent, entirely blind own-core rewrite.** Closed
  by three independent, converging checks: a blind-timer replay predicts
  100.0% of `core_defender`'s "defensive" credit; `reactive_core_defender`
  does not consistently outperform that blind timer (the sign of the
  advantage flips by budget); and a strictly-less-capable turtle probe
  matches or exceeds both real defenders at every tested budget (the
  closeout, Sec 4–8).

## 6. Scheduler/action-budget finding

Independent of the defensive-scoring line, the program found a real,
mechanically verified Ruleset-level property: **reaction-opportunity
denial rises from 0.0% to 34.6% purely as absolute `instr_per_tick` rises
along a constant-density diagonal** (2 → 8 → 32 → 128, density held fixed
at `S ≈ 0.781`) — an effect invisible to any density-normalized measure
(the closeout, Sec 9–12, following Phase 6/7's own high-budget diagnosis).
The mechanism has an exact boundary: a perfectly informed attacker can
capture an earlier-scheduled, non-reacting victim within one action block
once `instr_per_tick >= CORE_SIZE` (= 8), and cannot below it (the
closeout, Sec 13). The shipped default sits exactly at that boundary, which
is consistent with, and explains, its own low (1.9%) but non-zero denial
rate.

**This is recorded as research methodology, not a gameplay-rule finding**:
future strategic-mechanics research must disclose and justify any
`instr_per_tick` materially above `CORE_SIZE`, independent of and in
addition to justifying arena/action density. No default or Ruleset constant
was changed by this finding.

## 7. Open but unqualified future ideas

None of the following is a v3.0 product commitment. Each requires its own
hypothesis-driven qualification before implementation — see
[FUTURE_PLANS.md](FUTURE_PLANS.md)'s "Future Ruleset research candidates"
section for the full, deliberately non-committal catalogue, and the
"Ruleset-reopen gate" in [V3_PRODUCT_SCOPE.md](V3_PRODUCT_SCOPE.md) for the
process a reopened question would need to follow.

* Whether the fixed-size, fixed-address core model itself (rather than
  entrant omnipresence) is the deeper source of Ruleset v2's single-axis
  ecology — implicated independently by both Phase 1 (§9.1's scale effect)
  and Phase 2 (contiguous-sweep incidental capture), without either phase
  setting out to find it (Phase 2, Sec 24).
* Whether execution-trace-level telemetry (recording *why* an action was
  taken, not merely *that* an ownership transition occurred) could
  distinguish responsive defense where ownership history provably cannot —
  named as the most promising remaining direction if defense's deficit is
  ever revisited, explicitly unevaluated and unimplemented, requiring its
  own anti-gaming analysis before any further defensive-scoring experiment
  (the closeout, Sec 8, Sec 25).
* Whether a scheduler/quota-semantics change (e.g. a guaranteed reaction
  window) would meaningfully change the ecology — genuinely unmodeled by
  any phase in this program; concentrated at `instr_per_tick` values well
  above the shipped default and never shown to degrade the shipped ecology
  (the closeout, Sec 18–20).
* Relative (locality-style) addressing's translation-invariance benefit,
  decoupled from bounded reach itself — Phase 2 measured this as a real,
  clean secondary result (placement sensitivity falls from double digits to
  near-zero) attributable to relative addressing, not to bounding reach,
  and it survives the locality thesis's own rejection (Phase 2, Sec 19,
  Sec 24).

## 8. Why no Ruleset 3 was created

Every semantic-change candidate actually investigated across Phases 0–7 and
the closeout either failed its own predeclared qualification standard, was
structurally disqualified by direct proof, or — in the one case with a real
measured effect (scheduler topology) — was shown to be concentrated well
outside the shipped operating condition and never evidenced to degrade the
shipped ecology. The closeout's own decision matrix (Sec 20) scores every
candidate change against evidence-for, evidence-against, compatibility
impact, and risk; "no change (status quo)" is the only candidate it
recommends adopting.

`bytefray-rules-2` and `bytefray-rules-1` are unchanged by every phase of
this program. One new, explicitly non-stable, non-product-facing Ruleset
identity was created and used entirely within the research: `bytefray-
rules-3-alpha1` (Phase 2's locality mechanic). It is not `bytefray-rules-3`,
was never registered on any product CLI's `--ruleset` choices, and this
program's conclusion is that no stable Ruleset 3 is currently justified.

## 9. Links to full reports

All ten reports are linked inline above (§3) and throughout this document.
There is no separate reading order beyond the phase sequence in §3 — each
report states its own predecessors' relevant findings before extending
them.

## 10. Relationship to v3.0 product development

Bytefray v3.0 software development proceeds on the existing, unchanged
`bytefray-rules-2` foundation. See
[V3_PRODUCT_SCOPE.md](V3_PRODUCT_SCOPE.md) for the v3.0 product thesis, its
compatibility freeze, and the explicit gate under which any of §7's open
ideas could someday become a new research program — not an implementation
task entered directly from this summary.
