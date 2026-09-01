"""GUI regression coverage for the Phase 2 M1 compatibility convergence.

Before this, only the Simple tab asked the engine's Agent-API-aware
compatibility question. Advanced asked a narrower runtime-kind-only one (so
an Agent API v2 agent was offered Ruleset v2, which cannot run it), and
Development/Evaluation asked nothing at all, offering every Ruleset and
relying on the engine to reject the match after launch.

These pin the converged behavior at each surface. The *rules* themselves
are pinned once, headlessly, against the engine policy in
``engine/tests/test_designer_ruleset_options.py``; what these add is that
each view actually applies them, including selection repair and the
fail-closed empty state.

Marked ``gui`` like the other Designer tests: excluded from the default
headless run, exercised by the dedicated display-backed workflow.
"""

from __future__ import annotations

import os

import pytest

BYTEFRAY_RULESET_ID = "bytefray-rules-1"
BYTEFRAY_RULESET_V2_ID = "bytefray-rules-2"
BYTEFRAY_RULESET_V4_ALPHA1_ID = "bytefray-rules-4-alpha1"


def _make_app():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _row(name: str, kind: str, api_version: int | None = None):
    from app.services.agent_catalog import AgentRow

    meta: dict[str, object] = {"name": name, "kind": kind}
    if api_version is not None:
        meta["api_version"] = api_version
    return AgentRow(name, f"/agents/{name}", None, meta, agent_id=name)


def _offered(combo) -> set[str]:
    """Ruleset ids the combo presents as selectable."""

    model = combo.model()
    return {
        str(combo.itemData(index))
        for index in range(combo.count())
        if model is None or model.item(index) is None or model.item(index).isEnabled()
    }


# ---------------------------------------------------------------------------
# Advanced
# ---------------------------------------------------------------------------


@pytest.mark.gui
@pytest.mark.parametrize(
    ("api_version", "expected_offered"),
    [
        (1, {BYTEFRAY_RULESET_V2_ID, BYTEFRAY_RULESET_ID}),
        (2, {BYTEFRAY_RULESET_V4_ALPHA1_ID}),
    ],
)
def test_advanced_offers_only_rulesets_the_selected_agents_can_run(
    tmp_path, api_version, expected_offered
):
    _make_app()
    from app.views.advanced import AdvancedPanel

    panel = AdvancedPanel(catalog=None, data_root=tmp_path)
    try:
        panel.setAgents([_row("a", "python", api_version), _row("b", "python", api_version)])
        assert _offered(panel.ruleset) == expected_offered
        assert panel.ruleset.currentData() in expected_offered
        assert panel.btnRun.isEnabled()
    finally:
        panel.deleteLater()


@pytest.mark.gui
def test_advanced_keeps_a_compatible_selection_and_repairs_an_incompatible_one(tmp_path):
    _make_app()
    from app.views.advanced import AdvancedPanel

    panel = AdvancedPanel(catalog=None, data_root=tmp_path)
    try:
        panel.setAgents([_row("legacy", "python", 1), _row("legacy2", "python", 1)])
        # Ruleset v1 is compatible with Agent API v1, so an explicit choice
        # of it must survive a re-sync rather than snapping back to v2.
        panel.ruleset.setCurrentIndex(panel.ruleset.findData(BYTEFRAY_RULESET_ID))
        panel.setAgents([_row("legacy", "python", 1), _row("legacy2", "python", 1)])
        assert panel.ruleset.currentData() == BYTEFRAY_RULESET_ID

        # Switching to Agent API v2 agents makes that selection incompatible;
        # it is replaced by the deterministic first compatible option, never
        # left on an incompatible one.
        panel.setAgents([_row("proc", "python", 2), _row("proc2", "python", 2)])
        assert panel.ruleset.currentData() == BYTEFRAY_RULESET_V4_ALPHA1_ID
    finally:
        panel.deleteLater()


@pytest.mark.gui
def test_advanced_disables_running_when_no_ruleset_supports_the_pairing(tmp_path):
    _make_app()
    from app.views.advanced import AdvancedPanel

    panel = AdvancedPanel(catalog=None, data_root=tmp_path)
    try:
        panel.setAgents([_row("legacy", "python", 1), _row("proc", "python", 2)])
        panel.agentA.setCurrentIndex(0)
        panel.agentB.setCurrentIndex(1)

        assert _offered(panel.ruleset) == set()
        assert not panel.btnRun.isEnabled()
        assert panel.rulesetExplanation.isVisibleTo(panel)
        assert "No available Ruleset" in panel.rulesetExplanation.text()

        # Becoming idle must not quietly re-enable an impossible match.
        panel.setBusy(True)
        panel.setBusy(False)
        assert not panel.btnRun.isEnabled()
    finally:
        panel.deleteLater()


@pytest.mark.gui
def test_advanced_vm_selection_keeps_its_existing_ruleset_v1_behavior(tmp_path):
    _make_app()
    from app.views.advanced import AdvancedPanel

    panel = AdvancedPanel(catalog=None, data_root=tmp_path)
    try:
        panel.setAgents([_row("runner", "builtin"), _row("writer", "builtin")])
        assert _offered(panel.ruleset) == {BYTEFRAY_RULESET_ID}
        assert panel.ruleset.currentData() == BYTEFRAY_RULESET_ID
        assert panel.btnRun.isEnabled()
        assert "VM/blob agents run under Ruleset v1 only" in panel.rulesetExplanation.text()
    finally:
        panel.deleteLater()


# ---------------------------------------------------------------------------
# Simple (known-good reference: behavior must not change)
# ---------------------------------------------------------------------------


@pytest.mark.gui
@pytest.mark.parametrize(
    ("ruleset_id", "expected_agents"),
    [
        (BYTEFRAY_RULESET_V2_ID, ["legacy"]),
        (BYTEFRAY_RULESET_V4_ALPHA1_ID, ["proc"]),
    ],
)
def test_simple_still_filters_agents_by_the_selected_ruleset(
    ruleset_id, expected_agents
):
    """Simple's Ruleset-first UX is the reference this phase converged on;
    it must be unchanged by the shared-helper extraction."""

    _make_app()
    from app.views.simple import SimplePanel

    panel = SimplePanel(catalog=None)
    try:
        panel.setAgents([_row("legacy", "python", 1), _row("proc", "python", 2)])
        panel.ruleset.setCurrentIndex(panel.ruleset.findData(ruleset_id))
        listed = [panel.agentA.itemData(i) for i in range(panel.agentA.count())]
        assert listed == expected_agents
        assert panel.btnRun.isEnabled()
    finally:
        panel.deleteLater()


# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------


@pytest.mark.gui
@pytest.mark.parametrize(
    ("api_version", "expected_offered"),
    [
        (1, {BYTEFRAY_RULESET_V2_ID, BYTEFRAY_RULESET_ID}),
        (2, {BYTEFRAY_RULESET_V4_ALPHA1_ID}),
    ],
)
def test_development_offers_only_rulesets_the_selected_agent_can_run(
    api_version, expected_offered
):
    _make_app()
    from app.views.development import AgentDevelopmentPanel

    panel = AgentDevelopmentPanel()
    try:
        panel.setAgents([_row("probe", "python", api_version)])
        panel.selectAgent("probe")
        assert _offered(panel.rulesetCombo) == expected_offered
        assert panel.selected_ruleset_id() in expected_offered
        assert panel.btnTest.isEnabled()
    finally:
        panel.deleteLater()


@pytest.mark.gui
def test_development_keeps_listing_every_python_agent_regardless_of_api_version():
    """Only the Ruleset choices narrow: this tab must stay usable for
    historical Agent API v1 agents and current Agent API v2 ones alike."""

    _make_app()
    from app.views.development import AgentDevelopmentPanel

    panel = AgentDevelopmentPanel()
    try:
        panel.setAgents([_row("legacy", "python", 1), _row("proc", "python", 2)])
        listed = [panel.agentCombo.itemData(i) for i in range(panel.agentCombo.count())]
        assert listed == ["legacy", "proc"]
    finally:
        panel.deleteLater()


@pytest.mark.gui
def test_development_reapplies_compatibility_when_the_selection_changes():
    _make_app()
    from app.views.development import AgentDevelopmentPanel

    panel = AgentDevelopmentPanel()
    try:
        panel.setAgents([_row("legacy", "python", 1), _row("proc", "python", 2)])
        panel.selectAgent("legacy")
        assert panel.selected_ruleset_id() == BYTEFRAY_RULESET_V2_ID

        panel.selectAgent("proc")
        assert panel.selected_ruleset_id() == BYTEFRAY_RULESET_V4_ALPHA1_ID
        assert _offered(panel.rulesetCombo) == {BYTEFRAY_RULESET_V4_ALPHA1_ID}
    finally:
        panel.deleteLater()


@pytest.mark.gui
def test_development_disables_test_for_an_incompatible_explicit_opponent():
    """An explicitly chosen opponent is a real entrant, so a mixed Agent API
    pairing must fail closed in the UI -- the internal Reference opponent,
    which adapts to the resolved Ruleset, must not."""

    _make_app()
    from app.views.development import AgentDevelopmentPanel

    panel = AgentDevelopmentPanel()
    try:
        panel.setAgents([_row("legacy", "python", 1), _row("proc", "python", 2)])
        panel.selectAgent("proc")
        assert panel.selected_opponent_id() is None  # Reference
        assert panel.btnTest.isEnabled()

        panel.opponentCombo.setCurrentIndex(panel.opponentCombo.findData("legacy"))
        assert _offered(panel.rulesetCombo) == set()
        assert not panel.btnTest.isEnabled()

        # Returning to the adaptable Reference opponent restores it.
        panel.opponentCombo.setCurrentIndex(panel.opponentCombo.findData(None))
        assert panel.btnTest.isEnabled()
    finally:
        panel.deleteLater()


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def _evaluation_dialog(tmp_path, default_candidate, with_metadata=True):
    from app.views.evaluation import EvaluationDialog

    metadata = {
        "legacy": {"kind": "python", "api_version": 1},
        "proc": {"kind": "python", "api_version": 2},
    }
    return EvaluationDialog(
        [("legacy", "legacy"), ("proc", "proc")],
        default_candidate=default_candidate,
        default_output=tmp_path / "out",
        agent_metadata=metadata if with_metadata else None,
    )


@pytest.mark.gui
@pytest.mark.parametrize(
    ("candidate", "expected_offered"),
    [
        ("legacy", {BYTEFRAY_RULESET_V2_ID, BYTEFRAY_RULESET_ID}),
        ("proc", {BYTEFRAY_RULESET_V4_ALPHA1_ID}),
    ],
)
def test_evaluation_offers_only_rulesets_the_candidate_can_run(
    tmp_path, candidate, expected_offered
):
    _make_app()
    dialog = _evaluation_dialog(tmp_path, candidate)
    try:
        assert _offered(dialog.pairwiseRulesetCombo) == expected_offered
        assert dialog.pairwise_ruleset_id() in expected_offered
        assert dialog.runButton.isEnabled()
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_evaluation_evaluates_compatibility_across_the_whole_roster(tmp_path):
    """Not just the candidate: an incompatible opponent narrows the choices
    exactly as an incompatible candidate does."""

    from PySide6.QtCore import Qt

    _make_app()
    dialog = _evaluation_dialog(tmp_path, "proc")
    try:
        assert _offered(dialog.pairwiseRulesetCombo) == {BYTEFRAY_RULESET_V4_ALPHA1_ID}
        for index in range(dialog.opponentsList.count()):
            item = dialog.opponentsList.item(index)
            if item.data(Qt.UserRole) == "legacy":
                item.setSelected(True)
        assert _offered(dialog.pairwiseRulesetCombo) == set()
        assert not dialog.runButton.isEnabled()
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_evaluation_without_supplied_metadata_keeps_previous_behavior(tmp_path):
    """A programmatic caller or test double that supplies no metadata must
    not have every Ruleset silently disabled by its absence."""

    _make_app()
    dialog = _evaluation_dialog(tmp_path, "proc", with_metadata=False)
    try:
        assert len(_offered(dialog.pairwiseRulesetCombo)) == dialog.pairwiseRulesetCombo.count()
        assert dialog.runButton.isEnabled()
    finally:
        dialog.deleteLater()
