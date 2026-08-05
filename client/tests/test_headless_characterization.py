from __future__ import annotations

import json

from battle_client.cli import main


def test_headless_client_processes_replay_without_pygame(tmp_path, capsys):
    replay = tmp_path / "replay.jsonl"
    replay.write_text(
        "\n".join(
            [
                json.dumps({"tick": 0, "ver": 6, "config": {"arena_size": 32}}),
                json.dumps({"tick": 1, "agents": [], "score": {}, "events": []}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "summary.json").write_text(
        json.dumps({"arena": 32, "agents": {"A": "writer", "B": "runner"}}),
        encoding="utf-8",
    )

    assert main(["--replay", str(replay), "--renderer", "headless"]) == 0
    output = capsys.readouterr().out
    assert "[BATTLE:HEADLESS] start arena=32" in output
    assert "EVENT" in output
    assert "[    ] END" in output
