from __future__ import annotations

from pathlib import Path

import pytest
from battle_engine.agent_trace import (
    DecisionRecord,
    ResetRecord,
    TraceAction,
    TraceDiagnostic,
    TraceFormatError,
    TraceHeader,
    TraceObservation,
    TraceWriter,
    first_divergence,
    read_trace,
)


def _write_sample(path: Path, *, action_value: int = 165) -> None:
    with TraceWriter(path) as writer:
        writer.write_header(
            TraceHeader(match_seed=1337, agents={"A": "a", "B": "b"}, supervised=True, agent_call_timeout=5.0)
        )
        writer.write_reset(ResetRecord(agent_id="A", wall_time_ms=1.5, diagnostic=None))
        writer.write_decision(
            DecisionRecord(
                tick=1,
                agent_id="A",
                action_slot=0,
                wall_time_ms=0.2,
                observation=TraceObservation(
                    tick=1, agent_id="A", pc=0, register_a=0, register_p=0,
                    zero_flag=False, last_read=None, alive=True,
                ),
                action=TraceAction(kind="write", operand=10, value=action_value),
                diagnostic=None,
            )
        )


def test_round_trip_write_then_read(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    _write_sample(path)

    document = read_trace(path)

    assert document.header.match_seed == 1337
    assert document.header.agents == {"A": "a", "B": "b"}
    assert document.header.supervised is True
    assert document.header.agent_call_timeout == 5.0
    assert len(document.resets) == 1
    assert len(document.decisions) == 1
    decision = document.decisions[0]
    assert decision.tick == 1
    assert decision.agent_id == "A"
    assert decision.action == TraceAction(kind="write", operand=10, value=165)
    assert decision.diagnostic is None


def test_writer_flushes_each_line_immediately(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    writer = TraceWriter(path)
    writer.write_header(TraceHeader(match_seed=1, agents={}, supervised=False))
    # No close() yet -- a reader opening the file now must already see the
    # header, proving each write is flushed rather than buffered until close.
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    writer.close()


def test_decision_with_diagnostic_has_no_action(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    with TraceWriter(path) as writer:
        writer.write_header(TraceHeader(match_seed=1, agents={"A": "a"}, supervised=True, agent_call_timeout=5.0))
        writer.write_decision(
            DecisionRecord(
                tick=3,
                agent_id="A",
                action_slot=0,
                wall_time_ms=5000.0,
                observation=TraceObservation(
                    tick=3, agent_id="A", pc=0, register_a=0, register_p=0,
                    zero_flag=False, last_read=None, alive=True,
                ),
                action=None,
                diagnostic=TraceDiagnostic(
                    code="agent_action_timeout", stage="action",
                    message="Python agent A act() did not return within 5s.",
                    agent_id="A", slot=0, tick=3, action_slot=0,
                ),
            )
        )

    document = read_trace(path)
    decision = document.decisions[0]
    assert decision.action is None
    assert decision.diagnostic is not None
    assert decision.diagnostic.code == "agent_action_timeout"
    assert document.failures() == (decision,)


def test_missing_header_raises_trace_format_error(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    path.write_text('{"record_type": "reset", "agent_id": "A", "wall_time_ms": 1.0}\n', encoding="utf-8")

    with pytest.raises(TraceFormatError, match="missing header"):
        read_trace(path)


def test_malformed_json_line_raises_trace_format_error(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    path.write_text(
        '{"schema": "bytefray.agent_trace", "schema_version": 1, "record_type": "header", '
        '"match_seed": 1, "agents": {}, "supervised": false}\n'
        "{not valid json\n",
        encoding="utf-8",
    )

    with pytest.raises(TraceFormatError, match="invalid JSON"):
        read_trace(path)


def test_unknown_record_type_raises_trace_format_error(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    path.write_text(
        '{"schema": "bytefray.agent_trace", "schema_version": 1, "record_type": "header", '
        '"match_seed": 1, "agents": {}, "supervised": false}\n'
        '{"record_type": "mystery"}\n',
        encoding="utf-8",
    )

    with pytest.raises(TraceFormatError, match="unknown record_type"):
        read_trace(path)


def test_unsupported_schema_version_raises_trace_format_error(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    path.write_text(
        '{"schema": "bytefray.agent_trace", "schema_version": 99, "record_type": "header", '
        '"match_seed": 1, "agents": {}, "supervised": false}\n',
        encoding="utf-8",
    )

    with pytest.raises(TraceFormatError, match="schema version"):
        read_trace(path)


def test_missing_required_field_raises_trace_format_error(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    path.write_text(
        '{"schema": "bytefray.agent_trace", "schema_version": 1, "record_type": "header", '
        '"match_seed": 1, "agents": {}, "supervised": false}\n'
        '{"record_type": "decision", "tick": 1, "agent_id": "A"}\n',
        encoding="utf-8",
    )

    with pytest.raises(TraceFormatError, match="missing required field"):
        read_trace(path)


def test_nonexistent_file_raises_trace_format_error(tmp_path: Path) -> None:
    with pytest.raises(TraceFormatError, match="not found"):
        read_trace(tmp_path / "does_not_exist.jsonl")


def test_tick_range_and_query_helpers(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    with TraceWriter(path) as writer:
        writer.write_header(TraceHeader(match_seed=1, agents={"A": "a", "B": "b"}, supervised=False))
        for tick in (1, 2, 3):
            for agent_id in ("A", "B"):
                writer.write_decision(
                    DecisionRecord(
                        tick=tick, agent_id=agent_id, action_slot=0, wall_time_ms=0.1,
                        observation=TraceObservation(
                            tick=tick, agent_id=agent_id, pc=0, register_a=0, register_p=0,
                            zero_flag=False, last_read=None, alive=True,
                        ),
                        action=TraceAction(kind="nop"),
                        diagnostic=None,
                    )
                )

    document = read_trace(path)
    assert document.tick_range() == (1, 3)
    assert len(document.for_tick(2)) == 2
    assert len(document.for_agent("A")) == 3
    assert len(document.around_tick(2, 1)) == 6  # ticks 1-3, both agents


def test_first_divergence_none_for_identical_traces(tmp_path: Path) -> None:
    path_a = tmp_path / "a.jsonl"
    path_b = tmp_path / "b.jsonl"
    _write_sample(path_a)
    _write_sample(path_b)

    assert first_divergence(read_trace(path_a), read_trace(path_b)) is None


def test_first_divergence_finds_differing_action(tmp_path: Path) -> None:
    path_a = tmp_path / "a.jsonl"
    path_b = tmp_path / "b.jsonl"
    _write_sample(path_a, action_value=165)
    _write_sample(path_b, action_value=200)

    divergence = first_divergence(read_trace(path_a), read_trace(path_b))

    assert divergence is not None
    assert divergence.tick == 1
    assert divergence.agent_id == "A"
    assert divergence.reason == "action/diagnostic differ"
    assert divergence.record_a is not None and divergence.record_a.action is not None
    assert divergence.record_a.action.value == 165
    assert divergence.record_b is not None and divergence.record_b.action is not None
    assert divergence.record_b.action.value == 200


def test_first_divergence_reports_length_mismatch(tmp_path: Path) -> None:
    path_a = tmp_path / "a.jsonl"
    path_b = tmp_path / "b.jsonl"
    with TraceWriter(path_a) as writer:
        writer.write_header(TraceHeader(match_seed=1, agents={"A": "a"}, supervised=False))
        for tick in (1, 2):
            writer.write_decision(
                DecisionRecord(
                    tick=tick, agent_id="A", action_slot=0, wall_time_ms=0.1,
                    observation=TraceObservation(
                        tick=tick, agent_id="A", pc=0, register_a=0, register_p=0,
                        zero_flag=False, last_read=None, alive=True,
                    ),
                    action=TraceAction(kind="nop"), diagnostic=None,
                )
            )
    with TraceWriter(path_b) as writer:
        writer.write_header(TraceHeader(match_seed=1, agents={"A": "a"}, supervised=False))
        writer.write_decision(
            DecisionRecord(
                tick=1, agent_id="A", action_slot=0, wall_time_ms=0.1,
                observation=TraceObservation(
                    tick=1, agent_id="A", pc=0, register_a=0, register_p=0,
                    zero_flag=False, last_read=None, alive=True,
                ),
                action=TraceAction(kind="nop"), diagnostic=None,
            )
        )

    divergence = first_divergence(read_trace(path_a), read_trace(path_b))

    assert divergence is not None
    assert divergence.tick == 2
    assert divergence.reason == "one trace is missing this decision"
    assert divergence.record_a is not None
    assert divergence.record_b is None
