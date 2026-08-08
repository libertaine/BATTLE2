from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from battle_engine import command
from battle_engine.agent_scaffold import create_agent as scaffold_create_agent
from battle_engine.agent_test import (
    REFERENCE_OPPONENT_NAME,
    AgentTestError,
    DevelopmentTestOutcome,
    InitializationFailureOutcome,
    main,
)
from battle_engine.agent_test import test_agent as run_development_test
from battle_engine.config import Config
from battle_engine.match_service import MatchRequest, NativeMatchService
from battle_engine.replay import iter_replay
from battle_engine.result_model import verify_result_replay

ROOT = Path(__file__).resolve().parents[2]


def _write_python_agent(root: Path, name: str, action: str) -> Path:
    directory = root / "agents" / name
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text(
        json.dumps(
            {
                "kind": "python",
                "api_version": 1,
                "entrypoint": "agent.py:create_agent",
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
    return directory


def _write_reset_failing_agent(root: Path, name: str, message: str = "boom") -> Path:
    directory = root / "agents" / name
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text(
        json.dumps(
            {
                "kind": "python",
                "api_version": 1,
                "entrypoint": "agent.py:create_agent",
                "version": "1.0",
            }
        ),
        encoding="utf-8",
    )
    (directory / "agent.py").write_text(
        f"""
class Agent:
    def reset(self, context):
        raise RuntimeError({message!r})
    def act(self, observation):
        return None
def create_agent(): return Agent()
""",
        encoding="utf-8",
    )
    return directory


def _write_builtin_agent(root: Path, name: str) -> Path:
    directory = root / "agents" / name
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text(
        json.dumps({"name": name, "defaults": {}}), encoding="utf-8"
    )
    return directory


def _run(*args: str, cwd: Path = ROOT, env: dict[str, str] | None = None):
    full_env = dict(os.environ) if env is None else env
    full_env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "engine" / "src"), str(ROOT / "client" / "src"), str(ROOT)]
    )
    return subprocess.run(
        [sys.executable, "-m", "battle_engine", *args],
        cwd=cwd,
        env=full_env,
        text=True,
        capture_output=True,
        check=False,
    )


# --------------------------------------------------------------------------
# Normal development flow
# --------------------------------------------------------------------------


def test_scaffolded_agent_tests_successfully_against_reference(tmp_path):
    scaffold_create_agent("example", data_root=tmp_path, resource_root=ROOT)

    outcome = run_development_test("example", data_root=tmp_path, resource_root=ROOT)

    assert isinstance(outcome, DevelopmentTestOutcome)
    assert outcome.agent_id == "example"
    assert outcome.opponent_name == REFERENCE_OPPONENT_NAME
    assert outcome.seed == Config().seed
    assert outcome.ticks_requested == 200
    assert outcome.match_result.ticks_run == 200
    assert outcome.match_result.replay_path.is_file()
    assert outcome.match_result.result_path.is_file()
    assert outcome.summary_path.is_file()


def test_validate_then_test_both_succeed(tmp_path):
    scaffold_create_agent("example", data_root=tmp_path, resource_root=ROOT)

    from battle_engine.agent_validation import validate_agent

    validate_agent("example", data_root=tmp_path)
    outcome = run_development_test("example", data_root=tmp_path, resource_root=ROOT)
    assert isinstance(outcome, DevelopmentTestOutcome)


def test_deterministic_repeated_execution_for_same_seed(tmp_path):
    scaffold_create_agent("example", data_root=tmp_path, resource_root=ROOT)

    first = run_development_test("example", data_root=tmp_path, resource_root=ROOT, seed=7)
    second = run_development_test("example", data_root=tmp_path, resource_root=ROOT, seed=7)

    assert first.match_result.winner == second.match_result.winner
    assert first.match_result.termination_reason == second.match_result.termination_reason
    assert first.match_result.ticks_run == second.match_result.ticks_run
    assert first.match_result.match_id == second.match_result.match_id
    assert first.match_result.result_id == second.match_result.result_id

    first_records = list(iter_replay(first.match_result.replay_path))
    second_records = list(iter_replay(second.match_result.replay_path))
    assert len(first_records) == len(second_records)


def test_seed_override_changes_recorded_seed(tmp_path):
    scaffold_create_agent("example", data_root=tmp_path, resource_root=ROOT)

    outcome = run_development_test("example", data_root=tmp_path, resource_root=ROOT, seed=99)

    assert outcome.seed == 99
    data = json.loads(outcome.match_result.result_path.read_text(encoding="utf-8"))
    assert data["reproducibility"]["seed"] == 99


def test_ticks_override_changes_effective_ticks(tmp_path):
    scaffold_create_agent("example", data_root=tmp_path, resource_root=ROOT)

    outcome = run_development_test("example", data_root=tmp_path, resource_root=ROOT, ticks=5)

    assert outcome.ticks_requested == 5
    assert outcome.match_result.ticks_run <= 5


def test_explicit_python_opponent_substitutes_for_reference(tmp_path):
    scaffold_create_agent("example", data_root=tmp_path, resource_root=ROOT)
    _write_python_agent(tmp_path, "other", "AgentAction(ActionKind.NOP)")

    outcome = run_development_test(
        "example", opponent="other", data_root=tmp_path, resource_root=ROOT
    )

    assert outcome.opponent_name == "other"
    data = json.loads(outcome.match_result.result_path.read_text(encoding="utf-8"))
    names = {entrant["agent_id"]: entrant["name"] for entrant in data["entrants"]}
    assert names["B"] == "other"


def test_canonical_artifacts_are_produced_and_replay_verifies(tmp_path):
    scaffold_create_agent("example", data_root=tmp_path, resource_root=ROOT)

    outcome = run_development_test("example", data_root=tmp_path, resource_root=ROOT)

    assert verify_result_replay(outcome.match_result.result_path)
    records = list(iter_replay(outcome.match_result.replay_path))
    assert records


def test_replay_loads_via_replay_session_and_client_cli(tmp_path):
    scaffold_create_agent("example", data_root=tmp_path, resource_root=ROOT)
    outcome = run_development_test("example", data_root=tmp_path, resource_root=ROOT, ticks=5)

    from battle_client.session import ReplaySession

    session = ReplaySession()
    session.load(outcome.match_result.replay_path)
    assert session.header is not None

    from battle_client.cli import main as replay_main

    exit_code = replay_main(
        ["--replay", str(outcome.match_result.replay_path), "--renderer", "headless"]
    )
    assert exit_code == 0


def test_repeated_runs_do_not_overwrite_artifacts(tmp_path):
    scaffold_create_agent("example", data_root=tmp_path, resource_root=ROOT)

    first = run_development_test("example", data_root=tmp_path, resource_root=ROOT, ticks=3)
    second = run_development_test("example", data_root=tmp_path, resource_root=ROOT, ticks=3)

    assert first.match_result.replay_path != second.match_result.replay_path
    assert first.match_result.replay_path.is_file()
    assert second.match_result.replay_path.is_file()


# --------------------------------------------------------------------------
# Agent outcomes
# --------------------------------------------------------------------------


def test_tested_agent_loss_is_a_successful_test(tmp_path):
    # A passive agent (NOP forever) reliably loses territory/alive scoring
    # to the reference opponent, which writes every tick.
    _write_python_agent(tmp_path, "passive", "AgentAction(ActionKind.NOP)")

    outcome = run_development_test("passive", data_root=tmp_path, resource_root=ROOT)

    assert isinstance(outcome, DevelopmentTestOutcome)
    assert outcome.match_result.agents_by_id["A"].diagnostic is None


def test_tested_agent_runtime_forfeit_from_act_exception(tmp_path):
    _write_python_agent(
        tmp_path, "raises", "(_ for _ in ()).throw(RuntimeError('act boom'))"
    )

    outcome = run_development_test("raises", data_root=tmp_path, resource_root=ROOT)

    assert isinstance(outcome, DevelopmentTestOutcome)
    diagnostic = outcome.match_result.agents_by_id["A"].diagnostic
    assert diagnostic is not None
    assert diagnostic.code == "agent_action_failed"


def test_tested_agent_invalid_returned_action_forfeits(tmp_path):
    _write_python_agent(tmp_path, "invalid_action", "AgentAction(ActionKind.SET_A, 'nope')")

    outcome = run_development_test("invalid_action", data_root=tmp_path, resource_root=ROOT)

    assert isinstance(outcome, DevelopmentTestOutcome)
    diagnostic = outcome.match_result.agents_by_id["A"].diagnostic
    assert diagnostic is not None
    assert diagnostic.code == "agent_action_invalid"


def test_tested_agent_reset_failure_before_tick_zero(tmp_path):
    _write_reset_failing_agent(tmp_path, "broken_reset")

    outcome = run_development_test("broken_reset", data_root=tmp_path, resource_root=ROOT)

    assert isinstance(outcome, InitializationFailureOutcome)
    assert outcome.agent_id == "broken_reset"
    assert outcome.diagnostic.code == "agent_reset_failed"
    assert outcome.diagnostic.stage == "reset"
    assert "Traceback" not in outcome.diagnostic.message

    run_root = tmp_path / "runs" / "agents_test" / "broken_reset"
    run_dirs = list(run_root.iterdir())
    assert len(run_dirs) == 1
    assert list(run_dirs[0].iterdir()) == []


def test_explicit_opponent_reset_failure_is_a_completed_test_result(tmp_path):
    """An explicit --opponent is user-provided code being evaluated by this
    development test, exactly like the tested agent itself: its own
    pre-tick-zero initialization failure is a test result (exit 0), not a
    tool failure -- unlike the internal reference opponent (see
    test_broken_reference_resource_is_a_tool_failure and
    test_reference_opponent_reset_failure_is_a_tool_error below)."""

    scaffold_create_agent("example", data_root=tmp_path, resource_root=ROOT)
    _write_reset_failing_agent(tmp_path, "broken_opponent", message="opp boom")

    outcome = run_development_test(
        "example",
        opponent="broken_opponent",
        data_root=tmp_path,
        resource_root=ROOT,
    )

    assert isinstance(outcome, InitializationFailureOutcome)
    assert outcome.agent_id == "example"
    assert outcome.opponent_name == "broken_opponent"
    assert outcome.diagnostic.code == "agent_reset_failed"
    assert outcome.diagnostic.stage == "reset"
    assert "Traceback" not in outcome.diagnostic.message

    run_root = tmp_path / "runs" / "agents_test" / "example"
    run_dirs = list(run_root.iterdir())
    assert len(run_dirs) == 1
    assert list(run_dirs[0].iterdir()) == []


def test_explicit_opponent_reset_failure_cli_output(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    scaffold_create_agent("example", data_root=tmp_path, resource_root=ROOT)
    _write_reset_failing_agent(tmp_path, "broken_opponent", message="opp boom")

    exit_code = main(["example", "--opponent", "broken_opponent"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    assert "agent: example" in captured.out
    assert "opponent: broken_opponent" in captured.out
    assert "status: initialization_failed" in captured.out
    assert "stage: reset" in captured.out
    assert "code: agent_reset_failed" in captured.out
    assert "broken_opponent reset failed" in captured.out
    assert "detail: RuntimeError" in captured.out
    assert "result: none" in captured.out
    assert "replay: none" in captured.out
    assert "Traceback" not in captured.out


def test_reference_opponent_reset_failure_is_a_tool_error(tmp_path, monkeypatch):
    """Unlike an explicit --opponent, the internal reference opponent is
    Bytefray-owned infrastructure, not user code under evaluation: its own
    pre-tick-zero initialization failure remains a tool failure (exit 2)."""

    scaffold_create_agent("example", data_root=tmp_path, resource_root=ROOT)

    import battle_engine.agent_test as agent_test_module

    broken_reference = _write_reset_failing_agent(
        tmp_path, "broken_reference_template", message="reference boom"
    )

    def broken_reference_spec(resource_root=None):
        from battle_engine.agents import AgentSpec

        return AgentSpec(
            name="reference",
            display="Bytefray reference agent",
            dir=broken_reference,
            blob=None,
            defaults={},
            kind="python",
            api_version=1,
            version="0.1.0",
            source_path=(broken_reference / "agent.py").resolve(),
            entry_point="agent.py:create_agent",
            manifest={},
        )

    monkeypatch.setattr(
        agent_test_module, "_reference_opponent_spec", broken_reference_spec
    )

    with pytest.raises(AgentTestError) as caught:
        run_development_test("example", data_root=tmp_path, resource_root=ROOT)

    assert caught.value.diagnostic.code == "agent_test_internal_error"
    message = caught.value.diagnostic.message
    assert "reference" in message.lower()
    assert "not a result about 'example'" in message


def test_explicit_opponent_runtime_forfeit_still_completes_test(tmp_path):
    scaffold_create_agent("example", data_root=tmp_path, resource_root=ROOT)
    _write_python_agent(
        tmp_path, "opp_forfeits", "(_ for _ in ()).throw(RuntimeError('opp act boom'))"
    )

    outcome = run_development_test(
        "example", opponent="opp_forfeits", data_root=tmp_path, resource_root=ROOT
    )

    assert isinstance(outcome, DevelopmentTestOutcome)
    diagnostic = outcome.match_result.agents_by_id["B"].diagnostic
    assert diagnostic is not None
    assert diagnostic.code == "agent_action_failed"


# --------------------------------------------------------------------------
# Tool failures
# --------------------------------------------------------------------------


def test_unknown_tested_agent(tmp_path):
    with pytest.raises(AgentTestError) as caught:
        run_development_test("does_not_exist", data_root=tmp_path, resource_root=ROOT)

    assert caught.value.diagnostic.code == "agent_unknown"


def test_non_python_tested_agent(tmp_path):
    _write_builtin_agent(tmp_path, "builtin_agent")

    with pytest.raises(AgentTestError) as caught:
        run_development_test("builtin_agent", data_root=tmp_path, resource_root=ROOT)

    assert caught.value.diagnostic.code == "agent_kind_unsupported"


def test_unknown_opponent(tmp_path):
    scaffold_create_agent("example", data_root=tmp_path, resource_root=ROOT)

    with pytest.raises(AgentTestError) as caught:
        run_development_test(
            "example", opponent="does_not_exist", data_root=tmp_path, resource_root=ROOT
        )

    assert caught.value.diagnostic.code == "agent_unknown"


def test_non_python_opponent(tmp_path):
    scaffold_create_agent("example", data_root=tmp_path, resource_root=ROOT)
    _write_builtin_agent(tmp_path, "builtin_agent")

    calls = {"count": 0}
    real_run = NativeMatchService.run

    def spying_run(self, request: MatchRequest):
        calls["count"] += 1
        return real_run(self, request)

    import battle_engine.agent_test as agent_test_module

    original = agent_test_module.NativeMatchService.run
    agent_test_module.NativeMatchService.run = spying_run
    try:
        with pytest.raises(AgentTestError) as caught:
            run_development_test(
                "example",
                opponent="builtin_agent",
                data_root=tmp_path,
                resource_root=ROOT,
            )
    finally:
        agent_test_module.NativeMatchService.run = original

    assert caught.value.diagnostic.code == "agent_kind_unsupported"
    assert calls["count"] == 0
    assert not (tmp_path / "runs" / "agents_test" / "example").exists()


def test_broken_reference_resource_is_a_tool_failure(tmp_path):
    scaffold_create_agent("example", data_root=tmp_path, resource_root=ROOT)

    with pytest.raises(AgentTestError) as caught:
        run_development_test("example", data_root=tmp_path, resource_root=tmp_path)

    assert caught.value.diagnostic.code == "agent_test_internal_error"
    assert "example" not in caught.value.diagnostic.message


def test_unwritable_output_path_is_a_tool_failure(tmp_path, monkeypatch):
    scaffold_create_agent("example", data_root=tmp_path, resource_root=ROOT)

    import battle_engine.agent_test as agent_test_module

    def failing_mkdir(self, *args, **kwargs):
        raise PermissionError("simulated permission error")

    monkeypatch.setattr(agent_test_module.Path, "mkdir", failing_mkdir)

    with pytest.raises(AgentTestError) as caught:
        run_development_test("example", data_root=tmp_path, resource_root=ROOT)

    assert caught.value.diagnostic.code == "output_directory_failed"


def test_invalid_cli_arguments_have_no_traceback(capsys):
    with pytest.raises(SystemExit) as caught:
        main([])
    assert caught.value.code == 2


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def test_cli_success_output_and_exit_code(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    scaffold_create_agent("example", data_root=tmp_path, resource_root=ROOT)

    exit_code = main(["example", "--ticks", "5"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    assert "agent: example" in captured.out
    assert "opponent: reference" in captured.out
    assert "winner:" in captured.out
    assert "result:" in captured.out
    assert "replay:" in captured.out
    assert "summary:" in captured.out
    assert "bytefray replay" in captured.out
    assert "Traceback" not in captured.out


def test_cli_initialization_failure_output_and_exit_code(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    _write_reset_failing_agent(tmp_path, "broken_reset")

    exit_code = main(["broken_reset"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    assert "status: initialization_failed" in captured.out
    assert "stage: reset" in captured.out
    assert "code: agent_reset_failed" in captured.out
    assert "result: none" in captured.out
    assert "replay: none" in captured.out
    assert "Traceback" not in captured.out


def test_cli_tool_failure_output_and_exit_code(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))

    exit_code = main(["does_not_exist"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "status: error" in captured.err
    assert "code: agent_unknown" in captured.err
    assert "Traceback" not in captured.err


def test_forfeit_line_present_on_tested_agent_forfeit(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    _write_python_agent(
        tmp_path, "raises", "(_ for _ in ()).throw(RuntimeError('act boom'))"
    )

    exit_code = main(["raises"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "forfeit: raises stage=action code=agent_action_failed" in captured.out


def test_cli_help_exits_zero_and_mentions_flags():
    with pytest.raises(SystemExit) as caught:
        main(["--help"])
    assert caught.value.code == 0


def test_cli_help_text_mentions_required_flags(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    assert "agent_id" in out
    assert "--opponent" in out
    assert "--seed" in out
    assert "--ticks" in out


def test_invalid_ticks_exits_two():
    with pytest.raises(SystemExit) as caught:
        main(["example", "--ticks", "0"])
    assert caught.value.code == 2


def test_invalid_seed_exits_two():
    with pytest.raises(SystemExit) as caught:
        main(["example", "--seed", "not-an-int"])
    assert caught.value.code == 2


def test_battle2_alias_behaves_identically(tmp_path):
    data_root = tmp_path / "data-root"
    env = dict(os.environ, BYTEFRAY_ROOT=str(data_root))
    env.pop("BATTLE2_ROOT", None)
    env.pop("BATTLE_ROOT", None)

    created = _run("agents", "create", "example", cwd=tmp_path, env=env)
    assert created.returncode == 0, created.stderr

    snippet = (
        "from battle_engine.command import battle2_main; "
        "raise SystemExit(battle2_main(['agents', 'test', 'example', '--ticks', '5']))"
    )
    result = subprocess.run(
        [sys.executable, "-c", snippet],
        cwd=tmp_path,
        env=dict(
            env,
            PYTHONPATH=os.pathsep.join(
                [str(ROOT / "engine" / "src"), str(ROOT / "client" / "src"), str(ROOT)]
            ),
        ),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "BATTLE2 has been renamed Bytefray" in result.stderr
    assert "agent: example" in result.stdout


def test_agents_help_mentions_test():
    result = _run("agents", "--help")
    assert result.returncode == 0
    assert "test" in result.stdout


def test_bare_agents_create_and_validate_are_unaffected(tmp_path):
    data_root = tmp_path / "data-root"
    env = dict(os.environ, BYTEFRAY_ROOT=str(data_root))
    env.pop("BATTLE2_ROOT", None)
    env.pop("BATTLE_ROOT", None)

    listed = _run("agents", cwd=tmp_path, env=env)
    assert listed.returncode == 0

    created = _run("agents", "create", "example", cwd=tmp_path, env=env)
    assert created.returncode == 0

    validated = _run("agents", "validate", "example", cwd=tmp_path, env=env)
    assert validated.returncode == 0


def test_command_dispatch_reaches_test_module(tmp_path, monkeypatch):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    scaffold_create_agent("dispatched", data_root=tmp_path, resource_root=ROOT)

    assert command.main(["agents", "test", "dispatched", "--ticks", "3"]) == 0


# --------------------------------------------------------------------------
# Architecture
# --------------------------------------------------------------------------


def test_uses_native_match_service_not_a_private_loop(tmp_path, monkeypatch):
    scaffold_create_agent("example", data_root=tmp_path, resource_root=ROOT)

    calls: list[MatchRequest] = []
    real_run = NativeMatchService.run

    def recording_run(self, request: MatchRequest):
        calls.append(request)
        return real_run(self, request)

    monkeypatch.setattr(NativeMatchService, "run", recording_run)

    outcome = run_development_test("example", data_root=tmp_path, resource_root=ROOT, ticks=3)

    assert isinstance(outcome, DevelopmentTestOutcome)
    assert len(calls) == 1
    request = calls[0]
    assert len(request.entrants) == 2
    assert request.entrants[0].agent_id == "A"
    assert request.entrants[0].name == "example"
    assert request.entrants[0].kind == "python"
    assert request.entrants[1].agent_id == "B"
    assert request.entrants[1].name == REFERENCE_OPPONENT_NAME
    assert request.entrants[1].kind == "python"

    import inspect

    import battle_engine.agent_test as agent_test_module

    source = inspect.getsource(agent_test_module)
    assert "PythonEntrantController(" not in source
    assert "class VM" not in source


# --------------------------------------------------------------------------
# Custom data root
# --------------------------------------------------------------------------


def test_custom_bytefray_root_is_honored(monkeypatch, tmp_path):
    monkeypatch.delenv("BATTLE2_ROOT", raising=False)
    monkeypatch.delenv("BATTLE_ROOT", raising=False)
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    scaffold_create_agent("example", data_root=tmp_path, resource_root=ROOT)

    exit_code = main(["example", "--ticks", "3"])

    assert exit_code == 0
    assert (tmp_path / "runs" / "agents_test" / "example").exists()


def test_battle2_root_fallback_is_honored_when_bytefray_root_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("BYTEFRAY_ROOT", raising=False)
    monkeypatch.delenv("BATTLE_ROOT", raising=False)
    monkeypatch.setenv("BATTLE2_ROOT", str(tmp_path))
    scaffold_create_agent("example", data_root=tmp_path, resource_root=ROOT)

    exit_code = main(["example", "--ticks", "3"])

    assert exit_code == 0
    assert (tmp_path / "runs" / "agents_test" / "example").exists()
