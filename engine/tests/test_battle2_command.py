from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from battle_engine import command, legacy


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
