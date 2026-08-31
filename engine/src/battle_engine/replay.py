"""Versioned replay records with v0.1/v0.2 compatibility conversion."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TypeAlias

from battle_engine.rules import BYTEFRAY_RULESET_ID, RulesetProvenance

SCHEMA_NAME = "battle2.replay"
SCHEMA_VERSION = 4
SUPPORTED_SCHEMA_VERSIONS = (2, 3, 4)


class ReplayFormatError(ValueError):
    """A replay record is malformed or uses an unsupported schema."""


Position: TypeAlias = int | tuple[int, int]


@dataclass(frozen=True)
class MatchConfiguration:
    arena_size: int
    instr_per_tick: int = 0
    seed: int | None = None
    win_mode: str = "score_fallback"
    weights: Mapping[str, int | float] = field(default_factory=dict)


@dataclass(frozen=True)
class ProcessState:
    process_id: str
    entrant_id: str
    anchor: int
    disrupted: bool
    reach: int


@dataclass(frozen=True)
class AgentState:
    agent_id: str
    pc: Position
    alive: bool = True
    cpu_used: int = 0
    mem_writes: int = 0
    region: tuple[int, int] | None = None
    # Engine-owned register/controller state, populated where the runtime
    # tracks it. ``register_a``/``register_p``/``zero_flag`` are meaningful
    # for both VM and Python runtimes (both track A/P/Z-shaped state).
    # ``last_read`` is Python-only; the VM has no equivalent concept.
    register_a: int | None = None
    register_p: int | None = None
    zero_flag: bool | None = None
    last_read: int | None = None
    # Populated on the terminal result record (and, for Python entrants,
    # on the tick where the entrant stopped): "normal_halt" or "forfeit".
    # Always ``None`` for VM entrants -- the native VM scheduler does not
    # track a per-agent termination reason at this granularity.
    termination_reason: str | None = None
    # v3 research Phase 2: this entrant's bounded-locality execution locus
    # on this tick, or ``None`` under every Ruleset whose addressing is
    # absolute. Round-tripped so an experimental replay can be re-read and
    # (later, if the mechanic survives) visualized; the key is omitted
    # entirely from serialized output when ``None``, so no non-locality
    # replay record changes shape. Additive to schema version 3.
    locus: int | None = None


@dataclass(frozen=True)
class MemoryDiff:
    address: int
    length: int = 1
    owner: str | None = None
    # Byte values actually written, in address order, one per byte covered
    # by ``length`` (accounting for a possible run of merged single-byte
    # writes). Empty for legacy v0.1/v0.2 records, which never captured
    # written values.
    values: tuple[int, ...] = ()


@dataclass(frozen=True)
class KillDeathEvent:
    event_type: Literal["kill", "death"]
    victim: str
    killer: str | None = None


@dataclass(frozen=True)
class AgentEvent:
    """Renderer-neutral form of historical movement/ownership events."""

    event_type: Literal["spawn", "move", "territory", "claim"]
    agent_id: str | None = None
    position: Position | None = None
    previous_position: Position | None = None
    cells: tuple[Position, ...] = ()
    cell_count: int | None = None


@dataclass(frozen=True)
class RuntimeEvent:
    event_type: Literal["forfeit"]
    victim: str
    reason: str
    stage: str | None = None
    tick: int | None = None
    action_slot: int | None = None


EngineEvent: TypeAlias = KillDeathEvent | AgentEvent | RuntimeEvent


RuntimeKind: TypeAlias = Literal["vm", "python"]


@dataclass(frozen=True)
class ReplayHeader:
    config: MatchConfiguration
    agents: Mapping[str, str] = field(default_factory=dict)
    # Canonical v3 identity and match-composition metadata. ``None``/empty
    # for v0.1/v0.2 headers and for any header not produced by the
    # canonical native-match finalization step.
    replay_id: str | None = None
    match_id: str | None = None
    result_id: str | None = None
    runtime_kind: RuntimeKind | None = None
    reproducibility: Mapping[str, Any] = field(default_factory=dict)
    entrants: tuple[Mapping[str, Any], ...] = ()
    # v0.10 Phase 4: the Bytefray gameplay Ruleset identity this match
    # executed under. One discriminator per match, carried on the header
    # only -- the identical precedent ``runtime_kind`` already establishes
    # ("it is not repeated per tick or per agent"; see "Runtime-kind
    # semantics" in docs/REPLAY_SCHEMA.md). Additive to schema version 3
    # (extended in place, like every other v3 field before it -- see
    # docs/REPLAY_SCHEMA.md's "Compatibility note"); ``None`` for any
    # header produced before this field existed, and always ``None`` for a
    # non-native/non-canonical header (Redcode/pMARS produces no canonical
    # replay at all, so this case does not arise in practice).
    ruleset_id: str | None = None
    schema: str = SCHEMA_NAME
    schema_version: int = SCHEMA_VERSION
    record_type: Literal["header"] = "header"


@dataclass(frozen=True)
class TickSnapshot:
    tick: int
    agents: tuple[AgentState, ...] = ()
    score: Mapping[str, int | float] = field(default_factory=dict)
    memory_diffs: tuple[MemoryDiff, ...] = ()
    events: tuple[EngineEvent, ...] = ()
    processes: tuple[ProcessState, ...] = ()
    schema: str = SCHEMA_NAME
    schema_version: int = SCHEMA_VERSION
    record_type: Literal["tick"] = "tick"


@dataclass(frozen=True)
class MatchResult:
    winner: str | None
    win_mode: str
    ticks: int
    score: Mapping[str, int | float] = field(default_factory=dict)
    agents: tuple[AgentState, ...] = ()
    # Canonical v3 identity/outcome metadata; see ``ReplayHeader``.
    replay_id: str | None = None
    match_id: str | None = None
    result_id: str | None = None
    termination_reason: str | None = None
    entrants: tuple[Mapping[str, Any], ...] = ()
    processes: tuple[ProcessState, ...] = ()
    schema: str = SCHEMA_NAME
    schema_version: int = SCHEMA_VERSION
    record_type: Literal["result"] = "result"


ReplayRecord: TypeAlias = ReplayHeader | TickSnapshot | MatchResult


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReplayFormatError(f"{label} must be an object")
    return value


def _as_int(value: Any, label: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ReplayFormatError(f"{label} must be an integer") from exc


def _position(value: Any, label: str) -> Position:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return (_as_int(value[0], label), _as_int(value[1], label))
    raise ReplayFormatError(f"{label} must be an arena address or [x, y] position")


def _config_from_dict(value: Any) -> MatchConfiguration:
    data = _require_mapping(value, "config")
    if "arena_size" not in data:
        raise ReplayFormatError("config.arena_size is required")
    weights = _require_mapping(data.get("weights", {}), "config.weights")
    return MatchConfiguration(
        arena_size=_as_int(data["arena_size"], "config.arena_size"),
        instr_per_tick=_as_int(data.get("instr_per_tick", 0), "config.instr_per_tick"),
        seed=(None if data.get("seed") is None else _as_int(data["seed"], "config.seed")),
        win_mode=str(data.get("win_mode", "score_fallback")),
        weights={str(k): v for k, v in weights.items() if isinstance(v, (int, float))},
    )


def _process_from_dict(value: Any) -> ProcessState:
    data = _require_mapping(value, "process")
    process_id = data.get("process_id")
    if not isinstance(process_id, str) or not process_id:
        raise ReplayFormatError("process.process_id is required")
    entrant_id = data.get("entrant_id")
    if not isinstance(entrant_id, str) or not entrant_id:
        raise ReplayFormatError("process.entrant_id is required")
    return ProcessState(
        process_id=process_id,
        entrant_id=entrant_id,
        anchor=_as_int(data.get("anchor", 0), "process.anchor"),
        disrupted=bool(data.get("disrupted", False)),
        reach=_as_int(data.get("reach", 0), "process.reach"),
    )


def _agent_from_dict(value: Any) -> AgentState:
    data = _require_mapping(value, "agent")
    agent_id = data.get("id", data.get("agent_id"))
    if not isinstance(agent_id, str) or not agent_id:
        raise ReplayFormatError("agent.id is required")
    pc = _position(data.get("pc", data.get("position", 0)), "agent.pc")
    region_value = data.get("region")
    region = None
    if region_value is not None:
        parsed = _position(region_value, "agent.region")
        if isinstance(parsed, int):
            raise ReplayFormatError("agent.region must be [start, end]")
        region = parsed
    register_a = data.get("register_a")
    register_p = data.get("register_p")
    last_read = data.get("last_read")
    zero_flag = data.get("zero_flag")
    termination_reason = data.get("termination_reason")
    if termination_reason is not None and not isinstance(termination_reason, str):
        raise ReplayFormatError("agent.termination_reason must be a string or null")
    locus = data.get("locus")
    return AgentState(
        agent_id=agent_id,
        pc=pc,
        alive=bool(data.get("alive", True)),
        cpu_used=_as_int(data.get("cpu_used", 0), "agent.cpu_used"),
        mem_writes=_as_int(data.get("mem_writes", 0), "agent.mem_writes"),
        region=region,
        register_a=(None if register_a is None else _as_int(register_a, "agent.register_a")),
        register_p=(None if register_p is None else _as_int(register_p, "agent.register_p")),
        zero_flag=(None if zero_flag is None else bool(zero_flag)),
        last_read=(None if last_read is None else _as_int(last_read, "agent.last_read")),
        termination_reason=termination_reason,
        locus=(None if locus is None else _as_int(locus, "agent.locus")),
    )


def _diff_from_dict(value: Any) -> MemoryDiff:
    data = _require_mapping(value, "memory diff")
    address = data.get("address", data.get("addr"))
    if address is None:
        raise ReplayFormatError("memory diff address is required")
    owner = data.get("owner")
    if owner is not None and not isinstance(owner, str):
        raise ReplayFormatError("memory diff owner must be a string or null")
    values_value = data.get("values", ())
    if not isinstance(values_value, (list, tuple)):
        raise ReplayFormatError("memory diff values must be an array")
    return MemoryDiff(
        address=_as_int(address, "memory diff address"),
        length=_as_int(data.get("length", data.get("len", 1)), "memory diff length"),
        owner=owner,
        values=tuple(_as_int(item, "memory diff value") for item in values_value),
    )


def _event_from_dict(value: Any) -> EngineEvent:
    data = _require_mapping(value, "event")
    kind = data.get("event_type", data.get("type"))
    if kind == "die":
        kind = "death"
    if kind in ("kill", "death"):
        victim = data.get("victim", data.get("who"))
        if not isinstance(victim, str) or not victim:
            raise ReplayFormatError(f"{kind} event requires a victim")
        killer = data.get("killer", data.get("by"))
        if killer is not None and not isinstance(killer, str):
            raise ReplayFormatError("event killer must be a string or null")
        return KillDeathEvent(kind, victim, killer)
    if kind == "forfeit":
        victim = data.get("victim")
        reason = data.get("reason")
        if not isinstance(victim, str) or not isinstance(reason, str):
            raise ReplayFormatError("forfeit event requires victim and reason")
        return RuntimeEvent(
            "forfeit",
            victim,
            reason,
            str(data["stage"]) if data.get("stage") is not None else None,
            None if data.get("tick") is None else _as_int(data["tick"], "event.tick"),
            (
                None
                if data.get("action_slot") is None
                else _as_int(data["action_slot"], "event.action_slot")
            ),
        )
    if kind in ("spawn", "move", "territory", "claim"):
        agent_id = data.get("agent_id", data.get("who"))
        if agent_id is not None and not isinstance(agent_id, str):
            raise ReplayFormatError("event agent_id must be a string or null")
        position_value = data.get("position", data.get("pos", data.get("to")))
        previous_value = data.get("previous_position", data.get("from"))
        cells_value = data.get("cells", ())
        cell_count = data.get("cell_count", data.get("count"))
        if isinstance(cells_value, int):
            cell_count, cells_value = cells_value, ()
        if not isinstance(cells_value, (list, tuple)):
            raise ReplayFormatError("event cells must be an array or count")
        return AgentEvent(
            event_type=kind,
            agent_id=agent_id,
            position=(
                None
                if position_value is None
                else _position(position_value, "event position")
            ),
            previous_position=(
                None
                if previous_value is None
                else _position(previous_value, "event previous_position")
            ),
            cells=tuple(_position(cell, "event cell") for cell in cells_value),
            cell_count=(None if cell_count is None else _as_int(cell_count, "event cell_count")),
        )
    raise ReplayFormatError(f"unsupported event type: {kind!r}")


def record_to_dict(record: ReplayRecord) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema": SCHEMA_NAME,
        "schema_version": record.schema_version,
        "record_type": record.record_type,
    }
    if isinstance(record, ReplayHeader):
        base["config"] = {
            "arena_size": record.config.arena_size,
            "instr_per_tick": record.config.instr_per_tick,
            "seed": record.config.seed,
            "win_mode": record.config.win_mode,
            "weights": dict(record.config.weights),
        }
        base["agents"] = dict(record.agents)
        base.update(
            replay_id=record.replay_id,
            match_id=record.match_id,
            result_id=record.result_id,
            runtime_kind=record.runtime_kind,
            reproducibility=dict(record.reproducibility),
            entrants=[dict(entrant) for entrant in record.entrants],
            ruleset_id=record.ruleset_id,
        )
    elif isinstance(record, TickSnapshot):
        base.update(
            tick=record.tick,
            agents=[_agent_to_dict(agent) for agent in record.agents],
            score=dict(record.score),
            memory_diffs=[
                {
                    "address": diff.address,
                    "length": diff.length,
                    "owner": diff.owner,
                    "values": list(diff.values),
                }
                for diff in record.memory_diffs
            ],
            events=[_event_to_dict(event) for event in record.events],
        )
        # Process state is a schema-v4 addition.  Omitting the key entirely
        # from v2/v3 output preserves those historical wire encodings and
        # their byte-level replay digests.
        if record.schema_version >= 4:
            base["processes"] = [
                _process_to_dict(process) for process in record.processes
            ]
    elif isinstance(record, MatchResult):
        base.update(
            winner=record.winner,
            win_mode=record.win_mode,
            ticks=record.ticks,
            score=dict(record.score),
            agents=[_agent_to_dict(agent) for agent in record.agents],
            replay_id=record.replay_id,
            match_id=record.match_id,
            result_id=record.result_id,
            termination_reason=record.termination_reason,
            entrants=[dict(entrant) for entrant in record.entrants],
        )
        if record.schema_version >= 4:
            base["processes"] = [
                _process_to_dict(process) for process in record.processes
            ]
    else:  # pragma: no cover - protects callers bypassing static typing
        raise TypeError(f"unsupported replay record: {type(record).__name__}")
    return base


def _process_to_dict(process: ProcessState) -> dict[str, Any]:
    return {
        "process_id": process.process_id,
        "entrant_id": process.entrant_id,
        "anchor": process.anchor,
        "disrupted": process.disrupted,
        "reach": process.reach,
    }


def _agent_to_dict(agent: AgentState) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": agent.agent_id,
        "pc": list(agent.pc) if isinstance(agent.pc, tuple) else agent.pc,
        "alive": agent.alive,
        "cpu_used": agent.cpu_used,
        "mem_writes": agent.mem_writes,
        "region": list(agent.region) if agent.region is not None else None,
        "register_a": agent.register_a,
        "register_p": agent.register_p,
        "zero_flag": agent.zero_flag,
        "last_read": agent.last_read,
        "termination_reason": agent.termination_reason,
    }
    # v3 research Phase 2: omitted, never serialized as null, so a
    # non-locality replay is byte-identical to one written before the field
    # existed.
    if agent.locus is not None:
        payload["locus"] = agent.locus
    return payload


def _event_to_dict(event: EngineEvent) -> dict[str, Any]:
    if isinstance(event, KillDeathEvent):
        return {
            "event_type": event.event_type,
            "victim": event.victim,
            "killer": event.killer,
        }
    if isinstance(event, RuntimeEvent):
        return {
            "event_type": event.event_type,
            "victim": event.victim,
            "reason": event.reason,
            "stage": event.stage,
            "tick": event.tick,
            "action_slot": event.action_slot,
        }
    return {
        "event_type": event.event_type,
        "agent_id": event.agent_id,
        "position": list(event.position) if isinstance(event.position, tuple) else event.position,
        "previous_position": (
            list(event.previous_position)
            if isinstance(event.previous_position, tuple)
            else event.previous_position
        ),
        "cells": [list(cell) if isinstance(cell, tuple) else cell for cell in event.cells],
        "cell_count": event.cell_count,
    }


def serialize_record(record: ReplayRecord) -> str:
    """Serialize one canonical record with stable, sorted key order.

    Deterministic key ordering makes this the single authoritative wire
    encoding: the same record always produces the same bytes, so digests
    computed over serialized output (see ``result_model``) are stable
    across re-serialization, not just over whatever bytes happened to be
    written first.
    """

    return json.dumps(record_to_dict(record), sort_keys=True, separators=(",", ":"))


def deserialize_record(value: str | bytes | Mapping[str, Any]) -> ReplayRecord:
    if isinstance(value, (str, bytes)):
        try:
            raw = json.loads(value)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ReplayFormatError(f"invalid replay JSON: {exc}") from exc
    else:
        raw = value
    data = _require_mapping(raw, "replay record")

    if "schema" not in data:
        return adapt_v01_record(data)
    if data.get("schema") != SCHEMA_NAME:
        raise ReplayFormatError(f"unsupported replay schema: {data.get('schema')!r}")
    version = data.get("schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ReplayFormatError(
            f"unsupported {SCHEMA_NAME} schema version {version!r}; "
            f"supported versions are {SUPPORTED_SCHEMA_VERSIONS}"
        )

    record_type = data.get("record_type")
    if record_type == "header":
        agents = _require_mapping(data.get("agents", {}), "header.agents")
        runtime_kind = data.get("runtime_kind")
        if runtime_kind is not None and runtime_kind not in ("vm", "python"):
            raise ReplayFormatError("header.runtime_kind must be 'vm', 'python', or null")
        reproducibility = _require_mapping(
            data.get("reproducibility", {}), "header.reproducibility"
        )
        entrants_value = data.get("entrants", ())
        if not isinstance(entrants_value, (list, tuple)):
            raise ReplayFormatError("header.entrants must be an array")
        ruleset_id = data.get("ruleset_id")
        if ruleset_id is not None and not isinstance(ruleset_id, str):
            raise ReplayFormatError("header.ruleset_id must be a string or null")
        return ReplayHeader(
            _config_from_dict(data.get("config")),
            {str(k): str(v) for k, v in agents.items()},
            replay_id=data.get("replay_id"),
            match_id=data.get("match_id"),
            result_id=data.get("result_id"),
            runtime_kind=runtime_kind,
            reproducibility=dict(reproducibility),
            entrants=tuple(
                _require_mapping(item, "header.entrants item") for item in entrants_value
            ),
            ruleset_id=ruleset_id,
            schema_version=version,
        )
    if record_type == "tick":
        return TickSnapshot(
            tick=_as_int(data.get("tick"), "tick.tick"),
            agents=tuple(_agent_from_dict(item) for item in data.get("agents", ())),
            score=dict(_require_mapping(data.get("score", {}), "tick.score")),
            memory_diffs=tuple(_diff_from_dict(item) for item in data.get("memory_diffs", ())),
            events=tuple(_event_from_dict(item) for item in data.get("events", ())),
            processes=tuple(_process_from_dict(item) for item in data.get("processes", ())),
            schema_version=version,
        )
    if record_type == "result":
        winner = data.get("winner")
        if winner is not None and not isinstance(winner, str):
            raise ReplayFormatError("result.winner must be a string or null")
        termination_reason = data.get("termination_reason")
        if termination_reason is not None and not isinstance(termination_reason, str):
            raise ReplayFormatError("result.termination_reason must be a string or null")
        result_entrants_value = data.get("entrants", ())
        if not isinstance(result_entrants_value, (list, tuple)):
            raise ReplayFormatError("result.entrants must be an array")
        return MatchResult(
            winner=winner,
            win_mode=str(data.get("win_mode", "score_fallback")),
            ticks=_as_int(data.get("ticks"), "result.ticks"),
            score=dict(_require_mapping(data.get("score", {}), "result.score")),
            agents=tuple(_agent_from_dict(item) for item in data.get("agents", ())),
            replay_id=data.get("replay_id"),
            match_id=data.get("match_id"),
            result_id=data.get("result_id"),
            termination_reason=termination_reason,
            entrants=tuple(
                _require_mapping(item, "result.entrants item")
                for item in result_entrants_value
            ),
            processes=tuple(_process_from_dict(item) for item in data.get("processes", ())),
            schema_version=version,
        )
    raise ReplayFormatError(f"unsupported record_type: {record_type!r}")


def adapt_v01_record(data: Mapping[str, Any]) -> ReplayRecord:
    """Convert a supported v0.1/native or legacy record to the v0.2 model."""
    if "ver" in data and "config" in data:
        return ReplayHeader(config=_config_from_dict(data["config"]), schema_version=2)

    if isinstance(data.get("agents"), list):
        return TickSnapshot(
            tick=_as_int(data.get("tick", 0), "snapshot.tick"),
            agents=tuple(_agent_from_dict(item) for item in data["agents"]),
            score=dict(_require_mapping(data.get("score", {}), "snapshot.score")),
            memory_diffs=tuple(_diff_from_dict(item) for item in data.get("memory_diffs", ())),
            events=tuple(_event_from_dict(item) for item in data.get("events", ())),
            schema_version=2,
        )

    kind = data.get("type")
    if kind in ("spawn", "move", "territory", "claim", "death", "die", "kill"):
        return TickSnapshot(
            tick=_as_int(data.get("tick", 0), "event.tick"),
            events=(_event_from_dict(data),),
            schema_version=2,
        )
    if kind == "tick":
        positions = _require_mapping(data.get("positions", {}), "tick.positions")
        normalized_positions = dict(positions)
        for key, value in data.items():
            if (
                isinstance(key, str)
                and len(key) == 1
                and key.isalpha()
                and key not in normalized_positions
            ):
                normalized_positions[key] = value
        agents = tuple(
            AgentState(str(agent_id), _position(position, "tick position"))
            for agent_id, position in normalized_positions.items()
        )
        writes = data.get("writes", data.get("claims", ()))
        events: tuple[EngineEvent, ...] = ()
        if writes:
            if not isinstance(writes, (list, tuple)):
                raise ReplayFormatError("tick writes must be an array")
            events = (
                AgentEvent(
                    "claim",
                    data.get("who") if isinstance(data.get("who"), str) else None,
                    cells=tuple(_position(cell, "tick write") for cell in writes),
                ),
            )
        return TickSnapshot(
            tick=_as_int(data.get("tick", 0), "tick.tick"),
            agents=agents,
            events=events,
            schema_version=2,
        )
    if kind == "score":
        score_value = data.get("score", {})
        return TickSnapshot(
            tick=_as_int(data.get("tick", 0), "score.tick"),
            score=dict(_require_mapping(score_value, "score.score")),
            schema_version=2,
        )
    raise ReplayFormatError(
        "unrecognized replay record: expected a v0.1 header, snapshot, or legacy event"
    )


def iter_replay(path: str | Path) -> Iterator[ReplayRecord]:
    with Path(path).open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                yield deserialize_record(line)
            except ReplayFormatError as exc:
                raise ReplayFormatError(f"{path}:{line_number}: {exc}") from exc


def write_replay(path: str | Path, records: Iterable[ReplayRecord]) -> None:
    with Path(path).open("w", encoding="utf-8") as stream:
        stream.writelines(serialize_record(record) + "\n" for record in records)


def resolve_replay_ruleset(header: ReplayHeader) -> RulesetProvenance:
    """Attribute a confidence-qualified Ruleset identity to one replay header.

    * ``ruleset_id`` present -> ``"recorded"`` with that exact value.
    * ``ruleset_id`` absent, ``schema_version == 3`` -> ``"recovered"``
      ``BYTEFRAY_RULESET_ID``. Schema version 3 was introduced (and
      extended into its current shape) entirely within the v0.3.0
      development branch, before v0.3.0 was ever tagged (see
      docs/REPLAY_SCHEMA.md's "Compatibility note"), so every real
      schema-version-3 record -- adapted or canonical -- falls inside the
      source-proven-stable v0.3.0+ window docs/RULES.md establishes.
    * ``ruleset_id`` absent, any other ``schema_version`` -> ``"unknown"``.
      Deliberately an exact ``== 3`` check, not ``>= 3``: schema version 2
      was genuinely the canonical wire format of the pre-rename ``v0.2.0``
      release (confirmed by inspecting that tag's own ``replay.py``), and
      the same internal ``schema_version == 2`` shape is also what a
      genuinely unversioned v0.1 record adapts to
      (:func:`adapt_v01_record`) -- neither can be proven to fall inside the
      window docs/RULES.md's historical evidence actually covers, so this
      deliberately does not guess. A future schema version greater than 3
      is equally not automatically recoverable: whether it still falls
      inside a Ruleset-v1-proven window is a fact about *that* version's own
      history, to be established (and this function updated) deliberately
      when that version is introduced, never inferred from ``>=``.
    """

    if header.ruleset_id is not None:
        return RulesetProvenance(header.ruleset_id, "recorded")
    if header.schema_version == 3:
        return RulesetProvenance(BYTEFRAY_RULESET_ID, "recovered")
    return RulesetProvenance(None, "unknown")
