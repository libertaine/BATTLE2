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
        assert "def create_agent" in designer.development.pythonSource.toPlainText()
        assert "kind: python" in designer.development.manifestSource.toPlainText()
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
def test_agent_development_content_is_vertically_scrollable():
    """RC1: the workflow content lives inside a QScrollArea so it stays
    reachable when it doesn't fit the available vertical space (e.g. after
    a completed Development Test expands testStatusLabel on a constrained
    display), without truncating or hiding anything. Structural checks only
    -- no pixel-level/platform-specific scrollbar assertions.
    """
    _make_app()
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QScrollArea

    from app.views.development import AgentDevelopmentPanel

    panel = AgentDevelopmentPanel()
    try:
        scroll_areas = panel.findChildren(QScrollArea)
        assert len(scroll_areas) == 1
        scroll = scroll_areas[0]
        assert scroll.widgetResizable() is True
        assert scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff

        content = scroll.widget()
        assert content is not None

        # Every group's controls must still be reachable as descendants of
        # the scroll area's content widget, in their existing logical
        # order (Agent, Source, Validation, Development Test, Evaluation,
        # Status) -- nothing was moved outside the scrollable area or
        # dropped to make room.
        for control in (
            panel.agentCombo,
            panel.sourceTabs,
            panel.btnValidate,
            panel.btnTest,
            panel.testStatusLabel,
            panel.btnEvaluate,
            panel.statusLabel,
        ):
            assert content.isAncestorOf(control)
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
def test_new_agent_dialog_defaults_to_blank_template(monkeypatch, tmp_path):
    _make_app()
    from battle_engine.agent_scaffold import DEFAULT_TEMPLATE

    from app.views.development import NewAgentDialog

    data_root = tmp_path / "data"
    dialog = NewAgentDialog(data_root)
    assert dialog.selected_template() == DEFAULT_TEMPLATE == "blank"

    dialog.agentId.setText("default_template_agent")
    dialog._on_ok()

    assert dialog.result is not None
    source = dialog.result.source_path.read_text(encoding="utf-8")
    assert "cursor" not in source  # the annotated template's own giveaway


@pytest.mark.gui
def test_new_agent_dialog_annotated_template_produces_commented_agent(monkeypatch, tmp_path):
    _make_app()
    from app.views.development import NewAgentDialog

    data_root = tmp_path / "data"
    dialog = NewAgentDialog(data_root)
    index = dialog.templateCombo.findData("annotated")
    assert index >= 0
    dialog.templateCombo.setCurrentIndex(index)
    assert dialog.selected_template() == "annotated"

    dialog.agentId.setText("annotated_template_agent")
    dialog._on_ok()

    assert dialog.result is not None
    source = dialog.result.source_path.read_text(encoding="utf-8")
    assert "last_read" in source  # the annotated template explains this field


@pytest.mark.gui
def test_status_labels_are_selectable_for_copying_error_text(tmp_path):
    _make_app()
    from PySide6.QtCore import Qt

    from app.views.development import AgentDevelopmentPanel, NewAgentDialog

    panel = AgentDevelopmentPanel()
    try:
        for label in (panel.statusLabel, panel.testStatusLabel):
            flags = label.textInteractionFlags()
            assert flags & Qt.TextInteractionFlag.TextSelectableByMouse
    finally:
        panel.deleteLater()

    dialog = NewAgentDialog(tmp_path)
    flags = dialog.errorLabel.textInteractionFlags()
    assert flags & Qt.TextInteractionFlag.TextSelectableByMouse


@pytest.mark.gui
def test_reload_source_picks_up_an_external_edit_without_reselecting(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))

    from battle_engine.agent_scaffold import create_agent

    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        result = create_agent("editable_agent", data_root=data_root)
        designer.refresh_agents(select="editable_agent")
        assert "0xA5" in designer.development.pythonSource.toPlainText()

        # Simulate an external editor's save -- the Designer's own source
        # view must not know this happened until told to reload.
        result.source_path.write_text(
            "def create_agent():\n    raise RuntimeError('edited externally')\n",
            encoding="utf-8",
        )
        assert "edited externally" not in designer.development.pythonSource.toPlainText()

        designer.development.reloadSource()

        assert "edited externally" in designer.development.pythonSource.toPlainText()
        assert "0xA5" not in designer.development.pythonSource.toPlainText()
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_validate_and_test_buttons_reload_source_before_running(monkeypatch, tmp_path):
    """Panel-level (not full Designer): confirms both buttons refresh the
    preview via their real click-signal wiring, without needing to spin up
    an actual validate/test subprocess (nothing is connected to
    validateRequested/testRequested at this bare-panel level).
    """
    _make_app()
    from battle_engine.agent_scaffold import create_agent

    from app.services.agent_catalog import AgentRow
    from app.views.development import AgentDevelopmentPanel

    data_root = tmp_path / "data"
    result = create_agent("clickable_agent", data_root=data_root)
    row = AgentRow(
        "clickable_agent",
        str(result.source_path.parent),
        None,
        # Mirrors what agent_catalog actually records for the agent this
        # test just scaffolded: create_agent writes api_version 1, and
        # Ruleset compatibility (which gates Test) reads that field.
        {"kind": "python", "api_version": 1},
        agent_id="clickable_agent",
    )
    panel = AgentDevelopmentPanel()
    try:
        panel.setAgents([row])
        panel.selectAgent("clickable_agent")
        assert "0xA5" in panel.pythonSource.toPlainText()

        result.source_path.write_text("# edited before Validate\n", encoding="utf-8")
        panel.btnValidate.click()
        assert "edited before Validate" in panel.pythonSource.toPlainText()

        result.source_path.write_text("# edited before Test\n", encoding="utf-8")
        panel.btnTest.click()
        assert "edited before Test" in panel.pythonSource.toPlainText()
    finally:
        panel.deleteLater()


@pytest.mark.gui
def test_reload_source_button_refreshes_preview(tmp_path):
    _make_app()
    from battle_engine.agent_scaffold import create_agent

    from app.services.agent_catalog import AgentRow
    from app.views.development import AgentDevelopmentPanel

    data_root = tmp_path / "data"
    result = create_agent("reload_button_agent", data_root=data_root)
    row = AgentRow(
        "reload_button_agent",
        str(result.source_path.parent),
        None,
        {"kind": "python"},
        agent_id="reload_button_agent",
    )
    panel = AgentDevelopmentPanel()
    try:
        panel.setAgents([row])
        panel.selectAgent("reload_button_agent")

        result.source_path.write_text("# via reload button\n", encoding="utf-8")
        assert "via reload button" not in panel.pythonSource.toPlainText()

        panel.btnReloadSource.click()

        assert "via reload button" in panel.pythonSource.toPlainText()
    finally:
        panel.deleteLater()


@pytest.mark.gui
def test_invalidate_agent_state_also_refreshes_the_stale_preview(tmp_path):
    _make_app()
    from battle_engine.agent_scaffold import create_agent

    from app.services.agent_catalog import AgentRow
    from app.views.development import AgentDevelopmentPanel

    data_root = tmp_path / "data"
    result = create_agent("restored_agent", data_root=data_root)
    row = AgentRow(
        "restored_agent",
        str(result.source_path.parent),
        None,
        {"kind": "python"},
        agent_id="restored_agent",
    )
    panel = AgentDevelopmentPanel()
    try:
        panel.setAgents([row])
        panel.selectAgent("restored_agent")

        result.source_path.write_text("# restored from an older revision\n", encoding="utf-8")
        assert "restored from an older revision" not in panel.pythonSource.toPlainText()

        panel.invalidateAgentState("restored_agent", "Revision files were restored.")

        assert "restored from an older revision" in panel.pythonSource.toPlainText()
    finally:
        panel.deleteLater()


@pytest.mark.gui
def test_match_selectors_and_development_receive_their_intended_catalogs(
    monkeypatch, tmp_path
):
    """Simple filters by Ruleset while Advanced/Development keep their scope."""
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

        # Development keeps its established all-Python catalog. Advanced keeps
        # the full historical catalog, including VM starters. Simple defaults
        # to Ruleset v2 and therefore shows only Agent API v1 Python agents.
        dev_ids = {agent_id for _, agent_id in designer.development.python_agent_names()}
        simple_ids = {
            designer.simple.agentA.itemData(index)
            for index in range(designer.simple.agentA.count())
        }
        v2_ids = {
            row.agent_id
            for row in catalog_rows
            if row.meta.get("kind") == "python" and row.meta.get("api_version") == 1
        }
        assert dev_ids == python_ids
        assert dev_ids.isdisjoint(non_python_ids)
        assert simple_ids == v2_ids
        assert designer.advanced.agentA.count() == len(catalog_rows)
    finally:
        designer.deleteLater()
