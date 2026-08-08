from __future__ import annotations

import pytest
from battle_client import cli
from battle_engine.cli import main as engine_main


@pytest.mark.gui
def test_pygame_renders_replay_and_exits_on_quit(tmp_path, monkeypatch):
    pygame = pytest.importorskip("pygame")
    from battle_client.renderers.pygame_renderer import PygameRenderer

    replay = tmp_path / "replay.jsonl"
    assert engine_main(
        [
            "--ticks", "3", "--arena", "128", "--a-type", "writer",
            "--b-type", "runner", "--b-start", "64", "--replay", str(replay), "--quiet",
        ]
    ) == 0

    # PygameRenderer.run() opens the window and immediately starts its
    # event/render loop (Phase 7a Slice 3: no more blocking "press
    # spacebar to start" gate). Queue a QUIT event right after window
    # setup so the very first loop iteration exits cleanly.
    original_configure_window = PygameRenderer._configure_window

    def configure_then_quit(self):
        original_configure_window(self)
        pygame.event.post(pygame.event.Event(pygame.QUIT))

    monkeypatch.setattr(PygameRenderer, "_configure_window", configure_then_quit)
    assert cli.main(["--replay", str(replay), "--renderer", "pygame"]) == 0
    assert not pygame.get_init()


@pytest.mark.gui
def test_pygame_step_and_seek_advance_a_real_replay(tmp_path, monkeypatch):
    pygame = pytest.importorskip("pygame")
    from battle_client.renderers.pygame_renderer import PygameRenderer

    replay = tmp_path / "replay.jsonl"
    # "runner" vs "runner" reliably survives the full tick budget (unlike
    # writer/runner at close range, which can end the match after tick 1),
    # so there are enough ticks here to step forward twice and back once.
    assert engine_main(
        [
            "--ticks", "5", "--arena", "256", "--a-type", "runner",
            "--b-type", "runner", "--replay", str(replay), "--quiet",
        ]
    ) == 0

    seen_ticks: list[int] = []
    original_loop = PygameRenderer._loop

    def loop_and_record(self, controller):
        # pygame.event.get() returns every queued event in one call, so
        # posting several events upfront would deliver them all within a
        # single frame rather than spreading them across frames. Instead,
        # fake one event arriving per frame, recording the session's tick
        # before each frame's event is processed -- this drives the
        # *real* event/render loop and dispatch_key logic, proving real
        # keyboard input reaches ReplaySession through PlaybackController.
        pending = [
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT, mod=0),  # step to tick 1
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT, mod=0),  # step to tick 2
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_LEFT, mod=0),  # step back to tick 1
            pygame.event.Event(pygame.QUIT),
        ]

        def fake_get(*args, **kwargs):
            seen_ticks.append(controller.session.current_tick)
            return [pending.pop(0)] if pending else []

        monkeypatch.setattr(pygame.event, "get", fake_get)
        original_loop(self, controller)

    monkeypatch.setattr(PygameRenderer, "_loop", loop_and_record)
    # --paused: no auto-advance from PlaybackController.update() should
    # interfere with the manual stepping being verified here.
    assert cli.main(["--replay", str(replay), "--renderer", "pygame", "--paused"]) == 0
    assert not pygame.get_init()
    assert seen_ticks == [0, 1, 2, 1]
