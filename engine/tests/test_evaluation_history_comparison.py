"""battle_engine.evaluation_history.comparison: alignment, verdicts, denominators."""

from __future__ import annotations

from pathlib import Path

from battle_engine.evaluation_history.comparison import align
from battle_engine.evaluation_history.models import (
    AdaptedCell,
    ArtifactLocation,
    ConfidenceValue,
    EvaluationSummary,
    HealthReport,
    SchemaSupport,
)

CONDITIONS = {"tick_limit": 10, "arena_size": 4096, "win_mode": "score_fallback"}
RULES_ID = "evaluation-rules-1"


def _identity(agent_id: str, sha: str = "abc123", entry_point: str = "agent.py:create_agent") -> dict:
    return {
        "agent_id": agent_id,
        "kind": "python",
        "api_version": 1,
        "agent_version": "1.0",
        "entry_point": entry_point,
        "source_sha256": sha,
    }


def _cell(
    *,
    opponent_id: str = "opponent",
    seed: int = 1,
    outcome: str | None = "win",
    status: str = "completed",
    occurrence: int = 0,
    opponent_sha: str = "opp-sha",
    unknown_occurrence: bool = False,
    unknown_opponent_identity: bool = False,
    verified: bool | None = None,
) -> AdaptedCell:
    return AdaptedCell(
        schedule_id=f"sched-{opponent_id}-{seed}-{occurrence}",
        subject_role="candidate",
        subject_id="candidate",
        opponent_id=opponent_id,
        seed=seed,
        status=status,
        outcome=outcome,
        match_id=f"match-{opponent_id}-{seed}-{occurrence}",
        artifact_dir=f"matches/{opponent_id}-{seed}-{occurrence}",
        score_subject=5.0,
        score_opponent=1.0,
        territory_subject=None,
        territory_opponent=None,
        opponent_index=ConfidenceValue.recorded(0),
        seed_index=ConfidenceValue.recorded(0),
        condition_occurrence_index=(
            ConfidenceValue.unknown() if unknown_occurrence else ConfidenceValue.recorded(occurrence)
        ),
        condition_fingerprint=ConfidenceValue.recorded("fp"),
        opponent_identity=(
            ConfidenceValue.unknown()
            if unknown_opponent_identity
            else ConfidenceValue.recorded(_identity(opponent_id, sha=opponent_sha))
        ),
        verified=verified,
    )


def _summary(
    *,
    candidate_id: str = "candidate",
    candidate_sha: str = "cand-sha",
    candidate_identity_known: bool = True,
    baseline_id: str | None = None,
    baseline_identity_known: bool = True,
    baseline_sha: str = "base-sha",
    cells: tuple[AdaptedCell, ...] = (),
    conditions_known: bool = True,
    rules_id: str | None = RULES_ID,
) -> EvaluationSummary:
    location = ArtifactLocation(
        evaluation_json_path=Path("evaluation.json"), directory=Path("."), file_modified_at="x"
    )
    return EvaluationSummary(
        location=location,
        schema=SchemaSupport(schema="bytefray.evaluation", schema_version=2, supported=True),
        evaluation_id="evaluation-v2_x",
        candidate_id=candidate_id,
        baseline_id=baseline_id,
        opponent_ids=(),
        seeds=(),
        ticks=10,
        matrix_size=len(cells),
        lifecycle_state=ConfidenceValue.recorded("finished"),
        created_at=ConfidenceValue.recorded("2026-01-01T00:00:00Z"),
        finished_at=ConfidenceValue.recorded("2026-01-01T00:00:01Z"),
        rules_compatibility_id=(
            ConfidenceValue.recorded(rules_id) if rules_id else ConfidenceValue.unknown()
        ),
        candidate_identity=(
            ConfidenceValue.recorded(_identity(candidate_id, sha=candidate_sha))
            if candidate_identity_known
            else ConfidenceValue.unknown()
        ),
        baseline_identity=(
            ConfidenceValue.unknown()
            if baseline_id is None
            else (
                ConfidenceValue.recorded(_identity(baseline_id, sha=baseline_sha))
                if baseline_identity_known
                else ConfidenceValue.unknown()
            )
        ),
        effective_conditions=(
            ConfidenceValue.recorded(CONDITIONS) if conditions_known else ConfidenceValue.unknown()
        ),
        cells=cells,
        health=HealthReport(),
        aggregates_recomputed=(),
        comparison_recomputed=(),
    )


def test_identical_conditions_identical_outcomes_are_unchanged():
    left = _summary(cells=(_cell(outcome="win"),))
    right = _summary(cells=(_cell(outcome="win"),))
    result = align(left, right)
    assert result.denominators.directly_comparable == 1
    assert result.denominators.unchanged == 1
    assert result.orientation == "right_relative_to_left"


def test_right_win_over_left_tie_is_improved():
    left = _summary(cells=(_cell(outcome="tie"),))
    right = _summary(cells=(_cell(outcome="win"),))
    result = align(left, right)
    assert result.rows[0].verdict == "improved"


def test_right_loss_over_left_win_is_regressed():
    left = _summary(cells=(_cell(outcome="win"),))
    right = _summary(cells=(_cell(outcome="loss"),))
    result = align(left, right)
    assert result.rows[0].verdict == "regressed"


def test_candidate_logical_id_change_is_reported_as_different_candidates():
    left = _summary(candidate_id="candidate_a", cells=(_cell(outcome="win"),))
    right = _summary(candidate_id="candidate_b", cells=(_cell(outcome="win"),))
    result = align(left, right)
    assert result.candidate_changed is True
    # Cells still align on shared opponent condition even though the
    # logical candidate changed -- candidate identity is excluded from the
    # shared-condition fingerprint by construction.
    assert result.denominators.directly_comparable == 1


def test_identical_candidate_fingerprint_with_differing_outcome_is_not_anomaly_without_verification():
    """B3: a reproducibility anomaly must never be claimed from evidence that
    was only read and recomputed from each artifact's own recorded fields --
    only a genuinely deep-verified (``--verify``) comparison may claim one,
    even when the candidate identity fingerprint alone already matches."""

    left = _summary(candidate_sha="same-sha", cells=(_cell(outcome="win"),))
    right = _summary(candidate_sha="same-sha", cells=(_cell(outcome="loss"),))
    result = align(left, right)
    assert result.deep_verified is False
    assert result.reproducibility_anomalies == ()
    assert result.rows[0].verdict == "regressed"
    assert result.rows[0].reproducibility_anomaly is False


def test_identical_candidate_fingerprint_with_differing_outcome_is_anomaly_when_deep_verified():
    left = _summary(candidate_sha="same-sha", cells=(_cell(outcome="win", verified=True),))
    right = _summary(candidate_sha="same-sha", cells=(_cell(outcome="loss", verified=True),))
    result = align(left, right, deep_verified=True)
    assert result.reproducibility_anomalies
    assert result.reproducibility_anomalies[0].verdict == "regressed"


def test_identical_candidate_fingerprint_deep_verified_but_one_cell_unverified_is_not_anomaly():
    """Passing ``--verify`` alone is not enough -- the specific cells being
    compared must themselves have actually verified."""

    left = _summary(candidate_sha="same-sha", cells=(_cell(outcome="win", verified=True),))
    right = _summary(candidate_sha="same-sha", cells=(_cell(outcome="loss", verified=False),))
    result = align(left, right, deep_verified=True)
    assert result.reproducibility_anomalies == ()


def test_opponent_source_change_prevents_direct_comparison():
    left = _summary(cells=(_cell(outcome="win", opponent_sha="sha-1"),))
    right = _summary(cells=(_cell(outcome="win", opponent_sha="sha-2"),))
    result = align(left, right)
    assert result.denominators.directly_comparable == 0
    assert result.denominators.unmatched_left == 1
    assert result.denominators.unmatched_right == 1


def test_rules_compatibility_mismatch_prevents_direct_comparison():
    left = _summary(cells=(_cell(outcome="win"),), rules_id="evaluation-rules-1")
    right = _summary(cells=(_cell(outcome="win"),), rules_id="evaluation-rules-2")
    result = align(left, right)
    assert result.denominators.directly_comparable == 0


def test_v1_unknown_rules_id_never_compares_equal_even_to_another_unknown():
    left = _summary(cells=(_cell(outcome="win"),), rules_id=None)
    right = _summary(cells=(_cell(outcome="win"),), rules_id=None)
    result = align(left, right)
    assert result.denominators.directly_comparable == 0


def test_unknown_condition_occurrence_index_never_aligns():
    left = _summary(cells=(_cell(outcome="win", unknown_occurrence=True),))
    right = _summary(cells=(_cell(outcome="win"),))
    result = align(left, right)
    assert result.denominators.directly_comparable == 0


def test_duplicate_occurrence_alignment_preserves_multiplicity():
    left = _summary(
        cells=(_cell(outcome="win", occurrence=0), _cell(outcome="loss", occurrence=1))
    )
    right = _summary(
        cells=(_cell(outcome="win", occurrence=0), _cell(outcome="win", occurrence=1))
    )
    result = align(left, right)
    assert result.denominators.directly_comparable == 2
    verdicts = sorted(row.verdict for row in result.rows)
    assert verdicts == ["improved", "unchanged"]


def test_asymmetric_multiplicity_leaves_extra_occurrence_unmatched():
    left = _summary(cells=(_cell(outcome="win", occurrence=0),))
    right = _summary(
        cells=(_cell(outcome="win", occurrence=0), _cell(outcome="win", occurrence=1))
    )
    result = align(left, right)
    assert result.denominators.directly_comparable == 1
    assert result.denominators.unmatched_right == 1
    assert len(result.unmatched_right) == 1


def test_init_failure_cell_is_inconclusive_not_a_loss():
    left = _summary(cells=(_cell(outcome="win"),))
    right = _summary(cells=(_cell(outcome="subject_init_failed", status="completed"),))
    result = align(left, right)
    assert result.rows[0].verdict == "inconclusive"
    assert result.denominators.improved == 0
    assert result.denominators.regressed == 0


def test_failed_cell_never_treated_as_loss():
    left = _summary(cells=(_cell(outcome="win"),))
    right = _summary(cells=(_cell(outcome=None, status="failed"),))
    result = align(left, right)
    assert result.rows[0].verdict == "inconclusive"


def test_denominators_always_populated_even_when_zero():
    left = _summary(cells=())
    right = _summary(cells=())
    result = align(left, right)
    d = result.denominators
    assert d.improved == 0
    assert d.regressed == 0
    assert d.unchanged == 0
    assert d.inconclusive == 0
    assert d.directly_comparable == 0


def test_baseline_absent_on_both_sides():
    left = _summary(cells=())
    right = _summary(cells=())
    result = align(left, right)
    assert result.baseline_context.identity_status == "absent_both"


def test_baseline_absent_on_one_side():
    left = _summary(baseline_id="baseline", cells=())
    right = _summary(baseline_id=None, cells=())
    result = align(left, right)
    assert result.baseline_context.identity_status == "absent_one"


def _baseline_cell(schedule_id: str, match_id: str, artifact_dir: str, outcome: str, score_subject: float, *, verified: bool | None = None) -> AdaptedCell:
    return AdaptedCell(
        schedule_id=schedule_id, subject_role="baseline", subject_id="baseline", opponent_id="opponent",
        seed=1, status="completed", outcome=outcome, match_id=match_id, artifact_dir=artifact_dir,
        score_subject=score_subject, score_opponent=1.0, territory_subject=None, territory_opponent=None,
        opponent_index=ConfidenceValue.recorded(0), seed_index=ConfidenceValue.recorded(0),
        condition_occurrence_index=ConfidenceValue.recorded(0),
        condition_fingerprint=ConfidenceValue.recorded("fp"),
        opponent_identity=ConfidenceValue.recorded(_identity("opponent")),
        verified=verified,
    )


def test_baseline_same_identity_used_as_control_but_not_anomaly_without_verification():
    left = _summary(
        baseline_id="baseline", cells=(_baseline_cell("b-left", "m1", "d1", "tie", 1.0),)
    )
    right = _summary(
        baseline_id="baseline", cells=(_baseline_cell("b-right", "m2", "d2", "win", 5.0),)
    )
    result = align(left, right)
    assert result.baseline_context.identity_status == "same"
    # B3: a control-anomaly claim ("the same baseline diverged under
    # identical conditions") requires deep-verified evidence, same as the
    # main reproducibility-anomaly claim -- never from recomputed-only data.
    assert result.baseline_context.control_anomaly is False


def test_baseline_same_identity_control_anomaly_when_deep_verified():
    left = _summary(
        baseline_id="baseline",
        cells=(_baseline_cell("b-left", "m1", "d1", "tie", 1.0, verified=True),),
    )
    right = _summary(
        baseline_id="baseline",
        cells=(_baseline_cell("b-right", "m2", "d2", "win", 5.0, verified=True),),
    )
    result = align(left, right, deep_verified=True)
    assert result.baseline_context.identity_status == "same"
    assert result.baseline_context.control_anomaly is True  # tie -> win under identical conditions


def test_baseline_changed_identity_reported():
    left = _summary(baseline_id="baseline", baseline_sha="sha-1", cells=())
    right = _summary(baseline_id="baseline", baseline_sha="sha-2", cells=())
    result = align(left, right)
    assert result.baseline_context.identity_status == "changed"


def test_unknown_legacy_baseline_identity():
    left = _summary(baseline_id="baseline", baseline_identity_known=False, cells=())
    right = _summary(baseline_id="baseline", cells=())
    result = align(left, right)
    assert result.baseline_context.identity_status == "unknown_legacy"


def test_comparison_row_ordering_is_deterministic():
    left = _summary(
        cells=(
            _cell(opponent_id="b", seed=2, outcome="win"),
            _cell(opponent_id="a", seed=1, outcome="win"),
        )
    )
    right = _summary(
        cells=(
            _cell(opponent_id="b", seed=2, outcome="win"),
            _cell(opponent_id="a", seed=1, outcome="win"),
        )
    )
    result_a = align(left, right)
    result_b = align(left, right)
    assert [row.to_json() for row in result_a.rows] == [row.to_json() for row in result_b.rows]
