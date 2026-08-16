"""Shared runtime-labeled agent combo-box behavior for match selectors.

Both the Simple and Advanced tabs show each agent's runtime kind next to
its name (``claimer [Python]``, ``runner [VM]``) and disable Agent B
choices whose runtime kind is incompatible with the selected Agent A --
the UX correction that surfaces the existing mixed-VM/Python-execution
restriction *before* a user attempts an invalid match, instead of only
after ``validate_homogeneous`` rejects it. This module is the one shared
implementation both tabs call, so the two selectors cannot drift apart.

The combo's ``DisplayRole`` is always the decorated label; the real,
undecorated discovery identifier (``AgentRow.agent_id``, with a
``row.name`` fallback for legacy rows) is stored under
``Qt.UserRole`` and must always be read back from there via
``selected_agent_name`` -- never recovered by stripping the visible
``[Python]``/``[VM]`` suffix back off the display text.
"""

from __future__ import annotations

from collections import Counter

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox

from app.services.agent_catalog import AgentRow
from app.services.designer_workflows import agent_kind, decorate_agent_display

_NAME_ROLE = Qt.ItemDataRole.UserRole
_KIND_ROLE = Qt.ItemDataRole.UserRole + 1


def populate_agent_combo(combo: QComboBox, rows: list[AgentRow]) -> None:
    """Repopulate ``combo`` with runtime-labeled items from ``rows``.

    Preserves the current selection by its real identifier (not display
    text or index) when that agent is still present in ``rows``. An empty
    catalog falls back to the same undecorated ``"(none found)"`` placeholder
    the combo showed before this change.
    """
    previous = combo.itemData(combo.currentIndex(), _NAME_ROLE) if combo.count() else None
    combo.blockSignals(True)
    combo.clear()
    if not rows:
        combo.addItem("(none found)")
    else:
        display_counts = Counter(row.name for row in rows)
        for row in rows:
            agent_id = row.agent_id or row.name
            label = decorate_agent_display(row)
            if display_counts[row.name] > 1:
                label = f"{label} ({agent_id})"
            combo.addItem(label)
            index = combo.count() - 1
            combo.setItemData(index, agent_id, _NAME_ROLE)
            combo.setItemData(index, agent_kind(row), _KIND_ROLE)
        if previous is not None:
            index = combo.findData(previous, _NAME_ROLE)
            if index >= 0:
                combo.setCurrentIndex(index)
    combo.blockSignals(False)


def selected_agent_name(combo: QComboBox) -> str | None:
    """The real, undecorated agent identifier behind the current selection."""
    return combo.itemData(combo.currentIndex(), _NAME_ROLE)


def selected_agent_kind(combo: QComboBox) -> str | None:
    """The runtime kind (``"python"``/``"vm"``) behind the current selection."""
    return combo.itemData(combo.currentIndex(), _KIND_ROLE)


def sync_compatible_b_choices(combo_a: QComboBox, combo_b: QComboBox) -> None:
    """Disable Agent B entries incompatible with Agent A, repairing an
    incompatible current B selection deterministically.

    Disabling (rather than hiding) uses Qt's own item-enabled flag, so an
    incompatible entry cannot be reached via mouse, keyboard, or wheel
    navigation in the popup, without removing it from view.

    Repair order, once Agent A has a valid selection:

    1. keep the current Agent B selection if it is still compatible;
    2. otherwise select the first compatible entry that names a
       *different* agent than Agent A, if one exists;
    3. otherwise fall back to the first compatible entry at all (a
       self-match is allowed when it is the only compatible choice);
    4. if Agent A has no resolvable runtime kind, leave every Agent B
       entry enabled -- there is nothing to filter against yet.
    """
    required_kind = selected_agent_kind(combo_a)
    model = combo_b.model()
    for index in range(combo_b.count()):
        kind = combo_b.itemData(index, _KIND_ROLE)
        compatible = required_kind is None or kind is None or kind == required_kind
        item = model.item(index) if model is not None else None
        if item is not None:
            item.setEnabled(compatible)
    if required_kind is None:
        return
    if selected_agent_kind(combo_b) == required_kind:
        return  # Current selection is already compatible; leave it alone.

    a_name = selected_agent_name(combo_a)
    fallback_index = -1
    for index in range(combo_b.count()):
        if combo_b.itemData(index, _KIND_ROLE) != required_kind:
            continue
        if fallback_index < 0:
            fallback_index = index
        if combo_b.itemData(index, _NAME_ROLE) != a_name:
            combo_b.setCurrentIndex(index)
            return
    if fallback_index >= 0:
        combo_b.setCurrentIndex(fallback_index)
