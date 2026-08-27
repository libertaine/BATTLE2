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
from dataclasses import replace
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
    assert (
        "effective conditions, rules, methodology, or opponent revision differ" in gaps_text
    )


def test_compare_evaluations_ambiguous_groups_are_disclosed_not_silently_zero(tmp_path: Path):
    """Found during interactive qualification (real Designer session,
    native Qt backend): comparing two both-orientation evaluations, each
    with a duplicated seed, under changed ticks produces cells that fall
    entirely into the ``ambiguous_duplicate_groups`` bucket (two unmatched
    cells per (opponent, seed, orientation) -- one per repeated seed
    occurrence -- on each side), not ``changed_condition``. Before this
    fix, ``format_comparison_text``'s denominators line never mentioned
    that count at all, so the summary rendered as an uninformative wall of
    zeros with no visible signal that "Show ... Details" had anything to
    show.

    v3.0 Phase 3 (docs/V3_PRODUCT_SCOPE.md, disclosed at v1.6 Phase 6 Sec
    22): a single duplicated seed, without a changed condition, used to be
    enough to reach this state, because the pre-fix fallback grouping key
    was (opponent_id, seed) only -- a candidate_first cell and an
    opponent_first cell for the same (opponent, seed) collided into one
    spurious 2-vs-2 group even under a single seed. With orientation now
    part of that key, a single duplicated seed under a changed condition
    resolves cleanly into two independent 1-vs-1 changed_condition pairs
    (one per orientation) instead -- so this test now duplicates the seed
    itself (two physical occurrences per orientation) to construct a
    genuine ambiguity the fix does not, and should not, resolve.
    """

    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    left_path = _run_evaluation(tmp_path, "eval-short", ticks=10, seeds=(1, 1), both_orientations=True)
    right_path = _run_evaluation(tmp_path, "eval-long", ticks=25, seeds=(1, 1), both_orientations=True)

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


def test_find_candidate_cell_uses_nonserialized_side_refs_for_both_orientations(
    tmp_path: Path,
):
    """A current evaluation has two legitimate cells sharing the legacy
    fallback coordinate; exact side schedule refs must distinguish them,
    while an unscoped/duplicate lookup fails closed."""

    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    left_path = _run_evaluation(tmp_path, "eval-left", both_orientations=True)
    right_path = _run_evaluation(tmp_path, "eval-right", both_orientations=True)

    result = compare_evaluations(left_path, right_path)
    assert len(result.comparison.rows) == 2
    assert result.left.location.directory != result.right.location.directory

    resolved: dict[str, tuple[str, str]] = {}
    for row in result.comparison.rows:
        # Without an explicit side, the old coordinate matches both
        # orientations and therefore must not return an arbitrary first cell.
        assert find_candidate_cell(result.left, row) is None

        left_cell = find_candidate_cell(result.left, row, side="left")
        right_cell = find_candidate_cell(result.right, row, side="right")
        assert left_cell is not None
        assert right_cell is not None
        assert left_cell.schedule_id == row.left_schedule_id
        assert right_cell.schedule_id == row.right_schedule_id
        assert left_cell.orientation.value == right_cell.orientation.value
        resolved[str(left_cell.orientation.value)] = (
            left_cell.schedule_id,
            right_cell.schedule_id,
        )

        # The internal drill-down refs are deliberately absent from the
        # established comparison/CLI JSON representation.
        assert set(row.to_json()) == {
            "opponent_id",
            "seed",
            "condition_occurrence_index",
            "left_outcome",
            "right_outcome",
            "verdict",
            "reason",
            "left_score",
            "right_score",
            "left_territory",
            "right_territory",
            "reproducibility_anomaly",
        }

    assert set(resolved) == {"candidate_first", "opponent_first"}

    first_row = result.comparison.rows[0]
    first_cell = find_candidate_cell(result.left, first_row, side="left")
    assert first_cell is not None
    duplicate_summary = replace(
        result.left,
        cells=result.left.cells + (replace(first_cell),),
    )
    assert find_candidate_cell(duplicate_summary, first_row, side="left") is None


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
# Effective-condition disclosure (v3.0 Phase 4 CLI/GUI parity)
# ---------------------------------------------------------------------------


def test_format_evaluation_summary_text_hides_default_conditions(tmp_path: Path):
    """At ordinary defaults, the Designer's history detail pane must render
    exactly as it did before Phase 4 -- no experimental-condition noise for
    the overwhelming majority of evaluations that never override them."""

    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    path = _run_evaluation(tmp_path, "eval-default")

    summary, verify_error = load_evaluation_summary(path, verify=False)
    assert verify_error is None
    text = format_evaluation_summary_text(summary)
    assert "arena size" not in text
    assert "action budget" not in text
    assert "kill weight" not in text
    assert "locality reach" not in text


def test_format_evaluation_summary_text_discloses_non_default_conditions(tmp_path: Path):
    """The exact CLI/GUI parity gap Phase 4 closes: a non-default artifact
    (larger arena, different action budget, different kill weight) must
    read as non-default in the Designer's history view, not just in
    ``bytefray agents evaluations show`` -- using the identical wording
    (Sec "Effective conditions"), via the one shared
    ``effective_condition_lines`` interpretation."""

    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    path = _run_evaluation(
        tmp_path, "eval-nondefault", arena_size=1024, instr_per_tick=4, kill_weight=9.0
    )

    summary, verify_error = load_evaluation_summary(path, verify=False)
    assert verify_error is None
    text = format_evaluation_summary_text(summary)
    assert "arena size: 1024 (non-default)" in text
    assert "action budget/tick: 4 (non-default)" in text
    assert "kill weight: 9" in text and "(non-default)" in text
    # Ordering parity with `evaluation_history.cli._print_show`: the
    # disclosure sits between the seeds/ticks line and lifecycle.
    assert text.index("ticks:") < text.index("arena size") < text.index("lifecycle:")


def test_effective_condition_lines_silent_for_recovered_v1_defaults(tmp_path: Path):
    """A v1 (pre-Phase-0) artifact never recorded ``effective_conditions``
    at all -- the v1 adapter recovers it as certain (arena size/action
    budget/kill weight were not yet configurable, so a v1 evaluation always
    ran at defaults), not unknown. Either way the disclosure must stay
    silent: an artifact that (as far as anyone can tell) ran at defaults
    must never be presented as if it were non-default."""

    from battle_engine.evaluation_history import effective_condition_lines

    path = _v1_fixture(tmp_path)
    summary, _ = load_evaluation_summary(path, verify=False)
    assert summary.effective_conditions.confidence in (
        FieldConfidence.RECOVERED,
        FieldConfidence.UNKNOWN,
    )
    assert effective_condition_lines(summary) == []


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
