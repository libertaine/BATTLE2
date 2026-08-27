from __future__ import annotations

import subprocess
import sys

import pytest
from battle_client.analysis import (
    SelectedCellInfo,
    TerritoryHistory,
    collect_match_events,
    compute_territory_history,
    events_near_tick,
    nearest_recorded_tick,
    selected_cell_info,
    territory_summary,
    timeline_event_marks,
)
from battle_client.session import ReplaySession, ReplayState
from battle_engine.replay import (
    AgentEvent,
    AgentState,
    KillDeathEvent,
    MatchConfiguration,
    MatchResult,
    MemoryDiff,
    ReplayHeader,
    RuntimeEvent,
    TickSnapshot,
    write_replay,
)


# ---------------------------------------------------------------------------
# Helpers (mirrors the fixtures in test_pygame_renderer.py, which these
# tests were migrated from -- see docs/specs/replay_analysis.md §8).
# ---------------------------------------------------------------------------
def _agent(agent_id, pc=0, alive=True, cpu_used=0, mem_writes=0, region=None):
    return AgentState(
        agent_id=agent_id, pc=pc, alive=alive, cpu_used=cpu_used,
        mem_writes=mem_writes, region=region,
    )


def _events_session(tmp_path):
    """A 5-tick, 3-agent VM replay with known ownership and two real
    events: a killer-attributed "kill" at tick 2, and an unattributed
    "death" at tick 4. Arena size 10 gives clean round territory
    percentages (A ends with 3/10 = 30.0%, C with 2/10 = 20.0%, B with 0).
    """
    header = ReplayHeader(
        MatchConfiguration(arena_size=10),
        {"A": "alpha", "B": "beta", "C": "gamma"},
        runtime_kind="vm",
    )
    tick0 = TickSnapshot(
        0,
        agents=(_agent("A", pc=0), _agent("B", pc=4), _agent("C", pc=8)),
        score={"A": 0, "B": 0, "C": 0},
        memory_diffs=(
            MemoryDiff(address=0, length=1, owner="A", values=(1,)),
            MemoryDiff(address=4, length=1, owner="B", values=(1,)),
            MemoryDiff(address=8, length=1, owner="C", values=(1,)),
        ),
    )
    tick1 = TickSnapshot(
        1,
        agents=(_agent("A", pc=1), _agent("B", pc=4), _agent("C", pc=8)),
        score={"A": 0, "B": 0, "C": 0},
        memory_diffs=(MemoryDiff(address=1, length=1, owner="A", values=(1,)),),
    )
    tick2 = TickSnapshot(
        2,
        agents=(_agent("A", pc=2), _agent("B", pc=4, alive=False), _agent("C", pc=8)),
        score={"A": 2, "B": 0, "C": 0},
        memory_diffs=(MemoryDiff(address=4, length=1, owner="A", values=(1,)),),
        events=(KillDeathEvent("kill", "B", "A"),),
    )
    tick3 = TickSnapshot(
        3,
        agents=(_agent("A", pc=2), _agent("B", pc=4, alive=False), _agent("C", pc=9)),
        score={"A": 2, "B": 0, "C": 0},
        memory_diffs=(MemoryDiff(address=9, length=1, owner="C", values=(1,)),),
    )
    tick4 = TickSnapshot(
        4,
        agents=(
            _agent("A", pc=2), _agent("B", pc=4, alive=False), _agent("C", pc=9, alive=False),
        ),
        score={"A": 2, "B": 0, "C": 0},
        events=(KillDeathEvent("death", "C", None),),
    )
    result = MatchResult(
        winner="A", win_mode="score", ticks=4, score={"A": 2, "B": 0, "C": 0},
        agents=(_agent("A", pc=2), _agent("B", pc=4, alive=False), _agent("C", pc=9, alive=False)),
        termination_reason="last_agent_standing",
    )
    replay_path = tmp_path / "events.jsonl"
    write_replay(replay_path, [header, tick0, tick1, tick2, tick3, tick4, result])
    session = ReplaySession()
    session.load(replay_path)
    return session


def _no_events_session(tmp_path):
    header = ReplayHeader(MatchConfiguration(arena_size=8), {"A": "alpha"}, runtime_kind="vm")
    ticks = [TickSnapshot(t, agents=(_agent("A", pc=t),), score={"A": t}) for t in range(3)]
    replay_path = tmp_path / "no_events.jsonl"
    write_replay(replay_path, [header, *ticks])
    session = ReplaySession()
    session.load(replay_path)
    return session


def _python_session(tmp_path):
    """A real (not hand-built) 2-agent Python match, for coverage of the
    runtime-kind branch in selected_cell_info."""
    from battle_engine.agent_api import ActionKind, AgentAction  # noqa: F401
    from battle_engine.config import Config
    from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService

    source = """
from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        pass

    def act(self, observation):
        return AgentAction(ActionKind.NOP)

def create_agent():
    return Agent()
"""

    def _python_spec(root, name):
        import json

        from battle_engine.agents import resolve_agent

        directory = root / "agents" / name
        directory.mkdir(parents=True)
        (directory / "agent.yaml").write_text(
            json.dumps(
                {
                    "kind": "python", "api_version": 1, "entrypoint": "agent.py:create_agent",
                    "name": name, "display": name.title(), "version": "1.0",
                }
            ),
            encoding="utf-8",
        )
        (directory / "agent.py").write_text(source, encoding="utf-8")
        return resolve_agent(root, name)

    entrants = (
        MatchEntrant.python("A", "a", 0, _python_spec(tmp_path, "a")),
        MatchEntrant.python("B", "b", 4, _python_spec(tmp_path, "b")),
    )
    replay_path = tmp_path / "python_replay.jsonl"
    NativeMatchService().run(
        MatchRequest(
            Config(arena_size=32, instr_per_tick=1, seed=1),
            entrants, max_ticks=2, replay_path=replay_path, verbose=False,
        )
    )
    session = ReplaySession()
    session.load(replay_path)
    return session


def _run_vm_kill_match(tmp_path):
    """A real (not hand-built) VM match where A halts -- used to confirm
    collect_match_events picks up a genuine engine-produced death event,
    not just a hand-built one."""
    from battle_engine.config import Config
    from battle_engine.core import HALT, NOP, enc
    from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService

    entrants = (
        MatchEntrant("A", "halts", 0, enc(HALT)),
        MatchEntrant("B", "waits", 16, enc(NOP)),
    )
    replay_path = tmp_path / "vm_events.jsonl"
    NativeMatchService().run(
        MatchRequest(
            Config(arena_size=32, instr_per_tick=1, seed=1337),
            entrants, 2, replay_path, False,
        )
    )
    session = ReplaySession()
    session.load(replay_path)
    return session


def _python_forfeit_session(tmp_path):
    """A real Python match where entrant A forfeits via an unhandled
    exception in act(), for an end-to-end (not hand-built) forfeit event."""
    import json

    from battle_engine.agents import resolve_agent
    from battle_engine.config import Config
    from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService

    failing_source = """
from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        pass

    def act(self, observation):
        raise RuntimeError("boom")

def create_agent():
    return Agent()
"""
    nop_source = """
from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        pass

    def act(self, observation):
        return AgentAction(ActionKind.NOP)

def create_agent():
    return Agent()
"""

    def _spec(root, name, source):
        directory = root / "agents" / name
        directory.mkdir(parents=True)
        (directory / "agent.yaml").write_text(
            json.dumps(
                {
                    "kind": "python", "api_version": 1, "entrypoint": "agent.py:create_agent",
                    "name": name, "display": name.title(), "version": "1.0",
                }
            ),
            encoding="utf-8",
        )
        (directory / "agent.py").write_text(source, encoding="utf-8")
        return resolve_agent(root, name)

    entrants = (
        MatchEntrant.python("A", "failing", 0, _spec(tmp_path, "failing", failing_source)),
        MatchEntrant.python("B", "passive", 16, _spec(tmp_path, "passive", nop_source)),
    )
    replay_path = tmp_path / "forfeit_replay.jsonl"
    NativeMatchService().run(
        MatchRequest(
            Config(arena_size=32, instr_per_tick=1, seed=1),
            entrants, max_ticks=2, replay_path=replay_path, verbose=False,
        )
    )
    session = ReplaySession()
    session.load(replay_path)
    return session


# ---------------------------------------------------------------------------
# territory_summary
# ---------------------------------------------------------------------------
def test_territory_summary_matches_owner_counts_and_percentages(tmp_path):
    session = _events_session(tmp_path)
    while not session.at_end:
        session.step_forward()
    territory = territory_summary(session.current_state)
    assert territory == {"A": (3, 30.0), "B": (0, 0.0), "C": (2, 20.0)}


def test_territory_summary_reflects_state_at_an_earlier_tick(tmp_path):
    session = _events_session(tmp_path)
    territory = territory_summary(session.current_state)  # tick 0
    assert territory == {"A": (1, 10.0), "B": (1, 10.0), "C": (1, 10.0)}


def test_territory_summary_only_includes_agents_present_in_state():
    state = ReplayState(
        tick=0,
        arena=b"\x00" * 4,
        owners=("A", "A", None, None),
        agents={"A": _agent("A")},
        score={"A": 0},
        runtime_kind="vm",
    )
    assert territory_summary(state) == {"A": (2, 50.0)}


def test_territory_summary_on_empty_arena_does_not_divide_by_zero():
    state = ReplayState(
        tick=0, arena=b"", owners=(), agents={"A": _agent("A")}, score={}, runtime_kind="vm",
    )
    assert territory_summary(state) == {"A": (0, 0.0)}


# ---------------------------------------------------------------------------
# compute_territory_history
# ---------------------------------------------------------------------------
def test_compute_territory_history_matches_territory_summary_at_every_tick(tmp_path):
    session = _events_session(tmp_path)
    history = compute_territory_history(session)

    assert history.ticks == (0, 1, 2, 3, 4)
    session.restart()
    for index, tick in enumerate(history.ticks):
        if session.current_tick != tick:
            session.step_forward()
        expected = territory_summary(session.current_state)
        for agent_id, (_count, percentage) in expected.items():
            assert history.percentages[agent_id][index] == pytest.approx(percentage)


def test_compute_territory_history_shows_gain_and_loss_over_ticks(tmp_path):
    session = _events_session(tmp_path)
    history = compute_territory_history(session)

    assert history.percentages["A"] == (10.0, 20.0, 30.0, 30.0, 30.0)
    assert history.percentages["B"] == (10.0, 10.0, 0.0, 0.0, 0.0)
    assert history.percentages["C"] == (10.0, 10.0, 10.0, 20.0, 20.0)


def test_compute_territory_history_unowned_cells_never_attributed_to_an_agent(tmp_path):
    session = _events_session(tmp_path)  # arena_size=10, only 3 cells ever claimed at tick 0
    history = compute_territory_history(session)
    total_owned_pct = sum(history.percentages[a][0] for a in history.percentages)
    assert total_owned_pct == pytest.approx(30.0)  # 3/10 cells; the rest stay unowned


def test_compute_territory_history_restores_session_cursor(tmp_path):
    session = _events_session(tmp_path)
    session.seek(3)
    compute_territory_history(session)
    assert session.current_tick == 3


def test_compute_territory_history_empty_replay_is_empty(tmp_path):
    header = ReplayHeader(MatchConfiguration(arena_size=4), {"A": "alpha"}, runtime_kind="vm")
    replay_path = tmp_path / "empty.jsonl"
    write_replay(replay_path, [header])
    session = ReplaySession()
    session.load(replay_path)

    history = compute_territory_history(session)

    assert history == TerritoryHistory(ticks=(), percentages={})


def test_compute_territory_history_does_not_depend_on_canonical_score(tmp_path):
    # In _events_session, A's score jumps to 2 at tick 2 on the kill, but
    # A's territory percentage only reflects owned cells, not that score.
    session = _events_session(tmp_path)
    history = compute_territory_history(session)
    tick2_index = history.ticks.index(2)
    assert history.percentages["A"][tick2_index] == pytest.approx(30.0)  # 3/10 cells


# ---------------------------------------------------------------------------
# collect_match_events / events_near_tick
# ---------------------------------------------------------------------------
def test_collect_match_events_returns_every_event_in_chronological_order(tmp_path):
    session = _events_session(tmp_path)
    events = collect_match_events(session)
    assert events == [
        (2, KillDeathEvent("kill", "B", "A")),
        (4, KillDeathEvent("death", "C", None)),
    ]


def test_collect_match_events_on_a_replay_with_no_events_is_empty(tmp_path):
    session = _no_events_session(tmp_path)
    assert collect_match_events(session) == []


def test_collect_match_events_on_a_real_vm_match_finds_the_recorded_death(tmp_path):
    session = _run_vm_kill_match(tmp_path)
    events = collect_match_events(session)
    assert events == [(1, KillDeathEvent("death", "A", None))]


def test_collect_match_events_on_a_real_python_forfeit_match(tmp_path):
    session = _python_forfeit_session(tmp_path)
    events = collect_match_events(session)
    assert len(events) == 1
    _tick, event = events[0]
    assert isinstance(event, RuntimeEvent)
    assert event.event_type == "forfeit"
    assert event.victim == "A"
    assert event.reason == "agent_action_failed"


def test_collect_match_events_does_not_disturb_session_cursor(tmp_path):
    session = _events_session(tmp_path)
    session.seek(3)
    collect_match_events(session)
    assert session.current_tick == 3


def test_events_near_tick_excludes_events_after_the_given_tick():
    events = [(2, KillDeathEvent("kill", "B", "A")), (4, KillDeathEvent("death", "C", None))]
    assert events_near_tick(events, 1) == []
    assert events_near_tick(events, 2) == [(2, KillDeathEvent("kill", "B", "A"))]
    assert events_near_tick(events, 3) == [(2, KillDeathEvent("kill", "B", "A"))]
    assert events_near_tick(events, 4) == events


def test_events_near_tick_stays_in_ascending_order_and_respects_window():
    events = [(t, KillDeathEvent("death", str(t), None)) for t in range(10)]
    recent = events_near_tick(events, 9, window=3)
    assert [tick for tick, _event in recent] == [7, 8, 9]


def test_events_near_tick_zero_window_returns_nothing():
    events = [(2, KillDeathEvent("kill", "B", "A"))]
    assert events_near_tick(events, 2, window=0) == []


# ---------------------------------------------------------------------------
# selected_cell_info
# ---------------------------------------------------------------------------
def test_selected_cell_info_reports_byte_owner_and_vm_occupant(tmp_path):
    session = _events_session(tmp_path)  # tick 0: A owns/occupies 0, B owns/occupies 4
    info = selected_cell_info(session.current_state, 0)
    assert info == SelectedCellInfo(address=0, byte_value=1, owner="A", occupant="A")


def test_selected_cell_info_unowned_unoccupied_cell(tmp_path):
    session = _events_session(tmp_path)
    info = selected_cell_info(session.current_state, 5)
    assert info == SelectedCellInfo(address=5, byte_value=0, owner=None, occupant=None)


def test_selected_cell_info_owner_present_without_current_occupant(tmp_path):
    session = _events_session(tmp_path)
    session.step_forward()  # tick 1: A's pc moves to 1; address 0 still owned by A
    info = selected_cell_info(session.current_state, 0)
    assert info.owner == "A"
    assert info.occupant is None


def test_selected_cell_info_out_of_range_address_is_none(tmp_path):
    session = _events_session(tmp_path)
    assert selected_cell_info(session.current_state, 10) is None
    assert selected_cell_info(session.current_state, -1) is None


def test_selected_cell_info_python_replay_never_reports_an_occupant(tmp_path):
    session = _python_session(tmp_path)
    state = session.current_state
    assert state.runtime_kind == "python"
    for agent in state.agents.values():
        assert isinstance(agent.pc, int)
        info = selected_cell_info(state, agent.pc % len(state.owners))
        assert info.occupant is None  # never invented for a Python controller value


# ---------------------------------------------------------------------------
# Headless-importability (v0.4 Phase 5, docs/specs/replay_analysis.md §9)
# ---------------------------------------------------------------------------
def test_analysis_module_imports_without_pulling_in_pygame():
    code = (
        "import sys\n"
        "import battle_client.analysis\n"
        "assert 'pygame' not in sys.modules, sorted(sys.modules)\n"
        "print('ok')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


# ---------------------------------------------------------------------------
# Match-timeline marks and recorded-tick snapping (v3.0).
# ---------------------------------------------------------------------------
def test_timeline_event_marks_names_the_affected_entrant_per_event_kind():
    events = [
        (4, KillDeathEvent("kill", "A", "B")),
        (9, KillDeathEvent("death", "C", None)),
        (11, RuntimeEvent("forfeit", "D", "invalid_action")),
        (14, AgentEvent("claim", "B")),
    ]

    assert timeline_event_marks(events) == ((4, "A"), (9, "C"), (11, "D"), (14, "B"))


def test_timeline_event_marks_reports_no_agent_rather_than_guessing_one():
    """An ``AgentEvent`` need not name an actor; the mark stays anonymous
    instead of being attributed to somebody."""
    assert timeline_event_marks([(3, AgentEvent("claim", None))]) == ((3, None),)


def test_timeline_event_marks_collapses_duplicates_on_the_same_tick():
    """Several events naming the same entrant at one tick would otherwise
    draw the identical mark repeatedly at the identical pixel."""
    events = [
        (7, KillDeathEvent("kill", "A", "B")),
        (7, KillDeathEvent("death", "A", None)),
        (7, KillDeathEvent("kill", "C", "B")),
    ]

    assert timeline_event_marks(events) == ((7, "A"), (7, "C"))


def test_timeline_event_marks_preserves_ascending_tick_order():
    events = [(1, KillDeathEvent("kill", "A", "B")), (99, KillDeathEvent("kill", "B", "C"))]

    assert [tick for tick, _agent in timeline_event_marks(events)] == [1, 99]


def test_timeline_event_marks_of_an_eventless_match_is_empty():
    """The common case: most recorded matches run to the tick limit with no
    events at all, and the track simply shows progress."""
    assert timeline_event_marks([]) == ()


def test_nearest_recorded_tick_is_an_identity_for_a_canonical_replay():
    recorded = tuple(range(6))

    assert [nearest_recorded_tick(recorded, t) for t in recorded] == list(recorded)


def test_nearest_recorded_tick_snaps_into_a_sparse_replays_gap():
    recorded = (0, 10, 40)

    assert nearest_recorded_tick(recorded, 9) == 10
    assert nearest_recorded_tick(recorded, 12) == 10
    assert nearest_recorded_tick(recorded, 33) == 40


def test_nearest_recorded_tick_breaks_an_exact_tie_deterministically():
    assert nearest_recorded_tick((0, 10), 5) == 0


def test_nearest_recorded_tick_clamps_outside_the_recorded_range():
    recorded = (5, 6, 7)

    assert nearest_recorded_tick(recorded, -100) == 5
    assert nearest_recorded_tick(recorded, 100) == 7


def test_nearest_recorded_tick_of_an_empty_replay_is_none():
    assert nearest_recorded_tick((), 3) is None
