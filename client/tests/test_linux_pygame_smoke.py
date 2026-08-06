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
            "--ticks", "1", "--arena", "128", "--a-type", "writer",
            "--b-type", "runner", "--b-start", "64", "--replay", str(replay), "--quiet",
        ]
    ) == 0

    original_start = PygameRenderer.wait_for_start
    original_complete = PygameRenderer.on_complete

    def inject_start(self):
        pygame.event.clear()
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
        original_start(self)

    def complete_then_quit(self):
        original_complete(self)
        pygame.event.post(pygame.event.Event(pygame.QUIT))

    monkeypatch.setattr(PygameRenderer, "wait_for_start", inject_start)
    monkeypatch.setattr(PygameRenderer, "on_complete", complete_then_quit)
    assert cli.main(["--replay", str(replay), "--renderer", "pygame"]) == 0
    assert not pygame.get_init()
