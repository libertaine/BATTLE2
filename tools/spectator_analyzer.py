"""Deterministic factual spectator-event extraction for Schema 4 replays.

This is research infrastructure, not a public spectator API. It deliberately
derives only facts supported by the canonical replay and keeps presentation or
"drama" interpretation in a later layer.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from battle_engine.replay import (
    AgentEvent,
    KillDeathEvent,
    MatchResult,
    ReplayFormatError,
    ReplayHeader,
    RuntimeEvent,
    TickSnapshot,
    deserialize_record,
)

SOURCE_SCHEMA = "battle2.replay"
SOURCE_SCHEMA_VERSION = 4
SEMANTIC_SCHEMA = "bytefray.spectator_events"
SEMANTIC_SCHEMA_VERSION = 1


class SpectatorAnalysisError(ValueError):
    """A replay cannot support trustworthy spectator-event extraction."""


class SemanticEventKind(str, Enum):
    FOREIGN_OWNERSHIP_OVERWRITE = "FOREIGN_OWNERSHIP_OVERWRITE"
    CORE_DISRUPTION = "CORE_DISRUPTION"
    DETECTION_GAINED = "DETECTION_GAINED"
    DETECTION_LOST = "DETECTION_LOST"
    AGENT_ELIMINATED = "AGENT_ELIMINATED"
    AGENT_FORFEITED = "AGENT_FORFEITED"
    VICTORY = "VICTORY"


@dataclass(frozen=True)
class SemanticEvent:
    tick: int
    kind: SemanticEventKind
    entrant_id: str | None = None
    attacker_entrant_id: str | None = None
    target_entrant_id: str | None = None
    target_process_id: str | None = None
    viewer_entrant_id: str | None = None
    address: int | None = None
    previous_owner: str | None = None
    new_owner: str | None = None
    killer_entrant_id: str | None = None
    cause: str | None = None
    reason: str | None = None
    stage: str | None = None
    action_slot: int | None = None
    attribution: str | None = None
    candidate_attacker_entrant_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SpectatorAnalysis:
    source_path: str
    source_sha256: str
    replay_id: str | None
    match_id: str | None
    ruleset_id: str | None
    first_tick: int
    last_tick: int
    result_ticks: int
    events: tuple[SemanticEvent, ...]


@dataclass(frozen=True)
class _LoadedReplay:
    source_path: Path
    source_sha256: str
    header: ReplayHeader
    ticks: tuple[TickSnapshot, ...]
    result: MatchResult


def circular_distance(first: int, second: int, arena_size: int) -> int:
    distance = abs(first - second)
    return min(distance, arena_size - distance)


def _require_fields(value: Mapping[str, Any], required: Iterable[str], label: str) -> None:
    missing = sorted(set(required) - value.keys())
    if missing:
        raise SpectatorAnalysisError(f"{label} missing required field(s): {', '.join(missing)}")


def _require_array(value: Mapping[str, Any], field: str, label: str) -> list[Any]:
    item = value[field]
    if not isinstance(item, list):
        raise SpectatorAnalysisError(f"{label}.{field} must be an array")
    return item


def _require_integer(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise SpectatorAnalysisError(f"{label} must be an integer")
    return value


def _validate_process(value: Any, label: str, arena_size: int) -> None:
    if not isinstance(value, Mapping):
        raise SpectatorAnalysisError(f"{label} must be an object")
    _require_fields(
        value,
        ("process_id", "entrant_id", "anchor", "disrupted", "reach"),
        label,
    )
    if not isinstance(value["process_id"], str) or not value["process_id"]:
        raise SpectatorAnalysisError(f"{label}.process_id must be a non-empty string")
    if not isinstance(value["entrant_id"], str) or not value["entrant_id"]:
        raise SpectatorAnalysisError(f"{label}.entrant_id must be a non-empty string")
    anchor = _require_integer(value["anchor"], f"{label}.anchor")
    if not 0 <= anchor < arena_size:
        raise SpectatorAnalysisError(f"{label}.anchor must be within the {arena_size}-cell arena")
    if not isinstance(value["disrupted"], bool):
        raise SpectatorAnalysisError(f"{label}.disrupted must be a boolean")
    reach = _require_integer(value["reach"], f"{label}.reach")
    if reach < 0:
        raise SpectatorAnalysisError(f"{label}.reach must be non-negative")


def _validate_record_shape(value: Any, line_number: int, arena_size: int | None) -> int | None:
    label = f"line {line_number}"
    if not isinstance(value, Mapping):
        raise SpectatorAnalysisError(f"{label}: replay record must be an object")
    _require_fields(value, ("schema", "schema_version", "record_type"), label)
    if value["schema"] != SOURCE_SCHEMA or value["schema_version"] != SOURCE_SCHEMA_VERSION:
        raise SpectatorAnalysisError(
            f"{label}: unsupported replay schema {value['schema']!r} "
            f"version {value['schema_version']!r}; exactly {SOURCE_SCHEMA} "
            f"Schema {SOURCE_SCHEMA_VERSION} is required"
        )

    record_type = value["record_type"]
    if record_type == "header":
        _require_fields(value, ("config",), label)
        config = value["config"]
        if not isinstance(config, Mapping):
            raise SpectatorAnalysisError(f"{label}.config must be an object")
        _require_fields(config, ("arena_size",), f"{label}.config")
        size = _require_integer(config["arena_size"], f"{label}.config.arena_size")
        if size <= 0:
            raise SpectatorAnalysisError(f"{label}.config.arena_size must be positive")
        return size

    if arena_size is None:
        raise SpectatorAnalysisError(f"{label}: header must be the first record")

    if record_type == "tick":
        _require_fields(
            value,
            ("tick", "agents", "score", "memory_diffs", "events", "processes"),
            label,
        )
        _require_integer(value["tick"], f"{label}.tick")
        for field in ("agents", "memory_diffs", "events", "processes"):
            _require_array(value, field, label)
        if not isinstance(value["score"], Mapping):
            raise SpectatorAnalysisError(f"{label}.score must be an object")
        for index, process in enumerate(value["processes"]):
            _validate_process(process, f"{label}.processes[{index}]", arena_size)
        for index, diff in enumerate(value["memory_diffs"]):
            diff_label = f"{label}.memory_diffs[{index}]"
            if not isinstance(diff, Mapping):
                raise SpectatorAnalysisError(f"{diff_label} must be an object")
            _require_fields(diff, ("address", "length", "owner", "values"), diff_label)
            address = _require_integer(diff["address"], f"{diff_label}.address")
            length = _require_integer(diff["length"], f"{diff_label}.length")
            if not 0 <= address < arena_size:
                raise SpectatorAnalysisError(
                    f"{diff_label}.address must be within the {arena_size}-cell arena"
                )
            if length <= 0:
                raise SpectatorAnalysisError(f"{diff_label}.length must be positive")
            owner = diff["owner"]
            if owner is not None and (not isinstance(owner, str) or not owner):
                raise SpectatorAnalysisError(
                    f"{diff_label}.owner must be a non-empty string or null"
                )
            values = diff["values"]
            if not isinstance(values, list):
                raise SpectatorAnalysisError(f"{diff_label}.values must be an array")
            if len(values) != length:
                raise SpectatorAnalysisError(
                    f"{diff_label}.values length must equal memory diff length"
                )
            for value_index, byte in enumerate(values):
                byte = _require_integer(byte, f"{diff_label}.values[{value_index}]")
                if not 0 <= byte <= 255:
                    raise SpectatorAnalysisError(
                        f"{diff_label}.values[{value_index}] must be a byte"
                    )
        return arena_size

    if record_type == "result":
        _require_fields(
            value,
            ("winner", "win_mode", "ticks", "score", "agents", "processes"),
            label,
        )
        _require_integer(value["ticks"], f"{label}.ticks")
        for field in ("agents", "processes"):
            _require_array(value, field, label)
        if not isinstance(value["score"], Mapping):
            raise SpectatorAnalysisError(f"{label}.score must be an object")
        for index, process in enumerate(value["processes"]):
            _validate_process(process, f"{label}.processes[{index}]", arena_size)
        return arena_size

    raise SpectatorAnalysisError(f"{label}: unsupported record_type {record_type!r}")


def _load_schema4_replay(path: str | Path) -> _LoadedReplay:
    replay_path = Path(path)
    try:
        raw_bytes = replay_path.read_bytes()
    except OSError as exc:
        raise SpectatorAnalysisError(f"cannot read replay {replay_path}: {exc}") from exc

    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SpectatorAnalysisError(f"{replay_path}: replay is not UTF-8: {exc}") from exc

    parsed: list[ReplayHeader | TickSnapshot | MatchResult] = []
    arena_size: int | None = None
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            raise SpectatorAnalysisError(f"{replay_path}:{line_number}: blank record")
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SpectatorAnalysisError(
                f"{replay_path}:{line_number}: invalid replay JSON: {exc.msg}"
            ) from exc
        try:
            arena_size = _validate_record_shape(value, line_number, arena_size)
            parsed.append(deserialize_record(value))
        except (ReplayFormatError, SpectatorAnalysisError) as exc:
            raise SpectatorAnalysisError(f"{replay_path}:{line_number}: {exc}") from exc

    if not parsed:
        raise SpectatorAnalysisError(f"{replay_path}: replay is empty")
    if not isinstance(parsed[0], ReplayHeader):
        raise SpectatorAnalysisError(f"{replay_path}: header must be the first record")
    if sum(isinstance(record, ReplayHeader) for record in parsed) != 1:
        raise SpectatorAnalysisError(f"{replay_path}: replay must contain exactly one header")
    if not isinstance(parsed[-1], MatchResult):
        raise SpectatorAnalysisError(f"{replay_path}: result must be the final record")
    if sum(isinstance(record, MatchResult) for record in parsed) != 1:
        raise SpectatorAnalysisError(f"{replay_path}: replay must contain exactly one result")

    ticks = tuple(record for record in parsed if isinstance(record, TickSnapshot))
    if not ticks:
        raise SpectatorAnalysisError(f"{replay_path}: replay contains no tick records")
    if ticks[0].tick != 0:
        raise SpectatorAnalysisError(f"{replay_path}: first tick must be tick 0")
    expected_ticks = tuple(range(ticks[-1].tick + 1))
    actual_ticks = tuple(tick.tick for tick in ticks)
    if actual_ticks != expected_ticks:
        raise SpectatorAnalysisError(
            f"{replay_path}: tick records must be contiguous and strictly ordered from tick 0"
        )

    header = parsed[0]
    result = parsed[-1]
    assert isinstance(header, ReplayHeader)
    assert isinstance(result, MatchResult)
    return _LoadedReplay(
        source_path=replay_path,
        source_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        header=header,
        ticks=ticks,
        result=result,
    )


def _living_entrants(tick: TickSnapshot) -> set[str]:
    return {agent.agent_id for agent in tick.agents if agent.alive}


def _visible_pairs(tick: TickSnapshot, arena_size: int) -> set[tuple[str, str]]:
    living = _living_entrants(tick)
    sensors: dict[str, list[tuple[int, int]]] = {}
    targets: dict[str, list[int]] = {}
    for process in tick.processes:
        if process.entrant_id not in living:
            continue
        targets.setdefault(process.entrant_id, []).append(process.anchor)
        if not process.disrupted:
            sensors.setdefault(process.entrant_id, []).append((process.anchor, process.reach))

    visible: set[tuple[str, str]] = set()
    for viewer in sorted(living):
        for target in sorted(living):
            if viewer == target:
                continue
            if any(
                circular_distance(sensor_anchor, target_anchor, arena_size) <= reach
                for sensor_anchor, reach in sensors.get(viewer, ())
                for target_anchor in targets.get(target, ())
            ):
                visible.add((viewer, target))
    return visible


def _expanded_addresses(address: int, length: int, arena_size: int) -> tuple[int, ...]:
    return tuple((address + offset) % arena_size for offset in range(length))


def _semantic_engine_event(tick: int, event: object) -> SemanticEvent | None:
    if isinstance(event, KillDeathEvent):
        return SemanticEvent(
            tick=tick,
            kind=SemanticEventKind.AGENT_ELIMINATED,
            entrant_id=event.victim,
            killer_entrant_id=event.killer,
            cause=event.event_type,
        )
    if isinstance(event, RuntimeEvent):
        return SemanticEvent(
            tick=tick,
            kind=SemanticEventKind.AGENT_FORFEITED,
            entrant_id=event.victim,
            cause=event.event_type,
            reason=event.reason,
            stage=event.stage,
            action_slot=event.action_slot,
        )
    if isinstance(event, AgentEvent):
        return None
    raise SpectatorAnalysisError(f"tick {tick}: unsupported canonical event {type(event).__name__}")


def analyze_replay(path: str | Path) -> SpectatorAnalysis:
    loaded = _load_schema4_replay(path)
    arena_size = loaded.header.config.arena_size
    owner_map: list[str | None] = [None] * arena_size
    previous_visible: set[tuple[str, str]] = set()
    events: list[SemanticEvent] = []

    for tick in loaded.ticks:
        tick_events: list[SemanticEvent] = []
        anchor_writers: dict[int, list[tuple[int, str]]] = {}

        # Canonical memory-diff order is execution order. Range expansion is
        # address order, including wraparound.
        for diff_index, diff in enumerate(tick.memory_diffs):
            for address in _expanded_addresses(diff.address, diff.length, arena_size):
                previous_owner = owner_map[address]
                if (
                    diff.owner is not None
                    and previous_owner is not None
                    and previous_owner != diff.owner
                ):
                    tick_events.append(
                        SemanticEvent(
                            tick=tick.tick,
                            kind=SemanticEventKind.FOREIGN_OWNERSHIP_OVERWRITE,
                            attacker_entrant_id=diff.owner,
                            target_entrant_id=previous_owner,
                            address=address,
                            previous_owner=previous_owner,
                            new_owner=diff.owner,
                        )
                    )
                owner_map[address] = diff.owner
                if diff.owner is not None:
                    anchor_writers.setdefault(address, []).append((diff_index, diff.owner))

        disruptions: list[tuple[int, SemanticEvent]] = []
        for process in tick.processes:
            if not process.disrupted:
                continue
            opposing_writes = [
                (order, writer)
                for order, writer in anchor_writers.get(process.anchor, ())
                if writer != process.entrant_id
            ]
            if not opposing_writes:
                raise SpectatorAnalysisError(
                    f"tick {tick.tick}: disrupted process "
                    f"{process.entrant_id}/{process.process_id} has no replay-visible "
                    "opponent write at its anchor"
                )
            candidates = tuple(sorted({writer for _, writer in opposing_writes}))
            attacker = candidates[0] if len(candidates) == 1 else None
            disruptions.append(
                (
                    min(order for order, _ in opposing_writes),
                    SemanticEvent(
                        tick=tick.tick,
                        kind=SemanticEventKind.CORE_DISRUPTION,
                        attacker_entrant_id=attacker,
                        target_entrant_id=process.entrant_id,
                        target_process_id=process.process_id,
                        address=process.anchor,
                        attribution="exact" if attacker is not None else "ambiguous",
                        candidate_attacker_entrant_ids=candidates,
                    ),
                )
            )
        tick_events.extend(
            event
            for _, event in sorted(
                disruptions,
                key=lambda item: (
                    item[0],
                    item[1].target_entrant_id or "",
                    item[1].target_process_id or "",
                ),
            )
        )

        current_visible = _visible_pairs(tick, arena_size)
        lost = sorted(previous_visible - current_visible)
        gained = sorted(current_visible - previous_visible)
        transitions = [
            SemanticEvent(
                tick=tick.tick,
                kind=SemanticEventKind.DETECTION_LOST,
                viewer_entrant_id=viewer,
                target_entrant_id=target,
            )
            for viewer, target in lost
        ]
        transitions.extend(
            SemanticEvent(
                tick=tick.tick,
                kind=SemanticEventKind.DETECTION_GAINED,
                viewer_entrant_id=viewer,
                target_entrant_id=target,
            )
            for viewer, target in gained
        )
        transitions.sort(
            key=lambda event: (
                event.viewer_entrant_id or "",
                event.target_entrant_id or "",
                0 if event.kind is SemanticEventKind.DETECTION_LOST else 1,
            )
        )
        tick_events.extend(transitions)
        previous_visible = current_visible

        for engine_event in tick.events:
            semantic_event = _semantic_engine_event(tick.tick, engine_event)
            if semantic_event is not None:
                tick_events.append(semantic_event)
        events.extend(tick_events)

    if loaded.result.winner is not None:
        events.append(
            SemanticEvent(
                tick=loaded.result.ticks,
                kind=SemanticEventKind.VICTORY,
                entrant_id=loaded.result.winner,
                cause=loaded.result.win_mode,
            )
        )

    return SpectatorAnalysis(
        source_path=str(loaded.source_path),
        source_sha256=loaded.source_sha256,
        replay_id=loaded.header.replay_id,
        match_id=loaded.header.match_id,
        ruleset_id=loaded.header.ruleset_id,
        first_tick=loaded.ticks[0].tick,
        last_tick=loaded.ticks[-1].tick,
        result_ticks=loaded.result.ticks,
        events=tuple(events),
    )


def semantic_event_to_dict(event: SemanticEvent) -> dict[str, Any]:
    payload: dict[str, Any] = {"kind": event.kind.value, "tick": event.tick}
    fields = (
        "entrant_id",
        "attacker_entrant_id",
        "target_entrant_id",
        "target_process_id",
        "viewer_entrant_id",
        "address",
        "previous_owner",
        "new_owner",
        "killer_entrant_id",
        "cause",
        "reason",
        "stage",
        "action_slot",
        "attribution",
    )
    for field in fields:
        value = getattr(event, field)
        if value is not None:
            payload[field] = value
    if event.candidate_attacker_entrant_ids:
        payload["candidate_attacker_entrant_ids"] = list(event.candidate_attacker_entrant_ids)
    return payload


def analysis_records(analysis: SpectatorAnalysis) -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = [
        {
            "schema": SEMANTIC_SCHEMA,
            "schema_version": SEMANTIC_SCHEMA_VERSION,
            "record_type": "header",
            "source": {
                "match_id": analysis.match_id,
                "replay_id": analysis.replay_id,
                "replay_sha256": analysis.source_sha256,
                "ruleset_id": analysis.ruleset_id,
            },
        }
    ]
    events_by_tick: dict[int, list[dict[str, Any]]] = {}
    for event in analysis.events:
        events_by_tick.setdefault(event.tick, []).append(semantic_event_to_dict(event))
    for tick in sorted(events_by_tick):
        records.append(
            {
                "schema": SEMANTIC_SCHEMA,
                "schema_version": SEMANTIC_SCHEMA_VERSION,
                "record_type": "tick",
                "tick": tick,
                "events": events_by_tick[tick],
            }
        )
    records.append(
        {
            "schema": SEMANTIC_SCHEMA,
            "schema_version": SEMANTIC_SCHEMA_VERSION,
            "record_type": "result",
            "first_tick": analysis.first_tick,
            "last_tick": analysis.last_tick,
            "result_ticks": analysis.result_ticks,
            "event_count": len(analysis.events),
        }
    )
    return tuple(records)


def serialize_analysis(analysis: SpectatorAnalysis) -> str:
    return "".join(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        for record in analysis_records(analysis)
    )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        print("usage: spectator_analyzer.py REPLAY.jsonl", file=sys.stderr)
        return 2
    try:
        analysis = analyze_replay(arguments[0])
    except SpectatorAnalysisError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(serialize_analysis(analysis))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
