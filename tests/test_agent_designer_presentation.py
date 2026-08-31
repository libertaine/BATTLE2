"""Focused Qt coverage for Beta3 Agent Designer presentation state."""

from __future__ import annotations

import os

import pytest


def _make_app():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _row(agent_id: str, display: str, *, kind: str = "python"):
    from app.services.agent_catalog import AgentRow

    return AgentRow(
        name=display,
        path=f"/agents/{agent_id}",
        blob_path=None,
        meta={
            "name": agent_id,
            "display": display,
            "kind": kind,
            **({"api_version": 1} if kind == "python" else {}),
        },
        agent_id=agent_id,
    )


@pytest.mark.gui
def test_simple_panel_starts_with_real_empty_state_and_current_matchup():
    _make_app()
    from app.views.simple import SimplePanel

    panel = SimplePanel(catalog=None)
    panel.setAgents([_row("alpha", "Alpha"), _row("beta", "Beta")])

    assert panel.output.is_showing_empty_state() is True
    assert panel.output.readyLabel.text() == "Ready to run a match"
    assert panel.output.matchupLabel.text() == "Alpha [Python] vs Beta [Python]"
    assert panel.output.guidanceLabel.text() == (
        "Choose two compatible agents, then Run Match."
    )
    assert panel.log.toPlainText() == ""
    assert panel.output.matchupLabel.accessibleName() == "Selected matchup"
    assert panel.output.guidanceLabel.accessibleName() == "Next action"


@pytest.mark.gui
def test_empty_matchup_updates_by_disambiguated_labels_and_supports_self_match():
    _make_app()
    from app.views.simple import SimplePanel

    panel = SimplePanel(catalog=None)
    panel.setAgents([_row("alpha_id", "Friendly"), _row("beta_id", "Friendly")])

    panel.agentA.setCurrentIndex(panel.agentA.findData("beta_id"))
    panel.agentB.setCurrentIndex(panel.agentB.findData("beta_id"))

    assert panel.output.is_showing_empty_state() is True
    assert panel.output.matchupLabel.text() == (
        "Friendly [Python] (beta_id) vs Friendly [Python] (beta_id)"
    )
    assert panel.log.toPlainText() == ""


@pytest.mark.gui
def test_real_output_replaces_empty_state_without_polluting_log():
    _make_app()
    from app.views.simple import SimplePanel

    panel = SimplePanel(catalog=None)
    panel.setAgents([_row("alpha", "Alpha"), _row("beta", "Beta")])

    panel.appendLog("\n")
    assert panel.output.is_showing_empty_state() is True

    panel.appendLog("[RunMatch] starting\n")
    panel.appendLog("engine output\n")

    assert panel.output.currentWidget() is panel.log
    assert panel.log.toPlainText() == "[RunMatch] starting\nengine output"
    assert "Ready to run a match" not in panel.log.toPlainText()
    assert "Choose two compatible agents" not in panel.log.toPlainText()


@pytest.mark.gui
def test_clear_log_restores_current_empty_state_and_second_output_replaces_it():
    _make_app()
    from app.views.simple import SimplePanel

    panel = SimplePanel(catalog=None)
    panel.setAgents([_row("alpha", "Alpha"), _row("beta", "Beta")])
    panel.appendLog("first run")
    panel.agentA.setCurrentIndex(panel.agentA.findData("beta"))
    panel.agentB.setCurrentIndex(panel.agentB.findData("beta"))

    panel.clearLog()

    assert panel.output.is_showing_empty_state() is True
    assert panel.log.toPlainText() == ""
    assert panel.output.matchupLabel.text() == "Beta [Python] vs Beta [Python]"

    panel.appendLog("second run")
    assert panel.output.currentWidget() is panel.log
    assert panel.log.toPlainText() == "second run"


@pytest.mark.gui
def test_identity_header_uses_shared_source_icon_and_real_accessible_text():
    _make_app()
    from app.widgets.designer_presentation import DesignerIdentityHeader

    header = DesignerIdentityHeader()

    assert header.titleLabel.text() == "Bytefray Agent Designer"
    assert header.purposeLabel.text() == (
        "Build, test, and compare programmable agents."
    )
    assert header.titleLabel.accessibleName() == "Application"
    assert header.iconLabel.pixmap() is not None
    assert header.iconLabel.pixmap().isNull() is False


@pytest.mark.gui
def test_identity_header_degrades_to_text_when_optional_icon_is_missing(monkeypatch):
    _make_app()
    import app.widgets.designer_presentation as presentation

    monkeypatch.setattr(presentation, "get_branding_icon_path", lambda: None)
    header = presentation.DesignerIdentityHeader()

    assert header.iconLabel.isHidden() is True
    assert header.titleLabel.text() == "Bytefray Agent Designer"
    assert header.purposeLabel.text()


@pytest.mark.gui
def test_designer_keeps_tab_shell_and_structured_quick_match_layout(monkeypatch, tmp_path):
    _make_app()
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QGridLayout, QGroupBox, QLabel

    from app.agent_designer import AgentDesigner

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path / "data"))
    designer = AgentDesigner()
    central_layout = designer.centralWidget().layout()

    assert central_layout.indexOf(designer.identityHeader) >= 0
    assert central_layout.indexOf(designer.tabs) >= 0
    assert designer.tabs.indexOf(designer.simple) >= 0
    assert designer.tabs.tabText(designer.tabs.indexOf(designer.simple)) == "Simple"

    quick_match = next(
        group
        for group in designer.simple.findChildren(QGroupBox)
        if group.title() == "Quick Match"
    )
    assert isinstance(quick_match.layout().itemAt(0).layout(), QGridLayout)
    assert designer.simple.btnRun.font().bold() is True
    assert designer.simple.btnRun.focusPolicy() != Qt.FocusPolicy.NoFocus
    for text, control in (
        ("Ruleset", designer.simple.ruleset),
        ("Agent A", designer.simple.agentA),
        ("Agent B", designer.simple.agentB),
        ("Grid", designer.simple.gridSize),
        ("Ticks", designer.simple.ticks),
    ):
        label = next(
            candidate
            for candidate in quick_match.findChildren(QLabel)
            if candidate.text() == text
        )
        assert label.buddy() is control

    designer.deleteLater()
