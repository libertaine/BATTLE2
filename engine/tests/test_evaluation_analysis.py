"""Phase 4 statistical-analysis tests (docs/V1_6_PHASE4_EVALUATION_ANALYSIS.md).

Wilson-interval and exact-binomial test values are cross-checked against
independently derivable closed forms / published exact sign-test table
values, never solely against this module's own general-case output.
"""

from __future__ import annotations

import math
from pathlib import Path
from statistics import NormalDist

import pytest
from battle_engine.agent_evaluation import (
    BASELINE,
    CANDIDATE,
    ORIENTATION_CANDIDATE_FIRST,
    ORIENTATION_OPPONENT_FIRST,
    EvaluationCell,
)
from battle_engine.evaluation_analysis import (
    EvidenceState,
    PairedDirection,
    SampleState,
    analyze,
    exact_two_sided_binomial_p_value,
    paired_evidence_from_entries,
    paired_evidence_from_verdicts,
    rate_estimate_from_aggregate,
    wilson_interval,
)
from battle_engine.evaluation_history.models import evaluation_cells_from_raw

Z95 = NormalDist().inv_cdf(0.975)  # independent stdlib primitive, not this module's own code


def _cell(**overrides) -> EvaluationCell:
    defaults: dict = {
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
        "orientation": ORIENTATION_CANDIDATE_FIRST,
    }
    defaults.update(overrides)
    return EvaluationCell(**defaults)


# ---------------------------------------------------------------------------
# Wilson interval
# ---------------------------------------------------------------------------


def test_wilson_interval_zero_trials_is_none():
    assert wilson_interval(0, 0) is None


def test_wilson_interval_rejects_invalid_counts():
    with pytest.raises(ValueError):
        wilson_interval(5, 3)
    with pytest.raises(ValueError):
        wilson_interval(-1, 3)


def test_wilson_interval_zero_of_n_closed_form():
    # Independently derivable closed form at x=0: center == half_width, so
    # lower == 0 exactly, upper == z^2 / (n + z^2).
    n = 10
    z2 = Z95 * Z95
    expected_upper = z2 / (n + z2)
    interval = wilson_interval(0, n)
    assert interval is not None
    assert interval.lower == pytest.approx(0.0, abs=1e-12)
    assert interval.upper == pytest.approx(expected_upper, rel=1e-9)


def test_wilson_interval_n_of_n_closed_form():
    # Mirror image of the x=0 case: upper == 1 exactly, lower == n/(n+z^2).
    n = 10
    z2 = Z95 * Z95
    expected_lower = n / (n + z2)
    interval = wilson_interval(n, n)
    assert interval is not None
    assert interval.upper == 1.0
    assert interval.lower == pytest.approx(expected_lower, rel=1e-9)


def test_wilson_interval_one_of_one_matches_known_reference():
    # Textbook reference value for Wilson 95% CI of 1/1: [0.2065, 1.0000].
    interval = wilson_interval(1, 1)
    assert interval is not None
    assert interval.lower == pytest.approx(0.2065, abs=1e-3)
    assert interval.upper == 1.0


def test_wilson_interval_zero_of_one_matches_known_reference():
    # Mirror of the above: [0.0000, 0.7935].
    interval = wilson_interval(0, 1)
    assert interval is not None
    assert interval.lower == 0.0
    assert interval.upper == pytest.approx(0.7935, abs=1e-3)


def test_wilson_interval_balanced_sample_is_symmetric_around_half():
    interval = wilson_interval(5, 10)
    assert interval is not None
    midpoint = (interval.lower + interval.upper) / 2
    # Wilson center (not the naive midpoint of the bounds) sits above 0.5
    # only via a tiny, known asymmetry; the *bounds* themselves must still
    # bracket 0.5 symmetric to within floating point tolerance for p=0.5.
    assert midpoint == pytest.approx(0.5, abs=0.05)
    assert interval.lower < 0.5 < interval.upper


def test_wilson_interval_widens_as_n_shrinks_at_fixed_proportion():
    small = wilson_interval(1, 2)
    large = wilson_interval(50, 100)
    assert small is not None and large is not None
    assert (small.upper - small.lower) > (large.upper - large.lower)


def test_wilson_interval_always_contains_point_estimate_and_stays_in_bounds():
    for successes, trials in [(0, 1), (1, 1), (3, 7), (7, 7), (1, 100), (99, 100)]:
        interval = wilson_interval(successes, trials)
        assert interval is not None
        assert 0.0 <= interval.lower <= interval.upper <= 1.0
        p_hat = successes / trials
        assert interval.lower <= p_hat <= interval.upper


def test_wilson_interval_confidence_level_is_explicit_and_affects_width():
    narrow = wilson_interval(5, 20, confidence_level=0.80)
    wide = wilson_interval(5, 20, confidence_level=0.99)
    assert narrow is not None and wide is not None
    assert (narrow.upper - narrow.lower) < (wide.upper - wide.lower)
    assert narrow.confidence_level == 0.80
    assert wide.confidence_level == 0.99


def test_wilson_interval_rejects_invalid_confidence_level():
    with pytest.raises(ValueError):
        wilson_interval(1, 2, confidence_level=1.0)
    with pytest.raises(ValueError):
        wilson_interval(1, 2, confidence_level=0.0)


# ---------------------------------------------------------------------------
# Exact two-sided binomial (sign test / exact McNemar) p-value
# ---------------------------------------------------------------------------


def test_exact_binomial_requires_positive_trials():
    with pytest.raises(ValueError):
        exact_two_sided_binomial_p_value(0, 0)


@pytest.mark.parametrize(
    "successes, trials, expected",
    [
        # Independently published exact two-sided sign-test table values.
        (4, 4, 0.125),
        (0, 4, 0.125),
        (3, 4, 0.625),
        (1, 4, 0.625),
        (2, 4, 1.0),
        (1, 1, 1.0),
        (0, 1, 1.0),
        (2, 2, 0.5),
        (1, 2, 1.0),
    ],
)
def test_exact_binomial_matches_known_sign_test_values(successes, trials, expected):
    assert exact_two_sided_binomial_p_value(successes, trials) == pytest.approx(expected, abs=1e-9)


def test_exact_binomial_symmetric_in_successes():
    assert exact_two_sided_binomial_p_value(3, 10) == pytest.approx(
        exact_two_sided_binomial_p_value(7, 10), abs=1e-12
    )


def test_exact_binomial_most_extreme_split_is_smallest_p_value():
    for k in range(11):
        p = exact_two_sided_binomial_p_value(k, 10)
        assert 0.0 <= p <= 1.0
    assert exact_two_sided_binomial_p_value(0, 10) < exact_two_sided_binomial_p_value(3, 10)
    assert exact_two_sided_binomial_p_value(5, 10) == 1.0


# ---------------------------------------------------------------------------
# RateEstimate
# ---------------------------------------------------------------------------


def test_rate_estimate_insufficient_data_when_no_matches():
    cells = (_cell(status="failed", outcome=None),)
    result = analyze(CANDIDATE + "-id", None, cells)
    assert result.candidate_overall.state == SampleState.INSUFFICIENT_DATA
    assert result.candidate_overall.win_interval is None
    assert result.candidate_overall.observed_win_rate is None


def test_rate_estimate_tie_and_loss_rates_reported_separately_not_half_credited():
    cells = tuple(
        _cell(schedule_id=f"s{i}", outcome=outcome)
        for i, outcome in enumerate(["win", "win", "tie", "tie", "loss"])
    )
    result = analyze("cand", None, cells)
    overall = result.candidate_overall
    assert overall.wins == 2
    assert overall.ties == 2
    assert overall.losses == 1
    assert overall.matches_played == 5
    assert overall.observed_win_rate == pytest.approx(0.4)
    assert overall.tie_rate == pytest.approx(0.4)
    assert overall.loss_rate == pytest.approx(0.2)
    # A tie must never silently inflate the win interval as a half-win:
    # the interval is exactly wilson_interval(2, 5), not wilson_interval
    # derived from any tie-credited numerator.
    assert overall.win_interval == wilson_interval(2, 5)


# ---------------------------------------------------------------------------
# Paired candidate/baseline analysis
# ---------------------------------------------------------------------------


def _paired_cells(pairs, *, opponent_id="opp", orientation=ORIENTATION_CANDIDATE_FIRST):
    """Build candidate+baseline cells for a list of (candidate_outcome,
    baseline_outcome) pairs, one seed per pair."""

    cells = []
    for i, (cand_outcome, base_outcome) in enumerate(pairs):
        cells.append(
            _cell(
                schedule_id=f"c{i}",
                subject_role=CANDIDATE,
                subject_id="cand",
                opponent_id=opponent_id,
                seed=i,
                outcome=cand_outcome,
                orientation=orientation,
            )
        )
        cells.append(
            _cell(
                schedule_id=f"b{i}",
                subject_role=BASELINE,
                subject_id="base",
                opponent_id=opponent_id,
                seed=i,
                outcome=base_outcome,
                orientation=orientation,
            )
        )
    return tuple(cells)


def test_paired_analysis_candidate_always_better():
    cells = _paired_cells([("win", "loss")] * 6)
    result = analyze("cand", "base", cells)
    paired = result.overall_paired
    assert paired is not None
    assert paired.improved == 6
    assert paired.regressed == 0
    assert paired.discordant == 6
    assert paired.direction == PairedDirection.FAVORS_CANDIDATE
    assert paired.exact_p_value == pytest.approx(exact_two_sided_binomial_p_value(6, 6))
    assert paired.better_proportion_of_discordant == 1.0


def test_paired_analysis_baseline_always_better():
    cells = _paired_cells([("loss", "win")] * 6)
    result = analyze("cand", "base", cells)
    paired = result.overall_paired
    assert paired is not None
    assert paired.improved == 0
    assert paired.regressed == 6
    assert paired.direction == PairedDirection.FAVORS_BASELINE


def test_paired_analysis_all_equal_outcomes_no_discordant_pairs():
    cells = _paired_cells([("win", "win"), ("loss", "loss"), ("tie", "tie")])
    result = analyze("cand", "base", cells)
    paired = result.overall_paired
    assert paired is not None
    assert paired.discordant == 0
    assert paired.unchanged == 3
    assert paired.state == EvidenceState.NO_DISCORDANT_PAIRS
    assert paired.better_interval is None
    assert paired.exact_p_value is None
    assert paired.direction == PairedDirection.UNDETERMINED


def test_paired_analysis_all_ties_no_discordant_pairs():
    cells = _paired_cells([("tie", "tie")] * 4)
    result = analyze("cand", "base", cells)
    paired = result.overall_paired
    assert paired is not None
    assert paired.state == EvidenceState.NO_DISCORDANT_PAIRS
    assert paired.unchanged == 4


def test_paired_analysis_mixed_discordant_results():
    cells = _paired_cells([("win", "loss"), ("win", "loss"), ("loss", "win"), ("tie", "tie")])
    result = analyze("cand", "base", cells)
    paired = result.overall_paired
    assert paired is not None
    assert paired.improved == 2
    assert paired.regressed == 1
    assert paired.unchanged == 1
    assert paired.discordant == 3
    assert paired.direction == PairedDirection.FAVORS_CANDIDATE


def test_paired_analysis_very_small_sample_single_pair():
    cells = _paired_cells([("win", "loss")])
    result = analyze("cand", "base", cells)
    paired = result.overall_paired
    assert paired is not None
    assert paired.discordant == 1
    # A single discordant pair can never reach significance -- exact test
    # must reflect that honestly (p == 1.0), not overstate the evidence.
    assert paired.exact_p_value == 1.0


def test_paired_analysis_no_baseline_produces_no_paired_evidence():
    cells = tuple(_cell(schedule_id=f"c{i}", outcome="win") for i in range(3))
    result = analyze("cand", None, cells)
    assert result.overall_paired is None
    assert result.baseline_overall is None
    assert result.by_opponent == ()
    assert result.by_orientation == ()
    assert "no baseline" in result.opponent_consistency


def test_paired_analysis_zero_cells_no_matched_conditions():
    result = analyze("cand", "base", ())
    paired = result.overall_paired
    assert paired is not None
    assert paired.state == EvidenceState.NO_MATCHED_CONDITIONS
    assert paired.paired_count == 0


def test_paired_evidence_score_and_territory_deltas():
    cells = (
        _cell(
            schedule_id="c0",
            subject_role=CANDIDATE,
            subject_id="cand",
            outcome="win",
            score_subject=10.0,
            score_opponent=4.0,
            territory_subject=70.0,
        ),
        _cell(
            schedule_id="b0",
            subject_role=BASELINE,
            subject_id="base",
            outcome="loss",
            score_subject=3.0,
            score_opponent=9.0,
            territory_subject=30.0,
        ),
    )
    result = analyze("cand", "base", cells)
    paired = result.overall_paired
    assert paired is not None
    assert paired.candidate_score_differential_avg == pytest.approx(6.0)
    assert paired.baseline_score_differential_avg == pytest.approx(-6.0)
    assert paired.candidate_territory_avg == pytest.approx(70.0)
    assert paired.baseline_territory_avg == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# Opponent blocking
# ---------------------------------------------------------------------------


def test_opponent_blocking_same_overall_aggregate_different_distributions():
    # Opponent A: candidate strictly better. Opponent B: baseline strictly
    # better. Overall pooled evidence should show a mix even though the
    # two opponents individually are perfectly consistent internally.
    cells = _paired_cells(
        [("win", "loss")] * 3, opponent_id="opp_a"
    ) + _paired_cells([("loss", "win")] * 3, opponent_id="opp_b")
    result = analyze("cand", "base", cells)
    by_opponent = {p.scope_label: p for p in result.by_opponent}
    assert by_opponent["opp_a"].direction == PairedDirection.FAVORS_CANDIDATE
    assert by_opponent["opp_b"].direction == PairedDirection.FAVORS_BASELINE
    assert "mixed" in result.opponent_consistency


def test_opponent_blocking_consistent_direction_across_opponents():
    cells = _paired_cells([("win", "loss")] * 3, opponent_id="opp_a") + _paired_cells(
        [("win", "loss")] * 3, opponent_id="opp_b"
    )
    result = analyze("cand", "base", cells)
    assert "consistent" in result.opponent_consistency
    assert "candidate" in result.opponent_consistency


# ---------------------------------------------------------------------------
# Orientation blocking
# ---------------------------------------------------------------------------


def test_orientation_strong_first_position_effect():
    # Candidate wins every candidate_first cell, loses every
    # opponent_first cell -- overall pooled evidence must not hide this;
    # by_orientation must show opposite directions.
    cells = _paired_cells(
        [("win", "loss")] * 4, orientation=ORIENTATION_CANDIDATE_FIRST
    ) + _paired_cells([("loss", "win")] * 4, orientation=ORIENTATION_OPPONENT_FIRST)
    result = analyze("cand", "base", cells)
    by_orientation = {p.scope_label: p for p in result.by_orientation}
    assert by_orientation[ORIENTATION_CANDIDATE_FIRST].direction == PairedDirection.FAVORS_CANDIDATE
    assert by_orientation[ORIENTATION_OPPONENT_FIRST].direction == PairedDirection.FAVORS_BASELINE
    assert "mixed" in result.orientation_consistency
    # Candidate's own pooled win rate should reflect exactly half wins.
    assert result.candidate_overall.wins == 4
    assert result.candidate_overall.losses == 4


def test_orientation_symmetric_behavior_consistent_label():
    cells = _paired_cells(
        [("win", "loss")] * 3, orientation=ORIENTATION_CANDIDATE_FIRST
    ) + _paired_cells([("win", "loss")] * 3, orientation=ORIENTATION_OPPONENT_FIRST)
    result = analyze("cand", "base", cells)
    assert "consistent" in result.orientation_consistency


def test_orientation_candidate_by_orientation_rate_estimates_available_without_baseline():
    cells = tuple(
        _cell(schedule_id=f"c{i}", outcome="win", orientation=ORIENTATION_CANDIDATE_FIRST)
        for i in range(3)
    ) + tuple(
        _cell(schedule_id=f"o{i}", outcome="loss", orientation=ORIENTATION_OPPONENT_FIRST)
        for i in range(2)
    )
    result = analyze("cand", None, cells)
    by_orientation = {r.scope_label: r for r in result.candidate_by_orientation}
    assert by_orientation[ORIENTATION_CANDIDATE_FIRST].wins == 3
    assert by_orientation[ORIENTATION_OPPONENT_FIRST].losses == 2


# ---------------------------------------------------------------------------
# paired_evidence_from_verdicts (evaluations compare integration)
# ---------------------------------------------------------------------------


def test_paired_evidence_from_verdicts_matches_entries_equivalent():
    entries_cells = _paired_cells([("win", "loss"), ("loss", "win"), ("win", "win")])
    from battle_engine.agent_evaluation import compare_candidate_baseline

    entries = compare_candidate_baseline(entries_cells)
    from_entries = paired_evidence_from_entries("x", entries)
    from_verdicts = paired_evidence_from_verdicts("x", [e.classification for e in entries])
    assert from_entries.improved == from_verdicts.improved
    assert from_entries.regressed == from_verdicts.regressed
    assert from_entries.unchanged == from_verdicts.unchanged
    assert from_entries.inconclusive == from_verdicts.inconclusive
    assert from_entries.exact_p_value == from_verdicts.exact_p_value


# ---------------------------------------------------------------------------
# Identity isolation -- analysis must not mutate or depend on anything
# beyond the passed cells (frozen dataclasses guarantee no mutation; this
# proves no hidden global/identity-affecting side effect either).
# ---------------------------------------------------------------------------


def test_analysis_does_not_mutate_input_cells():
    cells = _paired_cells([("win", "loss"), ("loss", "win"), ("tie", "tie")])
    before = cells
    analyze("cand", "base", cells)
    assert cells == before
    for cell in cells:
        assert cell.status == "completed"


def test_analysis_is_a_pure_function_of_cells():
    cells = _paired_cells([("win", "loss"), ("loss", "win"), ("tie", "tie")])
    first = analyze("cand", "base", cells)
    second = analyze("cand", "base", cells)
    assert first.to_json() == second.to_json()


# ---------------------------------------------------------------------------
# Historical artifact compatibility -- analysis works from raw JSON-shaped
# cell dicts reconstructed via evaluation_history's own shared helper,
# exactly the seam v1/v2 adapters already use.
# ---------------------------------------------------------------------------


def test_analysis_works_from_evaluation_cells_from_raw():
    raw_cells = [
        {
            "schedule_id": "c0",
            "subject_role": CANDIDATE,
            "subject_id": "cand",
            "opponent_id": "opp",
            "seed": 1,
            "status": "completed",
            "outcome": "win",
            "score_subject": 10.0,
            "score_opponent": 5.0,
            "territory_subject": 60.0,
            "territory_opponent": 40.0,
            "orientation": ORIENTATION_CANDIDATE_FIRST,
            "artifact_dir": "matches/0001",
        },
        {
            "schedule_id": "b0",
            "subject_role": BASELINE,
            "subject_id": "base",
            "opponent_id": "opp",
            "seed": 1,
            "status": "completed",
            "outcome": "loss",
            "score_subject": 4.0,
            "score_opponent": 9.0,
            "territory_subject": 30.0,
            "territory_opponent": 70.0,
            "orientation": ORIENTATION_CANDIDATE_FIRST,
            "artifact_dir": "matches/0002",
        },
    ]
    cells = evaluation_cells_from_raw(raw_cells, Path("/tmp/does-not-need-to-exist"))
    result = analyze("cand", "base", cells)
    assert result.candidate_overall.wins == 1
    assert result.overall_paired is not None
    assert result.overall_paired.improved == 1


# ---------------------------------------------------------------------------
# rate_estimate_from_aggregate direct adapter sanity
# ---------------------------------------------------------------------------


def test_rate_estimate_from_aggregate_uses_orientation_scope_as_default_label():
    from battle_engine.agent_evaluation import SubjectAggregate

    aggregate = SubjectAggregate(
        subject_role=CANDIDATE,
        subject_id="cand",
        matches_played=4,
        wins=3,
        losses=1,
        orientation_scope="candidate_first",
    )
    estimate = rate_estimate_from_aggregate(aggregate)
    assert estimate.scope_label == "candidate_first"
    assert estimate.wins == 3
    assert estimate.win_interval == wilson_interval(3, 4)


def test_z95_value_matches_published_constant():
    # Cross-check statistics.NormalDist against the well-known published
    # value, independent of anything in evaluation_analysis.py.
    assert Z95 == pytest.approx(1.959963984540054, abs=1e-9)
    assert not math.isnan(Z95)
