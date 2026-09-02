from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from battle_client.perspective import (
    BROADCAST_MODE,
    KnowledgeStatus,
    PerspectiveManager,
)
from battle_client.renderers.pygame_renderer import dispatch_key
from battle_engine.agents import resolve_agent
from battle_engine.config import Config, Weights
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.ruleset_policy import RULESET_V4_ALPHA1
from battle_engine.spectator_perspective import (
    analyze_perspective,
)

_IMPORTS = (
    "from battle_engine.agent_api import AgentV2, ObservationV2, AgentAction, "
    "ActionKindV2, MatchContextV2, ProcessDeclaration\n"
)

ANVIL = (
    _IMPORTS
    + """
class Anvil:
    api_version = 2
    def declare_processes(self):
        return [ProcessDeclaration(id="body", reach=2, share=1.0)]
    def reset(self, context: MatchContextV2):
        pass
    def act(self, obs: ObservationV2) -> AgentAction:
        return AgentAction(ActionKindV2.WRITE, obs.own_core_base, 0xCE)
def create_agent() -> AgentV2:
    return Anvil()
"""
)

HUNTER = (
    _IMPORTS
    + """
class Hunter:
    api_version = 2
    def declare_processes(self):
        return [ProcessDeclaration(id="eye", reach=10, share=1.0)]
    def reset(self, context: MatchContextV2):
        pass
    def act(self, obs: ObservationV2) -> AgentAction:
        if obs.visible_enemy_anchor_addresses:
            target = obs.visible_enemy_anchor_addresses[0]
            if obs.current_tick % 2 == 0:
                return AgentAction(ActionKindV2.READ, target)
            return AgentAction(ActionKindV2.WRITE, target, 0x5A)
        return AgentAction(ActionKindV2.MOVE, 4)
def create_agent() -> AgentV2:
    return Hunter()
"""
)

COLOCATOR = (
    _IMPORTS
    + """
class Colocator:
    api_version = 2
    def declare_processes(self):
        return [
            ProcessDeclaration(id="m1", reach=4, share=0.5),
            ProcessDeclaration(id="m2", reach=4, share=0.5),
        ]
    def reset(self, context: MatchContextV2):
        pass
    def act(self, obs: ObservationV2) -> AgentAction:
        return AgentAction(ActionKindV2.READ, obs.own_core_base)
def create_agent() -> AgentV2:
    return Colocator()
"""
)


def _write_agent(root: Path, name: str, source: str) -> None:
    directory = root / "agents" / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "agent.py").write_text(source, encoding="utf-8")
    (directory / "agent.yaml").write_text(
        f"name: {name}\ndescription: Phase 5 fixture\nversion: '1.0'\napi_version: 2\n",
        encoding="utf-8",
    )


def _duel(root: Path, label: str = "duel", *, seed: int = 11):
    _write_agent(root, "hunter", HUNTER)
    _write_agent(root, "anvil", ANVIL)
    run = root / label
    run.mkdir(parents=True, exist_ok=True)
    replay_path = run / "replay.jsonl"
    trace_path = run / "trace.jsonl"
    request = MatchRequest(
        config=Config(
            seed=seed,
            arena_size=64,
            instr_per_tick=8,
            win_mode="capture",
            weights=Weights(),
        ),
        entrants=(
            MatchEntrant.python("A", "hunter", 0, resolve_agent(root, "hunter")),
            MatchEntrant.python("B", "anvil", 32, resolve_agent(root, "anvil")),
        ),
        max_ticks=12,
        replay_path=replay_path,
        trace_path=trace_path,
        ruleset_id=RULESET_V4_ALPHA1.ruleset_id,
    )
    result = NativeMatchService().run(request)
    return replay_path, trace_path, result


def test_perspective_manager_broadcast_fallback_on_missing_trace(tmp_path: Path) -> None:
    replay_path, _trace_path, _result = _duel(tmp_path, "missing_trace")
    # 1. No trace supplied
    mgr = PerspectiveManager(replay_path, None)
    assert not mgr.available
    assert mgr.mode == BROADCAST_MODE
    assert mgr.entrants == ()
    assert mgr.state_at_tick(0) is None
    assert "no trace supplied" in mgr.status_message.lower()

    # 2. Non-existent trace supplied
    mgr_missing = PerspectiveManager(replay_path, tmp_path / "nonexistent.jsonl")
    assert not mgr_missing.available
    assert mgr_missing.mode == BROADCAST_MODE
    assert "not found" in mgr_missing.status_message.lower()


def test_perspective_manager_lifecycle_and_mode_cycling(tmp_path: Path) -> None:
    replay_path, trace_path, _result = _duel(tmp_path, "lifecycle_duel")
    assert trace_path is not None
    mgr = PerspectiveManager(replay_path, trace_path)
    assert mgr.available
    assert mgr.mode == BROADCAST_MODE
    assert set(mgr.entrants) == {"A", "B"}

    # Cycle: broadcast -> A -> B -> broadcast
    assert mgr.cycle_mode() == "A"
    assert mgr.mode == "A"
    state_a = mgr.state_at_tick(1)
    assert state_a is not None
    assert state_a.entrant_id == "A"

    assert mgr.cycle_mode() == "B"
    assert mgr.mode == "B"
    state_b = mgr.state_at_tick(1)
    assert state_b is not None
    assert state_b.entrant_id == "B"

    assert mgr.cycle_mode() == BROADCAST_MODE
    assert mgr.mode == BROADCAST_MODE
    assert mgr.state_at_tick(1) is None

    # Set valid and invalid mode
    assert mgr.set_mode("A")
    assert mgr.mode == "A"
    assert not mgr.set_mode("INVALID_ENTRANT")
    assert mgr.mode == "A"


def test_negative_target_entrant_id_leakage_prohibited(tmp_path: Path) -> None:
    """Explicitly verify that no entrant knowledge structure contains or leaks target entrant id."""
    replay_path, trace_path, _result = _duel(tmp_path, "leakage_test")
    assert trace_path is not None
    mgr = PerspectiveManager(replay_path, trace_path)
    assert mgr.set_mode("A")

    for tick in range(5):
        state = mgr.state_at_tick(tick)
        assert state is not None
        for contact in state.current_contacts:
            assert not hasattr(contact, "target_entrant_id")
            assert not hasattr(contact, "entrant_id")
            assert not hasattr(contact, "process_id")
            assert not hasattr(contact, "track_id")
            assert isinstance(contact.address, int)
            assert contact.status is KnowledgeStatus.CURRENT
        for contact in state.stale_contacts:
            assert not hasattr(contact, "target_entrant_id")
            assert not hasattr(contact, "entrant_id")
            assert not hasattr(contact, "process_id")
            assert not hasattr(contact, "track_id")
            assert isinstance(contact.address, int)
            assert contact.status is KnowledgeStatus.STALE


def test_colocation_ambiguity_and_geometry_trap(tmp_path: Path) -> None:
    """Verify co-located enemy processes fold into one anonymous contact without ID leakage."""
    _write_agent(tmp_path, "hunter", HUNTER)
    _write_agent(tmp_path, "coloc", COLOCATOR)
    run = tmp_path / "coloc_run"
    run.mkdir(parents=True, exist_ok=True)
    replay_path = run / "replay.jsonl"
    trace_path = run / "trace.jsonl"
    request = MatchRequest(
        config=Config(seed=11, arena_size=64, instr_per_tick=8, win_mode="capture", weights=Weights()),
        entrants=(
            MatchEntrant.python("A", "hunter", 0, resolve_agent(tmp_path, "hunter")),
            MatchEntrant.python("B", "coloc", 32, resolve_agent(tmp_path, "coloc")),
        ),
        max_ticks=8,
        replay_path=replay_path,
        trace_path=trace_path,
        ruleset_id=RULESET_V4_ALPHA1.ruleset_id,
    )
    NativeMatchService().run(request)

    projection = analyze_perspective(replay_path, trace_path, "A")
    for tick in range(projection.first_tick, projection.result_ticks + 1):
        state = projection.state_at_tick(tick)
        addresses = [c.address for c in state.current_contacts]
        assert len(addresses) == len(set(addresses))
        for addr in addresses:
            assert 0 <= addr < projection.arena_size


def test_read_owner_separated_from_spatial_contact(tmp_path: Path) -> None:
    """Verify that cell owner from a delivered READ is not conflated with spatial contact identity."""
    replay_path, trace_path, _result = _duel(tmp_path, "read_duel")
    assert trace_path is not None
    mgr = PerspectiveManager(replay_path, trace_path, initial_mode="A")
    state = mgr.state_at_tick(3)
    assert state is not None
    for read in state.read_history:
        assert isinstance(read.applied, bool)
        if read.applied:
            assert read.normalized_address is not None
            assert isinstance(read.owner, (str, type(None)))


def test_stale_contact_transition_and_age(tmp_path: Path) -> None:
    """Verify CURRENT contacts transition to STALE with preserved last observed point and age."""
    replay_path, trace_path, _result = _duel(tmp_path, "stale_duel")
    assert trace_path is not None
    projection = analyze_perspective(replay_path, trace_path, "A")
    cursor = projection.cursor()

    for tick in range(projection.first_tick, projection.result_ticks + 1):
        state = cursor.state_at_tick(tick)
        for stale in state.stale_contacts:
            assert stale.status == KnowledgeStatus.STALE
            assert stale.last_observed_at is not None
            age = state.tick - stale.last_observed_at.tick
            assert age >= 0
            if stale.became_stale_at is not None:
                assert stale.became_stale_at.tick <= state.tick


def test_no_callback_interval_preserves_state(tmp_path: Path) -> None:
    """Verify no-callback ticks preserve last delivered state and indicate unsampled."""
    replay_path, trace_path, _result = _duel(tmp_path, "unsampled_duel")
    assert trace_path is not None
    mgr = PerspectiveManager(replay_path, trace_path, initial_mode="A")
    for tick in range(5):
        state = mgr.state_at_tick(tick)
        assert state is not None
        assert isinstance(state.sampled_this_tick, bool)
        for proc in state.own_processes:
            assert proc.process_id == "eye"


def test_perspective_cam_keyboard_dispatch() -> None:
    """Verify keyboard dispatch for perspective controls (V, P, 1-9, F3, D)."""
    pg_mock = SimpleNamespace(
        KMOD_SHIFT=1,
        K_ESCAPE=27,
        K_q=113,
        K_SPACE=32,
        K_RIGHT=275,
        K_LEFT=276,
        K_HOME=278,
        K_END=279,
        K_PLUS=43,
        K_EQUALS=61,
        K_PAGEUP=280,
        K_MINUS=45,
        K_UNDERSCORE=95,
        K_PAGEDOWN=281,
        K_LEFTBRACKET=91,
        K_RIGHTBRACKET=93,
        K_t=116,
        K_v=118,
        K_p=112,
        K_d=100,
        K_F3=284,
        K_1=49,
        K_2=50,
        K_3=51,
        K_4=52,
        K_0=48,
    )
    ctrl_mock = SimpleNamespace(
        toggle_play_pause=lambda: None,
        seek_relative=lambda n: None,
        step_forward=lambda: None,
        step_backward=lambda: None,
        restart=lambda: None,
        jump_to_end=lambda: None,
        speed_up=lambda: None,
        speed_down=lambda: None,
    )

    action_v = dispatch_key(pg_mock, pg_mock.K_v, 0, ctrl_mock)
    assert action_v.cycle_perspective

    action_p = dispatch_key(pg_mock, pg_mock.K_p, 0, ctrl_mock)
    assert action_p.cycle_perspective

    action_f3 = dispatch_key(pg_mock, pg_mock.K_F3, 0, ctrl_mock)
    assert action_f3.toggle_perspective_debug

    action_d = dispatch_key(pg_mock, pg_mock.K_d, 0, ctrl_mock)
    assert action_d.toggle_perspective_debug

    action_1 = dispatch_key(pg_mock, pg_mock.K_1, 0, ctrl_mock)
    assert action_1.select_perspective_index == 0  # Broadcast

    action_2 = dispatch_key(pg_mock, pg_mock.K_2, 0, ctrl_mock)
    assert action_2.select_perspective_index == 1  # Entrant 1

    action_3 = dispatch_key(pg_mock, pg_mock.K_3, 0, ctrl_mock)
    assert action_3.select_perspective_index == 2  # Entrant 2

class _RecordingSurface:
    """Minimal surface that records which grid pixels were painted."""

    def __init__(self, size=(0, 0)):
        self._size = size
        self.painted: dict[tuple[int, int], tuple[int, int, int]] = {}

    def fill(self, color):
        self.painted.clear()

    def set_at(self, xy, color):
        self.painted[xy] = color

    def get_at(self, xy):
        return self.painted.get(xy, (0, 0, 0))

    def blit(self, source, pos):
        pass

    def get_size(self):
        return self._size

    def get_width(self):
        return self._size[0]

    def get_height(self):
        return self._size[1]

    def get_rect(self, **kwargs):
        return (0, 0, *self._size)


class _NullDraw:
    def line(self, *a, **k):
        pass

    def circle(self, *a, **k):
        pass

    def rect(self, *a, **k):
        pass


class _NullTransform:
    def scale(self, surface, size):
        return surface


class _FakePygame:
    def __init__(self):
        self.draw = _NullDraw()
        self.transform = _NullTransform()
        self.SRCALPHA = 1

    def Surface(self, size, flags=0):
        return _RecordingSurface(size)

    def Rect(self, x, y, w, h):
        return (x, y, w, h)


def _blind_duel(root: Path, label: str = "blind"):
    """Two entrants whose reach never covers the other: A can never see B.

    Canonical replay still holds B's process anchor and owned core cells, so
    this is the geometry trap at the *rendering* layer -- Perspective Cam must
    paint nothing derived from B.
    """

    _write_agent(root, "anvil_a", ANVIL)
    _write_agent(root, "anvil_b", ANVIL)
    run = root / label
    run.mkdir(parents=True, exist_ok=True)
    replay_path = run / "replay.jsonl"
    trace_path = run / "trace.jsonl"
    NativeMatchService().run(
        MatchRequest(
            config=Config(
                seed=11, arena_size=64, instr_per_tick=8, win_mode="capture", weights=Weights()
            ),
            entrants=(
                MatchEntrant.python("A", "anvil_a", 0, resolve_agent(root, "anvil_a")),
                MatchEntrant.python("B", "anvil_b", 32, resolve_agent(root, "anvil_b")),
            ),
            max_ticks=6,
            replay_path=replay_path,
            trace_path=trace_path,
            ruleset_id=RULESET_V4_ALPHA1.ruleset_id,
        )
    )
    return replay_path, trace_path


def _instrumented_renderer(arena_size: int):
    """A renderer wired to fakes, with every non-grid band stubbed out."""

    from battle_client.hud_layout import calculate_layout
    from battle_client.renderers.pygame_renderer import PygameRenderer

    renderer = PygameRenderer()
    renderer.pg = _FakePygame()
    renderer.screen = _RecordingSurface((960, 700))
    renderer.grid_surf = _RecordingSurface((arena_size, arena_size))
    renderer.hud_font = SimpleNamespace(render=lambda *a, **k: _RecordingSurface((1, 1)))
    renderer.font = renderer.hud_font
    renderer.arena = arena_size
    renderer.grid_cols, renderer.grid_rows = renderer._resolve_grid_dims(arena_size)
    renderer._entrant_count = 2
    renderer._layout = calculate_layout(
        (960, 700), 2, (renderer.grid_cols, renderer.grid_rows)
    )
    renderer.grid_surf = _RecordingSurface((renderer.grid_cols, renderer.grid_rows))

    calls: dict[str, list] = {"agent": [], "anchor": [], "contact": [], "reach": []}
    renderer._draw_agent_marker = lambda *a, **k: calls["agent"].append(a)
    renderer._draw_process_anchor = lambda *a, **k: calls["anchor"].append(a)
    renderer._draw_perspective_contact = lambda *a, **k: calls["contact"].append(a)
    renderer._draw_sensor_reach = lambda *a, **k: calls["reach"].append(a)
    renderer._draw_selection_highlight = lambda *a, **k: None
    renderer._draw_top_band = lambda *a, **k: ()
    renderer._draw_capture_callout = lambda *a, **k: None
    renderer._draw_footer = lambda *a, **k: None
    return renderer, calls


def test_renderer_perspective_grid_never_paints_unobserved_enemy_geometry(
    tmp_path: Path,
) -> None:
    """The render path itself, not just PerspectiveState, must stay knowledge-limited.

    Drives the real grid renderer with a real ``PerspectiveManager`` over a
    real match in which entrant A never observes B.  Canonical replay knows
    exactly where B is; Perspective Cam must paint none of it, and must not
    fall back to replay entity coordinates for markers.
    """

    from battle_client.player import PlaybackController
    from battle_client.session import ReplaySession

    replay_path, trace_path = _blind_duel(tmp_path)
    session = ReplaySession()
    session.load(replay_path)
    controller = PlaybackController(session, playing=False)
    controller.seek_relative(3)
    state = session.current_state

    manager = PerspectiveManager(replay_path, trace_path)
    assert manager.available, manager.status_message
    assert manager.set_mode("A")
    perspective = manager.state_at_tick(state.tick)
    assert perspective is not None
    assert perspective.current_contacts == ()
    assert perspective.stale_contacts == ()

    # Canonical replay really does place B in the arena at this tick; that is
    # exactly the knowledge Perspective Cam must refuse to render.
    canonical_b = {
        address for address, owner in enumerate(state.owners) if owner == "B"
    }
    assert canonical_b, "fixture must give B canonical owned cells"

    renderer, calls = _instrumented_renderer(64)
    renderer._perspective_manager = manager
    renderer._redraw(controller)

    xy_to_address = {
        renderer._to_xy(address): address for address in range(64)
        if renderer._to_xy(address) is not None
    }
    painted = {
        xy_to_address[xy] for xy in renderer.grid_surf.painted if xy in xy_to_address
    }
    assert painted.isdisjoint(canonical_b), (
        f"perspective grid painted B-owned canonical cells: {sorted(painted & canonical_b)}"
    )
    assert calls["agent"] == [], "omniscient VM markers must not render in perspective mode"
    assert calls["contact"] == [], "no contact was ever observed, so none may be drawn"
    assert all(anchor[0] == "A" for anchor in calls["anchor"]), calls["anchor"]

    # Control: the same renderer in broadcast mode *does* render B, proving the
    # assertions above would catch a genuine disclosure leak.
    renderer_b, calls_b = _instrumented_renderer(64)
    renderer_b._perspective_manager = None
    renderer_b._redraw(controller)
    painted_broadcast = {
        xy_to_address[xy] for xy in renderer_b.grid_surf.painted if xy in xy_to_address
    }
    assert painted_broadcast & canonical_b, "broadcast must still be omniscient"
    assert any(anchor[0] == "B" for anchor in calls_b["anchor"]), (
        "broadcast must still draw B's process anchors"
    )
