# Bytefray Replay and Event Contract

## Canonical writer

Native Ruleset-v1/v2 matches use `battle2.replay` schema version 3. Every v4
Ruleset identity -- the stable `bytefray-rules-4` (`v4.0.0-rc1` Phase 2) and
both prerelease alphas, `bytefray-rules-4-alpha1`/`-alpha2` -- uses schema
version 4 so process state is present without changing the historical v3
wire shape; the schema did not bump at promotion, since nothing about its
wire shape changed. One authoritative
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

Readers continue accepting schema versions 2 and 3 and the historical
unversioned v0.1/native formats. See [RESULT_SCHEMA.md](RESULT_SCHEMA.md).

### Historical compatibility note: early v3 was extended in place

`battle2.replay` v3 was introduced, and then extended with the fields
described below, in the same `v0.3-foundation` development branch, hours
apart and both before `v0.3.0` was tagged -- so at the time of the
extension, no tagged release yet existed that depended on the
pre-extension v3 record shape; earlier v3 output only existed as
regenerable local/CI artifacts. (`battle2.replay` v3, in this already-
extended form, has since shipped in every tagged release from `v0.3.0`
onward -- see CHANGELOG.md -- so it is not correct to say today that v3
"has never appeared in a tagged release"; the point this note preserves is
narrower: no *tagged release* ever shipped the pre-extension shape that
would need to keep reading.) The fields described below (`runtime_kind`,
memory-diff `values`, the tick-zero initial state record, terminal
`agents`, per-agent register/termination state) were therefore added
directly to schema version 3 rather than introduced as a new version 4.
All new fields have safe, explicit defaults (`None`, `()`, or absence), so
a reader encountering an older, pre-extension v3 file (or a genuine
v0.1/v0.2 file) still parses it correctly -- it simply sees the new fields
as absent/default rather than populated. A future incompatible change to the
historical v3 wire shape (not just an additive field) should use a new schema
version rather than repeat this reasoning. Schema 4 below follows that rule.

### Schema 4 process state

Schema 4 is selected only for Ruleset-v4 production matches (stable
`bytefray-rules-4` and both prerelease alphas alike -- selection is driven
by the resolved Ruleset's process-agent policy, not by which of the three
identities specifically). Every tick and
terminal result record contains a `processes` array. Each entry contains:

- `process_id`: the entrant-local stable ID declared before tick 0;
- `entrant_id`: the owning match entrant ID;
- `anchor`: normalized absolute arena address;
- `disrupted`: whether the process is ineligible at that recorded tick; and
- `reach`: the process's declared circular action/detection reach.

Tick 0 records every declared process co-located at its entrant/core start
before any action executes. Later records make anchor movement and temporary
disruption reconstructable without running agent code. Schema-2/3
serialization omits the `processes` key entirely—even when the in-memory model
uses its empty default—so historical wire bytes and hashes remain unchanged.
Readers give schema-4 `processes` the same empty default for defensive parsing,
but a current production v4 match always emits the real non-empty state.

### Ruleset identity

`ReplayHeader.ruleset_id` (v0.10 Phase 4) is an *additive* header field:
the Bytefray gameplay Ruleset identity (`battle_engine.rules.
BYTEFRAY_RULESET_ID`, see [RULES.md](RULES.md)) this match executed under.
One discriminator per match, on the header only -- the identical precedent
`runtime_kind` already establishes ("it is not repeated per tick or per
agent"; see "Runtime-kind semantics" below). It is **required for current
native writers** -- `match_service._finalize_native_artifacts` records the
exact resolved Ruleset identity on every header it produces -- but it is
**not required for all historical artifacts**: any header written before
this field existed simply has it absent (`None`), and remains fully
readable.

No `SCHEMA_VERSION` bump was required: schema version 3 was already
designed to be extended in place with safe, explicit-default additive
fields (see "Compatibility note" above), and this addition follows that
exact precedent -- every released reader accepts an unrecognized top-level
key on a header record (verified directly against the `v0.9.0`-tagged
`replay.py` in an isolated worktree, not merely inferred). `battle_engine.
replay.resolve_replay_ruleset(header)` gives the honest,
confidence-qualified answer for a header that predates the field:
`"recorded"` when present, `"recovered"` `bytefray-rules-1` for a header
whose `schema_version` is **exactly** `3` (not `>= 3`) and is missing it
(schema version 3 never existed before the v0.3.0 development branch that
also established the currently-frozen gameplay semantics -- see
[RULES.md](RULES.md)), or `"unknown"` for anything else, including a
schema-version-2 header and a schema-4-or-later header missing its required
recorded identity.
Schema version 2 deliberately does **not** recover: it was genuinely the
pre-rename `v0.2.0` release's own canonical wire format (confirmed by
inspecting that tag's own `replay.py`), so a schema-version-2 header
cannot be proven to fall inside the source-proven-stable v0.3.0+ window --
treating it as `"recovered"` would be a guess, not evidence. The check is
deliberately exact equality rather than `>=` so that a future schema
version 4+ is never silently auto-recovered by this function without a
deliberate decision (and update to this function) establishing that it
belongs in the same proven window -- an unrelated future wire-shape change
is not automatically also a Ruleset-provenance fact.

`ruleset_id` **is** a first-class input to `match_id`'s hash payload as of
v0.10 Phase 4 -- see [RESULT_SCHEMA.md](RESULT_SCHEMA.md#identity-recipe)
for the full rationale and the documented native-ID transition this
causes, which applies identically here: `replay_id`/`match_id`/`result_id`
on the header are the same three IDs `result.json` carries, computed by
the same `canonical_match_id`.

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

The Agent API v1 `Observation` (`tick`, `agent_id`, `pc`, `register_a`,
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

The same boundary applies to Agent API v2: schema 4 records engine-owned
process anchors/reach/disruption at tick granularity, not every
`ObservationV2` delivered during that tick. Exact callback history belongs in
the optional trace surface, not in canonical match-state reconstruction.

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

## Canonical v0.2/v0.3/v4 records

Every serialized record carries:

```json
{
  "schema": "battle2.replay",
  "schema_version": 4,
  "record_type": "header"
}
```

Unknown schema names, unsupported versions, and record types fail with
`ReplayFormatError`. Readers add file and line context when processing JSONL.
Fields marked "v3+" below are present (non-null/non-empty) only on records produced by
the canonical native-match finalization path; a v0.1/v0.2 record, or a
pre-extension v3 record, has them at their default (`null`/`{}`/`()`).

### Header

`record_type: "header"` contains `config` and an optional mapping of agent IDs to
names. `MatchConfiguration` contains `arena_size`, `instr_per_tick`, `seed`,
`win_mode`, and numeric scoring `weights`. v3+: `replay_id`, `match_id`,
`result_id`, `runtime_kind` (`"vm"` or `"python"`, see "Runtime-kind semantics"
above), `reproducibility` (mirrors `result.json`'s `reproducibility`), and
`entrants` (identity/metadata per entrant, mirroring `result.json`'s
`entrants` shape). `ruleset_id` (v0.10 Phase 4, see "Ruleset identity"
above) is present (non-null) only on a header produced by a current native
writer; absent on any header written before that field existed.

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

Schema 4 additionally carries `processes`, the complete process snapshot
described in "Schema 4 process state" above. Schema 2/3 omit this key.

Agent movement/ownership events exist to retain supported historical records.
They contain only engine-domain IDs, addresses/positions, and cell collections;
they do not contain colors, surfaces, fonts, widget state, or other presentation
fields.

### Result

`record_type: "result"` contains `winner` (nullable when there is no single
winner), `win_mode`, `ticks`, final `score`, and final agent states (now
genuinely populated -- see "Terminal result record" above). v3+:
`replay_id`, `match_id`, `result_id`, `termination_reason`, and `entrants`
(the same rich per-entrant identity/statistics/diagnostic shape as
`result.json`'s `entrants`). This is the canonical in-memory and replay-stream
result model; it does not replace the v0.1/v0.2 compatibility `summary.json`.
Schema 4 also carries the terminal `processes` snapshot; schema 2/3 omit it.

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
