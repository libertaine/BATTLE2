# Bytefray v2.0.0-beta2 Phase 1 — Ruleset-v2 1v1 Evaluation Methodology

**Status: implementation complete on `v2.0-beta2-development`, not yet
released.** This document is Phase 1's design record and qualification
report. It converts the evaluation lessons from the v2.0 alpha research
series (alpha.1–alpha.11) into a supported, reproducible,
compatibility-honest Ruleset-v2 1v1 evaluation methodology inside the
normal Bytefray evaluation stack (`battle_engine.agent_evaluation`), while
leaving Ruleset-v1 evaluation and Beta1 gameplay semantics completely
unchanged.

Governing rule this phase enforces throughout:

> A Bytefray v2 evaluation result is meaningful only in the context of the
> exact deterministic conditions it sampled. Ruleset, order, placement,
> seed, and ticks are experimental conditions — not incidental
> implementation details.

Compatibility rule:

> Ruleset-v1 evaluation remains what it was. Ruleset-v2 gains a richer
> methodology without silently rewriting the meaning of Bytefray's
> historical evaluation artifacts.

---

## 1. Starting repository state

- `main` HEAD at task start: `2076576` ("docs: mark v2.0.0-beta1 published").
- `v2.0.0-beta1` tag (annotated) dereferences to commit `79f61f4`
  ("chore: prepare v2.0.0-beta1 release"), confirmed an ancestor of `main`
  HEAD.
- `origin/v2.0-beta1-development` = `79f61f4` (published beta-development
  branch, matches the tag target exactly).
- `v2.0-development` (local, historical alpha branch) = `ad67a0f` — left
  untouched throughout this phase.
- `origin/v2.0-development` = `151866c` — the unrelated remote branch named
  in the governing prompt; intentionally left outside the v2 lineage, not
  reconciled.
- Working tree was clean before any mutation.

## 2. Branch creation

`v2.0-beta2-development` was created from `main` HEAD (`2076576`) exactly,
verified as a direct descendant of the `v2.0.0-beta1` tag
(`git merge-base --is-ancestor v2.0.0-beta1 HEAD` succeeded). Lineage:

```text
v2.0.0-beta1 tag (79f61f4)
    |
    +-- post-release docs on main (2076576)
            |
            +-- v2.0-beta2-development
```

The branch was kept local for this phase (not pushed), per the governing
prompt's default. `main`, `v2.0-beta1-development`, the Beta1 tag, the
historical alpha branch, and `origin/v2.0-development`'s `151866c` are all
confirmed untouched at the end of this phase (see §31).

## 3. Starting regression baseline (re-measured, not assumed)

Beta1's final qualified baseline (1731 passed / 6 skipped / 0 failed) was
re-measured fresh on `v2.0-beta2-development`, before any Phase 1
implementation:

- `pytest`: **1737 collected, 1731 passed, 6 skipped, 0 failed, 0 errors**
  — identical counts to the recorded Beta1 baseline. The post-release
  documentation commits on `main` introduced no test drift.
- Ruff (`engine client`): all checks passed.
- mypy `engine/src/battle_engine`: no issues in 71 source files.
- mypy `client/src/battle_client`: no issues in 12 source files.
- `git diff --check`: clean.

This is the only valid Phase 1 regression baseline; nothing here was
carried over from Beta1's own qualification report without
re-verification.

---

## 4. Reconstructing the current (v1) evaluation contract

Before any design work, the existing `bytefray.evaluation` contract
(`battle_engine.agent_evaluation`, `evaluation_history`,
`evaluation_presets`, `evaluation_analysis`, `evaluation_behavior`) was
read in full, not summarized from memory. Answers to the governing
prompt's Phase 1A questions:

1. **Orientation representation.** Two independent axes already exist,
   deliberately decoupled: `subject_role ∈ {candidate, baseline}` (which
   agent is *being evaluated*) and `orientation ∈ {candidate_first,
   opponent_first}` (which physical slot acts first for one cell),
   resolved via `physical_slots_for_orientation()`. `EvaluationCell` stores
   both.
2. **Does orientation imply scheduler order?** Yes, already. `orientation`
   *is* today's scheduler-order axis for 1v1 — flipping it swaps which
   agent occupies the always-first-acting slot (`TESTED_AGENT_SLOT`/
   `OPPONENT_SLOT`), with every stored field still expressed from the
   subject/opponent role perspective. This was added in v0.9 Phase 6 (Phase
   5 spec Sec H/I) specifically because a candidate-first-only default was
   found to hide a first-mover advantage.
3. **How are starts assigned?** `agent_test.test_agent`/`_test_agent`
   already accept `agent_start`/`opponent_start` (v2.0.0-alpha.1's additive
   selectors), but `EvaluationService._execute_cell` never passed them
   before this phase — every historical evaluation cell places both
   entrants at `start=0`.
4. **Is arena alignment fixed?** Yes: `EVALUATION_ARENA_ALIGNMENT_MODE =
   "fixed"` was a module constant with exactly one possible value, already
   threaded through `evaluation_id`/`condition_fingerprint` identity (v0.9
   Phase 6) as an extension point for a future methodology that was never
   built until now.
5. **How is seed selected?** `EvaluationRequest.seeds: tuple[int, ...]`,
   explicit and unbounded, via `--seeds`/`--seed-range`, defaulting to a
   single seed (`Config().seed`) when nothing is specified.
6. **How many seeds are supported?** Unbounded — always has been.
7. **Is seed already part of schedule identity?** Yes — `seeds` is
   hashed directly into `evaluation_id`'s payload, and each cell's `seed`
   is part of `schedule_id`/`condition_fingerprint`.
8. **Is Ruleset identity part of evaluation identity?** Yes, structurally —
   `EVALUATION_RULES_COMPATIBILITY_ID` (a derived alias of
   `battle_engine.rules.BYTEFRAY_RULESET_ID`) was already a first-class
   sibling key in the hash payload — but its *value* was a hardcoded module
   constant, always `"bytefray-rules-1"`, because `agents evaluate` had no
   `--ruleset` flag at all before this phase.
9. **Are start positions part of schedule/evaluation identity?** Not before
   this phase — no start-address concept existed in evaluation identity at
   all (see §11 for the deeper `canonical_match_id` gap this phase closes).
10. **How does resume recognize a cell?** By `schedule_id` lookup into the
    prior checkpoint's `cells[]`, plus an independent re-derivation of the
    expected `match_id` (`_expected_cell_match_id`) to catch source/content
    drift on a completed cell.
11. **How does comparison align cells?** `evaluation_history.comparison.
    _condition_key()` — a strict tuple key (opponent identity, seed,
    effective-conditions fingerprint, normalized rules-compatibility id,
    arena-alignment id, condition-occurrence index, orientation) that must
    match exactly, with any `UNKNOWN` component refusing alignment rather
    than guessing.
12. **What does a preset currently control?** `candidate`, `baseline`,
    `opponents`, `seeds`/`seed_range`, `ticks`, `orientation` — a purely
    input-construction convenience, never part of `evaluation_id`'s hash
    (see `evaluation_presets.py`'s own module docstring).
13. **What does evaluation history persist?** The full `bytefray.
    evaluation` artifact (schema v4 at the time this phase started):
    evaluation-level identity/methodology fields, per-cell outcome/score/
    territory/provenance, execution contexts, agent revisions, recomputed
    aggregates/comparison — see `agent_evaluation.EvaluationService.
    _write_state`.
14. **What assumptions require exactly candidate/opponent?** `EvaluationRequest.
    candidate_id`/`baseline_id` (singular strings, at most two subjects),
    `EvaluationCell.subject_id`/`opponent_id` (singular opponent per cell),
    `physical_slots_for_orientation()` (returns exactly a 2-tuple),
    `agent_test.TESTED_AGENT_SLOT`/`OPPONENT_SLOT` (module-wide two-slot
    constants), `_test_agent`'s literal 2-tuple `MatchRequest.entrants`,
    and `compare_candidate_baseline`'s exactly-one-candidate-vs-one-baseline
    pairing.

This reconstruction is the compatibility wall Phase 1 does not cross: v1
was never redesigned to make room for v2's richer methodology.

## 5. Alpha evidence motivating the v2 methodology

Reconstructed from the original alpha reports (alpha.3, alpha.5, alpha.7,
alpha.8, alpha.9, alpha.10, alpha.11), not only their summary:

- **Scheduler order (alpha.9 §16, escalated in alpha.10/alpha.11).**
  Reversing only the entrant list, with placement/agents/seed held fixed,
  flipped survival outright in 4/16 (25%) matched offense-vs-defense cells
  in alpha.9 — "the single most important finding in this alpha." The
  mechanism: `apply_core_capture` checks ownership once per tick, *after*
  every entrant's action block that tick, so whichever entrant acts last in
  the decisive tick determines what that tick's capture check actually
  sees. Alpha.10 measured this at 40% within offense-vs-defense at 1v1
  scale and 35.9% globally at 3-way. Alpha.11's fixed candidate ruleset
  measured a 35% flip rate for offense-vs-defense (order-sensitivity
  persists, tracks genuine contestedness rather than brokenness) and 84%
  permutation sensitivity in contested three-entrant trios.
- **Placement (alpha.7, corroborated by alpha.8/alpha.10).** Two
  deliberately opposite fixtures built around Core Seeker's fixed scan
  geometry — COLD (nearest-to-historical, geometrically unreachable) and
  HOT (an early, high-tolerance opportunity) — produced 0/9 captures at
  COLD and 4/9 at HOT, "a large, clean, placement-attributable effect."
  This proved the long-standing "seat-B vulnerability" pattern in earlier
  alphas was a placement-convention artifact, not an intrinsic property of
  Vulnerable Core. Alpha.8's placement-agnostic Core Tracker (RNG-anchored
  scan start, not fixed) achieved a real capture *inside COLD*, and
  alpha.10 found HOT produced the *fewest* captures against an RNG-seeded
  attacker — "the opposite of its role in every prior alpha." Both results
  are direct, disclosed evidence that COLD/HOT are artifacts of one
  superseded attacker's geometry, not a property of placement itself — this
  phase deliberately does not reuse those coordinates or names as permanent
  methodology (Phase 1C).
- **Seed (alpha.8/alpha.9/alpha.10/alpha.11).** Core Tracker draws its scan
  anchor from `context.rng`, making seed a genuine behavioral variable.
  Alpha.9's single-seed matched comparison (blind vs. reactive Core
  Defender) found *zero* win/loss difference (16/16 identical); alpha.10's
  5-seed comparison of the same matchup found a real, one-directional
  advantage for reactive defense (6 cells favor reactive, 0 favor blind,
  across 40 matched cells) — "a single-seed evaluation methodology is
  demonstrably insufficient." Alpha.11 widened this: Core Tracker's win
  rate against expansion ranged 0.250–0.750 across seeds 1–5 on matched
  cells, meaning single-seed insufficiency now applies to two matchup
  classes, not one.
- **Capture distinct from win/loss (alpha.3, formalized alpha.9/alpha.11).**
  In every alpha.3 sampled capture match, the captured entrant was still
  numerically *ahead* on score at the moment of capture (e.g. Core Defender
  940 vs. Core Seeker 919) — invisible from win/loss alone, since
  `resolve_winner`'s survival-first rule overrides score once only one
  entrant survives. Alpha.9 formalizes "report robustness metrics
  separately, never as one composite score" as design doctrine specifically
  because aggregate survival can be identical (87.5% both) while
  capture-adjacent metrics (detection latency, opportunity-cost shape)
  reveal real, disclosed differences win/loss hides.

## 6. Ruleset selection

`agents evaluate` gains `--ruleset {bytefray-rules-1,bytefray-rules-2}`,
`default=None`, mirroring `agent_test`'s existing `--ruleset` precedent
exactly (same choice set, same help-text convention).

Resolution (`resolve_evaluation_ruleset_id`):

- **Omitted** (`None`) → resolves to `EVALUATION_RULES_COMPATIBILITY_ID`
  (`"bytefray-rules-1"`) — byte-identical to every evaluation ever run.
- **Explicit `bytefray-rules-1`** → resolves to the exact same value as
  omitted. Both are "v1 methodology," one and the same resolved
  configuration (Phase 1H).
- **Explicit `bytefray-rules-2`** → resolves to
  `battle_engine.ruleset_policy.BYTEFRAY_RULESET_V2_ID`
  (`"bytefray-rules-2"`), activating the v2 methodology below.
- Any other value (including every historical alpha identity, e.g.
  `bytefray-rules-2-alpha11`) is rejected by `EvaluationService._validate`
  with `EvaluationConfigurationError` before any cell is planned —
  product-facing evaluation never advertises an alpha Ruleset identity.

Methodology is tied 1:1 to the resolved Ruleset identity: v1 stays exactly
what it was; only `bytefray-rules-2` gets balanced placement, the standard
seed default, and capture/core evidence.

**Runtime boundary.** Evaluation has *always* restricted every entrant to
Python agents unconditionally (`_resolve_python_agent`), independent of
Ruleset — this predates Phase 1 entirely. That existing restriction already
satisfies "a VM entrant under v2 fails via the authoritative Beta1 runtime
compatibility boundary": there is no code path by which a VM entrant can
even reach evaluation, v1 or v2, so nothing new needed to be built or
duplicated here.

## 7. Orientation vs. scheduler order (Phase 1J)

The existing `orientation`/`subject_role` split already keeps "which agent
is being evaluated" separate from "who acts first." This phase preserves
that split unchanged and gives it explicit v2 disclosure (`scheduler
orders: balanced` in CLI output) rather than inventing new public
terminology. What Phase 1 *adds* is a physically independent third axis —
placement — that must not be conflated with either: `EvaluationService.
_execute_cell` resolves `agent_start`/`opponent_start` from the cell's
`subject_start`/`opponent_start` through the *same* `orientation`-aware
slot mapping already used for `test_agent_id`/`test_opponent_id`, so the
subject always starts at `subject_start` regardless of which physical slot
executes it.

## 8. Placement methodology (Phase 1C)

`agent_evaluation.EvaluationPlacement(placement_id, subject_start,
opponent_start)` — a deliberately 1v1-scoped pair, named to mirror
`EvaluationCell.subject_id`/`opponent_id` (never `candidate_start`, since a
baseline cell's "subject" is the baseline).

`standard_placements(arena_size=None)` derives three conditions
mechanically as fractions of `Config().arena_size` (default 4096) — never
hand-picked coordinates, never dependent on any specific opponent's scan
geometry:

| id | subject_start | opponent_start | rationale |
| --- | --- | --- | --- |
| `opposed` | `0` | `arena_size // 2` | maximal separation, phase 0 — the control condition |
| `quarter` | `0` | `arena_size // 4` | closer, non-opposed separation — proves a result isn't an artifact of exact-half separation |
| `opposed-shifted` | `arena_size // 4` | `(arena_size // 4 + arena_size // 2) % arena_size` | same half-arena gap as `opposed`, phase-shifted a quarter turn — proves an `opposed` result isn't an artifact of starting at address 0 |

Non-overlap is structural: every gap here is a quarter or half of
`arena_size`, vastly larger than `CORE_SIZE` (8) — verified directly by
`test_standard_placements_cores_never_overlap` via `python_runtime.
core_addresses`. This is deliberately **not** a reuse of alpha.7's
COLD/HOT coordinates or names — those were calibrated to one superseded
fixed-scan attacker (Core Seeker) and are documented in §5 as evidence the
program should generalize away from, not permanent methodology.

## 9. Seed methodology (Phase 1D)

`STANDARD_V2_SEEDS = (1, 2, 3, 4, 5)` — matches alpha.10/alpha.11's own
5-seed convention directly. Used as the v2 CLI default *only* when neither
an explicit `--seeds`/`--seed-range` nor a preset-supplied seed set is
given; an explicit selection always overrides it, exactly like every other
resolution tier `main()` already uses. Seeds were already fully
identity-affecting and resume-independent-per-cell before this phase — no
mechanism changed, only the default.

## 10. Standard cell matrix and default cost (Phase 1E/1W/1X)

For one opponent, standard v2 methodology:

```text
cells/opponent = seeds(5) × placements(3) × orientations(2) = 30
```

Measured real wall-clock cost (see §25 for the full characterization run):
Claimer vs. Core Defender, 30 cells, ticks=200 — **3.26s** total, serial
(`--workers` default 1). Core Tracker vs. two opponents (60 cells) with
`--workers 4` — **2.58s** total. Both are well within "ordinary local use
remains reasonable" — no dimension was dropped to hit this; the naive full
product (5×3×2=30/opponent) was already practical, so no balanced-subset
reduction was needed (Phase 1E's "if excessive, identify a coherent
balanced subset" branch was not triggered).

## 11. Condition identity (Phase 1F) — the critical compatibility work

Every gameplay-relevant v2 dimension now enters canonical identity, with
every change designed so a v1-methodology request's hash payload is
**byte-identical** to what this module computed before Phase 1 existed:

- **`evaluation_id`** (`EvaluationService._evaluation_id`): the
  `"rules_compatibility_id"` and `"arena_alignment_mode"` keys, previously
  fixed module constants, now resolve dynamically from the request
  (`request.resolved_rules_compatibility_id`,
  `resolved_arena_alignment_mode`). For v1 both resolve to the exact same
  constant values as before — the payload is unchanged. A new
  `"placements"` key (the actual resolved placement list, not just a mode
  label) is added **only** when the request is v2 — its absence for v1
  keeps that payload's key set byte-identical to every `evaluation_id` ever
  computed.
- **`schedule_id`** (`build_matrix`): gained `"placement_id"` in its hash
  payload, mirroring `orientation`'s own precedent exactly (defensive
  redundancy on top of the ordinal counter, so two cells differing only by
  placement are guaranteed distinct even if ordinal derivation ever
  changes). For v1, every cell's `placement_id` is the constant `"fixed"`,
  so this is a no-op on v1's actual cell count/order/identity shape — only
  ever exercised under v2.
- **`condition_fingerprint`** (`build_matrix`): gains a `"placement"` sub-key
  (id + both starts) **only** when placement is not `None` (v2) — same
  "conditionally add, never for v1" discipline.
- **`match_id`** (`match_service.canonical_match_id`) — a genuine identity
  *gap* this phase closes: a Python entrant's `start` address was never
  part of `canonical_match_id`'s metadata (unlike the `"vm"` branch, which
  already included `"entry"` unconditionally). Two Python matches differing
  only by start address silently collided on `match_id` before this fix.
  Fixed by adding `"start": entrant.start` to the Python metadata dict
  **only when `entrant.start != 0`**, so this key's absence at `start=0`
  keeps every historical **start=0** Python `match_id`/`result_id`/
  `replay_id` byte-for-byte unchanged. **Correction (Beta2 Phase 4.1):**
  this is not true of every historical Python match unconditionally — a
  non-zero Python start was always reachable (`bytefray run --a-start/
  --b-start`, and every tournament entrant past the first via
  `tournament_cli`'s own `index * spacing` placement), and this phase's own
  golden-value note below is direct evidence of that: a real historical
  non-zero-start Python `match_id` had to exist for refreshing it to be
  necessary. For every match that genuinely ran at `start=0`, the identity
  is unchanged; for one that did not, this is a deliberate, one-time
  identity transition — see [COMPATIBILITY.md](COMPATIBILITY.md)'s
  "Placement" note for the full, corrected compatibility statement and its
  tournament-resume consequence. The one place this *did* require
  refreshing a pinned golden value is `test_ruleset_v1_equivalence.py`'s
  own intentionally-non-zero-start Python fixtures (`slot * 19`/
  `slot * 2048`) — see that file's updated `EXPECTED` entries and their
  explanatory comment for the full before/after accounting; every
  non-identity fact in that golden corpus (winner, termination reason,
  ticks, score, per-agent behavior) is unchanged, proving this is a pure
  identity fix, never a gameplay change.
- **`compare_candidate_baseline`** grouping key gained `placement_id`
  alongside `(opponent_id, seed, orientation)` — a v2 candidate's
  `opposed` cell now only ever pairs against a baseline's `opposed` cell,
  never a differently-placed one. `ComparisonEntry` gained a
  `placement_id: str = "fixed"` field to carry this through reporting.

## 12. Schema decision (Phase 1G)

**Two additive, request-methodology-resolved version numbers**, never a
convenience bump:

- `IDENTITY_VERSION` (4) / `SCHEMA_VERSION` (4) — unchanged, used for every
  v1-methodology evaluation (omitted or explicit `bytefray-rules-1`).
- `IDENTITY_VERSION_V2` (5) / `SCHEMA_VERSION_V2` (5) — used **only** for a
  v2-methodology (`bytefray-rules-2`) evaluation.

Rationale: `EvaluationCell` gained five new fields (`rules_compatibility_id`,
`placement_id`, `subject_start`, `opponent_start`, `placement_index`) with
v1-preserving defaults. Because `asdict(cell)` always emits every dataclass
field, these inert, always-`"fixed"`/`0`-valued keys do appear in a freshly
written v1 evaluation's persisted cell dicts too — but `SCHEMA_VERSION`
stays `4` for those artifacts regardless, matching this module's own
established precedent (`IDENTITY_VERSION`/`SCHEMA_VERSION` are versioned
explicitly whenever the wire/hash recipe's *shape* changes, per the file's
own 2→3 and 3→4 history) while guaranteeing `_load_state`'s strict
`schema_version` equality check for v1 resume is completely unaffected —
resuming a v1 evaluation still requires and writes exactly `4`, exactly as
before Phase 1 existed.

`evaluation_history`'s adapter layer treats this the same way schema 4 was
introduced: `SUPPORTED_V2_VERSIONS` widened from `(2, 3, 4)` to
`(2, 3, 4, 5)`, `_ORIENTATION_AWARE_VERSIONS` widened from `(4,)` to
`(4, 5)`, and a new `_PLACEMENT_AWARE_VERSIONS = (5,)` recovers `placement`
as the certain historical fact `"fixed"` for every schema `< 5` artifact —
`v1_adapter.py` (schema 1) does the same. No new adapter module was
created; the existing `v2_adapter.py` (which already spans several schema
versions) grew one more, exactly matching its own established pattern.
`AdaptedCell.placement: ConfidenceValue` and the duplicate-condition-
coordinate structural health check both gained placement the identical way
`orientation` was added in a past phase.

**Historical compatibility.** No pre-Phase-1 `bytefray.evaluation` artifact
ever recorded `rules_compatibility_id="bytefray-rules-2"` (evaluation had
no Ruleset selector at all before now), so there is no historical v2
identity scheme to preserve compatibility with — Phase 1's v2 hash/schema
shape has complete design freedom. Every historical v1 artifact keeps its
original `evaluation_id`/`schedule_id`/`match_id`, unconditionally.

## 13. Preset/config changes (Phase 1I)

`evaluation_presets.EvaluationPreset` gained one new optional field,
`ruleset_id: str | None`, parsed from a new `ruleset:` YAML key (added to
`_ALLOWED_FIELDS`), validated against the same two-identity choice set
`agents evaluate --ruleset` accepts (`_VALID_RULESETS`, a duplicated
literal tuple — this module is deliberately import-independent of
`agent_evaluation`, mirroring `ORIENTATION_BOTH`'s own existing precedent).
`main()`'s existing three-tier resolution (explicit CLI > `--preset` >
ordinary default) now also resolves `ruleset_id` first, since the standard
v2 seed default depends on knowing whether the request is v2 before seeds
are resolved. A preset's `ruleset_id` never enters `evaluation_id`'s hash —
it is exactly as much an "input-construction convenience" as every other
preset field, per this module's own governing principle.

## 14. `EvaluationService` implementation (Phase 1N)

No `V2EvaluationService` was created — v2 is understood by the *same*
`EvaluationService`, exactly per the governing requirement. Summary of
what changed inside it:

- `EvaluationRequest` gained `ruleset_id: str | None = None` plus two
  derived properties, `resolved_rules_compatibility_id` and
  `is_v2_methodology`.
- `EvaluationCell` gained the five fields listed in §12.
- `build_matrix` gained a placement loop nested between seed and
  orientation (orientation stays innermost, matching its established
  precedent); placements/ruleset resolve internally from `request` itself
  (not from the function's pre-existing `rules_compatibility_id`/
  `arena_alignment_mode` parameters, which continue to feed only
  `condition_fingerprint`, preserving the exact existing call signature so
  no existing direct caller/test broke).
- `_execute_cell` resolves `agent_start`/`opponent_start` via the
  orientation-aware mapping in §7 and passes `ruleset_id=cell.
  rules_compatibility_id` to `test_agent()` — already-existing v2.0.0-
  alpha.1 selectors, now finally wired from evaluation. `current_execution_
  context` now reads the per-cell resolved Ruleset instead of the module
  constant, so a v2 cell's execution context correctly records
  `"bytefray-rules-2"`.
- `_expected_cell_match_id` (resume verification) gained `ruleset_id`/
  `subject_start`/`opponent_start` parameters, mirroring the real
  execution path exactly, so resume verification for a v2 cell recomputes
  the correct expected `match_id`.

## 15. Resume (Phase 1O)

No new resume-gating code was needed — the existing architecture already
generalizes correctly once identity is right (§11/§12): `_load_state`'s
strict `evaluation_id` **and** resolved-`schema_version` equality check
already fails closed on any methodology change, because a changed Ruleset,
seed set, or placement set (there being only one v2 placement set in this
phase) changes `evaluation_id` itself, and a changed Ruleset additionally
changes the required `schema_version`. Verified directly (see §25):
completed cells reused byte-for-byte across an interrupted/resumed real v2
run; missing cells freshly executed; changed seeds rejected with "Existing
evaluation state does not match this request"; changed Ruleset (v2 → v1
against the same output directory) rejected with an explicit unsupported-
schema-version message rather than silently misinterpreting the artifact.

## 16. History / 17. Comparison (Phase 1P)

`evaluations list`/`show` work unchanged for v2 artifacts (schema
dispatch is additive, §12). `show` now discloses the distinct placement
ids actually observed across an artifact's own cells (derived from cells,
never a separately stored/driftable field) and, when the artifact's own
`rules_compatibility_id` resolves to v2, a `capture/core evidence:` section
(§19) — gated behind the same `--no-behavior` opt-out already used for the
per-cell `result.json` read cost, since both are the identical cost class.
`evaluations compare`'s comparability-first design (§11's `_condition_key`
placement addition) means a v1/v2 pair, or two v2 evaluations with
different placement or seed sets, produce zero `rows` (clean matched
pairs) and fall through to `unmatched_left`/`unmatched_right`/
`changed_condition`/`ambiguous_duplicate_groups` — never a misleading
performance delta.

## 18. Statistical pairing (Phase 1Q)

`evaluation_analysis.analyze()` derives its pairing entirely from
`compare_candidate_baseline` (§11), so the Wilson-interval and exact
paired-sign-test evidence it computes is automatically placement-aware
once the shared pairing source is fixed — no separate pairing
reimplementation exists to drift. No new statistical test was introduced.

## 19. Capture/core metrics (Phase 1L/1M)

New sibling module, `battle_engine.evaluation_capture` — mirrors
`evaluation_behavior.py`'s Tier-2 (`result.json`-read) pattern exactly,
reusing its `CellRef`/`cell_ref_from_evaluation_cell` type rather than
duplicating it. Per cell: `subject_captured`/`opponent_captured` (from each
entrant's own `termination_reason == "core_captured"`, already persisted
per-entrant in `result.json`), `capture_tick` (the match's own recorded
`ticks` — Vulnerable Core capture ends the match at the tick it is
detected, so no replay parsing is needed to know when), and `killer`
(`"subject"`/`"opponent"`/`None` — derived from each side's own recorded
`statistics.kills`, matching `python_runtime`'s own "killer != victim"
ambiguity handling; never guessed). Aggregate: captures caused/suffered,
capture rate (both directions), a capture-avoidance survival rate
(deliberately distinct from `evaluation_behavior`'s continuous
alive-ticks-based `survival_fraction`), and mean/median capture tick.

**Minimum core integrity over time was explicitly deferred** — it would
require per-tick replay reconstruction, a materially higher cost class than
every other Phase 1 metric, and result.json's existing per-entrant
termination/statistics facts are already sufficient for every metric this
phase actually needs. This is a disclosed, deliberate Phase 1 scope
boundary, not an oversight.

## 20. Capture vs. win/behavior relationship (Phase 1M/1R)

Capture, win/loss, score, and behavior remain four structurally independent
facts, never combined into one "v2 performance score": `evaluation_
capture.py` never reads outcome/score, `evaluation_analysis.py`/
`evaluation_behavior.py` never read capture, and the CLI/`evaluations show`
print them in clearly separated sections (`comparison:`/`evidence:`,
`behavior:`, `capture/core evidence:`).

## 21. CLI output (Phase 1S)

`agents evaluate` under v2 prints, before execution:

```text
ruleset: bytefray-rules-2
seeds: 1, 2, 3, 4, 5
placements: 3 (opposed, quarter, opposed-shifted)
scheduler orders: balanced
cells/opponent: 30
```

alongside the existing `matches:`/`ticks:` lines, so a user is never left
to infer a 30-cell-per-opponent evaluation from a final win rate. At
completion, the existing W/L/T, statistical-evidence, and behavior blocks
are followed by a `capture/core evidence:` block for v2 evaluations, kept
visually and structurally separate.

## 22. JSON/API output (Phase 1T)

`evaluations show --json` gained a `"capture"` sibling key (present only
when computed) and `AdaptedCell.to_json()`/`EvaluationSummary` already
serialize the new `placement` field additively — no existing key removed
or reshaped. `evaluation-presets show --json` gained `"ruleset"`. `agents
evaluate` itself has never had a `--json` flag and still doesn't; this
phase did not add one, consistent with "avoid removing existing fields, add
additively."

## 23. Designer compatibility boundary (Phase 1U)

No Designer (`client/`) source file was touched. Every change reaching
Designer's evaluation-history/results consumers (`AdaptedCell`,
`EvaluationSummary`, `methodology_lines`) is purely additive — new fields
with defaults, a new optional keyword parameter — so existing Designer code
paths continue to compile and run against the exact same call shapes.
`methodology_lines(orientation_mode, *, arena_alignment_mode=...)`'s new
parameter defaults to the historical constant, so any caller that does not
pass it (there are none left needing an update) sees unchanged output.

## 24. Multi-entrant extension seam (Phase 1V)

Explicitly identified for Beta2 Phase 2:

- **Inherently 1v1 today, by design:** `EvaluationPlacement` (two named
  fields, `subject_start`/`opponent_start`); `EvaluationRequest.
  candidate_id`/`baseline_id` (singular); `EvaluationCell.opponent_id`
  (singular); `physical_slots_for_orientation()` (2-tuple).
- **Already generic enough to extend:** `orientation` conceptually
  generalizes to "scheduler permutation" for N entrants (alpha.11 §12's
  84% permutation-sensitivity finding already anticipates this); `seed`,
  `ticks`, and the `rules_compatibility_id`/`arena_alignment_mode`
  identity-hashing pattern are entrant-count-independent as written;
  `standard_placements()`'s "derive mechanically as fractions of
  arena_size" approach generalizes to N seats without redesign.
- **Deliberate non-generalization in Phase 1:** placement/orientation were
  kept as named 1v1 fields (not a generic seat→address/seat→order map)
  because Phase 1V's own governing prompt (Phase 1V) explicitly warns
  against over-generalizing prematurely while also warning against an
  obvious dead end (`scheduler_order = "candidate-first" | "opponent-
  first"` as a closed two-value enum) — this phase avoided the dead end by
  keeping `orientation`'s existing *representation* (which the
  N-permutation generalization can replace outright in Phase 2) rather than
  building new two-value-only surface.
- Phase 2's job: replace the 1v1-specific `EvaluationPlacement`/
  `subject_start`/`opponent_start` and `orientation`'s two-value
  vocabulary with a generic seat/permutation representation, without
  discarding the identity/schema/resume/comparison architecture Phase 1
  built (§11/§12/§15/§17), which is already entrant-count-agnostic.

## 25. Real methodology characterization (Phase 1W)

Run against real starter/reference agents (Claimer, Hunter, Core Defender,
Core Tracker, Reactive Core Defender — not the full alpha ecology), through
the actual `bytefray agents evaluate --ruleset bytefray-rules-2` CLI, in an
isolated scratch data root:

1. **Claimer vs. Core Defender**, standard v2 methodology (30 cells,
   ticks=200, `--workers` default 1): candidate won 30/30 (100%),
   `captures caused: 0/30`, `captures suffered: 0/30` — Claimer's
   territory-focused strategy never engages Core Defender's core; a
   meaningful, disclosed absence of capture evidence, not a defect.
2. **Core Tracker vs. {Core Defender, Reactive Core Defender}** (60 cells,
   `--workers 4`): candidate win rate 12/60 (20%) overall, but
   **candidate_first 0/30 (0%) vs. opponent_first 12/30 (40%)** — a
   real, large scheduler-order effect, directly reproducing alpha.9/
   alpha.10's order-sensitivity finding through the shipped product path
   for the first time. `captures caused: 12/60 (20%)`, `captures suffered:
   0/60`, `capture tick: mean=81.00 median=74.50` — capture evidence
   populated, plausible, and directly explaining the order effect (every
   capture happened in the orientation where Core Tracker acted second).
3. **Identity/uniqueness:** all 60 schedule_ids in run 2 were unique; all
   60 in a `--workers 1` rerun matched byte-for-byte (`evaluation_id`
   identical, every cell's `match_id`/`outcome` identical) against the
   `--workers 4` run — parallelism affects wall-clock only.
4. **Resume:** run 2's output directory was truncated to 50/60 cells (10
   removed along with their match artifacts, simulating an interruption)
   and re-run; the result had all 60 cells, with every one of the 60
   `match_id`s — both the 50 reused and the 10 freshly executed —
   byte-identical to the original uninterrupted run.
5. **v1 unaffected:** `test_evaluation_cells_always_execute_under_ruleset_v1`
   (pre-existing, still passing unmodified) confirms an omitted-`--ruleset`
   evaluation still persists `rules_compatibility_id ==
   "bytefray-rules-1"` on the evaluation artifact *and* on every cell's own
   nested `result.json`.

All nine of Phase 1W's validation questions are answered by the above:
both scheduler orders occurred; all three standard placements occurred
(confirmed via `evaluations show`'s new placement disclosure); all
requested seeds occurred; every schedule_id was unique; parallelism
preserved results; resume preserved results; capture metrics were
populated; win/capture results were plausibly variable exactly where alpha
evidence predicts (scheduler order); v1 remained unchanged. This was
methodology validation, not new balance research — no gameplay conclusion
is claimed from these two matchups.

## 26. Parallel determinism (Phase 1X)

Confirmed directly (§25 item 3) and by the new automated test
`test_workers_do_not_affect_v2_cell_identity_or_results` (`--workers 1` vs.
`--workers 4`, identical `evaluation_id` and per-cell `(match_id, outcome)`
pairs) plus the pre-existing `test_agent_evaluation_parallel.py` suite
(`workers ∈ {1, 2, 4, 50}`), unmodified and still passing.

## 27. Performance

- 30 cells (Claimer vs. Core Defender, ticks=200, serial): **3.26s**
  (~0.109s/cell).
- 60 cells (Core Tracker vs. two opponents, ticks=200, `--workers 4`):
  **2.58s** (~0.043s/cell wall-clock, showing real parallel speedup).
- No dimension of the standard matrix was reduced to hit a cost target —
  both measurements are well inside "ordinary local use remains
  reasonable."

## 28. Compatibility / regression

Final qualification on `v2.0-beta2-development` (clean, sequential — see
AGENTS.md's testing-workflow guidance on avoiding concurrent pytest
invocations against the shared repo-local `.pytest-tmp`):

- `pytest`: full suite, one clean sequential run, **0 failed, 0 errors**
  (exact collected/passed/skipped counts recorded in the final report
  below).
- Ruff (`engine client`): all checks passed.
- mypy `engine/src/battle_engine`: no issues.
- mypy `client/src/battle_client`: no issues.
- `git diff --check`: clean.
- One pinned golden-value fixture (`test_ruleset_v1_equivalence.py`'s
  three non-zero-start Python cases) required an explicit, documented
  refresh per that file's own "version the contract" policy — see §11.
  Every non-identity fact in that corpus is unchanged.
- One pre-existing test (`test_evaluate_cli_has_no_ruleset_selection_flag`)
  encoded the exact Beta1 boundary this phase is tasked with lifting; it
  was rewritten (not deleted) to assert the new, correct boundary — see
  that test file's updated section comment.

## 29. Phase-2 multi-entrant boundary

This phase implements **1v1 evaluation only**. No 3-entrant (or N-entrant)
evaluation schedule, permutation set, or generic seat model was built —
only the extension seam identified in §24. Beta2 Phase 2 owns: generic
seat/permutation identity, 3-entrant schedule generation, winner/placement
semantics for more than two entrants, and a generic cell/result
representation built on top of (not discarding) this phase's identity/
schema/resume/comparison architecture.
