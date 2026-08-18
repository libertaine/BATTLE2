# v1.6 Phase 0–1 — Evaluation scale architecture & baseline

This is the durable record of v1.6 Phase 0 (repository/architecture
baseline) and Phase 1 (scale characterization and the proposed v1.6
parallel-evaluation contract) for **v1.6.0 — Evaluation Scale & Analysis**,
the last substantive v1.x feature release. Per the governing prompt, this
document is investigation and measurement only: **no parallel execution,
presets, statistics, or behavior-profile code is implemented here.**
Everything below is either read directly from the current source tree or
measured directly against it; nothing is projected without evidence.

Written in the same spirit as `docs/V1_5_PHASE1_RULESET_V1_BASELINE.md`: a
pre-Phase-2 snapshot, not a design document to be silently superseded —
Phase 2 should cite this document rather than re-deriving its findings.

## 1. Repository / baseline state

- **Branch:** `main`. **HEAD:** `bc0cbae04a777c3f9762ca6aea9c7fb0676ff796`
  ("chore(release): prepare Bytefray 1.5.0 release"). **Working tree:**
  clean at the start of this investigation and again after it (confirmed
  by `git status --short` before writing this document; all benchmarking
  below ran against an isolated `BYTEFRAY_ROOT` outside the repository, so
  nothing in the working tree changed as a side effect of measurement).
- **Tags:** `v1.5.0` resolves (via `git rev-parse v1.5.0^{commit}` /
  `git describe --tags --long` → `v1.5.0-0-gbc0cbae`) to exactly `HEAD` —
  zero commits since the tagged release. `v1.4.1`, `v1.4.0`, `v1.3.0`, ...
  back to `v0.4.0` are present and ordered as expected.
- **Relevant recent commits** (`git log --oneline -8`):
  `bc0cbae` release prep, `7ea515f` "test/docs: qualify v1.5 architecture
  equivalence" (Phase 6), `c25c1e0` "refactor(runtime): separate entrant
  identity from execution state" (Phase 5), `77a0dbb` "refactor(rules):
  centralize Ruleset-v1 termination" (Phase 4), `c776c9a`
  "refactor(rules): add Ruleset-v1 policy dispatch" (Phase 3), `d2c4a56`
  "refactor(runtime): unify Ruleset-v1 scheduling" (Phase 2), `39d4d4e`
  "test/docs: lock v1.5 Ruleset-v1 architecture invariants" (Phase 1).
  v1.5 shipped as five refactor phases plus a qualification phase; each
  has its own durable `docs/V1_5_PHASE{2..6}_*.md` record, all read in
  full for this investigation.
- **Current test baseline** (`python -m pytest --junitxml=...`, this
  machine, Python 3.11.9 — note `bytefray --version` reports `3.11.9`
  here even though `.python-version`/CI matrix target 3.10-3.13; this is
  simply the interpreter this checkout's `.venv` happens to be built
  against, not a project change): **1283 passed, 6 skipped, 0 failures, 0
  errors** (`tests="1289"`, `skipped="6"` in the JUnit XML), full-suite
  wall time **78.463 s**. This is byte-identical to Phase 6's own recorded
  baseline (`1283 passed, 6 skipped`) — confirming nothing has drifted
  between the v1.5.0 tag and this `HEAD` (there is nothing between them)
  and that the suite is a valid, currently-green starting point for v1.6
  work.
- **Evaluation-relevant test inventory** (`pytest --collect-only`, counts
  per module): `test_agent_evaluation.py` 60, `test_agent_evaluation_
  orientation.py` 27, `test_agent_evaluation_revision_capture.py` 13,
  `test_agent_evaluation_v2.py` 42, `test_evaluation_history.py` 53,
  `test_evaluation_history_cli.py` 29, `test_evaluation_history_
  comparison.py` 40, `test_evaluation_history_revisions.py` 11,
  `test_evaluation_history_verification.py` 26, `test_evaluation_history_
  workflows.py` 16 (**317 tests** across evaluation + evaluation-history
  alone); `test_scheduler.py` 8, `test_scheduler_characterization.py` 7,
  `test_python_scheduler_characterization.py` 2, `test_ruleset_policy.py`
  17, `test_ruleset_v1_equivalence.py` 8, `test_entrant_identity.py` 10
  (**52** architecture-boundary tests); `test_native_match_service.py` 12,
  `test_tournament_service.py` 25, `test_agent_revisions.py` 53,
  `test_agent_revisions_cli.py` 16, `test_agent_revision_lifecycle.py` 1.

## 2. Current evaluation architecture

Established by direct reading of `engine/src/battle_engine/agent_
evaluation.py` (2452 lines) and `engine/src/battle_engine/evaluation_
history/` (8 modules, ~3400 lines combined), cross-checked against
`docs/specs/agent_evaluation.md` and `docs/specs/evaluation_history.md`
(the pre-implementation specs, still largely accurate — see caveats
inline below where current source has moved past them).

- **`EvaluationService`** (`agent_evaluation.py:1373`) is the sole
  orchestrator for `bytefray agents evaluate`, structurally a sibling of
  `TournamentService` (`tournament_service.py`), not a wrapper around it —
  both sit over `NativeMatchService`, but schedule genuinely different
  experiment shapes (round-robin peers vs. a fixed candidate/baseline ×
  opponent × seed × orientation matrix). `EvaluationService.preflight`
  (line 1382) validates a request and resolves its `evaluation_id`
  independent of an output directory; `EvaluationService.run` (line 1421)
  does the real work.
- **The matrix** is built once, deterministically, by `build_matrix`
  (line 716): `subject → opponent → seed → orientation`, always candidate
  before baseline, never re-sorted or deduplicated. Each cell
  (`EvaluationCell`, line 580) carries its own `schedule_id`, duplicate-
  occurrence coordinates (`opponent_index`, `seed_index`, `matrix_
  ordinal`, `condition_occurrence_index`), and `artifact_dir`. As of v0.9
  Phase 6, **both entrant orientations run by default**
  (`EvaluationRequest.both_orientations`, line 572, default `True`) —
  this doubles matrix size relative to the original v0.6 design unless
  `--single-orientation` is passed, and is the single most consequential
  scale-relevant default change since the original spec was written (see
  §5, §10).
- **Per-cell execution** is `EvaluationService._execute_cell`
  (line 1795): pre-execution source-drift check → `agent_test.test_agent`
  (the exact same function `bytefray agents test` uses standalone, called
  with `timeout=None, trace=False` — unsupervised and untraced by
  construction, not a caller choice) → post-execution drift check →
  `EvaluationCell` with outcome/scores/statistics filled in. This function
  is **already a pure function of `(cell, request, planned_identities,
  record_context_usage)`** returning one `EvaluationCell` — it reads no
  instance state beyond `self` (which itself has no mutable fields; see
  §4) and mutates nothing outside its return value except through the
  passed-in `record_context_usage` callback (see §4's concurrency-hazard
  finding).
- **The scheduling loop** is `EvaluationService.run`'s own
  `for cell in matrix:` block (line 1497-1557): strictly sequential, one
  cell fully executed and checkpointed before the next cell's `_execute_
  cell` call begins. This is **the seam v1.6 parallelism must extend** —
  see §4.
- **Persistence**: `<output_dir>/evaluation.json`
  (`bytefray.evaluation`, current `schema_version: 2`,
  `identity_version: 2`) is rewritten via `result_model.write_json_atomic`
  (temp-file-then-rename) after **every** newly-executed cell (line
  1534-1547), not only at the end, so an interrupted run leaves a
  readable, resumable artifact. `_checkpoint_cells` (line 1194) merges
  this run's newly-completed cells with any prior-persisted cells never
  reached yet this run, so a checkpoint is never less complete than what
  is already durable on disk (documented there as invariant "B2").
  `evaluation_id` (`_evaluation_id`, hashing candidate/baseline/opponent
  identities, seeds, ticks, `effective_conditions`, `rules_compatibility_
  id`, and an explicit `identity_version` marker) is frozen once at the
  start of `run()` from a single `planned_identities` snapshot — never
  re-derived from a second live read — specifically to close a TOCTOU gap
  found and fixed in a v0.7 correction pass (documented in `docs/specs/
  evaluation_history.md` §7).
- **Resume/retry**: identical shape to `TournamentService`'s established
  pattern — a completed cell's `result.json` is trusted only after
  verifying entrant order, seed, recomputed `match_id`, and replay digest
  (`_resumed_cell_mismatch`, line 1230); a mismatch demotes the cell to
  `corrupted`, never silently re-run or silently trusted. `--retry-
  failed` re-executes only `failed` cells; `drift_detected` cells are
  never retried inside the same artifact (the only correct recovery is a
  new evaluation, since the frozen plan itself no longer matches the
  agent(s) on disk).
- **`evaluation_history/`** (discovery, v1/v2 adapters, comparison,
  health, verification, CLI — `bytefray agents evaluations
  list|show|compare`) is a **read-only** layer over already-written
  `evaluation.json` artifacts: no shared index, a per-root non-recursive
  directory scan (`discovery.py:123`, confirmed by
  `docs/specs/evaluation_history.md`'s own "no index" decision, backed by
  measurement: ~1.86 s to scan/adapt 1000 synthetic artifacts, judged not
  worth an index at that scale). This layer is unaffected by v1.6
  parallel-execution work except insofar as it must keep reading whatever
  shape `evaluation.json` ends up having (§9).

## 3. End-to-end execution flow

Traced live, not inferred, by running the actual CLI and reading every
function on the path:

```
bytefray agents evaluate <candidate> --opponents ... --seeds ...
        |
        v
command.py:_agents()  ──►  agent_evaluation.main()            (CLI/argv)
        |  parse_opponents / _resolve_seeds / _parser()
        v
EvaluationService.preflight()  ──►  evaluation_id, default --output dir
        |
        v
EvaluationService.run(EvaluationRequest)
        |  _validate → planned_identities snapshot → build_matrix()
        |  _load_state (resume) → first checkpoint (if new)
        v
   for cell in matrix:                      <-- THE SEQUENTIAL SEAM
        |  resume check (_resolve_from_state) or:
        |  _execute_cell(cell, ...)
        |        |
        |        v
        |  agent_test.test_agent(subject, opponent, seed, ticks,
        |                        timeout=None, trace=False, run_dir=...)
        |        |
        |        v
        |  NativeMatchService.run(MatchRequest)      <-- THE EXECUTION
        |        |                                       BOUNDARY
        |        |-- resolve_ruleset_policy(BYTEFRAY_RULESET_ID)  (once)
        |        |-- PythonEntrantController / SupervisedPythonEntrant-
        |        |     Controller construction (fresh per call)
        |        |-- controller.run()
        |        |     |-- ruleset_policy.run_scheduler(...)
        |        |     |     -> scheduler.run_sequential_quota (§4)
        |        |     |-- ruleset_policy.resolve_termination(...)
        |        |-- _finalize_native_artifacts(): canonical_match_id,
        |        |     result_id, atomic replay + result.json write
        |        v
        |  EvaluationCell (outcome, scores, statistics, execution_
        |  context_id) returned up to EvaluationService.run
        |
        |  _write_state() -> evaluation.json checkpoint (atomic, whole-
        |                     file rewrite, see §5's O(n) finding)
        v
   aggregate_cells / all_subject_aggregates / compare_candidate_baseline
        v
   evaluation.json (final) + per-cell matches/<...>/{replay.jsonl,
   result.json, summary.json}
        v
CLI presentation (_print_result) / Designer reads evaluation.json back
(app/services/agent_workflows.py's read_evaluation_presentation)
```

**Designer entry point**: `app/views/evaluation.py`'s `EvaluationDialog`
is a plain input collector; `app/agent_designer.py`'s `_on_evaluate`
(guarded by one shared `self._proc` slot, so Evaluate/Validate/Test/
Tournament can never run concurrently from the Designer) builds the exact
same CLI argv via `app/services/designer_workflows.py`'s
`build_designer_evaluate_command` (reusing `agent_evaluation`'s own
`parse_opponents`/`parse_seed_list`/`parse_seed_range` — not a second
parser) and launches **one** `QProcess` running that CLI command. There is
no Designer-side fan-out today, and none is expected to be added in v1.6:
any parallelism must originate inside `EvaluationService`/`cli.py`, and the
Designer will simply observe a faster single CLI invocation.

## 4. Scheduler readiness assessment

The governing prompt is explicit that the scheduler abstraction must not
be assumed sufficient just because it was designed with future scaling in
mind, and must be verified from the implementation. It was verified, and
**the verification result is the single most important finding of this
investigation:**

> **`battle_engine.scheduler.run_sequential_quota` (the v1.5 scheduler
> abstraction) is not the seam for v1.6 evaluation parallelism, and must
> not be touched by it.**

`scheduler.run_sequential_quota` (`scheduler.py:34`) answers one question
only: *within one already-running match*, which live entrant gets the
next of its `instr_per_tick` execution opportunities, in what order, and
when to stop early because it died. It is invoked by the VM
(`match.MatchRunner._execute_agents`), unsupervised Python
(`python_runtime.PythonEntrantController.run`), and supervised Python
(`supervised_runtime.SupervisedPythonEntrantController.run`) — all three
*inside a single match's own tick loop*. It has no concept of "another
match," "another evaluation cell," or "another worker"; it is pure,
dependency-free (stdlib only), and its entire contract is Ruleset-v1
gameplay semantics (Invariant #1: **must not change**). Nothing about
v1.6 evaluation-scale work has any legitimate reason to call it, subclass
it, or reimplement its shape at a different level — doing so would be
exactly the "unrelated parallel execution path" the governing prompt
warns against, just aimed at the wrong abstraction.

The actual seam — the place where v1.5 already assembled a scheduler-*
shaped* abstraction one level up, over independent matches rather than
independent entrants — is **`EvaluationService.run`'s own `for cell in
matrix:` loop** (§3), which:

- already iterates a fully pre-computed, order-stable, deterministic
  sequence of independent units of work (`EvaluationCell`s);
- already delegates each unit's execution to one pure(-ish) function,
  `_execute_cell`, whose only side effects beyond its return value are
  (a) reading/writing files strictly under that cell's own `artifact_dir`
  (never shared with any other cell) and (b) calling the `record_context_
  usage` closure (see hazard below);
- already treats persistence (`_write_state`) as a separate, explicit
  step the loop performs *after* getting a cell's result back, not
  something `_execute_cell` does itself.

This shape — pure per-unit executor, orchestrator-owned checkpointing — is
precisely what a worker-pool dispatch model needs, and is why "extend
`EvaluationService.run`'s loop," not "invent a second orchestrator" or
"repurpose `scheduler.run_sequential_quota`," is the only architecturally
correct v1.6 direction (developed fully in §7-§9).

**Concurrency hazards found in the current shape** (must be resolved by
Phase 2's design, not by touching `scheduler.py`):

1. **`record_context_usage`** (`agent_evaluation.py:1460-1467`, a closure
   over `execution_contexts: list[...]` and `known_context_ids: set[...]`
   local to `run()`) is passed into every `_execute_cell` call and mutates
   those shared, unsynchronized containers whenever a cell executes under
   a not-yet-seen execution context. Under any concurrent dispatch model
   this closure must become owned by a single coordinator (never called
   directly from worker code), or be replaced by workers returning their
   observed context and the coordinator deciding uniquely whether to
   append it — otherwise two workers racing to append the *same* new
   context could corrupt `execution_contexts`/`known_context_ids` or
   (best case) merely waste effort re-detecting an already-known context.
2. **`_write_state`** (checkpoint persistence) must remain single-writer.
   `write_json_atomic` is atomic against *corruption* (a reader never
   observes a half-written file) but not against *concurrent writers*: two
   processes checkpointing the same `evaluation.json` at once would race,
   with the loser's cell(s) silently absent from the file it just
   overwrote (no lock, no merge — confirmed by direct reading; no
   `flock`/`msvcrt` locking primitive exists anywhere in `agent_
   evaluation.py`, `evaluation_history/`, or `paths.py`). Phase 2 must
   ensure exactly one process/thread ever calls `_write_state` for a given
   `evaluation.json`, regardless of how many workers are executing cells.
3. **Completion-order nondeterminism vs. `drift_detected`'s stop-the-
   world `break`** (`agent_evaluation.py:1548-1557`): today, the first
   drifted cell encountered *in matrix order* halts all further
   scheduling. Under concurrent dispatch, "the first drift encountered"
   becomes wall-clock-dependent unless the contract is redefined — see
   §8's explicit treatment.

Per-cell **execution itself** was independently confirmed safe to
parallelize at the process level (§6-§7's granularity analysis depends on
this): `derive_agent_seed` (`python_runtime.py:397`) is a pure SHA-256
function of `(match_seed, slot, agent_id, api_version)` — never a
worker/thread/process identifier, never wall-clock time, never Python's
randomized string hash. Each entrant gets its own `random.Random(seed)`
instance (`python_runtime.py:561`); no gameplay code reads the global
`random` module's default instance. `NativeMatchService`, `Kernel`, and
both Python controllers are constructed fresh per call with no
module-level mutable state (confirmed by direct reading of `match_
service.py`, `core.py`, `python_runtime.py`, `supervised_runtime.py` —
zero `global` statements, zero module-level mutable containers touched by
match execution). Agent source loading (`agent_api.py`'s `load_python_
agent`) imports each agent under a **per-path-hashed, never-reused**
`sys.modules` name (`agent_api.py:176-177`, confirmed by its own comment:
"one-shot dynamic imports under a per-path hashed module name ... never
re-imported"), so even two concurrent loads of the *same* agent id within
one process do not share a cached module object. Every artifact write
(`_finalize_native_artifacts`, `write_json_atomic`) goes through
`tempfile.mkstemp` (OS-guaranteed unique file per call, no fixed
intermediate name collision) followed by an atomic rename to a path that
is unique per cell (`cell.artifact_dir`) — no two cells ever target the
same file.

## 5. Scale / bottleneck measurements

All numbers below are freshly measured against current `HEAD` on this
machine (Windows 11, Python 3.11.9), using an isolated `BYTEFRAY_ROOT`
(never the repository's own data root — same discipline Phase 6 used for
its own native-runtime qualification) with the shipped Python starter
agents (`claimer`, `strider`, `hunter`, `wanderer`, `adaptive` — the five
Agent-API-v1 Python starters; `runner`/`writer`/`seeker`/`spiral` are VM
builtins and cannot be evaluation subjects/opponents, §17 of `docs/specs/
agent_evaluation.md`). These are wall-clock environment evidence, not
CI gates — the same posture `tools/benchmark_platform_scaling.py`
(the existing, permanent v1.4 scaling benchmark already in this repo,
read in full for this investigation) documents for itself.

### 5.1 Process / interpreter startup cost

| Measurement | Median of 3 |
|---|---|
| `python -c "pass"` (bare interpreter) | ~75-80 ms |
| `python -c "import battle_engine"` (package import only) | ~75-77 ms |
| `bytefray --version` (full CLI cold start via `-m battle_engine`) | ~185-189 ms |

Importing `battle_engine` itself adds negligible cost beyond bare
interpreter startup (noise-level). The ~110 ms gap between bare import and
`bytefray --version` is CLI/argparse tree construction plus
`project_info` gathering, paid **once per `bytefray agents evaluate`
invocation**, not once per cell — the whole matrix runs in one process
today (§2, §3). This matters directly for Phase 2 design: a worker model
that spawns a fresh interpreter per cell would pay this cost per cell
(net-negative for the ~85-95 ms/cell workloads measured below); a
long-lived worker-pool model pays it once per worker, amortized over
every cell that worker executes.

### 5.2 Single-cell cost and matrix-size scaling (`--ticks 200`, the CLI default)

Real `bytefray agents evaluate` invocations (subprocess, full CLI
overhead included in the total, then divided out):

| Matrix | Cells | Total wall time | Per-cell (total ÷ cells) |
|---|---|---|---|
| candidate+baseline × 3 opp × 5 seeds, single-orientation | 30 | 2.942 s | ~98 ms |
| candidate+baseline × 3 opp × 5 seeds, both-orientations | 60 | 5.269 s | ~88 ms |
| candidate+baseline × 3 opp × 3 seeds, both-orientations | 36 | 3.277 s | 91.0 ms |
| candidate+baseline × 3 opp × 10 seeds, both-orientations | 120 | 10.597 s | 88.3 ms |
| candidate+baseline × 3 opp × 20 seeds, both-orientations | 240 | 22.054 s | 91.9 ms |

Per-cell cost is **flat (~88-92 ms) as matrix size grows from 30 to 240
cells** — no evidence of superlinear scaling from match execution or
aggregation at this range. This is consistent with, and a little faster
than, the historical figure already on record in `docs/AGENT_LAB.md`
("Performance tradeoff" table): **unsupervised, untraced ~121 ms**/match
(200-tick, `instr_per_tick=8`, Python-vs-Python, template-derived agents,
measured on a different machine/agent set at v0.5-era code). The same
table records **unsupervised+traced ~196 ms** and **supervised+traced
~811 ms** — evaluation cells never trace or supervise (`agent_test.test_
agent(..., timeout=None, trace=False)`, hard-coded, not a caller choice —
§2), so neither of those multipliers applies to `agents evaluate` today,
only to the `agents test`/Agent Lab drill-down workflow it hands off to.

### 5.3 Per-tick scaling (fixed 9-cell matrix, growing `--ticks`)

| `--ticks` | Total (9 cells) | Per-cell |
|---|---|---|
| 200 | 1.059 s | 117.7 ms |
| 1000 | 2.334 s | 259.4 ms |
| 5000 | 9.211 s | 1023.4 ms |

Fitting a line (`per_cell_ms = fixed + slope * ticks`) across these three
points: **slope ≈ 0.18 ms/tick, fixed ≈ 82 ms/cell**. The fixed component
(agent resolution, module import, `reset()`, RNG derivation, artifact
open/close, digest hashing) dominates at the CLI default of 200 ticks
(~82 of ~118 ms, **~70%**); tick execution only becomes the dominant cost
above roughly 1000-1500 ticks. This means: for typical evaluation tick
budgets, **reducing per-cell fixed overhead matters at least as much as
per-tick execution speed** for total evaluation wall time — directly
relevant to whether a worker-pool design amortizes agent-loading cost
across cells assigned to the same worker (it can, and should — see §7).

### 5.4 Checkpoint-write scaling — a real superlinear cost, isolated and quantified

This is a genuine finding, not speculation: running growing single-
orientation matrices at a low tick count (`--ticks 50`, to suppress match-
execution cost and expose checkpoint overhead) showed **per-cell cost
increasing with total cell count**, which should not happen if per-cell
execution cost is independent of matrix size:

| Cells | Total wall time | Per-cell | `evaluation.json` size |
|---|---|---|---|
| 150 | 9.373 s | 62.49 ms | 157,620 B |
| 450 | 31.77 s | 70.6 ms | 462,133 B |
| 900 | 75.765 s | 84.18 ms | 919,671 B |

Cells grew 6×; total time grew 8.08× — genuinely superlinear. Isolating
the cause directly: `_write_state` calls `result_model.write_json_atomic`
on the **entire, growing** cell list after **every single newly-executed
cell** (`agent_evaluation.py:1534-1547`, §2/§4) — there is no checkpoint
batching. Re-running `write_json_atomic` against the actual
`evaluation.json` content already produced by the three runs above
(median of 20 reps each, isolated from match execution entirely):

| Cells | `evaluation.json` bytes | `write_json_atomic` median |
|---|---|---|
| 150 | 157,620 | 4.157 ms |
| 450 | 462,133 | 9.856 ms |
| 900 | 919,671 | 17.298 ms |

A single checkpoint write is itself roughly linear in file size (~1.4 ms
fixed + ~0.0000172 ms/byte, fit from the endpoints; middle point predicts
within 5%). Because a checkpoint fires **once per cell**, and each
checkpoint's cost grows with how many cells have completed *so far*, the
**cumulative** checkpoint-write cost across a full run is the sum of a
linearly-growing series — `O(n²)` in the number of cells, confirmed
directly by the flat-vs-superlinear contrast between §5.2 (per-cell cost
flat, no checkpoint-size effect visible up to 240 cells at 200 ticks,
where the ~88 ms match-execution cost still dwarfs a sub-2 ms checkpoint
write) and this section (per-cell cost visibly climbing once low ticks let
checkpoint cost become a non-trivial fraction of total per-cell time).
Extrapolating the fitted linear-per-write model, cumulative checkpoint
overhead alone reaches roughly **8-9 s at 900 cells** (matching the
observed gap between §5.2's flat-rate extrapolation and the measured 75.8
s total for the 900-cell/50-tick run) and would grow to **minutes** at the
10,000-cell "stress" scale this document recommends in §10 — potentially
comparable to or exceeding total match-execution time at that scale.

**This is not fixed in this phase** (per the governing prompt's scope
discipline: document, don't optimize, unless it blocks valid
characterization — it does not block characterization here, it *is* part
of the characterization). It is, however, a **first-order Phase 2 design
input**: any worker-pool design that dispatches many cells to complete in
quick succession (exactly what parallelism does) will hit this
checkpoint-write cost *more often per wall-clock second* than the serial
loop does today, making batched/coalesced checkpointing (e.g., every K
completions or every T seconds, still always ending on a final, complete
write) a near-necessity for a parallel design to net-positive at large
scale, not an optional optimization. See §9.

### 5.5 Aggregation, replay, and discovery costs (from existing record + inspection)

- **Aggregation** (`aggregate_cells`/`all_subject_aggregates`): plain
  `O(n)` Python loops/comprehensions over already-in-memory
  `EvaluationCell` dataclasses (`agent_evaluation.py:830-914`) — no I/O,
  no hashing, negligible relative to match execution or checkpoint
  writes at any scale measured.
- **Replay/trace generation cost**: evaluation cells never trace
  (§2/§5.2); the `docs/AGENT_LAB.md` table's traced-vs-untraced delta
  (~75 ms, ~62% overhead) is the standing reference for what *would* be
  paid if a future evaluation mode opted into tracing, which nothing does
  today.
- **Discovery/history-listing cost** (a different axis — reading
  *already-written* evaluations back, not producing them): `docs/specs/
  evaluation_history.md` §16 records a directly measured scan+adapt
  benchmark (synthetic 40-cell-shaped v2 artifacts, 5 timed reps): ~18 ms
  at 10 artifacts, ~182 ms at 100, ~1,862 ms at 1000 — judged in that spec
  as "well under two seconds even at 1000 artifacts," not meeting the
  "measurements demonstrate a real requirement" bar for an index. Nothing
  in this investigation contradicts that judgment; v1.6 parallel
  execution does not change discovery's shape (§2's read-only-layer
  finding), so this number is cited as existing context, not re-measured.
- **Memory behavior**: not deeply profiled (out of this phase's
  practical reach given the time budget), but nothing in the architecture
  reading suggests unbounded accumulation beyond the in-memory `matrix`/
  `completed` lists, which are `O(n)` in cell count and already bounded
  by the same scale as the persisted artifact — no caches, no retained
  per-tick replay data beyond one cell's own writer at a time (each
  cell's `JSONLSink`/`TraceWriter` is opened, used, and closed within
  `_execute_cell`'s call to `test_agent`).

## 6. Concurrency options considered

Evaluated against Bytefray's actual execution architecture (§4's findings
above), not chosen by convention:

| Granularity | Verdict | Why |
|---|---|---|
| **Sub-match (within `run_sequential_quota`)** | **Rejected** | Ruleset-v1 entrant turn order is sequential, deterministic gameplay semantics (Invariant #1); parallelizing within a match would change VM/arena mutation order and violate semantic determinism outright. Not a scale question at all — a gameplay-rules question already closed by v1.5. |
| **Match/evaluation-cell-level (one cell = one unit of work)** | **Recommended** | Cells are proven independent (§4): disjoint artifact directories, deterministic seeds independent of any worker identity, no shared mutable gameplay state, no shared caches. This is the only granularity that maps cleanly onto `EvaluationService.run`'s existing per-cell loop without inventing a second orchestration concept. |
| **Evaluation-condition-level (batch by opponent or by seed)** | **Not recommended as the primary unit** | Strictly coarser than cell-level with no independence benefit — a batch of cells sharing an opponent is not "more independent" than individual cells, it only changes dispatch granularity/overhead. Could be a *chunking* detail on top of cell-level dispatch (assigning contiguous matrix ranges to a worker to amortize §5.3's per-cell fixed overhead), not a different correctness model. |
| **Thread-based workers** | **Not recommended for throughput; not unsafe** | The VM and every Python runtime path are pure Python (`pyproject.toml`'s only runtime dependency is PyYAML; no numpy/ctypes/Cython found in `vm.py`/`core.py`/`match.py`) — the GIL prevents genuine wall-clock speedup for CPU-bound match execution under threads. Correctness-wise, threads would very likely be safe (§4's per-cell-state findings hold regardless of thread vs. process — even concurrent `sys.modules` mutation from `load_python_agent`'s per-path-hashed import names was checked and found non-colliding), but they would not deliver the throughput v1.6 exists to provide. |
| **Process-based workers** | **Recommended** | The only granularity that escapes the GIL for CPU-bound VM/Python-agent stepping, matching what §5.1's startup-cost data says is affordable **if workers are long-lived** (pool model, not spawn-per-cell) and what §4 already proved is correctness-safe (process isolation trivially prevents any of the shared-state hazards, even hypothetical ones §4 didn't find). |
| **`multiprocessing`/`concurrent.futures.ProcessPoolExecutor`** | **Usable, but not the first choice — see §7** | Technically process-based, but this codebase has a standing, deliberate architectural decision to avoid `multiprocessing` entirely for exactly this kind of worker: `agent_worker.py`'s own docstring states "No `multiprocessing` is used anywhere, so there is no Windows `freeze_support()` concern." Reintroducing it for v1.6 would reopen a concern this repository has already solved a different way (see §7) for the four PyInstaller-frozen distribution shapes `tools/build_win.ps1` produces. |
| **Reused `subprocess.Popen`-based worker pool** (the pattern `agent_worker.py`/`process_containment.py` already implement and ship, generalized) | **Recommended primary mechanism** | Already Windows-and-Linux-qualified, already frozen-executable-safe (spawn-safe argument-list-only resolution via `launchers.build_agents_command`, the same one every other child process in this codebase uses), already has a proven newline-delimited-JSON wire protocol and Windows Job-Object child-lifetime containment (`process_containment.py`). Extending this pattern to a small pool of long-lived "evaluation cell worker" subprocesses reuses proven infrastructure instead of introducing a new concurrency primitive — directly satisfying "use the v1.5 [era] execution machinery rather than an unrelated path" in spirit, even though (per §4) it is not literally `scheduler.run_sequential_quota`. |
| **Distributed/cloud execution** | **Out of scope** (explicit invariant #8) | Not evaluated further. |

## 7. Recommended concurrency design (for Phase 2 to implement, not this phase)

- **Unit of work**: one `EvaluationCell` (§6). The matrix (`build_matrix`)
  continues to be built once, upfront, entirely by the orchestrator
  process — **never** by a worker — so the planned match set, canonical
  match IDs, entrant identities, seeds, and conditions are, by
  construction, worker-count-independent (§8).
- **Mechanism**: a small pool of long-lived worker **subprocesses**,
  reusing the exact pattern already proven by `agent_worker.py`/
  `process_containment.py` (spawn-safe `launchers.build_agents_command`
  resolution, newline-delimited JSON stdin/stdout protocol, Windows Job
  Object / POSIX `prctl(PR_SET_PDEATHSIG)` child-lifetime binding) rather
  than `multiprocessing`/`ProcessPoolExecutor`, for the frozen-executable-
  safety reason given in §6. Each worker, once started, receives a stream
  of cell-execution requests (candidate/opponent ids, seed, ticks, target
  `artifact_dir` — plain, already-JSON-serializable data, no live Python
  objects need cross the process boundary) and returns each cell's
  outcome fields, amortizing §5.1's ~110 ms extra CLI-vs-bare-import
  startup cost and §5.3's ~82 ms/cell fixed overhead's *process-level*
  share (agent module import per worker, not per cell, if a worker is
  assigned multiple cells for the same agent) across every cell that
  worker executes, not paid once per cell.
- **Coordinator responsibilities** (never delegated to a worker):
  building `matrix`; deciding which cell goes to which worker and in what
  order (deterministic dispatch order, §8); owning `record_context_usage`
  and `_write_state` exclusively (§4's hazards 1-2); deciding, from
  workers' returned results, the final `lifecycle_state`/aggregate/
  comparison exactly as `EvaluationService.run` does today, unchanged.
- **Checkpoint batching** (§5.4): the coordinator should coalesce
  `_write_state` calls — e.g., after every *K* newly-completed cells or
  every *T* seconds, whichever comes first, always still guaranteeing a
  final, complete write at the end and at least one write before any cell
  has a chance to be lost to a crash (preserving the existing "a crash
  during cell 1 still leaves discoverable state" guarantee, just not
  literally "after cell 1" any more). This is a genuine, evidence-backed
  design requirement, not a nice-to-have: without it, a parallel design
  that completes cells faster will pay §5.4's superlinear cost *more
  often per wall-clock second*, potentially erasing some or all of the
  parallelism speedup at large scale.
- **Worker count default**: no recommendation is made here beyond "make
  it explicit and low-risk-default" (e.g., default to serial/1-worker
  unless requested, matching this repo's general pattern of conservative
  defaults — `agent_evaluation.md`'s own "conservative defaults" citation
  for `--seeds`) — sizing against actual CPU core counts and validating
  against Windows-specific process-creation overhead is Phase 2 empirical
  work, not something this phase's measurements (single-process only)
  can respons­ibly extrapolate.

## 8. Proposed deterministic parallel-evaluation contract

Distinguishing, as the governing prompt requires, **semantic determinism**
(the same logical outcome regardless of execution mechanics),
**canonical ordering** (a defined, worker-count-independent order for
anything presented or persisted as a sequence), and **byte-for-byte
reproducibility** (identical bytes on disk) — these are not the same
guarantee and this contract does not blur them:

| Item | Guarantee under N workers | Basis |
|---|---|---|
| Planned match set | **Byte-for-byte identical** to serial | `build_matrix` runs once, only in the coordinator, before any dispatch (§7) — never touched by worker count. |
| Canonical match IDs (`match_id`) | **Byte-for-byte identical** | Pure function of `MatchRequest` content (`canonical_match_id`, `match_service.py:551`) — no worker/process/thread identifier ever enters the hash. |
| Entrant identities | **Byte-for-byte identical** | `EntrantIdentity`/`agent_identity()` are pure functions of resolved `AgentSpec` content (§4). |
| Seeds | **Byte-for-byte identical** | `derive_agent_seed` is a pure SHA-256 function of `(match_seed, slot, agent_id, api_version)` (§4) — confirmed not to read process/thread state. |
| Conditions (`effective_conditions`) | **Byte-for-byte identical** | Computed once per evaluation from the request, never per-cell, never per-worker. |
| Match results (outcome, scores, statistics, per-cell `result_id`) | **Byte-for-byte identical**, *semantically* — each cell's inputs are fully determined by the frozen plan, independent of which worker or when it ran (§4's independence proof) | Same execution boundary (`NativeMatchService.run`) either way; no cell reads any other cell's state. |
| Replay contents | **Byte-for-byte identical per cell** | Replay content is a pure function of one match's own execution, unaffected by concurrency elsewhere. |
| Aggregate results | **Semantically identical, not byte-for-byte across a naive JSON diff** | `aggregate_cells`/`all_subject_aggregates` are pure functions of the **set** of cells (§5.5) — correct regardless of the order cells were *computed* in, provided the coordinator aggregates from the same final cell set. Canonical ordering (`cells` in `evaluation.json`, see below) must still be fixed for the JSON to be byte-comparable at all. |
| Evaluation fingerprint (`evaluation_id`) | **Byte-for-byte identical** | Frozen once, before any cell executes, from `planned_identities` + request fields only (§2) — worker count never enters this hash, and must continue not to. |
| Persisted artifact semantics (`evaluation.json` shape, `cells[]` ordering) | **Canonical ordering required, not naturally free** | See below — this is the one place completion-order nondeterminism must be explicitly designed against, not assumed away. |

**Completion-order nondeterminism, addressed explicitly:** today, `cells`
in `evaluation.json` and the loop that produces them are in **matrix
order** by construction (a serial `for cell in matrix:` loop). Under
concurrent dispatch, cells will *complete* in wall-clock order, which is
not matrix order. The contract this document proposes for Phase 2:

1. **The persisted `cells[]` sequence remains canonically matrix-ordered**
   regardless of completion order — the coordinator reassembles results
   into matrix order before each checkpoint write and before final
   aggregation, exactly as `_checkpoint_cells` (§2) already does today for
   the *resume* case (backfilling not-yet-reached matrix positions from
   prior state, in matrix order) — this is not a new mechanism, it is the
   existing resume-merge mechanism generalized to also cover "not yet
   returned by any worker" the same way it already covers "not yet
   reached by this run's own loop."
2. **`drift_detected`'s stop-the-world `break` (§4, hazard 3) needs an
   explicit Phase 2 decision, not an assumption.** Two honest options,
   named here rather than silently resolved: (a) preserve today's
   semantics as closely as possible by defining "first drift" as the
   first drift **in matrix order among cells that were actually
   dispatched**, and stop dispatching *new* cells once any drift is
   observed, but let already-in-flight cells finish rather than killing
   them mid-match (avoiding partial/corrupt artifacts) — this makes the
   *set* of cells that get a chance to complete a function of worker
   count/dispatch-window size (a real, disclosed behavior change from
   serial execution's exact single-cell granularity, but a bounded and
   explainable one); or (b) change source-drift handling so every already-
   planned cell is attempted regardless of an earlier drift elsewhere, and
   `lifecycle_state`/`abort_reason` are decided once, after the fact, from
   the complete result set. **This document does not choose between (a)
   and (b)** — it is exactly the kind of methodology-affecting decision
   the governing prompt reserves for a deliberate Phase 2 design step, not
   an incidental side effect of adding workers.
3. **Aggregation and comparison remain last-step, whole-set operations**
   (as today) computed once, after every dispatched cell has returned or
   the run has otherwise reached its terminal point — never incrementally
   recomputed per-worker-completion, avoiding any need for aggregation
   itself to be concurrency-aware.

## 9. Artifact / order / resume implications

- **`evaluation.json`'s schema does not need to change** for parallel
  execution per se (no new required field is implied by anything in this
  contract) — `execution_context_id` (already present, §2) already
  supports "which environment actually ran this cell" per cell, which is
  exactly the provenance question a multi-worker run raises; nothing new
  is needed there. Whether Phase 2 chooses to *additionally* record
  something like a worker index for diagnostic purposes is a Phase 2
  product decision, not an architectural requirement surfaced by this
  investigation.
- **Resume must treat "cell attempted by a worker that crashed mid-run"
  as a first-class case**, distinct from today's binary "cell present in
  prior state" / "cell absent." A worker process dying between accepting
  a cell and the coordinator recording its result must not silently drop
  that cell from the matrix — it must be re-dispatched on resume/retry,
  the same way an ordinary `pending` cell is today. This falls out
  naturally if workers report success only after the coordinator has
  durably recorded the result (never optimistically marking a cell
  "assigned" as if it were "completed"), but must be tested explicitly
  (§14).
- **`--retry-failed` semantics are unaffected in shape** (still "re-
  execute only `failed` cells") but its *scheduling* — which worker picks
  up a retried cell, and whether retries can run concurrently with the
  first pass of a resumed run — is a Phase 2 design detail this document
  flags but does not resolve.
- **The batched-checkpoint proposal (§7/§8) changes the *frequency*, not
  the *meaning*, of "durable state" — `lifecycle_state == "running"`
  continues to mean exactly what it means today** (§5 of `docs/specs/
  evaluation_history.md`): scheduler not yet at its terminal point.
  Nothing about batching changes when `"finished"`/`"aborted"` get
  written — only how often `"running"`'s intermediate snapshots update.
- **`evaluation_history/`'s read side needs no change** (§2, §5.5) — it
  already treats `evaluation.json` as a fully self-describing artifact and
  never assumes anything about how it was produced.

## 10. Recommended evaluation scale targets

Derived directly from §5's measurements, not chosen a priori:

| Target | Concrete size | Rationale |
|---|---|---|
| **Small developer smoke matrix** | **~12-20 cells** (e.g. 1 candidate, 2-3 opponents, 2-3 seeds, single-orientation) | At §5.2's measured ~88-95 ms/cell plus ~185 ms one-time startup, this completes in **under 3 s** — fast enough for an author to run after every small agent edit, the same "run it constantly during development" use case `docs/AGENT_LAB.md`'s own tracing-cost design already optimizes for (§2/§10 of `docs/specs/agent_evaluation.md`). |
| **Normal interactive evaluation** | **~40-80 cells** (matches this repository's own historical reference matrix: 1 candidate + 1 baseline × 4 opponents × 5 seeds = 40 single-orientation, or 80 with the current both-orientations default) | §5.2 measured this exact shape's smaller cousins directly (30-240 cells, flat ~88-92 ms/cell) — at 80 cells, roughly **7-8 s** total, matching `docs/specs/agent_evaluation.md` §10's own (previously unfilled) extrapolation of "roughly 5 seconds" for the pre-orientation-doubling 40-cell case. This is the size an author runs to get a real regressions/improvements report, not just a smoke check. |
| **Large evaluation** | **~500-1,000 cells** | §5.2's flat per-cell scaling is confirmed up to 240 cells; §5.4's checkpoint-write superlinearity was directly measured starting to bite in exactly this range (150-900 cells), making this the smallest scale at which the current architecture's genuine bottleneck (not match execution) becomes visible — the right size to validate that Phase 2's checkpoint-batching design (§7) actually neutralizes it, and to get a meaningful, not-noise-dominated read on parallel speedup. |
| **Stress / qualification evaluation** | **~5,000-10,000 cells** | Extrapolating §5.4's fitted linear-per-write model, cumulative checkpoint overhead at this scale would reach the **many-minutes** range under today's unbatched-checkpoint architecture — a genuine stress test of whether Phase 2's design choices (batched checkpointing, process-pool dispatch, canonical-ordering reassembly) hold up, not an arbitrary "big number." This is also the scale at which Windows process-creation overhead for a subprocess-pool design (§7) would first become measurable relative to total run time and should be specifically re-checked in Phase 2. |

## 11. Preset / suite architecture recommendation

Not implemented this phase, per the governing prompt. Recommendation,
grounded in what already exists rather than invented from scratch:

- **Model**: exactly the prompt's preferred shape — *named reusable
  definition → fully resolved explicit `EvaluationRequest` → canonical
  execution*, with the preset itself **never** entering `evaluation_id`'s
  hash (mirroring how `--seed-range` is already expanded to explicit
  seeds once, at parse time, before anything downstream ever sees it was
  a range — `agent_evaluation.py`'s `parse_seed_range`). A preset is
  purely an input-construction convenience; the moment it is resolved
  into a concrete `EvaluationRequest`, it is indistinguishable from one
  typed out by hand, and `EvaluationService.run` never needs to know a
  preset was involved at all.
- **Storage format**: a small, additively-versioned schema of its own
  (e.g. `bytefray.evaluation_preset` v1), following this repository's
  established one-schema-per-artifact-kind convention (`bytefray.agent_
  trace` v1, `bytefray.evaluation` v1→v2) rather than overloading the
  `bytefray.evaluation` artifact schema, which describes a *result*, not
  a *definition*. YAML is the natural fit given `agent.yaml` manifests
  are already the project's convention for small, hand-editable,
  human-authored configuration; JSON (matching `battle.config.legacy.
  json`) is an equally defensible alternative — this is a stylistic
  choice for Phase 2, not an architectural one.
- **Where it lives**: **user/data-root configuration, not evaluation
  artifacts** — a preset describes "what to run," a `bytefray.evaluation`
  artifact describes "what happened when it ran." Conflating the two
  would let a preset edit silently reinterpret a past evaluation's
  meaning, exactly the "hidden methodology switch" the governing prompt
  warns against. A natural location is a `presets/` (or `eval_presets/`)
  directory under `get_data_root()`, sibling to the existing `agents/`
  and `runs/` directories.
- **Override semantics**: any explicit CLI flag/Designer field always
  wins over a preset's corresponding value (standard, unsurprising
  layering) — a preset supplies defaults for whatever isn't explicitly
  overridden, then the merge result is validated and hashed exactly as an
  ordinary `EvaluationRequest` is today. No new validation path is
  needed; `EvaluationService._validate`/`preflight` (§2) is unchanged.
- **Resolved-configuration persistence**: whatever preset (if any) was
  used, and its own content fingerprint, should be recorded in `evaluation.
  json` **for human/provenance reference only** (mirroring exactly how
  `ProjectInfo`/package version is recorded verbatim today but
  deliberately excluded from `evaluation_id`'s hash, §2/§9 of `docs/specs/
  evaluation_history.md`) — never as something the identity or execution
  path depends on.
- **Compatibility/fingerprint implications**: none, by construction — a
  preset resolves to values already inside `evaluation_id`'s existing
  hash surface (candidate/baseline/opponent identities, seeds, ticks); no
  new hash input is required unless Phase 2 decides preset identity
  itself should be a first-class, separately-versioned axis, which this
  document does not recommend without a concrete product need for it.
- **CLI integration**: `bytefray agents evaluate --preset <name> [explicit
  overrides...]`, plus a small `bytefray agents evaluate-presets
  list|show` pair mirroring the already-established `agents evaluations
  list|show` read-only pattern (`evaluation_history/cli.py`, §2).
- **Designer integration**: a preset dropdown in `EvaluationDialog`
  pre-filling fields, still producing exactly one CLI invocation (§3) —
  no Designer-side special-casing, consistent with every other Designer
  workflow in this codebase.

## 12. Statistical-analysis data inventory

**Already directly observable**, no new capture required (`EvaluationCell`/
`SubjectAggregate`, §2): per-cell outcome (win/loss/tie/init-failed),
`score_subject`/`score_opponent`, `territory_subject`/`territory_
opponent`, `ticks_run`, seed, opponent identity, orientation; per-subject
`matches_played`/`wins`/`losses`/`ties` with an always-shown denominator
(`win_rate_display`, §2), `score_avg`/`score_differential_avg`, `territory_
avg`/`territory_differential_avg`, `ticks_avg`, and — already shipped, not
hypothetical — a full **orientation-scoped** breakdown (`all_subject_
aggregates` already computes `"all"`/`"candidate_first"`/`"opponent_
first"` views side by side, §2). Opponent- and seed-scoped breakdowns are
the same aggregation function applied to a filtered cell subset (one
implementation, two call sites, per the existing "avoid two aggregation
implementations that could independently drift" design note in `docs/
specs/agent_evaluation.md` §11).

**What would be statistically defensible** if Phase 4/5 add inferential
statistics on top of this: given `compare_candidate_baseline` (§2)
already aligns candidate and baseline cells **pairwise by exact
`(opponent_id, seed)`** (not pooled), the natural, already-supported
significance test is a **paired** one over those aligned win/loss/tie
outcomes (e.g., McNemar's test on the paired win/loss table, or a sign
test treating the existing `classify()` rank-delta as the paired
statistic) — not an unpaired two-proportion z-test, which would discard
the pairing structure the codebase already went to the trouble of
building and computing. A Wilson (not naive normal-approximation) score
interval on a single subject's pooled win rate is defensible as a
description of uncertainty *about this specific finite sample*, provided
it is disclosed honestly as such — not as "the agent's true strength
across all possible seeds," since seeds here are a small, literal,
author-chosen list (§2, `docs/specs/agent_evaluation.md` §3), not draws
from a randomly-sampled population.

**What would be misleading if implemented naively**, matching the
governing prompt's explicit ask to separate the two: (1) pooling wins/
losses across *different opponents* into one binomial test — opponents
are a real, non-random blocking factor (different opponents have
systematically different difficulty), so pooling inflates apparent
significance; any pooled test should at minimum disclose or control for
this, and a per-opponent-blocked test is preferable given the data is
already opponent-labeled. (2) Treating score/territory differentials as
normally distributed for a t-test without evidence of near-normality,
especially at small seed counts. (3) Comparing aggregates **across
different evaluation runs** (different opponent/seed sets) without going
through the existing `condition_key`/alignment machinery in `evaluation_
history/comparison.py` (§2) — that machinery exists specifically because
naive cross-run averaging is exactly the kind of comparison this
codebase has already identified as invalid without exact condition
matching.

## 13. Behavior-profile data inventory

**Directly observable today**, from already-persisted artifacts, no new
instrumentation: per-match `alive_ticks`, `kills`, `deaths`, `cpu_total`,
`mem_writes`, `territory_last`/`territory_max`/`territory_avg` and their
percentage forms (`NativeAgentResult`, `match_service.py`), full per-tick
replay content (memory diffs, ownership changes) via `iter_replay`, and —
already computed by existing client tooling, not hypothetical —
territory-over-time trajectories via `battle_client.analysis.compute_
territory_history` (used today by `tools/benchmark_platform_scaling.py`'s
own replay benchmark, confirming this function is already exercised
against real replay data).

**Derived, computable now without new capture**: survival-time
distribution across seeds (from `alive_ticks`/`termination_reason`
already in every cell); territory expansion/contraction rate
(differentiate `compute_territory_history`'s existing output); write-
pattern concentration vs. spread (from `mem_writes` combined with
territory-bucket data `ScoringPolicy`/`StatisticsCollector` already
track, `config.py`'s `Weights.territory_bucket`); and — the single
strongest **already-shipped** first-mover-sensitivity signal —
orientation-split aggregates (§2, §12): an agent whose `candidate_first`
and `opponent_first` win rates diverge sharply is, by construction,
exhibiting first-mover-dependent behavior, exactly the kind of
"superficial difference vs. genuine strategy difference" signal the
governing prompt's behavior-profile goal describes, without any new
metric being invented.

**Speculative, requiring validation before trust** (explicitly not
implemented, per the governing prompt): any composite "aggression score"
or "territorial score" combining several of the above into one number —
flagged the same way §11 of `docs/specs/agent_evaluation.md` already
flags a lexicographic win/score/territory comparator: technically
possible, not something the engine itself treats as ordered, and easy to
overclaim. Clustering agents into strategy archetypes from these metrics
is explicitly out of scope for this phase and would need validation
against a fixture set of *known*-different-strategy agents (e.g. the
existing starter agents, whose strategies are already documented in each
one's own module docstring, §13's inventory source) before any clustering
result could be trusted to mean what it claims to mean.

## 14. Required Phase 2 regression tests

Grounded in §1's existing test inventory and §4/§8's specific hazards —
not a generic checklist:

- **Serial-vs-parallel equivalence**: run the same `EvaluationRequest`
  once serially (`workers=1` or today's unmodified path) and once with
  N>1 workers; assert identical `evaluation_id`, identical (matrix-
  ordered) `cells[]` content field-for-field except any newly-added
  purely-diagnostic field (e.g. a worker index, if Phase 2 adds one),
  identical aggregates, identical per-cell `match_id`/`result_id`/replay
  bytes. This is the direct v1.6 analogue of `test_ruleset_v1_
  equivalence.py`'s golden-corpus role for v1.5 (§1) — and that file
  itself, unmodified, is a **strong existing oracle** that per-cell match
  execution is unaffected by anything Phase 2 touches, since Phase 2
  must not touch `NativeMatchService`/`scheduler.py`/`ruleset_policy.py`
  at all (§4).
- **Multiple worker counts** (e.g. 1, 2, 4, and a count exceeding the
  matrix size) against the same fixed matrix, asserting the equivalence
  above holds for every count, not just one.
- **Repeated execution**: the same request run twice independently
  (fresh output directories) with the same worker count produces
  identical results both times — protects against any residual
  nondeterminism (e.g. dict/set iteration order in whatever dispatch
  structure Phase 2 introduces).
- **Evaluation resume** under concurrent dispatch: interrupt a running
  parallel evaluation (simulated coordinator/worker kill) mid-matrix,
  resume it, and confirm the result is identical to an uninterrupted run
  — extending the existing resume test pattern already proven in
  `test_agent_evaluation.py`'s resume coverage (§1) to the new "worker
  died with a cell in flight" case named in §9.
- **Partial worker/match failure**: one worker crashes or one cell raises
  `AgentTestError` while others continue — assert the surviving cells'
  results are unaffected and the failed cell is correctly reported
  (`failed` status), not silently dropped or duplicated.
- **Deterministic identities under concurrency**: `derive_agent_seed`/
  `canonical_match_id`/`evaluation_id` golden-vector-style tests
  (mirroring `test_python_runtime.py::test_derive_agent_seed_golden_
  vectors`, §1) re-asserted specifically under multi-worker execution,
  not just single-process unit tests — closing the gap between "the
  function is provably pure" (this document's §4/§8 analysis) and "the
  actual multi-process wiring doesn't accidentally smuggle a worker
  identifier into an input" (only an integration-level test can catch
  that class of bug).
- **Canonical artifact ordering**: `cells[]` in `evaluation.json` is
  matrix-ordered regardless of completion order or worker count —
  directly testing §8's canonical-ordering guarantee, including a
  specifically-constructed case where completion order is deliberately
  reversed relative to matrix order (e.g. via artificial per-cell delay
  injection in a test double).
- **The `drift_detected` stop-the-world decision** (§8, whichever of
  options (a)/(b) Phase 2 chooses) needs its own explicit test proving
  the chosen behavior, since this document deliberately leaves that
  choice open.
- **Windows-specific**: subprocess-pool startup/teardown behavior,
  including that `process_containment.py`'s Windows Job Object binding
  correctly cleans up all worker processes if the coordinator is killed
  (extending `test_process_containment.py`'s existing 7-test coverage,
  §1, to the new multi-worker case rather than the single supervised-
  agent-worker case it covers today).
- **Linux-specific**: the POSIX `prctl(PR_SET_PDEATHSIG)` path
  (`process_containment.py`, also already covered for the single-worker
  case by `test_process_containment.py`) under a worker pool, and a
  genuine (not `/mnt/`-bridged) Linux run of the full new parallel test
  set — following Phase 6's own documented caution about WSL cross-
  filesystem I/O speed distorting timing-sensitive results (§1's baseline
  section, Phase 6's "Platform qualification").
- **Frozen/packaged execution**: at least a smoke-level check that a
  subprocess-pool worker launched from a frozen `bytefray.exe`
  (`tools/build_win.ps1`'s output) still resolves and spawns correctly
  via the existing `launchers.build_agents_command` frozen-or-source
  path — the specific risk named in §6/§7 for why `multiprocessing` was
  not recommended.

## 15. Risks and unresolved questions

- **The `drift_detected` semantics choice (§8)** is a genuine open
  design question, not merely an implementation detail — it changes
  which cells get a chance to run after a drift is detected, a
  user-visible behavior difference from serial execution that must be
  decided deliberately and documented, not defaulted into.
- **Checkpoint-batching interval choice (§7)** trades "how much work can
  be lost on an ungraceful crash" against "how much §5.4 overhead is
  avoided" — needs an explicit, disclosed default (e.g. bounded by both a
  cell count and a wall-clock interval) rather than an arbitrary number.
- **Worker-count defaults and auto-detection** (CPU count, Windows
  process-creation overhead at the low end of matrix sizes where §5.1's
  fixed costs could make more workers a net loss for small matrices) is
  empirical work this single-process-only measurement phase could not
  responsibly perform — flagged for Phase 2, not guessed at here.
- **Whether resume state itself needs a schema change** to robustly
  represent "a cell a worker had accepted but not yet completed when the
  process ended" (§9) — this document recommends that no such state ever
  become durable in the first place (a cell is either fully recorded or
  treated as `pending`), which sidesteps the schema question, but Phase 2
  must confirm no code path can create a durable "in progress" state that
  resume logic doesn't already know how to treat as `pending`.
- **This investigation measured only single-process serial execution
  directly** (§5) — every parallel-specific number in this document (worker
  startup amortization, expected speedup, actual behavior of a subprocess
  pool under load) is architectural reasoning from §4's correctness
  findings plus §5's serial measurements, not a measured parallel result,
  because no parallel code exists yet. Phase 2 must re-measure, not
  merely assume, once a real implementation exists.
- **`--single-orientation`'s interaction with future preset defaults**
  (§11) is unresolved — whether a preset can/should override the
  both-orientations default is a Phase 2+ product question, noted here
  only because §5.2/§10's scale numbers are sensitive to it (both-
  orientations roughly doubles matrix size for the same nominal
  opponent/seed count).

## 16. Exact files/modules expected to change in Phase 2

Based directly on §4's architecture reading — this list is a prediction
grounded in where the actual seams are, not a guess:

- **`engine/src/battle_engine/agent_evaluation.py`** — `EvaluationService.
  run`'s `for cell in matrix:` loop (§2/§4/§7) is the primary site of
  change: replacing (or wrapping) direct sequential `_execute_cell` calls
  with dispatch to a worker pool, redesigning `record_context_usage`'s
  ownership (§4 hazard 1), and batching `_write_state` calls (§7/§9).
  `_execute_cell` itself likely needs to become callable from a worker
  process's own entry point with the same inputs/outputs, but its
  *logic* should not need to change (§4 already found it side-effect-
  clean apart from the closure hazard).
- **A new worker-process module**, analogous to `engine/src/battle_
  engine/agent_worker.py` (§6/§7) — an "evaluation cell worker" reusing
  `launchers.build_agents_command`/the newline-delimited-JSON protocol
  pattern, reached through a new hidden CLI verb (mirroring `agents
  _worker`'s existing pattern) rather than `multiprocessing`.
- **`engine/src/battle_engine/process_containment.py`** — likely reused
  as-is (its `bind_child_to_parent_lifetime` is already generic over "a
  subprocess," not specific to the single-agent-worker case), but its
  test coverage (§14) needs extending to a multi-worker scenario.
- **`engine/src/battle_engine/agent_evaluation.py`'s CLI surface**
  (`_parser`, `main`, §2) — a new `--workers`/similar flag, plus (if §11's
  preset recommendation is picked up in the same phase) `--preset`.
- **A new, small preset module** (§11) if Phase 2 chooses to implement
  presets alongside parallelism — this document recommends against
  conflating the two pieces of work unnecessarily, but notes the CLI
  surface change would land in the same file either way.
- **Not expected to change**: `engine/src/battle_engine/scheduler.py`,
  `ruleset_policy.py`, `rules.py`, `match_service.py`, `match.py`,
  `core.py`, `vm.py`, `python_runtime.py`, `supervised_runtime.py`,
  `scoring.py`, `statistics.py`, `telemetry.py`, `replay.py`,
  `result_model.py`, `entrant_identity.py` — every one of these sits
  below or outside the evaluation-orchestration seam (§3's flow diagram)
  and none of Phase 2's design as recommended here has any reason to
  touch Ruleset-v1 gameplay, per-match execution, or persisted-schema
  code at all. `engine/src/battle_engine/evaluation_history/*` is
  expected to need **no** change (§2/§9) beyond whatever tests confirm it
  still reads Phase 2's output correctly.
- **`docs/AGENT_LAB.md`, `docs/specs/agent_evaluation.md`, `docs/specs/
  evaluation_history.md`, `docs/ROADMAP.md`, `docs/FUTURE_PLANS.md`** —
  documentation updates once Phase 2 lands, following this repository's
  existing convention of keeping specs/roadmap synchronized with shipped
  behavior (already true of every v1.5 phase doc read for this
  investigation).

## 17. Final verdict

**READY FOR PARALLEL-EVALUATION IMPLEMENTATION**, conditioned on Phase 2
explicitly resolving the two open design questions this document
deliberately leaves unresolved rather than defaulting (§8's `drift_
detected` semantics choice, and §7/§15's checkpoint-batching interval),
and on Phase 2 re-measuring §5's numbers against its actual
implementation rather than treating this document's architectural
reasoning as a substitute for that measurement (§15).

This verdict rests on direct evidence, not optimism: the real seam for
v1.6 parallelism (`EvaluationService.run`'s per-cell loop) was identified
and verified from source, not assumed (§4); the v1.5 scheduler
abstraction was verified to be a *different*, correctly-untouchable
abstraction rather than incorrectly assumed sufficient (§4, directly
answering the governing prompt's explicit caution); every cell-level
independence claim underlying the proposed contract (§8) was checked
against actual source — deterministic seeding, absence of shared mutable
gameplay state, absence of harmful `sys.modules`/import caching, atomic
per-cell artifact writes — rather than assumed from architecture-diagram
intent; and the one genuine architectural risk this investigation
surfaced (§5.4's superlinear checkpoint-write cost) was not just
identified but isolated and quantified with a dedicated measurement,
giving Phase 2 a concrete, evidence-backed reason to design checkpoint
batching in from the start rather than discovering the problem after
implementation at the "stress" scale (§10) where it would first become
painful.

No architectural rework is required before Phase 2 begins. The v1.5
architecture's own boundaries — the execution boundary
(`NativeMatchService`), the entrant-identity/execution-state separation,
the Ruleset policy dispatch seam, and (critically, and separately) the
already-existing evaluation-orchestration seam one level above all of
that — are exactly the boundaries v1.6 parallel evaluation needs, and
none of them need to move.
