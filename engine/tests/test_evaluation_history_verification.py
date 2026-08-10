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


def test_verify_detects_candidate_source_sha256_tamper(tmp_path: Path):
    """H1: previously only the opponent's identity was cross-checked here --
    a tampered *candidate* entrant identity went entirely uncaught."""

    state_path = _run_v2(tmp_path)
    summary = adapt_any(state_path)
    result_path = summary.location.directory / summary.cells[0].artifact_dir / "result.json"
    data = json.loads(result_path.read_text(encoding="utf-8"))
    for entrant in data["entrants"]:
        if entrant["agent_id"] == "A":  # TESTED_AGENT_SLOT -- the candidate
            entrant["metadata"]["source_sha256"] = "0" * 64
    result_path.write_text(json.dumps(data), encoding="utf-8")

    _, verification = verify_summary(summary)
    assert verification.verified_count == 0
    assert "candidate identity" in verification.failed[0].error
    assert "source_sha256" in verification.failed[0].error


def test_verify_detects_result_id_tamper(tmp_path: Path):
    """H1: a substituted result_id that leaves match_id/outcome untouched
    must still be caught -- previously result_id was never checked at all."""

    state_path = _run_v2(tmp_path)
    summary = adapt_any(state_path)
    result_path = summary.location.directory / summary.cells[0].artifact_dir / "result.json"
    data = json.loads(result_path.read_text(encoding="utf-8"))
    data["result_id"] = "result_deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    result_path.write_text(json.dumps(data), encoding="utf-8")

    _, verification = verify_summary(summary)
    assert verification.verified_count == 0
    assert "result_id" in verification.failed[0].error


def test_verify_detects_result_replay_header_disagreement(tmp_path: Path):
    """H1: the replay's own header must agree with the result envelope it
    was published alongside -- digest verification alone says nothing
    about the header record's own field values, so a header tampered to
    disagree with an otherwise-correct (and correctly-digested) replay
    must still be caught."""

    state_path = _run_v2(tmp_path)
    summary = adapt_any(state_path)
    cell_dir = summary.location.directory / summary.cells[0].artifact_dir
    result_path = cell_dir / "result.json"
    replay_path = cell_dir / "replay.jsonl"

    lines = replay_path.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    header["match_id"] = "evaluation-match_deadbeefdeadbeefdeadbeef"
    lines[0] = json.dumps(header)
    new_replay_text = "\n".join(lines) + "\n"
    replay_path.write_text(new_replay_text, encoding="utf-8")

    # Keep the result's own recorded replay digest matching the (now
    # header-tampered) bytes, so this test isolates header/envelope
    # disagreement from a plain digest mismatch (already covered by
    # test_verify_detects_replay_digest_tamper).
    import hashlib

    data = json.loads(result_path.read_text(encoding="utf-8"))
    data["replay"]["sha256"] = hashlib.sha256(replay_path.read_bytes()).hexdigest()
    result_path.write_text(json.dumps(data), encoding="utf-8")

    _, verification = verify_summary(summary)
    assert verification.verified_count == 0
    assert "header" in verification.failed[0].error


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


@pytest.mark.parametrize("value", ["C:evil.jsonl", "\\\\server\\share\\evil.jsonl"])
def test_resolve_contained_path_rejects_other_windows_drive_syntax(
    tmp_path: Path, value: str
):
    base = tmp_path / "eval"
    base.mkdir()
    with pytest.raises(ArtifactPathEscapeError):
        resolve_contained_path(base, value)


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


# ---------------------------------------------------------------------------
# H5: a result.json's own replay reference must be containment-checked too,
# not just the cell's artifact_dir -- a tampered result.json could otherwise
# point its replay filename outside the cell's own artifact directory.
# ---------------------------------------------------------------------------


def _tamper_replay_filename(result_path: Path, filename: str) -> None:
    data = json.loads(result_path.read_text(encoding="utf-8"))
    data["replay"]["filename"] = filename
    result_path.write_text(json.dumps(data), encoding="utf-8")


def test_verify_cell_rejects_dotdot_replay_filename(tmp_path: Path):
    state_path = _run_v2(tmp_path)
    summary = adapt_any(state_path)
    result_path = summary.location.directory / summary.cells[0].artifact_dir / "result.json"
    outside = tmp_path / "outside.jsonl"
    outside.write_text("not the real replay", encoding="utf-8")

    _tamper_replay_filename(result_path, "../../../outside.jsonl")

    _, verification = verify_summary(summary)
    assert verification.verified_count == 0
    assert "escapes" in verification.failed[0].error


def test_verify_cell_rejects_absolute_windows_replay_filename(tmp_path: Path):
    state_path = _run_v2(tmp_path)
    summary = adapt_any(state_path)
    result_path = summary.location.directory / summary.cells[0].artifact_dir / "result.json"

    _tamper_replay_filename(result_path, "C:\\Windows\\System32\\evil.jsonl")

    _, verification = verify_summary(summary)
    assert verification.verified_count == 0
    assert "escapes" in verification.failed[0].error


def test_verify_cell_rejects_alternate_drive_replay_filename(tmp_path: Path):
    state_path = _run_v2(tmp_path)
    summary = adapt_any(state_path)
    result_path = summary.location.directory / summary.cells[0].artifact_dir / "result.json"

    _tamper_replay_filename(result_path, "Z:\\nonexistent\\evil.jsonl")

    _, verification = verify_summary(summary)
    assert verification.verified_count == 0
    assert "escapes" in verification.failed[0].error


@pytest.mark.parametrize("filename", ["C:evil.jsonl", "\\\\server\\share\\evil.jsonl"])
def test_verify_cell_rejects_other_windows_drive_replay_filenames(
    tmp_path: Path, filename: str
):
    state_path = _run_v2(tmp_path)
    summary = adapt_any(state_path)
    result_path = summary.location.directory / summary.cells[0].artifact_dir / "result.json"

    _tamper_replay_filename(result_path, filename)

    _, verification = verify_summary(summary)
    assert verification.verified_count == 0
    assert "escapes" in verification.failed[0].error


@pytest.mark.skipif(os.name == "nt", reason="symlink creation requires elevated privileges on Windows")
def test_verify_cell_rejects_symlink_escape_replay_filename(tmp_path: Path):
    state_path = _run_v2(tmp_path)
    summary = adapt_any(state_path)
    cell_dir = summary.location.directory / summary.cells[0].artifact_dir
    result_path = cell_dir / "result.json"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.jsonl").write_text("nope", encoding="utf-8")
    link = cell_dir / "escape"
    link.symlink_to(outside, target_is_directory=True)

    _tamper_replay_filename(result_path, "escape/secret.jsonl")

    _, verification = verify_summary(summary)
    assert verification.verified_count == 0
    assert "escapes" in verification.failed[0].error


def test_verify_cell_still_works_after_the_whole_evaluation_directory_is_moved(tmp_path: Path):
    """A moved valid evaluation with legitimate relative paths must still
    verify -- containment is resolved against the directory as passed in
    at call time, never a path baked into the artifact."""

    import shutil

    original_root = tmp_path / "original"
    original_root.mkdir()
    state_path = _run_v2(original_root)
    moved_root = tmp_path / "moved" / "elsewhere"
    moved_root.parent.mkdir(parents=True)
    shutil.move(str(state_path.parent), str(moved_root))
    moved_state_path = moved_root / state_path.name

    summary = adapt_any(moved_state_path)
    _, verification = verify_summary(summary)
    assert verification.eligible_count == 1
    assert verification.verified_count == 1
    assert verification.all_eligible_verified is True
