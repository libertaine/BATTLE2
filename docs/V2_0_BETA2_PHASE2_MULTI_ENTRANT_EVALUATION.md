# Bytefray v2.0.0-beta2 Phase 2 — Multi-Entrant Evaluation Model

**Status: implementation complete on `v2.0-beta2-development`, not yet
released.** This document is Phase 2's design record and qualification
report. It replaces Phase 1's conceptually-1v1 candidate/opponent +
orientation vocabulary with a generic entrant/seat/permutation model
capable of real 3-entrant evaluation, while leaving Phase 1's identity,
schema, resume, comparison, and v1-compatibility architecture completely
unweakened — and, along the way, finds and fixes a genuine Phase 1 defect
in evaluation-artifact health verification (§14).

Governing invariant:

> A Bytefray multi-entrant evaluation cell represents a canonical roster
> under an explicit deterministic entrant-to-seat assignment and
> deterministic layout/environment condition. That identity remains
> correct across worker count, resume, comparison, and artifact reloading,
> while legacy v1 and Phase-1 pairwise v2 identities remain unchanged.

Three entrants are the first production evaluation surface proving this
model — not a special-cased three-player feature.

---

## 1. Pre-existing N-entrant engine capability

Before writing any Phase 2 code, the engine layer was audited directly
(not inferred from names) and found to already be fully N-entrant-capable,
proven at N=3 for both VM and Python, under both Ruleset v1 and the
Ruleset-v2 alpha lineage — no engine architecture change was needed for
this phase:

- `MatchRequest.entrants: tuple[MatchEntrant, ...]` has never been
  constrained to length 2; `NativeMatchService.run`'s only cardinality
  checks are "non-empty," "no mixed VM/Python composition," and "no
  duplicate `MatchEntrant.agent_id`."
- `match_service.canonical_match_id` already hashes the full entrant tuple
  generically (`enumerate(request.entrants)`), with no pairwise
  assumption.
- `results.resolve_winner` is already the single, N-entrant-generic
  winner-resolution algorithm shared by every runtime — see §7.
- `python_runtime.apply_core_capture`/`_attribute_core_capture` (Ruleset
  v2's Vulnerable Core) iterate `states` generically, with a docstring
  stating the "owns zero," not "opponent owns all" capture rule was
  *deliberately* written to "stay well-defined if Bytefray ever supports
  more than two entrants."
- `battle_engine.scheduler.run_sequential_quota` executes entrants in
  exactly the order it is given — entrant tuple order **is** scheduler
  execution order, with no separate concept of "seat" existing at the
  engine level before this phase.
- `engine/tests/test_v2_alpha4_multi_entrant.py` (483 lines, pre-existing)
  already proves this exhaustively: multi-death continuation, 3-way core
  capture with correct attribution, "kill stealing" between two
  simultaneous attackers, three-way score ties, the dead-highest-score
  exclusion, one-survivor forced wins, and full replay/result round-trips
  for three distinct match IDs — all under unmodified `bytefray-rules-1`.
  This phase reuses that coverage rather than re-proving it.
- `TournamentService` was confirmed **not** a 3-entrant precedent: it
  schedules classic all-pairs round robins (C(N,2) separate 1v1 matches
  from an N-candidate roster), never one N-entrant match. Its
  `_entrant_identity`/roster-hashing pattern was useful conceptual
  precedent but not reused code.

What was genuinely missing was entirely at the evaluation/product layer:
`agent_evaluation.py`'s hardcoded `TESTED_AGENT_SLOT`/`OPPONENT_SLOT` pair,
`EvaluationRequest.opponent_ids` treated as N *separate* pairwise
opponents rather than a roster that could be fielded together, and no
seat/permutation/layout concept at all.

## 2. Entrant / roster model

`EvaluationRequest` gained one new field, `group: bool = False`. Existing
`candidate_id`/`opponent_ids` are reused as the compatibility interface —
no new CLI vocabulary was introduced for entrant identity, per the
governing "prefer extending the existing abstraction" requirement:

- **`roster_agent_ids`** (property): `(candidate_id, *opponent_ids)`, in
  request order, **duplicates preserved** — this is the *logical* roster,
  a multiset, not a set. Preserving duplicates is what makes self-play
  (the same agent occupying two seats) representable at all.
- **`canonical_roster`** (property): `tuple(sorted(roster_agent_ids))` —
  the *identity* form used for cross-evaluation comparison and per-cell
  disclosure. Order-independent by design: "Claimer+Core Defender+Reactive
  Core Defender" is the same roster regardless of `--opponents` input
  order.

**Design audit finding, resolved by documentation rather than a code
change:** `evaluation_id`'s own hash payload still uses `opponent_ids` in
*request order* (`"opponents": [identities[o] for o in request.
opponent_ids]`), not the canonical form — this is not new to Phase 2 (the
pre-existing pairwise path has always hashed `opponent_ids` in request
order too, per `build_matrix`'s own long-standing "opponents and seeds in
exact request order, never re-sorted" contract) and is the *safe*,
conservative choice: it never silently reuses an output directory across
two invocations whose inputs merely happened to differ in typed order. The
layered design that actually matters is: **`evaluation_id`/resume identity
stays request-order-sensitive (matching every other evaluation mode's
existing behavior); cross-evaluation *cell* comparison is
order-independent**, via each cell's own canonical `roster` field (§10) —
so two separately-run evaluations of the same roster, typed in a different
`--opponents` order, still align cell-by-cell correctly under `evaluations
compare`, even though they get distinct `evaluation_id`s and cannot
`resume` into each other. Verified directly:
`test_roster_agent_ids_preserves_request_order_but_canonical_is_sorted`,
`test_canonical_roster_deterministic_regardless_of_input_order`.

**Duplicate agent / self-play.** The native engine rejects a duplicate
`MatchEntrant.agent_id` — but `MatchEntrant.agent_id` is the *seat* label
("A"/"B"/"C", always unique per cell in this design), never the logical
agent id (carried in `MatchEntrant.name`, which may legitimately repeat).
`agent_test._test_agents`/`EvaluationService._execute_group_cell`
construct entrants exactly this way (`MatchEntrant.python(seat, agent_id,
start, spec)`), so a roster with a duplicate logical agent id (e.g.
`--opponents claimer,core_defender` against `candidate=claimer`) executes
successfully through the real engine boundary — verified with a genuine
execution-level regression test, not just schedule generation:
`test_self_play_executes_successfully_through_real_engine` (9/9 cells
`status="completed"`, zero errors, every cell's own `result.json` records
3 distinct match-level entrant slots A/B/C even though only 2 distinct
logical agents occupy them). `enumerate_seat_assignments` (§3) already
deduplicates by resulting seat-agent tuple, so a 2-duplicate/1-distinct
roster correctly produces 3 distinct seat assignments (3!/2!), not 6.

**Candidate reporting role.** `subject_role`/`subject_id` continue to mean
"the focal entrant for aggregate reporting" for a group cell exactly as
for a pairwise cell — group mode does not abandon the "one distinguished
candidate" concept, it just fields that candidate together with its full
roster in one match instead of pairwise. `EvaluationCell.subject_seat`
(new) resolves which seat the candidate occupies for a *specific* cell
(self-play-aware: the first occurrence, deterministically, if the
candidate's own agent id repeats).

## 3. Seat / permutation model

`seat_label(index)` — `"A"`, `"B"`, `"C"`, ... (`chr(ord("A") + index)`,
supports up to 26 seats) — is literally the seat's `MatchEntrant.agent_id`
value, mirroring `TESTED_AGENT_SLOT`/`OPPONENT_SLOT`'s existing convention
generalized to N. Since the engine's scheduler executes entrants in
`MatchRequest.entrants` tuple order (§1), **seat order is scheduler
execution order — there is no separate axis to track.** A permutation is
therefore never cosmetic placement metadata; it changes real gameplay
scheduling and must remain (and does remain) identity-affecting.

`EvaluationSeatAssignment(seat_agent_ids: tuple[str, ...])` — ordered by
seat, the agent id occupying each one. `enumerate_seat_assignments(roster)`
enumerates every *distinct* seat assignment via `itertools.permutations`
over roster indices, deduplicated by the resulting `seat_agent_ids` tuple
(not the underlying index permutation) — this is what correctly collapses
a duplicate-agent roster's seat-assignment count below `N!` (§2).
`itertools.permutations` iterates in deterministic lexicographic index
order, so generation order is reproducible run to run
(`test_enumerate_seat_assignments_deterministic`).

For 3 distinct entrants: all 6 permutations are generated
(`test_all_three_player_permutations_generated_in_real_matrix`), verified
directly against a real 18-cell matrix. `MatchRequest.entrants`' actual
positional order matches the recorded `seat_agent_ids` order exactly by
construction (`_execute_group_cell` builds `GroupEntrantSpec`s via
`enumerate(zip(cell.seat_agent_ids, cell.seat_starts))`, and
`agent_test._test_agents` places each at `MatchEntrant.python(entrant.
seat, ...)` in that same iteration order).

**Phase 2 policy is exhaustive-permutation-only, deliberately.**
`enumerate_seat_assignments` has no policy parameter; future scheduling
policies (rotation-only, balanced subsets, an explicit preset-driven
policy) can be added as sibling functions with the identical
`tuple[EvaluationSeatAssignment, ...]` return shape, without changing this
function's contract. This is an intentional, documented scaling boundary:
`N!` exhaustive permutation quickly becomes impractical past small N (4! =
24, 5! = 120), and Phase 2 does not attempt to solve that — see §16.

## 4. Layout (placement) model

`EvaluationLayout(layout_id: str, seat_starts: tuple[int, ...])` — per-seat
start addresses, independent of which roster entrant occupies that seat
this cell (layout and seat assignment are orthogonal identity dimensions,
generalizing Phase 1's orientation-vs-placement separation).
`standard_layouts(entrant_count, arena_size=None)` derives three
conditions mechanically as fractions of `arena_size` (default 4096, from
`Config().arena_size`):

| id | formula | 3-entrant starts (arena_size=4096) |
| --- | --- | --- |
| `spread` | `seat_starts[i] = (i * arena_size // n) % arena_size` | `(0, 1365, 2730)` |
| `spread-shifted` | `seat_starts[i] = (i * gap + gap // 2) % arena_size` | `(682, 2047, 3412)` |
| `close` | `seat_starts[i] = (i * (gap // 2)) % arena_size` | `(0, 682, 1364)` |

where `gap = arena_size // entrant_count`. This is the direct N-seat
generalization of `standard_placements()`'s three 1v1 conditions
(`opposed`/`opposed-shifted`/`quarter`) — for `entrant_count=2` this exact
formula reproduces Phase 1's placements byte-for-byte
(`(0, 2048)`/`(1024, 3072)`/`(0, 1024)`), a mathematical coincidence
confirmed directly but **never wired into code**: `standard_placements()`
remains completely untouched, called only by the 1v1 path, forever — the
N=2 equivalence is documentation-only evidence that this is a genuine
generalization, not two independently-invented schemes. Non-overlap is
structural: every gap here is a fraction of `arena_size` (682 cells for
the tightest case at N=3, default arena) vastly larger than `CORE_SIZE`
(8) — verified directly via `python_runtime.core_addresses` for every seat
pair (`test_standard_layouts_seat_starts_never_collide`). Layout and seat
assignment are verified as genuinely distinct identity dimensions
(`test_layout_and_permutation_are_distinct_identity_dimensions`: the same
seat assignment under 3 different layouts produces 3 distinct
`schedule_id`s).

## 5. Schedule cardinality

For an N-entrant roster:

```text
cells = seeds × layouts(3) × distinct_seat_assignments
```

where `distinct_seat_assignments = N!` for a fully-distinct roster (fewer
for a self-play roster with repeats). For 3 distinct entrants: `seeds × 3
× 6`. Verified exactly:
`test_expected_group_cell_count_exact` (3 seeds → 54 cells). No dimension
was silently dropped; every generated cell has a unique
`schedule_id`/`match_id`/`condition_fingerprint` (verified both by test
and by real characterization, §12).

## 6. Winner semantics — reused, not reinvented

Phase 2 does **not** introduce a second winner-resolution algorithm. The
engine's existing `results.resolve_winner` (already fully N-entrant
generic, §1) is the sole authority:

- Exactly one entrant alive → that entrant wins outright, no score check.
- Two or more alive, `win_mode="survival"` → no winner (`""` /
  `WINNER_TIE_SENTINEL`).
- Two or more alive, score-fallback mode (the default) → **only the alive
  entrants are score-eligible** — a dead entrant is categorically excluded
  from winning while any entrant survives, *regardless of its accumulated
  score* (the v2.0.0-alpha.4.1 fix, generalizing the original 1v1 rule to
  N; territory scoring has no alive-gate, so an unguarded dead entrant
  could otherwise keep accruing score and outscore living entrants — this
  was alpha.4's own founding finding, already fixed and already tested by
  `test_v2_alpha4_multi_entrant.py`, not re-derived here).
- A strict top-score tie among eligible entrants → no winner (tie).
- Zero alive → falls back to comparing every entrant, dead or alive
  (deliberately no special rule for this case — see
  `docs/V2_0_ALPHA4_1_WINNER_SEMANTICS.md`).

`EvaluationService._cell_from_match_result_group`/`_cell_from_envelope_
group` map this into the candidate-centric `win`/`loss`/`tie` vocabulary
existing consumers expect: `"win"` iff `match_result.winner ==
cell.subject_seat` (the candidate's *actual* seat for that specific cell,
never a fixed slot), `"tie"` iff no winner, else `"loss"`. Verified this
mapping is not hardcoded to seat "A":
`test_candidate_outcome_is_win_only_when_literally_the_resolved_winner`
scripts every non-candidate entrant to HALT immediately, runs the full
18-cell matrix (candidate occupying seat A, B, *and* C across different
cells), and asserts `outcome == "win"` for every cell regardless of which
seat the candidate landed in that cell.

`score_opponent`/`territory_opponent` are deliberately left `None` for a
group cell — ill-defined once there is more than one "opponent"; the full
per-seat breakdown remains fully recoverable from that cell's own
persisted `result.json` (never discarded), just not duplicated onto these
1v1-shaped summary fields. `aggregate_cells`' existing `or 0.0` null-safety
(pre-existing, unmodified) degrades `score_differential_avg`/`territory_
differential_avg` gracefully to the candidate's raw values for group
cells rather than crashing — a documented, minor Phase 2 simplification.

## 7. Identity / schema

Every gameplay-relevant group dimension enters canonical identity, with
the same "conditionally add, never for non-group" discipline Phase 1
established for placement — a non-group v2 request's hash payload is
byte-identical to Phase 1's, unconditionally.

- **`evaluation_id`**: gains `"group": True` and the actual resolved
  layout list (`"layouts"`, not just a mode label — two different N-seat
  layout sets must never collide), and **omits** `"orientation_mode"`
  (meaningless once seat assignment is the real scheduler-order axis).
  `"opponents"` stays request-order (§2). Uses
  `IDENTITY_VERSION_V2_GROUP` (6) instead of `IDENTITY_VERSION_V2` (5).
- **`schedule_id`**: hashes `evaluation_id`, canonical `roster`,
  `seat_agent_ids`, `seed`, `layout_id`, and a defensive `ordinal`
  (mirroring Phase 1's own ordinal-plus-explicit-field redundancy
  precedent).
- **`condition_fingerprint`**: hashes each roster member's resolved
  identity (`agent_identity`), `seat_agent_ids`, `seed`,
  `effective_conditions`, `rules_compatibility_id`, `arena_alignment_mode`,
  and the resolved `layout` (id + seat starts).
- **`match_id`** (`canonical_match_id`, engine-level, unmodified by Phase
  2 — already N-generic, §1): hashes the full entrant tuple in seat order,
  each entrant's resolved source/identity, and (already, from Phase 1) each
  Python entrant's non-zero start address.
- **`AdaptedCell`/comparison** (`evaluation_history`): gained `roster`,
  `seat_agent_ids`, `layout_id` (`ConfidenceValue`-wrapped, mirroring
  `placement`'s exact recovery pattern). `comparison._condition_key`
  branches on `cell.roster` being non-empty: a group cell's alignment key
  is `("group", canonical_roster, seed, conditions_fp, rules_id,
  arena_alignment_id, seat_agent_ids, layout_id)` — structurally
  incompatible with (and therefore never colliding against) a pairwise
  cell's opponent-identity-based key, by construction (different tuple
  shape, `"group"` literal tag).

`EVALUATION_ARENA_ALIGNMENT_MODE_V2_GROUP_STANDARD =
"ruleset_v2_group_standard_layouts"` is a third sibling value, distinct
from both `"fixed"` (v1) and `"ruleset_v2_standard_placements"` (Phase 1
1v1) — this alone already makes a group evaluation and a 1v1 evaluation
comparability-incompatible via the *existing*, unmodified
`_arena_alignment_id` gate, with zero new comparison code required for
that specific guarantee.

## 8. Schema/identity version decision: v6, deliberately

```text
v1 (any Ruleset)                 -> SCHEMA_VERSION / IDENTITY_VERSION = 4  (unchanged)
Phase 1 v2, 1v1 (pairwise)       -> SCHEMA_VERSION_V2 / IDENTITY_VERSION_V2 = 5  (unchanged)
Phase 2 v2, group (multi-entrant) -> SCHEMA_VERSION_V2_GROUP / IDENTITY_VERSION_V2_GROUP = 6  (new)
```

Group evaluations introduce genuinely new, always-present
(`EvaluationCell` gained `roster_agent_ids`/`seat_agent_ids`/`layout_id`/
`seat_starts`/`seat_assignment_index`/`layout_index`) wire-shape fields —
not merely optional Phase-1 metadata reused differently. This is the exact
same justification Phase 1 used to introduce version 5 rather than reusing
4: a genuinely new hash/wire recipe gets its own version, gated so it only
ever applies to the methodology that actually produces it.
`resolved_schema_version`/`resolved_identity_version`/`resolved_arena_
alignment_mode` all became 3-way (`is_v2_methodology`, `group`), with every
existing call site updated to pass both flags. **No pairwise v2 (v5)
artifact is migrated to v6** — `_write_state` resolves the version from
the *current request's* `group` flag, never rewrites a resumed artifact's
prior version.

Confirmed: `test_group_schema_and_identity_version_are_six`,
`test_non_group_v2_evaluation_unaffected_by_group_field_existing`.

## 9. Resume

No new resume-gating code was needed, for the identical reason Phase 1
needed none: `EvaluationService._load_state`'s existing strict
`evaluation_id` **and** resolved-`schema_version` equality check already
fails closed on any methodology change, because a changed roster, seed
set, or Ruleset changes `evaluation_id` itself, and group vs. non-group
changes the required `schema_version` (5 vs. 6).

Automated coverage: `test_group_resume_reuses_completed_cells` (identical
match_ids across two `run()` calls against the same output),
`test_group_resume_executes_missing_cells` (a cell removed from both
`evaluation.json` and its own artifact directory is freshly re-executed;
every cell ends `status="completed"`), `test_changed_roster_rejects_
group_resume`, `test_group_vs_1v1_v2_rejects_resume_at_same_output`.

Manual characterization (§12) additionally exercised a real 36-cell
group evaluation: 8 completed cells (plus their match artifacts) removed,
`complete` reset to `False`, re-run — result: 36/36 cells, **every one of
the 36 `match_id`s (28 reused + 8 freshly executed) byte-identical to the
uninterrupted run**, `complete=True`.

## 10. Comparison

`evaluations compare` between two independent group-evaluation artifacts
now aligns at the true per-cell condition level (roster + seat assignment
+ layout + seed), never by aggregating permutations first:

- **Identical experiment** (same roster, seeds, methodology, run twice):
  every cell aligns — verified directly,
  `test_identical_group_evaluations_align_cleanly` (cardinality derived
  from the actual matrix, `zero` unmatched/changed_condition/ambiguous on
  either side) and manually (§12: 36/36 rows, 0 unmatched).
- **Different roster**: zero clean rows — `test_different_roster_group_
  evaluations_do_not_align`, and manually against the two real
  characterization matrices (Matrix A vs. Matrix B, different rosters and
  entrant counts): `comparable: 0, unmatched left: 36, unmatched right:
  54` — fail-closed, exactly the desired behavior.
- **Group vs. pairwise**: never aligns, by construction (§7's structurally
  distinct key shapes) — `test_group_and_1v1_evaluations_never_align`.
- **Existing 1v1 comparison**: unaffected —
  `test_1v1_comparison_still_works_unaffected` is a direct regression
  check that the group branch added to `_condition_key` never fires for a
  pairwise cell (`cell.roster` stays the recovered-empty sentinel for
  every historical/pairwise cell, §14).

## 11. CLI

```bash
bytefray agents evaluate claimer \
  --ruleset bytefray-rules-2 \
  --opponents "core_defender,reactive_core_defender" \
  --group \
  --seeds 1,2
```

`--group` is a new boolean flag (`agents evaluate --group`), reusing the
existing positional `candidate_id`/`--opponents`/`--seeds`/`--ruleset`
surface entirely — no separate multi-player command, no new entrant-id
vocabulary. Validated eagerly in `EvaluationService._validate`: requires
`--ruleset bytefray-rules-2`, requires at least two `--opponents` (a 3+
entrant roster), and rejects `--baseline` (deferred — cross-evaluation
comparison, §10, already covers the "compare two candidate builds against
the same roster" use case without a within-evaluation baseline).

Dry-run cardinality disclosure (fixed during this phase's own design
audit — see §16):

```text
candidate: claimer
baseline: none
opponents: core_defender, reactive_core_defender
ruleset: bytefray-rules-2
seeds: 1, 2
roster: claimer, core_defender, reactive_core_defender (3 entrants)
layouts: 3 (spread, spread-shifted, close)
seat assignments: 6
cells: 36
ticks: 200
matches: 36
Arena alignment: ruleset_v2_group_standard_layouts — translation robustness not evaluated
```

The 1v1-only "subjects: N opponents: M" and "Entrant orientation:
both/candidate-first only" lines are **suppressed** for `--group` (they
describe axes — `subject_role`, a 2-value orientation — that do not exist
in group methodology; printing them anyway would misrepresent a 6-seat-
permutation scheduler-order axis as a 2-value one). The arena-alignment
line is kept (it correctly names the resolved group methodology
identifier). The identical fix was applied to `evaluations show`'s
historical-artifact disclosure (`evaluation_history/cli.py`) so a group
artifact discloses `roster:`/`layouts:`/`seat assignments:` instead of the
1v1 `placements:` line, and omits the same misleading orientation line.

## 12. Manual characterization

Run against real starter/reference agents (Claimer, Hunter, Core Defender,
Core Tracker, Reactive Core Defender) through the actual CLI, isolated
scratch data root — **Matrix B below specifically closes the Hunter
coverage gap disclosed at the end of Phase 1.**

### Matrix A — Claimer vs. {Core Defender, Reactive Core Defender}

Roster: `claimer, core_defender, reactive_core_defender`. Ruleset:
`bytefray-rules-2`. Seeds: `1, 2`. Result: 3 layouts × 6 permutations × 2
seeds = **36 cells**, all 36 `schedule_id`/`match_id`/`condition_
fingerprint`s unique, all 6 seat permutations and all 3 layouts observed.
Serial vs. `--workers 4`: identical `evaluation_id`; identical
`(match_id, outcome)` per `schedule_id`. Candidate won all 36/36 (100%) —
Claimer's territory-expansion strategy dominated this particular pairing
of defensive opponents; not evidence of a general balance conclusion.
Wall time: **4.90s / 36 cells (~0.136s/cell)**.

### Matrix B — Core Tracker vs. {Hunter, Core Defender}

Roster: `core_tracker, hunter, core_defender`. Seeds: `1, 2, 3`. Result: 3
layouts × 6 permutations × 3 seeds = **54 cells**. Candidate `core_tracker`
won **2/54 (4%)** — a genuinely contested/lopsided 3-entrant matchup
(unlike Matrix A). Wall time: **6.70s / 54 cells (~0.124s/cell)**.

**Observed permutation/layout sensitivity** (reported honestly, not
forced): both of Core Tracker's 2 wins occurred with Core Tracker in seat
`"C"` (the last-acting seat that tick); the other 4 seat assignments (Core
Tracker in seat A or B) produced zero wins across all seeds/layouts. This
is directionally consistent with alpha.9/alpha.11's scheduler-order
finding (acting later in a tick's scheduling can matter for offense
timing) but is **not** presented as a proven causal effect — seed and
layout also varied between the two winning cells, and n=2 is far too small
to isolate seat as the sole driver. It is exactly the kind of signal the
Phase 2 architecture exists to make *visible* (a pairwise-only methodology
could never have surfaced a seat-dependent pattern at all), which is the
real point of this characterization: proving the architecture, not
settling a balance question.

### Self-play

`claimer` vs. `(claimer, core_defender)` with `--group`: roster
`(claimer, claimer, core_defender)` → 3 layouts × 3 distinct seat
assignments (3!/2!, not 6) = 9 cells, all `status="completed"`, zero
errors — see §2 for the execution-level mechanism this exercises.

### Determinism / resume (repeated from §9 for completeness)

Worker-count determinism and interrupted-resume were both verified against
Matrix A's real artifacts, not just synthetic fixtures (§9's manual
evidence).

## 13. Performance

| Matrix | cells | workers | wall time | cells/sec |
| --- | --- | --- | --- | --- |
| A (Claimer roster) | 36 | 1 | 4.90s | ~7.3 |
| B (Core Tracker roster) | 54 | 1 | 6.70s | ~8.0 |

Both are well within "ordinary local use remains reasonable" — no
dimension of the standard N=3 matrix (3 layouts × N! permutations × seeds)
was reduced to hit a cost target. No performance regression was found;
no optimization was attempted (correctness was Phase 2's stated primary
goal).

## 14. Phase 1 defect found and fixed: evaluation-history health rehash

**Discovered during this phase's own manual characterization**, not
speculatively: `evaluations show` against a genuine Phase 1 (schema
version 5, 1v1 v2) artifact reported
`health: planned_identity_inconsistent, condition_fingerprint_
inconsistent` — a false positive on every 1v1 v2 artifact ever created,
including artifacts already committed as part of Phase 1's own
qualification.

**Root cause**: `evaluation_history/v2_adapter.py`'s self-consistency
health check independently *rehashes* `evaluation_id`/each cell's
`condition_fingerprint` from persisted fields, to verify they were
computed honestly (B1's invariant) — a hand-maintained mirror of
`EvaluationService._evaluation_id`/`build_matrix`'s own payload
construction. Phase 1 added a `"placements"` key to `evaluation_id`'s
payload and a `"placement"` key to each cell's `condition_fingerprint`
payload (§11 of the Phase 1 doc) but never updated this independent mirror
to match — so every v5 artifact's real hash (computed with the extra key)
never matched the adapter's recomputed hash (computed without it),
regardless of whether the artifact was genuinely internally consistent.

**This is an artifact-*health-verification* bug, not evidence that any
Phase 1 persisted `evaluation_id`/`schedule_id`/`match_id` was ever wrong**
— the actual identity values Phase 1 computed and persisted were correct
throughout; only the *independent rehash used to check that fact* was
stale. No historical ID was rewritten or changed by this fix.

**Fix**: `v2_adapter.py`'s rehash now branches identically to
`_evaluation_id`/`build_matrix` themselves — `identity_version >= 5`
(non-group) adds the recomputed `"placements"` list
(`_recomputed_v1v1_placements`, calling the real `standard_placements()`);
`identity_version >= 6` (group) adds `"group": True` plus the recomputed
`"layouts"` list (`_recomputed_group_layouts`, calling the real
`standard_layouts()`) and omits `orientation_mode`, mirroring §7 exactly.
The per-cell `condition_fingerprint` rehash gained the equivalent
`"placement"` key for `identity_version >= 5` (non-group); the group case
is left honestly unverified by this specific check (the existing
`opponent_ids_list.index(...)` lookup this rehash relies on cannot resolve
a group cell's joined display-label `opponent_id` to a real opponent
identity — it `continue`s/skips rather than producing a false positive,
an accepted Phase 2 scope boundary, never a false negative).

**Regression coverage**: `test_group_artifact_is_healthy`,
`test_1v1_v2_artifact_is_healthy_regression` (the specific v5 case this
phase found broken), `test_historical_pre_group_artifact_recovers_
empty_roster`. Verified manually against both real characterization
artifacts: `evaluations show` now reports `health: healthy` for both the
v5 (Matrix A run under 1v1 methodology, spot-checked) and v6 (Matrix
A/B's own group artifacts) cases.

## 15. v1 / Phase-1 preservation

- **v1 evaluation**: `test_v1_matrix_unaffected_by_group_feature_
  existing` — an omitted-`--ruleset` request's matrix is unaffected by
  `group` existing as a concept; `roster_agent_ids` stays `()`,
  `rules_compatibility_id` stays the historical constant.
  `test_ruleset_v1_equivalence.py`'s full golden corpus (including the
  pre-existing 3-entrant VM/Python fixtures) re-run clean, unmodified.
- **Phase 1 v2 pairwise**: `test_non_group_v2_evaluation_unaffected_by_
  group_field_existing` confirms schema/identity stay at 5, `group: False`
  persisted explicitly. `test_1v1_comparison_still_works_unaffected`
  confirms comparison behavior is unchanged. The full Phase 1 test suite
  (`test_agent_evaluation_v2_methodology.py`, 46 tests) re-runs clean.
- **`test_v2_alpha4_multi_entrant.py`** (the engine's own N-entrant
  acceptance suite, pre-existing) re-runs clean, confirming Phase 2 made
  zero engine-layer changes.

## 16. Analysis compatibility (deferred to Phase 3)

`evaluation_behavior.py`/`evaluation_capture.py`'s Tier-2 readers resolve
the subject's physical match slot via `physical_slots_for_orientation`
(a 2-value candidate_first/opponent_first mapping) — meaningless for a
group cell, whose subject occupies whichever seat `subject_seat` says
(any of A/B/C, varying per cell). Rather than silently read the *wrong*
seat's `result.json` entry for any cell where the candidate isn't
literally in seat "A" (a real, confirmed-during-audit correctness risk,
not a hypothetical one), both the live CLI (`agent_evaluation._print_
result`) and the historical CLI (`evaluation_history.cli._cmd_show`)
explicitly skip behavior/capture computation for a group artifact,
printing `"behavior/capture analysis: deferred for multi-entrant
evaluations"` instead. 1v1 behavior/capture analysis is completely
unaffected — both modules are otherwise untouched by this phase. No
per-seat result data is discarded; every cell's `match_id`/`result_id`
still point at the real, complete `result.json`, fully available to a
future Phase 3 that builds proper N-entrant aggregate analysis on top of
it.

## 17. Remaining 1v1 assumptions

- `agent_evaluation.EffectiveConditions` (pre-existing, predates even
  Phase 1) carries constant `subject_slot`/`opponent_slot`/`entrant_order`
  default fields that are never actually derived from the request — they
  contribute the *same* constant value to `effective_conditions`'s hash
  for every evaluation, v1, pairwise-v2, and group alike, so they cause no
  incorrect behavior (no false collision or mismatch), just stale/unused
  field names. Deliberately left untouched: fixing it would risk changing
  v1's `effective_conditions_fingerprint` for zero functional benefit, and
  it predates this phase's own scope.
- `compare_candidate_baseline`/within-evaluation `--baseline` comparison
  remains 1v1-only; group mode's cross-build comparison need is served by
  `evaluations compare` between two separate evaluations instead (§10) —
  deliberately not unified into one mechanism this phase.
- `evaluation_behavior.py`/`evaluation_capture.py` remain 1v1-shaped
  internally (§16) — explicitly deferred, not silently broken.
- `ComparisonRow` (single-opponent-per-row comparison display) is not
  used for group-vs-group comparison in a per-seat breakdown sense; a
  group comparison row currently reports only the candidate's own
  aggregate outcome, matching §6's summary-field scope.
- `enumerate_seat_assignments`'s exhaustive-only policy does not scale
  past small N (4! = 24, 5! = 120, ...) — an intentional, disclosed Phase
  2 boundary (§3), not an oversight; a future phase should add an explicit
  balanced/rotation policy rather than relying on exhaustive enumeration
  alone once N grows.

None of these are silent correctness gaps — each either causes no
incorrect behavior, or is explicitly guarded/deferred with a clear
disclosure rather than a wrong answer.

## 18. Multi-entrant extension seam (confirmed generic, not 3-specific)

Every new type introduced this phase (`EvaluationLayout`,
`EvaluationSeatAssignment`, `seat_label`, `enumerate_seat_assignments`,
`standard_layouts`) is already written for arbitrary `entrant_count`, not
hardcoded to 3 — the 3-entrant characterization in this phase is the first
*proof* of the model, not a boundary the model was built up to. The one
explicitly bounded piece is exhaustive permutation enumeration itself
(§3/§17), which is a scheduling *policy* choice, cleanly separable from
the identity/schema/resume/comparison architecture (which has no N-limit
anywhere).
