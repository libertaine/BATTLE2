from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from app.services.agent_catalog import AgentRow
from app.services.designer_workflows import (
    DesignerValidationError,
    build_designer_tournament_command,
    match_artifact_paths,
    new_match_run_directory,
    read_match_presentation,
    read_tournament_presentation,
    validate_homogeneous,
)
from battle_engine.project_info import get_project_info
from battle_engine.replay import SCHEMA_VERSION as REPLAY_SCHEMA_VERSION
from battle_engine.result_model import SCHEMA_VERSION as RESULT_SCHEMA_VERSION


def _row(name: str, kind: str) -> AgentRow:
    return AgentRow(name.upper(), f"/agents/{name}", None, {"name": name, "kind": kind})


def test_designer_adapter_import_does_not_require_qt():
    assert validate_homogeneous([_row("alpha", "python"), _row("beta", "python")]) == "python"


def test_new_match_run_directory_is_unique_and_isolated(tmp_path):
    first = new_match_run_directory(tmp_path)
    second = new_match_run_directory(tmp_path)

    assert first != second
    assert first.parent == second.parent == tmp_path / "runs" / "_designer"
    assert first.is_absolute() and second.is_absolute()

    # Two runs' artifact paths, derived the normal way, cannot collide.
    first_result, first_replay = match_artifact_paths(first / "replay.jsonl")
    second_result, second_replay = match_artifact_paths(second / "replay.jsonl")
    assert first_result != second_result
    assert first_replay != second_replay


def test_match_artifacts_and_canonical_replay_reference(tmp_path):
    result_path, replay_path = match_artifact_paths(tmp_path / "replay.jsonl")
    result_path.write_text(json.dumps({
        "schema": "battle2.result", "schema_version": 1,
        "result_id": "result_1", "match_id": "match_1", "mode": "native",
        "winner": "alpha", "termination_reason": "last_alive", "ticks": 7,
        "replay": {"replay_id": "replay_1", "sha256": "abc", "filename": "replay.jsonl"},
    }), encoding="utf-8")

    shown = read_match_presentation(result_path)

    assert replay_path == tmp_path / "replay.jsonl"
    assert shown.winner == "alpha"
    assert shown.termination_reason == "last_alive"
    assert shown.result_path == result_path
    assert shown.replay_path == replay_path


def test_match_without_replay_is_presented_cleanly(tmp_path):
    result = tmp_path / "result.json"
    result.write_text(json.dumps({
        "schema": "battle2.result", "schema_version": 1,
        "result_id": "result_1", "match_id": "match_1", "mode": "pmars",
        "winner": "tie", "termination_reason": "rounds_complete", "ticks": 0,
        "replay": None,
    }), encoding="utf-8")
    assert read_match_presentation(result).replay_path is None


def test_tournament_command_validates_runtime_and_uses_supported_cli(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    command = build_designer_tournament_command(
        [_row("alpha", "python"), _row("beta", "python")],
        rounds=2, seed=19, output_dir=tmp_path / "Tournament With Spaces",
    )
    assert command[1:4] == ["-m", "battle_engine", "tournament"]
    assert command[4:] == [
        "alpha", "beta", "--rounds", "2", "--seed", "19",
        "--output", str((tmp_path / "Tournament With Spaces").resolve()),
    ]

    with pytest.raises(DesignerValidationError, match="Mixed VM/Python"):
        validate_homogeneous([_row("alpha", "python"), _row("beta", "builtin")])
    with pytest.raises(DesignerValidationError, match="at least 2"):
        validate_homogeneous([_row("alpha", "python")])


def test_tournament_state_is_adapted_to_status_and_standings(tmp_path):
    state = tmp_path / "tournament.json"
    state.write_text(json.dumps({
        "schema": "battle2.tournament", "schema_version": 1,
        "tournament_id": "tournament_1", "division": "vm",
        "matches": [{"status": "completed"}, {"status": "failed"}],
        "standings": [{"agent_id": "alpha", "wins": 1, "losses": 0,
                       "ties": 0, "score_total": 4}],
    }), encoding="utf-8")
    shown = read_tournament_presentation(state)
    assert (shown.completed, shown.failed, shown.rejected) == (1, 1, 0)
    assert shown.standings[0]["agent_id"] == "alpha"


def test_about_info_uses_canonical_schema_constants():
    info = get_project_info()
    assert info.result_schema_version == RESULT_SCHEMA_VERSION
    assert info.replay_schema_version == REPLAY_SCHEMA_VERSION
    assert info.agent_api_version == 1
    assert info.project_url.startswith("https://")
