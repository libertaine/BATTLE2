from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from battle_engine import cli, command, legacy


ROOT = Path(__file__).resolve().parents[2]


def _run(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "engine" / "src"), str(ROOT / "client" / "src"), str(ROOT)]
    )
    return subprocess.run(
        [sys.executable, "-m", "battle_engine", *args],
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_primary_help_lists_all_subcommands():
    result = _run("--help")
    assert result.returncode == 0
    assert "{run,replay,design,agents}" in result.stdout
    for name in command.COMMANDS:
        assert name in result.stdout


@pytest.mark.parametrize("subcommand", command.COMMANDS)
def test_every_subcommand_help_works_without_launching_optional_ui(subcommand):
    result = _run(subcommand, "--help")
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


def test_invalid_run_arguments_use_standard_exit_code_two():
    result = _run("run", "--definitely-not-an-option")
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


@pytest.mark.parametrize("quota", ["0", "-1"])
def test_run_rejects_nonpositive_quota(quota):
    result = _run("run", "--quota", quota)
    assert result.returncode == 2
    assert "must be greater than zero" in result.stderr


def test_successful_headless_match_invocation(tmp_path):
    replay = tmp_path / "artifacts" / "replay.jsonl"
    result = _run(
        "run",
        "--ticks",
        "3",
        "--arena",
        "128",
        "--seed",
        "17",
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
    summary = json.loads((replay.parent / "summary.json").read_text())
    assert summary["seed"] == 17
    assert summary["params"]["ticks_requested"] == 3


def test_quota_and_fractional_scores_reach_replay_and_summary(tmp_path):
    replay = tmp_path / "fractional" / "replay.jsonl"
    result = _run(
        "run",
        "--ticks",
        "1",
        "--arena",
        "128",
        "--quota",
        "3",
        "--alive-w",
        "0.25",
        "--kill-w",
        "0.5",
        "--territory-w",
        "0",
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

    records = [json.loads(line) for line in replay.read_text().splitlines()]
    assert records[0]["config"]["instr_per_tick"] == 3
    assert records[1]["score"] == {"A": 0.25, "B": 0.25}

    summary = json.loads((replay.parent / "summary.json").read_text())
    assert summary["score"] == {"A": 0.25, "B": 0.25}
    assert summary["agent_stats"]["A"]["score"] == 0.25
    assert summary["agent_stats"]["B"]["score"] == 0.25
    assert summary["winner"] == "tie"


def test_invalid_agent_does_not_create_or_truncate_replay(tmp_path):
    replay = tmp_path / "existing.jsonl"
    replay.write_text("keep me\n", encoding="utf-8")
    result = _run(
        "run",
        "--a-type",
        "not-a-real-agent",
        "--replay",
        str(replay),
        "--quiet",
        cwd=tmp_path,
    )
    assert result.returncode == 2
    assert replay.read_text(encoding="utf-8") == "keep me\n"


def test_battle2_root_precedes_legacy_battle_root(monkeypatch, tmp_path):
    preferred = tmp_path / "preferred"
    legacy_root = tmp_path / "legacy"
    monkeypatch.setenv("BATTLE2_ROOT", str(preferred))
    monkeypatch.setenv("BATTLE_ROOT", str(legacy_root))
    assert cli._battle_root() == preferred.resolve()


def test_legacy_battle_root_remains_a_fallback(monkeypatch, tmp_path):
    legacy_root = tmp_path / "legacy"
    monkeypatch.delenv("BATTLE2_ROOT", raising=False)
    monkeypatch.setenv("BATTLE_ROOT", str(legacy_root))
    assert cli._battle_root() == legacy_root.resolve()


def test_missing_designer_dependency_has_actionable_error(monkeypatch, capsys):
    real_import = importlib.import_module

    def missing_designer(name, package=None):
        if name == "app.agent_designer":
            error = ModuleNotFoundError("No module named 'PySide6'")
            error.name = "PySide6"
            raise error
        return real_import(name, package)

    monkeypatch.setattr(command.importlib, "import_module", missing_designer)
    assert command.main(["design"]) == 2
    assert "battle2[designer]" in capsys.readouterr().err


def test_legacy_battle_cli_wrapper_preserves_help():
    with pytest.raises(SystemExit) as exit_info:
        legacy.battle_cli(["--help"])
    assert exit_info.value.code == 0


def test_legacy_gui_wrappers_delegate_lazily(monkeypatch):
    monkeypatch.setitem(sys.modules, "app.match_runner", SimpleNamespace(main=lambda: 7))
    assert legacy.match_runner([]) == 7

    monkeypatch.setattr(
        legacy.importlib,
        "import_module",
        lambda name: SimpleNamespace(main=lambda: 8),
    )
    assert legacy.agent_designer([]) == 8


def test_legacy_gui_help_does_not_import_optional_apps(monkeypatch, capsys):
    def unexpected_import(name, package=None):
        raise AssertionError(f"optional app imported for help: {name}")

    monkeypatch.setattr(legacy.importlib, "import_module", unexpected_import)
    assert legacy.match_runner(["--help"]) == 0
    assert legacy.agent_designer(["--help"]) == 0
    output = capsys.readouterr().out
    assert "usage: match-runner" in output
    assert "usage: battle-agent-designer" in output
