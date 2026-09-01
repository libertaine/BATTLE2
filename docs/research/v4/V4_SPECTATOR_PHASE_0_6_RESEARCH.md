# Bytefray v4 Spectator Research Phase 0.6

## Decision

Phase 0.6 qualifies the post-match factual semantic pipeline as a research
foundation. It does not qualify a Director, commentary system, user interface,
or claim to reconstruct private agent reasoning.

| Area | Classification |
|---|---|
| Factual Semantic Events | **QUALIFIED AFTER REMEDIATION** |
| Spectator Analyzer | **QUALIFIED RESEARCH FOUNDATION** |
| Deterministic Temporal Aggregation | **FOUNDATION PROVEN** |
| Replay-Derived Spatial Perspective | **SOUND WITH DOCUMENTED LIMITATIONS** |
| API-v2 `agent_trace` | **READY FOR IMPLEMENTATION** |
| Spectator Director | **READY FOR NEXT RESEARCH PHASE** |
| Overall Spectator Foundation | **GO** |

The next work should make the semantic pipeline permanent and implement the
API-v2 trace contract before any trace-backed perspective. Fight Night, pacing,
and commentary remain later work.

## 1. Frozen baseline and repository hygiene

The pre-change state was recorded before modifying the analyzer:

| Fact | Value |
|---|---|
| Repository | `D:\Projects\BATTLE2` |
| Branch | `main` |
| Initial `HEAD` / Phase 0.5 | `94d19dab3dc8975350ed07b47f365726563d25c3` |
| `origin/main` | `4aa8ac3a4cc0deccfdd6c5b94136933b315335be` |
| Ahead/behind | ahead 2, behind 0 |
| Phase 0 | `a30a88abb693a2673d7227f0f8f23f5a83c9a8e7` |
| v4 alpha2 tag | `v4.0.0-alpha2` |
| v4 alpha2 tag commit | `0daee2b1a6129f091d8587dd69f2bdb6ebf29fcc` |

The tree had no tracked or staged changes. It was not clean: `analyzer.py`,
`analyzer_output.txt`, `combat_output.txt`, `out1.txt`, `out2.txt`, and
`result.json` were pre-existing untracked research artifacts. They were not
modified, deleted, staged, or committed. The ignored `test_replay.jsonl` and
`combat_replay.jsonl` were used read-only as representative v4 controls.

No runtime, scheduler, replay schema, result schema, UI, or client code was
changed.

## 2. Independent-review defects reproduced

All six required hypotheses reproduced on `94d19da` before remediation:

1. A disrupted enemy target disappeared from the target collection and caused
   a false `DETECTION_LOST`.
2. A canonical `KillDeathEvent` serialized with `event_type` crashed at
   `ev['type']`.
3. A three-entrant transition replay produced different output under different
   `PYTHONHASHSEED` values because set iteration supplied output order.
4. A non-Schema-4 replay exited successfully instead of being rejected.
5. A memory diff without `owner` raised an uncontrolled `KeyError`.
6. In the 3,000-tick representative replay, 2,966 disrupted tick snapshots
   (2,967 process states if the final result record is also counted) were
   collapsed to one false-to-true transition event.

The combined pre-change regression probe reported `4 failed, 1 passed`; the
malformed-diff and consecutive-disruption probes were run separately to retain
their exact failure modes. This establishes that the remediation fixed observed
defects rather than merely adding tests around the old behavior.

The earlier, unrelated group-analysis test failure remains **historical:
unreproduced; current spectator causality: excluded; root cause: unknown**. It
is not reopened unless it recurs.

## 3. Factual event contract

`tools/spectator_analyzer.py` now has a small frozen dataclass representation
and a versioned, deterministic research serialization:

```text
bytefray.spectator_events v1
```

This is internal research infrastructure, not a promised public API. The facts
are:

- `FOREIGN_OWNERSHIP_OVERWRITE`: a replay memory diff changes one cell from a
  non-null owner to a different non-null owner. It does not assert hostility,
  strategic value, or that the previous owner is still alive.
- `CORE_DISRUPTION`: a process snapshot is disrupted on that tick and the
  replay contains at least one opponent-owned write at its recorded anchor.
- `DETECTION_GAINED` / `DETECTION_LOST`: an end-of-tick replay-derived spatial
  relationship changes.
- `AGENT_ELIMINATED`: a canonical `kill` or `death`, retaining victim, killer,
  and cause.
- `AGENT_FORFEITED`: a canonical `forfeit`, retaining reason, stage, and action
  slot.
- `VICTORY`: the final result names a winner; the win mode is retained as its
  cause.

Initial tick-zero diffs seed ownership. Range diffs expand in recorded address
order with arena wrap. A same-owner rewrite is not foreign. Explicit
`owner=null` clears the cell and emits no overwrite; a later claim of that
unowned cell is also not foreign. Repeated diffs retain replay order.

### Disruption attribution boundary

The analyzer emits one disruption fact per `(tick, entrant_id, process_id)`.
It does not use a false-to-true edge, so consecutive D=1 hits remain separate.
Co-located processes each receive a fact.

If all opponent writes at the final anchor identify the same writer, the
attacker entrant is exact. If multiple writers appear, the event says
`attribution="ambiguous"`, omits a singular attacker, and retains a sorted
candidate set. It never guesses. Schema 4 lacks intra-tick process-move history,
so it cannot always prove which of several same-tick writes caused the state or
how many same-tick hits occurred. One process-tick fact is therefore the maximum
honest replay-derived claim. A disrupted snapshot with no replay-visible
opponent write at its anchor is rejected as inconsistent input.

### Process identity

Process-specific facts use entrant plus process ID. Duplicate process IDs in
different entrants are valid and covered. No analyzer state is keyed by a bare
process ID.

## 4. Replay validation and deterministic ordering

The analyzer accepts exactly canonical `battle2.replay` Schema 4. It validates
record order, one header, contiguous ticks beginning at zero, one final result,
required tick collections, process fields, and explicit memory-diff
`address`/`length`/`owner`/`values`. Diff values and range lengths are checked.
Malformed JSON, incomplete records, unsupported schemas, and inconsistent
disruption evidence produce a concise `SpectatorAnalysisError`; the CLI exits
2 with `ERROR:` and no traceback.

Same-tick order is part of semantic-events version 1:

1. foreign-ownership overwrites in replay diff order and range-address order;
2. disruption consequences by first candidate diff, target entrant, then
   process ID;
3. visibility transitions by viewer, target, then lost before gained;
4. canonical elimination/forfeit events in replay order;
5. final victory at the result tick.

All JSON uses sorted keys and compact separators. The header binds derived
output to source replay SHA-256, replay ID, match ID, and Ruleset ID. Tests run
the CLI under three hash seeds and require byte-identical output.

## 5. Replay-derived spatial perspective

The analyzer now matches the production v4 spatial rules at the replay
snapshot boundary:

- all undisrupted processes of a living viewer are eligible sensors;
- every process of a living enemy is a possible target, including disrupted
  processes;
- visibility is entrant-wide and asymmetric;
- the boundary is inclusive (`circular_distance <= reach`);
- arena wrap is applied;
- eliminated/forfeited entrants participate as neither viewer nor target.

This is **replay-derived spatial perspective**. It reflects end-of-tick process
anchors and cannot claim to be the exact per-callback `ObservationV2` history.
The future UI should expose one ordinary replay-derived spatial mode and an
optional **trace-backed engine-delivered perspective** only when a verified v2
trace exists. Neither mode is "agent thought".

## 6. Minimum deterministic temporal aggregation

`tools/spectator_aggregation.py` consumes factual events without consulting the
runtime and emits only four objective summaries:

- `OVERWRITE_WINDOW`: a maximal run of foreign overwrite facts in which
  successive overwrite ticks differ by at most two;
- `RECIPROCAL_OVERWRITE_WINDOW`: such a window contains both X-to-Y and Y-to-X
  ownership changes;
- `REPEATED_LOCATION_CHURN`: at least four overwrites of one address in a
  window, with at least two new owners;
- `QUIET_WINDOW`: at least three consecutive ticks with no factual semantic
  event.

The two-tick overwrite gap bridges one silent tick. This is the minimum needed
to avoid fragmenting the qualified K=2 process cadence into thousands of
one-event windows; two silent ticks still establish a boundary. Four changes at
one location represent two ownership reversals. All thresholds are explicit in
`AggregationConfig` and versioned with the aggregate schema so a future
Director can choose presentation policy without relabeling raw facts.

No aggregate is called an attack, engagement, important moment, or drama score.
Aggregates are stably sorted by start tick, kind, end tick, address, and
entrants.

## 7. Density controls

| Control | Ticks | Overwrites | Disruptions | Visibility | Elimination/result | Temporal aggregates |
|---|---:|---:|---:|---:|---:|---|
| Synthetic irrelevant one-cell churn | 8 | 700 | 0 | 0 | 0 | 1 overwrite, 1 reciprocal, 1 churn |
| Synthetic short decisive anchor event | 2 | 1 | 1 | 0 | 1 elimination + 1 victory | 1 overwrite |
| `test_replay.jsonl` (`v4_claimer` / `v4_scout`) | 3,000 | 1,483 | 2,966 | 1 gained | 1 victory | 1 overwrite, 1 quiet |
| `combat_replay.jsonl` representative combat | 3,000 | 2,937 | 2,937 | 1 gained | no winner | 1 overwrite, 1 reciprocal, 1 churn, 1 quiet |

The high-density control collapses 700 raw facts into three summaries without
claiming importance. The decisive control remains four factual events even
though it produces only one overwrite aggregate. This is the required proof
that aggregation reduces repetition but does not decide dramatic value.

The representative replays are pre-existing ignored research artifacts, not
new committed fixtures. The committed tests generate their inputs under
pytest's temporary-path support.

## 8. API-v2 `agent_trace` design

Current state is neither solved nor merely hypothetical: production API-v1
`bytefray.agent_trace` v1 is implemented and tested, while the canonical v4
process-match path currently opens the writer without passing it into
`ProcessMatchController`. A production API-v2 agent test therefore yielded a
one-line header-only trace. V1 behavior is unchanged in this phase.

The proposed artifact is `bytefray.agent_trace` **version 2**, separate from
Schema 4 replay. Existing v1 readers continue to accept v1 and must explicitly
reject v2 until upgraded.

### Records

The header contains `match_id`, Ruleset ID, match seed, entrant identities and
source identities, API version, arena/tick/action limits, and a declaration
that replay binding is supplied by the required integrity footer.

Before tick execution, ordered records capture each reset outcome and the
validated `ProcessDeclaration` list. One decision record per callback attempt
then contains:

```text
tick
global callback_index
action_slot
entrant_id
process_id
full ObservationV2
requested AgentAction or callback diagnostic
normalized action (kind, wrapped address or bounded move, byte value)
action result (applied, read value, read owner, failure category)
```

`callback_index` is global and monotonically increasing, making scheduler order
explicit. Requested, normalized, applied, and failed actions stay distinct.
Reset/declaration/act/worker diagnostics use stable codes and fields. Arbitrary
agent object state, locals, logging, and inferred intent are excluded.

### Replay binding and integrity

The writer remains streaming. After the canonical replay closes and its
SHA-256 is known, it appends one required integrity record containing:

```text
canonical replay SHA-256
semantic trace SHA-256
bound trace identity SHA-256
record/callback counts
```

The semantic digest is updated over canonical compact JSON projections of the
header/reset/declaration/decision records, excluding diagnostics timing and the
footer. The bound identity hashes the semantic digest together with replay
SHA-256, match ID, Ruleset ID, and entrant identity set. A crash can leave a
useful unbound diagnostic trace, but it cannot be presented as an exact replay
perspective.

A consumer accepts trace T for replay R only when all of these hold:

1. T is a supported complete v2 trace with exactly one integrity footer;
2. the SHA-256 of R's canonical bytes equals T's replay digest;
3. match ID, Ruleset ID, and ordered entrant identities equal R's header;
4. T's semantic and bound-identity digests recompute exactly;
5. callback indices are contiguous and record counts agree.

Mismatch is a hard trace/replay binding failure, not a warning. Trace creation,
compression, deletion, and retention do not alter simulation, winner, result,
replay bytes, or replay identity. Historical replays remain readable and simply
lack an enhanced trace-backed perspective.

### Determinism and diagnostics

The semantic projection must be byte deterministic for a deterministic match.
Fields such as `wall_time_ms`, worker PID, host paths, and timestamps are
diagnostic-only and live under an optional `diagnostics` envelope excluded from
semantic and bound identity. Consequently two full files need not be byte
identical when diagnostics are enabled; their semantic projections and
identities must match. A `--semantic-only` mode can omit the envelope when
byte-identical complete traces are desired.

### Size model and retention

The model serialized representative complete v2 decisions with every current
`ObservationV2` field, requested and normalized writes, action result, null
diagnostic, compact sorted JSON, Q=8 callbacks per entrant per tick, and a
header/footer. Gzip level 6 was streamed over the same varied records.

| Entrants | Ticks | Callbacks | JSONL | gzip |
|---:|---:|---:|---:|---:|
| 2 | 100 | 1,600 | 0.96 MiB | 0.04 MiB |
| 2 | 3,000 | 48,000 | 29.31 MiB | 1.20 MiB |
| 4 | 100 | 3,200 | 1.96 MiB | 0.10 MiB |
| 4 | 3,000 | 96,000 | 59.58 MiB | 2.91 MiB |
| 8 | 100 | 6,400 | 3.94 MiB | 0.21 MiB |
| 8 | 3,000 | 192,000 | 120.16 MiB | 6.41 MiB |

Measured JSON averaged about 630-656 bytes per callback. This is practical as
an explicitly requested development artifact, not as unconditional tournament
output. Generation remains off by default. The implementation should support
streaming gzip, store traces beside the run only when requested, and make
retention a caller policy rather than silently deleting artifacts. Compression
changes storage encoding, not semantic identity.

## 9. Replay seeking and checkpoints

No checkpoint or index architecture was added. The independent product-path
measurement at roughly 3,000 ticks found `ReplaySession` final seek median
7.65 ms, final p95 7.99 ms, and random-seek p95 7.72 ms; raw reparsing was about
44 ms but is not the normal buffered client path. Optimization remains deferred
until a real UI workload violates its frame budget.

## 10. Qualification coverage

The committed focused suite contains 36 tests across
`test_spectator_analyzer.py` and `test_spectator_aggregation.py`. It covers:

- exact Schema 4 acceptance and controlled schema/malformed/truncation errors;
- tick-zero ownership, first foreign overwrite, replay order, range/wrap,
  same owner, and `owner=null`;
- entrant-wide, asymmetric, inclusive, wrapped visibility; separate sensor and
  target eligibility; eliminated entrants; multiple processes; duplicate IDs;
- one and consecutive disruption ticks, same-tick writes, co-location,
  friendly writes, and ambiguous multiple attackers;
- canonical kill/death, forfeit details, victory, and same-tick ordering;
- exact repeat serialization and subprocess tests under three hash seeds;
- aggregation gaps, reciprocal direction, churn threshold, quiet windows,
  density controls, ordering, and serialization.

Qualification results after remediation:

| Check | Result |
|---|---|
| Focused analyzer + aggregation | **36 passed** in 0.56 s |
| Relevant v4/replay/client session | **203 passed** in 2.87 s |
| Existing API-v1 trace/inspect/integration | **32 passed** in 2.58 s |
| Full configured suite | **2,647 passed, 26 skipped, 2 deselected** in 267.85 s |
| Ruff, all tracked non-legacy Python plus new Phase 0.6 Python | **passed** |
| Mypy engine | **95 source files, no issues** |
| Mypy client | **12 source files, no issues** |
| Mypy analyzer + aggregation (`--explicit-package-bases`) | **2 source files, no issues** |

The first focused invocation named a basetemp under a nonexistent `.tmp`
parent, so pytest failed during setup before any test body ran. Re-running under
the repository's documented `.pytest-tmp` root passed. Mypy initially exposed a
stale venv binary mismatch: Python 3.13 had CPython-3.11 `librt` extensions.
Reinstalling the already pinned `librt==0.15.0` wheel for CPython 3.13 repaired
the venv; both required targets then passed.

`ruff check .` cannot honestly be called green in this dirty workstation: it
encounters the preserved untracked `analyzer.py` and reports that file's old
import formatting, plus access denial on a pre-existing cache directory. The
Phase 0.6 audit did not alter either. The clean tracked/non-legacy code scope
used by repository policy, plus every new Python file, passes Ruff.

## 11. Compatibility and remaining uncertainty

This phase is derived post-match interpretation. It changes no v1-v4 runtime
behavior, canonical result, replay record, replay identity, historical replay
byte, or API-v1 trace.

Remaining boundaries are explicit:

- replay-derived visibility is end-of-tick spatial state, not callback history;
- Schema 4 cannot always attribute one of several same-tick anchor writes or
  count same-tick repeated disruption hits exactly;
- the aggregate thresholds are objective version-1 grouping policy, not proof
  of spectator importance;
- API-v2 tracing is designed but not implemented;
- seek performance must be revisited only with a representative permanent UI.

These limitations do not invalidate the factual foundation because the code
rejects or labels uncertainty instead of presenting inference as fact.

## 12. Recommended next phase

Proceed to a permanent semantic spectator pipeline using the qualified event
and aggregation contracts, then implement and bind API-v2 trace v2. After that,
evaluate the replay-derived and optional trace-backed perspective presentations.
Director pacing research may proceed against these two deterministic layers.
Fight Night and Color Commentator remain premature until that work is measured.

Files intentionally in Phase 0.6 scope are:

- `tools/spectator_analyzer.py`
- `tools/spectator_aggregation.py`
- `engine/tests/test_spectator_analyzer.py`
- `engine/tests/test_spectator_aggregation.py`
- `docs/research/v4/V4_SPECTATOR_PHASE_0_6_RESEARCH.md`

The exact commit SHA is reported in the final handoff because a commit cannot
contain its own identity.
