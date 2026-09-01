"""Product-facing Ruleset choices for Agent Designer direct matches."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from battle_engine.rules import BYTEFRAY_RULESET_ID
from battle_engine.ruleset_policy import (
    BYTEFRAY_RULESET_V2_ID,
    BYTEFRAY_RULESET_V4_ALPHA1_ID,
    UnknownRulesetError,
    agent_supported_by_ruleset,
    resolve_ruleset_policy,
)


@dataclass(frozen=True)
class DesignerRulesetOption:
    ruleset_id: str
    label: str


RULESET_V2_OPTION = DesignerRulesetOption(
    BYTEFRAY_RULESET_V2_ID, "Ruleset v2 — Current / Recommended"
)
RULESET_V4_ALPHA1_OPTION = DesignerRulesetOption(
    BYTEFRAY_RULESET_V4_ALPHA1_ID,
    "Ruleset v4 alpha1 — Process-agent preview (Agent API v2)",
)
RULESET_V1_OPTION = DesignerRulesetOption(
    BYTEFRAY_RULESET_ID, "Ruleset v1 — Compatibility (Python and VM/blob)"
)

SIMPLE_RULESET_OPTIONS = (RULESET_V2_OPTION, RULESET_V4_ALPHA1_OPTION)
DESIGNER_RULESET_OPTIONS = (*SIMPLE_RULESET_OPTIONS, RULESET_V1_OPTION)

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
    """Project the engine policy's authoritative *runtime-kind* compatibility.

    Deliberately answers only half the compatibility question: it cannot
    tell ``bytefray-rules-2`` from ``bytefray-rules-4-alpha1``, which are
    both Python-only and differ by Agent API version. Every Designer surface
    that decides which Rulesets to *offer* therefore uses
    :func:`ruleset_supports_agent_metadata` instead. This remains for the
    VM/Python launch guard in ``validate_designer_ruleset``, where the
    runtime kind genuinely is the whole question.
    """
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


def ruleset_supports_agent_metadata(
    ruleset_id: str, metadata: Iterable[object]
) -> bool:
    """Does ``ruleset_id`` support *every* selected entrant's metadata?

    The single question every Designer surface asks about Ruleset
    compatibility, delegating to the engine's own
    :func:`~battle_engine.ruleset_policy.agent_supported_by_ruleset`
    predicate -- the same one ``NativeMatchService`` enforces before a match
    executes -- so the GUI cannot present a Ruleset the engine would then
    reject, and cannot drift from it as Rulesets are added.

    ``metadata`` is one entry per *selected* entrant, in any projection that
    predicate accepts (an ``AgentRow.meta`` mapping, an ``AgentSpec``).
    ``None`` entries mean "this selector has nothing selected yet" and
    impose no constraint; an empty selection is likewise unconstrained,
    since there is nothing for a Ruleset to be incompatible with. Anything
    genuinely selected but unreadable fails closed, exactly as
    :func:`agent_row_supported_by_ruleset` already does.
    """

    selected = [item for item in metadata if item is not None]
    return all(agent_supported_by_ruleset(item, ruleset_id) for item in selected)


def best_designer_ruleset_for_agents(
    metadata: Iterable[object],
    options: Iterable[DesignerRulesetOption] = DESIGNER_RULESET_OPTIONS,
) -> str | None:
    """The first product-preferred Ruleset supporting every selected entrant.

    Returns ``None`` when no offered Ruleset supports the selection, which
    is a real state a Designer surface must show (and disable execution
    for) rather than paper over with an incompatible fallback.
    """

    selected = tuple(metadata)
    for option in options:
        if ruleset_supports_agent_metadata(option.ruleset_id, selected):
            return option.ruleset_id
    return None


def agent_row_metadata(row: object) -> object:
    """The compatibility metadata carried by one catalog row.

    An unreadable row projects to an empty mapping rather than ``None`` on
    purpose: ``None`` means "nothing is selected here" and is unconstrained,
    while a row that *is* selected but carries no usable metadata must fail
    closed, exactly as :func:`agent_row_supported_by_ruleset` already makes
    it.
    """

    metadata = getattr(row, "meta", None)
    return metadata if isinstance(metadata, dict) else {}


def validate_designer_ruleset(ruleset_id: str, kinds: set[str]) -> None:
    """Keep programmatic launch callers behind the engine policy boundary."""
    if not ruleset_supports_runtime_kinds(ruleset_id, kinds):
        kinds_text = ", ".join(sorted(kinds)) or "selected"
        raise ValueError(
            f"Ruleset {ruleset_id} does not support {kinds_text} entrants. "
            "Use Ruleset v1 for VM/blob matches."
        )


def agent_row_supported_by_ruleset(row: object, ruleset_id: str) -> bool:
    """Project a catalog row through the engine's canonical predicate."""

    metadata = getattr(row, "meta", None)
    return isinstance(metadata, dict) and agent_supported_by_ruleset(
        metadata, ruleset_id
    )


def validate_designer_agent_rows(
    ruleset_id: str, rows: Iterable[object]
) -> None:
    """Reject stale/programmatic Designer launches with incompatible agents."""

    selected = tuple(rows)
    incompatible = [
        str(getattr(row, "agent_id", "") or getattr(row, "name", "<unknown>"))
        for row in selected
        if not agent_row_supported_by_ruleset(row, ruleset_id)
    ]
    if incompatible:
        names = ", ".join(incompatible)
        raise ValueError(
            f"Ruleset {ruleset_id} does not support the selected agent metadata: "
            f"{names}."
        )
