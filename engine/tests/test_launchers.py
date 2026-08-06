from __future__ import annotations

import sys
from pathlib import Path

import pytest
from battle_engine import launchers

from app.services import engine_commands
from app.services.osutil import get_default_paths


def _set_source(monkeypatch, executable: Path) -> None:
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))


def _set_frozen(monkeypatch, executable: Path) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))


def test_source_match_uses_primary_dispatcher_and_preserves_arguments(monkeypatch, tmp_path):
    python = tmp_path / "Python With Spaces" / "python.exe"
    arguments = ["--ticks", "25", "--a-blob", str(tmp_path / "Agent A" / "a.blob")]
    _set_source(monkeypatch, python)

    command = launchers.build_match_command(arguments)

    assert command == [str(python.resolve()), "-m", "battle_engine", "run", *arguments]


def test_source_replay_uses_client_module_and_keeps_path_one_argument(monkeypatch, tmp_path):
    python = tmp_path / "Python With Spaces" / "python.exe"
    replay = tmp_path / "Replay Files" / "match one.jsonl"
    _set_source(monkeypatch, python)

    command = launchers.build_replay_command(replay, ["--renderer", "pygame"])

    assert command == [
        str(python.resolve()),
        "-m",
        "battle_client.cli",
        "--replay",
        str(replay.resolve()),
        "--renderer",
        "pygame",
    ]


def test_frozen_commands_use_packaged_sibling_executables(monkeypatch, tmp_path):
    app_dir = tmp_path / "BATTLE2 Portable"
    designer = app_dir / "battle-agent-designer.exe"
    battle2 = app_dir / "battle2.exe"
    viewer = app_dir / "battle-replay-viewer.exe"
    app_dir.mkdir()
    battle2.touch()
    viewer.touch()
    _set_frozen(monkeypatch, designer)

    match_command = launchers.build_match_command(["--ticks", "5"])
    replay_command = launchers.build_replay_command(tmp_path / "Replay One.jsonl")

    assert match_command == [str(battle2.resolve()), "run", "--ticks", "5"]
    assert replay_command[:3] == [
        str(viewer.resolve()),
        "--replay",
        str((tmp_path / "Replay One.jsonl").resolve()),
    ]
    assert str(designer.resolve()) not in (match_command[0], replay_command[0])


def test_frozen_commands_support_current_onedir_sibling_layout(monkeypatch, tmp_path):
    bin_dir = tmp_path / "Program Files" / "BATTLE2" / "bin"
    designer = bin_dir / "battle-agent-designer" / "battle-agent-designer.exe"
    battle2 = bin_dir / "battle2" / "battle2.exe"
    viewer = bin_dir / "battle-replay-viewer" / "battle-replay-viewer.exe"
    designer.parent.mkdir(parents=True)
    battle2.parent.mkdir()
    viewer.parent.mkdir()
    battle2.touch()
    viewer.touch()
    _set_frozen(monkeypatch, designer)

    assert launchers.build_match_command([])[0] == str(battle2.resolve())
    assert launchers.build_replay_command(tmp_path / "replay.jsonl")[0] == str(
        viewer.resolve()
    )


@pytest.mark.parametrize("builder, executable_name", [
    (lambda: launchers.build_match_command([]), "battle2.exe"),
    (lambda: launchers.build_replay_command(Path("replay.jsonl")), "battle-replay-viewer.exe"),
])
def test_missing_packaged_executable_has_clear_error(
    monkeypatch, tmp_path, builder, executable_name
):
    designer = tmp_path / "designer" / "battle-agent-designer.exe"
    _set_frozen(monkeypatch, designer)

    with pytest.raises(FileNotFoundError, match=executable_name):
        builder()


def test_battle2_root_does_not_redirect_executable_discovery(monkeypatch, tmp_path):
    app_dir = tmp_path / "Application Bin"
    designer = app_dir / "battle-agent-designer.exe"
    battle2 = app_dir / "battle2.exe"
    app_dir.mkdir()
    battle2.touch()
    monkeypatch.setenv("BATTLE2_ROOT", str(tmp_path / "Writable Data"))
    _set_frozen(monkeypatch, designer)

    assert launchers.build_match_command([])[0] == str(battle2.resolve())


def test_designer_match_arguments_preserve_simple_and_advanced_options(tmp_path):
    a_blob = tmp_path / "Agent A" / "model one.blob"
    b_blob = tmp_path / "Agent B" / "model two.blob"

    arguments = launchers.build_designer_match_arguments(
        ticks=600,
        arena=512,
        a_type="alpha",
        b_type="beta",
        a_blob=a_blob,
        b_blob=b_blob,
        alive_w=0.25,
        kill_w=2.5,
        territory_w=0.75,
        territory_bucket=32,
        seed=123,
    )

    assert arguments == [
        "--ticks", "600",
        "--arena", "512",
        "--a-type", "alpha",
        "--b-type", "beta",
        "--a-blob", str(a_blob),
        "--b-blob", str(b_blob),
        "--alive-w", "0.25",
        "--kill-w", "2.5",
        "--territory-w", "0.75",
        "--territory-bucket", "32",
        "--seed", "123",
    ]

    assert "--a-blob" not in launchers.build_designer_match_arguments(
        ticks=1, arena=64, a_type="alpha", b_type="beta", a_blob=""
    )


def test_engine_runner_uses_shared_match_builder_and_preserves_config(monkeypatch, tmp_path):
    python = tmp_path / "Python With Spaces" / "python.exe"
    _set_source(monkeypatch, python)
    paths = get_default_paths(tmp_path / "Writable Data")
    config = engine_commands.RunConfig(
        a_type="alpha",
        b_type="beta",
        arena=256,
        ticks=40,
        alive_w=0.5,
        kill_w=3.0,
        territory_w=0.25,
        territory_bucket=16,
        seed=99,
    )

    command, _env = engine_commands.build_engine_command(config, paths)

    assert command[:4] == [str(python.resolve()), "-m", "battle_engine", "run"]
    assert command[4:] == [
        "--arena", "256",
        "--ticks", "40",
        "--win-mode", "score_fallback",
        "--replay", str(paths.replay_path),
        "--a-type", "alpha",
        "--b-type", "beta",
        "--alive-w", "0.5",
        "--kill-w", "3.0",
        "--territory-w", "0.25",
        "--territory-bucket", "16",
        "--seed", "99",
    ]


def test_replay_service_starts_shared_command_without_a_shell(monkeypatch, tmp_path):
    python = tmp_path / "Python With Spaces" / "python.exe"
    replay = tmp_path / "Replay Files" / "match one.jsonl"
    replay.parent.mkdir()
    replay.touch()
    _set_source(monkeypatch, python)
    calls = []

    def fake_popen(command, **kwargs):
        calls.append((command, kwargs))
        return object()

    monkeypatch.setattr(engine_commands, "Popen", fake_popen)

    engine_commands.open_pygame_client_direct(tmp_path, replay)

    command, kwargs = calls[0]
    assert command == launchers.build_replay_command(
        replay, ("--renderer", "pygame", "--tick-delay", "0.02")
    )
    assert kwargs["cwd"] == str(tmp_path)
    assert "shell" not in kwargs
