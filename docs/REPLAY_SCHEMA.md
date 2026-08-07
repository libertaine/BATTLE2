# BATTLE2 Replay and Event Contract

## v0.3 canonical writer

New native matches use `battle2.replay` schema version 3. One authoritative
finalization path converts VM and Python runtime events into header, tick, and
terminal result records. The header carries `replay_id`, `match_id`, `result_id`,
reproducibility settings, ordered entrant identity, and code/source digests. The
terminal result carries winner, termination reason, score, entrant statistics,
and structured Python diagnostics where applicable.

The sibling `result.json` references the replay by ID and SHA-256 digest. Readers
continue accepting schema version 2 and the historical unversioned v0.1/native
formats. See [RESULT_SCHEMA.md](RESULT_SCHEMA.md).

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

## Canonical v0.2 records

Every serialized record carries:

```json
{
  "schema": "battle2.replay",
  "schema_version": 2,
  "record_type": "header"
}
```

Unknown schema names, versions, and record types fail with `ReplayFormatError`.
Readers add file and line context when processing JSONL.

### Header

`record_type: "header"` contains `config` and an optional mapping of agent IDs to
names. `MatchConfiguration` contains `arena_size`, `instr_per_tick`, `seed`,
`win_mode`, and numeric scoring `weights`.

### Tick

`record_type: "tick"` contains:

- `tick`: integer tick number;
- `agents`: typed states (`id`, `pc`, `alive`, `cpu_used`, `mem_writes`, `region`);
- `score`: agent ID to numeric score;
- `memory_diffs`: `address`, `length`, and nullable `owner`; and
- `events`: typed kill/death or agent movement/ownership events.

Agent movement/ownership events exist to retain supported historical records.
They contain only engine-domain IDs, addresses/positions, and cell collections;
they do not contain colors, surfaces, fonts, widget state, or other presentation
fields.

### Result

`record_type: "result"` contains `winner` (nullable for a tie), `win_mode`,
`ticks`, final `score`, and final agent states. This is the canonical in-memory
and future replay-stream result model; it does not replace either v0.1 summary
writer in this migration phase.

## API

- `deserialize_record` parses canonical JSON/dicts or adapts supported historical
  records.
- `serialize_record` and `record_to_dict` emit canonical v0.2 records.
- `iter_replay` streams canonical models from mixed compatible JSONL input.
- `write_replay` writes canonical JSONL.
- `adapt_v01_record` is the explicit compatibility boundary.

The v0.1 `JSONLSink` remains unchanged. Replay renderers now consume
`ReplayHeader`, `TickSnapshot`, or `MatchResult` and contain no schema-version
detection.
