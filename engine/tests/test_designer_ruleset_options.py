from __future__ import annotations

import pytest
from battle_engine.rules import BYTEFRAY_RULESET_ID
from battle_engine.ruleset_policy import (
    BYTEFRAY_RULESET_V2_ID,
    BYTEFRAY_RULESET_V4_ALPHA1_ID,
    BYTEFRAY_RULESET_V4_ALPHA2_ID,
    BYTEFRAY_RULESET_V4_ID,
    agent_supported_by_ruleset,
)

from app.services.agent_catalog import AgentRow
from app.services.ruleset_options import (
    DESIGNER_RULESET_OPTIONS,
    SIMPLE_RULESET_OPTIONS,
    agent_row_metadata,
    agent_row_supported_by_ruleset,
    best_designer_ruleset,
    best_designer_ruleset_for_agents,
    ruleset_supports_agent_metadata,
    ruleset_supports_runtime_kinds,
    validate_designer_agent_rows,
    validate_designer_ruleset,
)


def test_product_options_include_all_v4_identities_without_changing_default_preference() -> None:
    """Advanced/Development offer all three v4 identities; Simple offers
    only current.

    Simple has followed a "current gameplay only" policy since
    v3.0.0-alpha2, so it carries one current Ruleset per Agent API
    generation, and both v4 alphas leave it once the permanent stable
    identity exists (v4.0.0-rc1 Phase 2) -- exactly as alpha1 left it once
    alpha2 arrived before. Advanced and Development keep both alphas so a
    historical alpha1/alpha2 match stays reproducible from the GUI, and the
    stable identity is listed before them so the automatic preference lands
    on current, permanent gameplay.
    """

    assert [option.ruleset_id for option in DESIGNER_RULESET_OPTIONS] == [
        BYTEFRAY_RULESET_V2_ID,
        BYTEFRAY_RULESET_V4_ID,
        BYTEFRAY_RULESET_V4_ALPHA2_ID,
        BYTEFRAY_RULESET_V4_ALPHA1_ID,
        BYTEFRAY_RULESET_ID,
    ]
    assert [option.ruleset_id for option in SIMPLE_RULESET_OPTIONS] == [
        BYTEFRAY_RULESET_V2_ID,
        BYTEFRAY_RULESET_V4_ID,
    ]
    assert best_designer_ruleset({"python"}) == BYTEFRAY_RULESET_V2_ID


def test_the_three_v4_options_are_distinguishable_to_a_reader() -> None:
    """All three v4 identities are Python-only Agent API v2, so their labels
    are the only thing telling a user which one they are about to run."""

    labels = {option.ruleset_id: option.label for option in DESIGNER_RULESET_OPTIONS}
    stable_label = labels[BYTEFRAY_RULESET_V4_ID]
    alpha2_label = labels[BYTEFRAY_RULESET_V4_ALPHA2_ID]
    alpha1_label = labels[BYTEFRAY_RULESET_V4_ALPHA1_ID]
    assert len({stable_label, alpha2_label, alpha1_label}) == 3
    assert "Current" in stable_label or "Recommended" in stable_label
    assert "alpha2" in alpha2_label and "historical" in alpha2_label
    assert "alpha1" in alpha1_label and "historical" in alpha1_label


def test_python_composition_prefers_v2_and_vm_composition_prefers_v1() -> None:
    assert best_designer_ruleset({"python"}) == BYTEFRAY_RULESET_V2_ID
    assert best_designer_ruleset({"vm"}) == BYTEFRAY_RULESET_ID
    assert ruleset_supports_runtime_kinds(BYTEFRAY_RULESET_V2_ID, {"python"})
    assert not ruleset_supports_runtime_kinds(BYTEFRAY_RULESET_V2_ID, {"vm"})


def test_programmatic_v2_vm_launch_is_rejected_before_spawn() -> None:
    with pytest.raises(ValueError, match="Use Ruleset v1 for VM/blob matches"):
        validate_designer_ruleset(BYTEFRAY_RULESET_V2_ID, {"vm"})

    validate_designer_ruleset(BYTEFRAY_RULESET_V2_ID, {"python"})
    validate_designer_ruleset(BYTEFRAY_RULESET_ID, {"vm"})


def test_catalog_row_projection_and_launch_validation_include_agent_api() -> None:
    api_v1 = AgentRow(
        "legacy", "/agents/legacy", None, {"kind": "python", "api_version": 1}
    )
    api_v2 = AgentRow(
        "process", "/agents/process", None, {"kind": "python", "api_version": 2}
    )
    vm = AgentRow("runner", "/agents/runner", None, {"kind": "builtin"})

    assert agent_row_supported_by_ruleset(api_v1, BYTEFRAY_RULESET_V2_ID)
    assert not agent_row_supported_by_ruleset(api_v2, BYTEFRAY_RULESET_V2_ID)
    assert agent_row_supported_by_ruleset(api_v2, BYTEFRAY_RULESET_V4_ALPHA1_ID)
    assert not agent_row_supported_by_ruleset(vm, BYTEFRAY_RULESET_V4_ALPHA1_ID)

    with pytest.raises(ValueError, match="selected agent metadata: process"):
        validate_designer_agent_rows(BYTEFRAY_RULESET_V2_ID, (api_v1, api_v2))


# ---------------------------------------------------------------------------
# Phase 2 M1: one canonical, Agent-API-aware compatibility policy
# ---------------------------------------------------------------------------

_API_V1 = {"kind": "python", "api_version": 1}
_API_V2 = {"kind": "python", "api_version": 2}
_VM = {"kind": "builtin"}
_UNVERSIONED = {"kind": "python"}


@pytest.mark.parametrize(
    "metadata", [_API_V1, _API_V2, _VM, _UNVERSIONED, {"kind": "blob"}, {}]
)
@pytest.mark.parametrize(
    "option", DESIGNER_RULESET_OPTIONS, ids=lambda option: option.ruleset_id
)
def test_designer_compatibility_always_agrees_with_engine_policy(
    metadata: dict[str, object], option
) -> None:
    """The anti-drift guard for M1.

    Agent Designer must never answer "is this Ruleset compatible?"
    differently from the engine that will execute the match -- that
    divergence *was* M1, where a view asked only about runtime kind and so
    offered Ruleset v2 for an Agent API v2 agent. Asserting agreement with
    ``agent_supported_by_ruleset`` for every offered Ruleset is stronger
    than restating expected lists per view, because a future Ruleset or
    Agent API generation is covered automatically.
    """

    assert ruleset_supports_agent_metadata(
        option.ruleset_id, [metadata]
    ) is agent_supported_by_ruleset(metadata, option.ruleset_id)


@pytest.mark.parametrize(
    ("metadata", "compatible_ids"),
    [
        (_API_V1, {BYTEFRAY_RULESET_V2_ID, BYTEFRAY_RULESET_ID}),
        (
            _API_V2,
            {BYTEFRAY_RULESET_V4_ALPHA1_ID, BYTEFRAY_RULESET_V4_ALPHA2_ID, BYTEFRAY_RULESET_V4_ID},
        ),
        (_VM, {BYTEFRAY_RULESET_ID}),
        # A Python agent declaring no API version cannot run under any
        # Ruleset -- the loader rejects it too -- so no surface may offer one.
        (_UNVERSIONED, set()),
    ],
)
def test_offered_rulesets_per_agent_api_generation(
    metadata: dict[str, object], compatible_ids: set[str]
) -> None:
    offered = {
        option.ruleset_id
        for option in DESIGNER_RULESET_OPTIONS
        if ruleset_supports_agent_metadata(option.ruleset_id, [metadata])
    }
    assert offered == compatible_ids


def test_compatibility_is_evaluated_across_the_whole_selected_roster() -> None:
    """One incompatible entrant disqualifies a Ruleset for the whole match."""

    assert ruleset_supports_agent_metadata(BYTEFRAY_RULESET_V2_ID, [_API_V1, _API_V1])
    assert not ruleset_supports_agent_metadata(BYTEFRAY_RULESET_V2_ID, [_API_V1, _API_V2])
    assert not ruleset_supports_agent_metadata(
        BYTEFRAY_RULESET_V4_ALPHA1_ID, [_API_V2, _API_V1]
    )


def test_unselected_slots_impose_no_constraint_but_selected_ones_fail_closed() -> None:
    # Nothing selected yet -- every Ruleset stays offerable.
    assert ruleset_supports_agent_metadata(BYTEFRAY_RULESET_V4_ALPHA1_ID, [])
    assert ruleset_supports_agent_metadata(BYTEFRAY_RULESET_V4_ALPHA1_ID, [None, None])
    assert ruleset_supports_agent_metadata(BYTEFRAY_RULESET_V4_ALPHA1_ID, [_API_V2, None])
    # A row that *is* selected but carries unusable metadata fails closed.
    assert not ruleset_supports_agent_metadata(BYTEFRAY_RULESET_V4_ALPHA1_ID, [{}])


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        ([_API_V1], BYTEFRAY_RULESET_V2_ID),
        ([_API_V2], BYTEFRAY_RULESET_V4_ID),
        ([_VM], BYTEFRAY_RULESET_ID),
        # No offered Ruleset supports a mixed Agent API roster: an explicit
        # "nothing is compatible" answer, never an incompatible fallback.
        ([_API_V1, _API_V2], None),
        ([_API_V2, _VM], None),
    ],
)
def test_designer_fallback_is_deterministic_and_never_incompatible(
    metadata: list[object], expected: str | None
) -> None:
    chosen = best_designer_ruleset_for_agents(metadata)
    assert chosen == expected
    if chosen is not None:
        assert ruleset_supports_agent_metadata(chosen, metadata)


def test_row_metadata_projection_fails_closed_but_is_distinct_from_no_selection() -> None:
    row = AgentRow("proc", "/agents/proc", None, {"kind": "python", "api_version": 2})
    assert agent_row_metadata(row) == {"kind": "python", "api_version": 2}
    # An unreadable row projects to an empty mapping (fails closed), never to
    # None, which would read as "nothing selected" and impose no constraint.
    assert agent_row_metadata(object()) == {}
    assert agent_row_metadata(object()) is not None
