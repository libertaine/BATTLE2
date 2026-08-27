"""Beta3 Phase 4 Qt-free Designer group-evaluation integration coverage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from battle_engine.agent_evaluation import EvaluationService, build_matrix
from battle_engine.rules import BYTEFRAY_RULESET_ID
from battle_engine.ruleset_policy import BYTEFRAY_RULESET_V2_ID

from app.services.designer_workflows import (
    EVALUATION_MODE_GROUP,
    EVALUATION_MODE_PAIRWISE,
    DesignerValidationError,
    build_designer_evaluate_command,
    build_designer_evaluate_command_from_plan,
    build_designer_evaluation_plan,
    read_evaluation_presentation,
)


def _write_nop_agent(root: Path, agent_id: str) -> None:
    directory = root / "agents" / agent_id
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text(
        json.dumps(
            {
                "kind": "python",
                "api_version": 1,
                "entrypoint": "agent.py:create_agent",
                "version": "1.0",
            }
        ),
        encoding="utf-8",
    )
    (directory / "agent.py").write_text(
        """from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, context): pass
    def act(self, observation): return AgentAction(ActionKind.NOP)
def create_agent(): return Agent()
""",
        encoding="utf-8",
    )


def _plan(root: Path, opponents: tuple[str, ...], **overrides):
    values = {
        "candidate_id": "focus",
        "baseline_id": None,
        "opponent_ids": opponents,
        "seeds_text": "7",
        "seed_range_text": "",
        "ticks": 3,
        "output_dir": root / "evaluation",
        "data_root": root,
        "mode": EVALUATION_MODE_GROUP,
    }
    values.update(overrides)
    return build_designer_evaluation_plan(**values)


@pytest.mark.parametrize(
    ("opponents", "expected_cells", "expected_assignments"),
    [
        (("a", "b"), 18, 6),
        (("a", "b", "c"), 72, 24),
        (("a", "b", "c", "d"), 360, 120),
    ],
)
def test_group_plan_uses_canonical_matrix_for_three_four_and_five_entrants(
    tmp_path: Path,
    opponents: tuple[str, ...],
    expected_cells: int,
    expected_assignments: int,
) -> None:
    for agent_id in ("focus", *opponents):
        _write_nop_agent(tmp_path, agent_id)

    plan = _plan(tmp_path, opponents)
    canonical = build_matrix(plan.request, plan.evaluation_id)

    assert plan.request.group is True
    assert plan.request.ruleset_id == BYTEFRAY_RULESET_V2_ID
    assert len(plan.matrix) == len(canonical) == expected_cells
    assert plan.seat_assignment_count == expected_assignments
    assert tuple(cell.schedule_id for cell in plan.matrix) == tuple(
        cell.schedule_id for cell in canonical
    )
    assert f"Planned cells: {expected_cells}" in plan.preview_text()


def test_group_plan_preserves_duplicate_identifiers_and_self_play(tmp_path: Path) -> None:
    _write_nop_agent(tmp_path, "focus")
    _write_nop_agent(tmp_path, "other")

    plan = _plan(tmp_path, ("focus", "other"))
    command = build_designer_evaluate_command_from_plan(plan, preset_name="ignored-in-group")

    assert plan.request.roster_agent_ids == ("focus", "focus", "other")
    assert plan.seat_assignment_count == 3
    assert len(plan.matrix) == 9
    assert "Self-play multiplicity: focus ×2" in plan.preview_text()
    assert command[command.index("--opponents") + 1] == "focus,other"
    assert "--group" in command
    assert command[command.index("--ruleset") + 1] == BYTEFRAY_RULESET_V2_ID
    assert "--single-orientation" not in command
    assert "--baseline" not in command
    assert "--preset" not in command


def test_group_plan_workers_default_omits_flag_and_never_affects_identity(tmp_path: Path) -> None:
    """v3.0 Phase 4: GUI worker-count parity for the group evaluation path
    -- ``--workers`` is only appended when non-default, and, being pure
    execution machinery, must never change the plan's ``evaluation_id`` or
    matrix (mirrors ``EvaluationRequest.workers``'s own identity guarantee,
    already covered end-to-end for the request/CLI layer by
    ``test_v3_phase0_evaluation_conditions.test_parallel_workers_reproduce_
    serial_results``)."""

    _write_nop_agent(tmp_path, "focus")
    _write_nop_agent(tmp_path, "other")

    serial = _plan(tmp_path, ("focus", "other"))
    assert serial.request.workers == 1
    serial_command = build_designer_evaluate_command_from_plan(serial)
    assert "--workers" not in serial_command

    parallel = _plan(tmp_path, ("focus", "other"), workers=4)
    assert parallel.request.workers == 4
    parallel_command = build_designer_evaluate_command_from_plan(parallel)
    assert parallel_command[parallel_command.index("--workers") + 1] == "4"

    assert parallel.evaluation_id == serial.evaluation_id
    assert tuple(cell.schedule_id for cell in parallel.matrix) == tuple(
        cell.schedule_id for cell in serial.matrix
    )


def test_group_plan_rejects_invalid_roster_and_baseline(tmp_path: Path) -> None:
    for agent_id in ("focus", "a", "b", "baseline"):
        _write_nop_agent(tmp_path, agent_id)

    with pytest.raises(DesignerValidationError, match="at least two roster members"):
        _plan(tmp_path, ("a",))
    with pytest.raises(DesignerValidationError, match="does not support --baseline"):
        _plan(tmp_path, ("a", "b"), baseline_id="baseline")


def test_group_plan_default_seeds_match_ruleset_v2_cli_default(tmp_path: Path) -> None:
    for agent_id in ("focus", "a", "b"):
        _write_nop_agent(tmp_path, agent_id)
    plan = _plan(tmp_path, ("a", "b"), seeds_text="")
    assert plan.request.seeds == (1, 2, 3, 4, 5)
    assert len(plan.matrix) == 90


def test_real_group_execution_round_trips_through_designer_presentation(tmp_path: Path) -> None:
    for agent_id in ("focus", "a", "b"):
        _write_nop_agent(tmp_path, agent_id)
    plan = _plan(tmp_path, ("a", "b"), ticks=2)

    result = EvaluationService().run(plan.request)
    presentation = read_evaluation_presentation(result.state_path)

    assert len(result.cells) == len(plan.matrix) == 18
    assert presentation.group is True
    assert presentation.candidate_id == "focus"
    assert presentation.roster_agent_ids == tuple(sorted(("focus", "a", "b")))
    assert presentation.rules_compatibility_id == BYTEFRAY_RULESET_V2_ID
    assert presentation.analysis is None
    assert presentation.behavior is None
    assert presentation.group_analysis is not None
    assert presentation.group_analysis.cells_analyzed == 18
    assert all(cell.is_group for cell in presentation.cells)
    assert {cell.layout_id for cell in presentation.cells} == {
        "spread",
        "spread-shifted",
        "close",
    }


# ---------------------------------------------------------------------------
# v3.0.0-alpha2: explicit pairwise Ruleset selection
# ---------------------------------------------------------------------------


def _pairwise_plan(root: Path, **overrides):
    values = {
        "candidate_id": "focus",
        "baseline_id": None,
        "opponent_ids": ("rival",),
        "seeds_text": "7",
        "seed_range_text": "",
        "ticks": 3,
        "output_dir": root / "evaluation",
        "data_root": root,
        "mode": EVALUATION_MODE_PAIRWISE,
    }
    values.update(overrides)
    return build_designer_evaluation_plan(**values)


def test_pairwise_omitted_ruleset_preserves_historical_identity(tmp_path: Path) -> None:
    """``None`` must stay byte-identical to the explicit v1 identity.

    ``resolve_evaluation_ruleset_id`` maps both to the same
    ``rules_compatibility_id``, so a caller that does not pass a Ruleset --
    including a Designer dialog double predating the alpha2 selector --
    lands on exactly the evaluation identity it always did. If this ever
    diverges, every previously written pairwise evaluation stops resuming.
    """

    _write_nop_agent(tmp_path, "focus")
    _write_nop_agent(tmp_path, "rival")

    omitted = _pairwise_plan(tmp_path, ruleset_id=None)
    explicit_v1 = _pairwise_plan(tmp_path, ruleset_id=BYTEFRAY_RULESET_ID)

    assert omitted.evaluation_id == explicit_v1.evaluation_id
    assert (
        omitted.request.resolved_rules_compatibility_id
        == explicit_v1.request.resolved_rules_compatibility_id
    )


def test_pairwise_v2_is_a_distinct_evaluation_identity(tmp_path: Path) -> None:
    """Selecting v2 is a genuinely different evaluation, not a relabelling."""

    _write_nop_agent(tmp_path, "focus")
    _write_nop_agent(tmp_path, "rival")

    v1 = _pairwise_plan(tmp_path, ruleset_id=BYTEFRAY_RULESET_ID)
    v2 = _pairwise_plan(tmp_path, ruleset_id=BYTEFRAY_RULESET_V2_ID)

    assert v1.evaluation_id != v2.evaluation_id
    assert v2.request.is_v2_methodology
    assert not v1.request.is_v2_methodology


def test_pairwise_command_sends_the_planned_ruleset_explicitly(tmp_path: Path) -> None:
    """The launched command must match the Ruleset the plan was hashed with.

    The Designer names each run's output directory after ``evaluation_id``,
    so a command that resolved a different Ruleset than the plan would write
    into a directory named for an evaluation it is not running.
    """

    _write_nop_agent(tmp_path, "focus")
    _write_nop_agent(tmp_path, "rival")

    for ruleset in (BYTEFRAY_RULESET_ID, BYTEFRAY_RULESET_V2_ID):
        plan = _pairwise_plan(tmp_path, ruleset_id=ruleset)
        command = build_designer_evaluate_command_from_plan(plan)
        assert "--ruleset" in command
        assert command[command.index("--ruleset") + 1] == ruleset
        assert "--group" not in command


def test_group_mode_still_forces_ruleset_v2(tmp_path: Path) -> None:
    """Group evaluation is Ruleset-v2-only and ignores any passed value."""

    for agent_id in ("focus", "rival", "third"):
        _write_nop_agent(tmp_path, agent_id)

    plan = _plan(tmp_path, ("rival", "third"), ruleset_id=BYTEFRAY_RULESET_ID)
    assert plan.request.resolved_rules_compatibility_id == BYTEFRAY_RULESET_V2_ID
    command = build_designer_evaluate_command_from_plan(plan)
    assert "--group" in command
    assert command[command.index("--ruleset") + 1] == BYTEFRAY_RULESET_V2_ID


def test_explicit_pairwise_command_builder_omits_ruleset_when_unset(tmp_path: Path) -> None:
    """The non-plan pairwise builder stays argument-identical when unset."""

    without = build_designer_evaluate_command(
        candidate_id="focus",
        baseline_id=None,
        opponent_ids=("rival",),
        seeds_text="1",
        seed_range_text="",
        ticks=5,
        output_dir=tmp_path / "out",
    )
    assert "--ruleset" not in without

    with_v2 = build_designer_evaluate_command(
        candidate_id="focus",
        baseline_id=None,
        opponent_ids=("rival",),
        seeds_text="1",
        seed_range_text="",
        ticks=5,
        output_dir=tmp_path / "out",
        ruleset_id=BYTEFRAY_RULESET_V2_ID,
    )
    assert with_v2[with_v2.index("--ruleset") + 1] == BYTEFRAY_RULESET_V2_ID
