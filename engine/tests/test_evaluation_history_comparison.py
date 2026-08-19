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

# H2: both sides default to the *same* recorded execution context, so tests
# that predate H2 and are not themselves about execution-context
# compatibility keep getting ordinary improved/regressed verdicts rather
# than everything degrading to inconclusive for lack of context evidence.
DEFAULT_CONTEXT_ID = "evaluation-context_default"
DEFAULT_CONTEXTS = (
    {
        "context_id": DEFAULT_CONTEXT_ID,
        "bytefray_version": "9.9.9-test",
        "agent_api_version": 1,
        "python_version": "3.11.0",
        "result_schema_version": 1,
        "replay_schema_version": 3,
        "rules_compatibility_id": RULES_ID,
        "first_used_at": "2026-01-01T00:00:00Z",
    },
)


def _identity(
    agent_id: str,
    sha: str = "abc123",
    entry_point: str = "agent.py:create_agent",
    local_source_fingerprint: str = "lfp-default",
) -> dict:
    return {
        "agent_id": agent_id,
        "kind": "python",
        "api_version": 1,
        "agent_version": "1.0",
        "entry_point": entry_point,
        "source_sha256": sha,
        "local_source_fingerprint": local_source_fingerprint,
    }


def _cell(
    *,
    opponent_id: str = "opponent",
    seed: int = 1,
    outcome: str | None = "win",
    status: str = "completed",
    occurrence: int = 0,
    opponent_sha: str = "opp-sha",
    opponent_local_fingerprint: str = "lfp-default",
    unknown_occurrence: bool = False,
    unknown_opponent_identity: bool = False,
    verified: bool | None = None,
    execution_context_id: str | None = DEFAULT_CONTEXT_ID,
    orientation: str | None = "candidate_first",
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
            else ConfidenceValue.recorded(
                _identity(opponent_id, sha=opponent_sha, local_source_fingerprint=opponent_local_fingerprint)
            )
        ),
        verified=verified,
        execution_context_id=(
            ConfidenceValue.recorded(execution_context_id)
            if execution_context_id is not None
            else ConfidenceValue.unknown()
        ),
        # v0.9 Phase 6 (Sec L.1): part of the alignment key now -- default
        # to "candidate_first" (also every pre-Phase-6 cell's certain
        # historical value) so this suite's existing fixtures keep aligning
        # exactly as before; `orientation=None` opts into UNKNOWN for tests
        # of that specific edge case.
        orientation=(
            ConfidenceValue.recorded(orientation)
            if orientation is not None
            else ConfidenceValue.unknown()
        ),
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
    execution_contexts: tuple[dict, ...] = DEFAULT_CONTEXTS,
    arena_alignment_mode: str | None = "fixed",
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
        execution_contexts=execution_contexts,
        # v0.9 Phase 6 (Sec AA.4.5): part of the alignment key now -- default
        # to "fixed" (v0.9's only value, and every pre-Phase-6 evaluation's
        # certain historical value) so this suite's existing fixtures keep
        # aligning exactly as before.
        arena_alignment_mode=(
            ConfidenceValue.recorded(arena_alignment_mode)
            if arena_alignment_mode is not None
            else ConfidenceValue.unknown()
        ),
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


# ---------------------------------------------------------------------------
# H2: narrow runtime-compatibility rule for direct comparison
# ---------------------------------------------------------------------------

OTHER_CONTEXT_ID = "evaluation-context_other"
OTHER_CONTEXTS = (
    {
        "context_id": OTHER_CONTEXT_ID,
        "bytefray_version": "9.9.9-test",
        "agent_api_version": 1,
        "python_version": "3.12.0",  # the one materially different field
        "result_schema_version": 1,
        "replay_schema_version": 3,
        "rules_compatibility_id": RULES_ID,
        "first_used_at": "2026-02-02T00:00:00Z",
    },
)


def test_same_execution_context_reports_ordinary_verdict():
    left = _summary(cells=(_cell(outcome="win"),))
    right = _summary(cells=(_cell(outcome="loss"),))
    result = align(left, right)
    assert result.rows[0].verdict == "regressed"


def test_different_runtime_context_downgrades_regression_to_inconclusive():
    left = _summary(cells=(_cell(outcome="win"),))
    right = _summary(
        cells=(_cell(outcome="loss", execution_context_id=OTHER_CONTEXT_ID),),
        execution_contexts=OTHER_CONTEXTS,
    )
    result = align(left, right)
    assert result.rows[0].verdict == "inconclusive"
    assert result.rows[0].reason is not None
    assert "execution context" in result.rows[0].reason
    assert result.denominators.regressed == 0
    assert result.denominators.inconclusive == 1


def test_different_runtime_context_downgrades_an_unchanged_verdict_too():
    """H3: for this pass, the conservative rule applies to *every* outcome
    verdict, including unchanged -- "no observed difference under
    different/unknown runtimes" is still not a controlled direct
    comparison, so it is downgraded to inconclusive exactly like
    improved/regressed would be, never left as an ordinary "unchanged"."""

    left = _summary(cells=(_cell(outcome="win"),))
    right = _summary(
        cells=(_cell(outcome="win", execution_context_id=OTHER_CONTEXT_ID),),
        execution_contexts=OTHER_CONTEXTS,
    )
    result = align(left, right)
    assert result.rows[0].verdict == "inconclusive"
    assert result.denominators.unchanged == 0


INCOMPLETE_CONTEXT_ID = "evaluation-context_incomplete"
INCOMPLETE_CONTEXTS = ({"context_id": INCOMPLETE_CONTEXT_ID},)  # missing every other required field


def test_both_sides_incomplete_execution_context_never_compares_equal():
    """H3: two *incomplete* context dicts (each only ``{"context_id": ...}``,
    with no other required field) must never be treated as compatible just
    because every missing field reads as ``None`` on both sides -- absence
    of evidence is not evidence of compatibility, even symmetrically."""

    left = _summary(
        cells=(_cell(outcome="win", execution_context_id=INCOMPLETE_CONTEXT_ID),),
        execution_contexts=INCOMPLETE_CONTEXTS,
    )
    right = _summary(
        cells=(_cell(outcome="loss", execution_context_id=INCOMPLETE_CONTEXT_ID),),
        execution_contexts=INCOMPLETE_CONTEXTS,
    )
    result = align(left, right)
    assert result.rows[0].verdict == "inconclusive"
    assert result.denominators.regressed == 0
    assert result.denominators.directly_comparable == 0


def test_one_side_incomplete_execution_context_never_compares_equal():
    left = _summary(
        cells=(_cell(outcome="win", execution_context_id=INCOMPLETE_CONTEXT_ID),),
        execution_contexts=INCOMPLETE_CONTEXTS,
    )
    right = _summary(cells=(_cell(outcome="loss"),))  # full DEFAULT_CONTEXT_ID context
    result = align(left, right)
    assert result.rows[0].verdict == "inconclusive"
    assert result.denominators.directly_comparable == 0


def test_missing_execution_context_downgrades_regression_to_inconclusive():
    left = _summary(cells=(_cell(outcome="win"),))
    right = _summary(cells=(_cell(outcome="loss", execution_context_id=None),))
    result = align(left, right)
    assert result.rows[0].verdict == "inconclusive"


def test_retry_under_second_context_is_still_comparable_to_itself():
    """A resumed cell that kept its original context (never rewritten by a
    later resuming process under a different context -- Sec 5/6) compares
    normally against another artifact recorded under that same context."""

    left = _summary(cells=(_cell(outcome="tie"),))
    right = _summary(cells=(_cell(outcome="win"),))  # both default to DEFAULT_CONTEXT_ID
    result = align(left, right)
    assert result.rows[0].verdict == "improved"


def test_mixed_context_matrix_only_affects_the_cells_that_actually_differ():
    left = _summary(
        cells=(
            _cell(opponent_id="a", outcome="win"),
            _cell(opponent_id="b", outcome="win", execution_context_id=OTHER_CONTEXT_ID),
        ),
        execution_contexts=DEFAULT_CONTEXTS + OTHER_CONTEXTS,
    )
    right = _summary(
        cells=(
            _cell(opponent_id="a", outcome="loss"),
            _cell(opponent_id="b", outcome="loss"),
        )
    )
    result = align(left, right)
    rows_by_opponent = {row.opponent_id: row for row in result.rows}
    assert rows_by_opponent["a"].verdict == "regressed"  # same context both sides
    assert rows_by_opponent["b"].verdict == "inconclusive"  # mismatched context


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
    """M3: strict alignment correctly refuses to treat this as directly
    comparable -- but since both sides still share (opponent_id, seed) and
    the mismatch is unambiguous (exactly one unmatched cell per side), it
    is reported honestly as changed_condition, not folded into a bare
    unmatched count that would look identical to "no related cell at all"."""

    left = _summary(cells=(_cell(outcome="win", opponent_sha="sha-1"),))
    right = _summary(cells=(_cell(outcome="win", opponent_sha="sha-2"),))
    result = align(left, right)
    assert result.denominators.directly_comparable == 0
    assert result.denominators.unmatched_left == 0
    assert result.denominators.unmatched_right == 0
    assert result.denominators.changed_condition == 1
    assert len(result.changed_condition) == 1


def test_opponent_helper_only_edit_prevents_direct_comparison():
    """B4: an opponent revision separated only by a local-helper edit (the
    entry file/`source_sha256` and `entry_point` are identical on both
    sides -- only `local_source_fingerprint` differs) must still be treated
    as a changed condition, never silently direct-comparable. Before the
    fix, `local_source_fingerprint` was excluded from the strict condition
    key, so this exact scenario would have compared directly and
    attributed any outcome delta to the candidate instead."""

    left = _summary(cells=(_cell(outcome="win", opponent_local_fingerprint="lfp-v1"),))
    right = _summary(cells=(_cell(outcome="loss", opponent_local_fingerprint="lfp-v2"),))
    result = align(left, right)
    assert result.denominators.directly_comparable == 0
    assert result.denominators.improved == 0
    assert result.denominators.regressed == 0
    assert result.denominators.unchanged == 0
    assert result.denominators.changed_condition == 1
    assert len(result.changed_condition) == 1
    assert not result.rows


def test_rules_compatibility_mismatch_prevents_direct_comparison():
    left = _summary(cells=(_cell(outcome="win"),), rules_id="evaluation-rules-1")
    right = _summary(cells=(_cell(outcome="win"),), rules_id="evaluation-rules-2")
    result = align(left, right)
    assert result.denominators.directly_comparable == 0


def test_historical_evaluation_rules_1_aligns_with_current_bytefray_rules_1():
    """v0.10 Phase 4: evaluation-rules-1 (historical) and bytefray-rules-1
    (current) denote the same gameplay semantics for their entire shared
    history (docs/RULES.md) and must align directly, not merely land in
    "changed_condition" -- Phase 2 renaming the canonical spelling must not,
    by itself, make an old baseline incomparable to a fresh run.
    """

    left = _summary(cells=(_cell(outcome="win"),), rules_id="evaluation-rules-1")
    right = _summary(cells=(_cell(outcome="tie"),), rules_id="bytefray-rules-1")
    result = align(left, right)
    assert result.denominators.directly_comparable == 1
    assert [row.verdict for row in result.rows] == ["regressed"]


def test_unrelated_rules_id_does_not_alias_by_naming_convention():
    """Only the one finite, evidence-backed alias normalizes -- a
    superficially similar but genuinely different Ruleset identity (a
    hypothetical future ``bytefray-rules-2``) must never silently compare
    equal to ``bytefray-rules-1`` just because it shares a naming pattern.
    """

    left = _summary(cells=(_cell(outcome="win"),), rules_id="bytefray-rules-1")
    right = _summary(cells=(_cell(outcome="win"),), rules_id="bytefray-rules-2")
    result = align(left, right)
    assert result.denominators.directly_comparable == 0


def test_v1_unknown_rules_id_never_compares_equal_even_to_another_unknown():
    left = _summary(cells=(_cell(outcome="win"),), rules_id=None)
    right = _summary(cells=(_cell(outcome="win"),), rules_id=None)
    result = align(left, right)
    assert result.denominators.directly_comparable == 0


def test_v2_alpha1_rules_id_never_aligns_against_v1():
    """v2.0.0-alpha.1's evaluation/comparison-machinery guard (Phase 6).

    Nothing in ``agent_evaluation.EvaluationService`` threads
    ``MatchRequest.ruleset_id`` through today -- ``EVALUATION_RULES_
    COMPATIBILITY_ID`` is a hardcoded module constant, so a real
    ``bytefray-rules-2-alpha1``-tagged evaluation summary cannot currently
    be produced through that pipeline (see docs/V2_0_ALPHA_ARCHITECTURE.md
    Sec 4/Sec 6's "Explicitly deferred" -- EvaluationService plumbing is
    out of this alpha's scope). This proves the *existing* alignment
    refusal already established by
    ``test_unrelated_rules_id_does_not_alias_by_naming_convention`` above
    also covers the exact literal alpha identity, using directly
    constructed summaries: if that pipeline is ever extended to run the
    alpha Ruleset, its results can never be silently conflated with a
    Ruleset-v1 evaluation's.
    """

    left = _summary(cells=(_cell(outcome="win"),), rules_id="bytefray-rules-1")
    right = _summary(cells=(_cell(outcome="win"),), rules_id="bytefray-rules-2-alpha1")
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


# ---------------------------------------------------------------------------
# M3: honest changed_condition / ambiguous_duplicate_groups classification
# ---------------------------------------------------------------------------


def test_asymmetric_duplicates_both_sides_nonempty_is_ambiguous_not_changed_condition():
    """Left has one unmatched duplicate for (opponent, seed); right has two.
    Both sides are non-empty, so this is not "nothing to relate it to" --
    but pairing 1 against 2 would have to guess, so it must be reported as
    an ambiguous_duplicate_group, never silently paired as changed_condition
    (which is reserved for an unambiguous 1:1 relation)."""

    left = _summary(cells=(_cell(outcome="win", unknown_occurrence=True),))
    right = _summary(
        cells=(
            _cell(outcome="win", unknown_occurrence=True),
            _cell(outcome="loss", unknown_occurrence=True),
        )
    )
    result = align(left, right)
    assert result.denominators.changed_condition == 0
    assert result.denominators.ambiguous_duplicate_groups == 1
    assert len(result.ambiguous_duplicate_groups) == 1
    group = result.ambiguous_duplicate_groups[0]
    assert group[0] == "opponent" and group[1] == 1
    assert len(group[2]) == 1 and len(group[3]) == 2


def test_symmetric_duplicates_two_and_two_are_ambiguous_not_positionally_zipped():
    """Two unmatched duplicates on each side for the same (opponent, seed)
    must never be silently zipped by list order -- reordering which
    duplicate appears first must not change the classification, since no
    pairing is ever attempted for a genuinely ambiguous group."""

    left = _summary(
        cells=(
            _cell(outcome="win", unknown_occurrence=True),
            _cell(outcome="loss", unknown_occurrence=True),
        )
    )
    right_in_order = _summary(
        cells=(
            _cell(outcome="loss", unknown_occurrence=True),
            _cell(outcome="win", unknown_occurrence=True),
        )
    )
    right_reordered = _summary(
        cells=(
            _cell(outcome="win", unknown_occurrence=True),
            _cell(outcome="loss", unknown_occurrence=True),
        )
    )
    result_a = align(left, right_in_order)
    result_b = align(left, right_reordered)
    for result in (result_a, result_b):
        assert result.denominators.changed_condition == 0
        assert result.denominators.ambiguous_duplicate_groups == 1
        # No row is ever synthesized from an ambiguous group -- it is
        # reported, not guessed at.
        assert result.rows == ()


def test_malformed_duplicate_occurrence_indices_never_crash_or_mispair():
    """H4: two cells on the same side both claiming
    condition_occurrence_index=0 for the same (opponent, seed) is a
    corrupted/malformed state -- the strict-key uniqueness invariant is
    already broken, so this group must never be zipped positionally
    (previously: one of the two same-side cells was silently guessed to
    "match" the single right-side cell purely by dict/zip ordering, which
    could pair either the win or the loss cell depending on iteration
    order). This must not crash comparison, and must report the group as
    ambiguous with zero ordinary direct verdicts, never a guessed pairing."""

    left = _summary(
        cells=(
            _cell(outcome="win", occurrence=0),
            _cell(outcome="loss", occurrence=0),  # malformed: duplicate index
        )
    )
    right = _summary(cells=(_cell(outcome="win", occurrence=0),))
    result = align(left, right)  # must not raise
    assert result.denominators.directly_comparable == 0
    assert result.denominators.ambiguous_duplicate_groups == 1
    assert not result.rows
    assert not result.unmatched_left
    assert not result.unmatched_right


def test_symmetric_malformed_duplicates_on_both_sides_are_not_position_paired():
    """H4 required test: two cells on *each* side claiming the identical
    (opponent, seed, condition_occurrence_index=0) coordinate, with
    reversed outcomes/order between the sides. Zipping positionally would
    silently produce two ordinary verdicts built from an arbitrary,
    unverifiable pairing -- this must instead be one ambiguous group with
    zero ordinary direct verdicts."""

    left = _summary(
        cells=(
            _cell(outcome="win", occurrence=0),
            _cell(outcome="loss", occurrence=0),
        )
    )
    right = _summary(
        cells=(
            _cell(outcome="loss", occurrence=0),
            _cell(outcome="win", occurrence=0),
        )
    )
    result = align(left, right)  # must not raise
    assert result.denominators.directly_comparable == 0
    assert result.denominators.improved == 0
    assert result.denominators.regressed == 0
    assert result.denominators.unchanged == 0
    assert result.denominators.ambiguous_duplicate_groups == 1
    assert not result.rows
    assert not result.unmatched_left
    assert not result.unmatched_right


def test_heterogeneous_v1_duplicate_outcomes_are_ambiguous_not_paired_by_outcome():
    """Legacy v1 duplicates (condition_occurrence_index UNKNOWN, per
    v1_adapter's honest handling of ambiguous duplicate evidence) with
    different outcomes on each side must never be paired based on which
    outcomes happen to match -- they are reported as ambiguous, full stop."""

    left = _summary(
        cells=(
            _cell(outcome="win", unknown_occurrence=True),
            _cell(outcome="win", unknown_occurrence=True),
        )
    )
    right = _summary(
        cells=(
            _cell(outcome="loss", unknown_occurrence=True),
            _cell(outcome="tie", unknown_occurrence=True),
        )
    )
    result = align(left, right)
    assert result.denominators.ambiguous_duplicate_groups == 1
    assert result.rows == ()
    assert result.reproducibility_anomalies == ()


def test_related_condition_family_differing_only_in_rules_id_is_changed_condition():
    """Same (opponent, seed) nominal slot, but the whole artifact's rules
    compatibility id differs -- a related-but-incompatible condition
    family, reported honestly as changed_condition rather than a bare
    unmatched count."""

    left = _summary(cells=(_cell(outcome="win"),), rules_id="evaluation-rules-1")
    right = _summary(cells=(_cell(outcome="loss"),), rules_id="evaluation-rules-2")
    result = align(left, right)
    assert result.denominators.directly_comparable == 0
    assert result.denominators.changed_condition == 1
    assert result.denominators.unmatched_left == 0
    assert result.denominators.unmatched_right == 0


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
        execution_context_id=ConfidenceValue.recorded(DEFAULT_CONTEXT_ID),
        orientation=ConfidenceValue.recorded("candidate_first"),
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
