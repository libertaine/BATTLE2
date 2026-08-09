"""GUI regression coverage for the Phase 4a Agent Development tab.

Covers: AgentDevelopmentPanel's python-only catalog, the centralized
``refresh_agents(select=...)`` mechanism, the New Agent dialog (success,
duplicate, invalid id, custom data root), Open Agent Folder enablement, and
that existing Simple/Advanced selectors continue to function.

Marked ``gui`` like the existing Designer lifecycle tests: excluded from
the default headless run, exercised by the dedicated display-backed
workflow. Real (not mocked) ``battle_engine.agent_scaffold.create_agent``
calls are used throughout, per the Phase 4 spec's requirement that the
backend scaffold API is reused rather than duplicated in the GUI.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def _make_app():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.mark.gui
def test_agent_development_tab_present_and_catalog_filters_to_python_agents(monkeypatch, tmp_path):
    _make_app()
    from battle_engine.agent_scaffold import create_agent

    data_root = tmp_path / "data"
    monkeypatch.setenv("BATTLE2_ROOT", str(data_root))

    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        assert hasattr(designer, "development")
        assert designer.tabs.indexOf(designer.development) >= 0

        # Starter agents (runner/writer/seeker/spiral) are VM built-ins
        # (kind != python), so before creating any Python agent the
        # Agent Development combo must be empty even though Simple/Advanced
        # already show the starters.
        assert designer.simple.agentA.count() > 0
        assert designer.development.agentCombo.count() == 0

        create_agent("my_first_agent", data_root=data_root)
        designer.refresh_agents()

        names = [
            designer.development.agentCombo.itemText(i)
            for i in range(designer.development.agentCombo.count())
        ]
        assert names == ["my_first_agent"]
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_new_agent_dialog_success_refreshes_and_selects(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BATTLE2_ROOT", str(data_root))

    from app.agent_designer import AgentDesigner
    from app.views.development import NewAgentDialog

    designer = AgentDesigner()
    try:
        dialog = NewAgentDialog(designer.battle_root)
        dialog.agentId.setText("shiny_agent")
        dialog._on_ok()

        assert dialog.result is not None
        assert dialog.result.agent_id == "shiny_agent"
        assert dialog.result.manifest_path.is_file()
        assert dialog.result.source_path.is_file()

        designer.refresh_agents(select=dialog.result.agent_id)
        assert designer.development.agentCombo.currentText() == "shiny_agent"
        assert designer.development.selectedAgentRow() is not None
        assert designer.development.btnOpenFolder.isEnabled() is True
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_new_agent_dialog_duplicate_id_shows_inline_error_and_stays_open(monkeypatch, tmp_path):
    _make_app()
    from battle_engine.agent_scaffold import create_agent

    data_root = tmp_path / "data"
    create_agent("dup_agent", data_root=data_root)

    from app.views.development import NewAgentDialog

    dialog = NewAgentDialog(data_root)
    dialog.agentId.setText("dup_agent")
    dialog._on_ok()

    assert dialog.result is None
    assert dialog.isVisible() is False  # never shown via exec() in this unit test
    assert dialog.errorLabel.isVisibleTo(dialog) is True
    assert "already exists" in dialog.errorLabel.text()


@pytest.mark.gui
def test_new_agent_dialog_invalid_id_shows_inline_error_no_traceback(monkeypatch, tmp_path):
    _make_app()
    from app.views.development import NewAgentDialog

    data_root = tmp_path / "data"
    dialog = NewAgentDialog(data_root)
    dialog.agentId.setText("bad id with spaces")
    dialog._on_ok()

    assert dialog.result is None
    assert dialog.errorLabel.isVisibleTo(dialog) is True
    assert "Invalid agent id" in dialog.errorLabel.text()
    assert not (data_root / "agents" / "bad id with spaces").exists()


@pytest.mark.gui
def test_new_agent_dialog_empty_id_is_rejected_without_touching_backend(monkeypatch, tmp_path):
    _make_app()
    from app.views.development import NewAgentDialog

    data_root = tmp_path / "data"
    dialog = NewAgentDialog(data_root)
    dialog.agentId.setText("   ")
    dialog._on_ok()

    assert dialog.result is None
    assert dialog.errorLabel.isVisibleTo(dialog) is True
    assert not data_root.exists()


@pytest.mark.gui
def test_new_agent_dialog_respects_custom_data_root_with_spaces(monkeypatch, tmp_path):
    _make_app()
    from app.views.development import NewAgentDialog

    data_root = tmp_path / "Custom Data Root With Spaces"
    dialog = NewAgentDialog(data_root)
    dialog.agentId.setText("spaced_root_agent")
    dialog._on_ok()

    assert dialog.result is not None
    assert dialog.result.manifest_path == data_root / "agents" / "spaced_root_agent" / "agent.yaml"
    assert dialog.result.manifest_path.is_file()


@pytest.mark.gui
def test_open_folder_disabled_with_no_selection_and_enabled_after_creation(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BATTLE2_ROOT", str(data_root))

    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        assert designer.development.agentCombo.count() == 0
        assert designer.development.btnOpenFolder.isEnabled() is False

        from battle_engine.agent_scaffold import create_agent

        result = create_agent("folder_agent", data_root=data_root)
        designer.refresh_agents(select="folder_agent")

        assert designer.development.btnOpenFolder.isEnabled() is True
        row = designer.development.selectedAgentRow()
        assert row is not None
        assert row.path == str(result.manifest_path.parent)
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_open_agent_folder_calls_qdesktopservices_with_correct_path(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BATTLE2_ROOT", str(data_root))

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        from battle_engine.agent_scaffold import create_agent

        result = create_agent("openable_agent", data_root=data_root)
        designer.refresh_agents(select="openable_agent")

        captured: list[str] = []
        monkeypatch.setattr(
            agent_designer_module.QDesktopServices,
            "openUrl",
            staticmethod(lambda url: captured.append(url.toLocalFile())),
        )

        designer._on_open_agent_folder()

        assert len(captured) == 1
        assert Path(captured[0]) == result.manifest_path.parent
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_open_agent_folder_noop_when_nothing_selected(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BATTLE2_ROOT", str(data_root))

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        captured: list[str] = []
        monkeypatch.setattr(
            agent_designer_module.QDesktopServices,
            "openUrl",
            staticmethod(lambda url: captured.append(url.toLocalFile())),
        )
        monkeypatch.setattr(
            agent_designer_module.QMessageBox,
            "information",
            staticmethod(lambda *a, **k: None),
        )

        designer._on_open_agent_folder()

        assert captured == []
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_existing_simple_and_advanced_selectors_still_populate(monkeypatch, tmp_path):
    """Regression: starters (kind != python) must still appear in Simple/Advanced."""
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BATTLE2_ROOT", str(data_root))

    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        assert designer.simple.agentA.count() > 0
        assert designer.advanced.agentA.count() > 0
        # Development combo stays empty until a Python agent exists.
        assert designer.development.agentCombo.count() == 0
    finally:
        designer.deleteLater()
