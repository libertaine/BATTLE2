# Bytefray v4 Spectator Research Phase 2 — API-v2 Agent Trace

## Decision

Phase 2 implements the API-v2 agent trace (`bytefray.agent_trace` schema
version 2) specified in `docs/specs/v4_api_v2_trace.md`. The implementation
committed at `b5fe0f4c` (`feat(v4): implement api-v2 agent trace schema and
observational pipeline`) was reviewed independently against that spec, the
canonical replay/binding contract, and the repository's compatibility rules.
The review found the record model, spec, and replay-equivalence design sound,
but found three defects severe enough that the trace's central purpose did not
work at all as shipped, plus two smaller fidelity/documentation gaps. All were
fixed narrowly, within Phase 2's existing file set, with regression tests
added for each.

| Area | Classification |
|---|---|
| Phase 2 specification (`docs/specs/v4_api_v2_trace.md`) | **QUALIFIED** |
| Schema/versioning (`schema_version`) | **NEEDS VERSION CHANGE → FIXED** |
| Trace data model (records) | **QUALIFIED** |
| Callback ordering/identity | **QUALIFIED** |
| ObservationV2 coverage | **FULL AFTER FIX** |
| READ/WRITE/MOVE coverage | **QUALIFIED AFTER FIX** |
| Requested vs. applied action model | **INCOMPLETE → FIXED** |
| Diagnostics/nondeterministic fields | **QUALIFIED AFTER FIX** |
| Replay binding lifecycle | **QUALIFIED** |
| API-v1 compatibility | **CONFIRMED AFTER FIX** |
| Trace failure semantics | **QUALIFIED (pre-existing V1 design, correctly reused)** |
| Enable/disable policy | **QUALIFIED (CLI opt-in, unchanged)** |
| Match/replay equivalence | **CONFIRMED** |
| Trace size/storage | **MEASURED — reasonable, opt-in** |
| Compression decision | **QUALIFIED (deferred by design, matches spec)** |
| Documentation/walkthrough | **QUALIFIED (no misleading tracked doc found)** |
| **Phase 2 overall** | **PASS AFTER REMEDIATION** |

Phase 3 has not been started as part of this review.

## 1. Repository state at review start

| Fact | Value |
|---|---|
| Repository | `D:\Projects\BATTLE2` |
| Branch | `v4-spectator-phase2-development` |
| `HEAD` (Gemini's reported Phase 2 completion) | `b5fe0f4c0800eb74788d13f5e7dea3fc56cd3f9a` |
| `origin/main` | `4aa8ac3a4cc0deccfdd6c5b94136933b315335be` |
| Ahead/behind `origin/main` | ahead 7 (`a30a88a`..`b5fe0f4c`), behind 0 |
| Phase 1 (wrapper hardening) | `f4cf99dad2e91959b1dd1144216ab7ba4ccb2184` |
| Phase 1 (semantic pipeline) | `ecbdb5aafa4ac00841062e68412b804e22d35075` |
| Phase 0.6 | `0463630...` |

`f4cf99d` is a direct ancestor of `b5fe0f4c` (`git merge-base --is-ancestor`
confirmed). The Phase 2 diff (`f4cf99d..b5fe0f4c`) touches exactly five files:
`docs/specs/v4_api_v2_trace.md` (new), `engine/src/battle_engine/agent_trace.py`,
`engine/src/battle_engine/match_service.py`,
`engine/src/battle_engine/process_runtime.py`, and
`engine/tests/test_v4_trace_equivalence.py` (new). No unrelated files are
touched; no `ProcessMatchController`/`NativeMatchService` change outside the
trace-emission call sites; no replay schema change.

The working tree at review start was clean (`git status`: "nothing to commit,
working tree clean"). The six historical untracked research artifacts this
task's brief expected to still be present (`analyzer.py`, `analyzer_output.txt`,
`combat_output.txt`, `out1.txt`, `out2.txt`, `result.json`) are **not present
on disk** — they do not exist at the repository root at all. This contradicts
the brief's framing ("the working tree ... six historical untracked files
remain"); it is recorded here rather than silently assumed. They were not
created, modified, or referenced by this review.

## 2. Defects found and fixed

All four code fixes are narrowly scoped to the same five files Phase 2 already
touched (plus `__all__` in `agent_trace.py`). None change replay/result
semantics, scheduler behavior, or agent-visible behavior; none touch API-v1
trace content.

### 2.1 `schema_version` never declared as 2 for API-v2 traces (critical)

`docs/specs/v4_api_v2_trace.md` §10 requires `TRACE_SCHEMA_VERSION = 2` for
API-v2 traces specifically so v1 tooling rejects them at the header. The
implementation left the module constant `TRACE_SCHEMA_VERSION = 1` (correct —
that constant is v1's own version) but then used the `TraceHeader` dataclass's
default (`schema_version=1`) unconditionally for *every* trace, v1 or v2, in
`_open_trace_writer`. Combined with `_parse_header` hard-coding rejection of
any `schema_version != TRACE_SCHEMA_VERSION` (i.e. != 1) before the new
`read_trace_v2` ever got to run its own `!= 2` check, **`read_trace_v2()`
could not successfully parse any trace this implementation ever produced** —
it always raised `TraceFormatError` on the header line, for both the "wrong
version" (1, not 2) and the unreachable-by-then "expected 2" code path. The
existing equivalence test masked this by asserting `header["schema_version"]
== 1` (i.e. codifying the bug as expected behavior) and by hand-parsing JSON
lines instead of calling the real reader.

Fix: `_parse_header` now only validates the shared `schema` string; each
reader (`read_trace`, `read_trace_v2`) enforces its own expected
`schema_version` afterward. `_open_trace_writer` takes an explicit
`schema_version` parameter; `NativeMatchService.run` passes
`TRACE_SCHEMA_VERSION_V2` (a new, named `= 2` constant, replacing a bare
literal) when the match uses the V4/API-v2 process runtime and
`TRACE_SCHEMA_VERSION` (1) otherwise. `read_trace_v2` now actually succeeds on
real V2 traces, and `read_trace` (v1) now correctly rejects a V2 trace at the
header per the spec's compatibility requirement.

### 2.2 `trace_writer` never reached the running controller (critical)

`ProcessMatchController.from_python_entrants` accepted a `trace_writer`
parameter and used it correctly while loading entrants (writing
`ResetRecord`/`DeclarationRecord`), but its final `return cls(config, specs,
max_ticks, ruleset_policy=ruleset_policy)` never forwarded `trace_writer=` into
the constructor. `ProcessMatchController.__init__` defaults `trace_writer` to
`None`, so `self.trace_writer` was always `None` on the controller `run()`
actually executes ticks on — meaning `_emit_decision_trace`'s `if writer is
None: return` fired on **every single call**, for every tick, every process,
every match. **Not one `DecisionRecordV2` was ever written**, regardless of
how many ticks ran or what agents did. Only the header, reset, declaration,
and binding records — none of which depend on this path — ever appeared in a
trace file. This is the trace's entire stated purpose (§7 of the spec:
recording the requested-vs-applied action per callback) and it did not
function at all. The existing equivalence test did not catch this because it
only asserted `len(lines) > 2`, which six non-decision records already
satisfy.

Fix: one line — `trace_writer=trace_writer` added to the `cls(...)` call.

### 2.3 `wall_time_ms` recorded a raw timestamp, not a duration (data-quality)

Every codebase precedent for this field name (`python_runtime.py`'s
`ResetRecord`/`DecisionRecord` emission, and the API-v2 spec's own
description of it as "diagnostic... Host timing") is an elapsed-duration
measurement: `(time.perf_counter() - start) * 1000`. The V2 emission sites
instead captured `time.perf_counter_ns() / 1_000_000.0` — an absolute,
arbitrary-epoch value — once, before the call, and wrote it through unchanged
as `wall_time_ms`. Every V2 trace's timing field was therefore a large,
meaningless number rather than a call duration. Because this field is
explicitly excluded from semantic identity (spec §8), this did not affect
correctness, determinism, or equivalence — only the diagnostic content's
usefulness.

Fix: both `ResetRecord` emission sites (in-process and supervised-worker
paths) and the per-tick `_emit_decision_trace` path now measure actual elapsed
time with `time.perf_counter()` before/after the call they describe. Three
scattered inline `import time` statements were consolidated into one
module-level import.

### 2.4 READ/WRITE never recorded their effective address (fidelity gap)

The final `_emit_decision_trace` call in the per-tick loop special-cased MOVE
(`normalized_address=active_proc.position`) but fell back to
`res_info.get("normalized_address")` for every other applied action — a key
`res_info` never set for READ or WRITE. Every successful READ or WRITE trace
record therefore had `normalized_address: null`, even though the effective,
wrapped address (`target_addr`) was computed and used two lines earlier to
perform the read/write. This directly undermines spec §7's stated purpose for
this field and the review brief's §9 requirement to verify READ/WRITE
normalized-address capture. Rejected (out-of-reach) READ/WRITE already
correctly omitted it (nothing was applied).

Fix: `res_info["normalized_address"] = target_addr` added on both the READ and
WRITE applied paths.

### 2.5 `__all__` omitted the entire V2 public surface (completeness)

`agent_trace.py`'s `__all__` still listed only the V1 symbols after Phase 2
added `TraceObservationV2`, `TraceActionV2`, `TraceResultV2`,
`DeclarationRecord`, `DecisionRecordV2`, `BindingRecord`, `TraceDocumentV2`,
and `read_trace_v2`. Fixed by adding all of them plus the new
`TRACE_SCHEMA_VERSION_V2` constant.

## 3. Regression tests added

`engine/tests/test_v4_trace_equivalence.py`:

- The existing `test_v4_trace_is_strictly_observational` now asserts
  `schema_version == TRACE_SCHEMA_VERSION_V2`, parses the trace with the real
  `read_trace_v2()` (not hand-rolled JSON parsing) and asserts declarations,
  decisions, and a matching binding are present, and asserts the v1 `read_trace()`
  raises `TraceFormatError` on the same file.
- New `test_v4_trace_v2_captures_normalized_address_for_applied_read_and_write`
  directly regresses §2.4: a writer agent and a reader agent each act within
  reach, and the test asserts every applied WRITE/READ decision's
  `applied_result.normalized_address` equals the actual target address.

Both pass. `ruff check .` is clean repo-wide. `mypy engine/src/battle_engine`
(97 files) and `mypy client/src/battle_client` (12 files) are both clean.

## 4. Spec, record model, and architecture review (no changes needed)

`docs/specs/v4_api_v2_trace.md` (added at `1e9ea6b`, ahead of the
implementation commit) explicitly defines purpose/boundary, the five-record
model (`HeaderRecordV2` via the shared `TraceHeader` + `schema_version=2`,
`ResetRecord`, `DeclarationRecord`, `DecisionRecordV2`, `BindingRecord`),
emission points, callback ordering/identity
(`(entrant_id, process_id)`, append order), full `ObservationV2` capture,
READ/WRITE/MOVE coverage, the requested-vs-applied `status` model, which
fields are diagnostic/nondeterministic, the replay-binding lifecycle and its
required fields, versioning/compatibility, the size/retention model
(opt-in, no built-in compression), and failure isolation. This is a complete,
implementable spec; **QUALIFIED**, no revision needed.

`ObservationV2` field coverage: every field on the real
`battle_engine.agent_api.ObservationV2` (`current_tick`, `last_callback_tick`,
`previous_action_tick`, `self_process_id`, `self_anchor`, `self_reach`,
`own_core_base`, `own_core_size`, `visible_enemy_anchor_addresses`,
`previous_action_applied`, `previous_read_value`, `previous_read_owner`) has a
field-for-field mirror in `TraceObservationV2`, checked by direct comparison
against the dataclass definitions in both `agent_api.py` and `agent_trace.py`.
No field is dropped or projected. `visible_enemy_anchor_addresses` is
constructed via `_visible_enemy_anchors`, which explicitly returns
`tuple(sorted(visible))` — deterministic regardless of `PYTHONHASHSEED` (int
hashing is not seed-randomized in CPython, and the result is sorted besides).
**FULL AFTER FIX** (fix being §2.4, which affects the *result*, not the
observation capture, but is the qualifying condition for this task's "does
the trace represent the exact interaction history" test).

Callback ordering/identity: `(agent_id, process_id)` is used consistently as
the trace key; ordering is strict append order, matching the v1 module's
documented contract ("Record order is append order, always"), driven by the
existing, unmodified `RulesetPolicy.run_scheduler` rotation. No new ordering
mechanism was introduced by Phase 2. **QUALIFIED**.

Two spec/implementation mismatches were found but judged out of narrow
Phase-2-remediation scope:

- The `status` enum (`APPLIED`, `REJECTED_INVALID`, `REJECTED_OUT_OF_REACH`,
  `REJECTED_QUOTA`, `DISRUPTED`, `EXCEPTION`) includes `REJECTED_QUOTA` and
  `DISRUPTED`, but `_select_active_process`/`_effective_process_quotas`
  already exclude disrupted and over-quota processes *before* `act()` is ever
  called — so no observation is delivered and no decision record can exist for
  those cases under current v4 semantics. These two status values are
  currently unreachable. This is a spec-vs-implementation wording mismatch,
  not a functional defect (nothing is lost — the process simply does not act
  that tick, consistent with "the trace must preserve engine-delivered
  observations, not arbitrary private agent reasoning"). Recommend a doc
  correction in a future pass rather than an engine behavior change.
- `ResetRecord` diagnostic capture is wired for the V1 flow
  (`python_runtime.py`) but not for the V2
  `ProcessMatchController.from_python_entrants` paths: a `reset()`/`declare_processes()`
  failure there raises `PythonEntrantInitializationError` (aborting match
  setup, pre-existing behavior, unchanged) without attaching a
  `TraceDiagnostic` to the already-written `ResetRecord`. A partial trace with
  no explanation of the abort can result. Judged a fidelity gap worth a
  follow-up, not a correctness defect (the abort itself is unaffected;
  `replay_path`/`summary.json` are already removed on this path, matching
  existing behavior).

## 5. Replay binding lifecycle

Traced end-to-end in `match_service.py`: the controller runs and writes a
temporary replay; `_finalize_native_artifacts` (pre-existing, unmodified)
synchronously rewrites the canonical bytes to the final `replay_path`; only
*after* that call returns does `NativeMatchService.run` compute
`hashlib.sha256(replay_path.read_bytes())` and write the `BindingRecord`;
`trace_writer.close()` happens last, in the outer `finally`. The hash is
therefore always computed from the finalized canonical bytes, never a
provisional pre-finalization hash. `BindingRecord` carries `match_id`
(`canonical_match_id(request)`), `replay_sha256`, `ruleset_id`, and
`entrant_identities` — sufficient context to bind trace, replay, ruleset, and
entrants together. If `_finalize_native_artifacts` itself raises, no
`BindingRecord` is written but the trace file is still closed (partial
artifact); this matches the match's own existing failure behavior on that path
and is not a new risk introduced by Phase 2. **QUALIFIED**.

`read_trace()` (v1) was extended with a generic `"binding"` record-type case,
so a `BindingRecord` — now appended to *every* traced match, v1 or v2 alike —
parses through the unmodified v1 reader too. This is additive (an `elif`
branch) and does not change how any pre-existing v1 record type parses;
`TraceDocument.decisions`/`.resets`/`.failures()` all use `isinstance` filters
that already correctly exclude `BindingRecord`. **V1 COMPATIBILITY: CONFIRMED
AFTER FIX** (the fix being §2.1, which is what makes the v1/v2 header
disambiguation in the spec's compatibility policy actually work).

## 6. Match/replay equivalence

Re-run via `test_v4_trace_is_strictly_observational`: identical seeded match
run with tracing disabled (Run A) and enabled (Run B). `result_a.winner ==
result_b.winner`, `result_a.termination_reason == result_b.termination_reason`,
and `sha256(replay_a) == sha256(replay_b)` all hold. The only additional
artifact in Run B is the trace file itself. **CONFIRMED**.

## 7. Trace size/storage (measured)

No size analysis existed anywhere in the repository prior to this review
(Gemini's report claimed one; none is committed). Measured directly with a
throwaway agent cycling MOVE/READ/WRITE every tick, across 2/4/8 entrants:

| Entrants | Records | Raw size | Avg record | gzip size | Ratio |
|---|---|---|---|---|---|
| 2 | 1,254 | 748.4 KiB | 611.1 B | 24.7 KiB | 30.3x |
| 4 | 1,546 | 921.9 KiB | 610.6 B | 33.7 KiB | 27.4x |
| 8 | 3,090 | 1,845.2 KiB | 611.5 B | 63.8 KiB | 28.9x |

Per-record size (~611 B) is stable across entrant counts, as expected for a
flat JSONL record format. Extrapolating to the spec's own stated worst case
(§11: "max 8 processes, 2 K-quota, ~3000 ticks = ~48,000 decisions"): 48,000 ×
611 B ≈ 29.3 MB uncompressed, closely matching the spec's own "~30 MB"
estimate — an independent, empirical corroboration of that figure rather than
a restatement of it. gzip compresses on the order of 28–30x, supporting the
spec's decision to defer built-in compression and leave it to consumers.
**Trace generation default: reasonable given it is opt-in** (see §8);
**should remain opt-in**, not made default-on.

## 8. Enable/disable policy

`request.trace_path` defaults to `None`; `MatchRequest` construction sites in
`agent_test.py` gate it explicitly (`trace_path = (run_dir / "trace.jsonl") if
trace else None`), driven by a `trace: bool` CLI-level parameter. This is
pre-existing V1 infrastructure that Phase 2 reuses unchanged via the same
`_open_trace_writer(request, ...)` call (`request.trace_path is None` early
return). No code path makes tracing default-on. **CLI opt-in, confirmed**.
Trace-disabled execution remains the default and is exercised by every
non-traced test in the suite.

## 9. Compression decision

Spec §11/§21 explicitly defers compression to consumers, citing latency; the
implementation matches (`TraceWriter` never compresses). §7's measured ~28–30x
gzip ratio supports this as a reasonable deferral rather than an
under-engineered gap. **QUALIFIED, not overengineered**.

## 10. Documentation/walkthrough

No file titled "Walkthrough: Bytefray v4.0.0-alpha1 Release" — or any file
containing that exact contradictory pairing (localized reach/MOVE/D=1 vs.
global reach/no movable anchors/deferred disruption) as *current* documentation
— exists anywhere in the tracked repository (`git grep -il walkthrough`
checked). The closest artifact, `docs/releases/V4_0_0_ALPHA1_RELEASE_REPORT.md`,
was last touched at `4aa8ac3` ("git overwrite"), predates Phase 0 entirely, and
describes only the historical alpha1 architecture (`D=1 Anchor Disruption`,
API-v2-required `ruleset_policy`) without the "final selected research model"
contradiction described in this task's brief. There is nothing tracked to
correct. **QUALIFIED** — this appears to describe content from outside the
committed repository (e.g. a report shown alongside the implementation, not
committed with it), not a file Phase 2 left behind.

## 11. Test results

Run after the fixes in §2, on the resulting `HEAD`:

| Group | Result |
|---|---|
| API-v2 trace tests (`test_v4_trace_equivalence.py`) | 2 passed |
| API-v1 trace regressions (`test_agent_trace.py`) | 17 passed |
| Replay/schema-4 tests (`test_replay_reconstruction.py`, `test_replay_contract.py`) | 21 passed |
| Phase 1 spectator regressions (`test_spectator_aggregation.py` + `test_spectator_analyzer.py`) | 39 passed (11 + 28), matching the expected Phase 1 focused scale exactly |
| `engine/tests/` (all) | **2274 passed, 14 skipped, 0 failed** (2288 collected) |
| Full repo suite (`_legacy/tests` + `engine/tests` + `client/tests`) | **2652 passed, 26 skipped, 0 failed** (2678 executed) |
| Ruff (`ruff check .`) | clean, repo-wide |
| mypy (`engine/src/battle_engine`) | clean, 97 source files |
| mypy (`client/src/battle_client`) | clean, 12 source files |

The full-suite delta from the previously-qualified baseline
(2650 passed, 26 skipped, 2 deselected) is exactly explained: `2650 + 2 =
2652` passed, where the 2 additional passing tests are the two new regression
tests added in §3; the skip count (26) is unchanged. Both this run and a
`--collect-only` check found 2678 selected/collected tests with `-m "not gui"`
applied, i.e. 0 currently deselected, versus the baseline's 2 deselected;
`--collect-only` without the marker filter returned the identical 2678,
meaning no test in the current tree currently carries the `gui` marker. This
is unrelated to anything Phase 2 touches (no display/GUI code is in the diff)
and is recorded as an observed, unexplained pre-existing drift rather than
investigated further here.

Gemini's reported counts (`pytest engine/tests/ → 2260 passed`;
`"background/full suite" → 2273 passed, 14 skipped`) do not match the
repository's actual full suite (2678 total across all three `testpaths`) at
all — they are close to, but not exactly matching, this review's own
`engine/tests/`-only figures (2288 total, 2274 passed / 14 skipped). The
"full suite" label in Gemini's report was **a mislabeled subset**, exactly the
failure mode this task's brief warned against ("do not call a subset the
'full suite'"). The true full suite is roughly 390 tests larger
(`_legacy/tests` + `client/tests`) than what Gemini called the full suite.

## 12. Remediation commit

`5b44dc8` — `fix(v4): harden API-v2 trace contract` — contains all five fixes
in §2 plus their regression tests, on top of `b5fe0f4c`. This document is
committed separately (`docs(v4): report Phase 2 qualification`). Neither
commit was pushed; the branch remains `v4-spectator-phase2-development`,
local-only relative to `origin/main`.

## 13. Scope discipline

No NativeMatchService business logic, replay schema, scheduler, or
non-tracing agent-visible behavior was changed. No file outside Phase 2's
original five (plus this document and the qualification record) was modified.
Phase 1 spectator code (`spectator_aggregation.py`, `spectator_events.py`,
their tools/tests) was not touched. Phase 3 was not started.
