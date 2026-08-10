"""battle_engine.evaluation_history.verification: deep-verification path (B3/M4)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from battle_engine.agent_evaluation import EvaluationRequest, EvaluationService
from battle_engine.evaluation_history import adapt_any
from battle_engine.evaluation_history.models import ArtifactPathEscapeError, resolve_contained_path
from battle_engine.evaluation_history.verification import verify_cell, verify_summary

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
        "ticks": 5,
        "data_root": tmp_path,
    }
    defaults.update(overrides)
    result = EvaluationService().run(EvaluationRequest(**defaults))
    return result.state_path


# ---------------------------------------------------------------------------
# verify_cell / verify_summary
# ---------------------------------------------------------------------------


def test_verify_summary_passes_for_an_untampered_v2_artifact(tmp_path: Path):
    state_path = _run_v2(tmp_path)
    summary = adapt_any(state_path)
    verified_summary, verification = verify_summary(summary)
    assert verification.eligible_count == 1
    assert verification.verified_count == 1
    assert verification.all_eligible_verified is True
    assert verified_summary.cells[0].verified is True
    assert verified_summary.cells[0].verify_error is None


def test_ordinary_adaptation_never_sets_verified(tmp_path: Path):
    state_path = _run_v2(tmp_path)
    summary = adapt_any(state_path)
    assert summary.cells[0].verified is None
    assert summary.cells[0].verify_error is None


def test_verify_detects_missing_nested_result(tmp_path: Path):
    state_path = _run_v2(tmp_path)
    summary = adapt_any(state_path)
    result_path = summary.location.directory / summary.cells[0].artifact_dir / "result.json"
    result_path.unlink()

    _, verification = verify_summary(summary)
    assert verification.verified_count == 0
    assert "missing nested result" in verification.failed[0].error


def test_verify_detects_replay_digest_tamper(tmp_path: Path):
    state_path = _run_v2(tmp_path)
    summary = adapt_any(state_path)
    replay_path = summary.location.directory / summary.cells[0].artifact_dir / "replay.jsonl"
    with replay_path.open("a", encoding="utf-8") as handle:
        handle.write("\n")

    _, verification = verify_summary(summary)
    assert verification.verified_count == 0
    assert "replay verification failed" in verification.failed[0].error


def test_verify_detects_wrong_seed(tmp_path: Path):
    state_path = _run_v2(tmp_path)
    summary = adapt_any(state_path)
    result_path = summary.location.directory / summary.cells[0].artifact_dir / "result.json"
    data = json.loads(result_path.read_text(encoding="utf-8"))
    data["reproducibility"]["seed"] = 999999
    result_path.write_text(json.dumps(data), encoding="utf-8")

    _, verification = verify_summary(summary)
    assert verification.verified_count == 0
    assert "seed" in verification.failed[0].error


def test_verify_detects_wrong_match_id(tmp_path: Path):
    state_path = _run_v2(tmp_path)
    data = json.loads(state_path.read_text(encoding="utf-8"))
    data["cells"][0]["match_id"] = "evaluation-match_deadbeefdeadbeefdeadbeef"
    state_path.write_text(json.dumps(data), encoding="utf-8")
    summary = adapt_any(state_path)

    _, verification = verify_summary(summary)
    assert verification.verified_count == 0
    assert "match_id" in verification.failed[0].error


def test_verify_detects_wrong_entrant_order(tmp_path: Path):
    state_path = _run_v2(tmp_path)
    summary = adapt_any(state_path)
    result_path = summary.location.directory / summary.cells[0].artifact_dir / "result.json"
    data = json.loads(result_path.read_text(encoding="utf-8"))
    data["entrants"] = list(reversed(data["entrants"]))
    result_path.write_text(json.dumps(data), encoding="utf-8")

    _, verification = verify_summary(summary)
    assert verification.verified_count == 0
    assert "entrant order" in verification.failed[0].error


def test_verify_detects_wrong_entrant_identity(tmp_path: Path):
    state_path = _run_v2(tmp_path)
    summary = adapt_any(state_path)
    result_path = summary.location.directory / summary.cells[0].artifact_dir / "result.json"
    data = json.loads(result_path.read_text(encoding="utf-8"))
    for entrant in data["entrants"]:
        if entrant["agent_id"] == "B":
            entrant["metadata"]["source_sha256"] = "0" * 64
    result_path.write_text(json.dumps(data), encoding="utf-8")

    _, verification = verify_summary(summary)
    assert verification.verified_count == 0
    assert "identity" in verification.failed[0].error


def test_verify_ineligible_cells_are_skipped_not_counted(tmp_path: Path):
    state_path = _run_v2(tmp_path)
    data = json.loads(state_path.read_text(encoding="utf-8"))
    data["cells"][0]["status"] = "failed"
    data["cells"][0]["outcome"] = None
    state_path.write_text(json.dumps(data), encoding="utf-8")
    summary = adapt_any(state_path)

    _, verification = verify_summary(summary)
    assert verification.eligible_count == 0
    assert verification.verified_count == 0
    # Zero eligible cells must never read as "verified" (no vacuous true).
    assert verification.all_eligible_verified is False


# ---------------------------------------------------------------------------
# M4: artifact path containment
# ---------------------------------------------------------------------------


def test_resolve_contained_path_accepts_a_simple_relative_path(tmp_path: Path):
    base = tmp_path / "eval"
    (base / "matches" / "cell-1").mkdir(parents=True)
    resolved = resolve_contained_path(base, "matches/cell-1")
    assert resolved == (base / "matches" / "cell-1").resolve()


def test_resolve_contained_path_rejects_dotdot_escape(tmp_path: Path):
    base = tmp_path / "eval"
    base.mkdir()
    (tmp_path / "outside").mkdir()
    with pytest.raises(ArtifactPathEscapeError):
        resolve_contained_path(base, "../outside")


def test_resolve_contained_path_rejects_windows_absolute_path(tmp_path: Path):
    base = tmp_path / "eval"
    base.mkdir()
    with pytest.raises(ArtifactPathEscapeError):
        resolve_contained_path(base, "C:\\Windows\\System32")


@pytest.mark.skipif(os.name == "nt", reason="symlink creation requires elevated privileges on Windows")
def test_resolve_contained_path_rejects_symlink_escape(tmp_path: Path):
    base = tmp_path / "eval"
    base.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("nope", encoding="utf-8")
    link = base / "escape"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ArtifactPathEscapeError):
        resolve_contained_path(base, "escape")


def test_verify_cell_reports_path_escape_as_failure(tmp_path: Path):
    state_path = _run_v2(tmp_path)
    summary = adapt_any(state_path)
    cell = summary.cells[0]
    from dataclasses import replace

    escaping_cell = replace(cell, artifact_dir="../outside")
    outcome = verify_cell(escaping_cell, summary.location.directory)
    assert outcome.eligible is True
    assert outcome.verified is False
    assert "escapes" in (outcome.error or "")
