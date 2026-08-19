"""v2.0.0-alpha.1 experimental reference agents: Core Defender, Core Seeker.

These are experimental/reference agents (docs/V2_0_ALPHA_ARCHITECTURE.md
Sec 6, docs/V2_0_ALPHA1_EVALUATION.md), not claims of optimal strategy.
They are deliberately not part of ``battle_engine.starters.
STARTER_AGENT_NAMES`` (see ``reference_agents.py``'s module docstring), so
they cannot be exercised through ``agent_validation.validate_agent``
(which requires writable-catalog discovery via ``resolve_agent``) the way
a catalog agent would be -- this file validates them the same way
``agent_test._reference_opponent_spec``'s own internal ``reference``
opponent is implicitly validated: by loading them through the real Agent
API v1 contract (``load_python_agent``) and by running them through real
matches end to end.

Named distinctly from ``test_reference_agents.py`` (which already existed
for an unrelated purpose -- VM ``builtins.registry`` instruction-level
fixtures) to avoid colliding with it.
"""

from __future__ import annotations

from battle_engine.agent_api import load_python_agent
from battle_engine.config import Config
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.reference_agents import REFERENCE_AGENT_NAMES, reference_agent_spec
from battle_engine.rules import BYTEFRAY_RULESET_ID
from battle_engine.ruleset_policy import BYTEFRAY_RULESET_V2_ALPHA1_ID

ALPHA = BYTEFRAY_RULESET_V2_ALPHA1_ID


def test_reference_agent_names_are_exactly_defender_and_seeker() -> None:
    # alpha.2 (docs/V2_0_ALPHA2_REACTIVE_DEFENSE.md) added a third,
    # additive reference agent, reactive_core_defender, alongside the
    # original two -- not a replacement, so the original pair stays
    # available for direct comparison.
    assert REFERENCE_AGENT_NAMES == ("core_defender", "core_seeker", "reactive_core_defender")


def test_reference_agents_are_not_part_of_the_general_starter_roster() -> None:
    from battle_engine.starters import STARTER_AGENT_NAMES

    assert "core_defender" not in STARTER_AGENT_NAMES
    assert "core_seeker" not in STARTER_AGENT_NAMES


def test_reference_agent_spec_rejects_unknown_names() -> None:
    import pytest

    with pytest.raises(ValueError, match="Unknown v2.0.0-alpha.1 reference agent"):
        reference_agent_spec("not_a_reference_agent")


def test_core_defender_satisfies_the_agent_api_v1_contract() -> None:
    loaded = load_python_agent(reference_agent_spec("core_defender"))
    assert loaded.metadata.agent_id == "core_defender"
    assert loaded.metadata.api_version == 1


def test_core_seeker_satisfies_the_agent_api_v1_contract() -> None:
    loaded = load_python_agent(reference_agent_spec("core_seeker"))
    assert loaded.metadata.agent_id == "core_seeker"
    assert loaded.metadata.api_version == 1


def _run(tmp_path, spec_a, start_a, spec_b, start_b, *, ruleset_id, ticks=100, arena_size=4096):
    entrants = (
        MatchEntrant.python("A", "A", start_a, spec_a),
        MatchEntrant.python("B", "B", start_b, spec_b),
    )
    request = MatchRequest(
        Config(arena_size=arena_size),
        entrants,
        max_ticks=ticks,
        replay_path=tmp_path / "run" / "replay.jsonl",
        verbose=False,
        ruleset_id=ruleset_id,
    )
    return NativeMatchService().run(request)


def test_core_defender_runs_a_full_match_without_forfeiting_under_the_alpha_ruleset(tmp_path) -> None:
    defender = reference_agent_spec("core_defender")
    result = _run(tmp_path, defender, 0, defender, 2048, ruleset_id=ALPHA)
    for agent in result.agents:
        assert agent.diagnostic is None


def test_core_seeker_runs_a_full_match_without_forfeiting_under_the_alpha_ruleset(tmp_path) -> None:
    seeker = reference_agent_spec("core_seeker")
    result = _run(tmp_path, seeker, 0, seeker, 2048, ruleset_id=ALPHA)
    for agent in result.agents:
        assert agent.diagnostic is None


def test_core_seeker_can_locate_and_capture_core_defenders_core(tmp_path) -> None:
    """Not a guarantee for every seed/orientation (this is a reference
    agent, not a solved strategy) -- but at least one seed must show the
    intended capture behavior actually occurring end to end, or the
    mechanic/agents are not doing what they were designed to do."""

    defender = reference_agent_spec("core_defender")
    seeker = reference_agent_spec("core_seeker")
    captured = False
    for seed in range(1, 9):
        entrants = (
            MatchEntrant.python("A", "core_defender", 0, defender),
            MatchEntrant.python("B", "core_seeker", 2048, seeker),
        )
        request = MatchRequest(
            Config(arena_size=4096, seed=seed),
            entrants,
            max_ticks=200,
            replay_path=tmp_path / f"run-{seed}" / "replay.jsonl",
            verbose=False,
            ruleset_id=ALPHA,
        )
        result = NativeMatchService().run(request)
        if result.agents_by_id["A"].termination_reason == "core_captured":
            captured = True
            assert result.agents_by_id["B"].kills == 1
            break
    assert captured, "Core Seeker never captured Core Defender's core across 8 seeds"


def test_reference_agents_also_run_cleanly_under_ruleset_v1(tmp_path) -> None:
    """The two reference agents are ordinary Agent API v1 Python agents --
    nothing about them requires the alpha ruleset to function; under v1
    they simply never experience a core capture (no core exists there)."""

    defender = reference_agent_spec("core_defender")
    seeker = reference_agent_spec("core_seeker")
    result = _run(tmp_path, defender, 0, seeker, 2048, ruleset_id=None, ticks=50)
    assert result.termination_reason.value in {"tick_limit", "last_agent_standing", "all_agents_dead"}
    for agent in result.agents:
        assert agent.diagnostic is None
        assert agent.termination_reason != "core_captured"
    header_ruleset_id = None
    from battle_engine.replay import ReplayHeader, iter_replay

    for record in iter_replay(result.replay_path):
        if isinstance(record, ReplayHeader):
            header_ruleset_id = record.ruleset_id
            break
    assert header_ruleset_id == BYTEFRAY_RULESET_ID
