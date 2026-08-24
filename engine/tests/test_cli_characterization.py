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
        capture_output=True,
        check=False,
    )


def test_engine_cli_starts_and_displays_help():
    result = _run("-m", "battle_engine.cli", "--help")
    assert result.returncode == 0
    assert "usage: bytefray run" in result.stdout
    assert "--list-agents" in result.stdout
    assert "--mode {native,redcode94}" in result.stdout


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


def _write_python_agent(root: Path, name: str) -> None:
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
        "from battle_engine.agent_api import ActionKind, AgentAction\n"
        "class Agent:\n"
        "    def reset(self, context): pass\n"
        "    def act(self, observation): return AgentAction(ActionKind.NOP)\n"
        "def create_agent(): return Agent()\n",
        encoding="utf-8",
    )


def test_ruleset_flag_omitted_defaults_to_v1(tmp_path):
    replay = tmp_path / "match" / "replay.jsonl"
    result = _run(
        "-m", "battle_engine.cli",
        "--ticks", "3", "--arena", "128", "--seed", "7",
        "--a-type", "writer", "--b-type", "runner", "--b-start", "64",
        "--replay", str(replay), "--quiet",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    canonical = json.loads((replay.parent / "result.json").read_text())
    assert canonical["ruleset_id"] == "bytefray-rules-1"
    header = json.loads(replay.read_text().splitlines()[0])
    assert header["ruleset_id"] == "bytefray-rules-1"


def test_ruleset_flag_explicit_v1(tmp_path):
    replay = tmp_path / "match" / "replay.jsonl"
    result = _run(
        "-m", "battle_engine.cli",
        "--ticks", "3", "--arena", "128", "--seed", "7",
        "--a-type", "writer", "--b-type", "runner", "--b-start", "64",
        "--ruleset", "bytefray-rules-1",
        "--replay", str(replay), "--quiet",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    canonical = json.loads((replay.parent / "result.json").read_text())
    assert canonical["ruleset_id"] == "bytefray-rules-1"
    header = json.loads(replay.read_text().splitlines()[0])
    assert header["ruleset_id"] == "bytefray-rules-1"


def test_ruleset_flag_explicit_v2_python_succeeds(tmp_path, monkeypatch):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    _write_python_agent(tmp_path, "alpha_agent")
    _write_python_agent(tmp_path, "beta_agent")
    replay = tmp_path / "match" / "replay.jsonl"
    result = _run(
        "-m", "battle_engine.cli",
        "--ticks", "3", "--arena", "128", "--seed", "7",
        "--a-type", "alpha_agent", "--b-type", "beta_agent", "--b-start", "64",
        "--ruleset", "bytefray-rules-2",
        "--replay", str(replay), "--quiet",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    canonical = json.loads((replay.parent / "result.json").read_text())
    assert canonical["ruleset_id"] == "bytefray-rules-2"
    header = json.loads(replay.read_text().splitlines()[0])
    assert header["ruleset_id"] == "bytefray-rules-2"


def test_ruleset_flag_explicit_v2_vm_fails_cleanly_with_no_artifacts(tmp_path):
    replay = tmp_path / "match" / "replay.jsonl"
    result = _run(
        "-m", "battle_engine.cli",
        "--ticks", "3", "--arena", "128", "--seed", "7",
        "--a-type", "writer", "--b-type", "runner", "--b-start", "64",
        "--ruleset", "bytefray-rules-2",
        "--replay", str(replay), "--quiet",
        cwd=tmp_path,
    )
    assert result.returncode == 2
    assert "bytefray-rules-2" in result.stderr
    assert "Python entrants only" in result.stderr
    assert "Traceback" not in result.stderr
    assert not replay.exists()
    assert not (replay.parent / "result.json").exists()


def test_ruleset_flag_unknown_value_fails_closed(tmp_path):
    result = _run(
        "-m", "battle_engine.cli",
        "--a-type", "writer", "--b-type", "runner",
        "--ruleset", "bytefray-rules-99",
        "--quiet",
        cwd=tmp_path,
    )
    assert result.returncode == 2
    assert "invalid choice" in result.stderr


def test_cli_help_lists_ruleset_product_choices_not_alpha_ids():
    result = _run("-m", "battle_engine.cli", "--help")
    assert result.returncode == 0
    assert "bytefray-rules-1" in result.stdout
    assert "bytefray-rules-2" in result.stdout
    assert "alpha" not in result.stdout


def test_resolve_agent_applies_per_agent_env_json_to_builtin_construction(
    monkeypatch, tmp_path
):
    """BYTEFRAY_AGENT_A_PARAMS_JSON/BYTEFRAY_AGENT_B_PARAMS_JSON must actually
    override a built-in agent's construction kwargs, not just be parsed and
    discarded. This is the engine-side half of the previously-confirmed
    "Agent Params silently discarded" bug: the Designer's Advanced tab
    exports its per-agent JSON editors to exactly these two env vars for the
    child process to consume.
    """
    from battle_engine.builtins import build_agent
    from battle_engine.cli import _resolve_agent, parse_args

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    monkeypatch.delenv("BYTEFRAY_AGENT_A_PARAMS_JSON", raising=False)

    args = parse_args(["--a-type", "writer", "--b-type", "writer"])
    # ``_resolve_agent`` requires an already-resolved (never ``None``) start;
    # ``main()`` normally resolves it via ``resolve_direct_match_starts``
    # before calling ``_resolve_agent`` -- this test calls it directly, so it
    # must resolve the omitted start itself (Ruleset v1's omitted-start
    # default remains 0, unaffected by this test's builtin-params focus).
    args.a_start = 0
    common_kwargs = {"offset": 1, "byte": 1}

    baseline_code, name, start, python_spec = _resolve_agent(
        "A", {}, None, args, None, common_kwargs
    )
    assert name == "writer"
    assert python_spec is None
    assert baseline_code == build_agent("writer", start, **common_kwargs)

    monkeypatch.setenv(
        "BYTEFRAY_AGENT_A_PARAMS_JSON", json.dumps({"offset": 99, "byte": 66})
    )
    overridden_code, _, _, _ = _resolve_agent(
        "A", {}, None, args, None, common_kwargs
    )
    assert overridden_code == build_agent("writer", start, offset=99, byte=66)
    assert overridden_code != baseline_code
