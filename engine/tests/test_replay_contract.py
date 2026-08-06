from __future__ import annotations

import json
from pathlib import Path

import pytest

from battle_engine.replay import (
    AgentEvent,
    AgentState,
    KillDeathEvent,
    MatchConfiguration,
    MatchResult,
    MemoryDiff,
    ReplayFormatError,
    ReplayHeader,
    TickSnapshot,
    deserialize_record,
    serialize_record,
)


FIXTURES = Path(__file__).parent / "fixtures" / "replay"


@pytest.mark.parametrize(
    ("filename", "expected_type"),
    [
        ("v01_header.json", ReplayHeader),
        ("v01_snapshot.json", TickSnapshot),
        ("legacy_event.json", TickSnapshot),
        ("v02_header.json", ReplayHeader),
        ("v02_tick.json", TickSnapshot),
    ],
)
def test_supported_fixture_records_are_readable(filename, expected_type):
    record = deserialize_record((FIXTURES / filename).read_text(encoding="utf-8"))
    assert isinstance(record, expected_type)
    assert record.schema == "battle2.replay"
    assert record.schema_version == 2


def test_v01_snapshot_is_normalized_to_typed_values():
    record = deserialize_record((FIXTURES / "v01_snapshot.json").read_text())
    assert isinstance(record, TickSnapshot)
    assert record.agents[0] == AgentState("A", 5, True, 2, 1, (0, 9))
    assert record.memory_diffs == (MemoryDiff(48, 2, "A"),)
    assert record.events == (KillDeathEvent("kill", "B", "A"),)


def test_legacy_spatial_event_is_normalized():
    record = deserialize_record((FIXTURES / "legacy_event.json").read_text())
    assert isinstance(record, TickSnapshot)
    assert record.events == (AgentEvent("move", "A", (2, 2), (1, 2)),)


@pytest.mark.parametrize(
    "record",
    [
        ReplayHeader(MatchConfiguration(128, 4, 42), {"A": "writer"}),
        TickSnapshot(
            7,
            agents=(AgentState("A", 12, region=(0, 20)),),
            score={"A": 9},
            memory_diffs=(MemoryDiff(30, 3, "A"),),
            events=(KillDeathEvent("kill", "B", "A"),),
        ),
        MatchResult("A", "score_fallback", 7, {"A": 9, "B": 2}),
    ],
)
def test_v02_records_round_trip(record):
    assert deserialize_record(serialize_record(record)) == record


@pytest.mark.parametrize(
    ("record", "message"),
    [
        (
            {"schema": "battle2.replay", "schema_version": 99, "record_type": "tick"},
            "unsupported battle2.replay schema version 99",
        ),
        (
            {"schema": "somebody.else", "schema_version": 2, "record_type": "tick"},
            "unsupported replay schema",
        ),
        (
            {"schema": "battle2.replay", "schema_version": 2, "record_type": "mystery"},
            "unsupported record_type",
        ),
    ],
)
def test_invalid_or_unsupported_schema_has_useful_error(record, message):
    with pytest.raises(ReplayFormatError, match=message):
        deserialize_record(record)
