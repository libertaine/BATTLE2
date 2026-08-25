"""v3 Phase 3: controlled ``weights.kill`` evaluation conditions.

Phase 3 exposes one already-identity-bearing scoring condition through the
evaluation path so the offense-payoff experiment can vary it in a controlled
corpus (docs/V3_PHASE3_OFFENSE_PAYOFF_CHARACTERIZATION.md). The governing
invariant every test here defends is the same one Phase 0 established for
``arena_size``/``instr_per_tick``: **omission changes nothing**. An
evaluation that does not name a kill weight must behave, identify, and
persist exactly as it did before Phase 3.

Mirrors ``test_v3_phase0_evaluation_conditions.py`` structurally -- see that
module for the surrounding precedent this extends.
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


def test_effective_conditions_omitted_matches_pre_phase3_weights() -> None:
    """Omitting ``kill_weight`` reproduces ``Config()``'s own default ``Weights``."""

    defaults = Config()
    conditions = effective_conditions_for(400, 1)
    assert conditions.weights == asdict(defaults.weights)


def test_effective_conditions_explicit_default_kill_weight_is_byte_identical_to_omission() -> None:
    omitted = effective_conditions_for(400, 1)
    explicit = effective_conditions_for(400, 1, kill_weight=Config().weights.kill)
    assert omitted == explicit
    assert stable_id("evaluation-conditions", asdict(omitted)) == stable_id(
        "evaluation-conditions", asdict(explicit)
    )


def test_non_default_kill_weight_changes_the_conditions_fingerprint() -> None:
    omitted = asdict(effective_conditions_for(400, 1))
    varied = asdict(effective_conditions_for(400, 1, kill_weight=1600.0))
    ids = {stable_id("evaluation-conditions", payload) for payload in (omitted, varied)}
    assert len(ids) == 2


def test_kill_weight_only_changes_the_kill_term() -> None:
    """The other three ``Weights`` fields must stay at their own defaults."""

    defaults = Config().weights
    conditions = effective_conditions_for(400, 1, kill_weight=1600.0)
    assert conditions.weights["kill"] == 1600.0
    assert conditions.weights["alive"] == defaults.alive
    assert conditions.weights["territory"] == defaults.territory
    assert conditions.weights["territory_bucket"] == defaults.territory_bucket


def test_request_resolved_kill_weight_falls_back_to_config_default(tmp_path: Path) -> None:
    defaults = Config()
    request = _request(tmp_path)
    assert request.resolved_kill_weight == defaults.weights.kill

    explicit = _request(tmp_path, kill_weight=1600.0)
    assert explicit.resolved_kill_weight == 1600.0


def test_omitted_kill_weight_preserves_evaluation_id(two_agents: Path) -> None:
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
        kill_weight=Config().weights.kill,
    )
    assert omitted_id == explicit_default_id


def test_non_default_kill_weight_changes_evaluation_id(two_agents: Path) -> None:
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
        kill_weight=1600.0,
    )
    assert baseline_id != varied_id


def test_distinct_kill_weights_produce_distinct_evaluation_ids(two_agents: Path) -> None:
    service = EvaluationService()
    ids = set()
    for weight in (5.0, 400.0, 1600.0, 3200.0):
        _specs, evaluation_id = service.preflight(
            candidate_id="candidate",
            opponent_ids=("opponent",),
            seeds=(1,),
            ticks=10,
            data_root=two_agents,
            both_orientations=False,
            kill_weight=weight,
        )
        ids.add(evaluation_id)
    assert len(ids) == 4


# ---------------------------------------------------------------------------
# Validation (fail closed)
# ---------------------------------------------------------------------------


def test_negative_kill_weight_is_rejected(two_agents: Path) -> None:
    service = EvaluationService()
    with pytest.raises(EvaluationConfigurationError, match="kill-weight"):
        service.preflight(
            candidate_id="candidate",
            opponent_ids=("opponent",),
            seeds=(1,),
            ticks=10,
            data_root=two_agents,
            kill_weight=-1.0,
        )


def test_zero_kill_weight_is_accepted(two_agents: Path) -> None:
    """K0-adjacent boundary: zero has a meaningful interpretation (no reward), unlike negative."""

    service = EvaluationService()
    _specs, evaluation_id = service.preflight(
        candidate_id="candidate",
        opponent_ids=("opponent",),
        seeds=(1,),
        ticks=10,
        data_root=two_agents,
        kill_weight=0.0,
    )
    assert evaluation_id


# ---------------------------------------------------------------------------
# Propagation into real execution
# ---------------------------------------------------------------------------


def test_explicit_kill_weight_reaches_the_executed_match(two_agents: Path) -> None:
    """End-to-end: the persisted result must record the requested weight."""

    request = _request(
        two_agents,
        ruleset_id=BYTEFRAY_RULESET_V2_ID,
        seeds=(1,),
        kill_weight=1600.0,
        output_dir=two_agents / "out",
    )
    result = EvaluationService().run(request)
    assert result.cells
    assert not result.failed_cells

    state = json.loads((request.output_dir / "evaluation.json").read_text(encoding="utf-8"))
    assert state["effective_conditions"]["weights"]["kill"] == 1600.0

    result_paths = sorted(request.output_dir.rglob("result.json"))
    assert result_paths
    for path in result_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        reproducibility = payload.get("reproducibility") or payload["result"]["reproducibility"]
        assert reproducibility["weights"]["kill"] == 1600.0


def test_group_kill_weight_reaches_the_executed_match(three_agents: Path) -> None:
    request = _request(
        three_agents,
        opponent_ids=("opponent", "third"),
        ruleset_id=BYTEFRAY_RULESET_V2_ID,
        group=True,
        both_orientations=True,
        seeds=(1,),
        kill_weight=400.0,
        output_dir=three_agents / "out",
    )
    result = EvaluationService().run(request)
    assert result.cells
    assert not result.failed_cells
    for path in sorted(request.output_dir.rglob("result.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        reproducibility = payload.get("reproducibility") or payload["result"]["reproducibility"]
        assert reproducibility["weights"]["kill"] == 400.0


def test_omitted_kill_weight_reaches_the_executed_match_as_the_shipped_default(
    two_agents: Path,
) -> None:
    request = _request(
        two_agents,
        ruleset_id=BYTEFRAY_RULESET_V2_ID,
        seeds=(1,),
        output_dir=two_agents / "out",
    )
    EvaluationService().run(request)
    for path in sorted(request.output_dir.rglob("result.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        reproducibility = payload.get("reproducibility") or payload["result"]["reproducibility"]
        assert reproducibility["weights"]["kill"] == Config().weights.kill


# ---------------------------------------------------------------------------
# Determinism, resume, and parallel-worker equivalence
# ---------------------------------------------------------------------------


def _cell_signature(output_dir: Path) -> list[tuple[str, str, str]]:
    state = json.loads((output_dir / "evaluation.json").read_text(encoding="utf-8"))
    return sorted(
        (cell["schedule_id"], str(cell.get("match_id")), str(cell.get("outcome")))
        for cell in state["cells"]
    )


def test_non_default_kill_weight_evaluation_is_deterministic(two_agents: Path) -> None:
    first = _request(
        two_agents,
        ruleset_id=BYTEFRAY_RULESET_V2_ID,
        kill_weight=1600.0,
        output_dir=two_agents / "run-a",
    )
    second = _request(
        two_agents,
        ruleset_id=BYTEFRAY_RULESET_V2_ID,
        kill_weight=1600.0,
        output_dir=two_agents / "run-b",
    )
    EvaluationService().run(first)
    EvaluationService().run(second)
    assert _cell_signature(first.output_dir) == _cell_signature(second.output_dir)


def test_non_default_kill_weight_resumes_without_identity_mismatch(two_agents: Path) -> None:
    """Resume recomputes the expected ``match_id`` from live specs -- it must
    rebuild the same non-default ``Config`` (including ``weights``) the
    original run executed under, or every completed cell falsely reports
    ``resumed_result_mismatch``."""

    request = _request(
        two_agents,
        ruleset_id=BYTEFRAY_RULESET_V2_ID,
        kill_weight=1600.0,
        output_dir=two_agents / "run-resume",
    )
    first = EvaluationService().run(request)
    assert not first.corrupted_cells

    resumed = EvaluationService().run(request)
    assert not resumed.corrupted_cells
    assert not resumed.failed_cells
    assert _cell_signature(request.output_dir)


def test_parallel_workers_reproduce_serial_results_at_a_non_default_kill_weight(
    two_agents: Path,
) -> None:
    serial = _request(
        two_agents,
        ruleset_id=BYTEFRAY_RULESET_V2_ID,
        kill_weight=1600.0,
        output_dir=two_agents / "serial",
    )
    parallel = _request(
        two_agents,
        ruleset_id=BYTEFRAY_RULESET_V2_ID,
        kill_weight=1600.0,
        workers=3,
        output_dir=two_agents / "parallel",
    )
    EvaluationService().run(serial)
    EvaluationService().run(parallel)
    assert _cell_signature(serial.output_dir) == _cell_signature(parallel.output_dir)


# ---------------------------------------------------------------------------
# Human-readable disclosure
# ---------------------------------------------------------------------------


def _show_output(evaluation_json: Path, capsys) -> str:
    from battle_engine.evaluation_history.cli import _print_show
    from battle_engine.evaluation_history.discovery import adapt_any

    _print_show(adapt_any(evaluation_json), verified=None, verify_error=None)
    return capsys.readouterr().out


def test_show_stays_silent_at_default_kill_weight(two_agents: Path, capsys) -> None:
    request = _request(
        two_agents, ruleset_id=BYTEFRAY_RULESET_V2_ID, output_dir=two_agents / "default-run"
    )
    EvaluationService().run(request)
    output = _show_output(request.output_dir / "evaluation.json", capsys)
    assert "kill weight:" not in output


def test_show_discloses_non_default_kill_weight(two_agents: Path, capsys) -> None:
    request = _request(
        two_agents,
        ruleset_id=BYTEFRAY_RULESET_V2_ID,
        kill_weight=1600.0,
        output_dir=two_agents / "varied-run",
    )
    EvaluationService().run(request)
    output = _show_output(request.output_dir / "evaluation.json", capsys)
    assert "kill weight: 1600" in output
    assert "(non-default)" in output


def test_live_matrix_print_discloses_non_default_kill_weight(two_agents: Path, capsys) -> None:
    from battle_engine.agent_evaluation import _print_matrix

    request = _request(
        two_agents,
        ruleset_id=BYTEFRAY_RULESET_V2_ID,
        kill_weight=1600.0,
        output_dir=two_agents / "matrix-print",
    )
    _print_matrix(request, build_matrix(request, "evaluation-test"))
    output = capsys.readouterr().out
    assert "kill weight: 1600" in output
    # Untouched siblings stay silent even when kill weight is varied.
    assert "arena size:" not in output
    assert "action budget/tick:" not in output


# ---------------------------------------------------------------------------
# CLI argument wiring
# ---------------------------------------------------------------------------


def test_cli_parser_accepts_kill_weight_flag() -> None:
    from battle_engine.agent_evaluation import _parser

    parser = _parser()
    args = parser.parse_args(["a", "--opponents", "b", "--kill-weight", "1600"])
    assert args.kill_weight == 1600.0


def test_cli_parser_defaults_kill_weight_to_none() -> None:
    from battle_engine.agent_evaluation import _parser

    parser = _parser()
    args = parser.parse_args(["a", "--opponents", "b"])
    assert args.kill_weight is None
