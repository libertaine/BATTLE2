"""schema-v3 agent-revision provenance in the evaluation_history domain layer
(docs/specs/agent_revision.md Sec 5.4/7.2).

Covers: v1/v2 artifacts degrade honestly to UNKNOWN (never a false
RECORDED value); malformed ``agent_revisions`` data is isolated per role/
opponent rather than destroying the rest of an otherwise-readable
artifact; duplicate/self-play opponent occurrences stay unambiguous; and
deep verification's four distinct local-store outcomes (not checked, not
available, invalid, verified) are never conflated and never fall back to
live agent source.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from battle_engine.agent_evaluation import EvaluationRequest, EvaluationService
from battle_engine.agent_revisions import agent_revisions_root
from battle_engine.evaluation_history import FieldConfidence, RevisionVerificationStatus, adapt_any
from battle_engine.evaluation_history.verification import verify_summary

NOP_ACTION = "AgentAction(ActionKind.NOP)"


def _write_python_agent(root: Path, name: str, action: str = NOP_ACTION) -> Path:
    directory = root / "agents" / name
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text(
        json.dumps(
            {
                "kind": "python",
                "api_version": 1,
                "entrypoint": "agent.py:create_agent",
                "version": "1.0",
            }
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
    return directory


def _request(tmp_path: Path, **overrides) -> EvaluationRequest:
    defaults = {
        "candidate_id": "candidate",
        "opponent_ids": ("opponent",),
        "seeds": (1,),
        "output_dir": tmp_path / "eval-out",
        "ticks": 10,
        "data_root": tmp_path,
    }
    defaults.update(overrides)
    return EvaluationRequest(**defaults)


@pytest.fixture()
def evaluated(tmp_path: Path):
    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "baseline")
    _write_python_agent(tmp_path, "opponent")
    result = EvaluationService().run(
        _request(tmp_path, baseline_id="baseline")
    )
    return tmp_path, result


# ---------------------------------------------------------------------------
# v1/v2 legacy artifacts: honest UNKNOWN, never a guessed RECORDED value
# ---------------------------------------------------------------------------


def test_v1_artifact_revision_fields_are_unknown(tmp_path: Path) -> None:
    v1_artifact = {
        "schema": "bytefray.evaluation",
        "schema_version": 1,
        "evaluation_id": "evaluation_abc123",
        "candidate_id": "candidate",
        "opponent_ids": ["opponent"],
        "seeds": [1],
        "ticks": 10,
        "complete": True,
        "cells": [],
    }
    path = tmp_path / "evaluation.json"
    path.write_text(json.dumps(v1_artifact), encoding="utf-8")
    summary = adapt_any(path)
    assert summary.candidate_agent_revision_id.confidence == FieldConfidence.UNKNOWN
    assert summary.baseline_agent_revision_id.confidence == FieldConfidence.UNKNOWN


def test_v2_shaped_artifact_without_agent_revisions_key_is_unknown(tmp_path: Path, evaluated) -> None:
    """A genuine pre-Phase-3 v2 artifact (schema_version 2, no
    "agent_revisions" key at all) must read as UNKNOWN, not crash and not
    infer a value from "planned_identities" or anything else.
    """

    tmp_path, result = evaluated
    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    data["schema_version"] = 2
    del data["agent_revisions"]
    path = tmp_path / "v2-shaped.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    summary = adapt_any(path)
    assert summary.schema.schema_version == 2
    assert summary.candidate_agent_revision_id.confidence == FieldConfidence.UNKNOWN
    assert summary.baseline_agent_revision_id.confidence == FieldConfidence.UNKNOWN
    for cell in summary.cells:
        assert cell.opponent_agent_revision_id.confidence == FieldConfidence.UNKNOWN


# ---------------------------------------------------------------------------
# v3 artifacts: honest RECORDED values, malformed entries isolated
# ---------------------------------------------------------------------------


def test_v3_artifact_exposes_recorded_revision_ids(evaluated) -> None:
    _tmp_path, result = evaluated
    summary = adapt_any(result.state_path)
    assert summary.schema.schema_version == 3
    assert summary.candidate_agent_revision_id.confidence == FieldConfidence.RECORDED
    assert summary.baseline_agent_revision_id.confidence == FieldConfidence.RECORDED
    assert summary.candidate_agent_revision_error.confidence == FieldConfidence.RECORDED
    assert summary.candidate_agent_revision_error.value is None
    opponent_cells = [c for c in summary.cells if c.opponent_id == "opponent"]
    assert opponent_cells
    assert opponent_cells[0].opponent_agent_revision_id.confidence == FieldConfidence.RECORDED


def test_malformed_candidate_revision_entry_does_not_affect_baseline_or_opponent(
    evaluated,
) -> None:
    """One malformed ``agent_revisions`` entry must not unnecessarily
    destroy unrelated valid history data (v0.8 audit requirement) --
    corrupting only the candidate's entry must leave baseline/opponent
    fields exactly as they'd have read without the corruption.
    """

    tmp_path, result = evaluated
    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    data["agent_revisions"]["candidate"] = "not-a-mapping"
    path = tmp_path / "corrupted.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    summary = adapt_any(path)
    assert summary.candidate_agent_revision_id.confidence == FieldConfidence.UNKNOWN
    assert summary.baseline_agent_revision_id.confidence == FieldConfidence.RECORDED
    opponent_cells = [c for c in summary.cells if c.opponent_id == "opponent"]
    assert opponent_cells[0].opponent_agent_revision_id.confidence == FieldConfidence.RECORDED


def test_malformed_opponent_revision_id_type_degrades_to_unknown(evaluated) -> None:
    tmp_path, result = evaluated
    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    data["agent_revisions"]["opponents"][0]["agent_revision_id"] = 12345
    path = tmp_path / "corrupted-opponent.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    summary = adapt_any(path)
    opponent_cells = [c for c in summary.cells if c.opponent_id == "opponent"]
    assert opponent_cells[0].opponent_agent_revision_id.confidence == FieldConfidence.UNKNOWN
    # Candidate/baseline, sitting under different keys, are unaffected.
    assert summary.candidate_agent_revision_id.confidence == FieldConfidence.RECORDED


# ---------------------------------------------------------------------------
# Self-play / duplicate opponent occurrences stay unambiguous
# ---------------------------------------------------------------------------


def test_duplicate_opponent_occurrences_map_to_the_same_revision_id_unambiguously(
    tmp_path: Path,
) -> None:
    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    result = EvaluationService().run(
        _request(tmp_path, opponent_ids=("opponent", "opponent"), seeds=(1, 2))
    )
    summary = adapt_any(result.state_path)
    opponent_cells = [c for c in summary.cells if c.opponent_id == "opponent"]
    assert len(opponent_cells) == 4  # 2 opponent occurrences x 2 seeds
    ids = {cell.opponent_agent_revision_id.value for cell in opponent_cells}
    assert len(ids) == 1
    assert None not in ids


# ---------------------------------------------------------------------------
# Deep verification: four distinct outcomes, never conflated, never a live-source fallback
# ---------------------------------------------------------------------------


def test_verify_summary_not_checked_without_verify(evaluated) -> None:
    """Ordinary (non-``--verify``) adaptation never populates revision
    verification -- ``verify_summary`` must be called explicitly."""

    _tmp_path, result = evaluated
    summary = adapt_any(result.state_path)
    assert summary.candidate_revision_verification == RevisionVerificationStatus.NOT_CHECKED
    assert summary.cells[0].opponent_revision_verification == RevisionVerificationStatus.NOT_CHECKED


def test_verify_summary_reports_verified_for_healthy_local_snapshot(evaluated) -> None:
    tmp_path, result = evaluated
    summary = adapt_any(result.state_path)
    verified_summary, verification = verify_summary(summary, data_root=tmp_path)
    assert verified_summary.candidate_revision_verification == RevisionVerificationStatus.VERIFIED
    assert verified_summary.baseline_revision_verification == RevisionVerificationStatus.VERIFIED
    assert verified_summary.cells[0].opponent_revision_verification == RevisionVerificationStatus.VERIFIED
    assert verification.revision_issues == ()
    assert verification.all_eligible_verified is True


def test_verify_summary_reports_not_available_for_missing_store_never_as_corruption(
    evaluated,
) -> None:
    """A copied/relocated artifact whose original revision store is absent
    must not crash, and must not be reported as corruption -- only as
    "not available here". Ordinary match-cell verification must be
    unaffected by the missing revision store.
    """

    tmp_path, result = evaluated
    empty_root = tmp_path / "no-store-here"
    empty_root.mkdir()
    summary = adapt_any(result.state_path)
    verified_summary, verification = verify_summary(summary, data_root=empty_root)
    assert verified_summary.candidate_revision_verification == RevisionVerificationStatus.NOT_AVAILABLE
    assert verified_summary.cells[0].opponent_revision_verification == RevisionVerificationStatus.NOT_AVAILABLE
    assert verification.revision_issues == ()
    # The match/replay verification for the cell itself is untouched by a
    # missing revision store -- these are independent evidence dimensions.
    assert verification.all_eligible_verified is True


def test_verify_summary_reports_invalid_for_tampered_snapshot_and_fails_overall(
    evaluated,
) -> None:
    tmp_path, result = evaluated
    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    candidate_revision_id = data["agent_revisions"]["candidate"]["agent_revision_id"]
    store_root = agent_revisions_root(tmp_path)
    (store_root / candidate_revision_id / "files" / "agent.py").write_bytes(b"tampered")

    summary = adapt_any(result.state_path)
    verified_summary, verification = verify_summary(summary, data_root=tmp_path)
    assert verified_summary.candidate_revision_verification == RevisionVerificationStatus.INVALID
    assert verification.revision_issues != ()
    assert verification.all_eligible_verified is False


def test_deep_verification_never_falls_back_to_live_agent_source(evaluated) -> None:
    """Editing the live agent after evaluation must not change what
    verification reports -- only the durable store snapshot is consulted,
    never the current on-disk agent directory.
    """

    tmp_path, result = evaluated
    (tmp_path / "agents" / "candidate" / "agent.py").write_text(
        "from battle_engine.agent_api import ActionKind, AgentAction\n"
        "class Agent:\n"
        "    def reset(self, context): pass\n"
        f"    def act(self, observation): return {NOP_ACTION}\n"
        "def create_agent(): return Agent()\n"
        "# edited after evaluation\n",
        encoding="utf-8",
    )
    summary = adapt_any(result.state_path)
    verified_summary, verification = verify_summary(summary, data_root=tmp_path)
    # The store snapshot is untouched by the live edit, so it still verifies.
    assert verified_summary.candidate_revision_verification == RevisionVerificationStatus.VERIFIED
    assert verification.revision_issues == ()
