from __future__ import annotations

import json

import pytest
from battle_client.player import SPEEDS, PlaybackController
from battle_client.renderers.pygame_renderer import (
    KeyAction,
    build_hud_lines,
    dispatch_key,
)
from battle_client.session import ReplaySession
from battle_engine.replay import (
    AgentState,
    MatchConfiguration,
    MatchResult,
    MemoryDiff,
    ReplayHeader,
    TickSnapshot,
    write_replay,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _agent(agent_id, pc=0, alive=True, cpu_used=0, mem_writes=0, region=None):
    return AgentState(
        agent_id=agent_id, pc=pc, alive=alive, cpu_used=cpu_used,
        mem_writes=mem_writes, region=region,
    )


def _five_tick_session(tmp_path, *, with_result=True):
    header = ReplayHeader(
        MatchConfiguration(arena_size=8), {"A": "alpha", "B": "beta"}, runtime_kind="vm"
    )
    ticks = tuple(
        TickSnapshot(
            t,
            agents=(_agent("A", pc=t, cpu_used=1, mem_writes=1), _agent("B", pc=t)),
            score={"A": t, "B": 0},
            memory_diffs=(MemoryDiff(address=t, length=1, owner="A", values=(0x10 + t,)),),
        )
        for t in range(5)
    )
    records = [header, *ticks]
    if with_result:
        records.append(
            MatchResult(
                winner="A", win_mode="score", ticks=4, score={"A": 4, "B": 0},
                agents=(_agent("A", pc=4), _agent("B", pc=4)),
                termination_reason="tick_limit",
            )
        )
    replay_path = tmp_path / "replay.jsonl"
    write_replay(replay_path, records)
    session = ReplaySession()
    session.load(replay_path)
    return session


def _sparse_session(tmp_path):
    header = ReplayHeader(MatchConfiguration(arena_size=8), runtime_kind="vm")
    ticks = [TickSnapshot(t, agents=(_agent("A", pc=t),)) for t in (0, 5, 9)]
    replay_path = tmp_path / "sparse.jsonl"
    write_replay(replay_path, [header, *ticks])
    session = ReplaySession()
    session.load(replay_path)
    return session


def _python_spec(root, name, source):
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


def _python_session(tmp_path):
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


# ---------------------------------------------------------------------------
# Construction / play / pause
# ---------------------------------------------------------------------------
def test_controller_starts_playing_by_default(tmp_path):
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session)
    assert controller.playing
    assert controller.session.current_tick == 0


def test_controller_can_start_paused(tmp_path):
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session, playing=False)
    assert not controller.playing


def test_pause_prevents_automatic_advancement(tmp_path):
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session, tick_interval=0.01, playing=False)
    controller.update(10.0)  # a huge elapsed time, would advance many ticks if playing
    assert session.current_tick == 0


def test_play_advances_over_time(tmp_path):
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session, tick_interval=0.1, playing=True)
    controller.update(0.25)  # 2 whole intervals at 1x
    assert session.current_tick == 2


def test_toggle_play_pause(tmp_path):
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session, playing=True)
    controller.toggle_play_pause()
    assert not controller.playing
    controller.toggle_play_pause()
    assert controller.playing


# ---------------------------------------------------------------------------
# Discrete navigation
# ---------------------------------------------------------------------------
def test_step_forward_advances_exactly_one_recorded_tick_and_pauses(tmp_path):
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session, playing=True)
    state = controller.step_forward()
    assert state.tick == 1
    assert not controller.playing


def test_step_forward_is_a_safe_no_op_at_the_final_tick(tmp_path):
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session)
    for _ in range(4):
        controller.step_forward()
    assert session.at_end
    state = controller.step_forward()  # must not raise
    assert state.tick == 4


def test_step_backward_uses_the_previous_recorded_tick(tmp_path):
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session)
    controller.step_forward()
    controller.step_forward()
    assert session.current_tick == 2
    state = controller.step_backward()
    assert state.tick == 1
    assert not controller.playing


def test_step_backward_is_a_safe_no_op_at_the_first_tick(tmp_path):
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session)
    state = controller.step_backward()  # already at tick 0
    assert state.tick == 0


def test_step_backward_uses_previous_recorded_tick_on_sparse_replay(tmp_path):
    session = _sparse_session(tmp_path)
    controller = PlaybackController(session)
    session.seek(5)
    state = controller.step_backward()
    assert state.tick == 0  # not 4 -- 4 was never recorded


def test_step_forward_uses_next_recorded_tick_on_sparse_replay(tmp_path):
    session = _sparse_session(tmp_path)
    controller = PlaybackController(session)  # starts at tick 0
    state = controller.step_forward()
    assert state.tick == 5  # not 1 -- 1 was never recorded


def test_seek_relative_forward_and_backward(tmp_path):
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session)
    controller.seek_relative(3)
    assert session.current_tick == 3
    controller.seek_relative(-2)
    assert session.current_tick == 1


def test_seek_relative_clamps_to_range(tmp_path):
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session)
    controller.seek_relative(-100)
    assert session.current_tick == 0
    controller.seek_relative(100)
    assert session.current_tick == 4


def test_seek_relative_snaps_into_range_on_sparse_replay(tmp_path):
    session = _sparse_session(tmp_path)
    controller = PlaybackController(session)
    state = controller.seek_relative(3)  # target 3 falls in the 0..5 gap
    assert state.tick == 5


def test_restart_returns_to_first_tick_and_pauses(tmp_path):
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session, playing=True)
    controller.step_forward()
    controller.step_forward()
    state = controller.restart()
    assert state.tick == 0
    assert not controller.playing


def test_jump_to_end(tmp_path):
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session)
    state = controller.jump_to_end()
    assert state.tick == 4
    assert session.at_end


# ---------------------------------------------------------------------------
# Speed
# ---------------------------------------------------------------------------
def test_speed_defaults_to_1x(tmp_path):
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session)
    assert controller.speed == 1.0


def test_speed_up_and_down_move_through_fixed_steps(tmp_path):
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session)
    controller.speed_up()
    assert controller.speed == 2.0
    controller.speed_up()
    assert controller.speed == 4.0
    controller.speed_down()
    controller.speed_down()
    controller.speed_down()
    assert controller.speed == 0.5


def test_speed_clamps_at_the_ends_of_the_fixed_range(tmp_path):
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session)
    for _ in range(10):
        controller.speed_down()
    assert controller.speed == SPEEDS[0]
    for _ in range(10):
        controller.speed_up()
    assert controller.speed == SPEEDS[-1]


def test_set_speed_snaps_to_nearest_supported_value(tmp_path):
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session)
    controller.set_speed(3.0)
    assert controller.speed == 2.0  # nearer to 2.0 than 4.0
    controller.set_speed(1000.0)
    assert controller.speed == SPEEDS[-1]


def test_speed_change_affects_pacing_on_the_next_update_call(tmp_path):
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session, tick_interval=0.1, playing=True)
    controller.speed_up()
    controller.speed_up()  # 4x
    controller.update(0.1)  # 0.1 * 4 = 0.4s accumulated -> 4 ticks at 0.1s/tick
    assert session.current_tick == 4
    assert session.at_end


# ---------------------------------------------------------------------------
# End-of-replay behavior
# ---------------------------------------------------------------------------
def test_reaching_the_final_tick_during_playback_auto_pauses(tmp_path):
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session, tick_interval=0.1, playing=True)
    controller.update(10.0)  # far more than enough to reach the end
    assert session.at_end
    assert not controller.playing


def test_play_at_final_tick_restarts_and_plays(tmp_path):
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session)
    controller.jump_to_end()
    assert session.at_end
    assert not controller.playing

    controller.play()
    assert session.current_tick == 0
    assert controller.playing


# ---------------------------------------------------------------------------
# HUD content
# ---------------------------------------------------------------------------
def test_hud_shows_tick_final_tick_status_and_speed(tmp_path):
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session, playing=False)
    lines = build_hud_lines(session, controller)
    joined = "\n".join(lines)
    assert "Tick 0 / 4" in joined
    assert "PAUSED" in joined
    assert "speed 1x" in joined


def test_hud_shows_playing_status(tmp_path):
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session, playing=True)
    assert "PLAYING" in "\n".join(build_hud_lines(session, controller))


def test_hud_omits_winner_until_a_terminal_result_exists(tmp_path):
    session = _five_tick_session(tmp_path, with_result=False)
    controller = PlaybackController(session, playing=False)
    joined = "\n".join(build_hud_lines(session, controller))
    assert "Winner" not in joined


def test_hud_shows_winner_and_termination_regardless_of_cursor_position(tmp_path):
    session = _five_tick_session(tmp_path, with_result=True)
    controller = PlaybackController(session, playing=False)
    # Winner/termination come from the terminal record, independent of
    # where playback currently is -- check at tick 0, not just at the end.
    assert session.current_tick == 0
    joined = "\n".join(build_hud_lines(session, controller))
    assert "Winner: A" in joined
    assert "Termination: tick_limit" in joined


def test_hud_vm_agent_line_labels_pc_cpu_and_region(tmp_path):
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session, playing=False)
    joined = "\n".join(build_hud_lines(session, controller))
    assert "pc=0" in joined
    assert "cpu=1" in joined
    assert "ctrl=" not in joined
    assert "actions=" not in joined


def test_hud_python_agent_line_does_not_use_vm_labels(tmp_path):
    session = _python_session(tmp_path)
    controller = PlaybackController(session, playing=False)
    joined = "\n".join(build_hud_lines(session, controller))
    assert "ctrl=" in joined
    assert "actions=" in joined
    # Python's degenerate (0, 0) region must never be presented as a real
    # code footprint.
    assert "region=n/a" in joined
    assert "region=[0, 0]" not in joined
    assert " pc=" not in joined


def test_hud_agent_line_reflects_alive_dead_status(tmp_path):
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session, playing=False)
    controller.jump_to_end()
    joined = "\n".join(build_hud_lines(session, controller))
    assert "A (alpha)  alive" in joined


def test_hud_stays_correct_after_seeking(tmp_path):
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session, playing=False)
    controller.step_forward()
    controller.step_forward()
    joined = "\n".join(build_hud_lines(session, controller))
    assert "Tick 2 / 4" in joined


# ---------------------------------------------------------------------------
# Keyboard dispatch (real pygame key constants; no display/window needed)
# ---------------------------------------------------------------------------
def test_dispatch_space_toggles_play_pause(tmp_path):
    pygame = pytest.importorskip("pygame")
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session, playing=True)
    dispatch_key(pygame, pygame.K_SPACE, 0, controller)
    assert not controller.playing
    dispatch_key(pygame, pygame.K_SPACE, 0, controller)
    assert controller.playing


def test_dispatch_right_steps_forward_without_modifier(tmp_path):
    pygame = pytest.importorskip("pygame")
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session)
    dispatch_key(pygame, pygame.K_RIGHT, 0, controller)
    assert session.current_tick == 1


def test_dispatch_shift_right_seeks_forward_ten(tmp_path):
    pygame = pytest.importorskip("pygame")
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session)
    dispatch_key(pygame, pygame.K_RIGHT, pygame.KMOD_SHIFT, controller)
    assert session.current_tick == 4  # clamped: only 4 ticks available


def test_dispatch_left_steps_backward_without_modifier(tmp_path):
    pygame = pytest.importorskip("pygame")
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session)
    controller.seek_relative(3)
    dispatch_key(pygame, pygame.K_LEFT, 0, controller)
    assert session.current_tick == 2


def test_dispatch_home_and_end(tmp_path):
    pygame = pytest.importorskip("pygame")
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session)
    dispatch_key(pygame, pygame.K_END, 0, controller)
    assert session.at_end
    dispatch_key(pygame, pygame.K_HOME, 0, controller)
    assert session.current_tick == 0


def test_dispatch_speed_keys(tmp_path):
    pygame = pytest.importorskip("pygame")
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session)
    dispatch_key(pygame, pygame.K_EQUALS, 0, controller)
    assert controller.speed == 2.0
    dispatch_key(pygame, pygame.K_MINUS, 0, controller)
    assert controller.speed == 1.0


def test_dispatch_quit_keys_report_quit_requested(tmp_path):
    pygame = pytest.importorskip("pygame")
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session)
    assert dispatch_key(pygame, pygame.K_ESCAPE, 0, controller) == KeyAction(quit_requested=True)
    assert dispatch_key(pygame, pygame.K_q, 0, controller) == KeyAction(quit_requested=True)


def test_dispatch_bracket_keys_report_rescale_not_speed(tmp_path):
    pygame = pytest.importorskip("pygame")
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session)
    action = dispatch_key(pygame, pygame.K_RIGHTBRACKET, 0, controller)
    assert action.rescale == 1
    assert controller.speed == 1.0  # unaffected -- brackets are not speed keys


def test_dispatch_zero_reports_fit_to_display(tmp_path):
    pygame = pytest.importorskip("pygame")
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session)
    assert dispatch_key(pygame, pygame.K_0, 0, controller).fit_to_display


def test_dispatch_t_reports_toggle_trails(tmp_path):
    pygame = pytest.importorskip("pygame")
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session)
    assert dispatch_key(pygame, pygame.K_t, 0, controller).toggle_trails


def test_dispatch_unknown_key_is_a_no_op(tmp_path):
    pygame = pytest.importorskip("pygame")
    session = _five_tick_session(tmp_path)
    controller = PlaybackController(session)
    assert dispatch_key(pygame, pygame.K_F5, 0, controller) == KeyAction()
