from __future__ import annotations

import pytest
from battle_client.analysis import SelectedCellInfo, collect_match_events, selected_cell_info
from battle_client.player import PlaybackController
from battle_client.renderers.pygame_renderer import (
    ACTIVITY_WINDOW_TICKS,
    PygameRenderer,
    _event_section_start,
    activity_intensity,
    build_hud_lines,
    downsample_series,
    format_event_line,
    format_inspector_lines,
    resolve_event_click,
    screen_pos_to_address,
    select_history_window,
    territory_graph_points,
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


# ---------------------------------------------------------------------------
# format_event_line
#
# collect_match_events/events_near_tick characterization moved to
# client/tests/test_analysis.py (v0.4 Phase 5) -- format_event_line stays
# here since it is presentation (text formatting), not a domain query; see
# docs/specs/replay_analysis.md §2-3.
# ---------------------------------------------------------------------------
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


# territory_summary/compute_territory_history characterization moved to
# client/tests/test_analysis.py (v0.4 Phase 5) -- see
# docs/specs/replay_analysis.md §2-3.


# ---------------------------------------------------------------------------
# select_history_window / downsample_series (Phase 7b Slice 3)
# ---------------------------------------------------------------------------
def test_select_history_window_keeps_only_the_trailing_range():
    ticks = (0, 1, 2, 3, 4, 5)
    values = (0.0, 10.0, 20.0, 30.0, 40.0, 50.0)
    windowed_ticks, windowed_values = select_history_window(ticks, values, current_tick=4, window=2)
    assert windowed_ticks == (2, 3, 4)
    assert windowed_values == (20.0, 30.0, 40.0)


def test_select_history_window_never_includes_ticks_after_current():
    ticks = (0, 1, 2, 3)
    values = (0.0, 1.0, 2.0, 3.0)
    windowed_ticks, _ = select_history_window(ticks, values, current_tick=1, window=100)
    assert windowed_ticks == (0, 1)


def test_select_history_window_empty_input_is_a_safe_no_op():
    assert select_history_window((), (), current_tick=5, window=10) == ((), ())


def test_downsample_series_keeps_all_points_under_the_cap():
    ticks = (0, 1, 2)
    values = (0.0, 1.0, 2.0)
    assert downsample_series(ticks, values, max_points=10) == (ticks, values)


def test_downsample_series_respects_the_cap_and_keeps_the_last_point():
    ticks = tuple(range(100))
    values = tuple(float(t) for t in ticks)
    sampled_ticks, sampled_values = downsample_series(ticks, values, max_points=10)
    assert len(sampled_ticks) <= 10
    assert sampled_ticks[-1] == 99
    assert sampled_values[-1] == 99.0


def test_downsample_series_non_positive_cap_is_a_safe_no_op():
    ticks, values = (0, 1, 2), (0.0, 1.0, 2.0)
    assert downsample_series(ticks, values, max_points=0) == (ticks, values)


# ---------------------------------------------------------------------------
# territory_graph_points (pure coordinate math -- no Pygame dependency)
# ---------------------------------------------------------------------------
def test_territory_graph_points_zero_percent_is_at_the_bottom():
    points = territory_graph_points((0,), (0.0,), (0, 0, 100, 50))
    assert points == [(0, 49)]


def test_territory_graph_points_hundred_percent_is_at_the_top():
    points = territory_graph_points((0,), (100.0,), (0, 0, 100, 50))
    assert points == [(0, 0)]


def test_territory_graph_points_spans_the_rect_by_tick():
    points = territory_graph_points((0, 10), (0.0, 0.0), (0, 0, 100, 50))
    assert points[0][0] == 0
    assert points[1][0] == 99  # rightmost pixel of the rect


def test_territory_graph_points_values_are_clamped_into_range():
    # A value above value_max (shouldn't happen for a real percentage, but
    # handled honestly) clamps to the top rather than drawing off-panel.
    points = territory_graph_points((0,), (150.0,), (0, 0, 100, 50), value_max=100.0)
    assert points == [(0, 0)]


def test_territory_graph_points_empty_or_degenerate_rect_is_a_safe_no_op():
    assert territory_graph_points((), (), (0, 0, 100, 50)) == []
    assert territory_graph_points((0,), (0.0,), (0, 0, 0, 50)) == []
    assert territory_graph_points((0,), (0.0,), (0, 0, 100, 0)) == []


# ---------------------------------------------------------------------------
# activity_intensity (pure decay/window math -- no Pygame dependency)
# ---------------------------------------------------------------------------
def test_activity_intensity_is_full_the_tick_it_changed():
    assert activity_intensity(current_tick=10, last_changed_tick=10, window=30) == 1.0


def test_activity_intensity_decays_linearly():
    assert activity_intensity(current_tick=25, last_changed_tick=10, window=30) == pytest.approx(0.5)


def test_activity_intensity_is_zero_at_and_beyond_the_window():
    assert activity_intensity(current_tick=40, last_changed_tick=10, window=30) == 0.0
    assert activity_intensity(current_tick=100, last_changed_tick=10, window=30) == 0.0


def test_activity_intensity_never_negative_for_a_future_change():
    assert activity_intensity(current_tick=5, last_changed_tick=10, window=30) == 0.0


def test_activity_intensity_non_positive_window_is_always_zero():
    assert activity_intensity(current_tick=10, last_changed_tick=10, window=0) == 0.0


# ---------------------------------------------------------------------------
# PygameRenderer._advance_transient_effects: recent-activity bookkeeping
# ---------------------------------------------------------------------------
def _state_with_owners(tick, owners, agents=None):
    return ReplayState(
        tick=tick,
        arena=bytes(len(owners)),
        owners=owners,
        agents=agents or {},
        score={},
        runtime_kind="vm",
    )


def test_linear_step_records_changed_addresses_in_recent_changes():
    renderer = PygameRenderer()
    renderer.arena, renderer.grid_cols, renderer.grid_rows = 4, 4, 1

    renderer._advance_transient_effects(_state_with_owners(0, (None, None, None, None)))
    renderer._advance_transient_effects(_state_with_owners(1, ("A", None, None, None)))

    assert renderer._recent_changes == {0: 1}


def test_recent_changes_decays_and_is_pruned_past_the_window():
    renderer = PygameRenderer()
    renderer.arena, renderer.grid_cols, renderer.grid_rows = 1, 1, 1

    renderer._advance_transient_effects(_state_with_owners(0, (None,)))
    renderer._advance_transient_effects(_state_with_owners(1, ("A",)))
    assert renderer._recent_changes == {0: 1}

    for tick in range(2, ACTIVITY_WINDOW_TICKS + 3):
        renderer._advance_transient_effects(_state_with_owners(tick, ("A",)))

    assert renderer._recent_changes == {}


def test_seek_clears_recent_changes():
    renderer = PygameRenderer()
    renderer.arena, renderer.grid_cols, renderer.grid_rows = 1, 1, 1

    renderer._advance_transient_effects(_state_with_owners(0, (None,)))
    renderer._advance_transient_effects(_state_with_owners(1, ("A",)))
    assert renderer._recent_changes == {0: 1}

    # A non-linear jump (e.g. a backward seek) -- next tick is not
    # last_rendered_tick + 1.
    renderer._advance_transient_effects(_state_with_owners(5, ("A",)))
    assert renderer._recent_changes == {}


def test_restart_clears_recent_changes():
    renderer = PygameRenderer()
    renderer.arena, renderer.grid_cols, renderer.grid_rows = 1, 1, 1

    renderer._advance_transient_effects(_state_with_owners(3, (None,)))
    renderer._advance_transient_effects(_state_with_owners(4, ("A",)))
    assert renderer._recent_changes == {0: 4}

    renderer._advance_transient_effects(_state_with_owners(0, (None,)))  # restart
    assert renderer._recent_changes == {}



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


# ---------------------------------------------------------------------------
# screen_pos_to_address (pure geometry -- no Pygame dependency)
# ---------------------------------------------------------------------------
def test_screen_pos_to_address_top_left_is_address_zero():
    assert screen_pos_to_address((0, 0), (100, 40), 5, 2, 10) == 0


def test_screen_pos_to_address_bottom_right_pixel_is_last_address():
    assert screen_pos_to_address((99, 39), (100, 40), 5, 2, 10) == 9


def test_screen_pos_to_address_cell_boundaries():
    # cols=5 -> cell width 20px; col 1 starts at x=20.
    assert screen_pos_to_address((19, 0), (100, 40), 5, 2, 10) == 0
    assert screen_pos_to_address((20, 0), (100, 40), 5, 2, 10) == 1
    # rows=2 -> cell height 20px; row 1 starts at y=20.
    assert screen_pos_to_address((0, 19), (100, 40), 5, 2, 10) == 0
    assert screen_pos_to_address((0, 20), (100, 40), 5, 2, 10) == 5


@pytest.mark.parametrize(
    "pos",
    [(100, 10), (-1, 10), (10, 40), (10, -1)],
)
def test_screen_pos_to_address_outside_screen_bounds_is_none(pos):
    assert screen_pos_to_address(pos, (100, 40), 5, 2, 10) is None


def test_screen_pos_to_address_degenerate_grid_is_a_safe_no_op():
    assert screen_pos_to_address((0, 0), (100, 40), 0, 2, 10) is None
    assert screen_pos_to_address((0, 0), (0, 0), 5, 2, 10) is None


# ---------------------------------------------------------------------------
# format_inspector_lines
#
# selected_cell_info's own domain-fact characterization (byte/owner/
# occupant derivation) moved to client/tests/test_analysis.py (v0.4 Phase
# 5). ``recently_changed`` is renderer-local presentation state -- see
# docs/specs/replay_analysis.md §6 -- so its characterization stays here,
# as a keyword argument to format_inspector_lines rather than a field on
# SelectedCellInfo.
# ---------------------------------------------------------------------------
def test_format_inspector_lines_none_selection_is_empty():
    assert format_inspector_lines(None) == []


def test_format_inspector_lines_shows_all_fields():
    info = SelectedCellInfo(address=7, byte_value=255, owner="A", occupant="A")
    lines = format_inspector_lines(info)
    assert lines[0] == "Selected cell:"
    assert "addr=7" in lines[1]
    assert "byte=0xff" in lines[1]
    assert "owner=A" in lines[1]
    assert "agent=A" in lines[1]
    assert "recently changed" not in lines[1]


def test_format_inspector_lines_unowned_unoccupied_reads_none():
    info = SelectedCellInfo(address=1, byte_value=0, owner=None, occupant=None)
    line = format_inspector_lines(info)[1]
    assert "owner=none" in line
    assert "agent=none" in line


def test_format_inspector_lines_recently_changed_is_flagged():
    info = SelectedCellInfo(address=1, byte_value=1, owner="A", occupant=None)
    line = format_inspector_lines(info, recently_changed=True)[1]
    assert "recently changed" in line


def test_format_inspector_lines_recently_changed_defaults_to_false():
    info = SelectedCellInfo(address=1, byte_value=1, owner="A", occupant=None)
    line = format_inspector_lines(info)[1]
    assert "recently changed" not in line


# ---------------------------------------------------------------------------
# build_hud_lines: selected-cell inspector integration
# ---------------------------------------------------------------------------
def test_hud_shows_selected_cell_between_agent_lines_and_events(tmp_path):
    session = _events_session(tmp_path)
    while not session.at_end:
        session.step_forward()
    controller = PlaybackController(session, playing=False)
    selected = selected_cell_info(session.current_state, 0)
    lines = build_hud_lines(session, controller, selected=selected)

    inspector_index = lines.index("Selected cell:")
    events_index = lines.index("Recent events:")
    agent_index = next(i for i, line in enumerate(lines) if line.startswith("A (alpha)"))
    assert agent_index < inspector_index < events_index


def test_hud_omits_selected_cell_section_when_nothing_selected(tmp_path):
    session = _no_events_session(tmp_path)
    controller = PlaybackController(session, playing=False)
    joined = "\n".join(build_hud_lines(session, controller))
    assert "Selected cell:" not in joined


# ---------------------------------------------------------------------------
# PygameRenderer cell selection: click handling, persistence, highlight
# ---------------------------------------------------------------------------
class _FakeScreen:
    """A minimal stand-in for a Pygame ``Surface``: only ``get_size()`` is
    exercised by cell-selection code, so this avoids needing a real window.
    """

    def __init__(self, size):
        self._size = size

    def get_size(self):
        return self._size


def _grid_renderer(arena_size, *, cell_px=20):
    renderer = PygameRenderer()
    cols, rows = renderer._resolve_grid_dims(arena_size)
    renderer.grid_cols, renderer.grid_rows, renderer.arena = cols, rows, arena_size
    renderer.screen = _FakeScreen((cols * cell_px, rows * cell_px))
    return renderer


def test_click_on_arena_cell_selects_its_address(tmp_path):
    session = _events_session(tmp_path)
    controller = PlaybackController(session, playing=False)
    renderer = _grid_renderer(10)

    renderer._handle_click(controller, (0, 0))

    assert renderer._selected_address == 0


def test_click_outside_arena_does_not_change_selection(tmp_path):
    session = _events_session(tmp_path)
    controller = PlaybackController(session, playing=False)
    renderer = _grid_renderer(10)
    renderer._selected_address = 3

    w, _h = renderer.screen.get_size()
    renderer._handle_click(controller, (w + 50, 5))

    assert renderer._selected_address == 3


def test_click_before_run_with_no_screen_leaves_selection_unchanged(tmp_path):
    session = _events_session(tmp_path)
    controller = PlaybackController(session, playing=False)
    renderer = PygameRenderer()  # screen/grid never configured (no run())

    renderer._handle_click(controller, (10, 10))

    assert renderer._selected_address is None


def test_event_panel_click_takes_priority_over_cell_selection(tmp_path):
    session = _events_session(tmp_path)
    controller = PlaybackController(session, playing=True)
    renderer = _grid_renderer(10)
    renderer._event_panel_origin = (0, 0)
    renderer._event_panel_size = (200, 32)
    renderer._event_panel_ticks = (2, 4)

    renderer._handle_click(controller, (0, 0))

    assert session.current_tick == 2  # seeked via the event panel
    assert renderer._selected_address is None  # cell selection untouched


def test_selection_persists_across_step_seek_and_restart(tmp_path):
    session = _events_session(tmp_path)
    controller = PlaybackController(session, playing=False)
    renderer = _grid_renderer(10)

    renderer._handle_click(controller, (0, 0))
    assert renderer._selected_address == 0

    session.step_forward()
    assert renderer._selected_address == 0

    session.seek(4)
    assert renderer._selected_address == 0

    session.restart()
    assert renderer._selected_address == 0


def test_inspector_values_update_as_replay_moves(tmp_path):
    session = _events_session(tmp_path)
    controller = PlaybackController(session, playing=False)
    renderer = _grid_renderer(10)
    renderer._handle_click(controller, (0, 0))  # address 0, owned+occupied by A at tick 0

    info_t0 = renderer._selected_cell_info(session.current_state)
    assert info_t0.owner == "A"
    assert info_t0.occupant == "A"

    session.step_forward()  # tick 1: A's pc moves to 1
    info_t1 = renderer._selected_cell_info(session.current_state)
    assert info_t1.owner == "A"
    assert info_t1.occupant is None

    session.seek(4)
    info_t4 = renderer._selected_cell_info(session.current_state)
    assert info_t4.address == 0


def test_selected_address_maps_back_to_the_clicked_cell_for_highlighting(tmp_path):
    session = _events_session(tmp_path)
    controller = PlaybackController(session, playing=False)
    renderer = _grid_renderer(10)

    renderer._handle_click(controller, (21, 21))  # inside cell col=1,row=1 (20px cells)
    assert renderer._selected_address == renderer.grid_cols + 1

    xy = renderer._to_xy(renderer._selected_address)
    assert xy == (1, 1)
