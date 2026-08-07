from __future__ import annotations

import json

import pytest
from battle_client.session import ReplaySession, ReplaySessionError, ReplayState
from battle_engine.builtins import build_agent
from battle_engine.config import Config
from battle_engine.core import HALT, NOP, enc
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.replay import (
    AgentState,
    KillDeathEvent,
    MatchConfiguration,
    MatchResult,
    MemoryDiff,
    ReplayFormatError,
    ReplayHeader,
    TickSnapshot,
    write_replay,
)


# ---------------------------------------------------------------------------
# Real v3 replays via NativeMatchService
# ---------------------------------------------------------------------------
def _config(arena_size=32, instr_per_tick=1, seed=1337):
    return Config(arena_size=arena_size, instr_per_tick=instr_per_tick, seed=seed)


def _run_vm_match(tmp_path):
    entrants = (
        MatchEntrant("A", "a", 0, build_agent("runner", 0)),
        MatchEntrant("B", "b", 16, build_agent("runner", 16)),
    )
    replay_path = tmp_path / "replay.jsonl"
    result = NativeMatchService().run(
        MatchRequest(_config(), entrants, max_ticks=3, replay_path=replay_path, verbose=False)
    )
    return result


def test_load_real_vm_replay_exposes_header_and_runtime_kind(tmp_path):
    result = _run_vm_match(tmp_path)
    session = ReplaySession()
    session.load(result.replay_path)

    assert session.loaded
    assert session.header is not None
    assert session.header.match_id == result.match_id
    assert session.runtime_kind == "vm"


def test_load_real_vm_replay_terminal_metadata_matches_result_json(tmp_path):
    from battle_engine.result_model import read_result

    result = _run_vm_match(tmp_path)
    session = ReplaySession()
    session.load(result.replay_path)

    envelope = read_result(result.result_path)
    assert session.termination_reason == envelope.termination_reason
    assert (session.winner or "tie") == envelope.winner

    while not session.at_end:
        final_state = session.step_forward()
    assert dict(final_state.score) == dict(envelope.score)


def test_events_at_tick_returns_the_recorded_death(tmp_path):
    entrants = (
        MatchEntrant("A", "halts", 0, enc(HALT)),
        MatchEntrant("B", "waits", 16, enc(NOP)),
    )
    result = NativeMatchService().run(
        MatchRequest(_config(arena_size=32), entrants, 2, tmp_path / "events.jsonl", False)
    )
    session = ReplaySession()
    session.load(result.replay_path)

    assert session.events_at_tick(1) == (KillDeathEvent("death", "A", None),)


# ---------------------------------------------------------------------------
# Hand-built replays: precise control over diffs for step/restart assertions
# ---------------------------------------------------------------------------
def _agent(agent_id, pc=0, alive=True):
    return AgentState(agent_id=agent_id, pc=pc, alive=alive)


def _write(path, records):
    write_replay(path, records)


def _small_replay_records():
    header = ReplayHeader(
        MatchConfiguration(arena_size=8),
        {"A": "a", "B": "b"},
        runtime_kind="vm",
    )
    tick0 = TickSnapshot(
        0,
        agents=(_agent("A", pc=0), _agent("B", pc=4)),
        score={"A": 0, "B": 0},
        memory_diffs=(MemoryDiff(address=0, length=1, owner="A", values=(0x10,)),),
    )
    tick1 = TickSnapshot(
        1,
        agents=(_agent("A", pc=1), _agent("B", pc=4)),
        score={"A": 1, "B": 0},
        memory_diffs=(MemoryDiff(address=1, length=1, owner="A", values=(0x20,)),),
    )
    tick2 = TickSnapshot(
        2,
        agents=(_agent("A", pc=2), _agent("B", pc=4, alive=False)),
        score={"A": 2, "B": 0},
        memory_diffs=(MemoryDiff(address=2, length=1, owner="A", values=(0x30,)),),
        events=(KillDeathEvent("death", "B", "A"),),
    )
    result = MatchResult(
        winner="A",
        win_mode="score",
        ticks=2,
        score={"A": 2, "B": 0},
        agents=(_agent("A", pc=2), _agent("B", pc=4, alive=False)),
        termination_reason="last_agent_standing",
    )
    return header, tick0, tick1, tick2, result


def test_initial_state_after_load_is_tick_zero_with_first_diff_applied(tmp_path):
    replay_path = tmp_path / "replay.jsonl"
    header, tick0, tick1, tick2, result = _small_replay_records()
    _write(replay_path, [header, tick0, tick1, tick2, result])

    session = ReplaySession()
    session.load(replay_path)

    state = session.current_state
    assert isinstance(state, ReplayState)
    assert state.tick == 0
    assert state.arena[0] == 0x10
    assert state.arena[1] == 0
    assert state.owners[0] == "A"
    assert state.agents["A"].pc == 0
    assert state.score == {"A": 0, "B": 0}
    assert not session.at_end


def test_step_forward_applies_only_the_next_ticks_diff(tmp_path):
    replay_path = tmp_path / "replay.jsonl"
    header, tick0, tick1, tick2, result = _small_replay_records()
    _write(replay_path, [header, tick0, tick1, tick2, result])

    session = ReplaySession()
    session.load(replay_path)

    state = session.step_forward()
    assert state.tick == 1
    # Tick 0's write is still present; tick 1 only added address 1.
    assert state.arena[0] == 0x10
    assert state.arena[1] == 0x20
    assert state.agents["A"].pc == 1
    assert state.score == {"A": 1, "B": 0}


def test_repeated_step_forward_reaches_final_tick_and_sets_at_end(tmp_path):
    replay_path = tmp_path / "replay.jsonl"
    header, tick0, tick1, tick2, result = _small_replay_records()
    _write(replay_path, [header, tick0, tick1, tick2, result])

    session = ReplaySession()
    session.load(replay_path)
    assert not session.at_end

    session.step_forward()
    assert not session.at_end
    state = session.step_forward()
    assert session.at_end
    assert state.tick == 2
    assert state.arena[2] == 0x30
    assert state.agents["B"].alive is False


def test_step_forward_past_the_final_tick_raises(tmp_path):
    replay_path = tmp_path / "replay.jsonl"
    header, tick0, tick1, tick2, result = _small_replay_records()
    _write(replay_path, [header, tick0, tick1, tick2, result])

    session = ReplaySession()
    session.load(replay_path)
    session.step_forward()
    session.step_forward()
    assert session.at_end

    with pytest.raises(ReplaySessionError, match="final tick"):
        session.step_forward()


def test_restart_returns_to_the_initial_state_after_stepping(tmp_path):
    replay_path = tmp_path / "replay.jsonl"
    header, tick0, tick1, tick2, result = _small_replay_records()
    _write(replay_path, [header, tick0, tick1, tick2, result])

    session = ReplaySession()
    session.load(replay_path)
    session.step_forward()
    session.step_forward()
    assert session.at_end

    state = session.restart()
    assert state.tick == 0
    assert state.arena[1] == 0
    assert state.arena[2] == 0
    assert not session.at_end


def test_winner_and_termination_reason_come_from_the_terminal_result(tmp_path):
    replay_path = tmp_path / "replay.jsonl"
    header, tick0, tick1, tick2, result = _small_replay_records()
    _write(replay_path, [header, tick0, tick1, tick2, result])

    session = ReplaySession()
    session.load(replay_path)

    assert session.winner == "A"
    assert session.termination_reason == "last_agent_standing"


def test_events_at_tick_on_hand_built_replay(tmp_path):
    replay_path = tmp_path / "replay.jsonl"
    header, tick0, tick1, tick2, result = _small_replay_records()
    _write(replay_path, [header, tick0, tick1, tick2, result])

    session = ReplaySession()
    session.load(replay_path)

    assert session.events_at_tick(2) == (KillDeathEvent("death", "B", "A"),)
    assert session.events_at_tick(0) == ()

    with pytest.raises(ReplaySessionError, match="no tick 99"):
        session.events_at_tick(99)


# ---------------------------------------------------------------------------
# Legacy version loading
# ---------------------------------------------------------------------------
def test_load_legacy_v01_replay(tmp_path):
    replay_path = tmp_path / "replay.jsonl"
    replay_path.write_text(
        "\n".join(
            [
                json.dumps({"tick": 0, "ver": 6, "config": {"arena_size": 16}}),
                json.dumps(
                    {
                        "tick": 1,
                        "agents": [{"id": "A", "pc": 2, "alive": True}],
                        "score": {"A": 1},
                        "events": [],
                        "memory_diffs": [{"addr": 3, "len": 1, "owner": "A"}],
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    session = ReplaySession()
    session.load(replay_path)

    assert session.header is not None
    assert session.header.config.arena_size == 16
    # The file's only tick record (tick 1) becomes the session's initial
    # position, since this legacy fixture has no tick-0 record.
    assert session.at_end
    state = session.current_state
    assert state.tick == 1
    assert state.agents["A"].pc == 2
    # Legacy records never captured written byte values, but ownership is
    # still reconstructable from owner/address/length alone.
    assert state.owners[3] == "A"
    assert state.arena[3] == 0


def test_load_legacy_v02_replay(tmp_path):
    replay_path = tmp_path / "replay.jsonl"
    replay_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "schema": "battle2.replay",
                        "schema_version": 2,
                        "record_type": "header",
                        "config": {"arena_size": 16},
                    }
                ),
                json.dumps(
                    {
                        "schema": "battle2.replay",
                        "schema_version": 2,
                        "record_type": "tick",
                        "tick": 1,
                        "agents": [],
                        "score": {"A": 1},
                        "events": [],
                        "memory_diffs": [],
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    session = ReplaySession()
    session.load(replay_path)

    assert session.header.schema_version == 2
    assert session.at_end
    state = session.current_state
    assert state.tick == 1
    assert state.score == {"A": 1}


# ---------------------------------------------------------------------------
# Malformed / truncated / structurally incomplete replays
# ---------------------------------------------------------------------------
def test_malformed_json_line_raises_replay_format_error(tmp_path):
    replay_path = tmp_path / "replay.jsonl"
    header, tick0, _tick1, _tick2, _result = _small_replay_records()
    _write(replay_path, [header, tick0])
    with replay_path.open("a", encoding="utf-8") as stream:
        stream.write("{not valid json\n")

    session = ReplaySession()
    with pytest.raises(ReplayFormatError):
        session.load(replay_path)


def test_failed_load_does_not_corrupt_a_previously_loaded_session(tmp_path):
    good_path = tmp_path / "good.jsonl"
    header, tick0, tick1, tick2, result = _small_replay_records()
    _write(good_path, [header, tick0, tick1, tick2, result])

    bad_path = tmp_path / "bad.jsonl"
    _write(bad_path, [header, tick0])
    with bad_path.open("a", encoding="utf-8") as stream:
        stream.write("{not valid json\n")

    session = ReplaySession()
    session.load(good_path)
    session.step_forward()
    state_before = session.current_state

    with pytest.raises(ReplayFormatError):
        session.load(bad_path)

    assert session.current_state == state_before


def test_missing_header_raises_replay_session_error(tmp_path):
    replay_path = tmp_path / "replay.jsonl"
    _write(replay_path, [TickSnapshot(0), TickSnapshot(1)])

    session = ReplaySession()
    with pytest.raises(ReplaySessionError, match="no header"):
        session.load(replay_path)


def test_missing_result_record_leaves_winner_and_termination_reason_none(tmp_path):
    replay_path = tmp_path / "replay.jsonl"
    header, tick0, tick1, tick2, _result = _small_replay_records()
    _write(replay_path, [header, tick0, tick1, tick2])

    session = ReplaySession()
    session.load(replay_path)

    assert session.result is None
    assert session.winner is None
    assert session.termination_reason is None
    # Ticks themselves are unaffected by the missing terminal record.
    assert session.step_forward().tick == 1


def test_empty_replay_header_only_is_defined_and_at_end(tmp_path):
    replay_path = tmp_path / "replay.jsonl"
    header, *_rest = _small_replay_records()
    _write(replay_path, [header])

    session = ReplaySession()
    session.load(replay_path)

    assert session.at_end
    state = session.current_state
    assert state.tick == 0
    assert state.arena == bytes(8)
    assert all(owner is None for owner in state.owners)

    with pytest.raises(ReplaySessionError, match="final tick"):
        session.step_forward()

    # restart() on an empty replay is a defined no-op, not an error.
    assert session.restart() == state


def test_duplicate_tick_number_events_at_tick_returns_the_last_occurrence(tmp_path):
    replay_path = tmp_path / "replay.jsonl"
    header = ReplayHeader(MatchConfiguration(arena_size=8), runtime_kind="vm")
    first_five = TickSnapshot(5, events=(KillDeathEvent("death", "A", "B"),))
    second_five = TickSnapshot(5, events=(KillDeathEvent("death", "B", "A"),))
    _write(replay_path, [header, first_five, second_five])

    session = ReplaySession()
    session.load(replay_path)

    assert session.events_at_tick(5) == (KillDeathEvent("death", "B", "A"),)
    # Both records are still walked in file order by step_forward.
    first_state = session.current_state
    assert first_state.tick == 5
    second_state = session.step_forward()
    assert second_state.tick == 5
    assert session.at_end
