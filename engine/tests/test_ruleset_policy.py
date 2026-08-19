"""Direct unit tests for the Ruleset-v1 policy/resolver dispatch seam.

These pin the policy and resolver in isolation, independent of any runtime
(VM/Python/supervised) that consumes them -- runtime-integration coverage
that the policy actually reaches each execution path lives in
``test_scheduler_characterization.py``, ``test_python_scheduler_characterization.py``,
and ``test_supervised_runtime.py`` (unchanged this phase, proving the wiring
introduced no behavior change).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass

import pytest
from battle_engine.rules import BYTEFRAY_RULESET_ID
from battle_engine.ruleset_policy import (
    BYTEFRAY_RULESET_V2_ALPHA1_ID,
    RULESET_V1,
    RULESET_V2_ALPHA1,
    RulesetPolicy,
    TerminationDecision,
    TerminationReason,
    UnknownRulesetError,
    resolve_ruleset_policy,
)
from battle_engine.scheduler import run_sequential_quota


@dataclass
class _FakeState:
    name: str
    alive: bool = True


def test_current_ruleset_id_resolves_to_the_v1_policy() -> None:
    assert resolve_ruleset_policy("bytefray-rules-1") is RULESET_V1


def test_resolved_policy_identity_matches_the_frozen_ruleset_id() -> None:
    policy = resolve_ruleset_policy(BYTEFRAY_RULESET_ID)
    assert policy.ruleset_id == "bytefray-rules-1" == BYTEFRAY_RULESET_ID


def test_ruleset_v1_singleton_identity_is_the_frozen_constant() -> None:
    assert RULESET_V1.ruleset_id == BYTEFRAY_RULESET_ID


def test_policy_scheduler_matches_the_phase_2_sequential_quota_behavior() -> None:
    """The policy's ``run_scheduler`` must reproduce
    ``scheduler.run_sequential_quota`` exactly -- same call order, same
    mid-quota mortality handling -- since this phase moves only *where*
    runtime code obtains the scheduler, not what it does.
    """

    states = [_FakeState("A"), _FakeState("B"), _FakeState("C")]
    via_policy: list[str] = []

    def execute_via_policy(state: _FakeState, slot: int) -> None:
        via_policy.append(f"{state.name}{slot}")
        if state.name == "B" and slot == 1:
            state.alive = False

    RULESET_V1.run_scheduler(states, 3, execute_via_policy)

    states_direct = [_FakeState("A"), _FakeState("B"), _FakeState("C")]
    via_direct: list[str] = []

    def execute_direct(state: _FakeState, slot: int) -> None:
        via_direct.append(f"{state.name}{slot}")
        if state.name == "B" and slot == 1:
            state.alive = False

    run_sequential_quota(states_direct, 3, execute_direct)

    assert via_policy == via_direct == ["A0", "A1", "A2", "B0", "B1", "C0", "C1", "C2"]


def test_v2_alpha1_ruleset_id_resolves_to_its_own_distinct_policy() -> None:
    """v2.0.0-alpha.1's dispatch registration (Phase 2/Sec 7 of
    docs/V2_0_ALPHA_ARCHITECTURE.md): registered under its own explicit
    key, distinct from -- and never aliased to or from -- Ruleset v1.
    """

    policy = resolve_ruleset_policy(BYTEFRAY_RULESET_V2_ALPHA1_ID)
    assert policy is RULESET_V2_ALPHA1
    assert policy.ruleset_id == "bytefray-rules-2-alpha1"
    assert policy is not RULESET_V1
    assert policy.ruleset_id != RULESET_V1.ruleset_id


def test_v2_alpha1_scheduling_and_termination_are_identical_to_v1() -> None:
    """The alpha changes core-capture mortality only -- scheduling order
    and the termination decision formula are the exact same shared
    implementation as Ruleset v1 (neither reads ``self.ruleset_id``).
    """

    states = [_FakeState("A"), _FakeState("B")]
    calls: list[str] = []
    RULESET_V2_ALPHA1.run_scheduler(states, 2, lambda s, slot: calls.append(f"{s.name}{slot}"))
    assert calls == ["A0", "A1", "B0", "B1"]
    assert RULESET_V2_ALPHA1.resolve_termination(
        alive_count=1, tick=1, max_ticks=10
    ) == TerminationDecision(terminated=True, reason=TerminationReason.LAST_AGENT_STANDING)


@pytest.mark.parametrize(
    "unknown_id",
    [
        "bytefray-rules-2",
        "unknown",
        "evaluation-rules-999",
        "evaluation-rules-1",
        "bytefray-rules-2-alpha2",
        "",
    ],
)
def test_unknown_ruleset_id_fails_closed_rather_than_resolving_to_v1(
    unknown_id: str,
) -> None:
    """No unrecognized ID -- including the historical artifact-provenance
    alias ``evaluation-rules-1`` -- may silently execute as Ruleset v1.
    Runtime dispatch and historical artifact-identity attribution
    (``rules.normalize_ruleset_id``) are deliberately different concerns;
    see ``docs/V1_5_PHASE3_RULESET_POLICY_DISPATCH.md``.
    """

    with pytest.raises(UnknownRulesetError) as excinfo:
        resolve_ruleset_policy(unknown_id)
    assert excinfo.value.ruleset_id == unknown_id


def test_ruleset_policy_is_immutable() -> None:
    policy = RulesetPolicy(ruleset_id="bytefray-rules-1")
    with pytest.raises(FrozenInstanceError):
        policy.ruleset_id = "tampered"  # type: ignore[misc]


def test_termination_continues_when_multiple_alive_below_tick_limit() -> None:
    decision = RULESET_V1.resolve_termination(alive_count=3, tick=1, max_ticks=10)
    assert decision == TerminationDecision(terminated=False, reason=None)


def test_termination_reports_last_agent_standing_when_exactly_one_alive() -> None:
    decision = RULESET_V1.resolve_termination(alive_count=1, tick=1, max_ticks=10)
    assert decision == TerminationDecision(
        terminated=True, reason=TerminationReason.LAST_AGENT_STANDING
    )


def test_termination_reports_all_agents_dead_when_none_alive() -> None:
    decision = RULESET_V1.resolve_termination(alive_count=0, tick=1, max_ticks=10)
    assert decision == TerminationDecision(
        terminated=True, reason=TerminationReason.ALL_AGENTS_DEAD
    )


def test_termination_reports_tick_limit_when_multiple_alive_at_the_limit() -> None:
    decision = RULESET_V1.resolve_termination(alive_count=2, tick=10, max_ticks=10)
    assert decision == TerminationDecision(terminated=True, reason=TerminationReason.TICK_LIMIT)


@pytest.mark.parametrize(
    ("alive_count", "expected_reason"),
    [
        (0, TerminationReason.ALL_AGENTS_DEAD),
        (1, TerminationReason.LAST_AGENT_STANDING),
    ],
)
def test_termination_precedence_prefers_alive_count_over_tick_limit(
    alive_count: int, expected_reason: TerminationReason
) -> None:
    """When the alive-count condition and the tick limit are both true on
    the same tick, the alive-count-based reason wins -- matching the
    pre-Phase-4 duplicated ``if alive_count == 0 / == 1 / else`` blocks,
    where the tick-limit case was always the trailing ``else``.
    """

    decision = RULESET_V1.resolve_termination(
        alive_count=alive_count, tick=10, max_ticks=10
    )
    assert decision == TerminationDecision(terminated=True, reason=expected_reason)


def test_termination_decision_is_immutable() -> None:
    decision = RULESET_V1.resolve_termination(alive_count=3, tick=1, max_ticks=10)
    with pytest.raises(FrozenInstanceError):
        decision.terminated = True  # type: ignore[misc]
