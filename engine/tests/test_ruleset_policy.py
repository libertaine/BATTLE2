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
    RULESET_V1,
    RulesetPolicy,
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


@pytest.mark.parametrize(
    "unknown_id",
    ["bytefray-rules-2", "unknown", "evaluation-rules-999", "evaluation-rules-1", ""],
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
