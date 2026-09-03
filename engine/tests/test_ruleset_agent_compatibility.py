"""Canonical Ruleset/runtime/Agent-API compatibility coverage."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from battle_engine.config import Config
from battle_engine.match_service import (
    MatchEntrant,
    MatchRequest,
    NativeMatchService,
    RulesetAgentUnsupportedError,
)
from battle_engine.rules import BYTEFRAY_RULESET_ID
from battle_engine.ruleset_policy import (
    BYTEFRAY_RULESET_V2_ID,
    BYTEFRAY_RULESET_V4_ALPHA1_ID,
    BYTEFRAY_RULESET_V4_ALPHA2_ID,
    BYTEFRAY_RULESET_V4_ID,
    agent_supported_by_ruleset,
)


@pytest.mark.parametrize(
    ("metadata", "ruleset_id", "expected"),
    [
        ({"kind": "builtin"}, BYTEFRAY_RULESET_ID, True),
        ({"kind": "blob"}, BYTEFRAY_RULESET_ID, True),
        ({"kind": "blob"}, BYTEFRAY_RULESET_V2_ID, False),
        ({"kind": "blob"}, BYTEFRAY_RULESET_V4_ALPHA1_ID, False),
        ({"kind": "python", "api_version": 1}, BYTEFRAY_RULESET_ID, True),
        ({"kind": "python", "api_version": 1}, BYTEFRAY_RULESET_V2_ID, True),
        ({"kind": "python", "api_version": 1}, BYTEFRAY_RULESET_V4_ALPHA1_ID, False),
        ({"kind": "python", "api_version": 2}, BYTEFRAY_RULESET_ID, False),
        ({"kind": "python", "api_version": 2}, BYTEFRAY_RULESET_V2_ID, False),
        ({"kind": "python", "api_version": 2}, BYTEFRAY_RULESET_V4_ALPHA1_ID, True),
        ({"kind": "python"}, BYTEFRAY_RULESET_V2_ID, False),
        ({"kind": "python", "api_version": True}, BYTEFRAY_RULESET_V2_ID, False),
        # v4.0.0-rc1 Phase 2: the permanent stable identity (task Sec 10) --
        # VM/blob + stable v4 rejected, API v1 + stable v4 rejected, API v2
        # + stable v4 accepted, mirroring alpha1/alpha2's existing rows
        # exactly (it shares their identical supported_runtime_kinds/
        # supported_python_api_versions fields).
        ({"kind": "blob"}, BYTEFRAY_RULESET_V4_ID, False),
        ({"kind": "python", "api_version": 1}, BYTEFRAY_RULESET_V4_ID, False),
        ({"kind": "python", "api_version": 2}, BYTEFRAY_RULESET_V4_ID, True),
        # Alpha2 explicitly too, for completeness alongside alpha1 above.
        ({"kind": "blob"}, BYTEFRAY_RULESET_V4_ALPHA2_ID, False),
        ({"kind": "python", "api_version": 1}, BYTEFRAY_RULESET_V4_ALPHA2_ID, False),
        ({"kind": "python", "api_version": 2}, BYTEFRAY_RULESET_V4_ALPHA2_ID, True),
    ],
)
def test_agent_supported_by_ruleset_uses_runtime_and_api_metadata(
    metadata: dict[str, object], ruleset_id: str, expected: bool
) -> None:
    assert agent_supported_by_ruleset(metadata, ruleset_id) is expected


@pytest.mark.parametrize(
    ("ruleset_id", "api_version"),
    [
        (BYTEFRAY_RULESET_ID, 2),
        (BYTEFRAY_RULESET_V2_ID, 2),
        (BYTEFRAY_RULESET_V4_ALPHA1_ID, 1),
        (BYTEFRAY_RULESET_V4_ALPHA1_ID, None),
        (BYTEFRAY_RULESET_V2_ID, True),
        # v4.0.0-rc1 Phase 2: a real NativeMatchService.run rejection under
        # the stable identity too -- "API v1 + Ruleset v4 must fail
        # clearly" (task Sec 10), proven at the actual execution boundary,
        # not only through the predicate above.
        (BYTEFRAY_RULESET_V4_ID, 1),
        (BYTEFRAY_RULESET_V4_ID, None),
    ],
)
def test_native_match_service_rejects_api_mismatch_before_runtime(
    tmp_path, ruleset_id: str, api_version: object
) -> None:
    entrants = tuple(
        MatchEntrant.python(
            slot,
            f"agent-{slot.lower()}",
            start,
            SimpleNamespace(kind="python", api_version=api_version),
        )
        for slot, start in (("A", 0), ("B", 32))
    )
    replay = tmp_path / "doomed" / "replay.jsonl"
    request = MatchRequest(
        config=Config(arena_size=128, instr_per_tick=8),
        entrants=entrants,
        max_ticks=1,
        replay_path=replay,
        verbose=False,
        ruleset_id=ruleset_id,
    )

    with pytest.raises(RulesetAgentUnsupportedError) as caught:
        NativeMatchService().run(request)

    assert caught.value.ruleset_id == ruleset_id
    assert [agent[0] for agent in caught.value.unsupported_agents] == [
        "A",
        "B",
    ]
    assert not replay.parent.exists()
