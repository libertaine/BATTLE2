"""Phase 8.5: Perspective HUD coherence -- entrant-card and capture-callout
knowledge-boundary integration.

``test_hud_layout.py`` already covers the pure ``entrant_card_known`` /
``known=False`` formatting contract (``hud_layout.py``) in isolation. This
file covers the renderer-level wiring that turns a real
``PerspectiveManager`` into that boolean every frame
(``PygameRenderer._perspective_card_knowledge_basis``), the equivalent
gating for the core-capture callout (``_perspective_safe_captures``), and
the brief's Sec. 38 mandatory real-match negative regression: a real replay
+ trace, run through ``analyze_pair`` and a real ``PerspectiveManager``,
proving a hidden canonical opponent core/score/territory change never
reaches a Perspective card while the identical Broadcast card shows it
plainly.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from battle_client.hud_layout import entrant_card_known, format_entrant_card_lines
from battle_client.perspective import BROADCAST_MODE, PerspectiveManager
from battle_client.renderers.pygame_renderer import (
    CoreCaptureAttribution,
    PygameRenderer,
    _perspective_safe_captures,
)
from battle_client.replay_status import get_entrant_statuses
from battle_client.session import ReplaySession, ReplayState
from battle_engine.agents import resolve_agent
from battle_engine.config import Config, Weights
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.replay import AgentState, KillDeathEvent
from battle_engine.ruleset_policy import RULESET_V4_ALPHA1
from battle_engine.spectator_derivation import SpectatorEventKind, analyze_pair


def _state(tick: int, agents: dict) -> ReplayState:
    return ReplayState(
        tick=tick, arena=bytes(0), owners=(), agents=agents, score={}, runtime_kind="vm"
    )

_IMPORTS = (
    "from battle_engine.agent_api import AgentV2, ObservationV2, AgentAction, "
    "ActionKindV2, MatchContextV2, ProcessDeclaration\n"
)

# Reused verbatim from engine/tests/test_v4_spectator_director.py's own
# EXECUTIONER/SLEEPER fixture (Phase 7 Sec. 13's mandatory timing-disclosure
# regression) -- exact same agents, arena size, tick budget and seed, which
# already proved (real derivation, not assumption) that this match produces
# a genuine core-strip-to-elimination and that the victim receives zero
# visible events for the whole match. Reusing a fixture already proven to
# converge avoids the exact kind of degenerate-fixture risk Phase 8 Sec. 2
# disclosed and had to fix (two of its sixteen corpus scenarios initially
# came back degenerate).
EXECUTIONER = _IMPORTS + '''
class Executioner:
    api_version = 2
    def declare_processes(self):
        return [ProcessDeclaration(id="axe", reach=24, share=1.0)]
    def reset(self, context: MatchContextV2):
        self.target = None
        self.step = 0
    def act(self, obs: ObservationV2) -> AgentAction:
        if self.target is None and obs.visible_enemy_anchor_addresses:
            self.target = obs.visible_enemy_anchor_addresses[0]
        if self.target is None or obs.self_anchor + 4 < self.target:
            return AgentAction(ActionKindV2.MOVE, 4)
        self.step += 1
        return AgentAction(ActionKindV2.WRITE, self.target + (self.step % 8), 0x11)
def create_agent() -> AgentV2:
    return Executioner()
'''

SLEEPER = _IMPORTS + '''
class Sleeper:
    api_version = 2
    def declare_processes(self):
        return [ProcessDeclaration(id="z", reach=1, share=1.0)]
    def reset(self, context: MatchContextV2):
        pass
    def act(self, obs: ObservationV2) -> AgentAction:
        return AgentAction(ActionKindV2.READ, obs.self_anchor)
def create_agent() -> AgentV2:
    return Sleeper()
'''


def _write_agent(root: Path, name: str, source: str) -> None:
    directory = root / "agents" / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "agent.py").write_text(source)
    (directory / "agent.yaml").write_text(
        f"name: {name}\ndescription: Phase 8.5 fixture\nversion: '1.0'\napi_version: 2\n"
    )


def _kill(root: Path) -> tuple[Path, Path]:
    """A (executioner) strips B's (sleeper's) core to elimination."""

    _write_agent(root, "executioner", EXECUTIONER)
    _write_agent(root, "sleeper", SLEEPER)
    replay_path = root / "replay.jsonl"
    trace_path = root / "trace.jsonl"
    NativeMatchService().run(
        MatchRequest(
            config=Config(
                seed=13, arena_size=64, instr_per_tick=8, win_mode="capture", weights=Weights()
            ),
            entrants=(
                MatchEntrant.python("A", "Entrant A", 0, resolve_agent(root, "executioner")),
                MatchEntrant.python("B", "Entrant B", 32, resolve_agent(root, "sleeper")),
            ),
            max_ticks=40,
            replay_path=replay_path,
            trace_path=trace_path,
            ruleset_id=RULESET_V4_ALPHA1.ruleset_id,
        )
    )
    return replay_path, trace_path


# ---------------------------------------------------------------------------
# _perspective_safe_captures: pure filtering logic
# ---------------------------------------------------------------------------
def test_broadcast_shows_every_capture_unchanged():
    captures = (CoreCaptureAttribution("B", "A"), CoreCaptureAttribution("C", "A"))
    assert (
        _perspective_safe_captures(captures, selected_entrant_id=None, is_terminal=False)
        == captures
    )


def test_terminal_tick_shows_every_capture_unchanged():
    captures = (CoreCaptureAttribution("B", "A"),)
    assert (
        _perspective_safe_captures(captures, selected_entrant_id="A", is_terminal=True)
        == captures
    )


def test_live_perspective_suppresses_an_opponent_vs_opponent_capture():
    captures = (CoreCaptureAttribution("B", "C"),)
    assert (
        _perspective_safe_captures(captures, selected_entrant_id="A", is_terminal=False) == ()
    )


def test_live_perspective_suppresses_a_capture_the_selected_entrant_caused():
    # A is the killer, not the victim -- still suppressed: AGENT_ELIMINATED
    # is omniscient-only unconditionally, with no "unless you did it"
    # exception (Phase 7 Sec. 2).
    captures = (CoreCaptureAttribution("B", "A"),)
    assert (
        _perspective_safe_captures(captures, selected_entrant_id="A", is_terminal=False) == ()
    )


def test_live_perspective_keeps_the_selected_entrants_own_capture_without_attribution():
    captures = (CoreCaptureAttribution("A", "B"),)
    visible = _perspective_safe_captures(captures, selected_entrant_id="A", is_terminal=False)
    assert visible == (CoreCaptureAttribution("A", None),)


def test_live_perspective_filters_mixed_simultaneous_captures():
    captures = (CoreCaptureAttribution("A", "C"), CoreCaptureAttribution("B", "C"))
    visible = _perspective_safe_captures(captures, selected_entrant_id="A", is_terminal=False)
    assert visible == (CoreCaptureAttribution("A", None),)


# ---------------------------------------------------------------------------
# PygameRenderer._perspective_card_knowledge_basis: wiring, stubbed manager
# ---------------------------------------------------------------------------
def test_knowledge_basis_is_none_false_with_no_perspective_manager():
    renderer = PygameRenderer()
    assert renderer._perspective_card_knowledge_basis(10) == (None, False)


def test_knowledge_basis_is_none_false_in_broadcast_mode():
    renderer = PygameRenderer()
    renderer._perspective_manager = SimpleNamespace(
        available=True, mode=BROADCAST_MODE, derivation=SimpleNamespace(result_ticks=50)
    )
    assert renderer._perspective_card_knowledge_basis(10) == (None, False)


def test_knowledge_basis_reports_selected_entrant_and_liveness():
    renderer = PygameRenderer()
    renderer._perspective_manager = SimpleNamespace(
        available=True, mode="A", derivation=SimpleNamespace(result_ticks=50)
    )
    assert renderer._perspective_card_knowledge_basis(10) == ("A", False)
    assert renderer._perspective_card_knowledge_basis(50) == ("A", True)
    assert renderer._perspective_card_knowledge_basis(51) == ("A", True)


def test_advance_capture_callout_suppresses_a_hidden_opponent_capture_in_perspective():
    renderer = PygameRenderer()
    renderer.arena, renderer.grid_cols, renderer.grid_rows = 1, 1, 1
    renderer._match_events = [(1, KillDeathEvent("kill", "B", "C"))]
    renderer._perspective_manager = SimpleNamespace(
        available=True, mode="A", derivation=SimpleNamespace(result_ticks=100)
    )
    alive = {"B": AgentState(agent_id="B", pc=0, alive=True)}
    captured = {"B": AgentState(agent_id="B", pc=0, alive=False, termination_reason="core_captured")}

    renderer._advance_transient_effects(_state(0, alive))
    renderer._advance_transient_effects(_state(1, captured))

    assert renderer._active_capture_callout is None
    assert renderer._capture_callout_queue == []


def test_advance_capture_callout_keeps_the_selected_entrants_own_capture_redacted():
    renderer = PygameRenderer()
    renderer.arena, renderer.grid_cols, renderer.grid_rows = 1, 1, 1
    renderer._match_events = [(1, KillDeathEvent("kill", "A", "B"))]
    renderer._perspective_manager = SimpleNamespace(
        available=True, mode="A", derivation=SimpleNamespace(result_ticks=100)
    )
    alive = {"A": AgentState(agent_id="A", pc=0, alive=True)}
    captured = {"A": AgentState(agent_id="A", pc=0, alive=False, termination_reason="core_captured")}

    renderer._advance_transient_effects(_state(0, alive))
    renderer._advance_transient_effects(_state(1, captured))

    assert renderer._active_capture_callout == (1, (CoreCaptureAttribution("A", None),))


# ---------------------------------------------------------------------------
# Sec. 38 mandatory real-match negative regression.
# ---------------------------------------------------------------------------
def test_real_match_hidden_opponent_core_loss_never_reaches_a_perspective_card(
    tmp_path: Path,
) -> None:
    """A real replay + trace, run through ``analyze_pair`` and a real
    ``PerspectiveManager``, proving a hidden canonical opponent core/score
    change never reaches entrant A's Perspective card while the identical
    Broadcast card shows it plainly -- the HUD-layer equivalent of Phase 7
    Sec. 13's Director regression and Phase 8's Fight Night ribbon
    regression, for the persistent entrant cards Phase 8 Sec. 11.1 left
    unresolved.
    """

    replay_path, trace_path = _kill(tmp_path)
    derivation = analyze_pair(replay_path, trace_path)

    # Precondition, proven from the real artifact: the match actually
    # produced a real elimination, and it (like every AGENT_ELIMINATED) is
    # omniscient-only -- delivered to no entrant, not even the attacker.
    eliminations = [e for e in derivation.events if e.kind == SpectatorEventKind.AGENT_ELIMINATED]
    assert eliminations, "fixture must actually eliminate the sleeper"
    assert all(event.visible_to == () for event in eliminations)

    session = ReplaySession()
    session.load(replay_path)

    # Discover, from real per-tick canonical status, a live tick where B has
    # taken real core damage but is not yet eliminated -- the strongest
    # "hidden core loss" case (Sec. 16), not just a post-death card.
    mid_tick = None
    mid_status = None
    for tick in range(derivation.result_ticks):
        session.seek(tick)
        status = next(s for s in get_entrant_statuses(session) if s.agent_id == "B")
        if status.alive and status.core is not None and status.core.intact_cells < 8:
            mid_tick, mid_status = tick, status
            break
    assert mid_status is not None, "fixture must damage B's core before eliminating it"
    assert 0 < mid_status.core.intact_cells < 8

    perspective = PerspectiveManager(replay_path, trace_path, initial_mode="A")
    assert perspective.available
    assert perspective.mode == "A"

    renderer = PygameRenderer()
    renderer._perspective_manager = perspective

    # Broadcast: the real damaged value is shown, unchanged.
    broadcast_basis = (None, False)
    broadcast_known = entrant_card_known(
        mid_status, selected_entrant_id=broadcast_basis[0], is_terminal=broadcast_basis[1]
    )
    broadcast_lines = format_entrant_card_lines(mid_status, known=broadcast_known)
    assert f"Core {mid_status.core.intact_cells}/8" in broadcast_lines[1]
    assert f"Score {mid_status.score:g}" in broadcast_lines[2]

    # Perspective A, same tick: the renderer's own wiring must agree this is
    # not known, and the real damaged count/score must not appear anywhere.
    selected_entrant_id, is_terminal = renderer._perspective_card_knowledge_basis(mid_tick)
    assert (selected_entrant_id, is_terminal) == ("A", False)
    perspective_known = entrant_card_known(
        mid_status, selected_entrant_id=selected_entrant_id, is_terminal=is_terminal
    )
    assert perspective_known is False
    perspective_lines = format_entrant_card_lines(mid_status, known=perspective_known)
    joined = " ".join(perspective_lines)
    assert "UNKNOWN" in joined
    assert f"{mid_status.core.intact_cells}/8" not in joined
    assert f"{mid_status.score:g}" not in joined or mid_status.score == 0

    # A's own card, same tick, is unaffected -- own information stays known.
    session.seek(mid_tick)
    a_status = next(s for s in get_entrant_statuses(session) if s.agent_id == "A")
    assert entrant_card_known(a_status, selected_entrant_id="A", is_terminal=False) is True

    # Terminal tick: the whole match is over, so the same opponent card
    # reverts to full canonical detail, matching Broadcast.
    session.seek(derivation.result_ticks)
    terminal_status = next(s for s in get_entrant_statuses(session) if s.agent_id == "B")
    terminal_selected, terminal_is_terminal = renderer._perspective_card_knowledge_basis(
        derivation.result_ticks
    )
    assert terminal_is_terminal is True
    assert (
        entrant_card_known(
            terminal_status, selected_entrant_id=terminal_selected, is_terminal=terminal_is_terminal
        )
        is True
    )
