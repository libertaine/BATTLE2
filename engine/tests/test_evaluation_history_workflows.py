"""``app.services.evaluation_history_workflows`` (v1.1 "Evaluation Insight" slice).

Qt-free -- lives under ``engine/tests`` rather than the root ``tests/`` GUI
suite by the same convention ``test_designer_workflows.py``/
``test_agent_workflows.py`` already use for other ``app.services`` modules:
this module imports no Qt, so its tests belong in the default headless run.

Covers: discovery over an empty/malformed data root, loading a fresh
(current-schema) and a legacy v1 evaluation summary (with and without deep
verification, with an explicit ``data_root``), comparing two evaluations
that are identical versus two that ran under materially different
conditions, agent-revision provenance loading including live current-source
drift detection, and the plain-text formatters' behavior on both shapes.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from battle_engine.agent_evaluation import EvaluationRequest, EvaluationService
from battle_engine.evaluation_history import ComparisonRow, FieldConfidence, HealthCode

from app.services.designer_workflows import DesignerValidationError
from app.services.evaluation_history_workflows import (
    compare_evaluations,
    discover_evaluation_listing,
    distinct_opponent_ids,
    find_candidate_cell,
    format_agent_revision_text,
    format_comparison_gaps_text,
    format_comparison_text,
    format_evaluation_summary_text,
    load_agent_revision,
    load_evaluation_summary,
    sorted_listing_entries,
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


def _write_reset_failing_agent(root: Path, name: str, message: str = "boom") -> None:
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


def _run_evaluation(tmp_path: Path, output_name: str, **overrides) -> Path:
    defaults = {
        "candidate_id": "candidate",
        "baseline_id": None,
        "opponent_ids": ("opponent",),
        "seeds": (1,),
        "output_dir": tmp_path / "runs" / "evaluations" / output_name,
        "ticks": 10,
        "data_root": tmp_path,
        "both_orientations": False,
    }
    defaults.update(overrides)
    result = EvaluationService().run(EvaluationRequest(**defaults))
    return result.state_path


def _v1_fixture(tmp_path: Path) -> Path:
    """A hand-built v1-shaped evaluation.json -- no ``rules_compatibility_id``,
    no ``agent_revisions``, no execution contexts, exactly the shape a v1
    (pre-v0.7) artifact actually has (docs/specs/evaluation_history.md's v1
    adapter contract): this is the "historical records with missing optional
    data" case the task explicitly requires coverage for.
    """

    from battle_engine.agent_test import TESTED_AGENT_SLOT, test_agent
    from battle_engine.results import WINNER_TIE_SENTINEL

    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")

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
        "complete": True,
    }
    path = eval_dir / "evaluation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def test_discover_evaluation_listing_empty_history_never_raises(tmp_path: Path):
    listing = discover_evaluation_listing(roots=(tmp_path / "runs" / "evaluations",))
    assert listing.entries == ()
    assert listing.duplicate_identity_groups == ()


def test_discover_malformed_sibling_does_not_abort_listing(tmp_path: Path):
    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    roots = tmp_path / "runs" / "evaluations"
    good_path = _run_evaluation(tmp_path, "good-eval")

    bad_dir = roots / "bad-eval"
    bad_dir.mkdir(parents=True)
    (bad_dir / "evaluation.json").write_text("not json at all {{{", encoding="utf-8")

    listing = discover_evaluation_listing(roots=(roots,))
    assert len(listing.entries) == 2
    by_path = {entry.location.evaluation_json_path: entry for entry in listing.entries}
    good_entry = by_path[good_path.resolve()]
    bad_entry = by_path[(bad_dir / "evaluation.json").resolve()]
    assert good_entry.summary is not None
    assert bad_entry.summary is None
    assert bad_entry.health.codes  # some diagnostic code was recorded, not an exception


def test_sorted_listing_entries_orders_most_recently_modified_first(tmp_path: Path):
    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    roots = tmp_path / "runs" / "evaluations"
    older = _run_evaluation(tmp_path, "older-eval")
    # Ensure a real, observable mtime gap regardless of filesystem timestamp
    # resolution (some filesystems only resolve to whole seconds).
    os.utime(older, (time.time() - 3600, time.time() - 3600))
    newer = _run_evaluation(tmp_path, "newer-eval", opponent_ids=("opponent",), seeds=(2,))

    listing = discover_evaluation_listing(roots=(roots,))
    ordered = sorted_listing_entries(listing)
    assert [e.location.evaluation_json_path for e in ordered] == [
        newer.resolve(),
        older.resolve(),
    ]


# ---------------------------------------------------------------------------
# Loading one summary
# ---------------------------------------------------------------------------


def test_load_evaluation_summary_current_schema_without_verify(tmp_path: Path):
    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    path = _run_evaluation(tmp_path, "eval1")

    summary, verify_error = load_evaluation_summary(path, verify=False)
    assert verify_error is None
    assert summary.candidate_id == "candidate"
    assert summary.schema.schema_version >= 2
    text = format_evaluation_summary_text(summary, verified=None, verify_error=None)
    assert "candidate: candidate" in text
    assert "verified:" not in text  # never claims verification that was never requested


def test_load_evaluation_summary_verify_uses_explicit_data_root(tmp_path: Path):
    """Deep verification's agent-revision cross-check must be scoped to the
    caller's own ``data_root`` -- not whatever ``get_data_root()`` happens
    to resolve to in the current process -- or a Designer/test run against
    an isolated data root would silently report every revision as
    unavailable (the exact bug caught while building this module)."""

    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    path = _run_evaluation(tmp_path, "eval1")

    summary, verify_error = load_evaluation_summary(path, verify=True, data_root=tmp_path)
    assert verify_error is None
    assert summary.candidate_revision_verification.value == "verified"
    text = format_evaluation_summary_text(summary, verified=True, verify_error=None)
    assert "verified: True" in text
    assert "[verified]" in text


def test_load_evaluation_summary_v1_legacy_missing_optional_data(tmp_path: Path):
    """A pre-v0.7 v1 artifact never recorded ``rules_compatibility_id``,
    execution contexts, or agent-revision provenance -- those must read as
    explicitly unknown, never a guessed current-schema value, and the
    formatter must render that without raising."""

    path = _v1_fixture(tmp_path)
    summary, verify_error = load_evaluation_summary(path, verify=False)
    assert verify_error is None
    assert summary.rules_compatibility_id.confidence == FieldConfidence.UNKNOWN
    assert summary.candidate_agent_revision_id.confidence == FieldConfidence.UNKNOWN
    assert summary.execution_contexts == ()

    text = format_evaluation_summary_text(summary)
    assert "rules_compatibility_id: unknown (unknown)" in text
    assert "execution contexts: none recorded (legacy/v1 artifact)" in text
    assert "candidate: unknown" in text  # agent revisions block, candidate role


def test_load_evaluation_summary_reports_init_failures_and_health_not_a_crash(tmp_path: Path):
    """An evaluation with a real initialization-failure cell (Sec 5.1 of
    ``docs/specs/evaluation_history.md``: ``FINISHED_WITH_INIT_FAILURES``
    can coexist with ``lifecycle_state == 'finished'``) must still adapt
    and render cleanly -- a failed/omitted cell is a fact about the agent
    under test, not a Designer-side error."""

    _write_reset_failing_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    path = _run_evaluation(tmp_path, "eval-broken")

    summary, verify_error = load_evaluation_summary(path, verify=False)
    assert verify_error is None
    assert HealthCode.FINISHED_WITH_INIT_FAILURES in summary.health.codes
    assert any(cell.outcome == "subject_init_failed" for cell in summary.cells)

    # The health-code line is where this fact is actually surfaced (mirrors
    # ``evaluation_history.cli._print_show`` exactly, Sec 4's "design for
    # clarity" -- the per-cell status-counts line groups by ``status``
    # ("completed"), not ``outcome``, since the health line already
    # discloses the init-failure fact once at the evaluation level).
    text = format_evaluation_summary_text(summary)
    assert "finished_with_init_failures" in text


def test_load_evaluation_summary_unreadable_path_raises_designer_validation_error(tmp_path: Path):
    bad = tmp_path / "evaluation.json"
    bad.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(DesignerValidationError):
        load_evaluation_summary(bad)


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def test_compare_evaluations_identical_runs_are_directly_comparable_and_unchanged(tmp_path: Path):
    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    path = _run_evaluation(tmp_path, "eval1")

    result = compare_evaluations(path, path, verify=True, data_root=tmp_path)
    assert result.left_verify_error is None
    assert result.right_verify_error is None
    assert result.fully_verified is True
    assert result.comparison.candidate_changed is False
    assert result.comparison.candidate_diff is None
    assert result.comparison.denominators.directly_comparable > 0
    assert result.comparison.denominators.regressed == 0
    assert all(row.verdict == "unchanged" for row in result.comparison.rows)

    text = format_comparison_text(result)
    assert "evidence: deep-verified (Verify)" in text
    assert "candidate identity: unchanged" in text
    gaps_text = format_comparison_gaps_text(result.comparison)
    assert "No unmatched" in gaps_text


def test_compare_evaluations_incompatible_conditions_are_not_directly_comparable(tmp_path: Path):
    """Two evaluations of the same candidate/opponent/seed but different
    ``ticks`` ran under materially different effective conditions -- the
    task's own requirement that a comparison "must not confidently present
    a performance delta when the underlying experimental conditions
    differ." They must not silently align as though comparable."""

    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    left_path = _run_evaluation(tmp_path, "eval-short", ticks=10)
    right_path = _run_evaluation(tmp_path, "eval-long", ticks=25)

    result = compare_evaluations(left_path, right_path)
    assert result.comparison.denominators.directly_comparable == 0
    assert result.comparison.rows == ()
    # Same nominal (opponent, seed) slot on both sides, but the underlying
    # effective conditions (ticks) differ -- this is the "changed_condition"
    # bucket (Sec 14), not an ordinary unmatched cell: there *is* something
    # to relate them to, it just isn't a like-for-like comparison.
    assert len(result.comparison.changed_condition) == 1
    assert result.comparison.denominators.changed_condition == 1

    gaps_text = format_comparison_gaps_text(result.comparison)
    assert "changed condition" in gaps_text


def test_compare_evaluations_ambiguous_groups_are_disclosed_not_silently_zero(tmp_path: Path):
    """Found during interactive qualification (real Designer session,
    native Qt backend): comparing two both-orientation evaluations that
    differ only in ``ticks`` produces cells that fall entirely into the
    ``ambiguous_duplicate_groups`` bucket (two unmatched cells per
    (opponent, seed) -- one per orientation -- on each side), not
    ``changed_condition``. Before this fix, ``format_comparison_text``'s
    denominators line never mentioned that count at all, so the summary
    rendered as an uninformative wall of zeros with no visible signal that
    "Show ... Details" had anything to show."""

    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    left_path = _run_evaluation(tmp_path, "eval-short", ticks=10, both_orientations=True)
    right_path = _run_evaluation(tmp_path, "eval-long", ticks=25, both_orientations=True)

    result = compare_evaluations(left_path, right_path)
    assert result.comparison.denominators.directly_comparable == 0
    assert result.comparison.denominators.changed_condition == 0
    assert result.comparison.denominators.ambiguous_duplicate_groups > 0

    text = format_comparison_text(result)
    assert f"ambiguous_duplicate_groups={result.comparison.denominators.ambiguous_duplicate_groups}" in text

    gaps_text = format_comparison_gaps_text(result.comparison)
    assert "ambiguous duplicate groups" in gaps_text


def test_find_candidate_cell_returns_none_when_no_match(tmp_path: Path):
    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    path = _run_evaluation(tmp_path, "eval1")
    summary, _ = load_evaluation_summary(path)

    row = ComparisonRow(
        opponent_id="nonexistent-opponent",
        seed=999,
        condition_occurrence_index=0,
        left_outcome="win",
        right_outcome="win",
        verdict="unchanged",
    )
    assert find_candidate_cell(summary, row) is None

    real_row = ComparisonRow(
        opponent_id="opponent",
        seed=1,
        condition_occurrence_index=0,
        left_outcome="win",
        right_outcome="win",
        verdict="unchanged",
    )
    cell = find_candidate_cell(summary, real_row)
    assert cell is not None
    assert cell.opponent_id == "opponent" and cell.seed == 1


def test_distinct_opponent_ids_dedupes_preserving_first_occurrence_order(tmp_path: Path):
    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "alpha")
    _write_python_agent(tmp_path, "beta")
    path = _run_evaluation(
        tmp_path, "eval1", opponent_ids=("alpha", "beta", "alpha"), seeds=(1,)
    )
    summary, _ = load_evaluation_summary(path)
    assert distinct_opponent_ids(summary) == ("alpha", "beta")


# ---------------------------------------------------------------------------
# Agent revision provenance
# ---------------------------------------------------------------------------


def test_load_agent_revision_reports_current_source_status_transitions(tmp_path: Path):
    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    path = _run_evaluation(tmp_path, "eval1")
    summary, _ = load_evaluation_summary(path)
    revision_id = summary.candidate_agent_revision_id.value
    assert revision_id

    matching = load_agent_revision(revision_id, data_root=tmp_path, current_agent_id="candidate")
    assert matching.live_source_status == "matches_current_source"
    assert matching.verified is True
    text = format_agent_revision_text(matching)
    assert "MATCHES the agent's current on-disk source" in text

    (tmp_path / "agents" / "candidate" / "agent.py").write_text(
        "from battle_engine.agent_api import ActionKind, AgentAction\n"
        "class Agent:\n    def reset(self, context): pass\n"
        f"    def act(self, observation): return {NOP_ACTION}\n"
        "    # changed\n"
        "def create_agent(): return Agent()\n",
        encoding="utf-8",
    )
    changed = load_agent_revision(revision_id, data_root=tmp_path, current_agent_id="candidate")
    assert changed.live_source_status == "changed_since_evaluation"

    missing = load_agent_revision(revision_id, data_root=tmp_path, current_agent_id="never-existed")
    assert missing.live_source_status == "agent_missing"

    unchecked = load_agent_revision(revision_id, data_root=tmp_path)
    assert unchecked.live_source_status == "unknown"


def test_load_agent_revision_unknown_id_raises_designer_validation_error(tmp_path: Path):
    with pytest.raises(DesignerValidationError):
        load_agent_revision("agent-revision_" + "0" * 64, data_root=tmp_path)
