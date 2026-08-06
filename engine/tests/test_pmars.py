from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from battle_engine import cli, pmars


def _executable(directory: Path, name: str = "pmars.exe") -> Path:
    executable = directory / name
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_bytes(b"fake")
    return executable.resolve()


def test_valid_explicit_pmars_command_is_absolute(tmp_path):
    executable = _executable(tmp_path / "tools")
    assert pmars.resolve_pmars_command(environ={"PMARS_CMD": str(executable)}) == [
        str(executable)
    ]


def test_explicit_quoted_path_with_spaces_is_preserved(tmp_path):
    executable = _executable(tmp_path / "pMARS With Spaces")
    command = pmars.resolve_pmars_command(environ={"PMARS_CMD": f'"{executable}"'})
    assert command == [str(executable)]


def test_invalid_explicit_command_does_not_fall_through(monkeypatch, tmp_path):
    fallback = _executable(tmp_path / "resource" / "pmars" / "windows")
    monkeypatch.setattr(
        pmars.shutil,
        "which",
        lambda name: None if name == "definitely-missing-pmars" else str(fallback),
    )
    with pytest.raises(pmars.PMarsNotFoundError, match="does not fall back"):
        pmars.resolve_pmars_command(
            environ={"PMARS_CMD": "definitely-missing-pmars"},
            resource_root=tmp_path / "resource",
            data_root=tmp_path / "data",
        )


def test_frozen_meipass_bundled_executable_discovery(monkeypatch, tmp_path):
    extraction = tmp_path / "PyInstaller Extraction"
    executable = _executable(extraction / "pmars" / "windows")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(extraction), raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "portable" / "battle2.exe"))
    assert pmars.resolve_pmars_command(environ={}) == [str(executable)]
    assert not (extraction / "agents").exists()


def test_portable_or_installed_data_layout_discovery(tmp_path):
    executable = _executable(tmp_path / "portable app" / "pmars" / "windows")
    command = pmars.resolve_pmars_command(
        environ={}, resource_root=tmp_path / "empty", data_root=tmp_path / "portable app"
    )
    assert command == [str(executable)]


def test_source_checkout_bundled_executable_discovery(tmp_path):
    executable = _executable(tmp_path / "checkout" / "pmars" / "windows")
    command = pmars.resolve_pmars_command(
        environ={}, resource_root=tmp_path / "checkout", data_root=tmp_path / "data"
    )
    assert command == [str(executable)]


def test_path_fallback_is_normalized(monkeypatch, tmp_path):
    executable = _executable(tmp_path / "PATH tools", name="pmars")
    monkeypatch.setattr(
        pmars.shutil, "which", lambda name: str(executable) if name in {"pmars", "pmars.exe"} else None
    )
    command = pmars.resolve_pmars_command(
        environ={}, resource_root=tmp_path / "resource", data_root=tmp_path / "data"
    )
    assert command == [str(executable)]


def test_missing_diagnostic_lists_configuration_searches_and_path(monkeypatch, tmp_path):
    monkeypatch.setattr(pmars.shutil, "which", lambda name: None)
    with pytest.raises(pmars.PMarsNotFoundError) as error:
        pmars.resolve_pmars_command(
            environ={}, resource_root=tmp_path / "resources", data_root=tmp_path / "data"
        )
    message = str(error.value)
    assert "PMARS_CMD" in message
    assert str((tmp_path / "resources" / "pmars" / "windows").resolve()) in message
    assert str((tmp_path / "data" / "pmars" / "windows").resolve()) in message
    assert "PATH" in message


def test_successful_invocation_preserves_command_and_streams(monkeypatch, tmp_path):
    executable = _executable(tmp_path / "pMARS With Spaces")
    completed = subprocess.CompletedProcess(
        [], 0, stdout="Alpha scores 3\nBeta scores 0\nResults: 1 0 0\n", stderr="warning\n"
    )
    monkeypatch.setattr(pmars.subprocess, "run", lambda *args, **kwargs: completed)
    result = pmars.run_pmars(["-b", "a.red", "b.red"], command=[str(executable)])
    assert result.winner == "A"
    assert result.command == (str(executable), "-b", "a.red", "b.red")
    assert result.stderr == "warning\n"


def test_nonzero_exit_and_stderr_are_preserved(monkeypatch):
    completed = subprocess.CompletedProcess([], 7, stdout="partial output", stderr="bad warrior")
    monkeypatch.setattr(pmars.subprocess, "run", lambda *args, **kwargs: completed)
    with pytest.raises(pmars.PMarsExecutionError) as error:
        pmars.run_pmars([], command=["pmars.exe"])
    assert error.value.returncode == 7
    assert error.value.exit_code == 7
    assert error.value.stdout == "partial output"
    assert error.value.stderr == "bad warrior"
    assert "bad warrior" in str(error.value)


def test_timeout_is_normalized_and_preserves_output(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"], output="partial", stderr="slow")

    monkeypatch.setattr(pmars.subprocess, "run", timeout)
    with pytest.raises(pmars.PMarsTimeoutError) as error:
        pmars.run_pmars([], command=["pmars.exe"], timeout=0.25)
    assert error.value.exit_code == 124
    assert error.value.stdout == "partial"
    assert error.value.stderr == "slow"


def test_unparseable_success_is_failure(monkeypatch):
    completed = subprocess.CompletedProcess([], 0, stdout="unexpected output", stderr="diagnostic")
    monkeypatch.setattr(pmars.subprocess, "run", lambda *args, **kwargs: completed)
    with pytest.raises(pmars.PMarsOutputError) as error:
        pmars.run_pmars([], command=["pmars.exe"])
    assert error.value.stdout == "unexpected output"
    assert error.value.stderr == "diagnostic"


def test_cli_failure_is_nonzero_stderr_and_does_not_write_summary(
    monkeypatch, tmp_path, capsys
):
    warrior_a = tmp_path / "a.red"
    warrior_b = tmp_path / "b.red"
    warrior_a.write_text(";redcode", encoding="utf-8")
    warrior_b.write_text(";redcode", encoding="utf-8")
    replay = tmp_path / "output" / "replay.jsonl"
    replay.parent.mkdir()
    summary = replay.with_name("summary.json")
    summary.write_text("stale summary\n", encoding="utf-8")
    monkeypatch.setattr(
        cli,
        "run_pmars",
        lambda arguments: (_ for _ in ()).throw(
            pmars.PMarsNotFoundError("configured pMARS is missing")
        ),
    )
    exit_code = cli.main(
        [
            "--mode",
            "redcode94",
            "--red-a",
            str(warrior_a),
            "--red-b",
            str(warrior_b),
            "--replay",
            str(replay),
        ]
    )
    assert exit_code == 2
    assert "pMARS error: configured pMARS is missing" in capsys.readouterr().err
    assert not summary.exists()


def test_gui_service_subprocess_receives_same_traceback_free_failure(tmp_path):
    warrior_a = tmp_path / "a.red"
    warrior_b = tmp_path / "b.red"
    warrior_a.write_text(";redcode", encoding="utf-8")
    warrior_b.write_text(";redcode", encoding="utf-8")
    env = dict(os.environ, PMARS_CMD=str(tmp_path / "missing pmars.exe"))
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "battle_engine.cli",
            "--mode",
            "redcode94",
            "--red-a",
            str(warrior_a),
            "--red-b",
            str(warrior_b),
            "--replay",
            str(tmp_path / "replay.jsonl"),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
        env=env,
    )
    # EngineRunner uses this same stderr-to-stdout subprocess model and emits
    # each resulting line through its GUI output signal.
    assert completed.returncode == 2
    assert "pMARS error: Configured PMARS_CMD executable was not found" in completed.stdout
    assert "Traceback" not in completed.stdout
