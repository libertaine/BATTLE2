"""Product-facing Ruleset choices for Agent Designer direct matches."""

from __future__ import annotations

from dataclasses import dataclass

from battle_engine.rules import BYTEFRAY_RULESET_ID
from battle_engine.ruleset_policy import (
    BYTEFRAY_RULESET_V2_ID,
    UnknownRulesetError,
    resolve_ruleset_policy,
)


@dataclass(frozen=True)
class DesignerRulesetOption:
    ruleset_id: str
    label: str


DESIGNER_RULESET_OPTIONS = (
    DesignerRulesetOption(
        BYTEFRAY_RULESET_V2_ID, "Ruleset v2 — Current / Recommended"
    ),
    DesignerRulesetOption(
        BYTEFRAY_RULESET_ID, "Ruleset v1 — Legacy / VM compatibility"
    ),
)

RULESET_DESCRIPTION = (
    "Ruleset v2 is the current Bytefray gameplay ruleset and supports Python agents. "
    "Ruleset v1 is retained for legacy reproduction and VM/blob matches."
)


def ruleset_supports_runtime_kinds(ruleset_id: str, kinds: set[str]) -> bool:
    """Project the engine policy's authoritative compatibility information."""
    try:
        policy = resolve_ruleset_policy(ruleset_id)
    except UnknownRulesetError:
        return False
    return not policy.unsupported_runtime_kinds(kinds)


def best_designer_ruleset(kinds: set[str]) -> str:
    """Return the first product-preferred Ruleset compatible with ``kinds``."""
    for option in DESIGNER_RULESET_OPTIONS:
        if ruleset_supports_runtime_kinds(option.ruleset_id, kinds):
            return option.ruleset_id
    return BYTEFRAY_RULESET_ID


def validate_designer_ruleset(ruleset_id: str, kinds: set[str]) -> None:
    """Keep programmatic launch callers behind the engine policy boundary."""
    if not ruleset_supports_runtime_kinds(ruleset_id, kinds):
        kinds_text = ", ".join(sorted(kinds)) or "selected"
        raise ValueError(
            f"Ruleset {ruleset_id} does not support {kinds_text} entrants. "
            "Use Ruleset v1 for VM/blob matches."
        )
