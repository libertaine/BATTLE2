"""Shared Agent Designer Ruleset combo-box behavior."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtWidgets import QComboBox, QLabel

from app.services.ruleset_options import (
    DESIGNER_RULESET_OPTIONS,
    RULESET_DESCRIPTION,
    VM_RULESET_EXPLANATION,
    DesignerRulesetOption,
    best_designer_ruleset_for_agents,
    ruleset_supports_agent_metadata,
)
from app.widgets.agent_combo import selected_agent_meta

# Shown next to a Ruleset selector when the current entrant selection has no
# compatible Ruleset at all. Deliberately states the cause (the selection,
# not the tool) and what to do, and is paired with disabled execution rather
# than a silent incompatible fallback.
NO_COMPATIBLE_RULESET_EXPLANATION = (
    "No available Ruleset supports this combination of agents. Agent API v1 "
    "and v2 agents cannot compete in the same match; select agents that share "
    "one Agent API version."
)


def populate_ruleset_combo(
    combo: QComboBox,
    options: tuple[DesignerRulesetOption, ...] = DESIGNER_RULESET_OPTIONS,
) -> None:
    combo.clear()
    for option in options:
        combo.addItem(option.label, option.ruleset_id)
    combo.setToolTip(RULESET_DESCRIPTION)
    combo.setAccessibleDescription(RULESET_DESCRIPTION)


def selected_ruleset_id(combo: QComboBox) -> str:
    return str(combo.currentData())


def sync_ruleset_choices_for_metadata(
    combo: QComboBox,
    metadata: Iterable[object],
    explanation: QLabel | None = None,
) -> bool:
    """Disable incompatible choices and deterministically repair selection.

    The one shared implementation every Designer surface uses to decide
    which Rulesets are offered for a given entrant selection, asking the
    engine's own compatibility predicate (via
    :func:`~app.services.ruleset_options.ruleset_supports_agent_metadata`)
    rather than a view-local rule. ``metadata`` is one entry per selected
    entrant; ``None`` entries mean "nothing selected in that slot".

    Selection repair is deterministic: a still-compatible current selection
    is always kept, and an incompatible one is replaced by the first
    product-preferred compatible option -- never by another incompatible
    one. Returns whether any compatible Ruleset exists, so a caller can
    disable execution instead of letting the engine discover the problem
    after launch.
    """

    selected = tuple(metadata)
    model = combo.model()
    for index in range(combo.count()):
        compatible = ruleset_supports_agent_metadata(str(combo.itemData(index)), selected)
        item = model.item(index) if model is not None else None
        if item is not None:
            item.setEnabled(compatible)

    offered = tuple(
        DesignerRulesetOption(str(combo.itemData(index)), combo.itemText(index))
        for index in range(combo.count())
    )
    replacement_id = best_designer_ruleset_for_agents(selected, offered)
    if replacement_id is not None and not ruleset_supports_agent_metadata(
        selected_ruleset_id(combo), selected
    ):
        replacement = combo.findData(replacement_id)
        if replacement >= 0:
            combo.setCurrentIndex(replacement)

    if explanation is not None:
        kinds = {
            item.get("kind")
            for item in selected
            if isinstance(item, dict)
        }
        if replacement_id is None:
            explanation.setText(NO_COMPATIBLE_RULESET_EXPLANATION)
            explanation.setVisible(True)
        elif kinds & {"vm", "builtin", "blob"}:
            explanation.setText(VM_RULESET_EXPLANATION)
            explanation.setVisible(True)
        else:
            explanation.setText("")
            explanation.setVisible(False)
    return replacement_id is not None


def sync_ruleset_choices(
    combo: QComboBox,
    agent_a: QComboBox,
    agent_b: QComboBox,
    explanation: QLabel,
) -> bool:
    """Match-selector wrapper: sync one Ruleset combo to two agent combos."""

    return sync_ruleset_choices_for_metadata(
        combo,
        (selected_agent_meta(agent_a), selected_agent_meta(agent_b)),
        explanation,
    )
