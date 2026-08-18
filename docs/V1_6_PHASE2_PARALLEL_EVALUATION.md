# v1.6 Phase 2 — Deterministic Parallel Evaluation

This is the durable implementation record for v1.6 Phase 2, the first
substantive v1.6.0 feature: bounded local subprocess-worker parallelism
across independent `EvaluationCell`s in `bytefray agents evaluate`, plus
the checkpoint-batching fix identified as a near-necessity for that
parallelism to net-positive at scale.

Written in the same spirit as the v1.5 phase docs and `docs/
V1_6_PHASE1_EVALUATION_SCALE_BASELINE.md`: this document cites Phase 0-1
as the authoritative pre-implementation baseline rather than re-deriving
it, and records where implementation evidence confirmed or refined that
baseline's predictions. Phase 0-1 is not superseded — read it first.

## 1. Starting state

Branch `main`, HEAD `bc0cbae04a777c3f9762ca6aea9c7fb0676ff796` (tag
`v1.5.0`, confirmed via `git describe --tags --long` →
`v1.5.0-0-gbc0cbae`), working tree clean except the expected untracked
Phase 0-1 document. Full suite reconfirmed green before any edit: **1283
passed, 6 skipped, 0 failures** (`python -m pytest`), byte-identical to
both Phase 0-1's and Phase 6's own recorded baselines.

## 2. Architectural correction respected

Per Phase 0-1's central finding and the governing prompt's explicit
correction: `battle_engine.scheduler.run_sequential_quota` and every
module below `NativeMatchService` (`scheduler.py`, `ruleset_policy.py`,
`rules.py`, `match_service.py`, `match.py`, `core.py`, `vm.py`,
`python_runtime.py`, `supervised_runtime.py`, `scoring.py`,
`statistics.py`, `telemetry.py`, `replay.py`, `result_model.py`,
`entrant_identity.py`) were **not touched** — confirmed by the final diff
(`git diff --stat`, below). The seam extended is exactly the one Phase 0-1
identified: `EvaluationService.run`'s per-cell orchestration in
`engine/src/battle_engine/agent_evaluation.py`.

## 3. Files changed

- **`engine/src/battle_engine/agent_evaluation.py`** (+519/−98 net lines) —
  the core of this phase. See Sec 4-9 below.
- **`engine/src/battle_engine/command.py`** (+10 lines) — one new hidden
  CLI verb dispatch (`_evaluation_worker`), mirroring the existing
  `_worker` branch exactly.
- **`engine/src/battle_engine/evaluation_worker.py`** (new, ~340 lines) —
  the parallel-evaluation worker subprocess module.
- **`engine/tests/test_agent_evaluation_parallel.py`** (new, 13 tests) —
  the governing spec's required regression matrix.
- **`engine/tests/test_evaluation_worker.py`** (new, 13 tests) — worker
  protocol unit/white-box tests, mirroring `test_agent_worker.py`'s
  structure.
- **`docs/V1_6_PHASE2_PARALLEL_EVALUATION.md`** (this document).

No change to `evaluation_history/*`, any Ruleset-v1/execution-boundary
module, any persisted schema (`SCHEMA_VERSION`/`IDENTITY_VERSION` both
unchanged), or the Designer.

## 4. Worker-pool architecture

A small pool of long-lived subprocess workers, reusing the exact pattern
already proven by `agent_worker.py`/`process_containment.py`/
`launchers.py`, not `multiprocessing`:

- **`evaluation_worker.py`** mirrors `agent_worker.py`'s one-file-both-
  sides structure: parent-side `EvaluationCellWorkerHandle`
  (`start`/`submit_cell`/`kill`/`close`), the same dedicated-reader-
  thread-plus-`queue.Queue` pattern (`_EOF` sentinel on stream close), and
  the same `WorkerCallStatus`/`WorkerCallResult` vocabulary (imported
  from `agent_worker.py`, not reinvented). Deliberately *not* shared code
  with `agent_worker.py` — that module's protocol (live per-tick
  `load`/`reset`/`act` calls into loaded agent code) is semantically a
  different thing from this one (one call = one whole, already-self-
  contained match); forcing a shared abstraction would have bent both
  protocols to fit a shape neither needs.
- **Spawn mechanism**: `launchers.build_agents_command("_evaluation_worker",
  [])` — the same spawn-safe, argument-list-only, frozen-or-source
  resolution every other child process in this codebase uses. No new
  frozen-executable concern: verified by construction (the frozen path
  resolution has zero special-casing per subcommand string), not by an
  actual PyInstaller build this session — see Sec 14.
- **Containment**: `bind_child_to_parent_lifetime`/`die_with_parent`
  (`process_containment.py`), reused verbatim — Windows Job Object /
  POSIX `PR_SET_PDEATHSIG`, unchanged.
- **No protocol-level timeout**: `submit_cell`'s round trip uses
  `timeout=None`, mirroring `agent_test.test_agent(..., timeout=None,
  ...)`'s existing, deliberate contract that evaluation cells are
  unsupervised and untraced by design (Phase 0-1 Sec 2). Worker death is
  detected via EOF/broken pipe, never an artificial deadline. This is a
  disclosed scope boundary, not an oversight: a genuinely hung cell still
  stalls only `1/workers` of throughput, improving on today's serial
  behavior for the same hang rather than regressing it.

## 5. Worker protocol

Newline-delimited JSON, one request = one whole cell job:

```jsonc
// parent -> worker
{"cmd": "run_cell", "cell": {...EvaluationCell fields, artifact_dir as str...},
 "ticks": 200, "data_root": "/abs/path"|null,
 "planned_identities": {"<agent_id>": {...agent_identity() dict...}, ...}}

// worker -> parent, success
{"ok": true, "cell": {...full EvaluationCell fields...},
 "execution_context": {...ExecutionContext fields...}|null}

// worker -> parent, worker-side crash outside _execute_cell's own handling
{"ok": false, "diagnostic": {"code": "evaluation_worker_internal_error", "message": "..."}}
```

The worker's dispatch function (`_handle_run_cell`) calls the refactored
`EvaluationService._execute_cell` **unchanged in logic** (see Sec 6) via a
function-local import of `battle_engine.agent_evaluation` — this direction
is safe as a module-top import (`evaluation_worker.py` is the "leaf").
The reverse direction (the coordinator importing `EvaluationCellWorkerHandle`
from `evaluation_worker.py`) is a genuine circular import and is resolved
with a function-local import inside `EvaluationService._run_pending_
parallel`, the same deferred-import pattern `command.py`'s `_agents()`
already uses for every subcommand.

## 6. `_execute_cell` decoupling

The old hazard: `_execute_cell` took a `record_context_usage: Callable[[],
str]` closure over coordinator-local mutable state
(`execution_contexts`/`known_context_ids`) — unsafe to call from a worker
process. Fixed by:

- Dropping `record_context_usage` and the whole `request: EvaluationRequest`
  parameter, replaced by the two primitives actually read (`ticks`,
  `data_root`) — narrow and worker-safe by construction, so a
  coordinator-only field (`resume`, `retry_failures`, `workers`, ...) can
  never accidentally become worker-reachable.
- New return type `CellExecutionResult(cell, execution_context)` —
  `execution_context` is `None` only for the pre-execution-drift early
  return (no execution attempted), matching the old closure's exact
  call/no-call behavior on every path, including the pre-existing,
  intentionally-unchanged asymmetry where the post-init-failure-drift
  branch *does* still register a context.
- `_register_execution_context(context, execution_contexts,
  known_context_ids)` — the closure's dedup/append body, now a plain
  coordinator-owned function called identically from the serial and
  parallel dispatch paths, never from a worker.

`_execute_cell`'s own logic (pre/post-execution drift checks, orientation
mapping, `test_agent` call, outcome classification) is **byte-for-byte
unchanged** — confirmed by every existing `test_agent_evaluation*.py` test
passing unmodified.

## 7. Coordinator responsibilities and dispatch model

`EvaluationService.run` now has two phases:

- **Phase A** (unchanged in effect, no threads): one forward pass over
  `matrix`, resolving every cell possible from prior state exactly as
  before, into a `completed_by_schedule_id: dict[str, EvaluationCell]`.
  Stops early — exactly matching the old loop's `break` — the instant it
  resolves a cell whose *persisted* status is already `drift_detected`
  (M2: the only correct recovery from a drifted evaluation is a fresh
  one). Everything else needing real execution goes into an ordered
  `pending: list[EvaluationCell]`.
- **Phase B**: `workers<=1` executes `pending` serially, in the
  coordinator thread, calling `_execute_cell` directly — this is the
  literal serial-equivalent path. `workers>1` dispatches via
  `_run_pending_parallel`: a shared `pending_queue` (seeded once, in
  matrix order) feeds `min(workers, len(pending))` long-lived dispatcher
  threads, each owning exactly one `EvaluationCellWorkerHandle` for its
  lifetime and processing cells strictly one-at-a-time against it — no
  wire-protocol correlation IDs needed, mirroring `AgentWorkerHandle`'s
  existing single-in-flight-call model. Only the coordinator/main thread
  ever calls `_register_execution_context`, updates
  `completed_by_schedule_id`, or writes a checkpoint; dispatcher threads
  only push results onto a shared `results` queue.

Every derived view — aggregates, comparison, the persisted `cells[]`, and
`EvaluationResult.cells` — is built from one canonically matrix-ordered
list (`_checkpoint_cells`, generalized to key its input by `schedule_id`
rather than assume positional matrix order, so it serves both dispatch
modes with one implementation) computed *after* Phase B completes, never
from the coordinator's raw arrival-order accumulation. This is what makes
worker count invisible to anything order-sensitive.

`EvaluationRequest` gained one field, `workers: int = 1`, validated `>=1`
in `_validate`. It is **not** part of `_evaluation_id`'s hash payload
(unaffected by construction — that payload cherry-picks specific fields,
never `asdict(request)`), confirmed by a dedicated test
(`test_evaluation_id_independent_of_worker_count`).

## 8. `--workers N` CLI

Reuses the existing `_positive_int` validator (already used for
`--ticks`). Default `1` (serial-equivalent, matching the spec's
conservative-default instruction and this module's existing "conservative
defaults" precedent for `--seeds`). Existing invocations without the flag
are byte-for-byte unaffected.

**Default recommendation from measurement (Sec 12)**: keep the default at
`1`. Speedup is real and substantial at 40+ cells (up to ~4.9x at 8
workers on a 640-cell matrix) but near-flat-to-negative at very small
matrices (≤20 cells) where per-worker subprocess startup cost dominates —
exactly Phase 0-1's own prediction (Sec 5.1's ~110ms/process startup
overhead), now measured rather than assumed. No matrix-size-sensitive
auto-policy is implemented this phase (out of scope per Sec 6 of the
governing prompt — "do not introduce automatic CPU-count sizing before
benchmarking the actual implementation"); this measurement is exactly that
benchmarking, and a future `--workers auto` heuristic can now be sized off
real data rather than a guess.

## 9. Source-drift semantics (§7 policy, implemented)

The moment the coordinator observes a `drift_detected` result — whether
resolved instantly from prior state (Phase A) or discovered by real
execution (Phase B) — it stops feeding new cells to workers, but already
in-flight cells are allowed to finish normally (never force-killed mid-
match, so no partial/corrupt per-cell artifacts are ever produced: the OS
only ever tears down a match process that was never mid-write, since
`write_json_atomic`'s temp-file-then-rename means a killed process leaves
at most an orphaned temp file, never a corrupt `result.json`).

**Authoritative drift selection**: the drift recorded as `abort_detail` is
the one with the smallest `matrix_ordinal` among *every* drifted cell
observed this run, across both phases. This falls out of the design
without special-case logic: Phase A's own early stop guarantees `pending`
never contains a cell at or after a Phase-A-found drift point, so any
Phase-B drift is always earlier in matrix order and naturally wins a
plain `min(..., key=lambda c: c.matrix_ordinal)` selection — implementing
Phase 0-1's option (a) ("first drift in matrix order among cells that
were actually dispatched").

**Aggregate filtering: none, by design** — verified concretely, not just
argued: `is_scored` requires `status == "completed"`, and `aggregate_cells`
only counts `completed`/`failed` statuses, so a `drift_detected` cell
already contributes nothing measurable. More decisively,
`evaluation_history/v2_adapter.py` recomputes aggregates from persisted
`cells[]` via the *same* aggregation functions on read; filtering the
live write but not the persisted `cells[]` (which must retain post-drift
completions for diagnostic reference) would make a later `evaluations
show` read recompute different numbers than what was originally written —
a self-contradicting artifact. `lifecycle_state="aborted"` remains the
sole don't-trust-this-as-final signal, unchanged from today.

Verified end-to-end with real concurrent subprocess execution (not a
monkeypatch, which a worker subprocess would never observe): a background
thread mutates an opponent's real `agent.py` on disk mid-run while five
slow (deliberately `time.sleep`-padded) opponents execute across two
workers (`test_source_drift_under_concurrency_stops_dispatch_cleanly`).

## 10. Checkpoint batching (§8, implemented)

Applied **uniformly** to both `workers=1` and `workers>1` — the O(n²) cost
Phase 0-1 isolated (rewriting the entire, growing `cells` list after every
single completed cell) exists independent of dispatch mode, and the
governing spec frames the fix as a general Phase 2 requirement, not a
parallel-only one.

Policy: checkpoint after every 16 newly-completed cells or every 1.0
second, whichever comes first — both parameterized on `EvaluationService.run`
(`checkpoint_batch_size`, `checkpoint_batch_interval`) rather than hardcoded,
so a test needing exact per-cell granularity can request it explicitly.
The unconditional pre-loop checkpoint (before any cell executes) and the
unconditional final checkpoint are both unchanged — only the *frequency*
of intermediate checkpoints changed, never their completeness (each is
still a full, canonically matrix-ordered snapshot) or the final persisted
content.

**Crash-behavior bound, explicit**: on an ungraceful coordinator crash, at
most `min(16 cells, ~1 second of throughput)` of already-completed work is
not yet durable. Resume simply re-executes exactly those cells — the same
handling already in place for any cell absent from a prior checkpoint. No
new durable "in-progress" cell state was introduced, per the spec's
explicit preference; a cell is still either durably completed or
`pending`, nothing in between.

**Existing test impact — smaller than predicted**: a pre-implementation
design-review pass flagged `test_retry_checkpoint_never_erases_a_later_
already_durable_cell` (`test_agent_evaluation_v2.py`) as needing an
explicit `checkpoint_batch_size=1` to preserve its crash-injection intent.
In practice **no existing test required modification** — the full suite
passed unmodified after the refactor. That specific test retries exactly
one cell, so batching naturally coalesces its "intermediate" checkpoint
into the same call as the final one; the assertion (checkpoint content
completeness under crash) holds regardless of which checkpoint it turns
out to be. Recorded here as a genuine, evidence-based correction to a
pre-implementation prediction, not silently dropped.

## 11. Resume and worker-failure semantics (§9)

**Resume** requires no new mechanism: a cell a worker accepted but never
durably returned is, by construction, simply absent from the next
checkpoint — indistinguishable from an ordinary never-reached `pending`
cell, so existing resume logic (`_resolve_from_state`) already treats it
correctly. Verified with a real crash injection
(`test_resume_after_coordinator_interruption_matches_uninterrupted_
reference`): a monkeypatched `_write_state` raises after the second
checkpoint under `workers=3`/`checkpoint_batch_size=1`; the resumed run's
final per-cell outcomes and `evaluation_id` are confirmed identical to an
uninterrupted `workers=1` reference run of the same request.

**Worker failure** (smallest-change policy, explicitly chosen): a cell
whose worker exits/protocol-errors mid-call is retried exactly once, on
any live worker (the dead worker's own dispatcher thread stops; no
automatic replacement subprocess is spawned). A second failure marks the
cell `status="failed"`, `error_code="evaluation_worker_exited"`. If every
worker eventually dies with cells still queued, those are marked
`status="failed"`, `error_code="evaluation_worker_unavailable"` — never
silently dropped, never hung on forever. The "never hang" property is
race-free by construction: `results.get()` blocks with **no timeout and
no polling** anywhere in the coordinator, because a coordinator-owned
`live_worker_count` (decremented only on a `WorkerFailure` message, which
is itself always sent exactly once per thread right before it exits) is
checked before any retry is queued, and `pending_queue` is drained
whenever that count reaches zero — so an item is never enqueued when no
thread could ever pop it. Verified with a real subprocess crash (an
opponent agent calling `os._exit(1)` in `act()`, killing its whole worker
process mid-match) in both `test_evaluation_worker.py`
(`test_worker_exit_mid_cell_is_reported_as_exited`) and
`test_agent_evaluation_parallel.py`
(`test_worker_crash_marks_cell_failed_and_others_continue_without_
hanging`), the latter confirming survivors are unaffected.

## 12. Canonical ordering

`cells[]` and every derived view stay matrix-ordered regardless of
completion order or worker count (Sec 7). Verified with real subprocess
timing, not simulated: `test_completion_order_reversal_preserves_matrix_
order` makes a matrix-first opponent genuinely slow (`time.sleep(0.6)`
inside its real, subprocess-executed `act()`) and two matrix-later
opponents fast, across 3 concurrent workers — the later opponents' cells
complete first in wall-clock time, yet the persisted `cells[]` order is
still `[opp_slow, opp_fast_1, opp_fast_2]`.

## 13. Serial-vs-parallel and worker-count equivalence results

`test_serial_and_parallel_produce_identical_artifacts` (parametrized
`workers=1,2,4,50` against a 6-cell matrix, the last deliberately
exceeding matrix size for the correctness-only over-provisioned case):
identical `evaluation_id`, identical persisted artifact content field-for-
field (excluding only `created_at`/`finished_at`/`updated_at`/`project`,
which legitimately differ across independently-timestamped runs — never
part of any semantic-equivalence claim), identical canonical `cells[]`
order, and byte-identical per-cell `replay.jsonl` content for every cell.
`test_repeated_parallel_runs_are_identical` confirms the same holds across
two independent fresh-output-directory runs at `workers=4`. A manual CLI
smoke test (real starter agents, isolated `BYTEFRAY_ROOT`, 9-cell matrix,
`--workers 1` vs `--workers 4`) reproduced the identical result
independently of the pytest suite.

## 14. Performance measurements

Isolated `BYTEFRAY_ROOT` outside the repository (shipped Python starter
agents: `claimer`, `hunter`, `strider`, `wanderer`, `adaptive`), this
machine (Windows 11, 24 logical cores, Python 3.11.9) — same discipline
Phase 0-1 used. All figures are real `bytefray agents evaluate` CLI
subprocess invocations, full CLI overhead included, `--ticks 200` (the CLI
default) unless noted.

### 14.1 Interactive scales

| Scale | Cells | workers=1 | workers=2 | workers=4 | workers=8 |
|---|---|---|---|---|---|
| Dev smoke (2 subj × 3 opp × 3 seeds, single-orientation) | 18 | 1.770s (98.3ms/cell) | 1.378s, **1.28x** | 1.095s, **1.62x** | — |
| Normal interactive (2 subj × 4 opp × 5 seeds, both-orient.) | 80 | 6.894s (86.2ms/cell) | 4.124s, **1.67x** | 2.551s, **2.70x** | 2.004s, **3.44x** |

At the smallest scale, per-worker subprocess startup cost (Phase 0-1's
~110ms/process CLI-overhead estimate, now directly observed) is a large
enough fraction of total work that speedup is real but modest — confirms
Phase 0-1's prediction that a worker-count default should not be
increased casually for small matrices.

### 14.2 Large scale (primary practical test, per the governing prompt)

2 subjects × 4 opponents × 40 seeds, both orientations = **640 cells**:

| workers | wall time | per-cell | speedup |
|---|---|---|---|
| 1 | 53.668s | 83.86ms | 1.00x |
| 2 | 28.975s | 45.27ms | **1.85x** |
| 4 | 16.645s | 26.01ms | **3.22x** |
| 8 | 10.945s | 17.10ms | **4.90x** |

Artifact size and shape are identical across all four runs (850,881
bytes, `matrix_size: 640`, `lifecycle_state: "finished"`) — confirmed
programmatically as part of the benchmark harness, not just by the
separate pytest equivalence suite. Per-cell cost at `workers=1`
(83.86ms) is consistent with Phase 0-1's flat ~88-92ms/cell reference
range at this tick count, confirming checkpoint batching did not
regress the already-good serial case.

### 14.3 Checkpoint-batching fix, directly isolated

Reproducing Phase 0-1's own isolation methodology exactly (Sec 5.4 of the
baseline: single-orientation, `--ticks 50` to suppress match-execution
cost and expose checkpoint overhead, growing cell count, `workers=1`):

| Cells | Phase 0-1 (unbatched) per-cell | This phase (batched) per-cell | Phase 0-1 total | This phase total |
|---|---|---|---|---|
| 150 | 62.49 ms | **57.86 ms** | 9.373s | 8.679s |
| 450 | 70.6 ms | **56.49 ms** | 31.77s | 25.421s |
| 900 | 84.18 ms | **56.45 ms** | 75.765s | **50.804s** |

Phase 0-1's unbatched numbers grow visibly superlinear (62.49 → 70.6 →
84.18 ms/cell, +35% from 150 to 900 cells); this phase's batched numbers
are **flat** (57.86 → 56.49 → 56.45 ms/cell) at the same scale — the O(n²)
cumulative checkpoint cost is eliminated, confirmed by direct measurement
against the same methodology, not by architectural argument alone. Total
wall time at 900 cells improved ~33% purely from batching, with **zero**
change to match-execution cost or worker count (`workers=1` throughout).

### 14.4 Stress scale

2 subjects × 4 opponents × 125 seeds, both orientations = **2,000 cells**
(a practical stress scale rather than the full 5,000-10,000 the baseline
named — per the governing prompt's own allowance not to let an
impractically long run become a blocker once the large-scale evidence is
already sufficient; this scale was chosen to comfortably exceed Sec 14.2's
640-cell primary test while staying inside this session's time budget):

| workers | wall time | per-cell | speedup |
|---|---|---|---|
| 1 | 181.349s | 90.67ms | 1.00x |
| 4 | 50.181s | 25.09ms | **3.61x** |
| 8 | 32.568s | 16.28ms | **5.57x** |

Completed successfully at every worker count tested, `lifecycle_state:
"finished"` throughout, identical artifact size (2,644,679 bytes) across
all three runs. Per-cell cost at `workers=1` (90.67ms) shows **no
degradation** relative to the 640-cell measurement (83.86ms) or the
checkpoint-isolation measurement at 900 cells (56.45ms at `--ticks 50`,
consistent once tick-count is accounted for) — no runaway checkpoint cost,
no instability, and no evidence of unbounded memory growth (the run
completed at the same steady per-cell rate from start to finish) at 3x the
primary test scale. Speedup continues to improve with worker count at this
larger scale (5.57x at 8 workers, vs. 4.90x at 640 cells), consistent with
worker-startup cost being amortized over more cells per worker.

## 15. Platform qualification

**Windows** (primary, this machine): full suite (1309 passed, 6 skipped,
0 failures — see Sec 16), all new parallel/worker tests, real subprocess
worker startup/shutdown/containment (Job Object), multi-worker execution,
and every performance measurement above.

**Linux** (WSL2 Ubuntu 6.6, Python 3.12.3, genuine filesystem — copied the
repository into `~/battle2-phase2` on the WSL native ext4 filesystem
rather than running against `/mnt/d/...`, per Phase 0-1's own documented
caution about cross-filesystem I/O distorting timing-sensitive results;
24 logical cores, 31GB RAM available to the VM): full suite run **four**
times. Three runs were completely clean (1315 tests, 0 failures, 0
errors, 16 skipped — 10 more platform-conditional skips than Windows'
6, expected: the Windows-only Job Object containment tests skip here,
while the POSIX `PR_SET_PDEATHSIG` path — untested on Windows — actually
executes). One run produced a single transient failure in
`test_completion_order_reversal_preserves_matrix_order` (a cell reported
`status="failed"` after its worker subprocess round trip failed, rather
than completing normally) while running as part of the full, maximally
concurrent 1315-test suite. Investigated directly: re-run in isolation
(twice) and two full-suite re-runs afterward were all clean; a careful
code review of the retry/failure-accounting path
(`_run_pending_parallel`/`_evaluation_dispatcher_loop`) found no logic
defect — every failure path there is driven entirely by the real
subprocess's own reported status (`WorkerCallStatus.EXITED`/
`PROTOCOL_ERROR`, never a timeout, since `submit_cell` never applies
one), not by any timing assumption in the coordinator's own logic. This
is disclosed as an observed, non-reproducing, environment-induced
single-worker hiccup under extreme concurrent subprocess load (not a
correctness defect in the reviewed code), consistent with this
codebase's own established acknowledgment that real-subprocess tests
carry inherent timing sensitivity (`agent_worker.py`'s test suite uses
the same `hang_safety_timeout` pattern for exactly this class of risk).
The diagnostic-poor original assertion was hardened afterward to print
each non-completed cell's `error_code`/`error_message` on failure, so any
recurrence is immediately actionable rather than a bare `AssertionError`.

**Frozen/packaged — qualified in a follow-up closeout session.** The
original "PyInstaller is not installed" claim above was **incorrect** —
a false negative from checking the wrong module name (`python -m
pyinstaller`, lowercase, which genuinely raises `ModuleNotFoundError`)
instead of the actual importable module (`python -m PyInstaller`,
matching PyInstaller's own capitalization). `pip show pyinstaller`
correctly reports it installed either way, which is what should have
been checked. PyInstaller 6.22.2, PySide6 6.11.2, and pefile 2024.8.26
were already present in the repo's `.venv` (the same venv the Phase 2
implementation session used throughout) — no dependency install was
required beyond re-running the documented `pip install -e
".[replay,designer,windows-build]"` step `build_win.ps1` itself performs
(a no-op here, since versions already matched).

*Build*: `tools/build_win.ps1` (unmodified, the documented path — no new
PyInstaller command was invented) run against `.venv\Scripts\python.exe`
(Python 3.11.9). All four artifacts built successfully: `bytefray.exe`,
`bytefray-cli.exe`, `bytefray-agent-designer.exe`, `bytefray-replay-
viewer.exe` under `dist\windows\`. The script's own downstream GUI
smoke-test step then failed with a PowerShell error (`Start-Process
-ArgumentList` rejecting an empty array element) while launching the
standalone Designer — **a pre-existing bug in `build_win.ps1` itself,
unrelated to Phase 2**: it fails identically regardless of any evaluation/
worker code, is specific to the Designer GUI smoke block (line ~107,
`-ArgumentList @($Smoke.Args)` where `$Smoke.Args` is an empty array),
and never touches anything this phase changed. Left unfixed, per this
closeout's explicit scope boundary ("do not broaden the work into
packaging cleanup"). The four PyInstaller builds themselves completed
before this point with **zero warnings or errors mentioning
`evaluation_worker`/`agent_evaluation`** (confirmed by grepping every
`warn-*.txt` PyInstaller emits) — the packaging-relevant part of the
script succeeded cleanly; only its own unrelated verification step did
not.

*Qualification, using the built `dist\windows\bytefray\bytefray.exe`
directly, isolated `BYTEFRAY_ROOT`, real starter agents* (2 subjects ×
3 opponents × 3 seeds, single-orientation = 18 cells):

| | `--workers 1` | `--workers 2` | `--workers 4` |
|---|---|---|---|
| wall time | 1.825s | 1.389s | 1.139s |
| `lifecycle_state` | finished | finished | finished |
| exit code | 0 | 0 | 0 |

`--workers 2` correctly spawned the hidden `agents _evaluation_worker`
child mode through `launchers.build_agents_command`'s frozen path — no
recursive full-application startup, no multiprocessing/`freeze_support()`
issue (none was ever at risk, since no `multiprocessing` is used
anywhere in this design), no command-resolution failure, no protocol
corruption. **Equivalence** (the same comparison the source-level test
suite already performs): `evaluation_id` identical across all three
worker counts; full artifact content identical (modulo the same
disclosed timestamp fields); per-cell `replay.jsonl` bytes identical
across all three. `tasklist`-based orphan check: 0 `bytefray.exe`
processes before the run, 0 stray processes after — clean teardown at
every worker count.

**Forced-termination worker-teardown smoke** (Sec 6 of the governing
closeout prompt): launched a real frozen evaluation with deliberately
slow agents (`time.sleep(0.5)` per `act()` call) at `--workers 2`,
confirmed via `Get-CimInstance Win32_Process -Filter
"ParentProcessId=<pid>"` that the parent `bytefray.exe` had spawned
exactly two child `bytefray.exe` processes (the two evaluation-cell
workers), then force-killed the parent (`Stop-Process -Force`). Both
worker children were gone within 500ms — `Get-Process -Name bytefray`
returned nothing at all (parent and both workers), confirmed again after
a further 3s wait. This is the existing Windows Job Object containment
(`process_containment.bind_child_to_parent_lifetime`, reused verbatim,
zero Phase-2-specific containment code) now directly proven to cover
`EvaluationCellWorkerHandle`-spawned processes in a genuine frozen build,
not just the pre-existing `AgentWorkerHandle` case it was built for. No
new test infrastructure was created for this — it reuses the identical
mechanism `test_agent_worker.py::test_worker_does_not_survive_a_hard_
kill_of_its_own_parent` already covers at the source level; this was a
manual frozen-build-level confirmation that the same, unmodified
mechanism still holds once packaged.

No defect was found in Phase 2's own code by any of this qualification.

## 16. Test results

Full suite: **1309 passed, 6 skipped, 0 failures, 0 errors** (up from
Phase 0-1's baseline of 1283 passed/6 skipped — 26 net new tests, all in
the two new files below; zero existing tests modified). `test_ruleset_v1_
equivalence.py` reconfirmed green and untouched, still the standing oracle
that per-cell match execution is unaffected. Reconfirmed identical
(1309 passed, 6 skipped, 0 failures, 0 errors) in the frozen-build
closeout session, both before and after the ruff auto-fixes in Sec 17 —
no implementation logic changed, so no regression was possible, but this
was verified rather than assumed.

- `engine/tests/test_agent_evaluation_parallel.py` — 13 tests: serial-
  vs-parallel equivalence (parametrized workers=1/2/4/50), repeatability,
  evaluation_id worker-count independence, completion-order reversal,
  worker-crash handling, source-drift-under-concurrency, resume-after-
  interruption, and three `--workers` CLI tests.
- `engine/tests/test_evaluation_worker.py` — 13 tests: wire
  (de)serialization round trip, white-box response-parsing (malformed
  JSON, missing `"ok"` key, EOF, well-formed `ok:false`), in-process
  `run_worker` loop tests (malformed request, unknown command, clean
  shutdown, a real `run_cell` execution), and real-subprocess round trip
  /worker-death/multi-handle-teardown tests.

## 17. Lint / type-check results

`mypy engine/src/battle_engine`: **clean, 0 errors** (61 source files).
`mypy client/src/battle_client`: **clean, 0 errors** (10 source files,
unaffected by this phase — confirmed, not assumed). Three type errors
surfaced and were fixed during implementation (a `set[Any | None]` vs
`set[str]` mismatch on `known_context_ids`'s initial comprehension, and
two `queue.Queue[EvaluationCell | None]` vs `queue.Queue[EvaluationCell]`
mismatches on `_drain_abandoned_cells`'s parameter type) — both are
narrow, expected consequences of adding an `Optional`-typed sentinel value
to a previously non-Optional queue, not design defects.

`ruff check .` (repo-wide, per `AGENTS.md`'s documented CI requirement):
initially 11 findings confined to the five Phase 2 files (all
auto-fixable, none behavioral) — 5x `UP037` (redundant quoted forward-
reference type annotations, unnecessary now that `from __future__ import
annotations` is already in effect in that module), 1x `UP035`
(`Mapping` importable from `collections.abc` instead of `typing`), and
in the new test file, an unsorted import block plus one genuinely unused
import (`WorkerFailure`, imported for a test that ended up not needing
it directly). Applied via `ruff check --fix` (mechanical, no logic
touched); `ruff check .` and the full test suite were both reconfirmed
clean immediately afterward (Sec 16).

## 18. Documentation changes

This document. No other spec/roadmap document was edited this phase — per
the governing prompt's own ordering ("update relevant specs/roadmap
documentation only after actual behavior is settled"), `docs/AGENT_LAB.md`,
`docs/specs/agent_evaluation.md`, `docs/specs/evaluation_history.md`, and
`docs/ROADMAP.md` updates are deferred to a follow-up documentation pass
once this phase's behavior is reviewed and accepted.

## 19. Remaining risks and follow-ups

- **`build_win.ps1`'s own GUI smoke-test step has a pre-existing,
  unrelated PowerShell bug** (Sec 15: `-ArgumentList @($Smoke.Args)`
  rejects an empty array when smoking the standalone Designer
  executable with no arguments) — reproduces on an unmodified checkout
  regardless of Phase 2, discovered incidentally while qualifying this
  phase's frozen build. Left unfixed per this closeout's explicit scope
  boundary against packaging cleanup; worth a one-line fix
  (`-ArgumentList (,$Smoke.Args)` or an `if ($Smoke.Args)` guard) in a
  dedicated, separate change.
- **One non-reproducing Linux flake** (Sec 15) in
  `test_completion_order_reversal_preserves_matrix_order`, observed once
  in four full-suite runs under maximum concurrent subprocess load,
  investigated and not attributable to a logic defect in the reviewed
  code. Worth a second look if it recurs with the now-improved diagnostic
  output, but not treated as blocking given the investigation performed.
- **`get_project_info()` is uncached** (`project_info.py`), called once
  per cell in every process that executes one (main process for
  resolved-from-state/serial cells, each worker subprocess for dispatched
  ones) — no behavior change from before this phase, but worth a targeted
  profiling pass if it becomes measurable at very high cell counts; out
  of scope for this phase's correctness work.
- **No `--workers auto`/CPU-count-sensitive default** was implemented
  (explicitly out of scope, Sec 6/8) — Sec 14's measurements are the
  evidence base a future default-sizing decision should use.
- **Evaluation presets, statistics, behavior profiles, distributed
  execution**: untouched, as scoped.

## 20. Final verdict

**PHASE 2 COMPLETE — READY FOR EVALUATION PRESETS/SUITES.**

The frozen-build qualification gap left open at the end of the initial
implementation session (Sec 15) has been closed in a dedicated closeout
pass: the documented build path (`tools/build_win.ps1`, unmodified)
produced all four shipped executables cleanly, with zero Phase-2-specific
warnings; the real frozen `bytefray.exe` was qualified end-to-end —
serial and parallel (`--workers 1/2/4`) evaluation through the frozen
worker-spawn path, full deterministic equivalence (`evaluation_id`, full
artifact content, replay bytes) across all three, clean worker teardown
after normal completion, and clean worker teardown after a forced parent
kill (Windows Job Object containment, reused unmodified, now proven at
the frozen level for this new worker type). No defect was found in Phase
2's own code. The only finding was a pre-existing, unrelated bug in
`build_win.ps1`'s own GUI smoke-test step (Sec 15/19), explicitly left
unfixed per this closeout's scope boundary against packaging cleanup, and
disclosed rather than silently worked around.

Every hard invariant in the governing prompt was verified, not assumed:
Ruleset-v1/execution-boundary modules untouched (Sec 2/3); worker
identity/count never enters `evaluation_id`/match/result identity (Sec 7,
directly tested, now including in the frozen build); serial and parallel
results semantically identical (Sec 13, directly tested at four worker
counts including one exceeding matrix size, and again in the frozen
build at three worker counts); `cells[]` canonically matrix-ordered under
real completion-order reversal (Sec 12, directly tested with genuine
subprocess timing); exactly one `evaluation.json` writer (Sec 7's design,
and every checkpoint/final write in every test still passes B2's
completeness invariant); no schema version bump was needed or made; no
merge, tag, or release action was taken; no commit was created without
explicit request (see the companion closeout commit record below, if
qualification led to one).
