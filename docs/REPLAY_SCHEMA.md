# Bytefray Replay and Event Contract

## v0.3 canonical writer

New native matches use `battle2.replay` schema version 3. One authoritative
finalization path (`match_service._finalize_native_artifacts`) converts VM and
Python runtime events into typed header, tick, and terminal result records --
the same `battle_engine.replay.ReplayHeader` / `TickSnapshot` / `MatchResult`
dataclasses, and the same `record_to_dict` / `serialize_record` / `write_replay`
functions, that any reader consumes. There is exactly one serialization path;
the writer cannot drift from what the typed reader understands, because it is
built from the same model.

The header carries `replay_id`, `match_id`, `result_id`, `runtime_kind`,
reproducibility settings, and ordered entrant identity/metadata (including
code/source digests). The terminal result record carries winner, termination
reason, final per-entrant state, score, and entrant statistics/diagnostics
(including structured Python diagnostics where applicable).

The sibling `result.json` references the replay by ID and SHA-256 digest. The
digest is computed over the exact bytes `write_replay` produced, so
`battle_engine.result_model.verify_replay_digest` (or the convenience
`verify_result_replay`) can always confirm a replay file matches its result
byte-for-byte; see "Digest verification" below.

Readers continue accepting schema version 2 and the historical unversioned
v0.1/native formats. See [RESULT_SCHEMA.md](RESULT_SCHEMA.md).

### Compatibility note: v3 was extended in place, not versioned to v4

`battle2.replay` v3 was introduced in the same `v0.3-foundation` development
branch as this extension and has never appeared in a tagged release (see
CHANGELOG.md) -- earlier v3 output only existed as regenerable local/CI
artifacts, not as a format any external consumer depended on. The fields
described below (`runtime_kind`, memory-diff `values`, the tick-zero initial
state record, terminal `agents`, per-agent register/termination state) were
therefore added directly to schema version 3 rather than introduced as a new
version 4. All new fields have safe, explicit defaults (`None`, `()`, or
absence), so a reader encountering an older, pre-extension v3 file (or a
genuine v0.1/v0.2 file) still parses it correctly -- it simply sees the new
fields as absent/default rather than populated. A future incompatible change
to the wire shape (not just an additive field) should bump `SCHEMA_VERSION`
rather than repeat this reasoning.

### Runtime-kind semantics

`ReplayHeader.runtime_kind` is `"vm"` or `"python"` -- matches are homogeneous
(mixed VM/Python is rejected before execution), so one discriminator per match
is sufficient; it is not repeated per tick or per agent. Consumers must branch
on it before interpreting several `AgentState` fields, which mean different
things depending on the runtime that produced them:

| Field | `runtime_kind: "vm"` | `runtime_kind: "python"` |
|---|---|---|
| `pc` | Real fetch address; the VM fetches and executes the opcode at this arena address, wrapped mod `arena_size`. | Agent-opaque controller bookkeeping. It only changes via an explicit `JUMP`/`JUMP_IF_ZERO` action, wraps mod 2^32 (**not** mod `arena_size`), and nothing is ever fetched from it. Most Python agents never move it from their spawn address. |
| `region` | Real code-load footprint (`[start, end]` of the bytes loaded at spawn). | Always a degenerate `[start, start]` one-cell marker; Python source is never written into the arena. |
| `cpu_used` | Count of VM instruction steps executed this tick. | Count of `act()` callback invocations this tick. |
| `register_a` / `register_p` / `zero_flag` | The VM's real A/P/Z registers. | The Python runtime's own A/P/Z-shaped controller state (see `python_runtime.PythonEntrantState`), semantically analogous but tracked independently of any VM. |
| `last_read` | Always `null`; the VM has no distinct "last read" concept (`LOAD` writes directly into `A`). | The byte last read by a `READ` action, or `null` before any read. |
| `termination_reason` | Always `null`; the native VM scheduler does not track a per-agent termination reason at this granularity (see "Termination vocabulary" in RESULT_SCHEMA.md). | `"normal_halt"` or `"forfeit"`, populated once the entrant stops. |

A viewer that visualizes "instruction pointer" or "code footprint" uniformly
across match kinds without checking `runtime_kind` will silently produce
nonsense for Python matches.

### Memory reconstruction

`MemoryDiff` carries `address`, `length`, `owner`, and now `values` -- the
actual bytes written, in address order, one per byte covered by `length`
(consecutive same-owner single-byte writes are still run-length merged into
one diff entry, exactly as before; only the missing byte content has been
added). `values` is empty for genuine legacy v0.1/v0.2 records, which never
captured written values, and for pre-extension v3 files.

Initial arena content (each entrant's spawned bytecode, for VM matches) is
represented the same way as any other write: `VM.load_code` now routes
through the same `_wr8` primitive every `STORE`/`STOREI`/Python `WRITE` uses,
so code placement produces ordinary memory diffs rather than being invisible.
Those diffs, together with each entrant's starting `AgentState`, are published
as an explicit **tick-zero** `TickSnapshot` -- emitted once, immediately after
the header and before any agent acts. Python matches also emit a tick-zero
snapshot (with empty `memory_diffs`, since Python source is never loaded into
the arena) so a reconstruction algorithm can treat "start from tick 0" as a
uniform rule regardless of runtime kind.

To reconstruct arena content at tick N: start from an all-zero `arena_size`
byte array (byte `0` is the `NOP` opcode and the arena's true initial value),
then apply every `memory_diffs` entry's `values` in tick order from tick 0
through tick N inclusive. This is a public, tested procedure -- see
`engine/tests/test_replay_reconstruction.py`, which independently re-derives
ground-truth arena/agent state (via direct `VM`/`Agent` stepping, bypassing
the replay-writing code path entirely) and asserts it against exactly this
reconstruction, for both a VM and a Python match, at every tick.

Reconstruction is currently linear-scan from tick 0 (no snapshot-at-tick-N
shortcut); seeking to a specific tick still requires replaying every diff up
to that point. A denser checkpoint format was deliberately not added in this
change -- see "Known limitations" below.

### Terminal result record

The terminal `record_type: "result"` record's `agents` field now carries the
real final per-entrant `AgentState` (previously always empty). It is built
from the last tick's recorded `AgentState` for each entrant, enriched with
that entrant's final `termination_reason` -- not recomputed independently, so
it cannot drift from what the tick stream already shows. `winner` is `null`
when there is no single winner (unlike `result.json`'s `winner`, which keeps
its existing non-null `"tie"` convention for compatibility -- see
"Winner representation" in RESULT_SCHEMA.md for why the two differ).

### Digest verification

`battle_engine.result_model.verify_replay_digest(envelope, replay_path)` reads
a replay file, computes its SHA-256, and compares it against
`envelope.replay.sha256`, raising a typed `ReplayIntegrityError` (with a
stable `.code`: `replay_reference_missing`, `replay_file_missing`,
`replay_file_unreadable`, or `replay_digest_mismatch`) on any failure.
`verify_result_replay(result_path)` is a convenience wrapper that reads the
`result.json` at `result_path` and resolves its replay relative to
`result_path`'s parent directory.

`read_result` itself never verifies the referenced replay -- verification is
opt-in, invoked explicitly by a caller that needs the guarantee (for example,
a Phase 7 tool building a replay index), so that reading historical results
whose replay was later pruned, moved, or never existed (pMARS) continues to
work exactly as before.

### Python Observation capture: explicitly out of scope

The Python Agent API's `Observation` (`tick`, `agent_id`, `pc`, `register_a`,
`register_p`, `zero_flag`, `last_read`, `alive`) is a read-only view of
engine-owned, per-entrant controller state -- not a separate diagnostic log.
This extension persists that state, once per tick, as part of each entrant's
`AgentState` (`pc`, `register_a`, `register_p`, `zero_flag`, `last_read`),
because it is genuine engine-observable state, no different in kind from the
VM's own registers.

What is **not** captured is a per-callback log of every `Observation` handed
to `act()` -- an entrant can receive up to `action_budget` callbacks in a
single tick, and each would see a slightly different `Observation` as state
changes mid-tick. Persisting all of them would multiply replay volume by the
action budget for no engine-observable benefit: the tick-level `AgentState`
already reflects the end-of-tick outcome, which is what "engine-observable
match state" means. A future feature that needs to show "exactly what agent X
was shown before its 3rd callback in tick 7" would be reconstructing agent
*diagnostic* history, not match state, and is intentionally left out of the
canonical replay guarantee.

That future feature is `bytefray.agent_trace` (see
`docs/specs/agent_lab.md`, unreleased Agent Lab work): a separate,
optional, versioned JSONL artifact carrying exactly the per-callback
Observation/Action/diagnostic history described above. It is not part of
this schema and does not change `battle2.replay` in any way -- confirming
the "intentionally left out" boundary drawn here rather than revisiting
it.

### Known limitations carried forward

- Reconstruction requires a linear scan of `memory_diffs` from tick 0; there
  is no snapshot/checkpoint shortcut for seeking directly to a late tick in a
  long match. Deferred deliberately -- see the Phase 6.5a task scope.
- RNG draws inside agent code are not individually logged; only each
  entrant's derived seed is captured. Reproducing an agent's exact
  intermediate reasoning (not just its actions) requires re-executing its
  source against that seed.
- A truncated/corrupted mid-stream replay (for example, a process killed
  mid-write) still fails the whole read at the point of corruption
  (`ReplayFormatError`, with file/line context) rather than offering a
  partial-recovery mode. This is a deliberate fail-fast choice to avoid
  silently presenting incomplete data as complete.

## Supported input shapes

The replay reader accepts the following historical and current records. All are
converted at the reader boundary to the canonical v0.2 dataclasses in
`battle_engine.replay`.

### v0.1 native header

```json
{"tick": 0, "ver": 6, "config": {"arena_size": 4096, "instr_per_tick": 8, "seed": 1337, "win_mode": "score_fallback", "weights": {}}}
```

`ver` is the native replay format marker. The adapter does not reinterpret this
as the canonical schema version.

### v0.1 native tick snapshot

```json
{
  "tick": 1,
  "agents": [{"id": "A", "pc": 5, "alive": true, "cpu_used": 8, "mem_writes": 1, "region": [0, 14]}],
  "score": {"A": 1},
  "events": [{"type": "kill", "victim": "B", "by": "A"}],
  "memory_diffs": [{"addr": 128, "len": 1, "owner": "A"}]
}
```

Nested events may use `kill`, `death`, or the historical `die` alias. Killers use
the old `by` key. Memory differences use `addr` and `len`.

### Legacy one-event records

Supported types and fields are:

- `spawn`: `tick`, `who`, `pos`
- `move`: `tick`, `who`, `from`, `to`
- `territory` or `claim`: `tick`, `who`, and `cells` as positions or `count`
- `death`, `die`, or `kill`: `tick`, `who` or `victim`, and optional `by`
- `score`: `tick` and a `score` object
- `tick`: `tick`, optional `positions`, `writes` or `claims`, optional `who`, and
  historical single-letter agent position keys such as `"A": [2, 3]`

A position may be a one-dimensional arena address or a historical `[x, y]`
coordinate. Coordinates survive compatibility conversion as domain position
values; no Pygame or Qt values enter the model.

### Summary metadata variants

Replay clients may find arena size at `arena`, `arena_size`, or `params.arena`,
and tick count at `ticks`, `params.ticks`, or `params.ticks_run`. The client
normalizes these once to `arena` and `ticks` before renderer setup. A native
header's `config.arena_size` is authoritative when encountered in-band.

The private `__owners__` value passed by `Kernel` to the old live renderer is not
serialized and is not part of any replay schema.

## Canonical v0.2/v0.3 records

Every serialized record carries:

```json
{
  "schema": "battle2.replay",
  "schema_version": 3,
  "record_type": "header"
}
```

Unknown schema names, versions, and record types fail with `ReplayFormatError`.
Readers add file and line context when processing JSONL. Fields marked
"v3 only" below are present (non-null/non-empty) only on records produced by
the canonical native-match finalization path; a v0.1/v0.2 record, or a
pre-extension v3 record, has them at their default (`null`/`{}`/`()`).

### Header

`record_type: "header"` contains `config` and an optional mapping of agent IDs to
names. `MatchConfiguration` contains `arena_size`, `instr_per_tick`, `seed`,
`win_mode`, and numeric scoring `weights`. v3 only: `replay_id`, `match_id`,
`result_id`, `runtime_kind` (`"vm"` or `"python"`, see "Runtime-kind semantics"
above), `reproducibility` (mirrors `result.json`'s `reproducibility`), and
`entrants` (identity/metadata per entrant, mirroring `result.json`'s
`entrants` shape).

### Tick

`record_type: "tick"` contains:

- `tick`: integer tick number, starting at **0** -- tick 0 is the initial
  state published before any agent acts (see "Memory reconstruction" above);
- `agents`: typed states (`id`, `pc`, `alive`, `cpu_used`, `mem_writes`,
  `region`, and now `register_a`, `register_p`, `zero_flag`, `last_read`,
  `termination_reason` -- see "Runtime-kind semantics" for which fields are
  meaningful for which runtime);
- `score`: agent ID to numeric score;
- `memory_diffs`: `address`, `length`, nullable `owner`, and now `values`
  (the bytes actually written, one per address in the run -- see "Memory
  reconstruction" above); and
- `events`: typed kill/death or agent movement/ownership events.

Agent movement/ownership events exist to retain supported historical records.
They contain only engine-domain IDs, addresses/positions, and cell collections;
they do not contain colors, surfaces, fonts, widget state, or other presentation
fields.

### Result

`record_type: "result"` contains `winner` (nullable when there is no single
winner), `win_mode`, `ticks`, final `score`, and final agent states (now
genuinely populated -- see "Terminal result record" above). v3 only:
`replay_id`, `match_id`, `result_id`, `termination_reason`, and `entrants`
(the same rich per-entrant identity/statistics/diagnostic shape as
`result.json`'s `entrants`). This is the canonical in-memory and replay-stream
result model; it does not replace the v0.1/v0.2 compatibility `summary.json`.

## API

- `deserialize_record` parses canonical JSON/dicts or adapts supported historical
  records.
- `serialize_record` and `record_to_dict` emit canonical records with stable,
  sorted key order (`serialize_record` always sorts keys, so re-serializing a
  parsed record reproduces byte-identical output -- this is what makes replay
  digests verifiable rather than merely descriptive).
- `iter_replay` streams canonical models from mixed compatible JSONL input.
- `write_replay` writes canonical JSONL. As of this extension it is the
  **actual production writer**: `match_service._finalize_native_artifacts`
  builds typed `ReplayHeader`/`TickSnapshot`/`MatchResult` objects and calls
  `write_replay` directly, rather than hand-serializing dicts through a
  second, independently-maintained code path. Writer and reader therefore
  cannot drift from each other by construction.
- `adapt_v01_record` is the explicit compatibility boundary.

The v0.1 `JSONLSink` remains unchanged as the raw per-tick capture mechanism
during a live match (see `telemetry.build_snapshot`); the canonical
finalization step reads that raw output back through `iter_replay` (which
adapts it via `adapt_v01_record`) and rewrites it as a fully typed, identity-
stamped v3 stream via `write_replay`. Replay renderers consume `ReplayHeader`,
`TickSnapshot`, or `MatchResult` and contain no schema-version detection.
