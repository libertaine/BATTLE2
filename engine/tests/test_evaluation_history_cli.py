"""``bytefray agents evaluations list|show|compare`` CLI (docs/specs/evaluation_history.md Sec 15)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from battle_engine.agent_evaluation import EvaluationRequest, EvaluationService
from battle_engine.evaluation_history.cli import main as evaluations_main

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


def _run(
    tmp_path: Path,
    output_dir: Path,
    candidate: str = "candidate",
    *,
    seeds: tuple[int, ...] = (1,),
) -> str:
    _write_python_agent(tmp_path, candidate) if not (tmp_path / "agents" / candidate).is_dir() else None
    if not (tmp_path / "agents" / "opponent").is_dir():
        _write_python_agent(tmp_path, "opponent")
    result = EvaluationService().run(
        EvaluationRequest(
            candidate_id=candidate,
            opponent_ids=("opponent",),
            seeds=seeds,
            output_dir=output_dir,
            ticks=10,
            data_root=tmp_path,
            # This suite predates entrant orientation (v0.9 Phase 6) and its
            # assertions are about list/show/compare CLI mechanics
            # orthogonal to it -- pinned to the legacy single-orientation
            # matrix shape/size.
            both_orientations=False,
        )
    )
    return result.evaluation_id


def test_cli_list_human_output(tmp_path: Path, capsys):
    root = tmp_path / "runs" / "evaluations"
    _run(tmp_path, root / "e1")
    code = evaluations_main(["list", "--root", str(root)])
    out = capsys.readouterr().out
    assert code == 0
    assert "evaluation-v2_" in out
    assert "candidate=candidate" in out


def test_cli_list_json_output_is_stable(tmp_path: Path, capsys):
    root = tmp_path / "runs" / "evaluations"
    _run(tmp_path, root / "e1")
    code = evaluations_main(["list", "--root", str(root), "--json"])
    out = capsys.readouterr().out
    assert code == 0
    data = json.loads(out)
    assert len(data["entries"]) == 1
    assert data["entries"][0]["summary"]["candidate_id"] == "candidate"


def test_cli_list_isolates_degraded_sibling(tmp_path: Path, capsys):
    root = tmp_path / "runs" / "evaluations"
    _run(tmp_path, root / "good")
    bad = root / "bad"
    bad.mkdir(parents=True)
    (bad / "evaluation.json").write_text("not json", encoding="utf-8")

    code = evaluations_main(["list", "--root", str(root)])
    out = capsys.readouterr().out
    assert code == 0
    assert "UNREADABLE" in out
    assert "evaluation-v2_" in out


def test_cli_show_human(tmp_path: Path, capsys):
    output_dir = tmp_path / "eval-out"
    evaluation_id = _run(tmp_path, output_dir)
    code = evaluations_main(["show", str(output_dir), "--verify"])
    out = capsys.readouterr().out
    assert code == 0
    assert evaluation_id in out
    assert "verified: True" in out


def test_cli_show_reports_opponent_with_no_recorded_revision_as_unknown(tmp_path: Path, capsys):
    """Regression test: an opponent whose ``agent_revision_id`` is absent
    (a legacy artifact, or a real archive-error case where archival never
    produced an id) must still get an explicit ``opponent:<id>: unknown``
    line -- ``_print_agent_revisions``'s own docstring promises "unknown ...
    is shown explicitly, never silently omitted," matching how candidate/
    baseline are already handled. Previously the opponent-collection loop
    only recorded an opponent at all when its revision id was truthy, so an
    opponent lacking one was dropped from the printed block entirely rather
    than shown as unknown."""

    output_dir = tmp_path / "eval-out"
    _run(tmp_path, output_dir)
    state_path = output_dir / "evaluation.json"
    data = json.loads(state_path.read_text(encoding="utf-8"))
    data["agent_revisions"]["opponents"][0]["agent_revision_id"] = None
    state_path.write_text(json.dumps(data), encoding="utf-8")

    code = evaluations_main(["show", str(output_dir)])
    out = capsys.readouterr().out
    assert code == 0
    assert "opponent:opponent: unknown" in out


def test_cli_show_json(tmp_path: Path, capsys):
    output_dir = tmp_path / "eval-out"
    _run(tmp_path, output_dir)
    code = evaluations_main(["show", str(output_dir), "--json"])
    out = capsys.readouterr().out
    assert code == 0
    data = json.loads(out)
    assert data["candidate_id"] == "candidate"


# ---------------------------------------------------------------------------
# H2: execution-context provenance exposed in show/compare
# ---------------------------------------------------------------------------


def test_cli_show_reports_mixed_execution_contexts(tmp_path: Path, capsys):
    output_dir = tmp_path / "eval-out"
    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent_a")
    _write_python_agent(tmp_path, "opponent_b")
    EvaluationService().run(
        EvaluationRequest(
            candidate_id="candidate",
            opponent_ids=("opponent_a", "opponent_b"),
            seeds=(1,),
            output_dir=output_dir,
            ticks=10,
            data_root=tmp_path,
        )
    )
    eval_path = output_dir / "evaluation.json"
    data = json.loads(eval_path.read_text(encoding="utf-8"))
    other_context = dict(
        data["execution_contexts"][0], context_id="evaluation-context_other", python_version="9.9.9"
    )
    data["execution_contexts"].append(other_context)
    data["cells"][1]["execution_context_id"] = other_context["context_id"]
    eval_path.write_text(json.dumps(data), encoding="utf-8")

    code = evaluations_main(["show", str(output_dir)])
    out = capsys.readouterr().out
    assert code == 0
    assert "MIXED EXECUTION CONTEXTS" in out


def test_cli_compare_across_incompatible_contexts_is_inconclusive_not_a_regression(
    tmp_path: Path, capsys
):
    left_dir = tmp_path / "left"
    right_dir = tmp_path / "right"
    _run(tmp_path, left_dir)
    _run(tmp_path, right_dir)

    right_path = right_dir / "evaluation.json"
    data = json.loads(right_path.read_text(encoding="utf-8"))
    other_context = dict(
        data["execution_contexts"][0], context_id="evaluation-context_other", python_version="9.9.9"
    )
    data["execution_contexts"] = [other_context]
    data["cells"][0]["execution_context_id"] = other_context["context_id"]
    real_outcome = data["cells"][0]["outcome"]
    data["cells"][0]["outcome"] = "loss" if real_outcome != "loss" else "win"
    right_path.write_text(json.dumps(data), encoding="utf-8")

    code = evaluations_main(["compare", str(left_dir), str(right_dir), "--json"])
    out = capsys.readouterr().out
    assert code == 0
    result = json.loads(out)
    assert result["rows"][0]["verdict"] == "inconclusive"
    assert "execution context" in result["rows"][0]["reason"]
    assert result["denominators"]["regressed"] == 0
    assert result["denominators"]["improved"] == 0


def test_cli_show_unreadable_selector_exits_1(tmp_path: Path, capsys):
    bad_dir = tmp_path / "bad"
    bad_dir.mkdir(parents=True)
    (bad_dir / "evaluation.json").write_text("not json", encoding="utf-8")
    code = evaluations_main(["show", str(bad_dir)])
    assert code == 1


def test_cli_show_missing_selector_exits_2(tmp_path: Path, capsys):
    code = evaluations_main(["show", "evaluation-v2_doesnotexist", "--root", str(tmp_path)])
    assert code == 2


def test_cli_show_ambiguous_selector_exits_2(tmp_path: Path, capsys):
    import shutil

    root = tmp_path / "runs" / "evaluations"
    original = root / "original"
    _run(tmp_path, original)
    shutil.copytree(original, root / "copy")

    evaluation_id = json.loads((original / "evaluation.json").read_text(encoding="utf-8"))["evaluation_id"]
    code = evaluations_main(["show", evaluation_id, "--root", str(root)])
    assert code == 2


def test_cli_compare_regressions_exit_zero(tmp_path: Path, capsys):
    left_dir = tmp_path / "left"
    right_dir = tmp_path / "right"
    _run(tmp_path, left_dir)
    _run(tmp_path, right_dir, candidate="candidate")

    code = evaluations_main(["compare", str(left_dir), str(right_dir)])
    out = capsys.readouterr().out
    assert code == 0  # a comparison result -- even with regressions -- is a successful command
    assert "orientation: right_relative_to_left" in out


def test_cli_compare_human_output_discloses_ambiguous_duplicate_groups(tmp_path: Path, capsys):
    """v1.3 CLI/Designer consistency fix (docs/specs/evaluation_history.md Sec 16).

    The v1.1 Designer already surfaced ``ambiguous_duplicate_groups`` in its
    comparison summary; the CLI's own human-readable ``_print_compare`` did
    not, even though the count was always present in ``--json`` output and
    in ``ComparisonDenominators`` itself. This asserts the human-readable
    line now includes it too, so the two presentations never disclose
    different information about the same comparison result.
    """

    left_dir = tmp_path / "left"
    right_dir = tmp_path / "right"
    _run(tmp_path, left_dir, seeds=(1, 2))
    _run(tmp_path, right_dir, candidate="candidate", seeds=(1, 2))

    # Corrupt one coordinate deliberately: two left cells now claim the
    # same (opponent, seed, occurrence) coordinate while seed 2 remains a
    # normal directly-comparable row. Comparison must report, rather than
    # guess-pair, that seed-1 group; retaining seed 2 keeps compare's exit
    # status at zero so this test remains specifically about presentation.
    left_path = left_dir / "evaluation.json"
    left_data = json.loads(left_path.read_text(encoding="utf-8"))
    duplicate = dict(left_data["cells"][0])
    duplicate["schedule_id"] += "-duplicate"
    left_data["cells"].append(duplicate)
    left_path.write_text(json.dumps(left_data), encoding="utf-8")

    code = evaluations_main(["compare", str(left_dir), str(right_dir)])
    out = capsys.readouterr().out
    assert code == 0
    assert "ambiguous_duplicate_groups=1" in out


def test_cli_compare_json_output(tmp_path: Path, capsys):
    left_dir = tmp_path / "left"
    right_dir = tmp_path / "right"
    _run(tmp_path, left_dir)
    _run(tmp_path, right_dir)

    code = evaluations_main(["compare", str(left_dir), str(right_dir), "--json"])
    out = capsys.readouterr().out
    assert code == 0
    data = json.loads(out)
    assert data["orientation"] == "right_relative_to_left"
    assert "denominators" in data


def test_cli_compare_no_comparable_cells_exits_1(tmp_path: Path, capsys):
    left_dir = tmp_path / "left"
    right_dir = tmp_path / "right"
    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent_left")
    _write_python_agent(tmp_path, "opponent_right")
    EvaluationService().run(
        EvaluationRequest(
            candidate_id="candidate", opponent_ids=("opponent_left",), seeds=(1,),
            output_dir=left_dir, ticks=10, data_root=tmp_path,
        )
    )
    EvaluationService().run(
        EvaluationRequest(
            candidate_id="candidate", opponent_ids=("opponent_right",), seeds=(1,),
            output_dir=right_dir, ticks=10, data_root=tmp_path,
        )
    )
    code = evaluations_main(["compare", str(left_dir), str(right_dir)])
    assert code == 1


# ---------------------------------------------------------------------------
# B3: `compare --verify` must actually deep-verify
# ---------------------------------------------------------------------------


def test_cli_compare_verify_both_sides_verified(tmp_path: Path, capsys):
    left_dir = tmp_path / "left"
    right_dir = tmp_path / "right"
    _run(tmp_path, left_dir)
    _run(tmp_path, right_dir)

    code = evaluations_main(["compare", str(left_dir), str(right_dir), "--verify"])
    out = capsys.readouterr().out
    assert code == 0
    assert "evidence: deep-verified (--verify)" in out
    assert "LEFT FAILED" not in out
    assert "RIGHT FAILED" not in out


def test_cli_compare_verify_json_reports_deep_verified_true(tmp_path: Path, capsys):
    left_dir = tmp_path / "left"
    right_dir = tmp_path / "right"
    _run(tmp_path, left_dir)
    _run(tmp_path, right_dir)

    code = evaluations_main(["compare", str(left_dir), str(right_dir), "--verify", "--json"])
    out = capsys.readouterr().out
    assert code == 0
    data = json.loads(out)
    assert data["deep_verified"] is True
    assert data["left_verify_error"] is None
    assert data["right_verify_error"] is None


def test_cli_compare_ordinary_comparison_is_not_deep_verified(tmp_path: Path, capsys):
    left_dir = tmp_path / "left"
    right_dir = tmp_path / "right"
    _run(tmp_path, left_dir)
    _run(tmp_path, right_dir)

    code = evaluations_main(["compare", str(left_dir), str(right_dir)])
    out = capsys.readouterr().out
    assert code == 0
    assert "evidence: NOT deep-verified" in out

    code = evaluations_main(["compare", str(left_dir), str(right_dir), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    assert data["deep_verified"] is False


def test_cli_compare_verify_detects_missing_nested_result(tmp_path: Path, capsys):
    left_dir = tmp_path / "left"
    right_dir = tmp_path / "right"
    _run(tmp_path, left_dir)
    _run(tmp_path, right_dir)

    data = json.loads((left_dir / "evaluation.json").read_text(encoding="utf-8"))
    result_path = left_dir / data["cells"][0]["artifact_dir"] / "result.json"
    result_path.unlink()

    code = evaluations_main(["compare", str(left_dir), str(right_dir), "--verify"])
    out = capsys.readouterr().out
    assert code == 1
    assert "LEFT FAILED" in out

    code = evaluations_main(["compare", str(left_dir), str(right_dir), "--verify", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 1
    assert data["deep_verified"] is False
    assert data["denominators"]["directly_comparable"] == 0
    assert data["denominators"]["improved"] == 0
    assert data["denominators"]["regressed"] == 0
    assert data["denominators"]["unchanged"] == 0
    assert all(row["verdict"] == "inconclusive" for row in data["rows"])


def test_cli_compare_verify_detects_missing_replay(tmp_path: Path, capsys):
    left_dir = tmp_path / "left"
    right_dir = tmp_path / "right"
    _run(tmp_path, left_dir)
    _run(tmp_path, right_dir)

    data = json.loads((left_dir / "evaluation.json").read_text(encoding="utf-8"))
    replay_path = left_dir / data["cells"][0]["artifact_dir"] / "replay.jsonl"
    replay_path.unlink()

    code = evaluations_main(["compare", str(left_dir), str(right_dir), "--verify"])
    out = capsys.readouterr().out
    assert code == 1
    assert "LEFT FAILED" in out

    code = evaluations_main(["compare", str(left_dir), str(right_dir), "--verify", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 1
    assert data["deep_verified"] is False
    assert data["denominators"]["directly_comparable"] == 0
    assert all(row["verdict"] == "inconclusive" for row in data["rows"])


def test_cli_compare_verify_detects_replay_digest_mismatch(tmp_path: Path, capsys):
    left_dir = tmp_path / "left"
    right_dir = tmp_path / "right"
    _run(tmp_path, left_dir)
    _run(tmp_path, right_dir)

    data = json.loads((left_dir / "evaluation.json").read_text(encoding="utf-8"))
    replay_path = left_dir / data["cells"][0]["artifact_dir"] / "replay.jsonl"
    with replay_path.open("a", encoding="utf-8") as handle:
        handle.write("\n")

    code = evaluations_main(["compare", str(left_dir), str(right_dir), "--verify"])
    out = capsys.readouterr().out
    assert code == 1
    assert "LEFT FAILED" in out

    code = evaluations_main(["compare", str(left_dir), str(right_dir), "--verify", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 1
    assert data["deep_verified"] is False
    assert data["denominators"]["directly_comparable"] == 0
    assert all(row["verdict"] == "inconclusive" for row in data["rows"])


def test_cli_compare_verify_detects_wrong_entrant_identity(tmp_path: Path, capsys):
    left_dir = tmp_path / "left"
    right_dir = tmp_path / "right"
    _run(tmp_path, left_dir)
    _run(tmp_path, right_dir)

    eval_data = json.loads((left_dir / "evaluation.json").read_text(encoding="utf-8"))
    result_path = left_dir / eval_data["cells"][0]["artifact_dir"] / "result.json"
    result_data = json.loads(result_path.read_text(encoding="utf-8"))
    for entrant in result_data["entrants"]:
        if entrant["agent_id"] == "B":
            entrant["metadata"]["source_sha256"] = "0" * 64
    result_path.write_text(json.dumps(result_data), encoding="utf-8")

    code = evaluations_main(["compare", str(left_dir), str(right_dir), "--verify"])
    out = capsys.readouterr().out
    assert code == 1
    assert "LEFT FAILED" in out

    code = evaluations_main(["compare", str(left_dir), str(right_dir), "--verify", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 1
    assert data["deep_verified"] is False
    assert data["denominators"]["directly_comparable"] == 0
    assert all(row["verdict"] == "inconclusive" for row in data["rows"])


def test_cli_compare_verify_detects_tampered_evaluation_outcome(tmp_path: Path, capsys):
    """The nested result/replay are untouched and internally consistent, but
    the evaluation.json cell's own recorded outcome was tampered -- deep
    verification must catch the mismatch between the canonical result's
    winner and what the evaluation cell claims."""

    left_dir = tmp_path / "left"
    right_dir = tmp_path / "right"
    _run(tmp_path, left_dir)
    _run(tmp_path, right_dir)

    eval_path = left_dir / "evaluation.json"
    data = json.loads(eval_path.read_text(encoding="utf-8"))
    real_outcome = data["cells"][0]["outcome"]
    data["cells"][0]["outcome"] = "loss" if real_outcome != "loss" else "win"
    eval_path.write_text(json.dumps(data), encoding="utf-8")

    code = evaluations_main(["compare", str(left_dir), str(right_dir), "--verify"])
    out = capsys.readouterr().out
    assert code == 1
    assert "LEFT FAILED" in out

    code = evaluations_main(["compare", str(left_dir), str(right_dir), "--verify", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 1
    assert data["deep_verified"] is False
    assert data["denominators"]["directly_comparable"] == 0
    assert all(row["verdict"] == "inconclusive" for row in data["rows"])


def test_cli_compare_verify_detects_wrong_result_seed(tmp_path: Path, capsys):
    left_dir = tmp_path / "left"
    right_dir = tmp_path / "right"
    _run(tmp_path, left_dir)
    _run(tmp_path, right_dir)

    eval_data = json.loads((left_dir / "evaluation.json").read_text(encoding="utf-8"))
    result_path = left_dir / eval_data["cells"][0]["artifact_dir"] / "result.json"
    result_data = json.loads(result_path.read_text(encoding="utf-8"))
    result_data["reproducibility"]["seed"] = 999999
    result_path.write_text(json.dumps(result_data), encoding="utf-8")

    code = evaluations_main(["compare", str(left_dir), str(right_dir), "--verify"])
    out = capsys.readouterr().out
    assert code == 1
    assert "LEFT FAILED" in out

    code = evaluations_main(["compare", str(left_dir), str(right_dir), "--verify", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 1
    assert data["deep_verified"] is False
    assert data["denominators"]["directly_comparable"] == 0
    assert all(row["verdict"] == "inconclusive" for row in data["rows"])


def test_cli_compare_verify_detects_wrong_match_id(tmp_path: Path, capsys):
    left_dir = tmp_path / "left"
    right_dir = tmp_path / "right"
    _run(tmp_path, left_dir)
    _run(tmp_path, right_dir)

    eval_path = left_dir / "evaluation.json"
    data = json.loads(eval_path.read_text(encoding="utf-8"))
    data["cells"][0]["match_id"] = "evaluation-match_deadbeefdeadbeefdeadbeef"
    eval_path.write_text(json.dumps(data), encoding="utf-8")

    code = evaluations_main(["compare", str(left_dir), str(right_dir), "--verify"])
    out = capsys.readouterr().out
    assert code == 1
    assert "LEFT FAILED" in out

    code = evaluations_main(["compare", str(left_dir), str(right_dir), "--verify", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 1
    assert data["deep_verified"] is False
    assert data["denominators"]["directly_comparable"] == 0
    assert all(row["verdict"] == "inconclusive" for row in data["rows"])


def test_cli_compare_verify_selected_side_failure_does_not_block_the_other(tmp_path: Path, capsys):
    """Only the side with the injected fault is reported as failed."""

    left_dir = tmp_path / "left"
    right_dir = tmp_path / "right"
    _run(tmp_path, left_dir)
    _run(tmp_path, right_dir)

    eval_data = json.loads((left_dir / "evaluation.json").read_text(encoding="utf-8"))
    result_path = left_dir / eval_data["cells"][0]["artifact_dir"] / "result.json"
    result_path.unlink()

    code = evaluations_main(["compare", str(left_dir), str(right_dir), "--verify"])
    out = capsys.readouterr().out
    assert code == 1
    assert "LEFT FAILED" in out
    assert "RIGHT FAILED" not in out


def test_cli_compare_verify_zero_eligible_cells_is_not_vacuously_verified(tmp_path: Path, capsys):
    """No completed/scored cells on one side must never be silently reported
    as ``deep_verified``/``verified`` (no vacuous verified=true)."""

    left_dir = tmp_path / "left"
    right_dir = tmp_path / "right"
    _run(tmp_path, left_dir)
    _run(tmp_path, right_dir)

    eval_path = right_dir / "evaluation.json"
    data = json.loads(eval_path.read_text(encoding="utf-8"))
    data["cells"][0]["status"] = "failed"
    data["cells"][0]["outcome"] = None
    eval_path.write_text(json.dumps(data), encoding="utf-8")

    code = evaluations_main(["compare", str(left_dir), str(right_dir), "--verify"])
    out = capsys.readouterr().out
    assert code == 1
    assert "RIGHT FAILED" in out
    assert "no eligible" in out

    code = evaluations_main(["compare", str(left_dir), str(right_dir), "--verify", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 1
    assert data["deep_verified"] is False
    assert data["denominators"]["directly_comparable"] == 0
    assert all(row["verdict"] == "inconclusive" for row in data["rows"])


def test_cli_invalid_verb_exits_2():
    with pytest.raises(SystemExit) as excinfo:
        evaluations_main(["bogus-verb"])
    assert excinfo.value.code == 2


def test_bytefray_dispatch_reaches_evaluations(tmp_path: Path, capsys):
    """The canonical dispatcher reaches evaluation history."""

    from battle_engine.command import main as bytefray_main

    root = tmp_path / "runs" / "evaluations"
    _run(tmp_path, root / "e1")

    code = bytefray_main(["agents", "evaluations", "list", "--root", str(root), "--json"])
    out1 = capsys.readouterr().out
    assert code == 0
    assert json.loads(out1)["entries"]
