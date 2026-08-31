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
    ProcessState,
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


def test_memory_diffs_at_tick_returns_the_raw_per_write_records(tmp_path):
    """Mirrors ``test_events_at_tick_returns_the_recorded_death`` for the
    sibling raw-lookup method (Beta1 Phase 3) -- a non-mutating lookup of
    one tick's own ``MemoryDiff`` records, independent of the playback
    cursor and distinct from ``current_state.owners`` (which reflects only
    the *final* merged ownership across every tick up to the cursor).
    """
    entrants = (
        MatchEntrant("A", "runner", 0, build_agent("runner", 0)),
        MatchEntrant("B", "writer", 16, build_agent("writer", 16)),
    )
    result = NativeMatchService().run(
        MatchRequest(_config(arena_size=32), entrants, 3, tmp_path / "diffs.jsonl", False)
    )
    session = ReplaySession()
    session.load(result.replay_path)

    tick0_diffs = session.memory_diffs_at_tick(0)
    assert tick0_diffs
    assert {diff.owner for diff in tick0_diffs} == {"A", "B"}

    with pytest.raises(ReplaySessionError):
        session.memory_diffs_at_tick(999)


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


def test_schema4_process_anchors_are_seekable_and_reconstructed(tmp_path):
    replay_path = tmp_path / "processes.jsonl"
    header = ReplayHeader(
        MatchConfiguration(arena_size=32),
        {"A": "process-agent"},
        runtime_kind="python",
        ruleset_id="bytefray-rules-4-alpha1",
        schema_version=4,
    )
    tick0 = TickSnapshot(
        0,
        agents=(_agent("A"),),
        processes=(ProcessState("scout", "A", 4, False, 8),),
        schema_version=4,
    )
    tick1 = TickSnapshot(
        1,
        agents=(_agent("A"),),
        processes=(ProcessState("scout", "A", 12, True, 8),),
        schema_version=4,
    )
    _write(replay_path, [header, tick0, tick1])

    session = ReplaySession()
    session.load(replay_path)
    assert session.current_state.processes[("A", "scout")].anchor == 4

    state = session.step_forward()
    assert state.processes[("A", "scout")] == ProcessState(
        "scout", "A", 12, True, 8
    )
    assert session.restart().processes[("A", "scout")].anchor == 4


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


def test_duplicate_tick_number_is_rejected_on_load(tmp_path):
    # Slice 1 tolerated duplicate ticks (last occurrence wins). Slice 2
    # introduces seek(tick), which requires each tick number to identify
    # exactly one deterministic state, so this is now rejected as a
    # corrupt/hand-edited replay instead.
    replay_path = tmp_path / "replay.jsonl"
    header = ReplayHeader(MatchConfiguration(arena_size=8), runtime_kind="vm")
    first_five = TickSnapshot(5, events=(KillDeathEvent("death", "A", "B"),))
    second_five = TickSnapshot(5, events=(KillDeathEvent("death", "B", "A"),))
    _write(replay_path, [header, first_five, second_five])

    session = ReplaySession()
    with pytest.raises(ReplaySessionError, match="not strictly greater"):
        session.load(replay_path)


def test_out_of_order_tick_is_rejected_on_load(tmp_path):
    replay_path = tmp_path / "replay.jsonl"
    header = ReplayHeader(MatchConfiguration(arena_size=8), runtime_kind="vm")
    tick_five = TickSnapshot(5)
    tick_three = TickSnapshot(3)
    _write(replay_path, [header, tick_five, tick_three])

    session = ReplaySession()
    with pytest.raises(ReplaySessionError, match="not strictly greater"):
        session.load(replay_path)


# ---------------------------------------------------------------------------
# seek(): a five-tick hand-built replay with a distinct, checkable diff and
# score at every tick, for precise forward/backward/range assertions.
# ---------------------------------------------------------------------------
def _five_tick_replay_records():
    header = ReplayHeader(MatchConfiguration(arena_size=8), {"A": "a"}, runtime_kind="vm")
    ticks = tuple(
        TickSnapshot(
            t,
            agents=(_agent("A", pc=t),),
            score={"A": t},
            memory_diffs=(MemoryDiff(address=t, length=1, owner="A", values=(0x10 + t,)),),
        )
        for t in range(5)
    )
    result = MatchResult(
        winner="A",
        win_mode="score",
        ticks=4,
        score={"A": 4},
        agents=(_agent("A", pc=4),),
        termination_reason="tick_limit",
    )
    return (header, *ticks, result)


def _load_five_tick_session(tmp_path, name="replay.jsonl"):
    replay_path = tmp_path / name
    _write(replay_path, list(_five_tick_replay_records()))
    session = ReplaySession()
    session.load(replay_path)
    return session, replay_path


def test_seek_forward_applies_only_intervening_ticks(tmp_path):
    session, _ = _load_five_tick_session(tmp_path)
    state = session.seek(3)
    assert state.tick == 3
    assert state.arena[:4] == bytes([0x10, 0x11, 0x12, 0x13])
    assert state.arena[4] == 0
    assert state.agents["A"].pc == 3
    assert state.score == {"A": 3}


def test_seek_backward_resets_and_replays_forward(tmp_path):
    session, _ = _load_five_tick_session(tmp_path)
    session.seek(4)
    state = session.seek(1)
    assert state.tick == 1
    assert state.arena[0] == 0x10
    assert state.arena[1] == 0x11
    assert state.arena[2] == 0  # tick 2's write hasn't happened at tick 1
    assert state.agents["A"].pc == 1


def test_seek_to_current_tick_is_a_no_op(tmp_path):
    session, _ = _load_five_tick_session(tmp_path)
    session.seek(2)
    before = session.current_state
    after = session.seek(2)
    assert after == before


def test_seek_to_tick_zero(tmp_path):
    session, _ = _load_five_tick_session(tmp_path)
    session.seek(4)
    state = session.seek(0)
    assert state.tick == 0
    assert state.arena[0] == 0x10
    assert all(byte == 0 for byte in state.arena[1:])


def test_seek_to_final_tick_sets_at_end(tmp_path):
    session, _ = _load_five_tick_session(tmp_path)
    assert not session.at_end
    state = session.seek(4)
    assert state.tick == 4
    assert session.at_end
    assert session.final_tick == 4


def test_seek_below_range_raises(tmp_path):
    session, _ = _load_five_tick_session(tmp_path)
    with pytest.raises(ReplaySessionError, match="outside the replay's recorded range"):
        session.seek(-1)


def test_seek_beyond_range_raises(tmp_path):
    session, _ = _load_five_tick_session(tmp_path)
    with pytest.raises(ReplaySessionError, match="outside the replay's recorded range"):
        session.seek(5)


def test_seek_on_replay_with_no_ticks_raises(tmp_path):
    replay_path = tmp_path / "replay.jsonl"
    header, *_rest = _five_tick_replay_records()
    _write(replay_path, [header])
    session = ReplaySession()
    session.load(replay_path)

    with pytest.raises(ReplaySessionError, match="no tick records to seek within"):
        session.seek(0)


def test_seek_after_step_forward_reaches_the_correct_state(tmp_path):
    session, _ = _load_five_tick_session(tmp_path)
    session.step_forward()  # tick 1
    session.step_forward()  # tick 2
    state = session.seek(4)
    assert state.tick == 4
    assert state.arena[3] == 0x13
    assert state.arena[4] == 0x14


def test_seek_every_tick_of_a_real_vm_replay_succeeds(tmp_path):
    # Empirically confirms canonical replays record every integer tick with
    # no gaps (established by inspecting match.py's publish loop), rather
    # than merely asserting it.
    result = _run_vm_match(tmp_path)
    session = ReplaySession()
    session.load(result.replay_path)

    final = session.final_tick
    assert final is not None
    for tick in range(final + 1):
        state = session.seek(tick)
        assert state.tick == tick


# ---------------------------------------------------------------------------
# Determinism: reconstructed state depends only on the target tick, never on
# the cursor's prior history.
# ---------------------------------------------------------------------------
def _snapshot(state):
    return (
        state.tick,
        state.arena,
        state.owners,
        dict(state.agents),
        dict(state.score),
        state.runtime_kind,
    )


def test_seeked_state_is_deterministic_regardless_of_cursor_history(tmp_path):
    replay_path = tmp_path / "replay.jsonl"
    _write(replay_path, list(_five_tick_replay_records()))

    session = ReplaySession()
    session.load(replay_path)
    session.seek(3)
    state_a = _snapshot(session.current_state)

    session.seek(1)
    session.seek(3)
    state_b = _snapshot(session.current_state)

    session.restart()
    session.seek(3)
    state_c = _snapshot(session.current_state)

    fresh = ReplaySession()
    fresh.load(replay_path)
    fresh.seek(3)
    state_d = _snapshot(fresh.current_state)

    assert state_a == state_b == state_c == state_d


# ---------------------------------------------------------------------------
# Sparse (non-contiguous) tick policy: gaps between strictly-increasing
# ticks are allowed, but seek never fabricates state for an unrecorded tick.
# ---------------------------------------------------------------------------
def test_sparse_ticks_seek_to_recorded_tick_succeeds(tmp_path):
    replay_path = tmp_path / "replay.jsonl"
    header = ReplayHeader(MatchConfiguration(arena_size=8), runtime_kind="vm")
    tick_zero = TickSnapshot(0, agents=(_agent("A", pc=0),), score={"A": 0})
    tick_five = TickSnapshot(5, agents=(_agent("A", pc=5),), score={"A": 5})
    tick_nine = TickSnapshot(9, agents=(_agent("A", pc=9),), score={"A": 9})
    _write(replay_path, [header, tick_zero, tick_five, tick_nine])

    session = ReplaySession()
    session.load(replay_path)

    state = session.seek(5)
    assert state.tick == 5
    assert state.agents["A"].pc == 5

    state = session.seek(9)
    assert state.tick == 9
    assert session.at_end


def test_sparse_ticks_seek_into_a_gap_raises_rather_than_fabricating_state(tmp_path):
    replay_path = tmp_path / "replay.jsonl"
    header = ReplayHeader(MatchConfiguration(arena_size=8), runtime_kind="vm")
    tick_zero = TickSnapshot(0)
    tick_five = TickSnapshot(5)
    tick_nine = TickSnapshot(9)
    _write(replay_path, [header, tick_zero, tick_five, tick_nine])

    session = ReplaySession()
    session.load(replay_path)

    with pytest.raises(ReplaySessionError, match="not recorded in this replay"):
        session.seek(3)


# ---------------------------------------------------------------------------
# Runtime-kind exposure: VM and Python
# ---------------------------------------------------------------------------
NOP_SOURCE = """
from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        pass

    def act(self, observation):
        return AgentAction(ActionKind.NOP)

def create_agent():
    return Agent()
"""


def _python_spec(root, name, source):
    from battle_engine.agents import resolve_agent

    directory = root / "agents" / name
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text(
        json.dumps(
            {
                "kind": "python",
                "api_version": 1,
                "entrypoint": "agent.py:create_agent",
                "name": name,
                "display": name.title(),
                "version": "1.0",
            }
        ),
        encoding="utf-8",
    )
    (directory / "agent.py").write_text(source, encoding="utf-8")
    return resolve_agent(root, name)


def _run_python_match(tmp_path):
    entrants = (
        MatchEntrant.python("A", "a", 0, _python_spec(tmp_path, "a", NOP_SOURCE)),
        MatchEntrant.python("B", "b", 4, _python_spec(tmp_path, "b", NOP_SOURCE)),
    )
    replay_path = tmp_path / "replay.jsonl"
    result = NativeMatchService().run(
        MatchRequest(_config(), entrants, max_ticks=3, replay_path=replay_path, verbose=False)
    )
    return result


def test_runtime_kind_is_exposed_for_a_vm_replay(tmp_path):
    result = _run_vm_match(tmp_path)
    session = ReplaySession()
    session.load(result.replay_path)

    assert session.runtime_kind == "vm"
    assert session.current_state.runtime_kind == "vm"


def test_runtime_kind_is_exposed_for_a_python_replay(tmp_path):
    result = _run_python_match(tmp_path)
    session = ReplaySession()
    session.load(result.replay_path)

    assert session.runtime_kind == "python"
    # A consumer can distinguish VM from Python semantics via runtime_kind
    # alone -- self-describing on the state object, not just the session --
    # without inspecting any AgentState field's incidental value.
    assert session.current_state.runtime_kind == "python"
    while not session.at_end:
        state = session.step_forward()
    # Python's region is always a degenerate one-cell marker, never a real
    # code footprint (Python source is never loaded into the arena).
    assert state.agents["A"].region == (0, 0)


# ---------------------------------------------------------------------------
# State mutation safety
# ---------------------------------------------------------------------------
def test_state_agents_mapping_rejects_mutation(tmp_path):
    session, _ = _load_five_tick_session(tmp_path)
    state = session.current_state
    with pytest.raises(TypeError):
        state.agents["A"] = _agent("Z")


def test_state_score_mapping_rejects_mutation(tmp_path):
    session, _ = _load_five_tick_session(tmp_path)
    state = session.current_state
    with pytest.raises(TypeError):
        state.score["A"] = 999


def test_state_owners_tuple_rejects_mutation(tmp_path):
    session, _ = _load_five_tick_session(tmp_path)
    state = session.current_state
    with pytest.raises(TypeError):
        state.owners[0] = "Z"


def test_state_arena_bytes_rejects_mutation(tmp_path):
    session, _ = _load_five_tick_session(tmp_path)
    state = session.current_state
    with pytest.raises(TypeError):
        state.arena[0] = 0xFF


def test_mutation_attempts_do_not_corrupt_subsequent_stepping(tmp_path):
    session, _ = _load_five_tick_session(tmp_path)
    state = session.current_state
    for attempt in (
        lambda: state.agents.update({"A": _agent("Z")}),
        lambda: state.score.update({"A": 999}),
    ):
        try:
            attempt()
        except (TypeError, AttributeError):
            pass

    next_state = session.step_forward()
    assert next_state.tick == 1
    assert next_state.arena[1] == 0x11
    assert next_state.agents["A"].pc == 1
    assert next_state.score == {"A": 1}


# ---------------------------------------------------------------------------
# events_at_tick after seek
# ---------------------------------------------------------------------------
def test_events_at_tick_after_seek_matches_recorded_events(tmp_path):
    replay_path = tmp_path / "replay.jsonl"
    header, tick0, tick1, tick2, result = _small_replay_records()
    _write(replay_path, [header, tick0, tick1, tick2, result])

    session = ReplaySession()
    session.load(replay_path)

    session.seek(2)
    assert session.events_at_tick(session.current_tick) == (KillDeathEvent("death", "B", "A"),)

    session.seek(0)
    assert session.events_at_tick(session.current_tick) == ()


def test_events_at_tick_for_an_unrecorded_tick_after_seek_raises(tmp_path):
    session, _ = _load_five_tick_session(tmp_path)
    session.seek(3)
    with pytest.raises(ReplaySessionError, match="no tick 99"):
        session.events_at_tick(99)


# ---------------------------------------------------------------------------
# current_tick / final_tick accessors
# ---------------------------------------------------------------------------
def test_current_tick_and_final_tick_accessors(tmp_path):
    session, _ = _load_five_tick_session(tmp_path)
    assert session.current_tick == 0
    assert session.final_tick == 4

    session.seek(3)
    assert session.current_tick == 3
    assert session.final_tick == 4  # stable regardless of cursor position


def test_recorded_ticks_is_contiguous_for_a_canonical_replay(tmp_path):
    session, _ = _load_five_tick_session(tmp_path)
    assert session.recorded_ticks == (0, 1, 2, 3, 4)


def test_recorded_ticks_reflects_gaps_in_a_sparse_legacy_replay(tmp_path):
    replay_path = tmp_path / "replay.jsonl"
    header = ReplayHeader(MatchConfiguration(arena_size=8), runtime_kind="vm")
    _write(replay_path, [header, TickSnapshot(0), TickSnapshot(5), TickSnapshot(9)])

    session = ReplaySession()
    session.load(replay_path)
    assert session.recorded_ticks == (0, 5, 9)


# ---------------------------------------------------------------------------
# at_end semantics across seek/restart/step
# ---------------------------------------------------------------------------
def test_at_end_semantics_across_seek_and_restart(tmp_path):
    session, _ = _load_five_tick_session(tmp_path)
    assert not session.at_end

    session.seek(4)
    assert session.at_end

    session.seek(2)
    assert not session.at_end

    session.restart()
    assert not session.at_end

    session.seek(4)
    assert session.at_end
    with pytest.raises(ReplaySessionError, match="final tick"):
        session.step_forward()


# ---------------------------------------------------------------------------
# The terminal MatchResult is never treated as an extra seekable tick
# ---------------------------------------------------------------------------
def test_terminal_result_is_not_a_fake_extra_tick(tmp_path):
    session, _ = _load_five_tick_session(tmp_path)
    assert session.final_tick == 4
    with pytest.raises(ReplaySessionError, match="outside the replay's recorded range"):
        session.seek(5)

    session.seek(0)
    assert session.winner == "A"
    assert session.termination_reason == "tick_limit"


# ---------------------------------------------------------------------------
# Legacy replay seeking
# ---------------------------------------------------------------------------
def test_seek_legacy_v01_replay(tmp_path):
    replay_path = tmp_path / "replay.jsonl"
    replay_path.write_text(
        "\n".join(
            [
                json.dumps({"tick": 0, "ver": 6, "config": {"arena_size": 16}}),
                json.dumps(
                    {
                        "tick": 1,
                        "agents": [{"id": "A", "pc": 1, "alive": True}],
                        "score": {"A": 1},
                        "events": [],
                        "memory_diffs": [{"addr": 1, "len": 1, "owner": "A"}],
                    }
                ),
                json.dumps(
                    {
                        "tick": 2,
                        "agents": [{"id": "A", "pc": 2, "alive": True}],
                        "score": {"A": 2},
                        "events": [],
                        "memory_diffs": [{"addr": 2, "len": 1, "owner": "A"}],
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    session = ReplaySession()
    session.load(replay_path)
    # No tick-0 snapshot in this fixture, so the session starts at the
    # first recorded tick (1).
    assert session.current_tick == 1

    state = session.seek(2)
    assert state.tick == 2
    assert state.owners[1] == "A"
    assert state.owners[2] == "A"
    # Legacy diffs never captured byte values.
    assert state.arena[1] == 0
    assert state.arena[2] == 0

    state = session.seek(1)
    assert state.tick == 1
    assert state.owners[2] is None  # tick 2's write hasn't happened yet


def test_seek_legacy_v02_replay(tmp_path):
    replay_path = tmp_path / "replay.jsonl"

    def _tick_record(tick, address):
        return json.dumps(
            {
                "schema": "battle2.replay",
                "schema_version": 2,
                "record_type": "tick",
                "tick": tick,
                "agents": [{"id": "A", "pc": tick, "alive": True}],
                "score": {"A": tick},
                "events": [],
                "memory_diffs": [{"addr": address, "len": 1, "owner": "A"}],
            }
        )

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
                _tick_record(1, 1),
                _tick_record(2, 2),
                _tick_record(3, 3),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    session = ReplaySession()
    session.load(replay_path)
    assert session.current_tick == 1

    state = session.seek(3)
    assert state.tick == 3
    assert state.owners[1:4] == ("A", "A", "A")
    assert all(owner is None for owner in state.owners[4:])
    assert state.owners[0] is None
    assert state.agents["A"].pc == 3

    state = session.seek(1)
    assert state.tick == 1
    assert state.owners[2] is None
    assert state.owners[3] is None
