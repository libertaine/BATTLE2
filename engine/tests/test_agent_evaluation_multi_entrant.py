"""v2.0.0-beta2 Phase 2 -- multi-entrant ("group") evaluation model
(docs/V2_0_BETA2_PHASE2_MULTI_ENTRANT_EVALUATION.md).

Integration-level: real ``EvaluationService`` group-mode runs exercising
the new roster/seat/layout domain model side by side with 1v1 (Phase 1)
preservation. See ``test_agent_evaluation_v2_methodology.py`` for the 1v1
v2 methodology this phase must not disturb, and
``test_v2_alpha4_multi_entrant.py`` for the engine-level (N-entrant
execution, winner semantics) coverage this phase reuses rather than
re-proves.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from battle_engine.agent_evaluation import (
    BYTEFRAY_RULESET_ID,
    BYTEFRAY_RULESET_V2_ID,
    IDENTITY_VERSION_V2,
    IDENTITY_VERSION_V2_GROUP,
    SCHEMA_VERSION_V2,
    SCHEMA_VERSION_V2_GROUP,
    EvaluationConfigurationError,
    EvaluationRequest,
    EvaluationSeatAssignment,
    EvaluationService,
    all_subject_aggregates,
    build_matrix,
    enumerate_seat_assignments,
    seat_label,
    standard_layouts,
)
from battle_engine.agent_evaluation import (
    main as evaluation_main,
)
from battle_engine.config import Config
from battle_engine.evaluation_history.comparison import align
from battle_engine.evaluation_history.discovery import adapt_any

NOP_ACTION = "AgentAction(ActionKind.NOP)"


def _write_agent(root: Path, name: str, act_body: str) -> Path:
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
    def act(self, observation):
{act_body}
def create_agent(): return Agent()
""",
        encoding="utf-8",
    )
    return directory


def _write_nop_agent(root: Path, name: str) -> Path:
    return _write_agent(root, name, f"        return {NOP_ACTION}")


def _write_halt_agent(root: Path, name: str) -> Path:
    return _write_agent(root, name, "        return AgentAction(ActionKind.HALT)")


def _request(root: Path, **overrides) -> EvaluationRequest:
    defaults: dict = {
        "candidate_id": "candidate",
        "opponent_ids": ("opp_a", "opp_b"),
        "seeds": (1,),
        "output_dir": root / "eval-out",
        "ticks": 15,
        "data_root": root,
        "both_orientations": False,
        "ruleset_id": BYTEFRAY_RULESET_V2_ID,
        "group": True,
    }
    defaults.update(overrides)
    return EvaluationRequest(**defaults)


@pytest.fixture()
def three_agents(tmp_path: Path) -> Path:
    _write_nop_agent(tmp_path, "candidate")
    _write_nop_agent(tmp_path, "opp_a")
    _write_nop_agent(tmp_path, "opp_b")
    return tmp_path


# ---------------------------------------------------------------------------
# Validation / boundaries
# ---------------------------------------------------------------------------


def test_group_requires_v2_ruleset(three_agents: Path):
    with pytest.raises(EvaluationConfigurationError):
        EvaluationService().run(_request(three_agents, ruleset_id=BYTEFRAY_RULESET_ID))


def test_group_requires_at_least_two_opponents(three_agents: Path):
    with pytest.raises(EvaluationConfigurationError):
        EvaluationService().run(_request(three_agents, opponent_ids=("opp_a",)))


def test_group_rejects_baseline(three_agents: Path):
    _write_nop_agent(three_agents, "baseline_agent")
    with pytest.raises(EvaluationConfigurationError):
        EvaluationService().run(_request(three_agents, baseline_id="baseline_agent"))


@pytest.mark.parametrize("orientation_flag", ["--single-orientation", "--both-orientations"])
def test_group_cli_rejects_pairwise_orientation_flags(orientation_flag: str, capsys):
    code = evaluation_main(
        [
            "candidate",
            "--opponents",
            "opp_a,opp_b",
            "--ruleset",
            BYTEFRAY_RULESET_V2_ID,
            "--group",
            orientation_flag,
            "--dry-run",
        ]
    )
    assert code == 2
    assert "cannot be combined with --group" in capsys.readouterr().err


def test_non_group_v2_evaluation_unaffected_by_group_field_existing(three_agents: Path):
    """A plain 1v1 v2 request (group=False, the default) is byte-shape
    unaffected by group mode existing -- schema/identity stay at Phase 1's
    5, never 6."""

    request = _request(three_agents, opponent_ids=("opp_a",), group=False)
    result = EvaluationService().run(request)
    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == SCHEMA_VERSION_V2 == 5
    assert data["identity_version"] == IDENTITY_VERSION_V2 == 5
    assert data["group"] is False


# ---------------------------------------------------------------------------
# Roster / entrant identity
# ---------------------------------------------------------------------------


def test_roster_agent_ids_preserves_request_order_but_canonical_is_sorted(three_agents: Path):
    request = _request(three_agents)
    assert request.roster_agent_ids == ("candidate", "opp_a", "opp_b")
    assert request.canonical_roster == tuple(sorted(("candidate", "opp_a", "opp_b")))


def test_canonical_roster_deterministic_regardless_of_input_order(three_agents: Path):
    a = _request(three_agents, candidate_id="candidate", opponent_ids=("opp_a", "opp_b"))
    b = _request(three_agents, candidate_id="candidate", opponent_ids=("opp_b", "opp_a"))
    assert a.canonical_roster == b.canonical_roster


def test_roster_membership_affects_identity(three_agents: Path):
    _write_nop_agent(three_agents, "opp_c")
    a = EvaluationService().preflight(
        candidate_id="candidate", opponent_ids=("opp_a", "opp_b"), seeds=(1,),
        data_root=three_agents, ruleset_id=BYTEFRAY_RULESET_V2_ID, group=True,
    )
    b = EvaluationService().preflight(
        candidate_id="candidate", opponent_ids=("opp_a", "opp_c"), seeds=(1,),
        data_root=three_agents, ruleset_id=BYTEFRAY_RULESET_V2_ID, group=True,
    )
    assert a[1] != b[1]


def test_entrant_count_affects_identity(three_agents: Path):
    _write_nop_agent(three_agents, "opp_c")
    two = EvaluationService().preflight(
        candidate_id="candidate", opponent_ids=("opp_a", "opp_b"), seeds=(1,),
        data_root=three_agents, ruleset_id=BYTEFRAY_RULESET_V2_ID, group=True,
    )
    three = EvaluationService().preflight(
        candidate_id="candidate", opponent_ids=("opp_a", "opp_b", "opp_c"), seeds=(1,),
        data_root=three_agents, ruleset_id=BYTEFRAY_RULESET_V2_ID, group=True,
    )
    assert two[1] != three[1]


def test_self_play_duplicate_agent_id_in_roster_does_not_crash(tmp_path: Path):
    """The same agent occupying two seats (self-play) is representable
    without ambiguity -- fewer distinct seat assignments than a fully
    distinct roster's N! would produce."""

    _write_nop_agent(tmp_path, "candidate")
    _write_nop_agent(tmp_path, "opp_a")
    request = _request(tmp_path, opponent_ids=("candidate", "opp_a"))
    matrix = build_matrix(request, "evaluation_x")
    # roster = (candidate, candidate, opp_a) -> 3!/2! = 3 distinct seat
    # assignments, not 6.
    assert len({c.seat_agent_ids for c in matrix}) == 3


def test_self_play_executes_successfully_through_real_engine(tmp_path: Path):
    """Execution-level proof, not just schedule generation: the native
    engine rejects duplicate MatchEntrant.agent_id (match_service.
    NativeMatchService.run), but MatchEntrant.agent_id is the seat label
    ("A"/"B"/"C", always unique per cell) -- the logical/source agent id
    (MatchEntrant.name) is what may legitimately repeat for self-play.
    _test_agents/_execute_group_cell must construct entrants this way
    (seat as agent_id, logical id as name) for a duplicate-agent roster to
    execute at all; this proves it does, for every one of the 3 distinct
    seat assignments a 2-duplicate/1-distinct roster produces."""

    _write_nop_agent(tmp_path, "candidate")
    _write_nop_agent(tmp_path, "opp_a")
    request = _request(tmp_path, opponent_ids=("candidate", "opp_a"), seeds=(1,))
    result = EvaluationService().run(request)
    assert len(result.cells) == 1 * 3 * 3  # seeds(1) x layouts(3) x seat assignments(3)
    assert all(cell.status == "completed" for cell in result.cells)
    assert all(cell.error_code is None for cell in result.cells)
    seats_seen = {cell.seat_agent_ids for cell in result.cells}
    assert seats_seen == {a.seat_agent_ids for a in enumerate_seat_assignments(request.roster_agent_ids)}
    assert len(seats_seen) == 3
    # Every cell's own result.json must record 3 distinct match-level
    # entrant slots (A/B/C) even though only 2 distinct logical agents
    # occupy them -- proving the engine boundary itself accepted the
    # duplicate-name roster (no "agent_unknown"/duplicate-id rejection).
    for cell in result.cells:
        data = json.loads((cell.artifact_dir / "result.json").read_text(encoding="utf-8"))
        assert {e["agent_id"] for e in data["entrants"]} == {"A", "B", "C"}
        assert sorted(e["name"] for e in data["entrants"]) == sorted(cell.seat_agent_ids)


# ---------------------------------------------------------------------------
# Seat / permutation model
# ---------------------------------------------------------------------------


def test_seat_label_matches_agent_test_slot_convention():
    from battle_engine.agent_test import OPPONENT_SLOT, TESTED_AGENT_SLOT

    assert seat_label(0) == TESTED_AGENT_SLOT == "A"
    assert seat_label(1) == OPPONENT_SLOT == "B"
    assert seat_label(2) == "C"


def test_enumerate_seat_assignments_exhaustive_for_distinct_roster():
    assignments = enumerate_seat_assignments(("a", "b", "c"))
    assert len(assignments) == 6
    assert len({a.seat_agent_ids for a in assignments}) == 6
    assert all(isinstance(a, EvaluationSeatAssignment) for a in assignments)


def test_enumerate_seat_assignments_deterministic():
    assert enumerate_seat_assignments(("a", "b", "c")) == enumerate_seat_assignments(("a", "b", "c"))


def test_all_three_player_permutations_generated_in_real_matrix(three_agents: Path):
    request = _request(three_agents, seeds=(1,))
    matrix = build_matrix(request, "evaluation_x")
    seats_seen = {c.seat_agent_ids for c in matrix}
    assert seats_seen == {a.seat_agent_ids for a in enumerate_seat_assignments(request.roster_agent_ids)}
    assert len(seats_seen) == 6


def test_no_duplicate_permutations_in_matrix(three_agents: Path):
    request = _request(three_agents, seeds=(1,))
    matrix = build_matrix(request, "evaluation_x")
    by_layout_seed = {}
    for cell in matrix:
        key = (cell.layout_id, cell.seed)
        by_layout_seed.setdefault(key, []).append(cell.seat_agent_ids)
    for seats in by_layout_seed.values():
        assert len(seats) == len(set(seats))


def test_seat_assignment_round_trips_through_artifact(three_agents: Path):
    request = _request(three_agents, seeds=(1,))
    result = EvaluationService().run(request)
    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    for raw_cell, cell in zip(data["cells"], result.cells, strict=True):
        assert tuple(raw_cell["seat_agent_ids"]) == cell.seat_agent_ids


def test_permutation_affects_schedule_identity(three_agents: Path):
    request = _request(three_agents, seeds=(1,))
    matrix = build_matrix(request, "evaluation_x")
    same_layout_seed = [c for c in matrix if c.layout_id == "spread" and c.seed == 1]
    assert len({c.schedule_id for c in same_layout_seed}) == len(same_layout_seed)


# ---------------------------------------------------------------------------
# Placement / layout model
# ---------------------------------------------------------------------------


def test_standard_layouts_derived_deterministically_from_arena_size():
    assert standard_layouts(3, 4096) == standard_layouts(3, 4096)
    assert len(standard_layouts(3, 4096)) == 3


def test_standard_layouts_seat_starts_never_collide():
    from battle_engine.python_runtime import core_addresses

    arena_size = Config().arena_size
    for layout in standard_layouts(3, arena_size):
        cells_by_seat = [set(core_addresses(start, arena_size)) for start in layout.seat_starts]
        for i in range(len(cells_by_seat)):
            for j in range(i + 1, len(cells_by_seat)):
                assert not (cells_by_seat[i] & cells_by_seat[j])


def test_layout_enters_identity(three_agents: Path):
    request = _request(three_agents, seeds=(1,))
    matrix = build_matrix(request, "evaluation_x")
    layouts_seen = {c.layout_id for c in matrix}
    assert layouts_seen == {"spread", "spread-shifted", "close"}
    assert len({c.schedule_id for c in matrix}) == len(matrix)


def test_layout_and_permutation_are_distinct_identity_dimensions(three_agents: Path):
    request = _request(three_agents, seeds=(1,))
    matrix = build_matrix(request, "evaluation_x")
    same_seats_different_layout = [
        c for c in matrix if c.seat_agent_ids == matrix[0].seat_agent_ids
    ]
    assert len({c.layout_id for c in same_seats_different_layout}) == 3
    assert len({c.schedule_id for c in same_seats_different_layout}) == 3


# ---------------------------------------------------------------------------
# Seeds
# ---------------------------------------------------------------------------


def test_seed_affects_group_identity(three_agents: Path):
    request = _request(three_agents, seeds=(1, 2))
    matrix = build_matrix(request, "evaluation_x")
    seeds_seen = {c.seed for c in matrix}
    assert seeds_seen == {1, 2}
    assert len({c.schedule_id for c in matrix}) == len(matrix)


def test_expected_group_cell_count_exact(three_agents: Path):
    request = _request(three_agents, seeds=(1, 2, 3))
    matrix = build_matrix(request, "evaluation_x")
    # seeds(3) x layouts(3) x permutations(6)
    assert len(matrix) == 3 * 3 * 6 == 54


# ---------------------------------------------------------------------------
# Ruleset
# ---------------------------------------------------------------------------


def test_v1_matrix_unaffected_by_group_feature_existing(three_agents: Path):
    from battle_engine.agent_evaluation import EVALUATION_RULES_COMPATIBILITY_ID

    request = EvaluationRequest(
        candidate_id="candidate", opponent_ids=("opp_a",), seeds=(1,),
        output_dir=three_agents / "out", data_root=three_agents, both_orientations=False,
    )
    matrix = build_matrix(request, "evaluation_x")
    assert len(matrix) == 1
    assert matrix[0].roster_agent_ids == ()
    assert matrix[0].rules_compatibility_id == EVALUATION_RULES_COMPATIBILITY_ID


def test_group_cells_execute_under_resolved_ruleset(three_agents: Path):
    result = EvaluationService().run(_request(three_agents, seeds=(1,)))
    for cell in result.cells:
        data = json.loads((cell.artifact_dir / "result.json").read_text(encoding="utf-8"))
        assert data["ruleset_id"] == BYTEFRAY_RULESET_V2_ID
        assert len(data["entrants"]) == 3


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------


def test_group_resume_reuses_completed_cells(three_agents: Path):
    request = _request(three_agents, seeds=(1, 2))
    first = EvaluationService().run(request)
    second = EvaluationService().run(request)
    assert [c.match_id for c in first.cells] == [c.match_id for c in second.cells]


def test_group_resume_executes_missing_cells(three_agents: Path):
    request = _request(three_agents, seeds=(1,))
    first = EvaluationService().run(request)
    data = json.loads(first.state_path.read_text(encoding="utf-8"))
    removed = data["cells"].pop()
    import shutil

    shutil.rmtree(request.output_dir / removed["artifact_dir"], ignore_errors=True)
    data["complete"] = False
    first.state_path.write_text(json.dumps(data), encoding="utf-8")

    resumed = EvaluationService().run(request)
    assert len(resumed.cells) == len(first.cells)
    assert all(cell.status == "completed" for cell in resumed.cells)


def test_changed_roster_rejects_group_resume(three_agents: Path):
    _write_nop_agent(three_agents, "opp_c")
    EvaluationService().run(_request(three_agents, opponent_ids=("opp_a", "opp_b"), seeds=(1,)))
    with pytest.raises(EvaluationConfigurationError):
        EvaluationService().run(_request(three_agents, opponent_ids=("opp_a", "opp_c"), seeds=(1,)))


def test_group_vs_1v1_v2_rejects_resume_at_same_output(three_agents: Path):
    group_request = _request(three_agents, opponent_ids=("opp_a", "opp_b"), seeds=(1,))
    EvaluationService().run(group_request)
    pairwise_request = _request(
        three_agents, opponent_ids=("opp_a", "opp_b"), seeds=(1,), group=False,
        output_dir=group_request.output_dir,
    )
    with pytest.raises(EvaluationConfigurationError):
        EvaluationService().run(pairwise_request)


def test_group_schema_and_identity_version_are_six(three_agents: Path):
    result = EvaluationService().run(_request(three_agents, seeds=(1,)))
    data = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == SCHEMA_VERSION_V2_GROUP == 6
    assert data["identity_version"] == IDENTITY_VERSION_V2_GROUP == 6
    assert data["schema_version"] != SCHEMA_VERSION_V2
    assert data["identity_version"] != IDENTITY_VERSION_V2


# ---------------------------------------------------------------------------
# Parallel execution
# ---------------------------------------------------------------------------


def test_workers_do_not_affect_group_cell_identity_or_results(three_agents: Path):
    kwargs = {"seeds": (1, 2)}
    serial = EvaluationService().run(
        _request(three_agents, output_dir=three_agents / "serial", workers=1, **kwargs)
    )
    parallel = EvaluationService().run(
        _request(three_agents, output_dir=three_agents / "parallel", workers=4, **kwargs)
    )
    assert serial.evaluation_id == parallel.evaluation_id
    serial_by_id = {c.schedule_id: (c.match_id, c.outcome) for c in serial.cells}
    parallel_by_id = {c.schedule_id: (c.match_id, c.outcome) for c in parallel.cells}
    assert serial_by_id == parallel_by_id


# ---------------------------------------------------------------------------
# Winner semantics (evaluation-layer surfacing of the engine's own
# resolve_winner -- see test_v2_alpha4_multi_entrant.py for the engine's
# own exhaustive N-entrant winner-semantics coverage, not re-proven here)
# ---------------------------------------------------------------------------


def test_candidate_outcome_is_win_only_when_literally_the_resolved_winner(tmp_path: Path):
    """Every entrant HALTs immediately except the candidate -- the
    candidate is the sole survivor and must win outright regardless of
    which seat it occupies (a direct evaluation-layer check that
    _cell_from_match_result_group's outcome derivation tracks
    resolve_winner's own survivor-eligibility rule, not a fixed slot)."""

    _write_nop_agent(tmp_path, "candidate")
    _write_halt_agent(tmp_path, "opp_a")
    _write_halt_agent(tmp_path, "opp_b")
    request = _request(tmp_path, seeds=(1,), ticks=10)
    result = EvaluationService().run(request)
    assert result.cells
    for cell in result.cells:
        assert cell.outcome == "win"
        assert cell.subject_seat is not None
        seat_index = ord(cell.subject_seat) - ord("A")
        assert cell.seat_agent_ids[seat_index] == cell.subject_id


def test_capture_and_win_loss_stay_structurally_distinct_fields(three_agents: Path):
    result = EvaluationService().run(_request(three_agents, seeds=(1,)))
    for cell in result.cells:
        # score_opponent/territory_opponent are ill-defined for a 3+
        # entrant cell (more than one "opponent") -- deliberately left
        # None (Phase 2 scope: full per-seat breakdown lives in the cell's
        # own result.json, never duplicated onto these 1v1-shaped fields).
        assert cell.score_opponent is None
        assert cell.territory_opponent is None
        assert cell.score_subject is not None


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def test_identical_group_evaluations_align_cleanly(three_agents: Path):
    """Two independent runs of the identical roster/seed/methodology must
    align every cell exactly -- cardinality is derived from the actual
    matrix (seeds x layouts x seat assignments), never hard-coded, since a
    hard-coded 1v1-shaped expectation (e.g. "one row per opponent") does
    not describe a group evaluation's condition space at all."""

    request = _request(three_agents, seeds=(1,))
    left = EvaluationService().run(_request(three_agents, output_dir=three_agents / "left", seeds=(1,)))
    right = EvaluationService().run(_request(three_agents, output_dir=three_agents / "right", seeds=(1,)))
    expected_cells = len(request.seeds) * len(standard_layouts(len(request.roster_agent_ids))) * len(
        enumerate_seat_assignments(request.roster_agent_ids)
    )
    assert len(left.cells) == len(right.cells) == expected_cells
    aligned = align(adapt_any(left.state_path), adapt_any(right.state_path))
    assert len(aligned.rows) == expected_cells
    assert not aligned.unmatched_left
    assert not aligned.unmatched_right
    assert not aligned.changed_condition
    assert not aligned.ambiguous_duplicate_groups


def test_same_group_roster_with_changed_opponent_source_does_not_strict_align(three_agents: Path):
    left = EvaluationService().run(
        _request(three_agents, output_dir=three_agents / "left", seeds=(1,))
    )
    opponent_source = three_agents / "agents" / "opp_a" / "agent.py"
    opponent_source.write_text(
        opponent_source.read_text(encoding="utf-8").replace(NOP_ACTION, "AgentAction(ActionKind.HALT)"),
        encoding="utf-8",
    )
    right = EvaluationService().run(
        _request(three_agents, output_dir=three_agents / "right", seeds=(1,))
    )

    aligned = align(adapt_any(left.state_path), adapt_any(right.state_path))
    assert not aligned.rows
    assert aligned.denominators.condition_intersection == 0
    assert aligned.ambiguous_duplicate_groups


def test_changed_candidate_source_with_unchanged_group_opponents_remains_comparable(
    three_agents: Path,
):
    left = EvaluationService().run(
        _request(three_agents, output_dir=three_agents / "left", seeds=(1,))
    )
    candidate_source = three_agents / "agents" / "candidate" / "agent.py"
    candidate_source.write_text(
        candidate_source.read_text(encoding="utf-8").replace(NOP_ACTION, "AgentAction(ActionKind.HALT)"),
        encoding="utf-8",
    )
    right = EvaluationService().run(
        _request(three_agents, output_dir=three_agents / "right", seeds=(1,))
    )

    aligned = align(adapt_any(left.state_path), adapt_any(right.state_path))
    assert aligned.candidate_diff is not None
    assert len(aligned.rows) == 18
    assert not aligned.unmatched_left
    assert not aligned.unmatched_right


def test_empty_group_orientation_scope_has_unknown_differentials(three_agents: Path):
    result = EvaluationService().run(_request(three_agents, seeds=(1,)))
    aggregates = all_subject_aggregates("candidate", None, result.cells)
    empty = next(row for row in aggregates if row.orientation_scope == "opponent_first")
    assert empty.matches_played == 0
    assert empty.score_differential_avg is None
    assert empty.territory_differential_avg is None


def test_different_roster_group_evaluations_do_not_align(three_agents: Path):
    _write_nop_agent(three_agents, "opp_c")
    left = EvaluationService().run(
        _request(three_agents, output_dir=three_agents / "left", opponent_ids=("opp_a", "opp_b"), seeds=(1,))
    )
    right = EvaluationService().run(
        _request(three_agents, output_dir=three_agents / "right", opponent_ids=("opp_a", "opp_c"), seeds=(1,))
    )
    aligned = align(adapt_any(left.state_path), adapt_any(right.state_path))
    assert not aligned.rows
    assert aligned.unmatched_left and aligned.unmatched_right


def test_group_and_1v1_evaluations_never_align(three_agents: Path):
    group_result = EvaluationService().run(
        _request(three_agents, output_dir=three_agents / "group", opponent_ids=("opp_a", "opp_b"), seeds=(1,))
    )
    pairwise_result = EvaluationService().run(
        _request(
            three_agents, output_dir=three_agents / "pairwise", opponent_ids=("opp_a",), seeds=(1,), group=False,
        )
    )
    aligned = align(adapt_any(group_result.state_path), adapt_any(pairwise_result.state_path))
    assert not aligned.rows


def test_1v1_comparison_still_works_unaffected(three_agents: Path):
    """Existing 1v1 v2 comparison behavior (Phase 1) is unaffected by the
    group-mode branch in _condition_key -- exercised here as a direct
    regression check."""

    kwargs = {"opponent_ids": ("opp_a",), "seeds": (1,), "group": False}
    left = EvaluationService().run(_request(three_agents, output_dir=three_agents / "left", **kwargs))
    right = EvaluationService().run(_request(three_agents, output_dir=three_agents / "right", **kwargs))
    aligned = align(adapt_any(left.state_path), adapt_any(right.state_path))
    assert len(aligned.rows) > 0
    assert not aligned.unmatched_left
    assert not aligned.unmatched_right


# ---------------------------------------------------------------------------
# History health / schema compatibility
# ---------------------------------------------------------------------------


def test_group_artifact_is_healthy(three_agents: Path):
    """Regression proof for the Phase 1 evaluation_id/condition_fingerprint
    rehash gap discovered and fixed during Phase 2 characterization (the
    v2 adapter's self-consistency health check must mirror
    EvaluationService._evaluation_id's exact per-methodology payload
    shape) -- covers both the v5 (1v1 v2) and v6 (group) cases."""

    from battle_engine.evaluation_history.models import HealthCode

    result = EvaluationService().run(_request(three_agents, seeds=(1,)))
    summary = adapt_any(result.state_path)
    assert HealthCode.HEALTHY in summary.health.codes
    assert HealthCode.PLANNED_IDENTITY_INCONSISTENT not in summary.health.codes
    assert HealthCode.CONDITION_FINGERPRINT_INCONSISTENT not in summary.health.codes


def test_1v1_v2_artifact_is_healthy_regression(three_agents: Path):
    """The specific Phase 1 defect this phase found and fixed: a 1v1 v2
    (schema 5) artifact's health check must not falsely flag
    PLANNED_IDENTITY_INCONSISTENT/CONDITION_FINGERPRINT_INCONSISTENT."""

    from battle_engine.evaluation_history.models import HealthCode

    request = _request(three_agents, opponent_ids=("opp_a",), seeds=(1,), group=False)
    result = EvaluationService().run(request)
    summary = adapt_any(result.state_path)
    assert HealthCode.HEALTHY in summary.health.codes
    assert HealthCode.PLANNED_IDENTITY_INCONSISTENT not in summary.health.codes
    assert HealthCode.CONDITION_FINGERPRINT_INCONSISTENT not in summary.health.codes


def test_historical_pre_group_artifact_recovers_empty_roster(three_agents: Path):
    request = _request(three_agents, opponent_ids=("opp_a",), seeds=(1,), group=False)
    result = EvaluationService().run(request)
    summary = adapt_any(result.state_path)
    assert summary.group.value is False
    assert all(cell.roster.value == () for cell in summary.cells)
