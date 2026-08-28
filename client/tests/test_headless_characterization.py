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
    assert "HEADER arena=32" in output
    assert "TICK score={}" in output
    assert "[    ] END" in output


def test_help_text_is_pure_ascii(capsys):
    """Regression: a frozen PyInstaller build's console renders a non-ASCII
    character (e.g. an em dash) in printed CLI output as a replacement
    character instead of the source glyph, even though a source `python`
    invocation in the same console renders it correctly. Found live in this
    parser's `description` (an em dash) during v3.0.0-rc1 qualification;
    fixed to ASCII `--` and pinned here so it cannot regress.
    """
    try:
        main(["--help"])
    except SystemExit:
        pass
    output = capsys.readouterr().out
    assert output.isascii(), f"non-ASCII in --help output: {output!r}"
