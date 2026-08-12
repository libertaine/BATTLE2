"""Coverage for the Bytefray gameplay Ruleset identity (docs/RULES.md)."""

from __future__ import annotations

from battle_engine.agent_evaluation import EVALUATION_RULES_COMPATIBILITY_ID
from battle_engine.rules import BYTEFRAY_RULESET_ID


def test_ruleset_id_is_the_frozen_v1_value():
    assert BYTEFRAY_RULESET_ID == "bytefray-rules-1"


def test_evaluation_rules_compatibility_id_is_a_ruleset_alias():
    """EVALUATION_RULES_COMPATIBILITY_ID must derive from BYTEFRAY_RULESET_ID
    rather than being a second, independently maintained rules counter (see
    docs/RULES.md's "Historical relationship to evaluation-rules-1" and
    docs/COMPATIBILITY.md). This is a deliberate compile-time relationship,
    not a coincidence -- if it ever drifts, a gameplay-semantic change could
    silently bump one identifier without the other.
    """

    assert EVALUATION_RULES_COMPATIBILITY_ID == BYTEFRAY_RULESET_ID
