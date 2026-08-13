from __future__ import annotations

import json
from typing import ClassVar

from battle_client import cli
from battle_client.renderers.base import AbstractRenderer
from battle_client.utils import maybe_load_summary
from battle_engine.replay import ReplayHeader, ReplayRecord, TickSnapshot


class CapturingRenderer(AbstractRenderer):
    instances: ClassVar[list[CapturingRenderer]] = []

    def __init__(self) -> None:
        super().__init__()
        self.records: list[ReplayRecord] = []
        self.__class__.instances.append(self)

    def on_event(self, event: ReplayRecord) -> None:
        self.records.append(event)


def test_renderer_receives_same_canonical_types_for_v01_and_v02(tmp_path, monkeypatch):
    replay = tmp_path / "replay.jsonl"
    replay.write_text(
        "\n".join(
            [
                json.dumps({"tick": 0, "ver": 6, "config": {"arena_size": 32}}),
                json.dumps({"tick": 1, "agents": [], "score": {}, "events": [], "memory_diffs": []}),
                json.dumps(
                    {
                        "schema": "battle2.replay",
                        "schema_version": 2,
                        "record_type": "tick",
                        "tick": 2,
                        "agents": [],
                        "score": {},
                        "events": [],
                        "memory_diffs": [],
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    CapturingRenderer.instances.clear()
    monkeypatch.setitem(cli.RENDERERS, "capture", CapturingRenderer)

    assert cli.main(["--replay", str(replay), "--renderer", "capture"]) == 0
    records = CapturingRenderer.instances[-1].records
    assert isinstance(records[0], ReplayHeader)
    assert isinstance(records[1], TickSnapshot)
    assert isinstance(records[2], TickSnapshot)
    assert type(records[1]) is type(records[2])


def test_historical_summary_metadata_locations_are_normalized(tmp_path):
    replay = tmp_path / "replay.jsonl"
    replay.touch()
    (tmp_path / "summary.json").write_text(
        json.dumps(
            {
                "arena_size": 64,
                "params": {"arena": 128, "ticks_run": 9},
                "agents": {"A": "writer"},
            }
        ),
        encoding="utf-8",
    )
    assert maybe_load_summary(replay) == {
        "arena": 64,
        "ticks": 9,
        "agents": {"A": "writer"},
    }
