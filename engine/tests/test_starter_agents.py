from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from battle_engine import cli, paths
from battle_engine.agents import discover_agents
from battle_engine.starters import STARTER_AGENT_NAMES, ensure_starter_agents

from app.services.agent_catalog import AgentCatalog


def _resource_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_empty_data_root_receives_all_starters_and_creates_agents_directory(tmp_path):
    data_root = tmp_path / "Writable Data With Spaces"

    created = ensure_starter_agents(resource_root=_resource_root(), data_root=data_root)

    expected = {
        (data_root / "agents" / name / "agent.yaml").resolve()
        for name in STARTER_AGENT_NAMES
    }
    assert set(created) == expected
    assert all(path.is_file() for path in expected)


def test_existing_starter_and_custom_files_are_never_modified(tmp_path):
    data_root = tmp_path / "data"
    existing = data_root / "agents" / "runner" / "agent.yaml"
    custom = data_root / "agents" / "my_custom_agent" / "notes.txt"
    existing.parent.mkdir(parents=True)
    custom.parent.mkdir(parents=True)
    existing.write_text("user-owned runner", encoding="utf-8")
    custom.write_text("keep me", encoding="utf-8")

    created = ensure_starter_agents(resource_root=_resource_root(), data_root=data_root)

    assert existing.read_text(encoding="utf-8") == "user-owned runner"
    assert custom.read_text(encoding="utf-8") == "keep me"
    assert existing.resolve() not in created


def test_repeated_initialization_is_idempotent(tmp_path):
    first = ensure_starter_agents(resource_root=_resource_root(), data_root=tmp_path)
    second = ensure_starter_agents(resource_root=_resource_root(), data_root=tmp_path)

    assert len(first) == len(STARTER_AGENT_NAMES)
    assert second == []


def test_source_resource_lookup_uses_repository_resources(tmp_path):
    created = ensure_starter_agents(data_root=tmp_path)

    assert len(created) == len(STARTER_AGENT_NAMES)


def test_installed_linux_initializes_starters_in_xdg_data_home(
    monkeypatch, tmp_path
):
    xdg_data = tmp_path / "isolated xdg data"
    monkeypatch.setattr(paths, "_source_checkout_root", lambda: None)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_data))
    monkeypatch.setenv("HOME", str(tmp_path / "unused home"))

    first = ensure_starter_agents(resource_root=_resource_root())
    second = ensure_starter_agents(resource_root=_resource_root())

    data_root = xdg_data / "battle2"
    assert set(first) == {
        (data_root / "agents" / name / "agent.yaml").resolve()
        for name in STARTER_AGENT_NAMES
    }
    assert second == []


def test_frozen_lookup_reads_meipass_and_writes_beside_executable(monkeypatch, tmp_path):
    extraction = tmp_path / "Read Only Extraction"
    packaged_resources = extraction / "battle_engine" / "data" / "starter_agents"
    source_resources = (
        _resource_root() / "engine" / "src" / "battle_engine" / "data" / "starter_agents"
    )
    for name in STARTER_AGENT_NAMES:
        target = packaged_resources / name
        target.mkdir(parents=True)
        target.joinpath("agent.yaml").write_bytes(
            source_resources.joinpath(name, "agent.yaml").read_bytes()
        )
    executable = tmp_path / "Portable Build With Spaces" / "battle-agent-designer.exe"
    executable.parent.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(extraction), raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.delenv("BATTLE2_ROOT", raising=False)
    monkeypatch.delenv("BATTLE_ROOT", raising=False)

    created = ensure_starter_agents()

    assert all(path.is_relative_to(executable.parent / "agents") for path in created)
    assert not (extraction / "agents").exists()


def test_missing_resource_set_has_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="Starter-agent resource directory not found"):
        ensure_starter_agents(resource_root=tmp_path / "missing", data_root=tmp_path / "data")


def test_malformed_starter_manifest_has_clear_error(tmp_path):
    resources = tmp_path / "resources" / "battle_engine" / "data" / "starter_agents"
    for name in STARTER_AGENT_NAMES:
        agent_dir = resources / name
        agent_dir.mkdir(parents=True)
        agent_dir.joinpath("agent.yaml").write_text(
            "not json" if name == "runner" else json.dumps({"name": name}),
            encoding="utf-8",
        )

    with pytest.raises(ValueError, match="runner.*malformed manifest"):
        ensure_starter_agents(resource_root=tmp_path / "resources", data_root=tmp_path / "data")


def test_every_starter_parses_and_designer_catalog_discovers_it(tmp_path):
    ensure_starter_agents(resource_root=_resource_root(), data_root=tmp_path)

    specs = discover_agents(tmp_path)
    rows = AgentCatalog(tmp_path).list_agents()

    assert set(specs) == set(STARTER_AGENT_NAMES)
    assert {row.meta["name"] for row in rows} == set(STARTER_AGENT_NAMES)


def test_manifest_only_starters_run_with_existing_builtin_implementations(
    monkeypatch, tmp_path
):
    ensure_starter_agents(resource_root=_resource_root(), data_root=tmp_path)
    monkeypatch.setenv("BATTLE2_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    result = cli.main(
        [
            "--a-type", "seeker",
            "--b-type", "writer",
            "--ticks", "2",
            "--replay", str(tmp_path / "runs" / "starter-match.jsonl"),
            "--quiet",
        ]
    )

    assert result == 0
    assert (tmp_path / "runs" / "starter-match.jsonl").is_file()
