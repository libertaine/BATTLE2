from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from battle_engine import command
from battle_engine.agent_api import ActionKind, MatchContext, Observation, load_python_agent
from battle_engine.agent_scaffold import (
    DEFAULT_TEMPLATE,
    TEMPLATE_DIRECTORIES,
    AgentScaffoldError,
    create_agent,
    main,
    template_resource_dir,
    validate_agent_id,
    validate_template,
)
from battle_engine.agents import discover_agents
from battle_engine.starters import ensure_starter_agents

ROOT = Path(__file__).resolve().parents[2]


def _resource_root() -> Path:
    return ROOT


def _context(agent_id: str = "A") -> MatchContext:
    import random

    return MatchContext(
        agent_id=agent_id,
        seed=1,
        arena_size=256,
        tick_limit=10,
        action_budget=1,
        rng=random.Random(1),
    )


def _observation(agent_id: str = "A") -> Observation:
    return Observation(
        tick=0,
        agent_id=agent_id,
        pc=0,
        register_a=0,
        register_p=0,
        zero_flag=False,
        last_read=None,
        alive=True,
    )


# --------------------------------------------------------------------------
# Successful creation
# --------------------------------------------------------------------------


def test_creates_expected_layout_and_returns_paths(tmp_path):
    result = create_agent("example", data_root=tmp_path, resource_root=_resource_root())

    agent_dir = tmp_path / "agents" / "example"
    assert result.agent_id == "example"
    assert result.manifest_path == agent_dir / "agent.yaml"
    assert result.source_path == agent_dir / "agent.py"
    assert sorted(p.name for p in agent_dir.iterdir()) == ["agent.py", "agent.yaml"]
    # No stray temp directory left behind after a successful publish.
    assert sorted(p.name for p in (tmp_path / "agents").iterdir()) == ["example"]


def test_cli_prints_expected_lines(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    exit_code = main(["example"])
    out = capsys.readouterr().out

    agent_dir = tmp_path / "agents" / "example"
    assert exit_code == 0
    assert "agent: example" in out
    assert f"manifest: {agent_dir / 'agent.yaml'}" in out
    assert f"source: {agent_dir / 'agent.py'}" in out
    assert "bytefray run --a-type example --b-type <opponent>" in out


def test_generated_content_is_byte_identical_across_agent_ids(tmp_path):
    create_agent("agent_one", data_root=tmp_path / "one", resource_root=_resource_root())
    create_agent("agent-two", data_root=tmp_path / "two", resource_root=_resource_root())

    one_dir = tmp_path / "one" / "agents" / "agent_one"
    two_dir = tmp_path / "two" / "agents" / "agent-two"
    assert (one_dir / "agent.yaml").read_bytes() == (two_dir / "agent.yaml").read_bytes()
    assert (one_dir / "agent.py").read_bytes() == (two_dir / "agent.py").read_bytes()


def test_two_sequential_creations_both_succeed(tmp_path):
    create_agent("first", data_root=tmp_path, resource_root=_resource_root())
    create_agent("second", data_root=tmp_path, resource_root=_resource_root())

    assert (tmp_path / "agents" / "first" / "agent.py").is_file()
    assert (tmp_path / "agents" / "second" / "agent.py").is_file()


# --------------------------------------------------------------------------
# Generated file content/contract
# --------------------------------------------------------------------------


def test_generated_manifest_parses_with_expected_fields(tmp_path):
    create_agent("example", data_root=tmp_path, resource_root=_resource_root())

    specs = discover_agents(tmp_path)
    spec = specs["example"]
    assert spec.kind == "python"
    assert spec.api_version == 1
    assert spec.entry_point == "agent.py:create_agent"
    assert spec.version == "0.1.0"


def test_generated_manifest_omits_deliberately_excluded_fields(tmp_path):
    create_agent("example", data_root=tmp_path, resource_root=_resource_root())

    specs = discover_agents(tmp_path)
    manifest = specs["example"].manifest
    for field in ("name", "display", "defaults", "description"):
        assert field not in manifest


def test_generated_agent_loads_and_writes_a_deterministic_byte(tmp_path):
    create_agent("example", data_root=tmp_path, resource_root=_resource_root())

    spec = discover_agents(tmp_path)["example"]
    loaded = load_python_agent(spec)
    loaded.instance.reset(_context())
    action = loaded.instance.act(_observation())

    assert action.kind == ActionKind.WRITE
    assert action.operand in range(256)
    assert action.value == 0xA5


# --------------------------------------------------------------------------
# Immediate discovery
# --------------------------------------------------------------------------


def test_created_agent_is_immediately_discoverable_in_process(tmp_path):
    create_agent("fresh", data_root=tmp_path, resource_root=_resource_root())

    assert "fresh" in discover_agents(tmp_path)


def _subprocess_env(data_root: Path) -> dict[str, str]:
    env = dict(os.environ, BYTEFRAY_ROOT=str(data_root))
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "engine" / "src"), str(ROOT / "client" / "src"), str(ROOT)]
    )
    return env


def test_end_to_end_create_then_run_via_subprocess(tmp_path):
    data_root = tmp_path / "data"
    env = _subprocess_env(data_root)

    created = subprocess.run(
        [sys.executable, "-m", "battle_engine", "agents", "create", "scaffolded"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert created.returncode == 0, created.stderr

    replay = tmp_path / "replay.jsonl"
    played = subprocess.run(
        [
            sys.executable,
            "-m",
            "battle_engine",
            "run",
            "--a-type",
            "scaffolded",
            "--b-type",
            "scaffolded",
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
    assert played.returncode == 0, played.stderr
    assert replay.is_file()


def test_command_dispatch_reaches_scaffold_module(tmp_path, monkeypatch):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    assert command.main(["agents", "create", "dispatched"]) == 0
    assert (tmp_path / "agents" / "dispatched" / "agent.py").is_file()


def test_agents_help_mentions_create(capsys):
    assert command.main(["agents", "--help"]) == 0
    assert "create" in capsys.readouterr().out.lower()


# --------------------------------------------------------------------------
# Duplicate protection
# --------------------------------------------------------------------------


def test_duplicate_directory_is_rejected_and_first_content_unchanged(tmp_path):
    create_agent("dup", data_root=tmp_path, resource_root=_resource_root())
    original = (tmp_path / "agents" / "dup" / "agent.py").read_bytes()

    with pytest.raises(AgentScaffoldError, match="already exists"):
        create_agent("dup", data_root=tmp_path, resource_root=_resource_root())

    assert (tmp_path / "agents" / "dup" / "agent.py").read_bytes() == original


def test_destination_file_collision_is_rejected(tmp_path):
    stray = tmp_path / "agents" / "stray"
    stray.parent.mkdir(parents=True)
    stray.write_text("not a directory", encoding="utf-8")

    with pytest.raises(AgentScaffoldError, match="already exists"):
        create_agent("stray", data_root=tmp_path, resource_root=_resource_root())

    assert stray.is_file()
    assert stray.read_text(encoding="utf-8") == "not a directory"


def test_creating_over_a_materialized_starter_is_rejected(tmp_path):
    ensure_starter_agents(resource_root=_resource_root(), data_root=tmp_path)

    with pytest.raises(AgentScaffoldError, match="already exists"):
        create_agent("runner", data_root=tmp_path, resource_root=_resource_root())


def test_creating_over_an_unmaterialized_starter_name_succeeds(tmp_path):
    # "bomber" is a compiled-in VM built-in with no starter directory, so no
    # prior ensure_starter_agents() call has populated agents/bomber/.
    result = create_agent("bomber", data_root=tmp_path, resource_root=_resource_root())
    assert result.agent_id == "bomber"


# --------------------------------------------------------------------------
# Invalid / path-traversal IDs
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "agent_id",
    [
        "",
        "..",
        "../evil",
        "a/b",
        "a\\b",
        "-leading-dash",
        "_leading-underscore",
        "a" * 65,
        "bad\x00name",
    ],
)
def test_invalid_ids_are_rejected_without_mutation(tmp_path, agent_id):
    with pytest.raises(AgentScaffoldError):
        create_agent(agent_id, data_root=tmp_path, resource_root=_resource_root())

    assert not (tmp_path / "agents").exists()


def test_id_with_harmless_double_dot_substring_is_rejected_by_the_stricter_allowlist(tmp_path):
    with pytest.raises(AgentScaffoldError):
        validate_agent_id("not..actually..traversing")


def test_max_length_boundary_is_accepted(tmp_path):
    agent_id = "a" * 64
    result = create_agent(agent_id, data_root=tmp_path, resource_root=_resource_root())
    assert result.agent_id == agent_id


def test_cli_invalid_id_reports_error_without_traceback(tmp_path, capsys):
    exit_code = main(["../evil"])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Traceback" not in captured.err
    assert captured.out == ""


# --------------------------------------------------------------------------
# Custom BYTEFRAY_ROOT
# --------------------------------------------------------------------------


def test_custom_bytefray_root_is_honored(monkeypatch, tmp_path):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))

    assert main(["rooted"]) == 0
    assert (tmp_path / "agents" / "rooted" / "agent.py").is_file()


# --------------------------------------------------------------------------
# Filesystem failure behavior
# --------------------------------------------------------------------------


def test_failure_writing_template_files_leaves_no_temp_directory(tmp_path, monkeypatch):
    import battle_engine.agent_scaffold as scaffold

    real_copyfileobj = scaffold.shutil.copyfileobj
    calls = {"count": 0}

    def flaky_copy(fsrc, fdst):
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("simulated disk failure")
        return real_copyfileobj(fsrc, fdst)

    monkeypatch.setattr(scaffold.shutil, "copyfileobj", flaky_copy)

    with pytest.raises(OSError, match="simulated disk failure"):
        create_agent("broken", data_root=tmp_path, resource_root=_resource_root())

    agents_dir = tmp_path / "agents"
    assert not (agents_dir / "broken").exists()
    assert list(agents_dir.glob(".tmp-*")) == []


def test_rename_failure_never_populates_the_real_destination(tmp_path, monkeypatch):
    import battle_engine.agent_scaffold as scaffold

    def failing_rename(src, dst):
        raise OSError("simulated rename failure")

    monkeypatch.setattr(scaffold.os, "rename", failing_rename)

    with pytest.raises(OSError, match="simulated rename failure"):
        create_agent("never-published", data_root=tmp_path, resource_root=_resource_root())

    assert not (tmp_path / "agents" / "never-published").exists()


def test_cli_reports_io_failure_without_traceback(tmp_path, monkeypatch, capsys):
    import battle_engine.agent_scaffold as scaffold

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))

    def failing_mkdir(self, *args, **kwargs):
        raise PermissionError("simulated permission error")

    monkeypatch.setattr(scaffold.Path, "mkdir", failing_mkdir)

    exit_code = main(["blocked"])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Traceback" not in captured.err
    assert "simulated permission error" in captured.err


# --------------------------------------------------------------------------
# Windows/POSIX path semantics
# --------------------------------------------------------------------------


def test_data_root_with_spaces_works(tmp_path):
    data_root = tmp_path / "Writable Data With Spaces"
    result = create_agent("example", data_root=data_root, resource_root=_resource_root())
    assert result.source_path.is_file()


def test_generated_files_use_lf_line_endings(tmp_path):
    create_agent("example", data_root=tmp_path, resource_root=_resource_root())

    agent_dir = tmp_path / "agents" / "example"
    for filename in ("agent.yaml", "agent.py"):
        content = (agent_dir / filename).read_bytes()
        assert b"\r\n" not in content


# --------------------------------------------------------------------------
# Phase 2 (v3.0): scaffold template choice
# --------------------------------------------------------------------------


def test_default_template_is_blank():
    assert DEFAULT_TEMPLATE == "blank"
    assert set(TEMPLATE_DIRECTORIES) == {"blank", "annotated"}


def test_omitting_template_is_byte_identical_to_explicit_blank(tmp_path):
    create_agent("default_choice", data_root=tmp_path / "a", resource_root=_resource_root())
    create_agent(
        "explicit_blank",
        data_root=tmp_path / "b",
        resource_root=_resource_root(),
        template="blank",
    )

    default_dir = tmp_path / "a" / "agents" / "default_choice"
    explicit_dir = tmp_path / "b" / "agents" / "explicit_blank"
    assert (default_dir / "agent.py").read_bytes() == (explicit_dir / "agent.py").read_bytes()
    assert (default_dir / "agent.yaml").read_bytes() == (explicit_dir / "agent.yaml").read_bytes()


def test_annotated_template_differs_from_blank_and_is_valid(tmp_path):
    create_agent(
        "annotated_agent", data_root=tmp_path, resource_root=_resource_root(), template="annotated"
    )

    agent_dir = tmp_path / "agents" / "annotated_agent"
    blank_source = template_resource_dir(_resource_root(), "blank") / "agent.py"
    assert (agent_dir / "agent.py").read_bytes() != blank_source.read_bytes()

    spec = discover_agents(tmp_path)["annotated_agent"]
    loaded = load_python_agent(spec)
    loaded.instance.reset(_context())
    action = loaded.instance.act(_observation())
    assert action.kind == ActionKind.READ


def test_annotated_template_manifest_omits_deliberately_excluded_fields(tmp_path):
    create_agent("annotated_agent", data_root=tmp_path, resource_root=_resource_root(), template="annotated")

    manifest = discover_agents(tmp_path)["annotated_agent"].manifest
    for field in ("name", "display", "defaults", "description"):
        assert field not in manifest


def test_unknown_template_is_rejected_without_mutation(tmp_path):
    with pytest.raises(AgentScaffoldError, match="Unknown template"):
        create_agent("nope", data_root=tmp_path, resource_root=_resource_root(), template="bogus")

    assert not (tmp_path / "agents").exists()


def test_validate_template_accepts_known_and_rejects_unknown():
    assert validate_template("blank") == "blank"
    assert validate_template("annotated") == "annotated"
    with pytest.raises(AgentScaffoldError, match="Unknown template"):
        validate_template("bogus")


def test_cli_template_flag_selects_annotated_content(tmp_path, monkeypatch):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    assert main(["from_cli", "--template", "annotated"]) == 0

    agent_py = (tmp_path / "agents" / "from_cli" / "agent.py").read_bytes()
    annotated_source = (template_resource_dir(_resource_root(), "annotated") / "agent.py").read_bytes()
    assert agent_py == annotated_source


def test_cli_template_flag_rejects_unknown_choice(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    with pytest.raises(SystemExit) as excinfo:
        main(["from_cli", "--template", "bogus"])
    assert excinfo.value.code == 2
    assert not (tmp_path / "agents").exists()
