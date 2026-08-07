from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BTCTL_PATH = ROOT / "tournament" / "scripts" / "btctl.py"


def _load_btctl():
    spec = importlib.util.spec_from_file_location("btctl_under_test", BTCTL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _unexpected_call(*args, **kwargs):
    raise AssertionError("unexpected call")


def test_import_does_not_resolve_build_tool(monkeypatch):
    monkeypatch.setenv("BUILD_SH", str(ROOT / "does-not-exist" / "build.sh"))
    module = _load_btctl()
    assert module.ROSTER == ROOT / "tournament" / "roster.json"


def test_report_does_not_load_roster_or_resolve_build_tool(monkeypatch, tmp_path):
    module = _load_btctl()
    calls = []
    monkeypatch.setattr(module, "load_roster", _unexpected_call)
    monkeypatch.setattr(module, "_find_build_sh", _unexpected_call)
    monkeypatch.setattr(module, "aggregate_leaderboard", lambda *args: calls.append(args))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "btctl",
            "report",
            "--in",
            str(tmp_path),
            "--csv",
            str(tmp_path / "leaderboard.csv"),
            "--md",
            str(tmp_path / "leaderboard.md"),
        ],
    )

    module.main()

    assert calls == [
        (str(tmp_path), str(tmp_path / "leaderboard.csv"), str(tmp_path / "leaderboard.md"))
    ]


def test_default_battle_command_uses_current_source_dispatcher(monkeypatch):
    monkeypatch.delenv("BATTLE_BIN", raising=False)
    module = _load_btctl()
    assert module._battle_cmd() == [sys.executable, "-m", "battle_engine", "run"]


def test_run_game_uses_supported_arguments_and_current_environment(monkeypatch, tmp_path):
    module = _load_btctl()
    captured = {}

    def record(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs

    monkeypatch.setattr(module.subprocess, "run", record)
    a = {
        "name": "writer",
        "cli": "writer",
        "cfg": {"type": "builtin", "id": "writer"},
    }
    b = {
        "name": "runner",
        "cli": "runner",
        "cfg": {"type": "builtin", "id": "runner"},
    }

    module.run_game(a, b, 7, tmp_path, params={"ticks": 1})

    command = captured["command"]
    assert command[:4] == [sys.executable, "-m", "battle_engine", "run"]
    assert "--config" not in command
    assert "--replay" in command
    assert captured["kwargs"]["cwd"] == ROOT
    python_paths = captured["kwargs"]["env"]["PYTHONPATH"].split(os.pathsep)
    assert str(ROOT / "engine" / "src") in python_paths
    assert json.loads(captured["kwargs"]["env"]["BATTLE_AGENTS_JSON"]) == {
        "A": a["cfg"],
        "B": b["cfg"],
    }


def test_build_script_resolution_prefers_override_then_current_tool(monkeypatch, tmp_path):
    module = _load_btctl()
    override = tmp_path / "custom build.sh"
    override.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("BUILD_SH", str(override))
    assert module._find_build_sh() == override

    monkeypatch.delenv("BUILD_SH")
    assert module._find_build_sh() == ROOT / "sdk" / "tooling" / "build.sh"


def test_build_customs_uses_current_build_script_contract(monkeypatch, tmp_path):
    module = _load_btctl()
    build_sh = ROOT / "sdk" / "tooling" / "build.sh"
    calls = []
    monkeypatch.setattr(module, "_find_build_sh", lambda: build_sh)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda command, **kwargs: calls.append((command, kwargs)),
    )

    built = module.build_customs(
        [
            {
                "name": "example",
                "asm": "_legacy/agents_tooling/claude_agent.asm",
                "header": 16,
                "entry": 16,
            }
        ],
        tmp_path,
    )

    command, kwargs = calls[0]
    assert command == [
        str(build_sh),
        str(ROOT / "_legacy" / "agents_tooling" / "claude_agent.asm"),
        str(tmp_path / "example.blob"),
        "--entry",
        "16",
        "--name",
        "example",
    ]
    assert "--header" not in command
    assert kwargs == {"cwd": build_sh.parent, "check": True}
    assert built == [{"name": "example", "blob": str(tmp_path / "example.blob")}]


def test_roster_is_portable_regular_json_file():
    roster = ROOT / "tournament" / "roster.json"
    assert roster.is_file()
    assert not roster.is_symlink()
    assert json.loads(roster.read_text(encoding="utf-8")) == json.loads(
        (ROOT / "tournament" / "rosters" / "default.json").read_text(encoding="utf-8")
    )
