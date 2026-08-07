from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _pythonpath() -> str:
    paths = [ROOT / "engine" / "src", ROOT / "client" / "src", ROOT]
    existing = os.environ.get("PYTHONPATH")
    if existing:
        paths.append(Path(existing))
    return os.pathsep.join(map(str, paths))


def _run(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, PYTHONPATH=_pythonpath())
    return subprocess.run(
        [sys.executable, *args],
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_engine_cli_starts_and_displays_help():
    result = _run("-m", "battle_engine.cli", "--help")
    assert result.returncode == 0
    assert "usage: BATTLE" in result.stdout
    assert "--list-agents" in result.stdout
    assert "--mode {b2,redcode94}" in result.stdout


def test_cli_creates_replay_and_summary_json(tmp_path):
    replay = tmp_path / "match" / "replay.jsonl"
    result = _run(
        "-m",
        "battle_engine.cli",
        "--ticks",
        "3",
        "--arena",
        "128",
        "--seed",
        "7",
        "--a-type",
        "writer",
        "--b-type",
        "runner",
        "--b-start",
        "64",
        "--replay",
        str(replay),
        "--quiet",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert replay.exists()
    records = [json.loads(line) for line in replay.read_text().splitlines()]
    summary = json.loads((replay.parent / "summary.json").read_text())
    assert records[0]["schema"] == "battle2.replay"
    assert records[0]["schema_version"] == 3
    assert records[0]["record_type"] == "header"
    assert records[-1]["record_type"] == "result"
    canonical = json.loads((replay.parent / "result.json").read_text())
    assert canonical["schema"] == "battle2.result"
    assert canonical["replay"]["sha256"]
    assert summary["version"] == 2
    assert summary["mode"] == "b2"
    assert summary["seed"] == 7
    assert summary["params"]["ticks_requested"] == 3
    assert summary["agents"] == {"A": "writer", "B": "runner"}
    assert set(summary["score"]) == {"A", "B"}
