from __future__ import annotations

import pytest
from battle_client.player import PlaybackController
from battle_client.renderers.pygame_renderer import (
    PygameRenderer,
    _event_section_start,
    build_hud_lines,
    collect_match_events,
    events_near_tick,
    format_event_line,
    resolve_event_click,
    territory_summary,
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
# Helpers (local to this file, matching the existing per-file convention --
# see test_playback_controller.py / test_replay_session.py).
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

FAILING_SOURCE = """
from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        pass

    def act(self, observation):
        raise RuntimeError("boom")

def create_agent():
    return Agent()
"""


def _python_spec(root, name, source):
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


def _python_session(tmp_path):
    """A real (not hand-built) 2-agent Python match with no events, for
    parametrized VM-vs-Python coverage of the HUD/territory rendering."""
    from battle_engine.config import Config
    from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService

    entrants = (
        MatchEntrant.python("A", "a", 0, _python_spec(tmp_path, "a", NOP_SOURCE)),
        MatchEntrant.python("B", "b", 4, _python_spec(tmp_path, "b", NOP_SOURCE)),
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


def _python_forfeit_session(tmp_path):
    """A real Python match where entrant A forfeits via an unhandled
    exception in act(), for an end-to-end (not hand-built) forfeit event."""
    from battle_engine.config import Config
    from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService

    entrants = (
        MatchEntrant.python("A", "failing", 0, _python_spec(tmp_path, "failing", FAILING_SOURCE)),
        MatchEntrant.python("B", "passive", 16, _python_spec(tmp_path, "passive", NOP_SOURCE)),
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


def _run_vm_kill_match(tmp_path):
    """A real (not hand-built) VM match where A halts and B kills nobody
    -- used to confirm collect_match_events picks up a genuine engine-
    produced death event, not just a hand-built one."""
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


# ---------------------------------------------------------------------------
# collect_match_events / events_near_tick / format_event_line
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


def test_format_event_line_kill_with_attributed_killer():
    assert format_event_line(42, KillDeathEvent("kill", "B", "A")) == "T042 kill: B by A"


def test_format_event_line_death_with_no_killer_omits_by_clause():
    line = format_event_line(4, KillDeathEvent("death", "C", None))
    assert line == "T004 death: C"
    assert "by" not in line


def test_format_event_line_forfeit_shows_reason():
    event = RuntimeEvent("forfeit", "C", "agent_action_failed", "action", 17, 0)
    assert format_event_line(17, event) == "T017 forfeit: C (agent_action_failed)"


def test_format_event_line_agent_event_legacy_compatibility():
    assert format_event_line(3, AgentEvent("spawn", agent_id="A")) == "T003 spawn: A"
    assert format_event_line(3, AgentEvent("spawn", agent_id=None)) == "T003 spawn: ?"


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
# resolve_event_click (pure geometry -- no Pygame dependency)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "click,expected",
    [
        ((50, 100), 2),
        ((50, 115), 2),
        ((50, 116), 4),
        ((50, 131), 4),
        ((50, 132), None),  # past the last rendered line
        ((50, 99), None),  # above the panel
        ((-5, 100), None),  # left of the panel
        ((400, 100), None),  # exactly at the right edge (exclusive)
    ],
)
def test_resolve_event_click(click, expected):
    ticks = (2, 4)
    assert resolve_event_click(ticks, (0, 100), (400, 32), 16, click) == expected


def test_resolve_event_click_degenerate_line_height_is_a_safe_no_op():
    assert resolve_event_click((2, 4), (0, 100), (400, 32), 0, (50, 100)) is None


def test_resolve_event_click_empty_ticks_is_a_safe_no_op():
    assert resolve_event_click((), (0, 100), (400, 32), 16, (50, 100)) is None


# ---------------------------------------------------------------------------
# _event_section_start
# ---------------------------------------------------------------------------
def test_event_section_start_locates_the_marker():
    lines = ["a", "b", "Recent events:", "  T002 kill: B by A"]
    assert _event_section_start(lines) == 3


def test_event_section_start_absent_returns_none():
    assert _event_section_start(["a", "b"]) is None


# ---------------------------------------------------------------------------
# build_hud_lines: territory + recent-events integration
# ---------------------------------------------------------------------------
def test_hud_shows_territory_distinct_from_score(tmp_path):
    session = _events_session(tmp_path)
    while not session.at_end:
        session.step_forward()
    controller = PlaybackController(session, playing=False)
    joined = "\n".join(build_hud_lines(session, controller))
    assert "territory=3/10 (30.0%)" in joined
    assert "territory=0/10 (0.0%)" in joined
    assert "territory=2/10 (20.0%)" in joined
    # score= and territory= must remain distinct tokens, never merged.
    assert "score=2  territory=3/10" in joined


def test_hud_shows_recent_events_section_after_agent_lines_before_winner(tmp_path):
    session = _events_session(tmp_path)
    while not session.at_end:
        session.step_forward()
    controller = PlaybackController(session, playing=False)
    lines = build_hud_lines(session, controller)
    events_index = lines.index("Recent events:")
    winner_index = next(i for i, line in enumerate(lines) if line.startswith("Winner:"))
    agent_index = next(i for i, line in enumerate(lines) if line.startswith("A (alpha)"))
    assert agent_index < events_index < winner_index
    assert "T002 kill: B by A" in lines[events_index + 1]
    assert "T004 death: C" in lines[events_index + 2]


def test_hud_omits_recent_events_section_when_there_are_none(tmp_path):
    session = _no_events_session(tmp_path)
    controller = PlaybackController(session, playing=False)
    joined = "\n".join(build_hud_lines(session, controller))
    assert "Recent events:" not in joined


def test_hud_recent_events_reflects_cursor_position_not_only_final_tick(tmp_path):
    session = _events_session(tmp_path)
    session.step_forward()  # tick 1: before either event
    controller = PlaybackController(session, playing=False)
    joined = "\n".join(build_hud_lines(session, controller))
    assert "Recent events:" not in joined

    session.step_forward()  # tick 2: the kill has happened
    joined = "\n".join(build_hud_lines(session, controller))
    assert "T002 kill: B by A" in joined
    assert "T004 death: C" not in joined


def test_hud_accepts_precomputed_match_events_without_rescanning(tmp_path):
    session = _events_session(tmp_path)
    while not session.at_end:
        session.step_forward()
    controller = PlaybackController(session, playing=False)
    precomputed = collect_match_events(session)
    joined = "\n".join(build_hud_lines(session, controller, match_events=precomputed))
    assert "T002 kill: B by A" in joined


@pytest.mark.parametrize("build_session", [_events_session, _python_session])
def test_hud_renders_without_crashing_for_vm_and_python_replays(tmp_path, build_session):
    session = build_session(tmp_path)
    controller = PlaybackController(session, playing=False)
    lines = build_hud_lines(session, controller)
    assert lines  # non-empty, no exception


def test_hud_python_forfeit_event_shows_reason_not_vm_wording(tmp_path):
    session = _python_forfeit_session(tmp_path)
    while not session.at_end:
        session.step_forward()
    controller = PlaybackController(session, playing=False)
    joined = "\n".join(build_hud_lines(session, controller))
    assert "forfeit: A (agent_action_failed)" in joined


# ---------------------------------------------------------------------------
# PygameRenderer._handle_click -- exercised directly, no real window/mouse
# ---------------------------------------------------------------------------
def test_handle_click_on_an_event_line_pauses_and_seeks(tmp_path):
    # Deliberately left at tick 0 (not stepped to the end) so that
    # ``playing=True`` actually takes effect (PlaybackController auto-
    # pauses on construction only when the session is already at_end) --
    # that way a False afterward genuinely proves _handle_click paused it.
    session = _events_session(tmp_path)
    controller = PlaybackController(session, playing=True)
    assert controller.playing is True
    renderer = PygameRenderer()
    renderer._event_panel_origin = (0, 100)
    renderer._event_panel_size = (400, 32)
    renderer._event_panel_ticks = (2, 4)

    renderer._handle_click(controller, (50, 100))

    assert controller.playing is False
    assert session.current_tick == 2


def test_handle_click_outside_the_panel_is_a_no_op(tmp_path):
    session = _events_session(tmp_path)
    controller = PlaybackController(session, playing=True)
    assert controller.playing is True
    renderer = PygameRenderer()
    renderer._event_panel_origin = (0, 100)
    renderer._event_panel_size = (400, 32)
    renderer._event_panel_ticks = (2, 4)

    renderer._handle_click(controller, (50, 9999))

    assert controller.playing is True
    assert session.current_tick == 0


def test_handle_click_with_no_panel_is_a_safe_no_op(tmp_path):
    session = _events_session(tmp_path)
    controller = PlaybackController(session, playing=True)
    renderer = PygameRenderer()  # _event_panel_origin defaults to None

    renderer._handle_click(controller, (50, 100))

    assert controller.playing is True
    assert session.current_tick == 0
