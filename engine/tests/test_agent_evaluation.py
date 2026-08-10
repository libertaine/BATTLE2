from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from battle_engine.agent_evaluation import (
    BASELINE,
    CANDIDATE,
    SCHEMA_NAME,
    SCHEMA_VERSION,
    EvaluationCell,
    EvaluationConfigurationError,
    EvaluationRequest,
    EvaluationService,
    aggregate_cells,
    build_matrix,
    classify,
    compare_candidate_baseline,
    main,
    parse_opponents,
    parse_seed_list,
    parse_seed_range,
    read_evaluation,
    rerun_command,
    source_digest,
)
from battle_engine.agent_scaffold import create_agent as scaffold_create_agent
from battle_engine.agent_test import test_agent as run_development_test

ROOT = Path(__file__).resolve().parents[2]


def _write_python_agent(root: Path, name: str, action: str) -> Path:
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
    return directory


def _write_reset_failing_agent(root: Path, name: str, message: str = "boom") -> Path:
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
class Agent:
    def reset(self, context):
        raise RuntimeError({message!r})
    def act(self, observation):
        return None
def create_agent(): return Agent()
""",
        encoding="utf-8",
    )
    return directory


def _write_builtin_agent(root: Path, name: str) -> Path:
    directory = root / "agents" / name
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text(json.dumps({"name": name, "defaults": {}}), encoding="utf-8")
    return directory


NOP_ACTION = "AgentAction(ActionKind.NOP)"


def _request(tmp_path: Path, **overrides) -> EvaluationRequest:
    defaults = {
        "candidate_id": "candidate",
        "opponent_ids": ("opponent",),
        "seeds": (1,),
        "output_dir": tmp_path / "eval-out",
        "ticks": 20,
        "data_root": tmp_path,
    }
    defaults.update(overrides)
    return EvaluationRequest(**defaults)


# --------------------------------------------------------------------------
# Matrix construction (Sec 7/18)
# --------------------------------------------------------------------------


def test_matrix_cell_count_and_order_single_candidate():
    request = EvaluationRequest(
        candidate_id="cand",
        opponent_ids=("opp_a", "opp_b"),
        seeds=(1, 2, 3),
        output_dir=Path("out"),
    )
    matrix = build_matrix(request, "evaluation_x")
    assert len(matrix) == 6
    assert [(c.subject_role, c.opponent_id, c.seed) for c in matrix] == [
        (CANDIDATE, "opp_a", 1),
        (CANDIDATE, "opp_a", 2),
        (CANDIDATE, "opp_a", 3),
        (CANDIDATE, "opp_b", 1),
        (CANDIDATE, "opp_b", 2),
        (CANDIDATE, "opp_b", 3),
    ]


def test_matrix_cell_count_with_baseline_matches_expected_formula():
    request = EvaluationRequest(
        candidate_id="cand",
        baseline_id="base",
        opponent_ids=("a", "b", "c", "d"),
        seeds=(1, 2, 3, 4, 5),
        output_dir=Path("out"),
    )
    matrix = build_matrix(request, "evaluation_x")
    assert len(matrix) == 2 * 4 * 5 == 40
    roles = [cell.subject_role for cell in matrix]
    assert roles[:20] == [CANDIDATE] * 20
    assert roles[20:] == [BASELINE] * 20


def test_matrix_preserves_repeated_opponent_and_seed_as_distinct_cells():
    request = EvaluationRequest(
        candidate_id="cand",
        opponent_ids=("opp", "opp"),
        seeds=(1, 1),
        output_dir=Path("out"),
    )
    matrix = build_matrix(request, "evaluation_x")
    assert len(matrix) == 4
    # Every cell is distinct by both artifact_dir and schedule_id despite
    # identical inputs producing identical (opponent, seed) pairs -- ordinal
    # is baked into the label/dir and into the schedule_id hash itself, so a
    # repeated cell can't collide in a schedule_id-keyed lookup (regression
    # for the resume/comparison bugs this collision used to cause).
    assert len({cell.artifact_dir for cell in matrix}) == 4
    assert len({cell.schedule_id for cell in matrix}) == 4


def test_candidate_may_equal_an_opponent(tmp_path):
    service = EvaluationService()
    scaffold_create_agent("solo", data_root=tmp_path, resource_root=ROOT)
    request = _request(tmp_path, candidate_id="solo", opponent_ids=("solo",))
    result = service.run(request)
    assert result.cells[0].status == "completed"


def test_candidate_equal_to_baseline_is_rejected(tmp_path):
    service = EvaluationService()
    scaffold_create_agent("solo", data_root=tmp_path, resource_root=ROOT)
    request = _request(tmp_path, candidate_id="solo", baseline_id="solo", opponent_ids=("solo",))
    with pytest.raises(EvaluationConfigurationError):
        service.run(request)


# --------------------------------------------------------------------------
# Seed/opponent parsing (Sec 12/18)
# --------------------------------------------------------------------------


def test_parse_opponents_splits_and_strips():
    assert parse_opponents(" a, b ,c") == ("a", "b", "c")


def test_parse_opponents_rejects_empty():
    with pytest.raises(EvaluationConfigurationError):
        parse_opponents("  ,  ,")


def test_parse_seed_list():
    assert parse_seed_list("1, 2,3") == (1, 2, 3)


def test_parse_seed_list_rejects_non_integer():
    with pytest.raises(EvaluationConfigurationError):
        parse_seed_list("1,x")


def test_parse_seed_range_inclusive():
    assert parse_seed_range("1000:1004") == (1000, 1001, 1002, 1003, 1004)


def test_parse_seed_range_rejects_end_before_start():
    with pytest.raises(EvaluationConfigurationError):
        parse_seed_range("10:5")


def test_parse_seed_range_rejects_malformed():
    with pytest.raises(EvaluationConfigurationError):
        parse_seed_range("not-a-range")


# --------------------------------------------------------------------------
# evaluation_id determinism (Sec 8/18)
# --------------------------------------------------------------------------


def test_evaluation_id_deterministic_for_identical_request(tmp_path):
    scaffold_create_agent("cand", data_root=tmp_path, resource_root=ROOT)
    scaffold_create_agent("opp", data_root=tmp_path, resource_root=ROOT)
    service = EvaluationService()
    _specs1, id1 = service.preflight(
        candidate_id="cand", opponent_ids=("opp",), seeds=(1, 2), data_root=tmp_path
    )
    _specs2, id2 = service.preflight(
        candidate_id="cand", opponent_ids=("opp",), seeds=(1, 2), data_root=tmp_path
    )
    assert id1 == id2


def test_evaluation_id_changes_with_opponent_order(tmp_path):
    scaffold_create_agent("cand", data_root=tmp_path, resource_root=ROOT)
    scaffold_create_agent("opp_a", data_root=tmp_path, resource_root=ROOT)
    scaffold_create_agent("opp_b", data_root=tmp_path, resource_root=ROOT)
    service = EvaluationService()
    _specs1, id1 = service.preflight(
        candidate_id="cand", opponent_ids=("opp_a", "opp_b"), seeds=(1,), data_root=tmp_path
    )
    _specs2, id2 = service.preflight(
        candidate_id="cand", opponent_ids=("opp_b", "opp_a"), seeds=(1,), data_root=tmp_path
    )
    assert id1 != id2


def test_evaluation_id_changes_with_seed_order(tmp_path):
    scaffold_create_agent("cand", data_root=tmp_path, resource_root=ROOT)
    scaffold_create_agent("opp", data_root=tmp_path, resource_root=ROOT)
    service = EvaluationService()
    _specs1, id1 = service.preflight(
        candidate_id="cand", opponent_ids=("opp",), seeds=(1, 2), data_root=tmp_path
    )
    _specs2, id2 = service.preflight(
        candidate_id="cand", opponent_ids=("opp",), seeds=(2, 1), data_root=tmp_path
    )
    assert id1 != id2


def test_evaluation_id_changes_with_source_content(tmp_path):
    _write_python_agent(tmp_path, "cand", NOP_ACTION)
    scaffold_create_agent("opp", data_root=tmp_path, resource_root=ROOT)
    service = EvaluationService()
    _specs1, id1 = service.preflight(
        candidate_id="cand", opponent_ids=("opp",), seeds=(1,), data_root=tmp_path
    )
    # Mutate the candidate's source -- identity must change.
    (tmp_path / "agents" / "cand" / "agent.py").write_text(
        "class Agent:\n    def reset(self, context): pass\n    def act(self, observation): return None\n"
        "def create_agent(): return Agent()\n",
        encoding="utf-8",
    )
    _specs2, id2 = service.preflight(
        candidate_id="cand", opponent_ids=("opp",), seeds=(1,), data_root=tmp_path
    )
    assert id1 != id2


def test_source_digest_none_for_missing_file(tmp_path):
    assert source_digest(None) is None
    assert source_digest(tmp_path / "does-not-exist.py") is None


def test_source_digest_hashes_real_file(tmp_path):
    path = tmp_path / "agent.py"
    path.write_text("x = 1\n", encoding="utf-8")
    digest = source_digest(path)
    assert digest is not None
    assert len(digest) == 64


# --------------------------------------------------------------------------
# Aggregation (Sec 11/18)
# --------------------------------------------------------------------------


def _cell(**overrides) -> EvaluationCell:
    defaults = {
        "schedule_id": "s",
        "subject_role": CANDIDATE,
        "subject_id": "cand",
        "opponent_id": "opp",
        "seed": 1,
        "artifact_dir": Path("."),
        "status": "completed",
        "outcome": "win",
        "score_subject": 10.0,
        "score_opponent": 5.0,
        "territory_subject": 60.0,
        "territory_opponent": 40.0,
        "ticks_run": 100,
    }
    defaults.update(overrides)
    return EvaluationCell(**defaults)


def test_aggregate_cells_win_rate_and_averages():
    cells = [
        _cell(seed=1, outcome="win", score_subject=10.0, score_opponent=4.0),
        _cell(seed=2, outcome="loss", score_subject=2.0, score_opponent=8.0),
        _cell(seed=3, outcome="tie", score_subject=5.0, score_opponent=5.0),
    ]
    aggregate = aggregate_cells(CANDIDATE, "cand", cells)
    assert aggregate.matches_played == 3
    assert aggregate.wins == 1
    assert aggregate.losses == 1
    assert aggregate.ties == 1
    assert aggregate.win_rate_display == "1/3 (33%)"
    assert aggregate.score_avg == pytest.approx((10 + 2 + 5) / 3)
    assert aggregate.score_differential_avg == pytest.approx(((10 - 4) + (2 - 8) + (5 - 5)) / 3)


def test_aggregate_cells_excludes_init_failures_and_failed_from_denominator():
    cells = [
        _cell(seed=1, outcome="win"),
        _cell(seed=2, status="completed", outcome="subject_init_failed", score_subject=None, score_opponent=None),
        _cell(seed=3, status="completed", outcome="opponent_init_failed", score_subject=None, score_opponent=None),
        _cell(seed=4, status="failed", outcome=None, score_subject=None, score_opponent=None),
    ]
    aggregate = aggregate_cells(CANDIDATE, "cand", cells)
    assert aggregate.matches_played == 1
    assert aggregate.subject_init_failures == 1
    assert aggregate.opponent_init_failures == 1
    assert aggregate.failed == 1


def test_aggregate_cells_win_rate_display_with_zero_played():
    aggregate = aggregate_cells(CANDIDATE, "cand", [])
    assert aggregate.win_rate_display == "0/0 (n/a)"


def test_aggregate_cells_filters_by_subject():
    cells = [
        _cell(subject_role=CANDIDATE, subject_id="cand", outcome="win"),
        _cell(subject_role=BASELINE, subject_id="base", outcome="loss"),
    ]
    candidate_agg = aggregate_cells(CANDIDATE, "cand", cells)
    baseline_agg = aggregate_cells(BASELINE, "base", cells)
    assert candidate_agg.wins == 1
    assert baseline_agg.losses == 1


# --------------------------------------------------------------------------
# Comparison / classify (Sec 11/18)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "candidate_outcome,baseline_outcome,expected",
    [
        ("win", "win", "unchanged"),
        ("win", "tie", "improved"),
        ("win", "loss", "improved"),
        ("tie", "win", "regressed"),
        ("tie", "tie", "unchanged"),
        ("tie", "loss", "improved"),
        ("loss", "win", "regressed"),
        ("loss", "tie", "regressed"),
        ("loss", "loss", "unchanged"),
    ],
)
def test_classify_outcome_rank_truth_table(candidate_outcome, baseline_outcome, expected):
    assert classify(candidate_outcome, baseline_outcome) == expected


def test_compare_candidate_baseline_classifies_matched_cells():
    cells = [
        _cell(subject_role=CANDIDATE, subject_id="cand", opponent_id="opp", seed=1, outcome="win"),
        _cell(subject_role=BASELINE, subject_id="base", opponent_id="opp", seed=1, outcome="loss"),
    ]
    entries = compare_candidate_baseline(cells)
    assert len(entries) == 1
    assert entries[0].classification == "improved"
    assert entries[0].candidate_outcome == "win"
    assert entries[0].baseline_outcome == "loss"


def test_compare_candidate_baseline_marks_init_failure_as_inconclusive():
    cells = [
        _cell(subject_role=CANDIDATE, subject_id="cand", opponent_id="opp", seed=1, outcome="subject_init_failed"),
        _cell(subject_role=BASELINE, subject_id="base", opponent_id="opp", seed=1, outcome="win"),
    ]
    entries = compare_candidate_baseline(cells)
    assert len(entries) == 1
    assert entries[0].classification == "inconclusive"
    assert entries[0].reason is not None


def test_compare_candidate_baseline_marks_missing_cell_as_inconclusive():
    cells = [
        _cell(subject_role=CANDIDATE, subject_id="cand", opponent_id="opp", seed=1, outcome="win"),
    ]
    entries = compare_candidate_baseline(cells)
    assert len(entries) == 1
    assert entries[0].classification == "inconclusive"
    assert entries[0].baseline_outcome is None


def test_rerun_command_shape():
    command = rerun_command("cand", "opp", 42, 200)
    assert command == "bytefray agents test cand --opponent opp --seed 42 --ticks 200"


# --------------------------------------------------------------------------
# End-to-end single-candidate and paired evaluations
# --------------------------------------------------------------------------


def test_single_candidate_evaluation_end_to_end(tmp_path):
    scaffold_create_agent("cand", data_root=tmp_path, resource_root=ROOT)
    _write_python_agent(tmp_path, "opp", NOP_ACTION)
    service = EvaluationService()
    request = _request(tmp_path, candidate_id="cand", opponent_ids=("opp",), seeds=(1, 2))
    result = service.run(request)

    assert len(result.cells) == 2
    assert all(cell.status == "completed" for cell in result.cells)
    assert len(result.aggregates) == 1
    assert result.aggregates[0].matches_played == 2
    assert result.comparison == ()
    assert result.state_path.is_file()

    data = read_evaluation(result.state_path)
    assert data["schema"] == SCHEMA_NAME
    assert data["schema_version"] == SCHEMA_VERSION
    assert len(data["cells"]) == 2
    assert data["complete"] is True


def test_paired_candidate_baseline_evaluation_end_to_end(tmp_path):
    scaffold_create_agent("cand", data_root=tmp_path, resource_root=ROOT)
    scaffold_create_agent("base", data_root=tmp_path, resource_root=ROOT)
    _write_python_agent(tmp_path, "opp", NOP_ACTION)
    service = EvaluationService()
    request = _request(
        tmp_path,
        candidate_id="cand",
        baseline_id="base",
        opponent_ids=("opp",),
        seeds=(1, 2),
    )
    result = service.run(request)

    assert len(result.cells) == 4
    assert len(result.aggregates) == 2
    assert len(result.comparison) == 2


def test_paired_evaluation_with_duplicate_seed_produces_one_comparison_entry_per_duplicate(
    tmp_path,
):
    """Regression: a repeated (opponent, seed) pair must not collapse in
    compare_candidate_baseline's grouping -- each duplicate candidate cell
    needs its own paired baseline cell and its own ComparisonEntry, not just
    the last-seen duplicate on each side (which previously undercounted
    "of {total} matched cells" and silently dropped some duplicates)."""

    scaffold_create_agent("cand", data_root=tmp_path, resource_root=ROOT)
    scaffold_create_agent("base", data_root=tmp_path, resource_root=ROOT)
    _write_python_agent(tmp_path, "opp", NOP_ACTION)
    service = EvaluationService()
    request = _request(
        tmp_path,
        candidate_id="cand",
        baseline_id="base",
        opponent_ids=("opp",),
        seeds=(1, 1, 2),
    )
    result = service.run(request)

    assert len(result.cells) == 6  # 2 subjects x 1 opponent x 3 seeds (incl. duplicate)
    assert len(result.comparison) == 3  # one entry per (opp, seed) occurrence, not 2


def test_reproduction_command_matches_a_standalone_agents_test_rerun(tmp_path):
    """Proves Sec 8's reproducibility claim is true, not just documented."""

    scaffold_create_agent("cand", data_root=tmp_path, resource_root=ROOT)
    _write_python_agent(tmp_path, "opp", NOP_ACTION)
    service = EvaluationService()
    request = _request(tmp_path, candidate_id="cand", opponent_ids=("opp",), seeds=(7,), ticks=30)
    result = service.run(request)
    cell = result.cells[0]
    assert cell.match_id is not None

    standalone = run_development_test(
        "cand", opponent="opp", seed=7, ticks=30, data_root=tmp_path, resource_root=ROOT, trace=False
    )
    assert standalone.match_result.match_id == cell.match_id
    assert standalone.match_result.result_id == cell.result_id


# --------------------------------------------------------------------------
# Failure aggregation (Sec 9/18)
# --------------------------------------------------------------------------


def test_unknown_opponent_fails_preflight_before_any_cell_runs(tmp_path):
    scaffold_create_agent("cand", data_root=tmp_path, resource_root=ROOT)
    service = EvaluationService()
    request = _request(tmp_path, candidate_id="cand", opponent_ids=("does-not-exist",))
    with pytest.raises(EvaluationConfigurationError):
        service.run(request)
    # No matches/ directory should have been created -- preflight failed first.
    assert not (request.output_dir / "matches").exists()


def test_non_python_opponent_rejected(tmp_path):
    scaffold_create_agent("cand", data_root=tmp_path, resource_root=ROOT)
    _write_builtin_agent(tmp_path, "vm_opp")
    service = EvaluationService()
    request = _request(tmp_path, candidate_id="cand", opponent_ids=("vm_opp",))
    with pytest.raises(EvaluationConfigurationError):
        service.run(request)


def test_subject_init_failure_recorded_as_completed_not_failed(tmp_path):
    _write_reset_failing_agent(tmp_path, "broken")
    _write_python_agent(tmp_path, "opp", NOP_ACTION)
    service = EvaluationService()
    request = _request(tmp_path, candidate_id="broken", opponent_ids=("opp",))
    result = service.run(request)
    cell = result.cells[0]
    assert cell.status == "completed"
    assert cell.outcome == "subject_init_failed"
    assert cell.error_code is not None


def test_opponent_init_failure_recorded_distinctly(tmp_path):
    scaffold_create_agent("cand", data_root=tmp_path, resource_root=ROOT)
    _write_reset_failing_agent(tmp_path, "broken_opp")
    service = EvaluationService()
    request = _request(tmp_path, candidate_id="cand", opponent_ids=("broken_opp",))
    result = service.run(request)
    cell = result.cells[0]
    assert cell.status == "completed"
    assert cell.outcome == "opponent_init_failed"


def test_init_failures_excluded_from_win_rate_but_visible_in_aggregate(tmp_path):
    scaffold_create_agent("cand", data_root=tmp_path, resource_root=ROOT)
    _write_python_agent(tmp_path, "opp_ok", NOP_ACTION)
    _write_reset_failing_agent(tmp_path, "opp_broken")
    service = EvaluationService()
    request = _request(
        tmp_path, candidate_id="cand", opponent_ids=("opp_ok", "opp_broken"), seeds=(1,)
    )
    result = service.run(request)
    aggregate = result.aggregates[0]
    assert aggregate.matches_played == 1
    assert aggregate.opponent_init_failures == 1


# --------------------------------------------------------------------------
# Resume / retry (Sec 14/18)
# --------------------------------------------------------------------------


def test_resume_reexecutes_never_run_duplicate_cell_instead_of_corrupting_it(tmp_path):
    """Regression: a repeated (opponent, seed) pair used to collide in the
    resume-state lookup dict (both cells shared one schedule_id), so if only
    one duplicate had actually completed when an evaluation was interrupted,
    the still-pending duplicate was misclassified "corrupted" on resume
    (its own artifact_dir legitimately has no result.json yet -- that's not
    corruption, it just never ran) instead of simply being re-executed."""

    scaffold_create_agent("cand", data_root=tmp_path, resource_root=ROOT)
    _write_python_agent(tmp_path, "opp", NOP_ACTION)
    service = EvaluationService()
    request = _request(tmp_path, candidate_id="cand", opponent_ids=("opp",), seeds=(1, 1, 2))
    first = service.run(request)
    assert all(cell.status == "completed" for cell in first.cells)

    # Simulate an interruption: drop the second seed=1 duplicate's cell
    # record and delete its artifact directory, as if it never ran.
    duplicates = [cell for cell in first.cells if cell.seed == 1]
    assert len(duplicates) == 2
    never_ran = duplicates[1]
    state_path = first.state_path
    data = json.loads(state_path.read_text(encoding="utf-8"))
    data["cells"] = [
        entry
        for entry in data["cells"]
        if Path(entry["artifact_dir"]).name != never_ran.artifact_dir.name
    ]
    data["complete"] = False
    state_path.write_text(json.dumps(data), encoding="utf-8")
    shutil.rmtree(never_ran.artifact_dir, ignore_errors=True)

    second = service.run(request)
    by_dir = {cell.artifact_dir.name: cell for cell in second.cells}
    assert by_dir[never_ran.artifact_dir.name].status == "completed"
    assert by_dir[never_ran.artifact_dir.name].outcome in ("win", "loss", "tie")


def test_resume_trusts_completed_cell_without_rerunning(tmp_path):
    scaffold_create_agent("cand", data_root=tmp_path, resource_root=ROOT)
    _write_python_agent(tmp_path, "opp", NOP_ACTION)
    service = EvaluationService()
    request = _request(tmp_path, candidate_id="cand", opponent_ids=("opp",), seeds=(1, 2))
    first = service.run(request)
    first_match_ids = [cell.match_id for cell in first.cells]

    second = service.run(request)
    second_match_ids = [cell.match_id for cell in second.cells]
    assert first.evaluation_id == second.evaluation_id
    assert first_match_ids == second_match_ids


def test_resume_demotes_tampered_result_to_corrupted(tmp_path):
    scaffold_create_agent("cand", data_root=tmp_path, resource_root=ROOT)
    _write_python_agent(tmp_path, "opp", NOP_ACTION)
    service = EvaluationService()
    request = _request(tmp_path, candidate_id="cand", opponent_ids=("opp",), seeds=(1,))
    first = service.run(request)
    cell = first.cells[0]
    result_path = cell.artifact_dir / "result.json"
    data = json.loads(result_path.read_text(encoding="utf-8"))
    data["reproducibility"]["seed"] = 999999
    result_path.write_text(json.dumps(data), encoding="utf-8")

    second = service.run(request)
    assert second.cells[0].status == "corrupted"
    assert second.cells[0].error_code == "resumed_result_mismatch"


def test_resume_rejects_replay_filename_escaping_the_cell_directory(tmp_path):
    """H5: a tampered result.json whose replay filename tries to escape the
    cell's own artifact directory (via `../`) must be refused during resume
    verification, never followed outside the evaluation tree."""

    scaffold_create_agent("cand", data_root=tmp_path, resource_root=ROOT)
    _write_python_agent(tmp_path, "opp", NOP_ACTION)
    service = EvaluationService()
    request = _request(tmp_path, candidate_id="cand", opponent_ids=("opp",), seeds=(1,))
    first = service.run(request)
    cell = first.cells[0]
    result_path = cell.artifact_dir / "result.json"
    data = json.loads(result_path.read_text(encoding="utf-8"))
    data["replay"]["filename"] = "../../../outside.jsonl"
    result_path.write_text(json.dumps(data), encoding="utf-8")

    second = service.run(request)
    assert second.cells[0].status == "corrupted"
    assert second.cells[0].error_code == "resumed_result_mismatch"
    assert "escapes" in second.cells[0].error_message


def test_retry_failed_reexecutes_only_failed_cells(tmp_path):
    scaffold_create_agent("cand", data_root=tmp_path, resource_root=ROOT)
    _write_python_agent(tmp_path, "opp", NOP_ACTION)
    # Preflight rejects an unknown opponent up front (tested separately), so a
    # genuine mid-run tool failure is simulated here via a directly-tampered
    # "failed" cell in prior state -- the realistic shape an infra failure
    # would leave behind for --retry-failed to pick up.
    service2 = EvaluationService()
    ok_request = _request(tmp_path, candidate_id="cand", opponent_ids=("opp",), seeds=(1,))
    first = service2.run(ok_request)
    state_path = first.state_path
    data = json.loads(state_path.read_text(encoding="utf-8"))
    data["cells"][0]["status"] = "failed"
    data["cells"][0]["outcome"] = None
    data["cells"][0]["error_code"] = "engine_failed"
    state_path.write_text(json.dumps(data), encoding="utf-8")

    retried = service2.run(replace_request(ok_request, retry_failures=True))
    assert retried.cells[0].status == "completed"


def replace_request(request: EvaluationRequest, **overrides) -> EvaluationRequest:
    from dataclasses import replace as _replace

    return _replace(request, **overrides)


def test_incompatible_existing_output_rejected(tmp_path):
    scaffold_create_agent("cand", data_root=tmp_path, resource_root=ROOT)
    scaffold_create_agent("other", data_root=tmp_path, resource_root=ROOT)
    _write_python_agent(tmp_path, "opp", NOP_ACTION)
    service = EvaluationService()
    request = _request(tmp_path, candidate_id="cand", opponent_ids=("opp",), seeds=(1,))
    service.run(request)

    conflicting = _request(tmp_path, candidate_id="other", opponent_ids=("opp",), seeds=(1,))
    conflicting = replace_request(conflicting, output_dir=request.output_dir)
    with pytest.raises(EvaluationConfigurationError):
        service.run(conflicting)


# --------------------------------------------------------------------------
# Artifact schema (Sec 18)
# --------------------------------------------------------------------------


def test_read_evaluation_rejects_wrong_schema(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"schema": "not.evaluation", "schema_version": 1}), encoding="utf-8")
    with pytest.raises(EvaluationConfigurationError):
        read_evaluation(path)


def test_read_evaluation_rejects_unsupported_version(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"schema": SCHEMA_NAME, "schema_version": 999}), encoding="utf-8")
    with pytest.raises(EvaluationConfigurationError):
        read_evaluation(path)


def test_artifact_round_trip(tmp_path):
    scaffold_create_agent("cand", data_root=tmp_path, resource_root=ROOT)
    _write_python_agent(tmp_path, "opp", NOP_ACTION)
    service = EvaluationService()
    request = _request(tmp_path, candidate_id="cand", opponent_ids=("opp",), seeds=(1,))
    result = service.run(request)
    data = read_evaluation(result.state_path)
    assert data["evaluation_id"] == result.evaluation_id
    assert data["candidate_id"] == "cand"


def test_artifact_paths_are_relative_to_evaluation_directory(tmp_path):
    scaffold_create_agent("cand", data_root=tmp_path, resource_root=ROOT)
    _write_python_agent(tmp_path, "opp", NOP_ACTION)
    service = EvaluationService()
    request = _request(tmp_path, candidate_id="cand", opponent_ids=("opp",), seeds=(1,))
    result = service.run(request)
    data = read_evaluation(result.state_path)
    for cell in data["cells"]:
        assert not Path(cell["artifact_dir"]).is_absolute()


# --------------------------------------------------------------------------
# CLI (Sec 12/18)
# --------------------------------------------------------------------------


def test_cli_dry_run_prints_matrix_and_runs_nothing(tmp_path, monkeypatch, capsys):
    scaffold_create_agent("cand", data_root=tmp_path, resource_root=ROOT)
    _write_python_agent(tmp_path, "opp", NOP_ACTION)
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    exit_code = main(["cand", "--opponents", "opp", "--seeds", "1,2", "--dry-run"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "matches: 2" in captured.out
    assert not (tmp_path / "runs" / "evaluations").exists()


def test_cli_exit_code_2_for_unknown_agent(tmp_path, monkeypatch, capsys):
    scaffold_create_agent("cand", data_root=tmp_path, resource_root=ROOT)
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    exit_code = main(["cand", "--opponents", "nope", "--seeds", "1", "--dry-run"])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "ERROR" in captured.err


def test_cli_exit_code_0_for_full_run(tmp_path, monkeypatch, capsys):
    scaffold_create_agent("cand", data_root=tmp_path, resource_root=ROOT)
    _write_python_agent(tmp_path, "opp", NOP_ACTION)
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    exit_code = main(
        ["cand", "--opponents", "opp", "--seeds", "1", "--ticks", "10", "--quiet"]
    )
    assert exit_code == 0


def test_cli_seeds_and_seed_range_are_mutually_exclusive(tmp_path, monkeypatch):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    with pytest.raises(SystemExit):
        main(["cand", "--opponents", "opp", "--seeds", "1", "--seed-range", "1:2"])


def test_cli_default_seed_is_config_default(tmp_path, monkeypatch, capsys):
    from battle_engine.config import Config

    scaffold_create_agent("cand", data_root=tmp_path, resource_root=ROOT)
    _write_python_agent(tmp_path, "opp", NOP_ACTION)
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    exit_code = main(["cand", "--opponents", "opp", "--dry-run"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert f"seeds: {Config().seed}" in captured.out


def test_run_dir_extension_places_artifacts_at_given_path(tmp_path):
    scaffold_create_agent("cand", data_root=tmp_path, resource_root=ROOT)
    _write_python_agent(tmp_path, "opp", NOP_ACTION)
    custom_dir = tmp_path / "custom-run-dir"
    outcome = run_development_test(
        "cand", opponent="opp", data_root=tmp_path, resource_root=ROOT, run_dir=custom_dir, trace=False
    )
    assert outcome.match_result.replay_path.parent == custom_dir
    assert (custom_dir / "result.json").is_file()

    # Calling again with the same run_dir must not fail (exist_ok=True for
    # caller-provided directories, unlike the default agent_id/run_label path).
    outcome2 = run_development_test(
        "cand", opponent="opp", data_root=tmp_path, resource_root=ROOT, run_dir=custom_dir, trace=False
    )
    assert outcome2.match_result.replay_path.parent == custom_dir
