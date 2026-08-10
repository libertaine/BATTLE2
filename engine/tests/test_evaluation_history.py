"""battle_engine.evaluation_history: v1/v2 adapters and discovery (docs/specs/evaluation_history.md)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from battle_engine.agent_evaluation import EvaluationRequest, EvaluationService
from battle_engine.evaluation_history import (
    AmbiguousSelectorError,
    ArtifactReadError,
    FieldConfidence,
    HealthCode,
    adapt_any,
    adapt_v1,
    adapt_v2,
    discover,
    resolve_selector,
)

NOP_ACTION = "AgentAction(ActionKind.NOP)"


def _write_python_agent(root: Path, name: str, action: str = NOP_ACTION) -> None:
    directory = root / "agents" / name
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text(
        json.dumps(
            {"kind": "python", "api_version": 1, "entrypoint": "agent.py:create_agent", "version": "1.0"}
        ),
        encoding="utf-8",
    )
    (directory / "agent.py").write_text(
        f"""
from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, context): pass
    def act(self, observation): return {action}
def create_agent(): return Agent()
""",
        encoding="utf-8",
    )


def _run_v2(tmp_path: Path, **overrides) -> Path:
    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    defaults = {
        "candidate_id": "candidate",
        "opponent_ids": ("opponent",),
        "seeds": (1,),
        "output_dir": tmp_path / "eval-out",
        "ticks": 10,
        "data_root": tmp_path,
    }
    defaults.update(overrides)
    result = EvaluationService().run(EvaluationRequest(**defaults))
    return result.state_path


# ---------------------------------------------------------------------------
# Headless import
# ---------------------------------------------------------------------------


def test_headless_import_never_pulls_in_qt_or_pygame():
    before = {name for name in sys.modules if "PySide6" in name or name == "pygame"}
    import battle_engine.evaluation_history  # noqa: F401

    after = {name for name in sys.modules if "PySide6" in name or name == "pygame"}
    assert after == before


# ---------------------------------------------------------------------------
# v2 adapter
# ---------------------------------------------------------------------------


def test_v2_round_trip_via_adapt_any(tmp_path: Path):
    state_path = _run_v2(tmp_path)
    summary = adapt_any(state_path)
    assert summary.schema.schema_version == 2
    assert summary.candidate_id == "candidate"
    assert summary.lifecycle_state.value == "finished"
    assert summary.lifecycle_state.confidence == FieldConfidence.RECORDED
    assert summary.rules_compatibility_id.value == "evaluation-rules-1"
    assert len(summary.cells) == 1
    cell = summary.cells[0]
    assert cell.opponent_index.confidence == FieldConfidence.RECORDED
    assert cell.condition_fingerprint.value is not None
    assert summary.health.codes == (HealthCode.HEALTHY,)


def test_v2_adapt_recomputes_aggregates_never_trusts_stored_blindly(tmp_path: Path):
    state_path = _run_v2(tmp_path)
    # Corrupt the stored aggregates in place -- the adapter must recompute
    # from cells, not echo this tampered value back.
    data = json.loads(state_path.read_text(encoding="utf-8"))
    data["aggregates"][0]["wins"] = 999
    state_path.write_text(json.dumps(data), encoding="utf-8")

    summary = adapt_v2(state_path)
    assert summary.aggregates_recomputed[0].wins != 999


def test_v2_adapter_rejects_wrong_schema(tmp_path: Path):
    path = tmp_path / "evaluation.json"
    path.write_text(json.dumps({"schema": "not.evaluation", "schema_version": 2}), encoding="utf-8")
    with pytest.raises(ArtifactReadError) as excinfo:
        adapt_v2(path)
    assert excinfo.value.code == HealthCode.WRONG_SCHEMA


def test_v2_adapter_rejects_unsupported_version(tmp_path: Path):
    from battle_engine.agent_evaluation import SCHEMA_NAME

    path = tmp_path / "evaluation.json"
    path.write_text(json.dumps({"schema": SCHEMA_NAME, "schema_version": 999}), encoding="utf-8")
    with pytest.raises(ArtifactReadError) as excinfo:
        adapt_v2(path)
    assert excinfo.value.code == HealthCode.UNSUPPORTED_VERSION


def test_v2_adapter_rejects_malformed_json(tmp_path: Path):
    path = tmp_path / "evaluation.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ArtifactReadError) as excinfo:
        adapt_v2(path)
    assert excinfo.value.code == HealthCode.MALFORMED_JSON


def test_v2_health_reflects_source_drift_abort(tmp_path: Path, monkeypatch):
    import battle_engine.agent_evaluation as mod

    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opp_a")
    _write_python_agent(tmp_path, "opp_b")
    request = EvaluationRequest(
        candidate_id="candidate",
        opponent_ids=("opp_a", "opp_b"),
        seeds=(1,),
        output_dir=tmp_path / "eval-out",
        ticks=10,
        data_root=tmp_path,
    )

    def _detect_with_injected_drift(self, cell, planned_identities, root):
        if cell.opponent_id == "opp_b":
            return {"error_code": "pre_execution_source_drift", "error_message": "boom"}
        return None

    monkeypatch.setattr(
        mod.EvaluationService, "_detect_pre_execution_drift", _detect_with_injected_drift
    )
    result = mod.EvaluationService().run(request)
    summary = adapt_any(result.state_path)
    assert HealthCode.SOURCE_DRIFT_ABORTED in summary.health.codes
    assert summary.lifecycle_state.value == "aborted"


# ---------------------------------------------------------------------------
# v1 adapter
# ---------------------------------------------------------------------------


def _v1_fixture(tmp_path: Path, *, complete: bool = True) -> Path:
    """A hand-built v1-shaped evaluation.json with one real completed cell."""

    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")

    from battle_engine.agent_test import TESTED_AGENT_SLOT, test_agent
    from battle_engine.results import WINNER_TIE_SENTINEL

    outcome = test_agent(
        "candidate",
        opponent="opponent",
        seed=1,
        ticks=10,
        timeout=None,
        trace=False,
        run_dir=tmp_path / "eval-out" / "matches" / "cell-1",
        data_root=tmp_path,
    )
    match_result = outcome.match_result

    eval_dir = tmp_path / "eval-out"
    cell = {
        "schedule_id": "evaluation-cell_deadbeef",
        "subject_role": "candidate",
        "subject_id": "candidate",
        "opponent_id": "opponent",
        "seed": 1,
        "artifact_dir": "matches/cell-1",
        "status": "completed",
        "outcome": (
            "tie"
            if match_result.winner == WINNER_TIE_SENTINEL
            else ("win" if match_result.winner == TESTED_AGENT_SLOT else "loss")
        ),
        "match_id": match_result.match_id,
        "result_id": match_result.result_id,
        "ticks_run": match_result.ticks_run,
        "score_subject": float(match_result.score.get(TESTED_AGENT_SLOT, 0)),
        "score_opponent": float(match_result.score.get("B", 0)),
        "territory_subject": None,
        "territory_opponent": None,
        "error_code": None,
        "error_message": None,
    }
    data = {
        "schema": "bytefray.evaluation",
        "schema_version": 1,
        "evaluation_id": "evaluation_deadbeefcafefeed00000000",
        "candidate_id": "candidate",
        "baseline_id": None,
        "opponent_ids": ["opponent"],
        "seeds": [1],
        "ticks": 10,
        "matrix_size": 1,
        "project": {"version": "0.6.1"},
        "cells": [cell],
        "aggregates": [],
        "comparison": [],
        "complete": complete,
    }
    path = eval_dir / "evaluation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return path


def test_v1_artifact_read_and_never_mutated(tmp_path: Path):
    path = _v1_fixture(tmp_path)
    before = path.read_bytes()
    summary = adapt_v1(path)
    after = path.read_bytes()
    assert before == after
    assert summary.schema.schema_version == 1
    assert summary.candidate_id == "candidate"


def test_v1_identity_recovery_is_honestly_unknown(tmp_path: Path):
    """result.json never persists api_version/agent_version/source_sha256 --
    v1 identity recovery must report UNKNOWN, not fabricate RECOVERED data."""

    path = _v1_fixture(tmp_path)
    summary = adapt_v1(path)
    assert summary.candidate_identity.confidence == FieldConfidence.UNKNOWN
    assert summary.baseline_identity.confidence == FieldConfidence.UNKNOWN
    assert summary.rules_compatibility_id.confidence == FieldConfidence.UNKNOWN
    assert summary.cells[0].opponent_identity.confidence == FieldConfidence.UNKNOWN


def test_v1_effective_conditions_recovered_from_nested_result(tmp_path: Path):
    path = _v1_fixture(tmp_path)
    summary = adapt_v1(path)
    assert summary.effective_conditions.confidence == FieldConfidence.RECOVERED
    assert summary.effective_conditions.value["tick_limit"] == 10
    assert summary.effective_conditions.value["arena_size"] == 4096


def test_v1_unfinished_health(tmp_path: Path):
    path = _v1_fixture(tmp_path, complete=False)
    summary = adapt_v1(path)
    assert HealthCode.UNFINISHED in summary.health.codes


def test_v1_never_uses_current_agent_discovery_as_evidence(tmp_path: Path):
    """Deleting the agent directories after the fixture is built must not
    change what the v1 adapter reports -- it must never re-resolve current
    agent discovery as historical evidence."""

    path = _v1_fixture(tmp_path)
    import shutil

    shutil.rmtree(tmp_path / "agents")
    summary = adapt_v1(path)  # must not raise
    assert summary.candidate_id == "candidate"


def test_adapt_any_rejects_missing_required_fields(tmp_path: Path):
    path = tmp_path / "evaluation.json"
    path.write_text(json.dumps({"schema": "bytefray.evaluation", "schema_version": 1}), encoding="utf-8")
    with pytest.raises(ArtifactReadError) as excinfo:
        adapt_any(path)
    assert excinfo.value.code == HealthCode.INVALID_REQUIRED_FIELDS


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def test_discovery_empty_root(tmp_path: Path):
    listing = discover(roots=[tmp_path / "runs" / "evaluations"])
    assert listing.entries == ()
    assert listing.duplicate_identity_groups == ()


def test_discovery_default_root_scan(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    _run_v2(tmp_path, output_dir=tmp_path / "runs" / "evaluations" / "e1")
    listing = discover()
    assert len(listing.entries) == 1
    assert listing.entries[0].summary is not None


def test_discovery_malformed_sibling_does_not_abort_listing(tmp_path: Path):
    root = tmp_path / "runs" / "evaluations"
    good_dir = root / "good"
    good_dir.mkdir(parents=True)
    _run_v2(tmp_path, output_dir=good_dir)

    bad_dir = root / "bad"
    bad_dir.mkdir(parents=True)
    (bad_dir / "evaluation.json").write_text("{not valid json", encoding="utf-8")

    listing = discover(roots=[root])
    assert len(listing.entries) == 2
    statuses = {entry.summary is not None for entry in listing.entries}
    assert statuses == {True, False}
    bad_entry = next(entry for entry in listing.entries if entry.summary is None)
    assert HealthCode.MALFORMED_JSON in bad_entry.health.codes


def test_discovery_explicit_artifact_path(tmp_path: Path):
    state_path = _run_v2(tmp_path, output_dir=tmp_path / "custom" / "location")
    listing = discover(artifacts=[state_path])
    assert len(listing.entries) == 1
    assert listing.entries[0].evaluation_id is not None


def test_discovery_moved_directory_still_usable(tmp_path: Path):
    original_dir = tmp_path / "runs" / "evaluations" / "e1"
    state_path = _run_v2(tmp_path, output_dir=original_dir)
    evaluation_id_before = adapt_any(state_path).evaluation_id

    moved_dir = tmp_path / "moved"
    original_dir.rename(moved_dir)
    moved_path = moved_dir / "evaluation.json"
    summary = adapt_any(moved_path)
    assert summary.evaluation_id == evaluation_id_before
    # The moved cell's own result.json is still reachable via the relative
    # artifact_dir recorded in evaluation.json.
    assert (moved_dir / summary.cells[0].artifact_dir / "result.json").is_file()


def test_discovery_duplicate_evaluation_id_flagged(tmp_path: Path):
    root = tmp_path / "runs" / "evaluations"
    original = root / "original"
    _run_v2(tmp_path, output_dir=original)

    import shutil

    copy_dir = root / "copy"
    shutil.copytree(original, copy_dir)

    listing = discover(roots=[root])
    assert len(listing.duplicate_identity_groups) == 1
    _evaluation_id, paths = listing.duplicate_identity_groups[0]
    assert len(paths) == 2
    for entry in listing.entries:
        assert HealthCode.DUPLICATE_IDENTITY_LOCATION in entry.health.codes


def test_resolve_selector_ambiguous_id_raises(tmp_path: Path):
    root = tmp_path / "runs" / "evaluations"
    original = root / "original"
    _run_v2(tmp_path, output_dir=original)
    import shutil

    shutil.copytree(original, root / "copy")

    summary = adapt_any(original / "evaluation.json")
    with pytest.raises(AmbiguousSelectorError):
        resolve_selector(summary.evaluation_id, roots=[root])


def test_resolve_selector_explicit_path_bypasses_lookup(tmp_path: Path):
    state_path = _run_v2(tmp_path, output_dir=tmp_path / "eval-out")
    resolved = resolve_selector(str(state_path.parent), roots=[])
    assert resolved == state_path.resolve()


def test_resolve_selector_unknown_id_raises_not_found(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        resolve_selector("evaluation-v2_doesnotexist", roots=[tmp_path])
