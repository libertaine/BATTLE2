"""Coverage for ``v4_quorum``, the bundled Agent API v2 advanced example.

Promoted from the ``experiment/v4-quorum-agent`` research branch onto the
permanent RC2 release path (see ``battle_engine.starters.STARTER_AGENT_NAMES``).
Unlike the five simpler ``v4_*`` starters, Quorum is explicitly an advanced
example rather than a beginner starting point -- its manifest ``display``
must say so -- but it is otherwise a completely normal, publicly-authored
Agent API v2 entrant and is checked the same structural way the other
bundled starters are (see ``test_starter_agents.py`` and
``test_default_python_agents.py``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from battle_engine.agent_test import test_agent as run_development_test
from battle_engine.agent_validation import validate_agent
from battle_engine.agents import discover_agents
from battle_engine.rules import BYTEFRAY_RULESET_V4_ID
from battle_engine.starters import (
    STARTER_AGENT_NAMES,
    ensure_starter_agents,
    starter_agent_resource_dir,
)

from app.services.agent_catalog import AgentCatalog


def _resource_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_v4_quorum_is_declared_bundled_starter() -> None:
    assert "v4_quorum" in STARTER_AGENT_NAMES


def test_v4_quorum_bundled_resource_dir_exists() -> None:
    agent_dir = starter_agent_resource_dir("v4_quorum", resource_root=_resource_root())

    assert agent_dir.is_dir()
    assert (agent_dir / "agent.yaml").is_file()
    assert (agent_dir / "agent.py").is_file()


def test_v4_quorum_manifest_is_valid_permanent_v2_advanced_example() -> None:
    manifest_path = (
        starter_agent_resource_dir("v4_quorum", resource_root=_resource_root())
        / "agent.yaml"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["name"] == "v4_quorum"
    assert manifest["api_version"] == 2
    assert manifest["kind"] == "python"
    assert "Advanced Example" in manifest["display"]
    # The permanent identity must not leak the research-branch naming.
    assert "experimental" not in manifest["name"]
    assert "Experimental" not in manifest["display"]


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    ensure_starter_agents(resource_root=_resource_root(), data_root=tmp_path)
    return tmp_path


def test_v4_quorum_starter_bootstrap_installs_through_normal_path(
    data_root: Path,
) -> None:
    installed_dir = data_root / "agents" / "v4_quorum"

    assert (installed_dir / "agent.yaml").is_file()
    assert (installed_dir / "agent.py").is_file()


def test_v4_quorum_bootstrap_preserves_existing_user_files(tmp_path: Path) -> None:
    existing = tmp_path / "agents" / "v4_quorum" / "agent.yaml"
    existing.parent.mkdir(parents=True)
    existing.write_text("user-owned quorum override", encoding="utf-8")

    result = ensure_starter_agents(resource_root=_resource_root(), data_root=tmp_path)

    assert existing.read_text(encoding="utf-8") == "user-owned quorum override"
    assert existing.resolve() not in result.installed


def test_v4_quorum_discovered_by_engine_and_designer_catalog(data_root: Path) -> None:
    specs = discover_agents(data_root)
    rows = {row.agent_id: row for row in AgentCatalog(data_root).list_agents()}

    assert "v4_quorum" in specs
    assert specs["v4_quorum"].api_version == 2
    assert "Advanced Example" in specs["v4_quorum"].display

    assert "v4_quorum" in rows
    assert "Advanced Example" in rows["v4_quorum"].name


def test_v4_quorum_validates_through_agent_api_v2(data_root: Path) -> None:
    result = validate_agent("v4_quorum", data_root=data_root)

    assert result.api_version == 2


@pytest.mark.parametrize(
    "opponent",
    ["v4_defender_scout", "v4_local_defender", "v4_concentrated_attacker"],
)
def test_v4_quorum_runs_legally_against_permanent_v4_opponents(
    data_root: Path, opponent: str
) -> None:
    outcome = run_development_test(
        "v4_quorum",
        opponent=opponent,
        data_root=data_root,
        resource_root=_resource_root(),
        seed=1337,
        ticks=200,
        ruleset_id=BYTEFRAY_RULESET_V4_ID,
    )

    assert outcome.ruleset_id == BYTEFRAY_RULESET_V4_ID
    quorum_result = outcome.match_result.agents_by_id["A"]
    assert quorum_result.diagnostic is None
    assert quorum_result.alive_ticks >= 1
    assert quorum_result.cpu_total <= outcome.match_result.ticks_run * 8


def test_v4_quorum_deterministic_reruns_produce_identical_outcomes(
    data_root: Path,
) -> None:
    first = run_development_test(
        "v4_quorum",
        opponent="v4_defender_scout",
        data_root=data_root,
        resource_root=_resource_root(),
        seed=2024,
        ticks=150,
        ruleset_id=BYTEFRAY_RULESET_V4_ID,
        run_dir=data_root / "runs" / "first",
    )
    second = run_development_test(
        "v4_quorum",
        opponent="v4_defender_scout",
        data_root=data_root,
        resource_root=_resource_root(),
        seed=2024,
        ticks=150,
        ruleset_id=BYTEFRAY_RULESET_V4_ID,
        run_dir=data_root / "runs" / "second",
    )

    assert first.match_result.replay_sha256 == second.match_result.replay_sha256
    assert first.match_result.winner == second.match_result.winner
    assert first.match_result.ticks_run == second.match_result.ticks_run
