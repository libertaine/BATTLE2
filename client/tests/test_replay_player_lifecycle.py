from __future__ import annotations

import builtins
import json

import pytest

from battle_client import cli
from battle_client.player import ReplayPlayer
from battle_client.renderers.base import AbstractRenderer
from battle_client.renderers.base import RendererDependencyError
from battle_client.renderers.pygame_renderer import PygameRenderer
from battle_engine.replay import MatchConfiguration, ReplayHeader, ReplayRecord, TickSnapshot


RECORDS = [
    ReplayHeader(MatchConfiguration(arena_size=32)),
    TickSnapshot(1),
    TickSnapshot(2),
]


class LifecycleRenderer(AbstractRenderer):
    def __init__(self, *, fail_on_event: bool = False) -> None:
        super().__init__()
        self.calls: list[str] = []
        self.records: list[ReplayRecord] = []
        self.fail_on_event = fail_on_event

    def setup(self, metadata=None) -> None:
        self.calls.append("setup")
        super().setup(metadata)

    def wait_for_start(self) -> None:
        self.calls.append("wait_for_start")

    def wait_until_ready(self) -> None:
        self.calls.append("wait_until_ready")

    def on_event(self, event: ReplayRecord) -> None:
        self.calls.append("on_event")
        if self.fail_on_event:
            raise RuntimeError("render failed")
        self.records.append(event)

    def update(self) -> None:
        self.calls.append("update")

    def on_complete(self) -> None:
        self.calls.append("on_complete")

    def hold_open(self) -> None:
        self.calls.append("hold_open")

    def teardown(self) -> None:
        self.calls.append("teardown")


def test_explicit_lifecycle_order_wraps_event_delivery():
    renderer = LifecycleRenderer()
    ReplayPlayer(renderer).play(RECORDS, {"arena": 32})
    assert renderer.calls == [
        "setup",
        "wait_for_start",
        "wait_until_ready",
        "on_event",
        "update",
        "wait_until_ready",
        "on_event",
        "update",
        "wait_until_ready",
        "on_event",
        "update",
        "on_complete",
        "hold_open",
        "teardown",
    ]
    assert renderer.records == RECORDS


def test_pause_gate_does_not_drop_the_pending_record():
    class PauseOnceRenderer(LifecycleRenderer):
        def __init__(self) -> None:
            super().__init__()
            self.gates = 0

        def wait_until_ready(self) -> None:
            self.gates += 1
            # Simulate a pause/resume cycle before the second delivery. The
            # player must retain that pending record while this gate runs.
            if self.gates == 2:
                assert self.records == RECORDS[:1]
            super().wait_until_ready()

    renderer = PauseOnceRenderer()
    ReplayPlayer(renderer).play(RECORDS)
    assert renderer.records == RECORDS


def test_one_step_permit_processes_exactly_one_logical_record():
    class StopAfterStep(Exception):
        pass

    class SingleStepRenderer(LifecycleRenderer):
        def wait_until_ready(self) -> None:
            if len(self.records) == 1:
                raise StopAfterStep
            super().wait_until_ready()

    renderer = SingleStepRenderer()
    with pytest.raises(StopAfterStep):
        ReplayPlayer(renderer).play(RECORDS)
    assert renderer.records == RECORDS[:1]
    assert renderer.calls[-1] == "teardown"


def test_pygame_step_permit_is_consumed_even_by_a_header():
    renderer = PygameRenderer()
    renderer.arena = 32
    renderer.paused = True
    renderer.step_once = True
    renderer.on_event(ReplayHeader(MatchConfiguration(arena_size=32)))
    assert renderer.paused
    assert not renderer.step_once


def test_runtime_error_tears_down_without_false_completion():
    renderer = LifecycleRenderer(fail_on_event=True)
    with pytest.raises(RuntimeError, match="render failed"):
        ReplayPlayer(renderer).play(RECORDS)
    assert "on_complete" not in renderer.calls
    assert renderer.calls[-1] == "teardown"


def test_empty_replay_still_completes_before_teardown():
    renderer = LifecycleRenderer()
    ReplayPlayer(renderer).play([])
    assert renderer.calls[-3:] == ["on_complete", "hold_open", "teardown"]


def test_headless_cli_does_not_import_pygame(tmp_path, monkeypatch):
    replay = tmp_path / "replay.jsonl"
    replay.write_text(
        json.dumps({"tick": 0, "ver": 6, "config": {"arena_size": 32}}) + "\n",
        encoding="utf-8",
    )
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "pygame" or name.startswith("pygame."):
            raise AssertionError("headless replay imported pygame")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    assert cli.main(["--replay", str(replay), "--renderer", "headless"]) == 0


def test_missing_renderer_dependency_returns_exit_code_two(tmp_path, monkeypatch, capsys):
    replay = tmp_path / "replay.jsonl"
    replay.write_text(
        json.dumps({"tick": 0, "ver": 6, "config": {"arena_size": 32}}) + "\n",
        encoding="utf-8",
    )

    class MissingRenderer(AbstractRenderer):
        def setup(self, metadata=None) -> None:
            raise RendererDependencyError("install the replay extra")

        def on_event(self, event: ReplayRecord) -> None:
            pass

    monkeypatch.setitem(cli.RENDERERS, "missing", MissingRenderer)
    assert cli.main(["--replay", str(replay), "--renderer", "missing"]) == 2
    assert "dependency error" in capsys.readouterr().err
