"""Product-facing Ruleset choices for Agent Designer direct matches."""

from __future__ import annotations

from dataclasses import dataclass

from battle_engine.rules import BYTEFRAY_RULESET_ID
from battle_engine.ruleset_policy import (
    BYTEFRAY_RULESET_V2_ID,
    BYTEFRAY_RULESET_V4_ALPHA1_ID,
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
        BYTEFRAY_RULESET_V4_ALPHA1_ID,
        "Ruleset v4 alpha1 — Process-agent preview (Agent API v2)",
    ),
    DesignerRulesetOption(
        BYTEFRAY_RULESET_ID, "Ruleset v1 — Compatibility (Python and VM/blob)"
    ),
)

# Accurate on both axes, which the previous "Legacy / VM compatibility"
# wording was not: Ruleset v1 is not Python-incompatible (a Python agent
# runs unmodified under either identity -- see docs/COMPATIBILITY.md's
# "The same Agent API v1 Python agent source may execute under more than
# one compatible Ruleset"), it is merely not the current gameplay. What is
# genuinely exclusive is the other direction: only v1 executes VM/blob
# entrants. Deliberately says nothing about Redcode/pMARS, which uses no
# Bytefray Ruleset at all (docs/RULES.md's "Redcode/pMARS -- not Ruleset
# v1") and must never be implied to be a Ruleset-v1 format.
RULESET_DESCRIPTION = (
    "Ruleset v2 is Bytefray's current gameplay ruleset and runs Python agents only. "
    "Ruleset v4 alpha1 is the process-agent preview and requires Agent API v2. "
    "Ruleset v1 also runs Agent API v1 Python agents and is the only Bytefray "
    "ruleset that runs VM/blob agents."
)

# Shown next to a Ruleset selector whenever the current entrant selection
# includes a VM/blob agent.
VM_RULESET_EXPLANATION = (
    "VM/blob agents run under Ruleset v1 only. Rulesets v2 and v4 alpha1 are "
    "Python-agent only."
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
