"""Coverage for the Bytefray gameplay Ruleset identity (docs/RULES.md)."""

from __future__ import annotations

from battle_engine.agent_evaluation import EVALUATION_RULES_COMPATIBILITY_ID
from battle_engine.rules import BYTEFRAY_RULESET_ID, RulesetProvenance, normalize_ruleset_id


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


def test_normalize_ruleset_id_maps_the_one_established_historical_alias():
    assert normalize_ruleset_id("evaluation-rules-1") == BYTEFRAY_RULESET_ID


def test_normalize_ruleset_id_is_idempotent_on_the_canonical_value():
    assert normalize_ruleset_id(BYTEFRAY_RULESET_ID) == BYTEFRAY_RULESET_ID


def test_normalize_ruleset_id_never_aliases_by_naming_convention():
    """v0.10 Phase 4.28: the alias table is finite and explicit, never
    prefix/pattern matching -- a superficially similar but unrelated or
    future value must pass through unchanged, not opportunistically
    normalize.
    """

    for unrelated in ("evaluation-rules-2", "bytefray-rules-2", "evaluation-rules-10", "unknown"):
        assert normalize_ruleset_id(unrelated) == unrelated


def test_ruleset_provenance_is_a_plain_value_confidence_pair():
    provenance = RulesetProvenance(BYTEFRAY_RULESET_ID, "recorded")
    assert provenance.value == BYTEFRAY_RULESET_ID
    assert provenance.confidence == "recorded"
