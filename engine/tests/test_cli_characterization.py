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


def _write_python_agent_v2(root: Path, name: str) -> None:
    directory = root / "agents" / name
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text(
        json.dumps(
            {
                "kind": "python",
                "api_version": 2,
                "entrypoint": "agent.py:create_agent",
                "version": "1.0",
            }
        ),
        encoding="utf-8",
    )
    (directory / "agent.py").write_text(
        "from battle_engine.agent_api import ActionKindV2, AgentAction\n"
        "class Agent:\n"
        "    def reset(self, context): pass\n"
        "    def declare_processes(self): return []\n"
        "    def act(self, observation): return AgentAction(ActionKindV2.MOVE, operand=0)\n"
        "def create_agent(): return Agent()\n",
        encoding="utf-8",
    )


def _scaffold(root: Path, name: str, api_version: int) -> None:
    """Create a real scaffolded agent, exercising the shipped templates."""

    from battle_engine.agent_scaffold import create_agent

    create_agent(name, data_root=root, resource_root=ROOT, api_version=api_version)


def test_run_omitted_ruleset_resolves_current_v4_for_api_v2_agents(tmp_path, monkeypatch):
    """H1: an Agent API v2 roster with --ruleset omitted must reach the
    process-agent Ruleset automatically. Before this, resolution saw only
    "python", chose bytefray-rules-2, and the match died on a compatibility
    error the user had no obvious way to fix but to learn an internal
    Ruleset identity and pass it by hand.

    The identity it reaches is the *current* v4 gameplay contract: the
    permanent stable identity as of v4.0.0-rc1 Phase 2 (alpha2 from
    v4.0.0-alpha2 through Phase 1) -- see the explicit-alpha1 test below
    for the other half of that contract."""
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    _scaffold(tmp_path, "v2_alpha", api_version=2)
    _scaffold(tmp_path, "v2_beta", api_version=2)
    replay = tmp_path / "match" / "replay.jsonl"
    result = _run(
        "-m", "battle_engine.cli",
        "--ticks", "5", "--arena", "128", "--seed", "7",
        "--a-type", "v2_alpha", "--b-type", "v2_beta", "--b-start", "64",
        "--replay", str(replay), "--quiet",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    canonical = json.loads((replay.parent / "result.json").read_text())
    assert canonical["ruleset_id"] == "bytefray-rules-4"
    header = json.loads(replay.read_text().splitlines()[0])
    assert header["ruleset_id"] == "bytefray-rules-4"


def test_run_explicit_v4_alpha1_remains_reproducible(tmp_path, monkeypatch):
    """Naming alpha1 explicitly still runs and records an alpha1 match.

    Alpha2 taking the omitted-Ruleset default is a change of *preference*,
    not of availability: every historical alpha1 match must stay
    reproducible from the CLI by naming its Ruleset."""
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    _scaffold(tmp_path, "v2_alpha", api_version=2)
    _scaffold(tmp_path, "v2_beta", api_version=2)
    replay = tmp_path / "match" / "replay.jsonl"
    result = _run(
        "-m", "battle_engine.cli",
        "--ticks", "5", "--arena", "128", "--seed", "7",
        "--ruleset", "bytefray-rules-4-alpha1",
        "--a-type", "v2_alpha", "--b-type", "v2_beta", "--b-start", "64",
        "--replay", str(replay), "--quiet",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    canonical = json.loads((replay.parent / "result.json").read_text())
    assert canonical["ruleset_id"] == "bytefray-rules-4-alpha1"
    header = json.loads(replay.read_text().splitlines()[0])
    assert header["ruleset_id"] == "bytefray-rules-4-alpha1"


def test_run_omitted_ruleset_still_resolves_v2_for_api_v1_agents(tmp_path, monkeypatch):
    """The historical Agent API v1 default is untouched by API awareness."""
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    _scaffold(tmp_path, "v1_alpha", api_version=1)
    _scaffold(tmp_path, "v1_beta", api_version=1)
    replay = tmp_path / "match" / "replay.jsonl"
    result = _run(
        "-m", "battle_engine.cli",
        "--ticks", "5", "--arena", "128", "--seed", "7",
        "--a-type", "v1_alpha", "--b-type", "v1_beta", "--b-start", "64",
        "--replay", str(replay), "--quiet",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    canonical = json.loads((replay.parent / "result.json").read_text())
    assert canonical["ruleset_id"] == "bytefray-rules-2"


def test_run_omitted_ruleset_fails_closed_on_mixed_agent_api_roster(tmp_path, monkeypatch):
    """H1 fail-closed requirement: no single Ruleset runs Agent API v1 and
    v2 together, and that is knowable from discovered metadata, so
    resolution must say so rather than guess one and let the other entrant
    discover the mismatch later."""
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    _scaffold(tmp_path, "v1_agent", api_version=1)
    _scaffold(tmp_path, "v2_agent", api_version=2)
    replay = tmp_path / "match" / "replay.jsonl"
    result = _run(
        "-m", "battle_engine.cli",
        "--ticks", "5", "--arena", "128", "--seed", "7",
        "--a-type", "v1_agent", "--b-type", "v2_agent", "--b-start", "64",
        "--replay", str(replay), "--quiet",
        cwd=tmp_path,
    )
    assert result.returncode == 2
    assert result.stderr.startswith("ERROR:")
    assert "No Bytefray Ruleset supports" in result.stderr
    assert "Traceback (most recent call last)" not in result.stderr
    assert not replay.exists()
    assert not (replay.parent / "result.json").exists()


def test_run_explicit_ruleset_still_overrides_automatic_resolution(tmp_path, monkeypatch):
    """An explicit --ruleset stays authoritative, and an incompatible one
    keeps the Phase 1 clean configuration-error presentation."""
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    _scaffold(tmp_path, "v2_alpha", api_version=2)
    _scaffold(tmp_path, "v2_beta", api_version=2)
    replay = tmp_path / "match" / "replay.jsonl"
    result = _run(
        "-m", "battle_engine.cli",
        "--ticks", "5", "--arena", "128", "--seed", "7",
        "--a-type", "v2_alpha", "--b-type", "v2_beta", "--b-start", "64",
        "--ruleset", "bytefray-rules-2",
        "--replay", str(replay), "--quiet",
        cwd=tmp_path,
    )
    assert result.returncode == 2
    assert "does not support entrant metadata" in result.stderr
    assert "Traceback (most recent call last)" not in result.stderr
    assert not replay.exists()


def test_run_reports_ruleset_agent_unsupported_cleanly_with_no_traceback(tmp_path, monkeypatch):
    """H2 regression: an API-v2 Python agent under a Ruleset that only
    supports API v1 entrants (``bytefray-rules-2``) must surface as a
    concise, exit-2 configuration error -- not an unhandled
    ``RulesetAgentUnsupportedError`` traceback."""
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    _write_python_agent_v2(tmp_path, "v2_agent")
    _write_python_agent_v2(tmp_path, "v2_opponent")
    replay = tmp_path / "match" / "replay.jsonl"
    result = _run(
        "-m", "battle_engine.cli",
        "--ticks", "3", "--arena", "128", "--seed", "7",
        "--a-type", "v2_agent", "--b-type", "v2_opponent", "--b-start", "64",
        "--ruleset", "bytefray-rules-2",
        "--replay", str(replay), "--quiet",
        cwd=tmp_path,
    )
    assert result.returncode == 2
    assert result.stderr.startswith("ERROR:")
    assert "bytefray-rules-2" in result.stderr
    assert "does not support entrant metadata" in result.stderr
    assert "Traceback (most recent call last)" not in result.stderr
    assert not replay.exists()
    assert not (replay.parent / "result.json").exists()


def test_ruleset_flag_omitted_defaults_to_v1_for_vm_entrants(tmp_path):
    """RC1 default-Ruleset-defect fix, VM-compatibility guarantee (sec 9):
    an all-VM match with --ruleset omitted must keep resolving to Ruleset
    v1 exactly as before -- fixing the Python default must never make
    ordinary VM commands start failing or silently change ruleset."""
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


def test_ruleset_flag_omitted_defaults_to_v2_for_python_entrants(tmp_path, monkeypatch):
    """RC1 default-Ruleset-defect fix (sec 3/4): a Python-only match with
    --ruleset omitted now resolves to Ruleset v2, the same current-gameplay
    default Agent Designer has used since v3.0.0-alpha2 -- not the
    historical Ruleset-v1 fallback every native execution path used to
    fall back to. This is the core regression this fix exists to prevent."""
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    _write_python_agent(tmp_path, "alpha_agent")
    _write_python_agent(tmp_path, "beta_agent")
    replay = tmp_path / "match" / "replay.jsonl"
    result = _run(
        "-m", "battle_engine.cli",
        "--ticks", "3", "--arena", "128", "--seed", "7",
        "--a-type", "alpha_agent", "--b-type", "beta_agent", "--b-start", "64",
        "--replay", str(replay), "--quiet",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    canonical = json.loads((replay.parent / "result.json").read_text())
    assert canonical["ruleset_id"] == "bytefray-rules-2"
    header = json.loads(replay.read_text().splitlines()[0])
    assert header["ruleset_id"] == "bytefray-rules-2"


def test_ruleset_flag_omitted_mixed_runtime_fails_cleanly(tmp_path, monkeypatch):
    """A mixed Python/VM roster with --ruleset omitted keeps its existing,
    Ruleset-independent rejection (NativeMatchService.run's homogeneous-
    composition guard fires before any Ruleset is even consulted) -- the
    RC1 default-Ruleset-defect fix does not change this."""
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    _write_python_agent(tmp_path, "alpha_agent")
    replay = tmp_path / "match" / "replay.jsonl"
    result = _run(
        "-m", "battle_engine.cli",
        "--ticks", "3", "--arena", "128", "--seed", "7",
        "--a-type", "alpha_agent", "--b-type", "runner", "--b-start", "64",
        "--replay", str(replay), "--quiet",
        cwd=tmp_path,
    )
    assert result.returncode == 2
    assert "all VM entrants or all Python entrants" in result.stderr
    assert not replay.exists()
    assert not (replay.parent / "result.json").exists()


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


def test_cli_help_lists_product_rulesets_including_v4_alpha1():
    result = _run("-m", "battle_engine.cli", "--help")
    assert result.returncode == 0
    assert "bytefray-rules-1" in result.stdout
    assert "bytefray-rules-2" in result.stdout
    assert "bytefray-rules-4-alpha1" in result.stdout
    assert "bytefray-rules-2-alpha1" not in result.stdout
    assert "bytefray-rules-3-alpha1" not in result.stdout


def test_run_help_documents_the_trace_flag():
    result = _run("-m", "battle_engine.cli", "--help")
    assert result.returncode == 0
    assert "--trace TRACE" in result.stdout


def test_trace_flag_accepts_an_explicit_path():
    from battle_engine.cli import parse_args

    args = parse_args(["--trace", "/tmp/example-trace.jsonl"])
    assert args.trace == "/tmp/example-trace.jsonl"


def test_trace_flag_omitted_is_none_in_parsed_arguments():
    from battle_engine.cli import parse_args

    args = parse_args(["--a-type", "writer", "--b-type", "runner"])
    assert args.trace is None


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
