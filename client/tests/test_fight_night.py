"""Phase 8: client-side Fight Night manager, layout, and viewer integration.

Layout assertions here are deliberately made against the *real*
``calculate_layout`` output at concrete window sizes -- including the
documented 640x480 minimum with two, three and four entrants -- rather than
against hand-built rects, so a regression that changes the HUD's own band
geometry is caught here rather than only in a screenshot.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from battle_client.fight_night import (
    BROADCAST_MODE,
    FightNightManager,
    FightNightPhase,
)
from battle_client.hud_layout import (
    EXPANDED_HELP_LINES,
    FIGHT_NIGHT_LINE_HEIGHT,
    FIGHT_NIGHT_MIN_GUTTER_WIDTH,
    MIN_VIEWER_SIZE,
    calculate_layout,
    fight_night_card_rect,
    fight_night_ribbon_capacity,
    fight_night_ribbon_rect,
    format_fight_night_opening_lines,
    format_fight_night_result_lines,
    format_fight_night_ribbon_line,
    format_fight_night_ribbon_title,
)
from battle_client.renderers.pygame_renderer import HUD_CHAR_WIDTH_PX, dispatch_key
from battle_engine.agents import resolve_agent
from battle_engine.config import Config, Weights
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.ruleset_policy import RULESET_V4_ALPHA1
from battle_engine.spectator_derivation import analyze_pair

_IMPORTS = (
    "from battle_engine.agent_api import AgentV2, ObservationV2, AgentAction, "
    "ActionKindV2, MatchContextV2, ProcessDeclaration\n"
)

HERMIT = _IMPORTS + '''
class Hermit:
    api_version = 2
    def declare_processes(self):
        return [ProcessDeclaration(id="h", reach=1, share=1.0)]
    def reset(self, context: MatchContextV2):
        pass
    def act(self, obs: ObservationV2) -> AgentAction:
        return AgentAction(ActionKindV2.READ, obs.self_anchor)
def create_agent() -> AgentV2:
    return Hermit()
'''

HUNTER = _IMPORTS + '''
class Hunter:
    api_version = 2
    def declare_processes(self):
        return [ProcessDeclaration(id="hunt", reach=20, share=1.0)]
    def reset(self, context: MatchContextV2):
        self.target = None
        self.step = 0
    def act(self, obs: ObservationV2) -> AgentAction:
        if obs.visible_enemy_anchor_addresses:
            self.target = obs.visible_enemy_anchor_addresses[0]
        if self.target is None:
            return AgentAction(ActionKindV2.MOVE, 3)
        delta = self.target - obs.self_anchor
        if delta > 2:
            return AgentAction(ActionKindV2.MOVE, 2)
        if delta < -2:
            return AgentAction(ActionKindV2.MOVE, -2)
        self.step += 1
        return AgentAction(ActionKindV2.WRITE, self.target + (self.step % 8), 0x22)
def create_agent() -> AgentV2:
    return Hunter()
'''

_SOURCES = {"hermit": HERMIT, "hunter": HUNTER}

# A realistically long display name. Phase 6 attempted this stress case via
# `agent.yaml`'s `name:` field and found it did not reach the HUD (Phase 6
# research document Sec. 12/20 item 4); the replay header's entrant `name`
# comes from the `MatchEntrant` the caller constructs, which is what this
# fixture sets, so the long name genuinely reaches the presentation path.
LONG_NAME = "Recursive Perimeter Denial Construct MK-VII"


def _run(
    root: Path,
    label: str,
    entrants: tuple[tuple[str, str, str, int], ...],
    *,
    arena_size: int,
    max_ticks: int,
    seed: int,
) -> tuple[Path, Path]:
    for _entrant_id, _name, agent_name, _start in entrants:
        directory = root / "agents" / agent_name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "agent.py").write_text(_SOURCES[agent_name])
        (directory / "agent.yaml").write_text(
            f"name: {agent_name}\ndescription: Phase 8 fixture\n"
            "version: '1.0'\napi_version: 2\n"
        )
    run = root / label
    run.mkdir(parents=True, exist_ok=True)
    replay_path = run / "replay.jsonl"
    trace_path = run / "trace.jsonl"
    NativeMatchService().run(
        MatchRequest(
            config=Config(
                seed=seed,
                arena_size=arena_size,
                instr_per_tick=8,
                win_mode="capture",
                weights=Weights(),
            ),
            entrants=tuple(
                MatchEntrant.python(entrant_id, name, start, resolve_agent(root, agent_name))
                for entrant_id, name, agent_name, start in entrants
            ),
            max_ticks=max_ticks,
            replay_path=replay_path,
            trace_path=trace_path,
            ruleset_id=RULESET_V4_ALPHA1.ruleset_id,
        )
    )
    return replay_path, trace_path


def _four_entrant_manager(root: Path) -> tuple[FightNightManager, int, int]:
    """A four-entrant manager plus the match's (last_tick, result_ticks)."""

    replay_path, trace_path = _run(
        root,
        "fnc4",
        (
            ("A", "Entrant A", "hunter", 0),
            ("B", "Entrant B", "hermit", 30),
            ("C", "Entrant C", "hunter", 200),
            ("D", "Entrant D", "hermit", 230),
        ),
        arena_size=400,
        max_ticks=90,
        seed=31,
    )
    derivation = analyze_pair(replay_path, trace_path)
    return FightNightManager(derivation), derivation.last_tick, derivation.result_ticks


# ---------------------------------------------------------------------------
# 1. Manager availability and caching
# ---------------------------------------------------------------------------


def test_manager_is_unavailable_without_a_derivation() -> None:
    manager = FightNightManager(None)
    assert not manager.available
    assert "unavailable" in manager.status_message.lower()
    assert manager.plan_for(BROADCAST_MODE) is None
    assert manager.state_at_tick(BROADCAST_MODE, 0) is None


def test_manager_caches_one_plan_per_mode(tmp_path: Path) -> None:
    manager, _last, _result = _four_entrant_manager(tmp_path)
    assert manager.available

    broadcast = manager.plan_for(BROADCAST_MODE)
    assert broadcast is not None
    assert manager.plan_for(BROADCAST_MODE) is broadcast

    entrant = manager.plan_for("A")
    assert entrant is not None
    assert manager.plan_for("A") is entrant
    assert entrant is not broadcast
    assert manager.plan_for("ZZ") is None


# ---------------------------------------------------------------------------
# 2. Phases, seeking, restart and mode switching
# ---------------------------------------------------------------------------


def test_phases_are_a_pure_function_of_the_tick(tmp_path: Path) -> None:
    manager, last, result_ticks = _four_entrant_manager(tmp_path)

    opening = manager.state_at_tick(BROADCAST_MODE, 0)
    assert opening is not None and opening.phase is FightNightPhase.OPENING

    mid = manager.state_at_tick(BROADCAST_MODE, result_ticks // 2)
    assert mid is not None and mid.phase is FightNightPhase.LIVE

    end = manager.state_at_tick(BROADCAST_MODE, result_ticks)
    assert end is not None and end.phase is FightNightPhase.RESULT
    assert manager.state_at_tick(BROADCAST_MODE, last).phase is FightNightPhase.RESULT


def test_seeking_reproduces_identical_presentation_state(tmp_path: Path) -> None:
    """Sec. 43/44: the same tick must present identically along any path."""

    manager, last, _result = _four_entrant_manager(tmp_path)
    ticks = list(range(0, last + 1))

    sequential = {tick: manager.state_at_tick(BROADCAST_MODE, tick) for tick in ticks}

    # Backwards, and a restart-then-seek for every sampled tick.
    for tick in reversed(ticks):
        assert manager.state_at_tick(BROADCAST_MODE, tick) == sequential[tick]
    for tick in ticks[::7]:
        manager.state_at_tick(BROADCAST_MODE, 0)  # restart to tick 0
        assert manager.state_at_tick(BROADCAST_MODE, tick) == sequential[tick]


def test_seeking_mid_match_never_shows_the_opening_card(tmp_path: Path) -> None:
    manager, _last, result_ticks = _four_entrant_manager(tmp_path)
    for tick in range(1, result_ticks):
        state = manager.state_at_tick(BROADCAST_MODE, tick)
        assert state is not None
        assert state.phase is not FightNightPhase.OPENING


def test_restart_returns_to_the_opening_card_with_no_residue(tmp_path: Path) -> None:
    """Restart is just "tick 0 again" -- there is no state to clear."""

    manager, _last, result_ticks = _four_entrant_manager(tmp_path)
    before = manager.state_at_tick(BROADCAST_MODE, 0)
    manager.state_at_tick(BROADCAST_MODE, result_ticks)  # play to the end
    after = manager.state_at_tick(BROADCAST_MODE, 0)  # restart
    assert after == before
    assert after is not None and after.phase is FightNightPhase.OPENING
    assert after.ribbon == ()


def test_switching_mode_at_one_tick_leaves_no_stale_presentation(
    tmp_path: Path,
) -> None:
    """Sec. 42: cutting between modes must not carry a ribbon across."""

    manager, _last, result_ticks = _four_entrant_manager(tmp_path)
    tick = result_ticks // 2

    broadcast_first = manager.state_at_tick(BROADCAST_MODE, tick)
    blind_after = manager.state_at_tick("B", tick)
    broadcast_again = manager.state_at_tick(BROADCAST_MODE, tick)
    assert broadcast_again == broadcast_first

    assert broadcast_first is not None and blind_after is not None
    assert broadcast_first.visibility_basis == "broadcast"
    assert blind_after.visibility_basis == "perspective:B"
    # B is a blind hermit: its own ribbon is empty at a tick where Broadcast
    # has content, so nothing survived the switch.
    assert broadcast_first.ribbon != ()
    assert blind_after.ribbon == ()


def test_a_blind_entrant_never_receives_a_ribbon_entry_at_any_tick(
    tmp_path: Path,
) -> None:
    manager, last, _result = _four_entrant_manager(tmp_path)
    for entrant in ("B", "D"):
        for tick in range(0, last + 1):
            state = manager.state_at_tick(entrant, tick)
            assert state is not None
            assert state.ribbon == ()


# ---------------------------------------------------------------------------
# 3. Layout: 2/3/4 entrants, long names, minimum window
# ---------------------------------------------------------------------------


def _viewport(window: tuple[int, int], entrants: int) -> tuple[int, int, int, int]:
    return calculate_layout(window, entrants, (16, 16)).arena_viewport_rect


def test_fight_night_reserves_no_layout_space_at_any_entrant_count() -> None:
    """Turning Fight Night on must not move a single existing HUD pixel.

    Asserted structurally: ``calculate_layout`` takes no Fight Night argument
    at all, so the same window/entrant inputs produce the identical layout
    whether Fight Night is on or off. This test pins the *consequence* that
    matters -- the arena viewport at the supported minimum is unchanged from
    the pre-Phase-8 geometry for every supported entrant count.
    """

    for entrants in (2, 3, 4):
        layout = calculate_layout(MIN_VIEWER_SIZE, entrants, (16, 16))
        viewport = layout.arena_viewport_rect
        # The arena band still exists and still clears the documented useful
        # minimum height at 640x480.
        assert viewport[3] >= 256
        # And the ribbon lives inside that band rather than beside it.
        rect = fight_night_ribbon_rect(viewport, 4)
        assert rect[1] >= viewport[1]
        assert rect[1] + rect[3] <= viewport[1] + viewport[3]
        assert rect[0] >= viewport[0]
        assert rect[0] + rect[2] <= viewport[0] + viewport[2]


def test_ribbon_fits_the_documented_minimum_window_for_two_three_and_four_entrants() -> None:
    for entrants in (2, 3, 4):
        viewport = _viewport(MIN_VIEWER_SIZE, entrants)
        capacity = fight_night_ribbon_capacity(viewport, 4)
        assert capacity >= 3, (entrants, capacity)
        rect = fight_night_ribbon_rect(viewport, capacity)
        assert rect[2] > 0 and rect[3] > 0
        # The ribbon never claims more than half the arena band.
        assert rect[3] <= viewport[3] // 2 + FIGHT_NIGHT_LINE_HEIGHT


def test_the_ribbon_takes_the_letterbox_gutter_instead_of_covering_the_arena() -> None:
    """The arena stays visually primary: no cell is covered when it need not be.

    The arena is drawn at an integer cell scale centered in its band, so a
    letterbox column beside it is the ordinary case. Where that column is
    wide enough, the ribbon must sit entirely within it rather than on top of
    the battlefield.
    """

    for window in ((640, 480), (1280, 820)):
        for entrants in (2, 3, 4):
            layout = calculate_layout(window, entrants, (20, 20))
            viewport = layout.arena_viewport_rect
            arena = layout.arena_rect
            gutter = arena[0] - viewport[0]
            assert gutter >= FIGHT_NIGHT_MIN_GUTTER_WIDTH, (window, entrants, gutter)

            rect = fight_night_ribbon_rect(viewport, 4, arena)
            # Entirely to the left of the arena's own left edge.
            assert rect[0] + rect[2] <= arena[0], (window, entrants, rect, arena)
            # And still wide enough to read.
            assert rect[2] >= FIGHT_NIGHT_MIN_GUTTER_WIDTH - 2 * 6


def test_the_ribbon_overlays_only_when_the_arena_spans_the_full_width() -> None:
    """A gutter-free window falls back to overlaying, and says so by geometry."""

    viewport = (0, 100, 640, 600)
    full_width_arena = (0, 100, 640, 600)
    rect = fight_night_ribbon_rect(viewport, 4, full_width_arena)
    assert rect[2] > 0
    # No gutter exists, so the ribbon keeps its full width and overlaps.
    assert rect[0] + rect[2] > full_width_arena[0]
    # Without an arena rect at all, behaviour is unchanged from the overlay
    # default -- callers that do not know the arena still get a usable rect.
    assert fight_night_ribbon_rect(viewport, 4) == rect


def test_ribbon_degrades_gracefully_rather_than_forcing_a_larger_window() -> None:
    """Sec. 34's option B, checked down to a pathologically short viewport."""

    tall = fight_night_ribbon_capacity((0, 0, 640, 400), 4)
    short = fight_night_ribbon_capacity((0, 0, 640, 130), 4)
    tiny = fight_night_ribbon_capacity((0, 0, 640, 80), 4)
    narrow = fight_night_ribbon_capacity((0, 0, 150, 400), 4)

    assert tall == 4
    assert 0 < short < 4
    assert tiny == 0
    assert narrow == 0
    # A zero capacity yields a degenerate rect, which every caller skips.
    assert fight_night_ribbon_rect((0, 0, 640, 80), 0)[2:] == (0, 0)


def test_long_entrant_names_never_overflow_the_opening_card() -> None:
    """Closes the Phase 6 long-name gap for the opening card (Sec. 35).

    Checked at the documented minimum for two, three and four entrants: every
    line must fit the card's own character budget, and the entrant id must
    survive truncation so the card still identifies who is fighting even when
    the display name is cut.
    """

    for count in (2, 3, 4):
        viewport = _viewport(MIN_VIEWER_SIZE, count)
        entrants = tuple("ABCD"[:count])
        names = {entrant: f"{LONG_NAME} {entrant}" for entrant in entrants}
        rect = fight_night_card_rect(viewport, 1)
        budget = max(6, (rect[2] - 12) // HUD_CHAR_WIDTH_PX)

        lines = format_fight_night_opening_lines(
            entrants, names, ruleset_label="bytefray-rules-4-alpha1", max_chars=budget
        )
        assert all(len(line) <= budget for line in lines)
        for entrant in entrants:
            assert any(line.startswith(f"{entrant} ·") for line in lines)

        card = fight_night_card_rect(viewport, len(lines))
        assert card[1] >= viewport[1]
        assert card[1] + card[3] <= viewport[1] + viewport[3]


def test_long_entrant_names_never_overflow_the_result_card() -> None:
    for count in (2, 3, 4):
        viewport = _viewport(MIN_VIEWER_SIZE, count)
        entrants = tuple("ABCD"[:count])
        names = {entrant: f"{LONG_NAME} {entrant}" for entrant in entrants}
        rect = fight_night_card_rect(viewport, 1)
        budget = max(6, (rect[2] - 12) // HUD_CHAR_WIDTH_PX)

        lines = format_fight_night_result_lines(
            winner="A",
            termination_reason="last_agent_standing",
            result_ticks=90,
            survivors=entrants,
            names=names,
            max_chars=budget,
        )
        assert all(len(line) <= budget for line in lines)
        assert lines[0] == "MATCH COMPLETE"


def test_long_ribbon_entries_truncate_without_losing_the_label() -> None:
    line = format_fight_night_ribbon_line("PROCESS DISRUPTED", "A", 123, max_chars=None)
    assert line == "T123 A · PROCESS DISRUPTED"

    # Under pressure the tick prefix is dropped before the label is touched.
    squeezed = format_fight_night_ribbon_line(
        "PROCESS DISRUPTED", "A", 123, max_chars=22
    )
    assert squeezed == "A · PROCESS DISRUPTED"
    assert len(squeezed) <= 22

    # And only then does it ellipsis-truncate, never silently overflowing.
    tiny = format_fight_night_ribbon_line("PROCESS DISRUPTED", "A", 123, max_chars=10)
    assert len(tiny) <= 10
    assert tiny.endswith("…")


def test_ribbon_entries_fit_the_minimum_window_ribbon_width() -> None:
    """Every real ribbon label must fit at 640x480 without truncation."""

    from battle_engine.spectator_fight_night import RIBBON_LABELS

    viewport = _viewport(MIN_VIEWER_SIZE, 4)
    rect = fight_night_ribbon_rect(viewport, 4)
    budget = max(6, (rect[2] - 12) // HUD_CHAR_WIDTH_PX)
    for label, _role in RIBBON_LABELS.values():
        rendered = format_fight_night_ribbon_line(label, "A", 999, max_chars=budget)
        assert not rendered.endswith("…"), (label, rendered, budget)


# ---------------------------------------------------------------------------
# 4. Information-domain labelling
# ---------------------------------------------------------------------------


def test_the_ribbon_title_always_names_its_information_domain() -> None:
    """Sec. 18: no ambiguous middle state, answered on screen."""

    assert format_fight_night_ribbon_title("broadcast") == "FIGHT NIGHT · BROADCAST"
    assert format_fight_night_ribbon_title("perspective:A") == "FIGHT NIGHT · A KNOWS"
    assert format_fight_night_ribbon_title("perspective:D") == "FIGHT NIGHT · D KNOWS"


def test_result_card_reports_a_missing_winner_as_a_draw() -> None:
    lines = format_fight_night_result_lines(
        winner=None,
        termination_reason="tick_limit",
        result_ticks=100,
        survivors=("A", "B"),
        names={},
    )
    assert "DRAW / TIE" in lines
    assert "tick limit" in lines


# ---------------------------------------------------------------------------
# 5. Viewer integration and independence
# ---------------------------------------------------------------------------


def _key_stub() -> SimpleNamespace:
    """The renderer's key-dispatch surface, mirroring test_perspective.py's."""

    return SimpleNamespace(
        K_ESCAPE=27,
        K_q=113,
        K_SPACE=32,
        K_RIGHT=275,
        K_LEFT=276,
        K_HOME=278,
        K_END=279,
        K_PLUS=270,
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
        K_g=103,
        K_n=110,
        K_F3=282,
        K_1=49,
        K_2=50,
        K_3=51,
        K_4=52,
        K_5=53,
        K_6=54,
        K_7=55,
        K_8=56,
        K_9=57,
        K_h=104,
        K_SLASH=47,
        K_QUESTION=63,
        KMOD_SHIFT=3,
    )


def test_n_toggles_fight_night_without_touching_playback() -> None:
    """Sec. 39: Fight Night is presentation only."""

    pg = _key_stub()
    calls: list[str] = []
    controller = SimpleNamespace(
        speed=1.0,
        toggle_play_pause=lambda: calls.append("toggle"),
        step_forward=lambda: calls.append("step"),
        pause=lambda: calls.append("pause"),
        restart=lambda: calls.append("restart"),
    )
    action = dispatch_key(pg, pg.K_n, 0, controller)
    assert action.toggle_fight_night is True
    assert action.toggle_director is False
    assert calls == []


def test_g_and_n_are_independent_bindings() -> None:
    """Sec. 41: neither feature's key touches the other's state."""

    pg = _key_stub()
    controller = SimpleNamespace(speed=1.0)
    director = dispatch_key(pg, pg.K_g, 0, controller)
    fight_night = dispatch_key(pg, pg.K_n, 0, controller)
    assert (director.toggle_director, director.toggle_fight_night) == (True, False)
    assert (fight_night.toggle_director, fight_night.toggle_fight_night) == (False, True)


def test_expanded_help_advertises_fight_night_within_its_character_budget() -> None:
    """The footer help line must document `N` and still fit at 640px."""

    budget = (MIN_VIEWER_SIZE[0] - 12) // HUD_CHAR_WIDTH_PX
    assert "N night" in EXPANDED_HELP_LINES[1]
    assert "G dir" in EXPANDED_HELP_LINES[1]
    for line in EXPANDED_HELP_LINES:
        assert len(line) <= budget, (len(line), budget, line)
