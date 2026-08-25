"""v3 Phase 0D/0I: controlled ``arena_size``/``instr_per_tick`` evaluation conditions.

Phase 0 exposes two already-identity-bearing execution conditions through
the evaluation path so later v3 phases can vary them in controlled
experiments (docs/V3_PHASE0_RESEARCH_BASELINE.md). The governing invariant
every test here defends is **omission changes nothing**: an evaluation that
does not name these values must behave, identify, and persist exactly as it
did before Phase 0.

See ``test_agent_evaluation_v2.py`` for the surrounding v2 identity
behavior these build on.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest
from battle_engine.agent_evaluation import (
    BYTEFRAY_RULESET_V2_ID,
    EvaluationConfigurationError,
    EvaluationRequest,
    EvaluationService,
    build_matrix,
    effective_conditions_for,
    standard_layouts,
    standard_placements,
)
from battle_engine.config import Config
from battle_engine.result_model import stable_id

NOP_ACTION = "AgentAction(ActionKind.NOP)"


def _write_python_agent(root: Path, name: str, action: str = NOP_ACTION) -> Path:
    directory = root / "agents" / name
    directory.mkdir(parents=True, exist_ok=True)
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


def _request(tmp_path: Path, **overrides) -> EvaluationRequest:
    defaults = {
        "candidate_id": "candidate",
        "opponent_ids": ("opponent",),
        "seeds": (1,),
        "output_dir": tmp_path / "eval-out",
        "ticks": 10,
        "data_root": tmp_path,
        "both_orientations": False,
    }
    defaults.update(overrides)
    return EvaluationRequest(**defaults)


@pytest.fixture()
def two_agents(tmp_path: Path) -> Path:
    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    return tmp_path


@pytest.fixture()
def three_agents(tmp_path: Path) -> Path:
    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    _write_python_agent(tmp_path, "third")
    return tmp_path


# ---------------------------------------------------------------------------
# Defaults: omission must change nothing
# ---------------------------------------------------------------------------


def test_effective_conditions_omitted_matches_pre_phase0_literals() -> None:
    """Omitting both parameters reproduces the exact values this function hardcoded."""

    defaults = Config()
    conditions = effective_conditions_for(400, 1)
    assert conditions.arena_size == defaults.arena_size
    assert conditions.action_budget == defaults.instr_per_tick


def test_effective_conditions_explicit_defaults_are_byte_identical_to_omission() -> None:
    """Naming the default value must not be a different evaluation from omitting it.

    If these diverged, the fingerprint below would split one experimental
    condition into two incomparable ones purely on how it was spelled.
    """

    omitted = effective_conditions_for(400, 1)
    explicit = effective_conditions_for(400, 1, arena_size=4096, instr_per_tick=8)
    assert omitted == explicit
    assert stable_id("evaluation-conditions", asdict(omitted)) == stable_id(
        "evaluation-conditions", asdict(explicit)
    )


def test_non_default_conditions_change_the_conditions_fingerprint() -> None:
    omitted = asdict(effective_conditions_for(400, 1))
    smaller = asdict(effective_conditions_for(400, 1, arena_size=1024))
    cheaper = asdict(effective_conditions_for(400, 1, instr_per_tick=4))
    ids = {
        stable_id("evaluation-conditions", payload) for payload in (omitted, smaller, cheaper)
    }
    assert len(ids) == 3


def test_request_resolved_properties_fall_back_to_config_defaults(tmp_path: Path) -> None:
    defaults = Config()
    request = _request(tmp_path)
    assert request.resolved_arena_size == defaults.arena_size
    assert request.resolved_instr_per_tick == defaults.instr_per_tick

    explicit = _request(tmp_path, arena_size=1024, instr_per_tick=4)
    assert explicit.resolved_arena_size == 1024
    assert explicit.resolved_instr_per_tick == 4


def test_omitted_conditions_preserve_evaluation_id(two_agents: Path) -> None:
    """The headline compatibility guarantee: no historical evaluation_id moves."""

    service = EvaluationService()
    _specs, omitted_id = service.preflight(
        candidate_id="candidate",
        opponent_ids=("opponent",),
        seeds=(1,),
        ticks=10,
        data_root=two_agents,
        both_orientations=False,
    )
    _specs, explicit_default_id = service.preflight(
        candidate_id="candidate",
        opponent_ids=("opponent",),
        seeds=(1,),
        ticks=10,
        data_root=two_agents,
        both_orientations=False,
        arena_size=Config().arena_size,
        instr_per_tick=Config().instr_per_tick,
    )
    assert omitted_id == explicit_default_id


def test_non_default_conditions_change_evaluation_id(two_agents: Path) -> None:
    service = EvaluationService()
    _specs, baseline_id = service.preflight(
        candidate_id="candidate",
        opponent_ids=("opponent",),
        seeds=(1,),
        ticks=10,
        data_root=two_agents,
        both_orientations=False,
    )
    _specs, varied_id = service.preflight(
        candidate_id="candidate",
        opponent_ids=("opponent",),
        seeds=(1,),
        ticks=10,
        data_root=two_agents,
        both_orientations=False,
        arena_size=1024,
        instr_per_tick=4,
    )
    assert baseline_id != varied_id


# ---------------------------------------------------------------------------
# Placement/layout derivation
# ---------------------------------------------------------------------------


def test_standard_placements_are_pure_functions_of_arena_size() -> None:
    assert standard_placements(1024) == standard_placements(1024)
    assert standard_placements(1024) != standard_placements(4096)
    for placement in standard_placements(1024):
        assert 0 <= placement.subject_start < 1024
        assert 0 <= placement.opponent_start < 1024


def test_v2_matrix_placements_follow_the_requested_arena_size(two_agents: Path) -> None:
    """A non-default arena must not emit start addresses outside itself.

    ``MatchEntrant.python`` wraps a start modulo arena size, so a matrix
    built from default-derived placements against a 1024-cell arena would
    silently collapse ``opposed`` (0, 2048) onto (0, 0) -- two entrants in
    the same core, measuring collision rather than the variable under test.
    """

    request = _request(
        two_agents,
        ruleset_id=BYTEFRAY_RULESET_V2_ID,
        arena_size=1024,
        output_dir=two_agents / "out",
    )
    matrix = build_matrix(request, "evaluation-test")
    assert matrix
    expected = {
        (placement.placement_id, placement.subject_start, placement.opponent_start)
        for placement in standard_placements(1024)
    }
    actual = {(cell.placement_id, cell.subject_start, cell.opponent_start) for cell in matrix}
    assert actual == expected
    for cell in matrix:
        assert cell.subject_start < 1024
        assert cell.opponent_start < 1024
        assert cell.subject_start != cell.opponent_start


def test_group_matrix_layouts_follow_the_requested_arena_size(three_agents: Path) -> None:
    request = _request(
        three_agents,
        opponent_ids=("opponent", "third"),
        ruleset_id=BYTEFRAY_RULESET_V2_ID,
        group=True,
        both_orientations=True,
        arena_size=2048,
        output_dir=three_agents / "out",
    )
    matrix = build_matrix(request, "evaluation-test")
    assert matrix
    expected = {layout.seat_starts for layout in standard_layouts(3, 2048)}
    assert {cell.seat_starts for cell in matrix} == expected
    for cell in matrix:
        assert all(start < 2048 for start in cell.seat_starts)


# ---------------------------------------------------------------------------
# Validation (fail closed)
# ---------------------------------------------------------------------------


def test_arena_too_small_for_the_roster_is_rejected(two_agents: Path) -> None:
    service = EvaluationService()
    with pytest.raises(EvaluationConfigurationError, match="too small"):
        service.preflight(
            candidate_id="candidate",
            opponent_ids=("opponent",),
            seeds=(1,),
            ticks=10,
            data_root=two_agents,
            arena_size=16,
        )


def test_group_arena_bound_scales_with_roster_size(three_agents: Path) -> None:
    """A 3-entrant roster needs a larger minimum arena than a 1v1 pair."""

    service = EvaluationService()
    with pytest.raises(EvaluationConfigurationError, match="too small"):
        service.preflight(
            candidate_id="candidate",
            opponent_ids=("opponent", "third"),
            seeds=(1,),
            ticks=10,
            data_root=three_agents,
            ruleset_id=BYTEFRAY_RULESET_V2_ID,
            group=True,
            arena_size=40,
        )


def test_non_positive_action_budget_is_rejected(two_agents: Path) -> None:
    service = EvaluationService()
    with pytest.raises(EvaluationConfigurationError, match="instr-per-tick"):
        service.preflight(
            candidate_id="candidate",
            opponent_ids=("opponent",),
            seeds=(1,),
            ticks=10,
            data_root=two_agents,
            instr_per_tick=0,
        )


# ---------------------------------------------------------------------------
# Propagation into real execution
# ---------------------------------------------------------------------------


def test_explicit_conditions_reach_the_executed_match(two_agents: Path) -> None:
    """End-to-end: the persisted result must record the requested conditions."""

    request = _request(
        two_agents,
        ruleset_id=BYTEFRAY_RULESET_V2_ID,
        seeds=(1,),
        arena_size=1024,
        instr_per_tick=4,
        output_dir=two_agents / "out",
    )
    result = EvaluationService().run(request)
    assert result.cells
    assert not result.failed_cells

    state = json.loads((request.output_dir / "evaluation.json").read_text(encoding="utf-8"))
    assert state["effective_conditions"]["arena_size"] == 1024
    assert state["effective_conditions"]["action_budget"] == 4

    result_paths = sorted(request.output_dir.rglob("result.json"))
    assert result_paths
    for path in result_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        reproducibility = payload.get("reproducibility") or payload["result"]["reproducibility"]
        assert reproducibility["arena_size"] == 1024
        assert reproducibility["action_budget"] == 4


def test_group_conditions_reach_the_executed_match(three_agents: Path) -> None:
    request = _request(
        three_agents,
        opponent_ids=("opponent", "third"),
        ruleset_id=BYTEFRAY_RULESET_V2_ID,
        group=True,
        both_orientations=True,
        seeds=(1,),
        arena_size=2048,
        instr_per_tick=4,
        output_dir=three_agents / "out",
    )
    result = EvaluationService().run(request)
    assert result.cells
    assert not result.failed_cells
    for path in sorted(request.output_dir.rglob("result.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        reproducibility = payload.get("reproducibility") or payload["result"]["reproducibility"]
        assert reproducibility["arena_size"] == 2048
        assert reproducibility["action_budget"] == 4


# ---------------------------------------------------------------------------
# Determinism, resume, and parallel-worker equivalence
# ---------------------------------------------------------------------------


def _cell_signature(output_dir: Path) -> list[tuple[str, str, str]]:
    state = json.loads((output_dir / "evaluation.json").read_text(encoding="utf-8"))
    return sorted(
        (cell["schedule_id"], str(cell.get("match_id")), str(cell.get("outcome")))
        for cell in state["cells"]
    )


def test_non_default_evaluation_is_deterministic(two_agents: Path) -> None:
    """Requirement 7 of Phase 0's final validation: a non-default configuration
    must reproduce exactly from its own persisted inputs."""

    first = _request(
        two_agents,
        ruleset_id=BYTEFRAY_RULESET_V2_ID,
        arena_size=1024,
        instr_per_tick=4,
        output_dir=two_agents / "run-a",
    )
    second = _request(
        two_agents,
        ruleset_id=BYTEFRAY_RULESET_V2_ID,
        arena_size=1024,
        instr_per_tick=4,
        output_dir=two_agents / "run-b",
    )
    EvaluationService().run(first)
    EvaluationService().run(second)
    assert _cell_signature(first.output_dir) == _cell_signature(second.output_dir)


def test_non_default_evaluation_resumes_without_identity_mismatch(two_agents: Path) -> None:
    """Resume recomputes the expected ``match_id`` from live specs -- it must
    rebuild the same non-default ``Config`` the original run executed under,
    or every completed cell falsely reports ``resumed_result_mismatch``."""

    request = _request(
        two_agents,
        ruleset_id=BYTEFRAY_RULESET_V2_ID,
        arena_size=1024,
        instr_per_tick=4,
        output_dir=two_agents / "run-resume",
    )
    first = EvaluationService().run(request)
    assert not first.corrupted_cells

    resumed = EvaluationService().run(request)
    assert not resumed.corrupted_cells
    assert not resumed.failed_cells
    assert _cell_signature(request.output_dir)


def test_parallel_workers_reproduce_serial_results(two_agents: Path) -> None:
    serial = _request(
        two_agents,
        ruleset_id=BYTEFRAY_RULESET_V2_ID,
        arena_size=1024,
        instr_per_tick=4,
        output_dir=two_agents / "serial",
    )
    parallel = _request(
        two_agents,
        ruleset_id=BYTEFRAY_RULESET_V2_ID,
        arena_size=1024,
        instr_per_tick=4,
        workers=3,
        output_dir=two_agents / "parallel",
    )
    EvaluationService().run(serial)
    EvaluationService().run(parallel)
    assert _cell_signature(serial.output_dir) == _cell_signature(parallel.output_dir)


# ---------------------------------------------------------------------------
# Human-readable disclosure (Phase 0D/0E)
# ---------------------------------------------------------------------------


def _show_output(evaluation_json: Path, capsys) -> str:
    from battle_engine.evaluation_history.cli import _print_show
    from battle_engine.evaluation_history.discovery import adapt_any

    _print_show(adapt_any(evaluation_json), verified=None, verify_error=None)
    return capsys.readouterr().out


def test_show_stays_silent_at_default_conditions(two_agents: Path, capsys) -> None:
    """Every historical artifact's `show` output must be unchanged."""

    request = _request(
        two_agents, ruleset_id=BYTEFRAY_RULESET_V2_ID, output_dir=two_agents / "default-run"
    )
    EvaluationService().run(request)
    output = _show_output(request.output_dir / "evaluation.json", capsys)
    assert "arena size:" not in output
    assert "action budget/tick:" not in output


def test_show_discloses_non_default_conditions(two_agents: Path, capsys) -> None:
    """A non-default artifact must not read as if it ran at defaults."""

    request = _request(
        two_agents,
        ruleset_id=BYTEFRAY_RULESET_V2_ID,
        arena_size=1024,
        instr_per_tick=4,
        output_dir=two_agents / "varied-run",
    )
    EvaluationService().run(request)
    output = _show_output(request.output_dir / "evaluation.json", capsys)
    assert "arena size: 1024 (non-default)" in output
    assert "action budget/tick: 4 (non-default)" in output


def test_live_matrix_print_discloses_non_default_conditions(two_agents: Path, capsys) -> None:
    from battle_engine.agent_evaluation import _print_matrix

    request = _request(
        two_agents,
        ruleset_id=BYTEFRAY_RULESET_V2_ID,
        arena_size=1024,
        output_dir=two_agents / "matrix-print",
    )
    _print_matrix(request, build_matrix(request, "evaluation-test"))
    output = capsys.readouterr().out
    assert "arena size: 1024 (non-default)" in output
    # Untouched default stays silent even when its sibling is varied.
    assert "action budget/tick:" not in output
