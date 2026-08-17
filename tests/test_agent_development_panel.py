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
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))

    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        assert hasattr(designer, "development")
        assert designer.tabs.indexOf(designer.development) >= 0

        # Bytefray seeds both VM starters (kind != python) and Python
        # starters (kind == python) at startup -- see
        # battle_engine.starters. The Agent Development combo must show
        # only the Python ones. Identify them by discovery id (independent
        # of the catalog's current size or ordering) so this keeps holding
        # if the starter roster grows on either side of that split.
        assert designer.simple.agentA.count() > 0
        catalog_rows = designer.catalog.list_agents()
        python_ids = {row.agent_id for row in catalog_rows if row.meta.get("kind") == "python"}
        non_python_ids = {row.agent_id for row in catalog_rows if row.meta.get("kind") != "python"}
        assert python_ids, "expected at least one Python starter agent"
        assert non_python_ids, "expected at least one non-Python (VM) starter agent"

        dev_ids_before = {agent_id for _, agent_id in designer.development.python_agent_names()}
        assert dev_ids_before == python_ids
        assert dev_ids_before.isdisjoint(non_python_ids)

        create_agent("my_first_agent", data_root=data_root)
        designer.refresh_agents()

        dev_ids_after = {agent_id for _, agent_id in designer.development.python_agent_names()}
        assert dev_ids_after == dev_ids_before | {"my_first_agent"}
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_new_agent_dialog_success_refreshes_and_selects(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))

    from app.agent_designer import AgentDesigner
    from app.views.development import NewAgentDialog

    designer = AgentDesigner()
    try:
        dialog = NewAgentDialog(designer.data_root)
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
def test_open_folder_disabled_with_no_agents():
    """Isolated panel unit test: no catalog means nothing is selectable.

    Uses a bare ``AgentDevelopmentPanel`` (same pattern as the panel's other
    presentation-only tests below) rather than a full ``AgentDesigner``,
    because Bytefray's real startup always seeds Python starter agents
    (``battle_engine.starters``) -- there is no way to observe a genuinely
    empty, nothing-selected catalog through the full Designer anymore.
    """
    _make_app()
    from app.views.development import AgentDevelopmentPanel

    panel = AgentDevelopmentPanel()
    try:
        assert panel.agentCombo.count() == 0
        assert panel.btnOpenFolder.isEnabled() is False
    finally:
        panel.deleteLater()


@pytest.mark.gui
def test_development_selection_and_state_invalidation_use_exact_agent_id(tmp_path):
    _make_app()
    from app.services.agent_catalog import AgentRow
    from app.views.development import AgentDevelopmentPanel

    first_dir = tmp_path / "alpha_id"
    second_dir = tmp_path / "beta_id"
    first_dir.mkdir()
    second_dir.mkdir()
    rows = [
        AgentRow(
            "Friendly",
            str(first_dir),
            None,
            {"display": "Friendly", "kind": "python"},
            agent_id="alpha_id",
        ),
        AgentRow(
            "Friendly",
            str(second_dir),
            None,
            {"display": "Friendly", "kind": "python"},
            agent_id="beta_id",
        ),
    ]
    panel = AgentDevelopmentPanel()
    try:
        panel.setAgents(rows)
        panel.selectAgent("beta_id")
        selected = panel.selectedAgentRow()
        assert selected is not None
        assert selected.agent_id == "beta_id"
        assert panel.agentCombo.currentText() == "Friendly (beta_id)"
        assert panel.selected_opponent_id() in {None, "alpha_id", "beta_id"}

        panel._last_validation = object()  # type: ignore[assignment]
        panel._last_test = object()  # type: ignore[assignment]
        panel._last_test_replay = tmp_path / "stale-replay.jsonl"
        panel._last_test_trace = tmp_path / "stale-trace.jsonl"
        panel.btnOpenTestReplay.setEnabled(True)
        panel.btnInspectTrace.setEnabled(True)
        before = panel.statusLabel.text()

        panel.invalidateAgentState("alpha_id", "restored older source")
        assert panel.statusLabel.text() == before  # wrong duplicate-display row: no-op

        panel.invalidateAgentState("beta_id", "restored older source")
        assert panel._last_validation is None
        assert panel._last_test is None
        assert panel.last_test_replay_path() is None
        assert panel.last_test_trace_path() is None
        assert panel.btnOpenTestReplay.isEnabled() is False
        assert panel.btnInspectTrace.isEnabled() is False
        assert "Source changed" in panel.statusLabel.text()
        assert "restored older source" in panel.statusLabel.text()
        assert "results were cleared" in panel.testStatusLabel.text()
    finally:
        panel.deleteLater()


@pytest.mark.gui
def test_open_folder_enabled_after_creation_and_selection(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))

    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        from battle_engine.agent_scaffold import create_agent

        result = create_agent("folder_agent", data_root=data_root)
        designer.refresh_agents(select="folder_agent")

        assert designer.development.agentCombo.currentText() == "folder_agent"
        assert designer.development.btnOpenFolder.isEnabled() is True
        row = designer.development.selectedAgentRow()
        assert row is not None
        assert row.agent_id == "folder_agent"
        assert row.path == str(result.manifest_path.parent)
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_open_agent_folder_calls_qdesktopservices_with_correct_path(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))

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
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        # Force an empty Python-agent catalog so nothing is selectable, even
        # though Bytefray now seeds Python starter agents by default (see
        # battle_engine.starters). Open Agent Folder's "nothing selected"
        # guard is still real production behavior (app.agent_designer
        # ._on_open_agent_folder) and needs its own coverage independent of
        # startup seeding.
        designer.development.setAgents([])
        assert designer.development.selectedAgentRow() is None

        captured: list[str] = []
        informed: list[bool] = []
        monkeypatch.setattr(
            agent_designer_module.QDesktopServices,
            "openUrl",
            staticmethod(lambda url: captured.append(url.toLocalFile())),
        )
        monkeypatch.setattr(
            agent_designer_module.QMessageBox,
            "information",
            staticmethod(lambda *a, **k: informed.append(True)),
        )

        designer._on_open_agent_folder()

        assert captured == []
        assert informed == [True]
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_existing_simple_and_advanced_selectors_still_populate(monkeypatch, tmp_path):
    """Regression: starters (kind != python) must still appear in Simple/Advanced."""
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))

    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        assert designer.simple.agentA.count() > 0
        assert designer.advanced.agentA.count() > 0

        catalog_rows = designer.catalog.list_agents()
        python_ids = {row.agent_id for row in catalog_rows if row.meta.get("kind") == "python"}
        non_python_ids = {row.agent_id for row in catalog_rows if row.meta.get("kind") != "python"}
        assert non_python_ids, "expected at least one non-Python (VM) starter agent"

        # Development is filtered to Python agents only; Simple/Advanced show
        # the full catalog, including the VM starters Development excludes.
        dev_ids = {agent_id for _, agent_id in designer.development.python_agent_names()}
        assert dev_ids == python_ids
        assert dev_ids.isdisjoint(non_python_ids)
        assert designer.simple.agentA.count() == len(catalog_rows)
        assert designer.advanced.agentA.count() == len(catalog_rows)
    finally:
        designer.deleteLater()
