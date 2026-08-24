from __future__ import annotations

from types import SimpleNamespace

import pytest
from battle_client.analysis import SelectedCellInfo, collect_match_events
from battle_client.hud_layout import calculate_layout
from battle_client.player import PlaybackController
from battle_client.renderers.pygame_renderer import (
    ACTIVITY_WINDOW_TICKS,
    HELP_TEXT,
    HUD_CHAR_WIDTH_PX,
    PygameRenderer,
    activity_intensity,
    choose_initial_window_scale,
    downsample_series,
    format_event_line,
    format_inspector_lines,
    integer_scale_to_fit,
    resolve_event_click,
    screen_pos_to_address,
    select_history_window,
    territory_graph_points,
)
from battle_client.replay_status import get_entrant_statuses
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
# Replay-window sizing (maintenance fix after v0.7.0)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("arena", "expected_grid", "expected_scale", "expected_window"),
    [
        (256, (16, 16), 37, (592, 592)),
        (512, (32, 16), 30, (960, 480)),
        (1024, (32, 32), 18, (576, 576)),
    ],
)
def test_automatic_initial_window_uses_a_useful_integer_scale(
    arena, expected_grid, expected_scale, expected_window
):
    renderer = PygameRenderer()
    grid = renderer._resolve_grid_dims(arena)
    scale = choose_initial_window_scale(*grid, (1728, 972))

    assert grid == expected_grid
    assert scale == expected_scale
    assert (grid[0] * scale, grid[1] * scale) == expected_window
    assert expected_window not in ((64, 64), (128, 64), (128, 128))


@pytest.mark.parametrize(
    ("arena", "expected_window"),
    [
        (256, (432, 432)),
        (512, (576, 288)),
        (1024, (416, 416)),
    ],
)
def test_automatic_initial_window_shrinks_with_a_small_display(arena, expected_window):
    renderer = PygameRenderer()
    grid = renderer._resolve_grid_dims(arena)
    display_bounds = (576, 432)  # 90% of a 640x480 display
    scale = choose_initial_window_scale(*grid, display_bounds)
    window = (grid[0] * scale, grid[1] * scale)

    assert scale >= 1
    assert window == expected_window
    assert window[0] <= display_bounds[0]
    assert window[1] <= display_bounds[1]
    assert window[0] // grid[0] == window[1] // grid[1] == scale


def test_initial_explicit_scale_is_a_display_capped_preference():
    assert choose_initial_window_scale(32, 16, (1728, 972), requested_scale=4) == 4
    assert choose_initial_window_scale(32, 16, (1728, 972), requested_scale=100) == 54


def test_integer_scale_to_fit_is_positive_and_handles_resize_geometry():
    assert integer_scale_to_fit(32, 16, (800, 500)) == 25
    assert integer_scale_to_fit(32, 16, (160, 80)) == 5
    assert integer_scale_to_fit(32, 16, (0, -1)) == 1


def _display_stub(width, height):
    return SimpleNamespace(
        display=SimpleNamespace(
            Info=lambda: SimpleNamespace(current_w=width, current_h=height)
        ),
        error=RuntimeError,
    )


def test_configure_window_uses_display_margin_and_preferred_viewport():
    set_mode_calls = []
    set_icon_calls = []
    display = SimpleNamespace(
        Info=lambda: SimpleNamespace(current_w=1920, current_h=1080),
        set_mode=lambda size, flags: set_mode_calls.append((size, flags)) or object(),
        set_caption=lambda title: None,
        set_icon=lambda surface: set_icon_calls.append(surface),
    )
    renderer = PygameRenderer()
    renderer.pg = SimpleNamespace(
        display=display,
        error=RuntimeError,
        RESIZABLE=1,
        Surface=lambda size: object(),
        font=SimpleNamespace(SysFont=lambda name, size: object()),
        image=SimpleNamespace(load=lambda path: path),
    )
    renderer.grid_cols, renderer.grid_rows = 32, 16

    renderer._configure_window()

    assert renderer._display_safe_bounds == (1728, 972)
    assert renderer.scale == 30
    # Beta1 Phase 4: the window is the arena (960x480, unchanged) plus the
    # fixed-height top HUD and footer bands (100 + 60 = 160px) -- see
    # hud_layout.TOP_BAND_HEIGHT/FOOTER_HEIGHT.
    assert set_mode_calls == [((960, 640), 1)]
    # The source checkout ships assets/branding/bytefray-icon.png, so this
    # runs for real (not mocked) -- see get_branding_icon_path.
    assert len(set_icon_calls) == 1


def test_display_bounds_are_captured_before_set_mode_and_reused():
    info_calls = []
    renderer = PygameRenderer()
    renderer.pg = SimpleNamespace(
        display=SimpleNamespace(
            Info=lambda: info_calls.append(None)
            or SimpleNamespace(current_w=1920, current_h=1080)
        ),
        error=RuntimeError,
    )

    assert renderer._display_bounds() == (1728, 972)
    assert renderer._display_bounds() == (1728, 972)
    assert len(info_calls) == 1


def test_fit_to_display_can_enlarge_and_shrink(monkeypatch):
    renderer = PygameRenderer()
    renderer.pg = _display_stub(1920, 1080)
    renderer.grid_cols, renderer.grid_rows = 32, 16
    resize_calls = []
    monkeypatch.setattr(renderer, "_resize_window", lambda: resize_calls.append(renderer.scale))

    # Beta1 Phase 4: the display-safe bounds (1728, 972) are reduced by the
    # fixed top HUD/footer band heights (160px) before scale-fitting, so
    # the arena's own fit scale is 50 here, not the pre-Phase-4 54 (which
    # fit the *whole* display, arena included, to the grid).
    renderer.scale = 4
    renderer._fit_to_display()
    assert renderer.scale == 50

    renderer.scale = 100
    renderer._fit_to_display()
    assert renderer.scale == 50
    assert resize_calls == [50, 50]


def test_manual_rescale_moves_one_step_and_respects_display_limit(monkeypatch):
    renderer = PygameRenderer()
    renderer.pg = _display_stub(1920, 1080)
    renderer.grid_cols, renderer.grid_rows = 32, 16
    resize_calls = []
    monkeypatch.setattr(renderer, "_resize_window", lambda: resize_calls.append(renderer.scale))

    renderer.scale = 30
    renderer._rescale(1)
    renderer._rescale(-1)
    assert resize_calls == [31, 30]

    # 50 is the arena's own display-safe limit here (see
    # test_fit_to_display_can_enlarge_and_shrink) -- already at it, so one
    # more +1 step clamps rather than moves.
    renderer.scale = 50
    renderer._rescale(1)
    assert renderer.scale == 50
    assert resize_calls == [31, 30]


def test_ordinary_resize_preserves_requested_outer_dimensions():
    set_mode_calls = []
    renderer = PygameRenderer()
    renderer.pg = SimpleNamespace(
        display=SimpleNamespace(
            set_mode=lambda size, flags: set_mode_calls.append((size, flags))
            or _FakeSurface(size),
            set_caption=lambda title: None,
        ),
        RESIZABLE=1,
    )
    renderer.grid_cols, renderer.grid_rows = 32, 16
    renderer._entrant_count = 4

    renderer._handle_window_resize((777, 555))

    assert set_mode_calls == [((777, 555), 1)]
    assert renderer.screen.get_size() == (777, 555)
    assert renderer._layout.window_size == (777, 555)
    assert renderer._layout.arena_scale == renderer.scale
    assert renderer._layout.arena_rect[2] == 32 * renderer.scale
    assert renderer._layout.arena_rect[3] == 16 * renderer.scale


def test_below_supported_minimum_resize_is_honored_and_bounded():
    renderer = PygameRenderer()
    renderer.pg = SimpleNamespace(
        display=SimpleNamespace(
            set_mode=lambda size, flags: _FakeSurface(size),
            set_caption=lambda title: None,
        ),
        RESIZABLE=1,
    )
    renderer.grid_cols, renderer.grid_rows = 64, 64
    renderer._entrant_count = 8

    renderer._handle_window_resize((420, 300))

    assert renderer.screen.get_size() == (420, 300)
    assert renderer._layout.window_size == (420, 300)
    ax, ay, aw, ah = renderer._layout.arena_rect
    assert 0 <= ax and ax + aw <= 420
    assert 0 <= ay and ay + ah <= 300


def test_manual_scale_window_uses_supported_minimum_and_responsive_chrome():
    renderer = PygameRenderer()
    renderer.grid_cols, renderer.grid_rows = 32, 16
    renderer._entrant_count = 4

    assert renderer._window_size_for_scale(4) == (640, 480)
    width, height = renderer._window_size_for_scale(30)
    assert width == 960
    assert height > 16 * 30  # responsive top HUD + footer are outside arena


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
# Beta1 Phase 4: PygameRenderer._draw_top_band / _draw_footer integration.
#
# These exercise the *actual* renderer methods (not a hand-rolled
# reimplementation) end to end, through the real Phase-3 status model
# (get_entrant_statuses), using minimal fakes for the low-level Pygame
# primitives (Surface/font/draw) -- the same "mock the display, drive the
# real code" convention this file already established for window sizing
# (_display_stub) and cell selection (_FakeScreen), and the governing
# task's own explicit preference for geometry/formatting-level testing over
# pixel-perfect screenshot testing (see docs/V2_0_BETA1_PHASE4_REPLAY_HUD.md).
# ---------------------------------------------------------------------------
class _FakeSurface:
    def __init__(self, size=(0, 0)):
        self._size = size

    def fill(self, color):
        pass

    def blit(self, source, pos):
        pass

    def get_size(self):
        return self._size

    def get_width(self):
        return self._size[0]

    def get_height(self):
        return self._size[1]

    def get_rect(self):
        return (0, 0, *self._size)


class _FakeFont:
    """Records every string it was asked to render, so a test can assert on
    HUD *content* without needing real glyph rasterization.
    """

    def __init__(self):
        self.rendered: list[str] = []

    def render(self, text, antialias, color):
        self.rendered.append(text)
        return _FakeSurface((len(text) * 7, 13))


class _FakeDraw:
    def rect(self, surface, color, rect, width=0):
        pass

    def line(self, surface, color, start, end):
        pass

    def lines(self, surface, color, closed, points, width=1):
        pass

    def circle(self, surface, color, center, radius, width=0):
        pass


class _FakePygame:
    def __init__(self):
        self.draw = _FakeDraw()
        self.SRCALPHA = 1

    def Surface(self, size, flags=0):
        return _FakeSurface(size)

    def Rect(self, x, y, w, h):
        return (x, y, w, h)


def _band_renderer(window_size, entrant_count, *, arena_size=32):
    renderer = PygameRenderer()
    renderer.pg = _FakePygame()
    renderer.screen = _FakeSurface(window_size)
    renderer.hud_font = _FakeFont()
    renderer.font = _FakeFont()
    renderer.arena = arena_size
    renderer.grid_cols, renderer.grid_rows = renderer._resolve_grid_dims(arena_size)
    renderer._entrant_count = entrant_count
    renderer._layout = calculate_layout(
        window_size,
        entrant_count,
        (renderer.grid_cols, renderer.grid_rows),
    )
    return renderer


def _core_seed_diff(agent_id, start, arena_size):
    """Tick-0 ``MemoryDiff`` record(s) a real ``seed_core_ownership`` call
    would produce for one entrant -- mirrors ``test_replay_status.py``'s
    own helper of the same purpose (duplicated per that module's own
    documented convention of not sharing fixtures across test files).
    """
    from battle_engine.python_runtime import CORE_BEACON_BYTE, core_addresses

    addresses = core_addresses(start, arena_size)
    runs: list[tuple[int, int]] = []
    for address in addresses:
        if runs and runs[-1][0] + runs[-1][1] == address:
            runs[-1] = (runs[-1][0], runs[-1][1] + 1)
        else:
            runs.append((address, 1))
    return tuple(
        MemoryDiff(address=a, length=length, owner=agent_id, values=(CORE_BEACON_BYTE,) * length)
        for a, length in runs
    )


def _v2_header(entrants, *, arena_size):
    from battle_engine.ruleset_policy import BYTEFRAY_RULESET_V2_ID

    return ReplayHeader(
        MatchConfiguration(arena_size=arena_size),
        {agent_id: agent_id.title() for agent_id in entrants},
        runtime_kind="python",
        ruleset_id=BYTEFRAY_RULESET_V2_ID,
        entrants=tuple({"agent_id": a, "name": a.title()} for a in entrants),
    )


def _load(tmp_path, name, records):
    path = tmp_path / name
    write_replay(path, records)
    session = ReplaySession()
    session.load(path)
    return session


def _v2_two_entrant_session(tmp_path, *, unattributed=False):
    """A- and B-owned non-overlapping cores (arena 32: A at 0, B at 16).
    Tick 0: both healthy. Tick 1: B damages 3 of A's cells. Tick 2: B takes
    A's remaining 5 cells -- A's core reaches 0/8 and is captured.
    """
    header = _v2_header(("A", "B"), arena_size=32)
    tick0 = TickSnapshot(
        0,
        agents=(_agent("A"), _agent("B")),
        score={"A": 10, "B": 5},
        memory_diffs=_core_seed_diff("A", 0, 32) + _core_seed_diff("B", 16, 32),
    )
    tick1 = TickSnapshot(
        1,
        agents=(_agent("A"), _agent("B")),
        score={"A": 10, "B": 5},
        memory_diffs=(MemoryDiff(address=0, length=3, owner="B", values=(9, 9, 9)),),
    )
    killer = None if unattributed else "B"
    event = KillDeathEvent("death" if unattributed else "kill", "A", killer)
    tick2 = TickSnapshot(
        2,
        agents=(
            AgentState(agent_id="A", pc=0, alive=False, termination_reason="core_captured"),
            _agent("B"),
        ),
        score={"A": 10, "B": 8},
        memory_diffs=(MemoryDiff(address=3, length=5, owner="B", values=(9, 9, 9, 9, 9)),),
        events=(event,),
    )
    name = "v2_unattributed.jsonl" if unattributed else "v2_capture.jsonl"
    return _load(tmp_path, name, [header, tick0, tick1, tick2])


def _v2_three_entrant_session(tmp_path):
    """Three non-overlapping healthy cores in a 48-cell arena."""
    header = _v2_header(("A", "B", "C"), arena_size=48)
    tick0 = TickSnapshot(
        0,
        agents=(_agent("A"), _agent("B"), _agent("C")),
        score={"A": 1, "B": 2, "C": 3},
        memory_diffs=(
            _core_seed_diff("A", 0, 48) + _core_seed_diff("B", 16, 48) + _core_seed_diff("C", 32, 48)
        ),
    )
    return _load(tmp_path, "v2_three_entrant.jsonl", [header, tick0])


def _many_entrant_session(tmp_path, entrant_count=6):
    entrants = tuple(chr(ord("A") + index) for index in range(entrant_count))
    header = ReplayHeader(
        MatchConfiguration(arena_size=64),
        {agent_id: f"entrant-{agent_id.lower()}" for agent_id in entrants},
        runtime_kind="vm",
    )
    tick0 = TickSnapshot(
        0,
        agents=tuple(_agent(agent_id, pc=index) for index, agent_id in enumerate(entrants)),
        score={agent_id: index for index, agent_id in enumerate(entrants)},
    )
    return _load(tmp_path, "many_entrants.jsonl", [header, tick0])


def test_top_band_renders_v1_entrants_with_no_core_field(tmp_path):
    session = _no_events_session(tmp_path)
    controller = PlaybackController(session, playing=False)
    renderer = _band_renderer((960, 700), entrant_count=1, arena_size=8)
    renderer._match_events = []
    renderer._ruleset_label = "bytefray-rules-1"

    renderer._draw_top_band(controller)  # must not raise

    rendered = "\n".join(renderer.hud_font.rendered)
    assert "Alive" in rendered
    assert "Core" not in rendered


def test_top_band_renders_v2_healthy_and_damaged_core(tmp_path):
    session = _v2_two_entrant_session(tmp_path)
    controller = PlaybackController(session, playing=False)
    renderer = _band_renderer((960, 700), entrant_count=2, arena_size=32)
    renderer._match_events = collect_match_events(session)
    renderer._ruleset_label = "bytefray-rules-2"

    renderer._draw_top_band(controller)
    rendered = "\n".join(renderer.hud_font.rendered)
    assert "Core 8/8" in rendered  # B, healthy

    session.step_forward()  # tick 1: A damaged to 5/8
    renderer.hud_font = _FakeFont()
    renderer._draw_top_band(controller)
    rendered = "\n".join(renderer.hud_font.rendered)
    assert "Core 5/8" in rendered


def test_top_band_renders_v2_capture_with_attribution(tmp_path):
    session = _v2_two_entrant_session(tmp_path)
    while not session.at_end:
        session.step_forward()
    controller = PlaybackController(session, playing=False)
    renderer = _band_renderer((960, 700), entrant_count=2, arena_size=32)
    renderer._match_events = collect_match_events(session)
    renderer._ruleset_label = "bytefray-rules-2"

    renderer._draw_top_band(controller)

    rendered = "\n".join(renderer.hud_font.rendered)
    assert "CAPTURED" in rendered
    assert "Core 0/8" in rendered
    assert "by B" in rendered


def test_top_band_unattributed_capture_shows_no_fake_killer(tmp_path):
    session = _v2_two_entrant_session(tmp_path, unattributed=True)
    while not session.at_end:
        session.step_forward()
    controller = PlaybackController(session, playing=False)
    renderer = _band_renderer((960, 700), entrant_count=2, arena_size=32)
    renderer._match_events = collect_match_events(session)
    renderer._ruleset_label = "bytefray-rules-2"

    renderer._draw_top_band(controller)

    rendered = "\n".join(renderer.hud_font.rendered)
    assert "CAPTURED" in rendered
    assert " by " not in rendered


def test_top_band_renders_three_entrants_all_represented(tmp_path):
    session = _v2_three_entrant_session(tmp_path)
    controller = PlaybackController(session, playing=False)
    renderer = _band_renderer((960, 700), entrant_count=3, arena_size=48)
    renderer._match_events = collect_match_events(session)
    renderer._ruleset_label = "bytefray-rules-2"

    renderer._draw_top_band(controller)

    rendered = "\n".join(renderer.hud_font.rendered)
    assert "A" in rendered and "B" in rendered and "C" in rendered
    assert rendered.count("Core 8/8") == 3


def test_top_band_renders_compact_high_entrant_roster_with_text_badges(tmp_path):
    session = _many_entrant_session(tmp_path, entrant_count=6)
    controller = PlaybackController(session, playing=False)
    renderer = _band_renderer((640, 480), entrant_count=6, arena_size=64)
    renderer._match_events = []
    renderer._ruleset_label = "bytefray-rules-1"

    assert renderer._layout.card_mode == "compact"
    renderer._draw_top_band(controller)

    rendered = "\n".join(renderer.hud_font.rendered)
    for ordinal, agent_id in enumerate("ABCDEF", start=1):
        assert f"#{ordinal} {agent_id}" in rendered
    assert rendered.count("Alive") == 6


def test_top_band_emphasizes_authoritative_terminal_result(tmp_path):
    session = _events_session(tmp_path)
    controller = PlaybackController(session, playing=False)
    renderer = _band_renderer((640, 480), entrant_count=3, arena_size=10)
    renderer._match_events = collect_match_events(session)
    renderer._ruleset_label = "bytefray-rules-1"

    renderer._draw_top_band(controller)

    rendered = "\n".join(renderer.hud_font.rendered)
    assert "MATCH COMPLETE" in rendered
    assert "Winner: A" in rendered
    assert "last agent standing" in rendered


@pytest.mark.parametrize(
    "build_session",
    [
        _events_session,
        _python_session,
        _python_forfeit_session,
        _v2_two_entrant_session,
        _v2_three_entrant_session,
    ],
)
def test_bands_render_without_crashing_for_every_replay_kind(tmp_path, build_session):
    session = build_session(tmp_path)
    controller = PlaybackController(session, playing=False)
    entrant_count = len(get_entrant_statuses(session, match_events=()))
    renderer = _band_renderer((960, 700), entrant_count=entrant_count, arena_size=session.header.config.arena_size)
    renderer._match_events = collect_match_events(session)
    renderer._ruleset_label = "unknown"

    renderer._draw_top_band(controller)
    renderer._draw_footer(controller)  # must not raise


def test_footer_shows_tick_playback_and_controls(tmp_path):
    session = _no_events_session(tmp_path)
    controller = PlaybackController(session, playing=False)
    renderer = _band_renderer((960, 700), entrant_count=1, arena_size=8)
    renderer._match_events = []

    renderer._draw_footer(controller)

    rendered = "\n".join(renderer.hud_font.rendered)
    assert "Tick 0" in rendered
    assert "PAUSED" in rendered
    # The controls line is deterministically truncated to the footer's own
    # text column width (Phase 4H) rather than rendered at full length, so
    # only its (stable) prefix is guaranteed present -- see
    # test_footer_controls_line_truncates_to_its_column_width below for the
    # truncation behavior itself.
    assert HELP_TEXT.split("  ")[0] in rendered


def test_compact_footer_help_fits_its_column_without_truncation(tmp_path):
    """Beta3's compact hint remains bounded without looking broken."""
    session = _no_events_session(tmp_path)
    controller = PlaybackController(session, playing=False)
    renderer = _band_renderer((960, 700), entrant_count=1, arena_size=8)
    renderer._match_events = []

    renderer._draw_footer(controller)

    controls_rendered = renderer.hud_font.rendered[-1]
    _tx, _ty, tw, _th = renderer._layout.footer_text_rect
    assert len(controls_rendered) <= max(6, tw // HUD_CHAR_WIDTH_PX)
    assert controls_rendered == HELP_TEXT
    assert not controls_rendered.endswith("…")


def test_expanded_help_replaces_event_and_graph_without_covering_arena(tmp_path, monkeypatch):
    session = _events_session(tmp_path)
    controller = PlaybackController(session, playing=False)
    renderer = _band_renderer((640, 480), entrant_count=3, arena_size=10)
    renderer._match_events = collect_match_events(session)
    renderer.help_visible = True
    graph_rects = []
    monkeypatch.setattr(
        renderer,
        "_draw_footer_graph",
        lambda state, rect: graph_rects.append(rect),
    )

    renderer._draw_footer(controller)

    rendered = "\n".join(renderer.hud_font.rendered)
    assert "Home/End first/last" in rendered
    assert "? close" in rendered
    assert renderer._event_panel_ticks == ()
    assert graph_rects == [(0, 0, 0, 0)]
    assert not any(line.endswith("…") for line in renderer.hud_font.rendered[-2:])


def test_footer_shows_most_recent_event_and_is_clickable(tmp_path):
    session = _events_session(tmp_path)
    while not session.at_end:
        session.step_forward()
    controller = PlaybackController(session, playing=False)
    renderer = _band_renderer((960, 700), entrant_count=3, arena_size=10)
    renderer._match_events = collect_match_events(session)

    renderer._draw_footer(controller)

    rendered = "\n".join(renderer.hud_font.rendered)
    assert "T004 death: C" in rendered  # most recent of the two events
    assert renderer._event_panel_ticks == (4,)
    assert renderer._event_panel_origin is not None


def test_footer_shows_idle_message_when_no_events(tmp_path):
    session = _no_events_session(tmp_path)
    controller = PlaybackController(session, playing=False)
    renderer = _band_renderer((960, 700), entrant_count=1, arena_size=8)
    renderer._match_events = []

    renderer._draw_footer(controller)

    rendered = "\n".join(renderer.hud_font.rendered)
    assert "No recent events" in rendered
    assert renderer._event_panel_ticks == ()


def test_footer_shows_selected_cell_instead_of_event_when_selected(tmp_path):
    session = _events_session(tmp_path)
    while not session.at_end:
        session.step_forward()
    controller = PlaybackController(session, playing=False)
    renderer = _band_renderer((960, 700), entrant_count=3, arena_size=10)
    renderer._match_events = collect_match_events(session)
    renderer._selected_address = 0

    renderer._draw_footer(controller)

    rendered = "\n".join(renderer.hud_font.rendered)
    assert "Selected cell:" in rendered
    assert "addr=0" in rendered
    # The selected-cell readout takes the message slot, so it is not
    # click-to-seek like an event line.
    assert renderer._event_panel_ticks == ()


# ---------------------------------------------------------------------------
# Beta1 Phase 4: _handle_click is arena-rect aware once a layout exists.
# ---------------------------------------------------------------------------
def test_handle_click_translates_into_arena_local_coordinates(tmp_path):
    session = _events_session(tmp_path)
    controller = PlaybackController(session, playing=False)
    renderer = _band_renderer((960, 700), entrant_count=2, arena_size=10)

    ax, ay, _aw, _ah = renderer._layout.arena_rect
    # A click a few pixels inside the arena band's top-left corner should
    # resolve to arena address 0, even though the arena no longer starts at
    # window (0, 0) -- see hud_layout.TOP_BAND_HEIGHT.
    renderer._handle_click(controller, (ax + 1, ay + 1))

    assert renderer._selected_address == 0


def test_handle_click_above_the_arena_band_does_not_select_a_cell(tmp_path):
    session = _events_session(tmp_path)
    controller = PlaybackController(session, playing=False)
    renderer = _band_renderer((960, 700), entrant_count=2, arena_size=10)
    renderer._selected_address = 5

    renderer._handle_click(controller, (10, 10))  # inside the top HUD band

    assert renderer._selected_address == 5  # unchanged


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
