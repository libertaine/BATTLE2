"""``bytefray agents export|import|package show`` CLI (docs/specs/agent_package.md Sec 11).

Thin-wrapper tests: argument parsing, exit codes, human-readable and
``--json`` output shape, and the top-level ``command.main`` dispatcher
wiring. Domain-level behavior (safety, integrity, provenance) is covered
by ``test_agent_package.py``; this file only proves the CLI surface calls
through to it correctly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from battle_engine.agent_package_cli import export_main, import_main, package_main
from battle_engine.command import main as command_main


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _make_python_agent(root: Path, name: str = "hunter") -> Path:
    agent_dir = root / "agents" / name
    _write(agent_dir / "agent.yaml", b'{"kind": "python", "api_version": 1, "version": "1.0"}')
    _write(agent_dir / "agent.py", b"def create_agent():\n    return None\n")
    return agent_dir


@pytest.fixture(autouse=True)
def _data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "data_root"
    root.mkdir()
    monkeypatch.setenv("BYTEFRAY_ROOT", str(root))
    return root


def _run_export(args: list[str], capsys: pytest.CaptureFixture) -> tuple[int, str, str]:
    code = export_main(args)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _run_import(args: list[str], capsys: pytest.CaptureFixture) -> tuple[int, str, str]:
    code = import_main(args)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _run_package(args: list[str], capsys: pytest.CaptureFixture) -> tuple[int, str, str]:
    code = package_main(args)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


def test_export_human_output(_data_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    _make_python_agent(_data_root)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    code, out, _ = _run_export(["hunter", "--output", str(out_dir)], capsys)

    assert code == 0
    assert "Exported agent: hunter" in out
    assert "Revision: agent-revision_" in out
    assert "SHA-256:" in out
    assert any(out_dir.iterdir())


def test_export_json_output(_data_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    _make_python_agent(_data_root)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    code, out, _ = _run_export(["hunter", "--output", str(out_dir), "--json"], capsys)

    assert code == 0
    payload = json.loads(out)
    assert payload["agent_id"] == "hunter"
    assert payload["agent_revision_id"].startswith("agent-revision_")
    assert Path(payload["package_path"]).is_file()


def test_export_unknown_agent_reports_error(_data_root: Path, capsys: pytest.CaptureFixture) -> None:
    code, _, err = _run_export(["does-not-exist"], capsys)
    assert code == 2
    assert "does-not-exist" in err


def test_export_builtin_agent_reports_typed_error(_data_root: Path, capsys: pytest.CaptureFixture) -> None:
    _write((_data_root / "agents" / "manifest_only" / "agent.yaml"), b'{"display": "starter"}')
    code, _, err = _run_export(["manifest_only"], capsys)
    assert code == 2
    assert "package_unsupported_kind" in err


# ---------------------------------------------------------------------------
# package show
# ---------------------------------------------------------------------------


def test_package_show_human_output(_data_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    _make_python_agent(_data_root)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    _run_export(["hunter", "--output", str(out_dir)], capsys)
    package_file = next(out_dir.iterdir())

    code, out, _ = _run_package(["show", str(package_file)], capsys)

    assert code == 0
    assert "valid: True" in out
    assert "agent_id: hunter" in out
    assert "importable on this installation: True" in out
    assert "not a safety or trust statement" in out


def test_package_show_json_output(_data_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    _make_python_agent(_data_root)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    _run_export(["hunter", "--output", str(out_dir)], capsys)
    package_file = next(out_dir.iterdir())

    code, out, _ = _run_package(["show", str(package_file), "--json"], capsys)

    assert code == 0
    payload = json.loads(out)
    assert payload["valid"] is True
    assert payload["compatible"] is True
    assert payload["agent_id"] == "hunter"


def test_package_show_invalid_file_reports_error_exit(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    bogus = tmp_path / "bogus.bytefray-agent"
    bogus.write_bytes(b"not a zip")

    code, out, _ = _run_package(["show", str(bogus)], capsys)

    assert code == 2
    assert "valid: False" in out


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------


def test_import_human_output(_data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    export_source_root = tmp_path / "export_source"
    export_source_root.mkdir()
    _make_python_agent(export_source_root)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    monkeypatch.setenv("BYTEFRAY_ROOT", str(export_source_root))
    _run_export(["hunter", "--output", str(out_dir)], capsys)
    package_file = next(out_dir.iterdir())

    monkeypatch.setenv("BYTEFRAY_ROOT", str(_data_root))
    code, out, _ = _run_import([str(package_file)], capsys)

    assert code == 0
    assert "Imported hunter" in out
    assert "executable" in out
    assert (_data_root / "agents" / "hunter").is_dir()


def test_import_json_output_and_as_flag(_data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    export_source_root = tmp_path / "export_source"
    export_source_root.mkdir()
    _make_python_agent(export_source_root)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    monkeypatch.setenv("BYTEFRAY_ROOT", str(export_source_root))
    _run_export(["hunter", "--output", str(out_dir)], capsys)
    package_file = next(out_dir.iterdir())

    monkeypatch.setenv("BYTEFRAY_ROOT", str(_data_root))
    code, out, _ = _run_import([str(package_file), "--as", "hunter2", "--json"], capsys)

    assert code == 0
    payload = json.loads(out)
    assert payload["agent_id"] == "hunter2"
    assert (_data_root / "agents" / "hunter2").is_dir()


def test_import_collision_reports_error_without_mutation(
    _data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    export_source_root = tmp_path / "export_source"
    export_source_root.mkdir()
    _make_python_agent(export_source_root)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    monkeypatch.setenv("BYTEFRAY_ROOT", str(export_source_root))
    _run_export(["hunter", "--output", str(out_dir)], capsys)
    package_file = next(out_dir.iterdir())

    monkeypatch.setenv("BYTEFRAY_ROOT", str(_data_root))
    existing = _make_python_agent(_data_root)
    _write(existing / "marker.txt", b"do-not-touch")

    code, _, err = _run_import([str(package_file)], capsys)

    assert code == 2
    assert "package_import_conflict" in err
    assert (existing / "marker.txt").read_bytes() == b"do-not-touch"


def test_import_already_present_is_noop_success(
    _data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    export_source_root = tmp_path / "export_source"
    export_source_root.mkdir()
    _make_python_agent(export_source_root)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    monkeypatch.setenv("BYTEFRAY_ROOT", str(export_source_root))
    _run_export(["hunter", "--output", str(out_dir)], capsys)
    package_file = next(out_dir.iterdir())

    monkeypatch.setenv("BYTEFRAY_ROOT", str(_data_root))
    _run_import([str(package_file)], capsys)
    code, out, _ = _run_import([str(package_file)], capsys)

    assert code == 0
    assert "already present" in out


# ---------------------------------------------------------------------------
# top-level `bytefray agents ...` dispatcher wiring
# ---------------------------------------------------------------------------


def test_command_dispatcher_wires_export_package_import(
    _data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _make_python_agent(_data_root)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    code = command_main(["agents", "export", "hunter", "--output", str(out_dir), "--json"])
    out = capsys.readouterr().out
    assert code == 0
    package_path = Path(json.loads(out)["package_path"])

    code = command_main(["agents", "package", "show", str(package_path), "--json"])
    out = capsys.readouterr().out
    assert code == 0
    assert json.loads(out)["valid"] is True

    other_root = tmp_path / "other_root"
    other_root.mkdir()
    monkeypatch.setenv("BYTEFRAY_ROOT", str(other_root))
    code = command_main(["agents", "import", str(package_path), "--json"])
    out = capsys.readouterr().out
    assert code == 0
    assert json.loads(out)["agent_id"] == "hunter"
    assert (other_root / "agents" / "hunter").is_dir()


def test_agents_help_mentions_new_commands(capsys: pytest.CaptureFixture) -> None:
    code = command_main(["agents", "--help"])
    out = capsys.readouterr().out
    assert code == 0
    assert "agents export" in out
    assert "agents package show" in out
    assert "agents import" in out
