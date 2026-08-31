# Bytefray Ruleset v2 — pre-beta candidate

**Status: candidate, not a contract.** This is the pre-beta definition of
Ruleset v2 derived from the v2.0 alpha.1–alpha.11 evidence. It is *not*
`docs/RULES.md` (which remains the frozen Ruleset v1 reference and is
unchanged), and it does *not* claim the permanent `bytefray-rules-2`
identity. The semantics below currently execute under the experimental
identity **`bytefray-rules-2-alpha11`**.

Evidence: `docs/V2_0_ALPHA11_RULESET_V2_CANDIDATE_RESOLUTION.md` and the
alpha.1–alpha.10 documents it cites. Where this document says "unchanged",
it means byte-identical to Ruleset v1 as documented in `docs/RULES.md`.

---

## 1. Scope

Ruleset v2 is a **Python-runtime** gameplay change. The native VM path is
unchanged and continues to run `bytefray-rules-1`; the VM already has its own
native code-vulnerability mechanic, and extending core semantics to it is a
separate, later question, not part of this candidate.

Everything not stated below is inherited unchanged from Ruleset v1.

## 2. Arena

**Unchanged from v1.** A circular, mutable byte array of `Config.arena_size`
(default 4096), addressed by a single flat `pos % arena_size` wrap for every
access. Ownership is a parallel per-byte "most recent writer" value,
engine-internal and not readable by agent code. `READ` never changes
ownership; `WRITE` assigns the byte to the writer and keeps only the low
eight bits. Any entrant may read or write **any** address; there is no
access control.

**Placement.** Each entrant has a start address (`MatchEntrant.start`). Under
v1 this is configuration, not Ruleset identity, and that remains true. What
changes is that it is now *load-bearing*: it anchors the entrant's core (§3).
Distinct per-entrant start addresses are required for the mechanic to be
meaningful; the harness support for this already exists
(`agent_test.test_agent`'s `agent_start`/`opponent_start`). No random-start
feature is proposed, and none exists.

## 3. Vulnerable Core

**Size and anchor.** An entrant's core is the fixed window of `CORE_SIZE = 8`
contiguous bytes beginning at `entrant.start % arena_size`, using the
ordinary arena wrap. It is fixed at construction and never moves — unlike
`pc`, which the entrant's own actions can relocate. It is deliberately not
derived from program size, write count, or any entrant-controlled property.

**Ownership seeding.** At match initialisation, before any `reset()` or
`act()` call, the engine establishes the entrant as sole owner of all eight
of its core cells, through an ordinary write routed like any other. This is
the Python-runtime equivalent of the VM's spawn-time `load_code` ownership
and appears in tick-zero replay diffs exactly as that does.

**Observability (new in alpha.11 — the resolution this candidate exists to
carry).**

> Every cell of a living entrant's core that is currently owned by that
> entrant holds a non-zero byte at every tick boundary.

Realised as two clauses:

1. **Beacon seeding.** The initialisation write above uses the public
   constant `CORE_BEACON_BYTE = 0xCE` rather than `0`.
2. **Non-blank maintenance.** At the end of every tick, after capture
   resolution and before scoring, any cell of a *living* entrant's core that
   **that entrant still owns** and whose content is `0x00` is rewritten to
   `CORE_BEACON_BYTE`, attributed to that same owner.

Normative consequences, all of which are load-bearing:

- The footprint exists **independently of whether the owner ever defends,
  refreshes, patrols, or writes to its own core.** It is a Ruleset property,
  not a consequence of strategy.
- Maintenance touches **only cells the owner already owns**. It never
  reverts another entrant's write, never restores ownership, never changes
  ownership counts or territory score, and cannot make a core
  indestructible.
- Maintenance repairs **only `0x00`**. An entrant's own non-zero content in
  its own core is never overwritten, so read-then-compare defensive logic is
  unaffected.
- A dead entrant's core is not maintained.
- `CORE_BEACON_BYTE` is **public Ruleset knowledge**, on the same footing as
  `CORE_SIZE`. It is not keyed to any agent, and no agent needs to recognise
  it: any content-based search keying on "non-zero and not mine" observes it
  for free.
- Discovery still costs ordinary `READ` actions against addresses the
  searcher chose itself. No coordinates, ownership, or opponent identity are
  ever disclosed.

**Damage, capture, mortality, attribution.** Unchanged from alpha.1. An
entrant is **core-captured** when it owns zero cells of its own core —
deliberately "owns zero", not "one opponent owns all of it", so the rule
stays well defined for any entrant count. Checked once per tick, after all of
that tick's actions and before scoring/termination, so a captured entrant
receives no alive/territory score for the tick it dies on and gets no extra
turn. The entrant's `termination_reason` is `"core_captured"`. Kill credit
goes to whichever entrant's `WRITE` took the final owner-held core cell that
tick, when that is unambiguously determinable from the tick's write order;
otherwise the death is unattributed, exactly like an ordinary Python
halt/forfeit.

This is the **only** Python mortality attribution in the candidate. Ordinary
`HALT` and forfeit deaths remain unattributed, as in v1.

**Overlapping cores.** Not specially handled and not prohibited: later-seeded
entrants overwrite earlier ones, and an entrant left owning zero core cells at
its first check dies unattributed. Evaluation is responsible for choosing
non-overlapping placements.

## 4. Territory

**Unchanged from v1, and deliberately so.** Ownership is permanent until
overwritten; there is no decay, no expiry, no maintenance cost, and no
scoring-age term. Territory contributes
`floor(owned_cells / territory_bucket) * territory` points cumulatively each
tick.

This is an explicit decision, not an omission. Alpha.11's Resolution B
(deterministic territory maintenance) was a *contingency* gated on
Resolution A being mechanically sound but insufficient. Resolution A returned
A-PASS, so the gate did not open and no maintenance mechanic was designed,
implemented, or evaluated. Adding one now would be stacking a second
structural mechanic on a working one without evidence that it is needed.

## 5. Scheduling

**Unchanged from v1.** Sequential and ordered by spawn/request order. For
every tick, each living entrant receives up to `Config.instr_per_tick`
`act()` callbacks before the next entrant begins; an entrant that dies
mid-quota stops immediately and is skipped thereafter. Execution is not
simultaneous, so an earlier entrant can alter what a later entrant observes
before the later entrant acts at all in that tick.

## 6. Capture-check timing — explicit candidate decision

**Decision: retain the existing once-per-tick, post-action-block capture
resolution. Accepted as strategy, not deferred as unknown.**

This is stated explicitly rather than inherited silently, because alpha.9 and
alpha.10 both established that scheduler order materially affects
offense-vs-defense capture races (40% of matched offense-vs-defense cells in
alpha.10). The reasoning:

- The effect is **real but concentrated**, never global. Alpha.11 re-measured
  it at 35% within offense-vs-defense — slightly *lower* than alpha.10's 40%
  — and confirmed by direct test that it is not systematic: across the newly
  contested offense-vs-expansion class, being scheduled first is worth about
  10 percentage points (62.5% vs 52.5%), while the deciding variable is
  search outcome (25%–75% across seeds).
- Per-cell "flip rates" rose under alpha.11 (17% → 35% globally in 1v1) for a
  benign reason: cells that used to be foregone conclusions became genuine
  contests, and contested cells are sensitive to everything. Sensitivity
  concentrated in close matchups is the signature of a live ecology, not of a
  broken tiebreak.
- Being able to act last in a decisive tick is a legitimate positional
  advantage of the same kind v1 already documents for first-mover order.
- Changing capture-check timing in synthesis, without an experiment
  specifically designed to test the alternative, is precisely what the
  governing task forbids.

**Obligation this creates.** Because order is a competitive factor, any
Ruleset-v2 evaluation **must balance scheduler order** rather than sample it
once (see §12). This is a methodology requirement, not an open rules
question.

## 7. Winner eligibility

**Unchanged from v1/alpha.4.1**, via the single authoritative
`battle_engine.results.resolve_winner`:

- if exactly one entrant remains alive, it wins regardless of score;
- otherwise under `win_mode: "survival"` there is no winner;
- otherwise (`"score"` / `"score_fallback"`) the unique highest score wins;
  an exact tie in top score produces no winner;
- **dead entrants cannot win while any entrant survives**;
- zero survivors falls back to the score comparison among all entrants;
- entrant IDs break sort order for deterministic reporting but never break an
  equal score into a win.

Used unmodified in all 1,316 alpha.11 matches with no unexpected behaviour.

## 8. Scoring

**Unchanged from v1.** Default weights (alive `1.0`/tick, attributed kill
`5.0`, territory `1.0` per 64-cell bucket) and the three formulas are exactly
as `docs/RULES.md` documents.

Stated plainly, because it would be easy to over-claim: **alpha.3 and
alpha.5 did not validate any alternative scoring.** They established the
opposite — that retuning existing territory/alive/kill weights does not solve
the structural ecology problem — which is why alpha.11 resolved it with an
information rule instead and did not touch weights. The one change relative
to v1 is that the kill formula's precondition can now actually be met in a
Python match, via core capture (§3).

Observed in alpha.11's corpus: survival eligibility decides matches with a
capture; territory decides essentially everything else; kills never
independently determine a winner beyond the survivor override.

## 9. Seed

**Unchanged from v1 in mechanism, elevated in importance.** `Config.seed` is
the deterministic root from which each entrant's independent RNG stream is
derived (`derive_agent_seed`, an Agent API v1 contract detail). A given
(seed, placement, order, agents) tuple reproduces exactly.

Agents may consume `context.rng`. The reference offense benchmark
(`core_tracker`) draws its scan anchor from it, which makes the seed a
**first-class evaluation condition**, not an incidental parameter: alpha.11
measured `core_tracker`'s win rate against expansion varying from 25% to 75%
across five seeds at otherwise identical conditions. A single-seed
methodology is insufficient wherever an RNG-consuming agent is present.

The particular seed *value* used for one match remains configuration, not
Ruleset identity.

## 10. Multi-entrant behaviour

**Disposition: supported engine capability, exercised and characterised, but
not a required product workflow in this candidate.**

N-entrant native execution is architecturally real (alpha.4/4.1), produces
genuine third-party strategic interactions, and has now run 900 further
3-entrant matches in alpha.11 with zero infrastructure failures and correct
survivor semantics throughout. Every rule in this document is written to be
well-defined for any entrant count (notably §3's "owns zero" capture
condition).

What is *not* claimed: no product surface (CLI match construction,
evaluation, tournament, Designer) exposes 3+ entrant play as a supported
workflow today, and this candidate does not require one. Whether beta should
productise it is a beta-planning decision.

## 11. Agent API — candidate decision

**Agent API v1 remains the supported Python agent interface for the
Ruleset-v2 beta.** No Agent API v2, and no additive field, is proposed.

Evidence, all within v1's existing `READ`/`WRITE`/`NOP`/`HALT` vocabulary,
`Observation`, `MatchContext`, and `context.rng`:

- deliberate offense implemented in v1 (`core_seeker`, `core_tracker`);
- reactive, evidence-driven defense implemented in v1
  (`reactive_core_defender`);
- blind periodic defense implemented in v1 (`core_defender`);
- placement-agnostic coarse-to-fine search implemented in v1
  (`core_tracker`, alpha.8);
- alpha.11's entire resolution required **no agent change at all** — the
  reference attacker's improvement came from the Ruleset, with its source
  byte-for-byte fixed;
- no privileged extension was required at any point across eleven alphas.

A major product version number is not a reason to bump an API version. The
one genuinely additive candidate previously identified — an explicit
`MatchContext.spawn_address`, replacing the current reliance on
`Observation.pc`'s initial value — remains a nice-to-have for a future bump
that is justified on other grounds, not a reason to bump.

`Observation` and `MatchContext` continue to expose **nothing** about any
other entrant: no identity, no position, no core address, no ownership, no
score. This is pinned by test and is a precondition of §3's observability
design being an information rule rather than a disclosure.

## 12. Evaluation methodology requirements (for beta, not implemented here)

Derived from alpha.1–alpha.11 evidence. None of this is built yet; it is the
specification the beta evaluation work will need.

1. **Entrant orientation/order balancing.** Both orientations, always.
   Scheduler order is an accepted competitive factor (§6), so it must be
   balanced rather than sampled.
2. **Scheduler-order permutations for 3+ entrants.** All permutations, or a
   documented balanced subset — alpha.11 measured 84% permutation
   sensitivity in contested trios.
3. **Placement diversity.** At minimum a control, a historically-hard, and a
   held-out placement, with cores non-overlapping. Placement matters less
   than it did (alpha.11's captures were uniform across conditions) but is
   not eliminated.
4. **Seed diversity wherever RNG matters.** A genuine seed set, never seed 1
   alone, for any cell containing an RNG-consuming agent (§9).
5. **No pseudo-replication.** Cells with no RNG-consuming agent are exactly
   reproducible; running them repeatedly is not evidence. Report the
   distinction.
6. **Rules-identity comparability.** Never align or compare cells across
   differing Ruleset identities. The existing `rules_id`-keyed refusal in
   `evaluation_history` is correct and must be preserved.
7. **Capture and core metrics as first-class outputs**: capture rate, capture
   tick, killer attribution, minimum core ownership, first foreign core read,
   first covering assault. Win rate alone hides the mechanism — alpha.11's
   entire finding is invisible without the detection-versus-capture split.
8. **Behaviour/action-economics reporting**: expansion / information /
   own-core / opponent-core action fractions per entrant. Alpha.11's claim
   that the change is informational rather than economic rests on these being
   unchanged across Rulesets.
9. **Multi-entrant methodology** if 3+ entrant play is productised: seat
   assignment must be separated from scheduling order, as alpha.10/11's
   harnesses already do.

## 13. Ruleset identity and promotion strategy

**Current candidate identity: `bytefray-rules-2-alpha11`** (experimental).

- `bytefray-rules-1` is frozen and remains executable and authoritative for
  every historical artifact.
- `bytefray-rules-2-alpha1` remains executable with byte-identical
  historical semantics and is **not** superseded, aliased, or reinterpreted.
- `bytefray-rules-2` is **not** claimed and must not be minted yet. The
  resolver stays a finite, fail-closed table; an unrecognised identity —
  including a plausible-looking `"bytefray-rules-2"` — is rejected, never run
  as something else.

**Conditions that must be met before promoting these semantics to a beta
Ruleset identity:**

1. Beta planning explicitly accepts the semantics in §§2–10 as intended to
   freeze, rather than as a hypothesis still under test.
2. A decision is made on whether `CORE_SIZE` and `CORE_BEACON_BYTE` stay
   fixed module constants or become Ruleset-versioned parameters.
3. The evaluation methodology in §12 exists in some executable form, so the
   frozen Ruleset can be evaluated the way its own evidence says it must be.
4. A decision is made on whether 3+ entrant play is a required product
   workflow (§10) or remains engine capability.
5. VM-path disposition is decided — either explicitly out of scope for
   Ruleset v2 (the current candidate position) or brought in with its own
   evidence.
6. Whatever identity is claimed is claimed once, with `rules.py`'s alias
   table left free of speculative entries, and with canonical match identity
   demonstrably distinct from every experimental identity that preceded it.

## 14. Beta readiness

**GO** for beginning the separate v2 beta-planning phase, on the evidence
recorded in `docs/V2_0_ALPHA11_RULESET_V2_CANDIDATE_RESOLUTION.md`: expansion
dominance is materially resolved without a new universal strategy replacing
it; core observability is coherent and minimal; offense, defense and
expansion all retain real and distinct action costs; scheduler sensitivity is
understood and explicitly accepted; artifact identity is correct; and
Ruleset v1 and every historical alpha Ruleset remain preserved and
executable.

This document supplies evidence and a candidate definition only. It does not
modify `docs/ROADMAP.md`, `docs/FUTURE_PLANS.md`, the changelog, or the
project version.
