from __future__ import annotations

import json
import sys

import pytest
from battle_engine.agent_trace import read_trace_v2
from battle_engine.cli import main as run_cli
from battle_engine.launchers import build_designer_match_arguments
from battle_engine.project_info import get_project_info
from battle_engine.replay import SCHEMA_VERSION as REPLAY_SCHEMA_VERSION
from battle_engine.result_model import SCHEMA_VERSION as RESULT_SCHEMA_VERSION
from battle_engine.rules import BYTEFRAY_RULESET_ID
from battle_engine.ruleset_policy import (
    BYTEFRAY_RULESET_V2_ID,
    BYTEFRAY_RULESET_V4_ALPHA1_ID,
    BYTEFRAY_RULESET_V4_ALPHA2_ID,
)

from app.services.agent_catalog import AgentRow
from app.services.designer_workflows import (
    DesignerValidationError,
    agent_runtime_label,
    build_designer_tournament_command,
    decorate_agent_display,
    designer_trace_path,
    match_artifact_paths,
    new_match_run_directory,
    read_match_presentation,
    read_tournament_presentation,
    validate_homogeneous,
)


def _row(name: str, kind: str) -> AgentRow:
    return AgentRow(name.upper(), f"/agents/{name}", None, {"name": name, "kind": kind})


def test_designer_adapter_import_does_not_require_qt():
    assert validate_homogeneous([_row("alpha", "python"), _row("beta", "python")]) == "python"


def test_agent_runtime_label_reflects_python_vs_vm():
    assert agent_runtime_label(_row("claimer", "python")) == "Python"
    # Unset/unknown kind maps to VM, per agent_kind()'s existing semantics.
    assert agent_runtime_label(_row("runner", "builtin")) == "VM"
    assert agent_runtime_label(AgentRow("runner", "/agents/runner", None, {})) == "VM"


def test_decorate_agent_display_appends_runtime_suffix_without_altering_identity():
    row = _row("claimer", "python")
    assert decorate_agent_display(row) == "CLAIMER [Python]"
    # The undecorated identifier callers must actually use is untouched.
    assert row.name == "CLAIMER"


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


@pytest.mark.parametrize(
    "ruleset_id", [BYTEFRAY_RULESET_V4_ALPHA1_ID, BYTEFRAY_RULESET_V4_ALPHA2_ID]
)
def test_designer_trace_path_is_requested_for_v4_rulesets(tmp_path, ruleset_id):
    replay_path = tmp_path / "runs" / "_designer" / "run-1" / "replay.jsonl"
    trace_path = designer_trace_path(replay_path, ruleset_id)
    assert trace_path == replay_path.parent / "trace.jsonl"
    assert trace_path.name == "trace.jsonl"


@pytest.mark.parametrize("ruleset_id", [BYTEFRAY_RULESET_ID, BYTEFRAY_RULESET_V2_ID])
def test_designer_trace_path_is_none_for_historical_rulesets(tmp_path, ruleset_id):
    replay_path = tmp_path / "runs" / "_designer" / "run-1" / "replay.jsonl"
    assert designer_trace_path(replay_path, ruleset_id) is None


def test_designer_trace_path_cannot_collide_across_independent_runs(tmp_path):
    first_replay = new_match_run_directory(tmp_path) / "replay.jsonl"
    second_replay = new_match_run_directory(tmp_path) / "replay.jsonl"

    first_trace = designer_trace_path(first_replay, BYTEFRAY_RULESET_V4_ALPHA1_ID)
    second_trace = designer_trace_path(second_replay, BYTEFRAY_RULESET_V4_ALPHA2_ID)

    assert first_trace != second_trace
    assert first_trace.parent == first_replay.parent
    assert second_trace.parent == second_replay.parent
    # Neither trace lives in a shared/global location -- each stays inside
    # its own run's directory, a sibling of that run's own replay/result.
    assert first_trace.parent != tmp_path
    assert second_trace.parent != tmp_path


def test_designer_v4_match_produces_full_spectator_artifact_set(tmp_path, monkeypatch):
    """A short, real v4 match run with the exact arguments a Designer match
    now builds must produce result.json/replay.jsonl/trace.jsonl together as
    siblings, with the trace readable by the existing trace-parsing
    machinery -- proving the Designer's automatic-trace policy actually
    yields a spectator-capable run end to end, not just a command line that
    claims to.
    """
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))

    run_directory = new_match_run_directory(tmp_path)
    result_path, replay_path = match_artifact_paths(run_directory / "replay.jsonl")
    trace_path = designer_trace_path(replay_path, BYTEFRAY_RULESET_V4_ALPHA2_ID)
    assert trace_path is not None

    arguments = build_designer_match_arguments(
        ticks=2,
        arena=64,
        a_type="v4_claimer",
        b_type="v4_scout",
        ruleset_id=BYTEFRAY_RULESET_V4_ALPHA2_ID,
    )
    arguments.extend(("--replay", str(replay_path)))
    arguments.extend(("--trace", str(trace_path)))

    assert run_cli(arguments) == 0

    assert result_path.is_file()
    assert replay_path.is_file()
    assert trace_path.is_file()
    assert trace_path.parent == replay_path.parent == result_path.parent

    # v4 (Agent API v2) matches record a schema_version-2 trace; the v1
    # reader deliberately rejects it (agent_trace.py's format-check
    # docstring), so this is the reader the Alpha3 spectator suite itself
    # uses for v4 traces.
    document = read_trace_v2(trace_path)
    assert document.decisions


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
        "matches": [
            {"status": "completed"},
            {"status": "failed"},
            {"status": "corrupted"},
        ],
        "standings": [{"agent_id": "alpha", "wins": 1, "losses": 0,
                       "ties": 0, "score_total": 4}],
    }), encoding="utf-8")
    shown = read_tournament_presentation(state)
    assert (shown.completed, shown.failed, shown.rejected, shown.corrupted) == (1, 1, 0, 1)
    assert shown.standings[0]["agent_id"] == "alpha"


def test_about_info_uses_canonical_schema_constants():
    info = get_project_info()
    assert info.result_schema_version == RESULT_SCHEMA_VERSION
    assert info.replay_schema_version == REPLAY_SCHEMA_VERSION
    assert info.agent_api_version == 2
    assert info.project_url.startswith("https://")


def test_about_info_reports_current_project_name():
    info = get_project_info()
    assert info.project_name == "Bytefray"
    assert info.project_url == "https://github.com/libertaine/Bytefray"
