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
    BYTEFRAY_RULESET_V2_ID,
    BYTEFRAY_RULESET_V4_ALPHA1_ID,
    BYTEFRAY_RULESET_V4_ALPHA2_ID,
    OMITTED_RULESET_CANDIDATES,
    RULESET_V1,
    RULESET_V2,
    RULESET_V2_ALPHA1,
    RULESET_V2_ALPHA11,
    NoCompatibleRulesetError,
    RulesetPolicy,
    TerminationDecision,
    TerminationReason,
    UnknownRulesetError,
    resolve_omitted_ruleset_for_agents,
    resolve_omitted_ruleset_id,
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


def test_permanent_v2_ruleset_id_resolves_to_its_own_distinct_policy() -> None:
    """v2.0.0-beta1's permanent identity: registered under its own explicit
    key, distinct from -- and never aliased to or from -- Ruleset v1 or
    either historical alpha identity (docs/V2_0_BETA1_PLAN.md).
    """

    policy = resolve_ruleset_policy(BYTEFRAY_RULESET_V2_ID)
    assert policy is RULESET_V2
    assert policy.ruleset_id == "bytefray-rules-2"
    assert policy is not RULESET_V1
    assert policy is not RULESET_V2_ALPHA1
    assert policy is not RULESET_V2_ALPHA11
    assert policy.ruleset_id not in {
        RULESET_V1.ruleset_id,
        RULESET_V2_ALPHA1.ruleset_id,
        RULESET_V2_ALPHA11.ruleset_id,
    }


def test_permanent_v2_scheduling_and_termination_are_identical_to_v1() -> None:
    states = [_FakeState("A"), _FakeState("B")]
    calls: list[str] = []
    RULESET_V2.run_scheduler(states, 2, lambda s, slot: calls.append(f"{s.name}{slot}"))
    assert calls == ["A0", "A1", "B0", "B1"]
    assert RULESET_V2.resolve_termination(
        alive_count=1, tick=1, max_ticks=10
    ) == TerminationDecision(terminated=True, reason=TerminationReason.LAST_AGENT_STANDING)


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
        "bytefray-rules-3",
        "unknown",
        "evaluation-rules-999",
        "evaluation-rules-1",
        "bytefray-rules-2-alpha2",
        "bytefray-rules-2-alpha12",
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


# ---------------------------------------------------------------------------
# Phase 2 H1: Agent-API-aware omitted-Ruleset resolution
# ---------------------------------------------------------------------------


def _python(api_version: object, agent_id: str = "probe") -> dict[str, object]:
    return {"agent_id": agent_id, "kind": "python", "api_version": api_version}


_VM = {"agent_id": "runner", "kind": "builtin", "api_version": None}


@pytest.mark.parametrize(
    ("roster", "expected"),
    [
        # Historical Agent API v1 Python gameplay is unchanged.
        ([_python(1)], BYTEFRAY_RULESET_V2_ID),
        ([_python(1, "a"), _python(1, "b")], BYTEFRAY_RULESET_V2_ID),
        # Agent API v2 reaches the process-agent Ruleset without the author
        # ever naming it -- the H1 defect this resolution exists to fix. The
        # identity it reaches is the *newest intended* v4 development
        # Ruleset, which is alpha2 from v4.0.0-alpha2 onward; alpha1 stays
        # explicitly selectable (asserted directly below) but is no longer
        # what an omitted Ruleset lands on.
        ([_python(2)], BYTEFRAY_RULESET_V4_ALPHA2_ID),
        ([_python(2, "a"), _python(2, "b")], BYTEFRAY_RULESET_V4_ALPHA2_ID),
        # VM/blob composition keeps resolving to the only Ruleset that runs it.
        ([_VM], BYTEFRAY_RULESET_ID),
        ([_VM, _VM], BYTEFRAY_RULESET_ID),
        # A mixed Python/VM roster still resolves to v1 exactly as before:
        # v1 supports both, and NativeMatchService's own homogeneity guard --
        # not Ruleset resolution -- remains what rejects the composition.
        ([_python(1), _VM], BYTEFRAY_RULESET_ID),
        # Nothing to derive a Ruleset from keeps the historical default.
        ([], BYTEFRAY_RULESET_ID),
    ],
)
def test_omitted_ruleset_resolves_from_runtime_kind_and_api_version(
    roster: list[dict[str, object]], expected: str
) -> None:
    assert resolve_omitted_ruleset_for_agents(None, roster) == expected


@pytest.mark.parametrize(
    "roster",
    [
        # No single Ruleset supports both Agent API generations at once.
        [_python(1, "legacy"), _python(2, "process")],
        # An Agent API v2 entrant cannot join a VM roster under v1 either.
        [_python(2), _VM],
        # Python metadata with no usable API version fails closed, matching
        # the loader's own fail-closed treatment of it.
        [{"agent_id": "unversioned", "kind": "python", "api_version": None}],
        [_python(True)],
    ],
)
def test_incompatible_roster_fails_closed_instead_of_guessing(
    roster: list[dict[str, object]],
) -> None:
    with pytest.raises(NoCompatibleRulesetError) as caught:
        resolve_omitted_ruleset_for_agents(None, roster)

    assert caught.value.code == "ruleset_resolution_failed"
    assert "No Bytefray Ruleset supports" in str(caught.value)


@pytest.mark.parametrize(
    ("requested", "roster"),
    [
        # Compatible explicit selections are returned unchanged...
        (BYTEFRAY_RULESET_V4_ALPHA1_ID, [_python(2)]),
        (BYTEFRAY_RULESET_V2_ID, [_python(1)]),
        # ...and so are incompatible ones: resolution never overrides a
        # user's explicit choice, leaving NativeMatchService to reject it
        # with the clean configuration error the Phase 1 work established.
        (BYTEFRAY_RULESET_V2_ID, [_python(2)]),
        (BYTEFRAY_RULESET_V4_ALPHA1_ID, [_python(1)]),
        # Including a roster automatic resolution would have refused.
        (BYTEFRAY_RULESET_V2_ID, [_python(1), _python(2)]),
        # Including an experimental identity automatic resolution never picks.
        (BYTEFRAY_RULESET_V2_ALPHA1_ID, [_python(1)]),
    ],
)
def test_explicit_ruleset_selection_is_always_authoritative(
    requested: str, roster: list[dict[str, object]]
) -> None:
    assert resolve_omitted_ruleset_for_agents(requested, roster) == requested


def test_automatic_resolution_never_selects_an_experimental_identity() -> None:
    """Automatic resolution may only ever land on a product Ruleset.

    An omitted selection must never wander into an experimental identity
    (``bytefray-rules-2-alpha1``/``-alpha11``/``bytefray-rules-3-alpha1``)
    that the user did not ask for by name.
    """

    assert OMITTED_RULESET_CANDIDATES == (
        BYTEFRAY_RULESET_V2_ID,
        BYTEFRAY_RULESET_V4_ALPHA2_ID,
        BYTEFRAY_RULESET_ID,
    )
    assert all("alpha" not in candidate for candidate in OMITTED_RULESET_CANDIDATES[:1])
    # The v4 prerelease slot holds exactly one identity. Listing both v4
    # alphas would make whichever came second unreachable (they accept
    # identical rosters), so the tuple must never grow a second one rather
    # than quietly carrying a candidate no roster can select.
    assert (
        sum(
            candidate.startswith("bytefray-rules-4")
            for candidate in OMITTED_RULESET_CANDIDATES
        )
        == 1
    )


def test_v4_alpha1_remains_explicitly_selectable_after_alpha2_takes_the_default() -> None:
    """Alpha2 becoming the automatic v4 choice must not retire alpha1.

    Automatic resolution moving to alpha2 is a *default* change, not a
    compatibility removal: every historical alpha1 match must stay
    reproducible by naming alpha1 explicitly, and alpha1's policy must keep
    executing with its own frozen semantics rather than resolving to alpha2.
    """

    assert (
        resolve_omitted_ruleset_for_agents(BYTEFRAY_RULESET_V4_ALPHA1_ID, [_python(2)])
        == BYTEFRAY_RULESET_V4_ALPHA1_ID
    )
    alpha1 = resolve_ruleset_policy(BYTEFRAY_RULESET_V4_ALPHA1_ID)
    alpha2 = resolve_ruleset_policy(BYTEFRAY_RULESET_V4_ALPHA2_ID)
    assert alpha1.ruleset_id != alpha2.ruleset_id
    assert (alpha1.core_placement, alpha1.process_selection) == (
        "seat_spread",
        "priority",
    )
    assert (alpha2.core_placement, alpha2.process_selection) == (
        "seeded",
        "round_robin",
    )
    # Everything else about the two policies is deliberately identical.
    assert alpha1.supported_runtime_kinds == alpha2.supported_runtime_kinds
    assert (
        alpha1.supported_python_api_versions == alpha2.supported_python_api_versions
    )
    assert alpha1.scheduler_mode == alpha2.scheduler_mode
    assert alpha1.scheduler_chunk_size == alpha2.scheduler_chunk_size
    assert alpha1.scheduler_rotate_start == alpha2.scheduler_rotate_start


@pytest.mark.parametrize(
    ("kinds", "expected"),
    [
        ({"python"}, BYTEFRAY_RULESET_V2_ID),
        ({"vm"}, BYTEFRAY_RULESET_ID),
        ({"python", "vm"}, BYTEFRAY_RULESET_ID),
        (set(), BYTEFRAY_RULESET_ID),
        ({"unrecognized"}, BYTEFRAY_RULESET_ID),
    ],
)
def test_kind_only_compatibility_surface_keeps_its_historical_behavior(
    kinds: set[str], expected: str
) -> None:
    """``resolve_omitted_ruleset_id`` is retained for out-of-tree callers.

    It now delegates to the API-aware resolver (so the two cannot drift),
    projecting a bare ``python`` kind as Agent API v1 -- the assumption its
    signature always encoded -- and must therefore still answer exactly what
    it answered before that delegation existed, never raising.
    """

    assert resolve_omitted_ruleset_id(None, kinds) == expected


def test_kind_only_surface_still_passes_explicit_selections_through() -> None:
    assert (
        resolve_omitted_ruleset_id(BYTEFRAY_RULESET_V4_ALPHA1_ID, {"python"})
        == BYTEFRAY_RULESET_V4_ALPHA1_ID
    )
