"""Coverage for the v0.6.1 bundled default Python (Agent API v1) agents.

Claimer, Strider, Hunter, Wanderer, and Adaptive are shipped as starter
agents (``battle_engine.starters.STARTER_AGENT_NAMES``) alongside the
existing native VM starters. This module checks the structural properties
every shipped agent is required to have -- clean discovery, successful
validation, and successful match completion against a variety of
opponents and seeds -- without asserting any particular agent always wins
a particular seed (see AGENTS.md: prefer structural correctness over
encoding incidental game outcomes).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from battle_engine.agent_evaluation import EvaluationRequest, EvaluationService
from battle_engine.agent_test import DevelopmentTestOutcome
from battle_engine.agent_test import test_agent as run_development_test
from battle_engine.agent_validation import ValidationResult, validate_agent
from battle_engine.agents import discover_agents
from battle_engine.starters import STARTER_AGENT_NAMES, ensure_starter_agents

DEFAULT_PYTHON_AGENT_NAMES = ("claimer", "strider", "hunter", "wanderer", "adaptive")


def _resource_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    ensure_starter_agents(resource_root=_resource_root(), data_root=tmp_path)
    return tmp_path


def test_default_python_agent_names_are_starter_agents() -> None:
    for name in DEFAULT_PYTHON_AGENT_NAMES:
        assert name in STARTER_AGENT_NAMES


@pytest.mark.parametrize("name", DEFAULT_PYTHON_AGENT_NAMES)
def test_discovers_as_python_kind_with_v1_entrypoint(data_root: Path, name: str) -> None:
    specs = discover_agents(data_root)
    spec = specs[name]
    assert spec.kind == "python"
    assert spec.api_version == 1
    assert spec.entry_point == "agent.py:create_agent"
    assert spec.source_path is not None and spec.source_path.is_file()


@pytest.mark.parametrize("name", DEFAULT_PYTHON_AGENT_NAMES)
def test_validates_cleanly(data_root: Path, name: str) -> None:
    result = validate_agent(name, data_root=data_root)
    assert isinstance(result, ValidationResult)
    assert result.agent_id == name
    assert result.api_version == 1


@pytest.mark.parametrize("name", DEFAULT_PYTHON_AGENT_NAMES)
def test_completes_a_development_match_against_the_reference_opponent(
    data_root: Path, name: str
) -> None:
    outcome = run_development_test(
        name,
        data_root=data_root,
        resource_root=_resource_root(),
        seed=1337,
        ticks=60,
        trace=False,
    )
    assert isinstance(outcome, DevelopmentTestOutcome)
    match_result = outcome.match_result
    assert match_result.ticks_run == 60
    tested_agent = match_result.agents_by_id["A"]
    assert tested_agent.diagnostic is None, (
        f"{name} recorded a forfeit diagnostic against the reference opponent: "
        f"{tested_agent.diagnostic}"
    )


@pytest.mark.parametrize("subject", DEFAULT_PYTHON_AGENT_NAMES)
def test_completes_matches_against_every_other_default_agent(
    data_root: Path, subject: str
) -> None:
    """Behavioral smoke: each agent plays every sibling default agent across
    a few seeds and every cell must complete -- no infrastructure failures,
    no initialization failures, no unhandled exceptions. Outcomes
    themselves (win/loss/tie) are intentionally not asserted."""

    opponents = [name for name in DEFAULT_PYTHON_AGENT_NAMES if name != subject]
    request = EvaluationRequest(
        candidate_id=subject,
        baseline_id=None,
        opponent_ids=tuple(opponents),
        seeds=(1, 2, 3),
        ticks=60,
        output_dir=data_root / "runs" / "agents_evaluate" / subject,
        data_root=data_root,
    )
    result = EvaluationService().run(request)
    for cell in result.cells:
        assert cell.status == "completed", (
            f"{subject} vs {cell.opponent_id} seed={cell.seed} did not complete: "
            f"status={cell.status} error={cell.error_code}:{cell.error_message}"
        )
        assert cell.outcome in ("win", "loss", "tie")
