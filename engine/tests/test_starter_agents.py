from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from battle_engine import cli, paths, tournament_cli
from battle_engine.agents import discover_agents, resolve_agent
from battle_engine.starters import STARTER_AGENT_NAMES, ensure_starter_agents

from app.services.agent_catalog import AgentCatalog


def _resource_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _starter_source_dir(name: str) -> Path:
    return _resource_root() / "engine" / "src" / "battle_engine" / "data" / "starter_agents" / name


def _expected_starter_files(data_root: Path) -> set[Path]:
    """Every file a starter ships, mapped into the destination catalog.

    The four native VM starters ship only ``agent.yaml``; the Python
    starters (added in v0.6.1) also ship ``agent.py`` -- computed from the
    actual source tree rather than hard-coded, so this stays correct
    regardless of which starters carry how many files.
    """

    expected: set[Path] = set()
    for name in STARTER_AGENT_NAMES:
        source_dir = _starter_source_dir(name)
        for source in source_dir.rglob("*"):
            if source.is_file():
                relative = source.relative_to(source_dir)
                expected.add((data_root / "agents" / name / relative).resolve())
    return expected


def _write_synthetic_roster(resources_root: Path, *, malformed: frozenset[str] = frozenset()) -> None:
    """A minimal, disposable stand-in for the real bundled starter tree.

    Every real starter name (:data:`STARTER_AGENT_NAMES`) gets a
    manifest-only ``agent.yaml`` -- valid unless its name is in
    ``malformed``, which gets unparsable JSON instead. Used to exercise
    per-starter fault isolation (Phase 3 M2) without ever touching the real
    starter resource tree.
    """

    base = resources_root / "battle_engine" / "data" / "starter_agents"
    for name in STARTER_AGENT_NAMES:
        agent_dir = base / name
        agent_dir.mkdir(parents=True)
        agent_dir.joinpath("agent.yaml").write_text(
            "not json" if name in malformed else json.dumps({"name": name}),
            encoding="utf-8",
        )


def test_empty_data_root_receives_all_starters_and_creates_agents_directory(tmp_path):
    data_root = tmp_path / "Writable Data With Spaces"

    result = ensure_starter_agents(resource_root=_resource_root(), data_root=data_root)

    expected = _expected_starter_files(data_root)
    assert set(result.installed) == expected
    assert all(path.is_file() for path in expected)
    assert result.errors == ()


def test_existing_starter_and_custom_files_are_never_modified(tmp_path):
    data_root = tmp_path / "data"
    existing = data_root / "agents" / "runner" / "agent.yaml"
    custom = data_root / "agents" / "my_custom_agent" / "notes.txt"
    existing.parent.mkdir(parents=True)
    custom.parent.mkdir(parents=True)
    existing.write_text("user-owned runner", encoding="utf-8")
    custom.write_text("keep me", encoding="utf-8")

    result = ensure_starter_agents(resource_root=_resource_root(), data_root=data_root)

    assert existing.read_text(encoding="utf-8") == "user-owned runner"
    assert custom.read_text(encoding="utf-8") == "keep me"
    assert existing.resolve() not in result.installed


def test_repeated_initialization_is_idempotent(tmp_path):
    first = ensure_starter_agents(resource_root=_resource_root(), data_root=tmp_path)
    second = ensure_starter_agents(resource_root=_resource_root(), data_root=tmp_path)

    assert len(first.installed) == len(_expected_starter_files(tmp_path))
    assert second.installed == ()


def test_source_resource_lookup_uses_repository_resources(tmp_path):
    result = ensure_starter_agents(data_root=tmp_path)

    assert len(result.installed) == len(_expected_starter_files(tmp_path))


def test_installed_linux_initializes_starters_in_xdg_data_home(
    monkeypatch, tmp_path
):
    xdg_data = tmp_path / "isolated xdg data"
    data_root = paths.installed_data_root(
        {"XDG_DATA_HOME": str(xdg_data), "HOME": str(tmp_path / "unused home")},
        platform="linux",
    )
    monkeypatch.setattr(paths, "get_data_root", lambda environ=None: data_root)
    monkeypatch.setattr("battle_engine.starters.get_data_root", lambda: data_root)

    first = ensure_starter_agents(resource_root=_resource_root())
    second = ensure_starter_agents(resource_root=_resource_root())

    assert set(first.installed) == _expected_starter_files(data_root)
    assert second.installed == ()


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
    executable = tmp_path / "Portable Build With Spaces" / "bytefray-agent-designer.exe"
    executable.parent.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(extraction), raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.delenv("BYTEFRAY_ROOT", raising=False)

    result = ensure_starter_agents()

    assert all(path.is_relative_to(executable.parent / "agents") for path in result.installed)
    assert not (extraction / "agents").exists()


def test_missing_resource_set_has_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="Starter-agent resource directory not found"):
        ensure_starter_agents(resource_root=tmp_path / "missing", data_root=tmp_path / "data")


# ---------------------------------------------------------------------------
# Phase 3 M2: malformed-starter fault isolation
# ---------------------------------------------------------------------------


def test_malformed_starter_is_isolated_valid_starters_still_install(tmp_path):
    """One malformed bundled starter is recorded as an error and skipped; it
    must not prevent every other valid starter from installing. This is the
    fault-isolation fix: eagerly validating the whole roster before any
    copying began used to abort the entire bootstrap -- 0/16 starters
    installed -- for a single bad manifest anywhere in the roster."""

    resources = tmp_path / "resources"
    _write_synthetic_roster(resources, malformed=frozenset({"runner"}))

    result = ensure_starter_agents(resource_root=resources, data_root=tmp_path / "data")

    installed_names = {path.parent.name for path in result.installed}
    assert installed_names == set(STARTER_AGENT_NAMES) - {"runner"}
    assert not (tmp_path / "data" / "agents" / "runner").exists()
    assert len(result.errors) == 1
    assert result.errors[0].name == "runner"
    assert "malformed manifest" in result.errors[0].message


def test_existing_unrelated_agent_untouched_when_a_starter_is_malformed(tmp_path):
    resources = tmp_path / "resources"
    _write_synthetic_roster(resources, malformed=frozenset({"runner"}))
    data_root = tmp_path / "data"
    custom = data_root / "agents" / "my_custom_agent" / "notes.txt"
    custom.parent.mkdir(parents=True)
    custom.write_text("keep me", encoding="utf-8")

    ensure_starter_agents(resource_root=resources, data_root=data_root)

    assert custom.read_text(encoding="utf-8") == "keep me"


def test_requesting_malformed_starter_after_partial_bootstrap_fails_clearly(tmp_path):
    """The malformed starter itself stays unusable: it was never installed,
    so resolving it by name fails the same clear way any unknown agent
    name does -- fail-closed, never a silent fallback."""

    resources = tmp_path / "resources"
    _write_synthetic_roster(resources, malformed=frozenset({"runner"}))
    data_root = tmp_path / "data"

    ensure_starter_agents(resource_root=resources, data_root=data_root)

    with pytest.raises(SystemExit, match="Unknown agent 'runner'"):
        resolve_agent(data_root, "runner")


def test_unrelated_match_proceeds_despite_unused_malformed_starter(monkeypatch, tmp_path, capsys):
    """Product-path control for ``bytefray run``: a malformed bundled
    starter the requested match never references must not block it."""

    resources = tmp_path / "resources"
    _write_synthetic_roster(resources, malformed=frozenset({"v4_scout"}))
    data_root = tmp_path / "data"
    monkeypatch.setattr("battle_engine.starters.get_resource_root", lambda: resources)
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    monkeypatch.chdir(tmp_path)

    result = cli.main(
        [
            "--a-type", "seeker",
            "--b-type", "writer",
            "--ticks", "2",
            "--replay", str(data_root / "runs" / "unrelated-match.jsonl"),
            "--quiet",
        ]
    )

    assert result == 0
    assert (data_root / "runs" / "unrelated-match.jsonl").is_file()
    assert "v4_scout" in capsys.readouterr().err


def test_agents_list_warns_but_does_not_fail_on_malformed_starter(monkeypatch, tmp_path, capsys):
    """Product-path control for ``bytefray agents --list``: the malformed
    starter is reported, valid starters are still discovered, exit is 0."""

    resources = tmp_path / "resources"
    _write_synthetic_roster(resources, malformed=frozenset({"v4_scout"}))
    data_root = tmp_path / "data"
    monkeypatch.setattr("battle_engine.starters.get_resource_root", lambda: resources)
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))

    result = cli.main(["--list-agents"])

    assert result == 0
    captured = capsys.readouterr()
    assert "v4_scout" in captured.err
    assert "runner" in captured.out


def test_tournament_proceeds_despite_unused_malformed_starter(monkeypatch, tmp_path, capsys):
    """Product-path control for ``bytefray tournament``: same contract as
    ``bytefray run`` -- an unused malformed starter must not block it."""

    resources = tmp_path / "resources"
    _write_synthetic_roster(resources, malformed=frozenset({"v4_scout"}))
    data_root = tmp_path / "data"
    monkeypatch.setattr("battle_engine.starters.get_resource_root", lambda: resources)
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    monkeypatch.chdir(tmp_path)

    result = tournament_cli.main(
        [
            "seeker", "writer",
            "--rounds", "1",
            "--ticks", "3",
            "--quota", "2",
            "--quiet",
        ]
    )

    assert result == 0
    assert "v4_scout" in capsys.readouterr().err


def test_every_starter_parses_and_designer_catalog_discovers_it(tmp_path):
    result = ensure_starter_agents(resource_root=_resource_root(), data_root=tmp_path)
    assert result.errors == ()

    specs = discover_agents(tmp_path)
    rows = AgentCatalog(tmp_path).list_agents()

    assert set(specs) == set(STARTER_AGENT_NAMES)
    assert {row.meta["name"] for row in rows} == set(STARTER_AGENT_NAMES)


def test_manifest_only_starters_run_with_existing_builtin_implementations(
    monkeypatch, tmp_path
):
    ensure_starter_agents(resource_root=_resource_root(), data_root=tmp_path)
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
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
