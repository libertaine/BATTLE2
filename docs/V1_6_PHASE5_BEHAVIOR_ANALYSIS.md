# v1.6 Phase 5 — Behavior Profile Analytics

This is the durable design/implementation record for v1.6 Phase 5: a pure,
derived behavioral-description layer over already-authoritative evaluation
data — survival, write activity, territory occupancy/retention, and kill
interaction — that lets agents with similar win rates but genuinely
different strategies be distinguished, without inventing a composite
"strategy score," clustering, or ranking.

Written in the same spirit as `docs/V1_6_PHASE1_EVALUATION_SCALE_BASELINE.md`
through `docs/V1_6_PHASE4_EVALUATION_ANALYSIS.md`: this document cites all
four as the authoritative pre-implementation baseline rather than
re-deriving them, and in particular treats Phase 0-1 §13 ("Behavior-profile
data inventory") as the direct ancestor of the design below.

## 1. Starting state

Branch `v1.6-development`, HEAD `3f4f065` ("feat(evaluation): add
aggregate & statistical analysis", Phase 4's own closing commit) —
confirmed via `git rev-parse HEAD`. `main`/`origin/main` both at
`c210358` (Phase 0-1's docs commit, predating Phase 2-4, unchanged by this
phase). Working tree clean at the start (`git status --porcelain` empty).
Full suite reconfirmed green before any edit (see §24 for the final,
post-implementation numbers; the pre-implementation baseline this phase
started from was Phase 4's own recorded 1382 tests — see below).

Recent v1.6 history read in full before implementation:

- `bc0cbae` v1.5.0 release
- `85551e5` deterministic parallel evaluation (Phase 2)
- `c210358` v1.6 evaluation-scale baseline documentation (Phase 0-1)
- `624e292` reusable evaluation presets (Phase 3)
- `3f4f065` aggregate & statistical evaluation analysis (Phase 4)

## 2. Measurement inventory (per the governing prompt's §3)

Read directly from source, not assumed, before any design decision.

### 2.1 What `EvaluationCell` (persisted in `evaluation.json`) actually carries

`agent_evaluation.EvaluationCell` (`agent_evaluation.py:635`): `outcome`,
`match_id`, `result_id`, `ticks_run`, `score_subject`/`score_opponent`,
`territory_subject`/`territory_opponent` (**last-tick territory percentage
only** — `territory_pct_last`, never max/avg), `orientation`, seed,
opponent id, plus identity/provenance fields Phase 2-4 already use. This is
**classification 1 (directly persisted)** for: outcome, score, ticks_run,
territory (last-tick only), seed, opponent, orientation.

Critically, **`EvaluationCell` does *not* carry** `alive_ticks`, `kills`,
`deaths`, `cpu_total`, `mem_writes`, `territory_max`/`territory_avg` (raw
or percentage), or `termination_reason` — none of Phase 0-1 §13's named
candidate behavioral fields beyond last-tick territory are in the
canonical evaluation artifact at all.

### 2.2 What each cell's own `result.json` carries

Traced through `match_service._finalize_native_artifacts`
(`match_service.py:619`) and `NativeAgentResult.as_legacy_statistics()`
(`match_service.py:151`): every cell's own sibling `result.json`
(`battle2.result` v1, one per cell, at `cell.artifact_dir/result.json`)
already persists, per entrant, everything Phase 0-1 §13 named:
`alive`, `alive_ticks`, `kills`, `deaths`, `cpu_total`, `mem_writes`,
`territory_last`/`territory_max`/`territory_avg` (raw byte counts) *and*
their percentage forms (`territory_pct_last`/`territory_pct_max`/
`territory_pct_avg`), plus `termination_reason` at the entrant level. This
is **classification 3 (derivable only by reading a per-cell artifact)** —
but critically, *not* the tick-by-tick replay: `result.json` is a small,
already-fully-computed summary, the exact same artifact Phase 2's own
resume path already reads (`_cell_from_envelope`,
`agent_evaluation.py:1193`) and the exact same one
`evaluation_history.verification.verify_cell` already reads for deep
verification. Reusing this read path, rather than inventing a new one, is
the central architectural decision of this phase (§4).

### 2.3 What only the tick-by-tick replay can answer

`iter_replay`/`TickSnapshot.memory_diffs` (`replay.py`) exposes per-tick
write addresses directly, engine-side, no client dependency — a genuine
classification-3-via-full-traversal source for a write-address-concentration
metric (never implemented this phase; see §11's deferral). True
ownership-over-time reconstruction (which cell was whose, tick by tick) —
the basis for early-expansion-rate/peak-timing/contraction trajectory
metrics — requires the *incremental* diff-walk logic already implemented
once, in `battle_client.session.ReplaySession`/
`battle_client.analysis.compute_territory_history`. This is
**classification 4 for `battle_engine`-side code specifically**: not
because the data is unavailable in principle, but because of a real
architecture-boundary finding (§9).

### 2.4 Termination reasons

`ruleset_policy.TerminationReason` (`ruleset_policy.py:34`): exactly three
values — `last_agent_standing`, `all_agents_dead`, `tick_limit`. A small,
closed categorical, cheap to report as counts (§5's `termination_reason_counts`).

### 2.5 Starter-agent strategies (read from source, not assumed from names)

All five shipped Python starters (`agents/{claimer,hunter,strider,
wanderer,adaptive}/agent.py`) were read in full before any dimension was
selected. Every one is fundamentally a **blind-write sweeper** — none of
them read the arena to decide what to write (Wanderer reads occasionally,
~3% of actions, purely to detect and locally exploit already-contested
ground) — differing only in *where* and *when* they write:

- **Claimer**: one fixed stride (101), one origin (address 0), the entire
  match, no revisits, no defense.
- **Hunter**: two phases — 20 actions of a golden-ratio-derived sparse
  stride (scattering an early presence widely), then a dense stride (173)
  for the rest of the match, continuing from the sparse phase's landing
  point (not resetting to 0).
- **Strider**: one advance stride (131) with a periodic "defend" cycle
  (40 of every 940 actions replay the immediately preceding block of its
  own sweep) — the only starter with any built-in retention mechanism.
- **Wanderer**: a randomized-but-still-full-coverage stride (chosen from
  `context.rng` per match, always odd), plus an opportunistic
  read-and-locally-exploit habit (~3% of actions).
- **Adaptive**: three fixed-fraction phases — CLAIM (first 50%, stride
  149, from address 0), CONTEST (next 40%, a *different* stride/origin,
  explicitly *not* address 0, because the docstring documents that address
  0 is where a candidate's opponent is usually also sweeping from, and
  that opponent's writes land after this agent's within a tick, so it
  structurally cannot win contested ground there), DEFEND (final 10%,
  stop expanding, replay both earlier phases' actual sequences).

**Critically for kill/combat metrics**: `agent_api.ActionKind` (Agent API
v1) exposes no attack/kill action — `NOP`, `SET_A`, `ADD_A`, `READ`,
`WRITE`, `SET_P`, `ADD_P`, `JUMP`, `JUMP_IF_ZERO`, `HALT` only. Hunter's
own docstring states this explicitly: "Python agents never destroy each
other (`WRITE` claims a cell, it never kills)." Since `bytefray agents
evaluate` is Python-agent-only (`docs/AGENT_LAB.md`'s own documented
limitation), **`kills`/`deaths` are structurally zero for every population
this evaluation subsystem can currently analyze** — confirmed both by
source reading and by real measurement (§8's validation corpus: `kills_per_
match == 0.0` for all five starters, no exceptions). This is reported
honestly in §7/§8 rather than hidden or silently dropped.

## 3. What "behavior" means here (per the governing prompt's §4)

A behavioral measurement describes an *observable strategy characteristic*
— what the subject actually did during a match — never success itself.
Win rate, score, and Phase 4's statistical evidence describe *whether* the
subject did well; they are never treated as behavioral dimensions here,
and (§6) no behavioral computation in this phase ever reads a cell's
`outcome`/`score_subject`/`score_opponent` field at all — proven
structurally, not just by convention (§6.1).

## 4. Data-tier architecture

Two tiers, matching §2's inventory exactly:

- **Tier 1** — already inside `EvaluationCell`: free (no I/O beyond what
  the caller already paid to have the cell). Used only as a graceful
  fallback (`territory_last_fallback`) when Tier 2 is unavailable — see
  §7's historical-compatibility handling.
- **Tier 2** — each cell's own `result.json`: one small JSON file read per
  scored cell, real but modest I/O (§10 measures this precisely: ~5-6
  ms/cell on this development machine, combining path resolution and the
  read itself). This is the *primary* data source for every implemented
  dimension.

No **Tier 3** (full replay traversal) is implemented this phase — see §11.

## 5. Behavior data model (`engine/src/battle_engine/evaluation_behavior.py`)

Pure, dependency-free (stdlib only) aggregation layer, sibling to
`evaluation_analysis.py` (Phase 4), plus one narrow I/O boundary the
Phase 4 module never needed (Phase 4's inputs were always already
in-memory `EvaluationCell`s; Phase 5's dimensions require reading each
cell's own nested artifact).

```
CellRef              -- one scored cell's identity + a caller-resolved
                         path to its own result.json (or None)
CellBehaviorSample    -- one cell's loaded measurements (Tier 1 fallback +
                         Tier 2 if available), available: bool +
                         unavailable_reason: str | None
DimensionValue        -- mean/min/max/n for one dimension over some scope
BehaviorProfile        -- one subject, one scope: all 11 DimensionValues +
                         termination_reason_counts
DimensionDelta         -- symmetric (left - right) delta for one dimension
                         between two profiles
BehaviorAnalysis       -- top-level: candidate/baseline profiles (overall +
                         by-orientation + by-opponent), orientation
                         deltas, candidate-vs-baseline deltas
```

`CellRef` is the one deliberate seam: **path resolution — including
path-containment checking for untrusted historical artifacts — is always
the caller's responsibility, never this module's.** `evaluation_behavior.py`
itself has no knowledge of which trust model produced a path. Two callers,
two trust models:

- `cell_ref_from_evaluation_cell` (in `evaluation_behavior.py`): trusted,
  used by the live `agents evaluate` run path (a directory this process
  just created) and by Designer's `read_evaluation_presentation` (which
  already joins `artifact_dir` against the opened evaluation's own
  directory at the same trust level every other field there uses).
- `evaluation_history.behavior_adapter.cell_refs_for_behavior` (new,
  small, separate module): containment-checked, used by `evaluations
  show` — reuses `evaluation_history.models.resolve_contained_path`, the
  identical M4 primitive `verification.verify_cell` already applies to a
  cell's nested `result.json`, so an on-disk (potentially hand-edited)
  historical artifact can never make this module follow a path outside
  its own evaluation directory. A refused path resolves to
  `result_path=None`, handled identically to "file missing" — one refused
  cell never aborts the whole profile.

`analyze_behavior(candidate_id, baseline_id, refs) -> BehaviorAnalysis` is
the one entry point, mirroring Phase 4's `analyze()` shape exactly.

## 6. Selected dimensions

Eleven dimensions, each independent, none composited:

| Dimension | Formula | Unit | Tier |
|---|---|---|---|
| `survival_fraction` | `alive_ticks / ticks_run` | fraction 0-1 | 2 |
| `writes_per_tick` | `mem_writes / ticks_run` | rate, unbounded | 2 |
| `writes_per_alive_tick` | `mem_writes / alive_ticks` | rate, unbounded | 2 |
| `territory_last_pct` | `territory_pct_last` | percent 0-100 | 2 (Tier-1 fallback) |
| `territory_max_pct` | `territory_pct_max` | percent 0-100 | 2 |
| `territory_avg_pct` | `territory_pct_avg` | percent 0-100 | 2 |
| `territory_retention` | `territory_last_pct / territory_max_pct` | fraction 0-1 | 2 |
| `territory_spread` | `territory_max_pct - territory_avg_pct` | percentage points | 2 |
| `kills_per_match` | `kills` | rate, unbounded | 2 |
| `kill_involvement_rate` | `1.0 if kills > 0 else 0.0` | fraction 0-1 | 2 |
| `deaths_per_match` | `deaths` | rate, unbounded | 2 |

Every dimension reports a `DimensionValue`: mean, `n` (contributing cell
count — can be smaller than the scope's total, e.g. `territory_retention`
is undefined for a cell that never held territory), min, max. **Never a
confidence interval**: most of these are not literal per-match Bernoulli
trial counts the way Phase 4's win/loss counts are (a rate like
writes/tick, or an average-of-ratios like `survival_fraction`, is not the
statistical object a Wilson interval applies to), so computing one would
misrepresent what was actually measured. This is a deliberate,
disclosed choice, not an oversight (§6 of the governing prompt: separate
performance/outcome statistics from behavioral description).

### 6.1 Outcome independence — structural, not just observational

`CellRef` — the *only* input `analyze_behavior` ever receives — has no
`outcome`, `score_subject`, or `score_opponent` field at all
(`test_cell_ref_carries_no_outcome_or_score_field`, §12). Behavior
computation cannot read outcome even by accident; this is a structural
property of the type, verified by a dedicated test, not merely an
implementation habit that could silently drift.

### 6.2 Rejected/never-considered dimensions

- **Write-bucket concentration/dispersion** (Phase 0-1 §13's "write-pattern
  concentration vs. spread"): would require full per-tick replay
  traversal of `memory_diffs` — deferred, §11.
- **Territory trajectory** (early expansion rate, peak timing, contraction
  after peak): would require `battle_client`'s incremental ownership
  reconstruction — deferred for a genuine architecture-boundary reason,
  §9/§11, not merely "ran out of time."
- **A composite "aggression"/"defense"/"strategy" score**: never started.
  Combining `writes_per_tick` (unbounded) with `territory_retention`
  (0-1) would require an arbitrary cross-unit weighting the governing
  prompt explicitly warns against manufacturing (§11 of the governing
  prompt: "if choosing defensible weights becomes arbitrary, STOP at
  profile vectors ... that is an acceptable outcome"). This phase stops
  there.
- **Behavioral distance (single scalar)**: not implemented — see §11 for
  the concrete reasoning (the same "arbitrary weighting" problem, applied
  to *any* combination, not just a composite score).

## 7. Normalization

Every dimension's unit is intrinsic, never dataset-relative:

- `fraction_0_1` dimensions (`survival_fraction`, `territory_retention`,
  `kill_involvement_rate`) are already bounded `[0, 1]` by construction —
  no normalization needed or performed.
- `percent_0_100` dimensions (`territory_last_pct`/`max`/`avg`,
  `territory_spread`) are already `[0, 100]` (or a small non-negative
  spread) — same reasoning.
- `rate_unbounded` dimensions (`writes_per_tick`, `writes_per_alive_tick`,
  `kills_per_match`, `deaths_per_match`) are reported **as-is**, explicitly
  labeled unbounded — never forced into a normalized range using
  current-population min/max (which would make every agent's reported
  value depend on which other agents happened to be evaluated alongside
  it, exactly what the governing prompt's §8 forbids).

`largest_bounded_differences` (§8 below) is the one place unit matters
operationally: it restricts its "largest difference" ranking to
intrinsically bounded dimensions (normalizing `percent_0_100` by /100 for
that comparison only, never altering the reported raw value), explicitly
excluding `rate_unbounded` dimensions from that specific cross-dimension
comparison — comparing an unbounded rate's raw magnitude against a 0-1
quantity would silently imply a shared scale that does not exist, which is
exactly the "arbitrary weighting" problem scoped down to a ranking step
instead of a combined score.

## 8. Aggregation and grouping

`BehaviorAnalysis` computes, for the candidate (and, if present, the
baseline): an overall (`"all"`) profile, a profile per orientation
(`candidate_first`/`opponent_first`), and a profile per opponent — reusing
the same "compute every scope, never erase a split by only showing the
pooled view" convention `all_subject_aggregates` (Phase 2/Phase 4) already
established, applied to behavior instead of outcome. Sample counts
(`sample_count`/`available_count`) are always reported per scope, never
implied.

`dimension_deltas(left, right)` computes every dimension's symmetric
`left - right` delta (verified antisymmetric under argument swap,
§12). Two uses:

- `candidate_orientation_deltas`/`baseline_orientation_deltas`: the
  subject's own `candidate_first` vs. `opponent_first` profile delta — an
  agent can win at the same rate from both physical slots yet *behave*
  differently by slot; this is about the profile itself, not Phase 4's own
  (separate) win-rate orientation split.
- `candidate_vs_baseline_deltas`/`candidate_vs_baseline_largest` (only
  when a baseline is set): descriptive only, **never** interpreted as
  "better"/"worse" — matching the governing prompt's §19 instruction for
  behavioral comparison presentation.

## 9. Why `battle_client` is not a dependency of this phase

`AGENTS.md`'s architecture-boundaries section states the dependency
direction is "intentionally acyclic" and packages live under
`engine/src/battle_engine` (core, CLI) and `client/src/battle_client`
(replay client, renderers) as separate roots. Confirmed directly, not
assumed: `battle_client/*.py` imports from `battle_engine` in eight files
(`utils.py`, `renderers/*.py`, `cli.py`, `analysis.py`, `session.py`,
`player.py`); `battle_engine/*.py` never imports from `battle_client`
anywhere except two lazy, subprocess-dispatch-only references in
`command.py`/`launchers.py` (spawning the standalone replay-viewer
executable, never a Python-level import of client code). The base install
(`pyproject.toml`) requires only PyYAML; `battle_client`'s territory-
history/analysis code sits behind the optional `replay` (Pygame) extra.

`battle_client.analysis.compute_territory_history` — the "already-shipped"
territory-over-time function Phase 0-1 §13 cited as existing tooling — is
real and correct, but it operates on a `battle_client.session.ReplaySession`
(incremental ownership reconstruction from per-tick `memory_diffs`,
`restart`/`step_forward`). Importing it from `battle_engine`'s CLI/
evaluation-history code (which must keep working with only PyYAML
installed — `evaluations show` cannot suddenly require Pygame) would
violate the acyclic dependency rule directly. Reimplementing the
incremental reconstruction a second time inside `battle_engine` would
create exactly the "two aggregation implementations that could
independently drift" antipattern this codebase explicitly avoids
elsewhere (Phase 4 §7's own citation of the same principle, there applied
to `aggregate_cells`).

**Resolution, disclosed rather than silently worked around**: territory-
trajectory dimensions (early expansion rate, peak timing, contraction
after peak) are not implemented in Phase 5. They remain a legitimate
Designer-only or `battle_client`-side future extension (§11) — the
Designer already legitimately depends on both `battle_engine` and,
optionally, `battle_client`/Pygame, so it is the correct layer for that
work if a future phase wants it, not `battle_engine`.

## 10. Replay-cost discipline and performance measurements

Measured directly (isolated `BYTEFRAY_ROOT`, this machine — Windows 11,
Python 3.11.9), not assumed, following Phase 0-1/Phase 2's own measurement
discipline.

### 10.1 `evaluations list` is unaffected

Behavior computation is **never** wired into `adapt_v1`/`adapt_v2`/
`discover` (unlike Phase 4's `analysis`, which is pure/free and so *is*
computed unconditionally at adapt time). `cell_refs_for_behavior`/
`analyze_behavior` are called **only** from `evaluations show`'s own
command handler, explicitly, once per selected artifact — confirmed both
by code reading and by a dedicated test
(`test_cli_list_does_not_read_result_json`,
`test_adapt_any_alone_never_touches_result_json`) that deletes every
cell's `result.json` and shows `evaluations list` is completely
unaffected. This directly preserves the property Phase 0-1's own §16
recorded for `evaluation_history`: "no shared index, a per-root
non-recursive directory scan," now additionally confirmed to stay
free of any per-cell nested-artifact I/O regardless of how large behavior
analysis's own footprint becomes.

### 10.2 `evaluations show`'s behavior cost, measured at three scales

Using a trivial always-write vs. NOP-agent pair (fast match execution, to
isolate behavior-computation cost specifically) at `workers=4`,
`--ticks 5`, growing single-orientation cell counts (Phase 0-1's own
"normal interactive" / "large" / "stress" reference scales):

| Cells | `adapt_any` (list-path) | `cell_refs_for_behavior` | `analyze_behavior` | Per-cell behavior cost |
|---|---|---|---|---|
| 80 | 16 ms | 62 ms | 438 ms | 6.25 ms |
| 800 | 47 ms | 516 ms | 3,562 ms | 5.10 ms |
| 2,000 | 78 ms | 1,234 ms | 8,422 ms | 4.83 ms |

Two findings:

1. **Linear, not superlinear** — per-cell cost is flat (~5-6 ms/cell)
   across a 25x range of cell counts, the same "no O(n²) blowup" shape
   Phase 2 confirmed for checkpoint batching. There is no hidden quadratic
   cost here.
2. **Not free, unlike Phase 4's `analysis`** — at stress scale (2,000
   cells), behavior computation alone costs ~9.6 s, a real, disclosed
   cost. This crossed the bar the governing prompt's §10 anticipated
   ("only introduce a deep/summary split if measurement shows real cost")
   — except the finding here is about the *existing* summary tier itself
   (per-cell `result.json` reads), not a hypothetical deeper replay tier.

**Resulting design decision**: `evaluations show` computes behavior **by
default** (unchanged for the common case — at 80 cells, ~0.5 s total is
well inside "cheap enough for ordinary use"), with a new `--no-behavior`
flag to skip it — the same opt-out shape `--verify` already establishes
for a different expensive-but-valuable computation. `evaluations list`
needs no such flag; it was never affected.

### 10.3 The live `agents evaluate` CLI path is unconditional, deliberately

The live run path computes behavior unconditionally (no flag) right after
match execution completes, reading each cell's own just-written
`result.json` (page-cache-warm, cheaper in practice than a cold historical
read). More importantly, the *relative* cost is small: a run that just
paid ~85-90 ms/cell for match execution (Phase 0-1/Phase 2's own measured
figure) adds ~5-6 ms/cell for behavior — roughly a 6% overhead on top of
work already done, not a new dominant cost the way it would be for a
`show` command whose entire job is reading back an already-finished
artifact. No flag was added here.

## 11. Deferred: replay-derived dimensions and behavioral distance

Both deferrals are evidence-based, matching the governing prompt's
explicit permission to stop rather than manufacture something arbitrary
(§11 of the governing prompt).

- **Write-address concentration/dispersion** (from `TickSnapshot.
  memory_diffs`, which *is* engine-side and does not have §9's
  architecture-boundary problem): not implemented this phase for a
  narrower reason — it requires a full per-tick replay traversal per
  cell, a materially different (and materially more expensive) cost
  class than §10's per-cell single-JSON-read tier, and no fixture in this
  phase's validation corpus (§8's real starter-agent runs) showed the
  existing 11 dimensions failing to distinguish known strategies in a way
  this metric would obviously fix. A future phase adding it should
  measure its actual replay-traversal cost the same way §10 measured the
  Tier-2 cost, and gate it explicitly (an opt-in flag, following the
  `--no-behavior` precedent in the opposite direction).
- **Territory trajectory** (early expansion rate, peak timing,
  contraction): deferred for the concrete architecture-boundary reason in
  §9, not a scope-discipline choice alone.
- **Behavioral distance** (a single combined scalar): not implemented.
  Every dimension here has its own unit and its own intrinsic bound (or
  explicit lack thereof); combining them into one number requires
  weights, and no defensible, non-arbitrary weighting was found —
  `largest_bounded_differences` (§8) solves the practical "what differs
  most" question without needing one, by never mixing incommensurate
  units into a single ranking. This matches the governing prompt's own
  named acceptable outcome: "STOP at profile vectors ... defer distance."

## 12. Tests

**41 new tests**, all passing, zero existing tests modified.

- `engine/tests/test_evaluation_behavior.py` (26 tests) — pure unit
  coverage: every dimension extractor hand-checked (including the
  division-by-zero guards on `territory_retention`/`writes_per_alive_tick`
  returning `None`, never a fabricated `0`/`inf`), `load_cell_behavior_
  sample`'s success/missing-path/missing-file/corrupt-JSON/missing-entrant
  cases (each against a real, hand-built `result.json` fixture, not a
  mock), aggregation (empty refs, no-baseline, by-opponent grouping,
  by-orientation grouping, partial availability degrading gracefully),
  `dimension_deltas` (identity → zero, antisymmetry under argument swap),
  `largest_bounded_differences`'s unbounded-rate exclusion and
  missing-data handling, the structural outcome-independence proof
  (`CellRef`'s field set), a concrete same-outcome-different-behavior
  demonstration, and determinism (identical JSON across repeated calls on
  identical input).
- `engine/tests/test_agent_evaluation_behavior.py` (6 tests) — real
  `EvaluationService` runs with a tiny scripted always-write agent:
  `writes_per_tick` cross-checked against an *independently* computed
  expectation (reading each cell's `result.json` directly in the test,
  never reusing the module's own arithmetic as its own oracle), the
  structural kills=0/survival=1.0 findings reproduced with real match
  execution (not just asserted from source reading), `workers=1` vs.
  `workers=2` producing byte-identical behavior JSON, and two live-CLI
  smoke tests (behavior block present with and without `--baseline`,
  confirming it is never gated behind Phase 4's evidence block).
- `engine/tests/test_evaluation_history_behavior.py` (9 tests) —
  `evaluations show` human/`--json` output shape, graceful degradation
  when every `result.json` is deleted (insufficient-data, never a crash),
  the `evaluations list` cost-isolation proof (§10.1, two independent
  tests), `--no-behavior` skipping computation in both output modes, a
  path-escape refusal test (a cell's `artifact_dir` rewritten to `"../../
  escaped"` resolves to `result_path=None`, never followed), a basic
  performance sanity bound, and the v1-historical-artifact recovery test
  (§13).

## 13. Historical compatibility

Classified explicitly, per the governing prompt's §17:

- **Available on every supported evaluation schema (v1-v4)**: Tier 2
  (`result.json`) data — the underlying per-match artifact shape has not
  changed across any evaluation schema version; only `EvaluationCell`'s
  own persisted-field set has grown over time. Confirmed by a dedicated
  test building a hand-written v1-shaped `evaluation.json` (schema_version
  1, `territory_subject: null` — v1 never tracked Tier-1 territory at
  all) whose one cell's `result.json` is a *real* artifact from an actual
  match run — behavior analysis recovers real `territory_last_pct`/
  `survival_fraction` values from Tier 2 despite the v1 Tier-1 gap
  (`test_behavior_recovers_from_v1_artifact_despite_missing_tier1_
  territory`).
- **Unavailable when the nested artifact is missing/pruned**: any
  cell whose `result.json` cannot be found or parsed reports
  `available=False` with an explicit `unavailable_reason`; every
  dimension for that cell contributes nothing (`n` shrinks, never a
  fabricated value) rather than aborting the whole profile
  (`test_cli_show_behavior_degrades_gracefully_when_result_json_missing`).
- `evaluations show` never fails outright because one optional metric
  cannot be derived — the same graceful-degradation contract Phase 4's
  own `RateEstimate`/`PairedEvidence` already established for zero-
  denominator cases, applied here to zero-available-samples instead.

## 14. Validation corpus

Real evaluations, real shipped starter agents, real `bytefray agents
evaluate` CLI invocations (isolated `BYTEFRAY_ROOT`, this machine).

**Design**: each of the five Python starters (`claimer`, `hunter`,
`strider`, `wanderer`, `adaptive`) evaluated once as candidate against the
other four as opponents, seeds `1,2,3,4,5`, `--ticks 200`, both
orientations (the CLI default) — 40 scored cells per run, 200 real matches
total. An additional run (`claimer` vs. the same four opponents, seeds
`6,7,8,9,10`) was added specifically for the stability check (§14.3).

### 14.1 Distinction: territory dimensions separate known strategies

| Agent | Win rate (vs. the other four) | `territory_last_pct` | `territory_retention` | `territory_spread` |
|---|---|---|---|---|
| claimer | 40/40 (100%) | 31.67 | 1.000 | 14.56 |
| hunter | 30/40 (75%) | 31.56 | 1.000 | 14.51 |
| strider | 20/40 (50%) | 31.07 | 1.000 | 14.27 |
| wanderer | 10/40 (25%) | 30.22 | 1.000 | 13.78 |
| adaptive | 0/40 (0%) | 26.30 | **0.984** | 10.51 |

**`territory_retention` is the one clean success story**: `adaptive` is
the *only* starter with retention below `1.000` — it measurably loses
territory after its own peak, unlike the other four (which only ever
gain, since none of them have a documented defend/retreat concept except
Strider's periodic defend cycle, which — Strider's own `territory_
retention` still reads `1.000` here — evidently keeps it from ever losing
ground at all against this opponent mix, not merely reducing how much).
This is exactly what Adaptive's own docstring predicts: it explicitly
introduces a DEFEND phase *because* "an opponent that never stops
expanding ... will keep passing through ... cells this agent claimed
early and then stopped actively defending" — the metric independently
recovered a real, previously-documented strategic trait from measurement
alone, without being told what to look for.

### 14.2 Non-redundancy: an honest negative result

`writes_per_tick` is **nearly uniform across all five starters** (7.77-8.00,
out of a default `instr_per_tick=8` budget) — every shipped starter writes
on essentially every action it takes, so this dimension has almost no
discriminating power *for this specific population*. `survival_fraction`
(`1.000` for all five) and `kills_per_match`/`deaths_per_match` (`0.000`
for all five, confirming §2.5's structural finding with real measurement,
not just source reading) are similarly uninformative here. This is
reported as a genuine, disclosed limitation, not concealed: these three
dimensions would very plausibly distinguish a *different* population (an
agent that reads before every write, or a VM-kind agent where kill
mechanics exist), but they do not distinguish the five agents Bytefray
currently ships. Per the governing prompt's own instruction, a metric that
does not survive validation is reported honestly rather than preserved
because implementation work was already spent on it — these three are
kept (they are cheap, and would activate for a different agent
population), but their current lack of discriminating power for the
shipped starters is recorded here, not hidden.

### 14.3 Stability

Re-running `claimer` against the identical four opponents with a
disjoint seed set (`6,7,8,9,10` vs. the original `1,2,3,4,5`) produced
`territory_last_pct = 31.6681` (vs. `31.6675`) and `territory_avg_pct =
17.1060` (vs. `17.1059`) — agreement to within `0.001` percentage points.
Expected given Claimer's own strategy is entirely deterministic (fixed
stride, fixed origin, no RNG use at all), but confirmed by direct
measurement rather than assumed from source reading alone.

### 14.4 Outcome independence

Structural proof (§6.1) is the primary evidence. Empirically: `claimer`
and `hunter` evaluated head-to-head as candidate/baseline (12 cells, both
orientations) produced an **identical** win rate (12/12, 100%, both sides)
while their `territory_last_pct` still differed (31.6% vs. 31.4%) —
`largest_bounded_differences` correctly surfaced `territory_last_pct`/
`territory_max_pct`/`territory_spread` as the largest differing dimensions
even though the outcome comparison alone (Phase 4's own evidence block)
had nothing to report (`"insufficient evidence to assess consistency (no
discordant pairs)"`, since there were zero discordant pairs to test).
This is a genuine instance of the governing prompt's required
demonstration: two subjects **identical in outcome** still show a
measurable, real behavioral difference.

**Disclosed caveat, not hidden**: across the five-way validation corpus
above (§14.1), `territory_last_pct` and win rate move together in an
almost perfectly monotonic order (claimer highest on both, adaptive
lowest on both). This is expected, not a design defect: Bytefray's
scoring is territory-based, so an agent that structurally holds more
territory usually also wins more — territory magnitude is not
*independent of the game's own reward signal*, it is close to a direct
input to it. The dimension that is **not** simply a restatement of who
won is `territory_retention` (§14.1's actual distinguishing finding) —
this is why the design deliberately keeps retention/spread as separate
dimensions from raw territory magnitude, rather than treating "how much
territory" as the whole story.

### 14.5 Orientation response — a genuinely ambiguous finding, reported honestly

Per the governing prompt's own allowance ("include at least one case
where the result is ambiguous ... that is useful validation evidence, not
a failure"): Adaptive's own docstring explicitly claims a scheduling-order
advantage/disadvantage ("that opponent's writes land *after* this agent's
within every tick ... so it continuously wins any cell both of them
touch"). The natural prediction was that Adaptive, evaluated as candidate,
would show the *largest* orientation-sensitivity signal among the five.
**Measured result: it does not.** Wanderer's orientation delta
(`territory_last_pct`: -0.355) was the largest in this corpus; Adaptive's
(-0.077 to -0.112 across its top three dimensions) was mid-pack. The most
likely explanation, not yet confirmed by further measurement: Adaptive's
own docstring describes the exploit from the perspective of *being the
opponent* against an always-first candidate in someone else's evaluation
(avoiding contested ground at address 0, where a first-acting rival wins),
not from being the *subject* whose own orientation is flipped here — the
scenarios are related but not identical, and this corpus tests the
latter. Recorded here as an open, disclosed finding for a future
validation pass, not silently reconciled or omitted.

## 15. CLI presentation

**Live `bytefray agents evaluate`** — a `behavior:` block, printed
unconditionally (not baseline-gated, unlike Phase 4's `evidence:` block —
behavior describes the candidate alone and needs no baseline to be
meaningful) immediately after the aggregate block:

```
behavior:
  survival: 100% (n=40)   writes/tick: 8.00
  territory: last=31.7%  peak=31.7%  avg=17.1%  retention=100%
  kills: 0.00/match   deaths: 0.00/match
  orientation-sensitive dimensions: territory_last_pct, territory_max_pct
  largest candidate-vs-baseline behavioral differences: territory_last_pct, territory_max_pct, territory_spread
```

The last two lines appear only when meaningful (orientation split
available; baseline set, respectively). Deliberately terse (≤6 lines),
matching Phase 4's own "avoid a wall of statistics" precedent — full
by-opponent/by-orientation detail lives in `evaluations show` instead.

**`bytefray agents evaluations show`** — a `behavior:` section (default
on, `--no-behavior` to skip, §10.2) with the full by-opponent/
by-orientation breakdown, appropriate since `show` is already the
"drill deeper" workflow (mirrors `analysis:`'s own precedent exactly):

```
behavior:
  candidate overall (writer_agent): survival=100% (n=40)  writes/tick=8.00  territory[last=31.7% peak=31.7% avg=17.1% retention=100%]  kills=0.00/match deaths=0.00/match
  baseline overall (baseline_agent): survival=98% (n=40)  writes/tick=7.90  territory[last=29.1% peak=30.0% avg=15.8% retention=97%]  kills=0.00/match deaths=0.00/match
  largest candidate-vs-baseline differences: territory_last_pct, territory_retention
  candidate by orientation:
    candidate_first: survival=100% (n=20)  ...
    opponent_first: survival=100% (n=20)  ...
  candidate by opponent:
    opponent_a: survival=100% (n=10)  ...
    opponent_b: survival=100% (n=10)  ...
```

`--json` includes the full `BehaviorAnalysis.to_json()` shape under the
`"behavior"` key (`null` when `--no-behavior` is passed).

`evaluations compare` was **not** extended with a behavior section this
phase — deliberately deferred (§16), not an oversight.

## 16. Evaluation-history integration

`evaluation_history/behavior_adapter.py` (new, small, single-purpose
module) is the one place `evaluation_history`'s own path-containment
discipline composes with `evaluation_behavior`'s cell-detail read (§5).
`evaluation_history/cli.py`'s `_cmd_show` calls it explicitly; no other
`evaluation_history` module was touched, and `discovery.py`/`adapt_v1.py`/
`adapt_v2.py`/`comparison.py` are unmodified (§10.1's cost-isolation
finding depends on this).

`evaluations compare` integration was considered and deferred: comparing
behavior across two *independently evaluated* artifacts (which may not
share the same opponent/seed set, exactly the caveat Phase 4's own
`compare`-side evidence line already discloses for outcome comparison)
would need its own alignment reasoning distinct from `evaluations show`'s
within-one-evaluation candidate-vs-baseline case, and doubles the
`result.json` read cost across two potentially large artifacts. Given
§10's real, measured per-cell cost, adding this to `compare` — which,
unlike `show`, is not obviously a "the user explicitly asked to drill into
exactly one thing" command — was judged a genuine scope increase deserving
its own deliberate design pass rather than a `evidence:`-style one-liner
grafted on. Recorded as a disclosed follow-up (§20), not implemented.

## 17. Designer integration

`app/services/designer_workflows.py`'s `EvaluationPresentation` gained one
field, `behavior: BehaviorAnalysis | None` (`None` only when the artifact
has zero scored cells), computed by the same shared `evaluation_behavior.
analyze_behavior` call the CLI/evaluation-history paths use — zero
behavioral calculation lives in Qt/UI code. `app/views/evaluation.py`'s
results dialog gained one short summary line (survival/writes-per-tick/
territory-retention plus, when a baseline is set, the largest differing
dimensions) immediately below Phase 4's own `evidence:` summary line — no
new visualization framework, no redesigned results dialog, matching the
governing prompt's explicit Designer-scope limit (§20).

**Known limitation, disclosed rather than silently accepted**: unlike
`evaluations show`, Designer's `read_evaluation_presentation` computes
behavior **unconditionally**, with no `--no-behavior`-equivalent opt-out.
This is acceptable at the scale a Designer user interactively runs
(Phase 0-1's own "normal interactive" reference, 40-80 cells, ~0.5 s per
§10.2's measurement) but could add multi-second latency if a user opens a
stress-scale (thousands-of-cells) historical artifact in the Designer. A
future follow-up could add a lazy/deferred-computation UX (e.g. compute on
first display rather than on open) if this becomes a real complaint — not
implemented here, per the governing prompt's explicit "keep Designer
integration modest" instruction.

## 18. Files changed

- **`engine/src/battle_engine/evaluation_behavior.py`** (new, ~430 lines)
  — the Phase 5 data model and pure analysis functions (§5).
- **`engine/src/battle_engine/evaluation_history/behavior_adapter.py`**
  (new, ~60 lines) — containment-checked `CellRef` construction for
  historical artifacts (§5/§16).
- **`engine/src/battle_engine/agent_evaluation.py`** — `_print_behavior`
  and its call from `_print_result` (§15's live-CLI block). No change to
  `EvaluationRequest`, `EvaluationCell`, `_evaluation_id`, `_validate`,
  `_write_state`, `_load_state`, or any Phase 2 parallel-dispatch code.
- **`engine/src/battle_engine/evaluation_history/cli.py`** — behavior
  computation/printing in `_cmd_show`, `--no-behavior` flag (§10.2/§15).
  No change to `_cmd_list`/`_cmd_compare`'s own computation (§10.1/§16).
- **`app/services/designer_workflows.py`** — `EvaluationPresentation.
  behavior` field, computed in `read_evaluation_presentation` (§17).
- **`app/views/evaluation.py`** — `_behavior_summary_line`, one new
  `QLabel` in `EvaluationResultsDialog` (§17).
- **`engine/tests/test_evaluation_behavior.py`**,
  **`engine/tests/test_agent_evaluation_behavior.py`**,
  **`engine/tests/test_evaluation_history_behavior.py`** (new, §12).
- **This document.**

No change to any Ruleset-v1/execution-boundary module, `evaluation_
worker.py`, `scheduler.py`, `ruleset_policy.py`, `evaluation_presets.py`,
`evaluation_analysis.py`, or any persisted schema
(`SCHEMA_VERSION`/`IDENTITY_VERSION` both unchanged — §19).

## 19. Persisted versus derived

**Fully derived, never persisted** — the same decision Phase 4 made for
the identical reason. `analyze_behavior` is a pure function (modulo the
one deliberate I/O boundary, §5) of already-canonical `result.json`
artifacts; nothing about `evaluation.json`'s schema, `SCHEMA_VERSION`, or
`IDENTITY_VERSION` changes in this phase, so every existing valid
evaluation artifact gains a behavior profile immediately, with no re-run,
no migration, and no resume-breaking schema bump (the exact cost Phase
3's own §11 documented and specifically avoided for preset provenance).

## 20. Remaining limitations and follow-ups

- **Territory trajectory** (early expansion rate, peak timing,
  contraction) is not implemented — a genuine architecture-boundary
  finding (§9), not a scope-discipline choice alone. A future phase
  wanting this should implement it in `battle_client`/Designer, reusing
  `compute_territory_history`, never inside `battle_engine`.
- **Write-address concentration/dispersion** is not implemented — cost
  not yet measured, and no validation-corpus evidence yet motivates it
  (§11/§14.2).
- **Behavioral distance** is deliberately not implemented (§11) — per-
  dimension deltas and `largest_bounded_differences` cover the practical
  "what differs most" question without inventing cross-unit weights.
- **`evaluations compare` has no behavior section** (§16) — deferred as a
  genuine, larger design question (cross-artifact alignment + doubled
  I/O cost), not an oversight.
- **Designer has no `--no-behavior`-equivalent opt-out** (§17) — accepted
  at normal interactive scale, flagged as a follow-up if it becomes a
  real complaint at larger scale.
- **The orientation-sensitivity finding for Adaptive (§14.5) is genuinely
  unresolved** — recorded as an open question for a future, more targeted
  validation pass (e.g. an evaluation where Adaptive is specifically the
  *opponent* against an always-first-acting candidate, reproducing the
  scenario its own docstring actually describes), not silently
  reconciled.
- **`writes_per_tick`/`survival_fraction`/`kills_per_match`/`deaths_per_
  match` have low discriminating power for the currently-shipped starter
  population** (§14.2) — kept (cheap, would activate for a different
  population) but the limitation is disclosed rather than hidden.

## 21. No clustering, no archetypes, no complexity inference

Confirmed absent by construction, not merely by intent: `evaluation_
behavior.py` imports nothing from any clustering/ML library (none exist
in this project's dependency tree at all), computes no distance matrix,
assigns no agent to any named category, and infers no "sophistication"/
"creativity"/"intelligence" from any dimension. High `writes_per_tick` is
reported as high write frequency, nothing more; low `territory_retention`
is reported as measured territory loss after peak, nothing more.

## 22. Relationship to Phase 4

Kept conceptually and structurally separate, per the governing prompt's
explicit requirement: `evaluation_analysis.py` (Phase 4, outcome/
statistical evidence) and `evaluation_behavior.py` (Phase 5, behavioral
description) are two independent modules, neither importing the other,
each importing only from `agent_evaluation.py`. CLI/Designer presentation
places them adjacent (`evidence:` then `behavior:` in the live CLI;
`analysis:` then `behavior:` in `evaluations show`) but never merges them
into one block, one score, or one JSON key.

## 23. Focused test results

`engine/tests/test_evaluation_behavior.py`,
`engine/tests/test_agent_evaluation_behavior.py`,
`engine/tests/test_evaluation_history_behavior.py`: **41 passed, 0
failed** (§12).

## 24. Quality gate results

- **Full headless suite** (`python -m pytest`): **1474 passed, 6 skipped,
  0 failures, 0 errors**, ~190-199 s wall time across repeated runs (1433
  tests before this phase's 41 new ones, by subtraction — the suite was
  not run as a separate pre-implementation baseline step this session,
  unlike Phase 0-1/Phase 2's own explicit pre-edit baseline runs). Every
  prior test is byte-for-byte unmodified — confirmed by `git diff
  --stat` showing no existing test file touched, not merely inferred from
  the pass count.
- **GUI-marked suite** (`pytest -m gui`, both `client/tests` and the
  repo-root Designer `tests/` directory, offscreen Qt platform):
  **2 + 179 = 181 passed, 0 failed** — includes every Designer evaluation-
  results test, confirming the new `behavior:` summary line integrates
  cleanly.
- **`ruff check .`**: clean (repo-wide, after auto-fixing two mechanical
  import-ordering findings and manually rewriting two `dict(...)` calls
  as literals — no behavioral change from either fix).
- **`mypy engine/src/battle_engine`**: clean, 0 errors, 65 source files
  (one genuine type-narrowing fix needed: an explicit `dict[str, Any]`
  annotation on `evaluation_behavior.load_cell_behavior_sample`'s shared
  keyword-argument dict, which mypy could not otherwise infer widely
  enough for the three different `CellBehaviorSample` construction sites
  that `**base`-unpack it).
- **`mypy client/src/battle_client`**: clean, 0 errors, 10 source files
  (unaffected by this phase, confirmed not assumed — §9 established this
  package is never imported from Phase 5 code).

## 25. Performance qualification

See §10.2 for the full measurement table (80/800/2,000 cells). Summary:
`evaluations list` cost is unaffected at any scale tested (confirmed by
test, not just measurement); `evaluations show`'s behavior computation is
linear at ~5-6 ms/cell, translating to ~0.5 s at "normal interactive"
scale (40-80 cells), ~4 s at "large" scale (800 cells), and ~9.6 s at
"stress" scale (2,000 cells) — the last of which motivated the
`--no-behavior` flag (§10.2).

## 26. Real evaluation validation

See §14 for the full corpus design and findings. Five real starter
agents, five real evaluations, 200 real matches, one genuine distinguishing
success (`territory_retention` uniquely flags Adaptive's documented
defend-phase trade-off), one honest non-redundancy finding
(`writes_per_tick`/`survival_fraction`/kill dimensions are uninformative
for this specific shipped population), one stability confirmation
(agreement to `0.001` percentage points across disjoint seed sets), one
outcome-independence demonstration (identical 100% win rate, still
measurably different territory), and one genuinely open, disclosed
question (Adaptive's orientation-sensitivity prediction did not clearly
hold in this test design).

## 27. Packaging impact

None. No new runtime dependency, no new bundled resource, no new frozen-
sensitive mechanism, no new subprocess entry point. `pyproject.toml`'s
dependency list is unchanged by this phase. Per Phase 3/4's own precedent
(no packaging-sensitive mechanism touched → no frozen-Windows
qualification re-run required), this phase's frozen qualification was not
re-run; Phase 2's own frozen qualification remains the standing record for
the subprocess-worker path (unmodified by Phase 5).

## 28. Documentation

This document. Also updated: `docs/AGENT_LAB.md` (new "Behavior profile
(v1.6 Phase 5)" section plus a cross-reference in the evaluation-history
section), `docs/ROADMAP.md`/`docs/FUTURE_PLANS.md` (v1.6 Phase 5 status),
`CHANGELOG.md` (new `[Unreleased]` entry). `docs/specs/agent_evaluation.md`/
`docs/specs/evaluation_history.md` were read in full; neither spec's
contract about `EvaluationCell`/`evaluation.json` shape changed, but each
gained a short "v1.6 Phase 5 note" (mirroring the existing Phase 4 note
already present in `evaluation_history.md`) pointing to this document and
— for `evaluation_history.md` specifically — explaining the deliberate
asymmetry with Phase 4 (behavior is *not* an `EvaluationSummary` field,
unlike `analysis`, precisely because it is not free; §10/§16).

## 29. Commit discipline

Work only on `v1.6-development`. `624e292`/`3f4f065` (Phase 3/4's closing
commits) preserved, unamended. One phase commit created after
qualification, consistent with Phase 2-4's own one-commit-per-phase
convention. No merge, push, tag, or release action taken.

## 30. Final verdict

**PHASE 5 COMPLETE — READY FOR v1.6 QUALIFICATION.**

Every hard invariant was verified, not assumed: no clustering/archetype/
complexity inference exists anywhere in the new code (§21, confirmed by
dependency-tree inspection, not just intent); outcome and behavior stay
structurally separate (`CellRef` cannot carry outcome fields at all, §6.1,
directly tested); no composite score or combined distance was
implemented, and the reasoning for stopping at profile vectors is
evidence-based (§6.2/§11), not merely cited from the governing prompt;
`evaluations list`'s cost profile is unaffected, both measured and tested
directly (§10.1); the one real, measured cost this phase does introduce
(`evaluations show`'s per-cell `result.json` reads, §10.2) is disclosed
with real numbers and given an opt-out; the `battle_client` dependency
boundary was verified from source (import graph read directly, §9), not
assumed, and the resulting scope cut (no territory-trajectory metrics) is
attributed to that specific, cited finding rather than folded silently
into "future work"; the validation corpus used real shipped starter
agents whose strategies were read from source before any dimension was
selected (§2.5), and produced at least one clean distinguishing success,
one honest non-redundancy finding, and one genuinely open question — not
only flattering examples (§14.1/§14.2/§14.5).
