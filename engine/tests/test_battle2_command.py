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
    assert "{run,tournament,replay,design,agents}" in result.stdout
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


def _run_with_root(data_root: Path, cwd: Path, *arguments: str):
    env = dict(os.environ, BATTLE2_ROOT=str(data_root))
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "engine" / "src"), str(ROOT / "client" / "src"), str(ROOT)]
    )
    return subprocess.run(
        [sys.executable, "-m", "battle_engine", *arguments],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.parametrize(
    ("agents", "matches"),
    [(["runner", "writer"], 1), (["runner", "writer", "seeker"], 3)],
)
def test_tournament_cli_vm_round_robin_and_output(tmp_path, agents, matches):
    output = tmp_path / "tournament"
    result = _run_with_root(
        tmp_path / "data",
        tmp_path,
        "tournament",
        *agents,
        "--ticks",
        "2",
        "--arena",
        "256",
        "--output",
        str(output),
    )

    assert result.returncode == 0, result.stderr
    assert "Tournament:" in result.stdout
    assert "Standings:" in result.stdout
    assert f"completed={matches}" in result.stdout
    state = json.loads((output / "tournament.json").read_text())
    assert len(state["matches"]) == matches
    assert len(list((output / "matches").glob("*/result.json"))) == matches
    assert len(list((output / "matches").glob("*/replay.jsonl"))) == matches


def test_tournament_cli_multi_round_resume_has_stable_ids(tmp_path):
    output = tmp_path / "resume"
    arguments = (
        "tournament",
        "runner",
        "writer",
        "--rounds",
        "2",
        "--ticks",
        "1",
        "--arena",
        "128",
        "--seed",
        "44",
        "--output",
        str(output),
        "--quiet",
    )
    first = _run_with_root(tmp_path / "data", tmp_path, *arguments)
    before = json.loads((output / "tournament.json").read_text())
    second = _run_with_root(tmp_path / "data", tmp_path, *arguments)
    after = json.loads((output / "tournament.json").read_text())

    assert first.returncode == second.returncode == 0
    assert before["tournament_id"] == after["tournament_id"]
    assert [item["match_id"] for item in before["matches"]] == [
        item["match_id"] for item in after["matches"]
    ]
    assert len(after["matches"]) == 2


def test_tournament_cli_python_division_and_mixed_rejection(tmp_path):
    data_root = tmp_path / "data"
    _write_cli_python_agent(data_root, "py_one", "AgentAction(ActionKind.NOP)")
    _write_cli_python_agent(data_root, "py_two", "AgentAction(ActionKind.NOP)")
    python_output = tmp_path / "python"
    success = _run_with_root(
        data_root,
        tmp_path,
        "tournament",
        "py_one",
        "py_two",
        "--ticks",
        "1",
        "--arena",
        "64",
        "--output",
        str(python_output),
        "--quiet",
    )
    mixed_output = tmp_path / "mixed"
    mixed = _run_with_root(
        data_root,
        tmp_path,
        "tournament",
        "py_one",
        "runner",
        "--output",
        str(mixed_output),
    )

    assert success.returncode == 0, success.stderr
    assert json.loads((python_output / "tournament.json").read_text())["division"] == "python"
    assert mixed.returncode == 2
    assert "mixed groups are unsupported" in mixed.stderr
    assert "Traceback" not in mixed.stdout + mixed.stderr
    assert not mixed_output.exists()


def test_single_match_output_names_canonical_and_compatibility_artifacts(tmp_path):
    replay = tmp_path / "single" / "replay.jsonl"
    result = _run(
        "run",
        "--ticks",
        "1",
        "--arena",
        "128",
        "--replay",
        str(replay),
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert f"result: {replay.with_name('result.json')}" in result.stdout
    assert f"replay: {replay}" in result.stdout
    assert f"summary: {replay.with_name('summary.json')}" in result.stdout


def _write_cli_python_agent(root: Path, name: str, action: str) -> None:
    directory = root / "agents" / name
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text(
        json.dumps(
            {
                "kind": "python",
                "api_version": 1,
                "entrypoint": "agent.py:create_agent",
                "name": name,
                "version": "1.0",
            }
        ),
        encoding="utf-8",
    )
    (directory / "agent.py").write_text(
        f"""
from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, context): pass
    def act(self, observation): return {action}
def create_agent(): return Agent()
""",
        encoding="utf-8",
    )


def test_cli_runs_python_vs_python_match(tmp_path):
    data_root = tmp_path / "data"
    replay = tmp_path / "python-match" / "replay.jsonl"
    _write_cli_python_agent(
        data_root, "py_writer", "AgentAction(ActionKind.WRITE, 11, 77)"
    )
    _write_cli_python_agent(
        data_root, "py_passive", "AgentAction(ActionKind.NOP)"
    )
    env = dict(os.environ, BATTLE2_ROOT=str(data_root))
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "engine" / "src"), str(ROOT / "client" / "src"), str(ROOT)]
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "battle_engine",
            "run",
            "--a-type",
            "py_writer",
            "--b-type",
            "py_passive",
            "--ticks",
            "2",
            "--quota",
            "2",
            "--arena",
            "64",
            "--replay",
            str(replay),
            "--quiet",
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert replay.is_file()
    summary = json.loads(replay.with_name("summary.json").read_text())
    assert summary["agents"] == {"A": "py_writer", "B": "py_passive"}
    assert summary["agent_stats"]["A"]["mem_writes"] == 4


def test_cli_rejects_mixed_vm_python_without_traceback(tmp_path):
    data_root = tmp_path / "data"
    replay = tmp_path / "mixed" / "replay.jsonl"
    _write_cli_python_agent(
        data_root, "py_passive", "AgentAction(ActionKind.NOP)"
    )
    env = dict(os.environ, BATTLE2_ROOT=str(data_root))
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "engine" / "src"), str(ROOT / "client" / "src"), str(ROOT)]
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "battle_engine",
            "run",
            "--a-type",
            "py_passive",
            "--b-type",
            "runner",
            "--ticks",
            "1",
            "--replay",
            str(replay),
            "--quiet",
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "Mixed VM/Python matches are not supported" in result.stderr
    assert "Traceback" not in result.stderr
    assert not replay.exists()


def test_cli_python_act_failure_is_structured_without_traceback(tmp_path):
    data_root = tmp_path / "data"
    replay = tmp_path / "failure" / "replay.jsonl"
    _write_cli_python_agent(data_root, "broken", "(_ for _ in ()).throw(RuntimeError('boom'))")
    _write_cli_python_agent(
        data_root, "py_passive", "AgentAction(ActionKind.NOP)"
    )
    env = dict(os.environ, BATTLE2_ROOT=str(data_root))
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "engine" / "src"), str(ROOT / "client" / "src"), str(ROOT)]
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "battle_engine",
            "run",
            "--a-type",
            "broken",
            "--b-type",
            "py_passive",
            "--ticks",
            "2",
            "--replay",
            str(replay),
            "--quiet",
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stdout + result.stderr
    records = [json.loads(line) for line in replay.read_text().splitlines()]
    # records[1] is the tick-0 initial-state snapshot; tick 1 is records[2].
    assert records[2]["events"][0]["reason"] == "agent_action_failed"


def test_agents_command_initializes_starters_idempotently(tmp_path):
    data_root = tmp_path / "empty-data-root"
    env = dict(os.environ, BATTLE2_ROOT=str(data_root))
    env.pop("BATTLE_ROOT", None)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "engine" / "src"), str(ROOT / "client" / "src"), str(ROOT)]
    )

    first = subprocess.run(
        [sys.executable, "-m", "battle_engine", "agents"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert first.returncode == 0, first.stderr
    manifests = sorted(path.parent.name for path in (data_root / "agents").glob("*/agent.yaml"))
    assert manifests == ["runner", "seeker", "spiral", "writer"]
    runner = data_root / "agents" / "runner" / "agent.yaml"
    runner.write_text('{"name": "runner", "user_note": "keep"}\n', encoding="utf-8")

    second = subprocess.run(
        [sys.executable, "-m", "battle_engine", "agents"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert second.returncode == 0, second.stderr
    assert runner.read_text(encoding="utf-8") == '{"name": "runner", "user_note": "keep"}\n'


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
    # records[1] is the tick-0 initial-state snapshot; tick 1 is records[2].
    assert records[2]["score"] == {"A": 0.25, "B": 0.25}

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
