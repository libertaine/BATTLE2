"""Shared Agent Designer Ruleset combo-box behavior."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QLabel

from app.services.ruleset_options import (
    DESIGNER_RULESET_OPTIONS,
    RULESET_DESCRIPTION,
    VM_RULESET_EXPLANATION,
    best_designer_ruleset,
    ruleset_supports_runtime_kinds,
)
from app.widgets.agent_combo import selected_agent_kind


def populate_ruleset_combo(combo: QComboBox) -> None:
    combo.clear()
    for option in DESIGNER_RULESET_OPTIONS:
        combo.addItem(option.label, option.ruleset_id)
    combo.setToolTip(RULESET_DESCRIPTION)
    combo.setAccessibleDescription(RULESET_DESCRIPTION)


def selected_ruleset_id(combo: QComboBox) -> str:
    return str(combo.currentData())


def sync_ruleset_choices(
    combo: QComboBox,
    agent_a: QComboBox,
    agent_b: QComboBox,
    explanation: QLabel,
) -> None:
    """Disable incompatible choices and deterministically repair selection."""
    kinds = {
        kind
        for kind in (selected_agent_kind(agent_a), selected_agent_kind(agent_b))
        if kind is not None
    }
    model = combo.model()
    for index in range(combo.count()):
        compatible = ruleset_supports_runtime_kinds(str(combo.itemData(index)), kinds)
        item = model.item(index) if model is not None else None
        if item is not None:
            item.setEnabled(compatible)

    current_id = selected_ruleset_id(combo)
    if not ruleset_supports_runtime_kinds(current_id, kinds):
        replacement = combo.findData(best_designer_ruleset(kinds))
        if replacement >= 0:
            combo.setCurrentIndex(replacement)

    requires_v1 = "vm" in kinds
    explanation.setText(VM_RULESET_EXPLANATION if requires_v1 else "")
    explanation.setVisible(requires_v1)
