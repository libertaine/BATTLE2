# Bytefray v4 RC Path — Phase 1: Stable Evaluation Methodology and Evaluation Integrity

Branch: `v4-rc1-development` (off `main`@`010c3f6b1cbfc7d63988f8ccfc2626aae7dcef99`, the
published `v4.0.0-alpha4` commit)

Starting SHA: `010c3f6b1cbfc7d63988f8ccfc2626aae7dcef99`
Ending SHA: `71da24ca1d793617dae9d93b8865668a161c8f5c`

Authority for this phase's implementation decisions:
[docs/research/v4/V4_PRE_RC_GAMEPLAY_EVALUATION_RESEARCH.md](V4_PRE_RC_GAMEPLAY_EVALUATION_RESEARCH.md)
(carried onto this branch, byte-identical, from `v4-pre-rc-research`@`a089db8`), whose two
accepted conclusions are: no gameplay alpha5 is required for 4.0, and a stable v4 evaluation
methodology should be implemented and qualified against `bytefray-rules-4-alpha2` ahead of the
permanent `bytefray-rules-4` identity.

---

## A. Executive summary

| Gate | Result |
|---|---|
| F.6 evaluation-integrity defect reproduced and root-caused? | **YES** |
| An evaluation with failed cells can no longer masquerade as successfully complete? | **YES** |
| Stable v4 evaluation methodology (schema 7) implemented and qualified? | **YES** |
| Gameplay/API/replay semantics unchanged? | **YES** |
| `bytefray-rules-4` introduced early? | **NO** |
| Full suite / GUI suite / static checks clean? | **YES** |

```text
PHASE 1 QUALIFIED — READY FOR RC PATH PHASE 2
```

---

## B. Starting state, verified

```text
git status --short          (empty)
git branch --show-current   v4-pre-rc-research
git rev-parse HEAD          a089db8c1c67780043a8894925f44f58e4a71587
git rev-parse origin/main   010c3f6b1cbfc7d63988f8ccfc2626aae7dcef99
git rev-parse v4.0.0-alpha4 07a1bae30706c0110d16f5a879c24601bf66acb5 (annotated tag)
  -> ^{commit}               010c3f6b1cbfc7d63988f8ccfc2626aae7dcef99
git rev-parse v4-pre-rc-research  a089db8c1c67780043a8894925f44f58e4a71587
```

`main`/`origin/main` and the peeled `v4.0.0-alpha4` tag agreed exactly with the task prompt's
stated SHAs. The apparent mismatch in the prompt (`v4.0.0-alpha4` = `010c3f6b…`, `git rev-parse
v4.0.0-alpha4` = `07a1bae3…`) is not a discrepancy: `v4.0.0-alpha4` is an annotated tag object,
and `rev-parse` on an annotated tag returns the tag object's own SHA, not the commit it points
to; `^{commit}` peels it to `010c3f6b…`, the prompt's value. No other unexpected repository state
was found. `v4-rc1-development` was created from `main` at `010c3f6b…`, not from the research
branch, per the governing task's explicit instruction.

## C. Durable research record carried onto the product branch

`docs/research/v4/V4_PRE_RC_GAMEPLAY_EVALUATION_RESEARCH.md` was copied, byte-identical (verified
by direct diff), from `v4-pre-rc-research`@`a089db8` — its final revision, including the §L.6
validation/integrity section. Commit `71da24c`.

**Not carried forward**, per the governing task's explicit instruction: `tools/
v4_pre_rc_reach_study.py`, `tools/v4_pre_rc_eval_methodology_study.py`, `tools/
v4_pre_rc_generate_probes.py`, `tools/v4_pre_rc_agents/`. None of these are product code, and
nothing this phase implements calls into them — the accepted methodology reuses existing
production seams (`placement.resolve_direct_match_starts`) directly, not the research harness.
The research branch itself was not merged.

---

## D. F.6 — reproduction, root cause, and lifecycle-integrity remediation

### D.1 Reproduction (before any fix)

```text
$ bytefray agents evaluate v4_claimer --opponents v4_scout --seeds 1 --ticks 50 --output <dir> --json
```

Candidate `v4_claimer` and opponent `v4_scout` are both Agent API v2 (`api_version: 2`) under the
installed `C:\ProgramData\Bytefray\agents\` root. `--ruleset` omitted.

| Field | Value |
|---|---|
| Resolved Ruleset | `bytefray-rules-2` |
| CLI exit status | `1` (the CLI's cell-count-based exit logic already worked correctly — see D.4) |
| `lifecycle_state` | `"finished"` |
| `complete` | `true` |
| Cell count | 6/6 |
| Every cell's `status` | `"failed"` |
| Every cell's `error_code` | `"ruleset_agent_unsupported"` |
| Every cell's `error_message` | `Ruleset 'bytefray-rules-2' does not support entrant metadata: A (python, Agent API 2), B (python, Agent API 2).` |
| `matches_played` | `0` |

The artifact says `finished`/`complete: true` while zero matches ran. Reproduced independently of
the research report's own reproduction, on this machine, before any code change.

### D.2 Full lifecycle trace

```text
request (CLI main())
  -> ruleset_id = resolve_omitted_ruleset_id(None, {"python"})   <- BUG: kind-only, hardcodes "python"
  -> always resolves to bytefray-rules-2 regardless of the roster's declared Agent API version
  -> validation (EvaluationService._validate): accepts (bytefray-rules-2 is a valid --ruleset choice;
     _validate never checks Agent-API/Ruleset compatibility, only kind == "python")
  -> scheduling (build_matrix): 6 cells built normally (3 placements x 2 orientations)
  -> cell execution (EvaluationService._execute_cell -> agent_test.test_agent -> NativeMatchService.run):
     rejects at the Ruleset-compatibility boundary before any tick executes
       -> RulesetAgentUnsupportedError -> caught as AgentTestError
       -> cell persisted with status="failed", error_code="ruleset_agent_unsupported"
  -> aggregate/finalization (EvaluationService.run): drift is None (no source drift) so the pre-fix
     code unconditionally wrote lifecycle_state="finished" -- literally `"aborted" if drift is not
     None else "finished"`, with no reference to cell status at all
  -> top-level state: "finished", complete: true (pre-fix: `len(cells) >= len(matrix)`, which only
     asks "was every cell attempted", never "did any cell succeed")
  -> CLI exit behavior: `return 1 if (result.failed_cells or result.corrupted_cells or
     result.drift_cells) else 0` -- this was ALREADY correct pre-fix (see D.4)
  -> history/show/compare interpretation: evaluation_history's v2_adapter already derived a
     "health" annotation (HealthCode.FINISHED_WITH_FAILED_CELLS) from real per-cell status at
     *read* time, but the underlying artifact's own lifecycle_state/complete fields never said so
```

### D.3 Root cause

`agent_evaluation.main()`'s omitted-`--ruleset` resolution called
`ruleset_policy.resolve_omitted_ruleset_id(None, {"python"})` — the **kind-only** resolver, called
with a **hardcoded literal** `{"python"}` runtime-kind set that carries no Agent API version. This
always resolves to `bytefray-rules-2`, which does not support Agent API v2. Every other product
entry point (`bytefray run`, `agents test`, `tournament`) had already been migrated to the
metadata-aware `resolve_omitted_ruleset_for_agents` (which reads each entrant's declared
`api_version`) when that resolver was introduced; `agents evaluate` was never migrated with its
siblings — exactly as the research report's §F.6 identified, confirmed here independently by
reading the CLI's `main()` before making any change.

### D.4 A finding the research report did not need to make: the CLI exit code was already correct

`main()`'s final line, unchanged by this phase, is:

```python
return 1 if (result.failed_cells or result.corrupted_cells or result.drift_cells) else 0
```

This already returns a failure exit code when any cell fails — confirmed in the reproduction above
(exit `1`) *before* any fix. The defect was specifically in the **persisted artifact's** own
`lifecycle_state`/`complete` fields, not in the CLI's return value. This phase adds a regression
test for the CLI exit-code behavior (`test_cli_exit_code_reflects_real_cell_outcome`) since none
existed, but no code change was needed there.

### D.5 Whether the defect generalizes beyond the API-v2 case — checked, not assumed

The governing task asked whether F.6 can also occur with: one failed cell among successful ones;
all cells failed; worker exceptions; invalid opponent execution; invalid Ruleset/runtime
combinations; resumed evaluations containing failed cells; interrupted evaluations; zero runnable
cells.

Read from `EvaluationService.run`'s source directly (not assumed): the pre-fix `lifecycle_state`
computation was `"aborted" if drift is not None else "finished"` — a **two-way** branch keyed
*only* on source drift, with **no reference to cell status at all**. This means the defect was
never actually specific to the F.6 API-v2 scenario; it was a property of the write path itself,
reachable by **any** cell failure under **any** methodology (v1, v2, v2-group, and now v4 alike):
a worker crash (confirmed by fixing the existing
`test_worker_crash_marks_cell_failed_and_others_continue_without_hanging`, which was asserting
`lifecycle_state == "finished"` for an artifact with a worker-crashed cell — i.e. the *existing
test suite already had a passing test that encoded the bug as correct behavior*), a partial
failure, a resumed evaluation whose failed cells are reconstructed from prior state without
re-execution, and an all-cells-failed evaluation are all covered by the fix and by this phase's
regression tests (§F below). "Zero runnable cells" is not structurally possible: `EvaluationService.
_validate` rejects an empty `opponent_ids`/`seeds` before any matrix is built.

### D.6 The fix: a generic evaluation-state integrity rule

Implemented as `agent_evaluation._resolved_lifecycle_state(cells, drift)`, the one function both
`EvaluationService.run`'s final write and `_write_state`'s `complete` computation now go through:

```text
LIFECYCLE_STATE_ABORTED               if drift is not None (unchanged)
LIFECYCLE_STATE_FINISHED_WITH_FAILURES if any cell.status in {"failed", "corrupted"}
LIFECYCLE_STATE_FINISHED               otherwise
```

`complete` is redefined as exactly `lifecycle_state == LIFECYCLE_STATE_FINISHED`. This is a
**write-side correctness fix, not a schema change**: no new JSON key, no identity-hash payload
change (`lifecycle_state`/`complete` were never part of `_evaluation_id`'s hash), and no historical
artifact is reinterpreted — a pre-fix artifact that already (incorrectly) says `"finished"` with
failed cells keeps reading exactly as it always has. `evaluation_history`'s existing health-code
derivation (`v2_adapter.py`, already computing `HealthCode.FINISHED_WITH_FAILED_CELLS`/
`FINISHED_WITH_CORRUPTED_CELLS` from real per-cell status) is widened to also treat the new
`"finished_with_failures"` state as "the scheduler is done" for that same scan, so both old and
new artifacts get correctly-derived health.

`EvaluationService.run`'s "M1" no-op-resume chronology check (preserve the original `finished_at`
when a resume does no new work) was gated on `prior.get("lifecycle_state") == "finished"`; widened
to `in TERMINAL_LIFECYCLE_STATES` (`{"finished", "finished_with_failures"}`) so a resume of an
already-failed evaluation still correctly preserves chronology instead of minting a spurious new
timestamp on every idle resume.

### D.7 Fixing the resolver

`main()`'s omitted-`--ruleset` resolution is reordered so `opponent_ids` is resolved before
`ruleset_id` (previously the reverse), and the resolver call itself is swapped:

```python
ruleset_id = resolve_omitted_ruleset_for_agents(None, roster_specs)
```

where `roster_specs` is the real, resolved candidate/baseline/opponent `AgentSpec` set. This is
the same resolver `run`/`agents test`/`tournament` already use. Per the accepted memory/standing
rule for this repository (never repoint an established command's default at a newer generation
merely because it exists): an Agent API **v1** roster still resolves to `bytefray-rules-2`,
unchanged — only the Agent API v2 case, which previously produced an artifact where every cell
failed, changes, and it changes because the roster's own already-declared metadata now drives
resolution, not because a default was silently repointed.

---

## E. Current evaluation architecture (reconstructed before implementing v4)

Read from `010c3f6b…` before any change, confirmed against a real running artifact (§D.1), not
assumed:

| Concern | Mechanism (pre-Phase-1) |
|---|---|
| `EvaluationRequest` | A frozen dataclass; `ruleset_id: str \| None` resolves via `resolve_evaluation_ruleset_id`; `is_v2_methodology` gates on `_V2_METHODOLOGY_RULESET_IDS = {bytefray-rules-2, bytefray-rules-3-alpha1, bytefray-rules-4-alpha1}` — a finite, explicit set, never a prefix check. Alpha2 was in none of the three schema tiers. |
| Schedule construction | `build_matrix`: `subject x opponent x seed x placement x orientation`, iteration order preserved exactly as requested. |
| Orientation | `physical_slots_for_orientation`: swaps which physical slot (always-first-acting `"A"` vs `"B"`) each *role* (subject/opponent) executes in; the *subject's own* `subject_start` stays fixed regardless of slot — a role-anchored design, not a seat-bound one (see §F.3 for why v4 needed a different rule here). |
| Seed derivation | `Config.seed` per cell (`STANDARD_V2_SEEDS = (1..5)` default for v2 methodology); per-entrant RNG via `python_runtime.derive_agent_seed(match_seed, slot, agent_id, api_version)`, unrelated to placement. |
| Arena placement/alignment | v1: `EVALUATION_ARENA_ALIGNMENT_MODE = "fixed"`, both starts `0`. v2: `EVALUATION_ARENA_ALIGNMENT_MODE_V2_STANDARD`, three mechanically-derived `standard_placements()` (`opposed`/`quarter`/`opposed-shifted`), imposed as **explicit starts**, so `placement.resolve_direct_match_starts` (the seam `bytefray run` uses) never fires for evaluation cells. |
| Match construction | `agent_test.test_agent` → `_test_agent` → `NativeMatchService.run(MatchRequest)`, the identical boundary `bytefray agents test` uses. |
| Worker partitioning | `EvaluationService._run_pending_parallel`; `_execute_cell` is a pure function of its own arguments (no coordinator-state reads), a v1.6 Phase 2 invariant this phase preserves. |
| Resume | `_resolve_from_state` reconstructs a prior cell from its persisted `result.json`, cross-checked against a freshly recomputed `_expected_cell_match_id`. |
| Artifact persistence | `EvaluationService._write_state`, one atomic JSON write per checkpoint. |
| Schema/version | `SCHEMA_VERSION`/`IDENTITY_VERSION` = 4 (v1); `SCHEMA_VERSION_V2`/`IDENTITY_VERSION_V2` = 5 (v2 1v1); `SCHEMA_VERSION_V2_GROUP`/`IDENTITY_VERSION_V2_GROUP` = 6 (group). |
| Evaluation ID / methodology identity | `_evaluation_id`: a `stable_id("evaluation-v2", payload)` hash over identities, seeds, ticks, effective conditions, `rules_compatibility_id`, `arena_alignment_mode`, and (v2 only) the *resolved placement set itself*. |
| `rules_compatibility_id` | The request's resolved Ruleset — a **gameplay** identity, never an evaluation-methodology identity. |
| `arena_alignment_mode` | The methodology discriminator — a sibling top-level field, never folded into `effective_conditions`. |
| History read/show | `evaluation_history.discovery.adapt_any` dispatches on `(schema, schema_version)`; `v1_adapter.py` for the (distinct, truly historical) schema_version 1; `v2_adapter.py` for versions 2–6 (a naming artifact: this adapter, despite its name, handles what the engine calls both "v1 methodology" schema 4 and "v2 methodology" schemas 5/6). |
| Deep verification | `evaluation_history.verification.verify_cell`/`verify_summary`: schema-agnostic, working entirely off `AdaptedCell`'s generic fields (orientation, seat assignment, seed, result/match id, identity). |
| Comparison | `evaluation_history.comparison._condition_key`: fails closed on any `UNKNOWN` confidence; keys on the full tuple including `arena_alignment_id`, `rules_id`, `placement.value`. |
| Agent Designer evaluation UI | `EVALUATION_RULESET_OPTIONS` (a separate, explicit tuple from `DESIGNER_RULESET_OPTIONS`) deliberately excluded alpha2, with a comment stating the engine rejected it. |
| CLI `agents evaluate` | `--ruleset` choices: `{bytefray-rules-1, bytefray-rules-2, bytefray-rules-4-alpha1}`. |
| Default Ruleset resolution | The F.6 defect (§D). |

---

## F. What was implemented for the stable v4 methodology

### F.1 Placement — no second placement algorithm

`build_matrix`, for a v4-methodology request, resolves one placement sample per seed via a new
single-call wrapper:

```python
def resolve_v4_seed_geometry(rules_compatibility_id, arena_size, seed) -> tuple[int, int]:
    starts = resolve_direct_match_starts(
        ruleset_id=rules_compatibility_id, arena_size=arena_size,
        entrant_count=2, supplied_starts=[None, None], seed=seed,
    )
    return starts[0], starts[1]
```

This is `placement.resolve_direct_match_starts` — bit-for-bit the same call `bytefray run` makes
— called with both starts omitted so `bytefray-rules-4-alpha2`'s own `core_placement="seeded"`
policy resolves them via `seeded_seat_starts`. `build_matrix` and `EvaluationService._evaluation_id`
both call this **one** function, so the persisted schedule and the identity hash can never drift
from each other or from production placement.

**Cross-validated against the research report's own pinned vectors** (§C.1): seed 3 at arena 512
resolves to `(495, 387)`, confirmed both by direct unit test
(`test_pinned_seed_vectors_match_the_research_report`) and by inspecting a real evaluation
artifact's cells.

### F.2 Eight deterministic placement samples

`STANDARD_V4_SEEDS = (1, 2, 3, 4, 5, 6, 7, 8)`, used as the default seed set only when the
resolved methodology is v4-seeded and no explicit `--seeds`/`--seed-range`/preset is given —
mirroring exactly how `STANDARD_V2_SEEDS` is used today. Not exposed as a separate `--k` knob.

### F.3 Orientation pairing — the one place v4's design genuinely differs from v2's

The pre-existing orientation mechanism (`physical_slots_for_orientation` + `_execute_cell`'s
role-anchored start assignment) keeps the **subject's own** `subject_start` fixed regardless of
which physical slot it executes in for a given orientation. That is correct for v2's fixed
placements (the subject "owns" address 0 in `opposed`, regardless of scheduling order), but it is
**not** what the research report's accepted design specifies for v4: "slot A always gets
`seeded_seat_starts(...)[0]`, and orientation decides who sits in slot A" (§H.1 item 4) — i.e. the
address must travel with the **physical seat**, and the *occupant* swaps, not the reverse.

`build_matrix` implements this precisely for v4-methodology cells only: both orientation cells of
one seed share the identical `resolve_v4_seed_geometry` result; the `opponent_first` cell's
`subject_start`/`opponent_start` are the *swap* of the `candidate_first` cell's. Verified directly:

```python
assert candidate_first.subject_start == opponent_first.opponent_start
assert candidate_first.opponent_start == opponent_first.subject_start
```

Every other methodology's existing role-anchored behavior is completely unaffected — the new
per-orientation swap logic in `build_matrix` is gated on `resolved_is_v4`, and for every other
methodology the swap is a no-op (`cell_subject_start == subject_start` unconditionally).

### F.4 Arena pinned to 512, fail-closed on an incompatible override

`STANDARD_V4_ARENA_SIZE = 512`. `EvaluationRequest.resolved_arena_size` — "the single authority
for arena size across matrix generation, identity, execution, and display", per its own existing
docstring — now returns the pin when `arena_size is None` and `is_v4_methodology`, instead of
falling through to the inherited `Config().arena_size` (4096) every other methodology still uses.
`EvaluationService._validate` rejects an explicit `--arena-size` that disagrees with the pin under
v4 methodology with a clear `EvaluationConfigurationError`, rather than silently producing an
artifact that still claims the standard methodology at a non-standard arena.

**A bug found and fixed during this same work**: `resolved_arena_size` alone was not sufficient.
Five call sites inside `EvaluationService` (`_effective_conditions`, the serial and parallel
`_execute_cell` dispatch paths, and `_resolve_from_state`'s resumed-cell `_expected_cell_match_id`
reconstruction) read the **raw** `request.arena_size` (`None` when omitted) directly, each with its
own independent `Config().arena_size` fallback baked further downstream — meaning a v4 evaluation
with omitted `--arena-size` would have computed its *placements* assuming 512 but *actually
executed its matches* at 4096, a genuine correctness defect this phase introduced and caught
before it shipped (manual reproduction: `effective_conditions.arena_size` read back as `4096` from
a real run; fixed; re-run showed `512`). All five sites now go through `resolved_arena_size`; a
dedicated regression test (`test_resume_of_a_successful_v4_evaluation_reconstructs_cleanly`) covers
the resume path specifically, since the existing all-cells-failed resume test's cells return early
in `_resolve_from_state` and never reach the arena-size-dependent reconstruction at all.

### F.5 Schema/identity version 7

`SCHEMA_VERSION_V4`/`IDENTITY_VERSION_V4 = 7`, a third additive recipe alongside 4/5/6 — no
historical `bytefray-rules-4-alpha2` evaluation artifact exists to preserve compatibility with,
since evaluation rejected this Ruleset entirely before this phase. New top-level
`arena_alignment_mode` value `EVALUATION_ARENA_ALIGNMENT_MODE_V4_SEEDED =
"ruleset_v4_seeded_placements"`, never reused. Per-cell `placement_id = f"seeded-{seed}"`,
`subject_start`/`opponent_start` resolved (§F.1/F.3). `_evaluation_id`'s payload gains, for
v4-methodology requests only, a `"placements"` key carrying the resolved sample set (seed +
resolved geometry per seed) — the exact same slot v2's payload uses for its own resolved placement
set, so two different v4 sample sets can never collide on `evaluation_id`.

### F.6 CLI and Designer integration

`--ruleset` gains `bytefray-rules-4-alpha2` as a choice; the seed default gains a `resolved_is_v4`
branch selecting `STANDARD_V4_SEEDS`; the omitted-Ruleset resolution fix (§D.7) is what actually
routes an Agent API v2 roster here by default. `bytefray-rules-4-alpha1` is completely unaffected
— confirmed by a dedicated regression test
(`test_explicit_alpha1_ruleset_keeps_its_historical_fixed_placement_methodology`) asserting its
schema stays 5, its `arena_alignment_mode` stays `ruleset_v2_standard_placements`, and its
placements stay the three historical fixed labels.

`app/services/ruleset_options.EVALUATION_RULESET_OPTIONS` gains `RULESET_V4_ALPHA2_OPTION`,
ordered *before* alpha1 to mirror `ruleset_policy.OMITTED_RULESET_CANDIDATES`'s own
product-preference order — an Agent API v2 Designer selection now defaults to alpha2 via the
existing, unmodified `best_designer_ruleset_for_agents` mechanism. No dialog/workflow code changes
were needed: `EvaluationDialog`'s existing `sync_ruleset_choices_for_metadata` already narrows/
repairs the selector from real roster metadata, and arena size is not a Designer evaluation
control at all (confirmed by reading `app/views/evaluation.py` and
`app/services/designer_workflows.py` in full) — a Designer-launched evaluation already omits
`--arena-size` entirely, so it lands on the pinned 512 default with no risk of an incompatible
override from that surface. Post-run methodology disclosure (`methodology_lines`/
`effective_condition_lines`) is already shared with the CLI, so the results/history views
correctly show `"ruleset_v4_seeded_placements"` and `"arena size: 512 (non-default)"` for a v4
evaluation with no further change — confirmed against a real artifact via `bytefray agents
evaluations show --verify`.

### F.7 Deep verification

`AdaptedCell` gains `subject_start`/`opponent_start` `ConfidenceValue` fields (previously only
`placement_id` was surfaced onto the adapted model). `verification.verify_cell` gains an
`expected_placement` check: `verify_summary` reconstructs the expected `(subject_start,
opponent_start)` from the evaluation's own recorded Ruleset/arena size and each cell's own seed via
`resolve_v4_seed_geometry`, accounting for orientation exactly as `build_matrix` assigns it, and
fails closed if the recorded starts disagree. This directly answers the research report's own
framing: "the artifact must be verifiable, not merely self-consistent" — a v4 cell's
`condition_fingerprint` rehash (§F.8) only proves internal self-consistency (the fingerprint
matches the cell's own claimed starts); this new check proves those starts are the geometry the
seed actually resolves to. Manually verified against a real artifact: 16/16 cells verify clean; a
deliberately tampered `subject_start` is caught with an exact expected-vs-actual diagnostic.

### F.8 `evaluation_history` schema-7 support

`v2_adapter.SUPPORTED_V2_VERSIONS` gains `7`; `_ORIENTATION_AWARE_VERSIONS`/
`_PLACEMENT_AWARE_VERSIONS` likewise, since schema 7 reuses the identical `orientation`/
`placement_id`/`subject_start`/`opponent_start` wire keys schema 5 introduced (only their
*meaning* changes). The self-consistency `evaluation_id` rehash gains a dedicated
`identity_version == IDENTITY_VERSION_V4` branch (checked *before* the existing `>= 5` fallback,
since 7 ≥ 5 would otherwise incorrectly match it and rehash with the v2 standard-placement
formula) that reconstructs the v4 sample set from the artifact's own recorded arena size and seeds
— never `Config()`'s default, unlike the pre-existing v2 rehash helper, which would have produced
false `PLANNED_IDENTITY_INCONSISTENT` reports for every real v4 artifact had this distinction been
missed. `agent_evaluation.read_evaluation`'s own independent supported-version tuple (used by the
CLI/Designer's dry-run-adjacent presentation code, distinct from `evaluation_history`'s adapters)
also gains `SCHEMA_VERSION_V4`.

### F.9 Comparison — confirmed to need no change

The research report's own conclusion (§H.2 item 8) is that `comparison.py` needs no code change.
Confirmed here by direct code reading (`_condition_key` already includes `arena_alignment_id`/
`rules_id`/`placement.value` in its alignment-key tuple) and by six new tests exercising `align()`
against hand-built v4-shaped `EvaluationSummary` fixtures (this file's own established synthetic-
fixture testing convention, since `align` is a pure function over already-adapted data): two
identical-conditions v4 evaluations align and produce an ordinary verdict; a v4-seeded cell never
aligns with a v2-standard-placement cell even at the same seed/orientation; alpha2 never aligns
with alpha1; two v4 evaluations at different sample counts align on their shared prefix only; a
historical v2 artifact's recorded labels are read exactly as recorded, never relabeled toward the
v4 spelling. No line of `comparison.py` was touched.

### F.10 Schedule cardinality and runtime

Verified directly against a real evaluation (2 opponents, `STANDARD_V4_SEEDS`, both orientations):
`len(result.cells) == 2 * 8 * 2 == 32`, matching the research report's `N x 8 x 2 = 16N` formula
exactly (§13 of the governing task). Compared with the historical default v2 methodology's `N x 5
x 3 x 2 = 30N`, this is `16/30 ≈ 0.53x` the match count — the research report's own headline
figure, now confirmed against the actual production schedule arithmetic rather than assumed.
Per-match cost is additionally lower at the pinned arena (512 vs. the historical 4096 inherited
default), consistent with — not independently re-measured by — the research report's own median-
tick-count finding.

### F.11 Determinism and worker invariance

`test_worker_count_does_not_change_schedule_or_outcome` runs an identical v4 request twice — once
serial (`workers=1`), once with `workers=4` — and asserts the two runs produce a byte-for-byte
identical canonical cell set (opponent, seed, orientation, placement id, both starts, status,
outcome, scores) *and* the identical `evaluation_id`. `resolve_v4_seed_geometry`'s own placement
draw (`placement._placement_draw`) is a pure SHA-256 counter stream over an ASCII payload — no
`random` module, no `PYTHONHASHSEED` dependence, no filesystem-ordering dependence — the same
cross-platform-pinned mechanism `bytefray-rules-4-alpha2`'s eleven release-blocking placement
vectors already establish for ordinary matches; this phase adds no second RNG system.

---

## G. Historical compatibility — verified, not merely asserted

* `bytefray-rules-4-alpha1` evaluation: unchanged behavior, unchanged schema (5), unchanged
  `arena_alignment_mode` (`ruleset_v2_standard_placements`), unchanged three fixed placement
  labels — regression-tested (§F.6).
* v1/Ruleset-v2/group evaluation: unaffected by any change in this phase; the full repository
  suite (§H) exercises the pre-existing test coverage for all three unchanged.
* Historical fixed alignment is never relabeled as v4-seeded placement, and vice versa —
  regression-tested directly (`test_historical_v2_evaluation_is_never_reinterpreted_as_v4_seeded`).
* No historical evaluation file was rewritten, migrated, or re-blessed.

---

## H. Qualification

All commands run on Windows 11 Pro 10.0.26120, Python 3.13.14, `.venv/` at the repository root,
against the final commit `71da24c` (the qualification test/static-check run itself was performed
at `21bd0c4`, one commit prior to a pure-documentation addition — see below).

### H.1 Qualification integrity protocol

Per this repository's standing requirement that the exact code qualified be the exact code
preserved in Git: `HEAD`, `git status --short`, and SHA-256 digests of every file this phase
modified were recorded immediately before the final full-suite/GUI-suite run and recomputed
immediately after.

```text
HEAD before:  21bd0c4361385e5db65e899d4117f217a6d038cd
HEAD after:   21bd0c4361385e5db65e899d4117f217a6d038cd   (unchanged)
git status:   clean, both times
SHA-256 digests of the 9 phase-critical source/test/doc files: identical, all 9, both times
```

The doc-only commit `71da24c` (carrying the research report onto this branch, §C) was made
*after* this qualification run, changes exactly one new file, and cannot affect test/static-check
results — reconfirmed independently afterward: `ruff check .` and `mypy engine/src/battle_engine`
both still clean at `71da24c`.

### H.2 Static checks

| Check | Command | Result |
|---|---|---|
| Ruff | `ruff check .` | **All checks passed** |
| Engine mypy | `mypy engine/src/battle_engine` | **Success, 101 source files** |
| Client mypy | `mypy client/src/battle_client` | **Success, 15 source files** |
| Whitespace | `git diff --check 010c3f6..HEAD` | clean |

### H.3 Focused evaluation tests

`pytest engine/tests/ -k "evaluation"` (repeated at multiple points through implementation, most
recently against the final commit): **all passing**, no failures.

### H.4 Full repository suite

```text
pytest --basetemp=.pytest-tmp/... --junitxml=...
```

**2893 collected, 2879 passed, 14 skipped, 0 failed, 0 errors**, in 304.8s.

Test-count reconciliation against the pre-RC research baseline (§L.6 of the research report: 2847
passed / 14 skipped): **+32**, exactly the count of new tests this phase added (27 in the new
`test_agent_evaluation_v4.py` + 5 new v4-specific tests appended to
`test_evaluation_history_comparison.py`). Skip count unchanged (14). No test was deleted; two
pre-existing tests were updated because their assertions encoded the F.6 defect as correct
behavior (`test_worker_crash_marks_cell_failed_and_others_continue_without_hanging`, previously
asserting `lifecycle_state == "finished"` for a worker-crashed cell) or needed a mechanical
`--ruleset` choices-string update (`test_evaluate_cli_exposes_all_product_ruleset_choices`).

One test flaked once during iteration (`test_resume_after_coordinator_interruption_matches_
uninterrupted_reference`, a `PermissionError` from Windows `os.replace` under a temp-directory
file-lock race) and passed cleanly on immediate isolated re-run and on every subsequent full-suite
run including the final qualification run — consistent with this repository's documented history
of transient Windows filesystem contention in this exact test, not a regression from this phase's
changes.

### H.5 Designer GUI suite

```text
pytest -m gui tests/ --junitxml=...
```

**251 collected, 251 passed, 0 skipped, 0 failed, 0 errors**, in 35.6s.

Reconciliation against the pre-RC baseline (250): **+1**, the one new default-selection test
(`test_evaluation_defaults_to_stable_v4_for_api_v2_roster`); the two other GUI test bodies this
phase modified changed their existing assertions in place rather than adding new test functions.

### H.6 Not performed, and not claimed

No Linux qualification was performed — everything in this report ran on Windows only. No
package/installer qualification was performed or is claimed. Cross-platform reproduction of the
new methodology's placement/identity vectors on Linux (mirroring the discipline `test_v4_alpha2_
placement.py`'s eleven pinned vectors already received) remains RC-qualification work, per the
governing task's own §7 item 6 and the research report's §J item 6.

---

## I. Files added/modified

```text
engine/src/battle_engine/agent_evaluation.py                         (core domain layer)
engine/src/battle_engine/evaluation_history/models.py                (+subject_start/opponent_start)
engine/src/battle_engine/evaluation_history/v2_adapter.py            (schema 7 + lifecycle widening)
engine/src/battle_engine/evaluation_history/verification.py          (v4 placement reconstruction check)
app/services/ruleset_options.py                                      (Designer evaluation option list)
engine/tests/test_agent_evaluation_parallel.py                       (F.6 assertion fix)
engine/tests/test_agent_evaluation_v2.py                             (--ruleset choices string fix)
engine/tests/test_agent_evaluation_v4.py                             (new, 27 tests)
engine/tests/test_evaluation_history_comparison.py                   (+5 v4 comparison tests)
tests/test_designer_ruleset_compatibility.py                         (GUI test updates + 1 new)
docs/COMPATIBILITY.md                                                (v4 methodology + F.6 sections)
CHANGELOG.md                                                         (Unreleased entry)
docs/research/v4/V4_PRE_RC_GAMEPLAY_EVALUATION_RESEARCH.md            (carried forward, byte-identical)
docs/research/v4/V4_RC1_PHASE1_EVALUATION_METHODOLOGY.md              (this report)
```

---

## J. Commits

```text
ef7ce5f fix(v4): evaluation-state integrity invariant + stable v4 seeded-placement methodology
3d13624 feat(v4): deep verification for the seeded-placement methodology
4cef366 feat(designer): offer the stable v4 evaluation methodology
c9d7c03 test(v4): comparison-gate coverage for the seeded-placement methodology
e6315e3 test(v4): comprehensive coverage for schema 7 and the F.6 remediation
a49abc4 docs(v4): compatibility and changelog entries for RC1 Phase 1
21bd0c4 test(v4): regression test for the resume arena-size mismatch
71da24c docs(v4): carry the accepted pre-RC research report onto the RC branch
```

Not merged to `main`. Not tagged. Not published.

---

## K. Semantics explicitly confirmed unchanged

* `bytefray-rules-4-alpha1` / `bytefray-rules-4-alpha2` gameplay semantics: core size, Q=8, reach
  legality/cost, MOVE, READ/WRITE reach, enemy-anchor observation, seeded Alpha2 placement
  algorithm and minimum separation, round-robin process selection, K=2 scheduling, disruption,
  quota allocation/redistribution, scoring, termination — none of `python_runtime.py`,
  `ruleset_policy.py`'s `RulesetPolicy` definitions, `scheduler.py`, or `process_runtime.py` was
  touched by this phase.
* Agent API v2: no new observation field, action kind, or declaration rule.
* `battle2.replay` schema 4: untouched.
* `bytefray-rules-4` (the permanent stable identity): **not introduced**. Every identifier used
  throughout this phase is the existing `bytefray-rules-4-alpha2`.

---

## L. Limitations

1. **No Linux qualification.** Everything in this report ran on Windows 11, Python 3.13.14.
   Cross-platform reproduction of the new placement/identity vectors is deferred to RC
   qualification, per the governing task's own scope note.
2. **No Windows package/installer qualification.** Not performed, not claimed.
3. **The v4-seeded methodology's schedule-cardinality/worker-invariance evidence uses a small
   roster** (2 opponents, minimal synthetic Agent API v2 agents) — sufficient to prove the
   mechanism is correctly wired and deterministic, but not a large-scale ecology characterization;
   that is what the accepted research corpus (9,638 matches) already supplies, and this phase
   deliberately does not repeat it.
4. **Group-mode v4 evaluation was not implemented and remains rejected.** `agents evaluate
   --group` continues to require `--ruleset bytefray-rules-2`, unaffected by this phase — v4-seeded
   group evaluation is out of scope per the governing task, and `EvaluationService._validate`'s
   existing group/methodology check already fails closed on the combination.
5. **`docs/specs/agent_evaluation.md`, the original pre-implementation design spec, was not
   rewritten.** Consistent with this repository's convention that specs are pre-implementation
   planning documents and durable evolution is recorded in `COMPATIBILITY.md`/`CHANGELOG.md`/phase
   reports instead — the same precedent every prior evaluation-methodology phase (Beta2 Phase 1/2)
   already followed.

None of these limitations contradicts the accepted stable evaluation contract; each is either
explicitly out of this phase's scope or explicitly deferred to RC qualification by the governing
task itself.

---

## M. Final decision

```text
PHASE 1 QUALIFIED — READY FOR RC PATH PHASE 2
```
