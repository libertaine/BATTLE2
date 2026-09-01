"""GUI regression coverage for the RC2 agent-runtime-compatibility UX correction.

Covers ``app.widgets.agent_combo`` directly (decoration, identifier
preservation, Agent B disabling/repair) plus the Simple and Advanced tabs'
own wiring of it, proving both tabs behave identically and that
``validate_homogeneous`` backend validation remains authoritative
regardless of what the UI now prevents.

Marked ``gui`` like the existing Designer tests: excluded from the default
headless run, exercised by the dedicated display-backed workflow.
"""

from __future__ import annotations

import os

import pytest


def _make_app():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _row(name: str, kind: str):
    from app.services.agent_catalog import AgentRow

    meta = {"name": name, "kind": kind}
    if kind == "python":
        meta["api_version"] = 1
    return AgentRow(name, f"/agents/{name}", None, meta)


def _rows():
    return [
        _row("claimer", "python"),
        _row("runner", "vm"),
        _row("hunter", "python"),
    ]


# ---------------------------------------------------------------------------
# app.widgets.agent_combo -- direct combo-box behavior
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_combo_shows_runtime_labels_but_stores_undecorated_identifier():
    _make_app()
    from PySide6.QtWidgets import QComboBox

    from app.widgets.agent_combo import populate_agent_combo, selected_agent_name

    combo = QComboBox()
    populate_agent_combo(combo, _rows())

    texts = [combo.itemText(i) for i in range(combo.count())]
    assert texts == ["claimer [Python]", "runner [VM]", "hunter [Python]"]

    combo.setCurrentIndex(1)
    assert selected_agent_name(combo) == "runner"  # never "runner [VM]"


@pytest.mark.gui
def test_combo_and_match_launch_use_discovery_ids_for_duplicate_display_names():
    _make_app()
    from app.services.agent_catalog import AgentRow
    from app.views.simple import SimplePanel

    rows = [
        AgentRow(
            "Friendly",
            "/agents/alpha_id",
            None,
            {"display": "Friendly", "kind": "python", "api_version": 1},
            agent_id="alpha_id",
        ),
        AgentRow(
            "Friendly",
            "/agents/beta_id",
            None,
            {"display": "Friendly", "kind": "python", "api_version": 1},
            agent_id="beta_id",
        ),
    ]
    panel = SimplePanel(catalog=None)
    panel.setAgents(rows)

    assert [panel.agentA.itemText(i) for i in range(2)] == [
        "Friendly [Python] (alpha_id)",
        "Friendly [Python] (beta_id)",
    ]
    panel.agentA.setCurrentIndex(0)
    panel.agentB.setCurrentIndex(1)
    captured = []
    panel.runRequested.connect(captured.append)
    panel._emit_run()

    assert captured[0].a_type == "alpha_id"
    assert captured[0].b_type == "beta_id"


@pytest.mark.gui
def test_selecting_python_a_disables_vm_b_entries():
    _make_app()
    from PySide6.QtWidgets import QComboBox

    from app.widgets.agent_combo import populate_agent_combo, sync_compatible_b_choices

    combo_a, combo_b = QComboBox(), QComboBox()
    populate_agent_combo(combo_a, _rows())
    populate_agent_combo(combo_b, _rows())

    combo_a.setCurrentIndex(0)  # claimer [Python]
    sync_compatible_b_choices(combo_a, combo_b)

    model = combo_b.model()
    enabled_by_text = {combo_b.itemText(i): model.item(i).isEnabled() for i in range(combo_b.count())}
    assert enabled_by_text == {
        "claimer [Python]": True,
        "runner [VM]": False,
        "hunter [Python]": True,
    }


@pytest.mark.gui
def test_selecting_vm_a_disables_python_b_entries():
    _make_app()
    from PySide6.QtWidgets import QComboBox

    from app.widgets.agent_combo import populate_agent_combo, sync_compatible_b_choices

    combo_a, combo_b = QComboBox(), QComboBox()
    populate_agent_combo(combo_a, _rows())
    populate_agent_combo(combo_b, _rows())

    combo_a.setCurrentIndex(1)  # runner [VM]
    sync_compatible_b_choices(combo_a, combo_b)

    model = combo_b.model()
    enabled_by_text = {combo_b.itemText(i): model.item(i).isEnabled() for i in range(combo_b.count())}
    assert enabled_by_text == {
        "claimer [Python]": False,
        "runner [VM]": True,
        "hunter [Python]": False,
    }


@pytest.mark.gui
def test_changing_a_repairs_an_incompatible_current_b_selection():
    _make_app()
    from PySide6.QtWidgets import QComboBox

    from app.widgets.agent_combo import (
        populate_agent_combo,
        selected_agent_name,
        sync_compatible_b_choices,
    )

    combo_a, combo_b = QComboBox(), QComboBox()
    populate_agent_combo(combo_a, _rows())
    populate_agent_combo(combo_b, _rows())

    # Both start on claimer (compatible); now flip A to the VM agent.
    combo_a.setCurrentIndex(0)
    combo_b.setCurrentIndex(0)
    sync_compatible_b_choices(combo_a, combo_b)
    assert selected_agent_name(combo_b) == "claimer"  # untouched; still compatible

    combo_a.setCurrentIndex(1)  # runner [VM]
    sync_compatible_b_choices(combo_a, combo_b)
    # Only one VM agent exists in this catalog -- self-match is the only
    # compatible choice, and is allowed (task Sec 8 item 4).
    assert selected_agent_name(combo_b) == "runner"

    combo_a.setCurrentIndex(0)  # back to claimer [Python]
    sync_compatible_b_choices(combo_a, combo_b)
    # Repaired B was VM; two Python agents exist (claimer, hunter) so the
    # repair must prefer the one different from A (Sec 8 item 3).
    assert selected_agent_name(combo_b) == "hunter"


@pytest.mark.gui
def test_selection_preserved_by_identifier_across_repopulation():
    _make_app()
    from PySide6.QtWidgets import QComboBox

    from app.widgets.agent_combo import populate_agent_combo, selected_agent_name

    combo = QComboBox()
    populate_agent_combo(combo, _rows())
    combo.setCurrentIndex(2)  # hunter
    assert selected_agent_name(combo) == "hunter"

    # Re-populate with the exact same catalog (a "Refresh Agents" click).
    populate_agent_combo(combo, _rows())
    assert selected_agent_name(combo) == "hunter"

    # Now the previously selected agent is gone -- falls back to the first entry.
    populate_agent_combo(combo, [_row("claimer", "python"), _row("runner", "vm")])
    assert selected_agent_name(combo) == "claimer"


@pytest.mark.gui
def test_empty_catalog_shows_placeholder_and_no_crash_on_sync():
    _make_app()
    from PySide6.QtWidgets import QComboBox

    from app.widgets.agent_combo import (
        populate_agent_combo,
        selected_agent_name,
        sync_compatible_b_choices,
    )

    combo_a, combo_b = QComboBox(), QComboBox()
    populate_agent_combo(combo_a, [])
    populate_agent_combo(combo_b, [])
    assert combo_a.itemText(0) == "(none found)"
    assert selected_agent_name(combo_a) is None

    sync_compatible_b_choices(combo_a, combo_b)  # must not raise
    assert combo_b.model().item(0).isEnabled() is True


# ---------------------------------------------------------------------------
# SimplePanel / AdvancedPanel -- both tabs wired identically
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_simple_panel_filters_from_ruleset_and_emits_real_identifiers():
    _make_app()
    from app.views.simple import SimplePanel

    panel = SimplePanel(catalog=None)
    panel.setAgents(_rows())
    panel.agentA.setCurrentIndex(0)  # claimer [Python]

    assert panel.ruleset.findData("bytefray-rules-1") == -1
    assert [panel.agentB.itemData(i) for i in range(panel.agentB.count())] == [
        "claimer",
        "hunter",
    ]

    captured = []
    panel.runRequested.connect(captured.append)
    panel.agentB.setCurrentIndex(panel.agentB.findData("hunter"))
    panel._emit_run()

    assert len(captured) == 1
    assert captured[0].a_type == "claimer"
    assert captured[0].b_type == "hunter"
    assert captured[0].ruleset_id == "bytefray-rules-2"


@pytest.mark.gui
def test_simple_ruleset_change_filters_api_generation_and_repairs_deterministically():
    _make_app()
    from app.services.agent_catalog import AgentRow
    from app.views.simple import SimplePanel

    rows = [
        _row("legacy_a", "python"),
        _row("vm_agent", "vm"),
        AgentRow(
            "Process A",
            "/agents/process_a",
            None,
            {"kind": "python", "api_version": 2},
            agent_id="process_a",
        ),
        AgentRow(
            "Process B",
            "/agents/process_b",
            None,
            {"kind": "python", "api_version": 2},
            agent_id="process_b",
        ),
        _row("legacy_b", "python"),
    ]
    panel = SimplePanel(catalog=None)
    panel.setAgents(rows)

    assert panel.ruleset.currentData() == "bytefray-rules-2"
    assert [panel.agentA.itemData(i) for i in range(panel.agentA.count())] == [
        "legacy_a",
        "legacy_b",
    ]
    assert panel.agentA.currentData() == "legacy_a"
    assert panel.agentB.currentData() == "legacy_b"

    panel.agentA.setCurrentIndex(panel.agentA.findData("legacy_b"))
    panel.setAgents(rows)
    assert panel.agentA.currentData() == "legacy_b"

    # Simple offers current gameplay only, so its Agent API v2 choice is
    # v4 alpha2; alpha1 stays selectable from Advanced/Development.
    panel.ruleset.setCurrentIndex(panel.ruleset.findData("bytefray-rules-4-alpha2"))
    assert [panel.agentA.itemData(i) for i in range(panel.agentA.count())] == [
        "process_a",
        "process_b",
    ]
    assert panel.agentA.currentData() == "process_a"
    assert panel.agentB.currentData() == "process_b"


@pytest.mark.gui
def test_simple_one_agent_allows_self_match_and_empty_state_prevents_launch():
    _make_app()
    from app.views.simple import SimplePanel

    panel = SimplePanel(catalog=None)
    panel.setAgents([_row("only_v1", "python")])
    assert panel.agentA.currentData() == panel.agentB.currentData() == "only_v1"
    assert panel.btnRun.isEnabled()

    captured = []
    panel.runRequested.connect(captured.append)
    panel.ruleset.setCurrentIndex(panel.ruleset.findData("bytefray-rules-4-alpha1"))
    assert panel.agentA.itemText(0) == "(none found)"
    assert panel.agentB.itemText(0) == "(none found)"
    assert not panel.btnRun.isEnabled()
    assert "No compatible agents" in panel.rulesetExplanation.text()

    panel._emit_run()
    assert captured == []
    assert "No compatible agents" in panel.log.toPlainText()


@pytest.mark.gui
def test_advanced_panel_matches_simple_panel_behavior(tmp_path):
    _make_app()
    from app.services.ruleset_options import VM_RULESET_EXPLANATION
    from app.views.advanced import AdvancedPanel

    panel = AdvancedPanel(catalog=None, data_root=tmp_path)
    panel.setAgents(_rows())
    panel.agentA.setCurrentIndex(1)  # runner [VM]

    model = panel.agentB.model()
    assert model.item(0).isEnabled() is False  # claimer [Python]
    assert model.item(1).isEnabled() is True  # runner [VM]
    assert model.item(2).isEnabled() is False  # hunter [Python]

    texts = [panel.agentA.itemText(i) for i in range(panel.agentA.count())]
    assert texts == ["claimer [Python]", "runner [VM]", "hunter [Python]"]

    captured = []
    panel.runRequested.connect(captured.append)
    panel._emit_run()

    assert len(captured) == 1
    assert captured[0].a_type == "runner"
    assert captured[0].b_type == "runner"  # self-match: the only compatible B
    assert captured[0].ruleset_id == "bytefray-rules-1"
    v2_index = panel.ruleset.findData("bytefray-rules-2")
    assert panel.ruleset.model().item(v2_index).isEnabled() is False
    # v3.0.0-alpha2 replaced "Ruleset v1 is required for VM/blob matches."
    # with copy that also states the converse (v2 is Python-only), so a
    # reader learns the whole compatibility rule rather than half of it.
    # Asserted against the shared constant, not a duplicated literal.
    assert panel.rulesetExplanation.text() == VM_RULESET_EXPLANATION
    assert "Ruleset v1 only" in panel.rulesetExplanation.text()


# ---------------------------------------------------------------------------
# Regression: the exact user-discovered scenario (task Sec 16)
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_regression_simple_filters_while_advanced_keeps_historical_catalog(tmp_path):
    _make_app()
    from app.views.advanced import AdvancedPanel
    from app.views.simple import SimplePanel

    rows = _rows()  # claimer [Python], runner [VM], hunter [Python]
    simple = SimplePanel(catalog=None)
    advanced = AdvancedPanel(catalog=None, data_root=tmp_path)

    simple.setAgents(rows)
    assert [simple.agentA.itemData(i) for i in range(simple.agentA.count())] == [
        "claimer",
        "hunter",
    ]

    advanced.setAgents(rows)
    assert [advanced.agentA.itemData(i) for i in range(advanced.agentA.count())] == [
        "claimer",
        "runner",
        "hunter",
    ]
    advanced.agentA.setCurrentIndex(1)
    assert advanced.ruleset.currentData() == "bytefray-rules-1"
