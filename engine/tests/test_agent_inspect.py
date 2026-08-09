from __future__ import annotations

from pathlib import Path

from battle_engine.agent_inspect import diverge_main, inspect_main
from battle_engine.agent_trace import (
    DecisionRecord,
    ResetRecord,
    TraceAction,
    TraceDiagnostic,
    TraceHeader,
    TraceObservation,
    TraceWriter,
)


def _write_trace(path: Path, *, failing_tick: int | None = None) -> None:
    with TraceWriter(path) as writer:
        writer.write_header(
            TraceHeader(match_seed=1337, agents={"A": "agent_a", "B": "agent_b"}, supervised=True, agent_call_timeout=5.0)
        )
        writer.write_reset(ResetRecord(agent_id="A", wall_time_ms=1.0, diagnostic=None))
        writer.write_reset(ResetRecord(agent_id="B", wall_time_ms=1.0, diagnostic=None))
        for tick in range(1, 6):
            for agent_id in ("A", "B"):
                diagnostic = None
                action: TraceAction | None = TraceAction(kind="nop")
                if failing_tick is not None and tick == failing_tick and agent_id == "A":
                    action = None
                    diagnostic = TraceDiagnostic(
                        code="agent_action_timeout", stage="action",
                        message="Python agent A act() did not return within 1.0s.",
                        agent_id="A", slot=0, tick=tick, action_slot=0,
                    )
                writer.write_decision(
                    DecisionRecord(
                        tick=tick, agent_id=agent_id, action_slot=0, wall_time_ms=0.1,
                        observation=TraceObservation(
                            tick=tick, agent_id=agent_id, pc=0, register_a=0, register_p=0,
                            zero_flag=False, last_read=None, alive=True,
                        ),
                        action=action, diagnostic=diagnostic,
                    )
                )


def test_inspect_summary(tmp_path: Path, capsys) -> None:
    trace_path = tmp_path / "trace.jsonl"
    _write_trace(trace_path)

    exit_code = inspect_main([str(trace_path)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "schema: bytefray.agent_trace v1" in out
    assert "decisions: 10" in out
    assert "failures: 0" in out


def test_inspect_accepts_run_directory(tmp_path: Path, capsys) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_trace(run_dir / "trace.jsonl")

    exit_code = inspect_main([str(run_dir)])

    assert exit_code == 0
    assert "schema: bytefray.agent_trace" in capsys.readouterr().out


def test_inspect_tick_shows_both_agents(tmp_path: Path, capsys) -> None:
    trace_path = tmp_path / "trace.jsonl"
    _write_trace(trace_path)

    exit_code = inspect_main([str(trace_path), "--tick", "3"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert out.count("tick: 3") == 2
    assert "agent: A" in out
    assert "agent: B" in out


def test_inspect_tick_and_agent_filters_to_one_decision(tmp_path: Path, capsys) -> None:
    trace_path = tmp_path / "trace.jsonl"
    _write_trace(trace_path)

    exit_code = inspect_main([str(trace_path), "--tick", "3", "--agent", "A"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert out.count("tick: 3") == 1
    assert "agent: A" in out
    assert "agent: B" not in out


def test_inspect_around_window(tmp_path: Path, capsys) -> None:
    trace_path = tmp_path / "trace.jsonl"
    _write_trace(trace_path)

    exit_code = inspect_main([str(trace_path), "--around", "3", "--window", "1"])

    out = capsys.readouterr().out
    assert exit_code == 0
    for tick in (2, 3, 4):
        assert f"tick: {tick}" in out
    assert "tick: 1" not in out
    assert "tick: 5" not in out


def test_inspect_failures_only(tmp_path: Path, capsys) -> None:
    trace_path = tmp_path / "trace.jsonl"
    _write_trace(trace_path, failing_tick=3)

    exit_code = inspect_main([str(trace_path), "--failures"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "agent_action_timeout" in out
    assert out.count("diagnostic.code:") == 1


def test_inspect_missing_file_exits_2(tmp_path: Path, capsys) -> None:
    exit_code = inspect_main([str(tmp_path / "nope")])

    assert exit_code == 2
    err = capsys.readouterr().err
    assert "code: trace_file_missing" in err


def test_inspect_malformed_trace_exits_2(tmp_path: Path, capsys) -> None:
    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text("not json\n", encoding="utf-8")

    exit_code = inspect_main([str(trace_path)])

    assert exit_code == 2
    err = capsys.readouterr().err
    assert "code: trace_format_invalid" in err


def test_diverge_identical_traces_reports_no_divergence(tmp_path: Path, capsys) -> None:
    trace_a = tmp_path / "a.jsonl"
    trace_b = tmp_path / "b.jsonl"
    _write_trace(trace_a)
    _write_trace(trace_b)

    exit_code = diverge_main([str(trace_a), str(trace_b)])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "status: identical" in out


def test_diverge_differing_traces_reports_first_divergence(tmp_path: Path, capsys) -> None:
    trace_a = tmp_path / "a.jsonl"
    trace_b = tmp_path / "b.jsonl"
    _write_trace(trace_a)
    _write_trace(trace_b, failing_tick=2)

    exit_code = diverge_main([str(trace_a), str(trace_b)])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "status: diverged" in out
    assert "tick: 2" in out
    assert "agent: A" in out


def test_diverge_missing_file_exits_2(tmp_path: Path, capsys) -> None:
    trace_a = tmp_path / "a.jsonl"
    _write_trace(trace_a)

    exit_code = diverge_main([str(trace_a), str(tmp_path / "nope")])

    assert exit_code == 2
    assert "code: trace_file_missing" in capsys.readouterr().err
