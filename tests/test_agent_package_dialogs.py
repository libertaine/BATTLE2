"""GUI regression coverage for the v1.3 Designer agent-package integration
(Area A: "Export Agent…" on the Agent Development tab, "Import Agent
Package…"/"Inspect Agent Package…" on the Tools menu).

Reuses the exact authoritative v1.2 engine functions
(``battle_engine.agent_package.export_agent``/``inspect_package``/
``import_package``) for every fixture and assertion here -- this suite
never reimplements package validation/import logic, it only proves the
Designer wiring calls those functions correctly, never executes packaged
agent code while inspecting, and presents their typed results consistently
with ``bytefray agents export``/``package show``/``import``.

Marked ``gui`` like the existing Designer tests: excluded from the default
headless run, exercised by the dedicated display-backed workflow.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

NOP_ACTION = "AgentAction(ActionKind.NOP)"


def _make_app():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _write_python_agent(
    root: Path,
    name: str,
    action: str = NOP_ACTION,
    variant: str = "",
    *,
    display: str | None = None,
) -> Path:
    directory = root / "agents" / name
    directory.mkdir(parents=True)
    manifest = {
        "kind": "python",
        "api_version": 1,
        "entrypoint": "agent.py:create_agent",
        "version": "1.0",
    }
    if display is not None:
        manifest["display"] = display
    (directory / "agent.yaml").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    (directory / "agent.py").write_text(
        f"""
# {variant}
from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, context): pass
    def act(self, observation): return {action}
def create_agent(): return Agent()
""",
        encoding="utf-8",
    )
    return directory


# ---------------------------------------------------------------------------
# Formatter functions (mirror agent_package_cli.py's own field selection)
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_format_export_result_text_matches_cli_field_selection(tmp_path):
    _make_app()
    from battle_engine.agent_package import export_agent

    from app.views.agent_package import format_export_result_text

    _write_python_agent(tmp_path, "hunter")
    result = export_agent("hunter", data_root=tmp_path, output=tmp_path / "out")

    text = format_export_result_text(result)
    assert "Exported agent: hunter" in text
    assert f"Revision: {result.agent_revision_id}" in text
    assert f"Package: {result.package_path}" in text
    assert f"SHA-256: {result.package_sha256}" in text


@pytest.mark.gui
def test_format_package_inspection_text_includes_trust_disclosure(tmp_path):
    _make_app()
    from battle_engine.agent_package import export_agent, inspect_package

    from app.views.agent_package import format_package_inspection_text

    _write_python_agent(tmp_path, "hunter")
    result = export_agent("hunter", data_root=tmp_path, output=tmp_path / "out")
    inspection = inspect_package(result.package_path)

    text = format_package_inspection_text(inspection)
    assert "agent_id: hunter" in text
    assert "importable on this installation: True" in text
    assert "not a safety or trust statement" in text
    assert "does not authenticate who created the package" in text


@pytest.mark.gui
def test_format_package_inspection_text_reports_invalid_package(tmp_path):
    _make_app()
    from battle_engine.agent_package import inspect_package

    from app.views.agent_package import format_package_inspection_text

    bad_path = tmp_path / "bad.bytefray-agent"
    bad_path.write_bytes(b"not a zip")
    inspection = inspect_package(bad_path)

    text = format_package_inspection_text(inspection)
    assert "valid: False" in text


@pytest.mark.gui
def test_package_formatter_escapes_control_text_from_untrusted_diagnostics(tmp_path):
    _make_app()
    from battle_engine.agent_package import PackageInspection

    from app.views.agent_package import format_package_inspection_text

    inspection = PackageInspection(
        package_path=tmp_path / "package\nspoof.bytefray-agent",
        valid=False,
        error="invalid\npretend-success",
    )
    text = format_package_inspection_text(inspection)

    assert "package\\nspoof" in text
    assert "invalid\\npretend-success" in text
    assert "\nspoof.bytefray-agent" not in text
    assert "\npretend-success" not in text


@pytest.mark.gui
def test_format_import_result_text_reports_no_op_and_success(tmp_path):
    _make_app()
    from battle_engine.agent_package import ImportResult

    from app.views.agent_package import format_import_result_text

    no_op = ImportResult(
        agent_id="hunter", agent_revision_id="agent-revision_abc", target_dir=tmp_path, already_present=True
    )
    text = format_import_result_text(no_op)
    assert "already present with this exact revision" in text

    fresh = ImportResult(
        agent_id="hunter", agent_revision_id="agent-revision_abc", target_dir=tmp_path, already_present=False
    )
    text = format_import_result_text(fresh)
    assert f"Imported hunter -> {tmp_path}" in text
    assert "not a safety or trust statement" in text


# ---------------------------------------------------------------------------
# PackageDetailsDialog: never executes packaged code, Import gated correctly
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_package_details_dialog_offers_import_button_only_when_valid_and_compatible(tmp_path):
    _make_app()
    from battle_engine.agent_package import export_agent, inspect_package

    from app.views.agent_package import PackageDetailsDialog

    _write_python_agent(tmp_path, "hunter")
    result = export_agent("hunter", data_root=tmp_path, output=tmp_path / "out")
    inspection = inspect_package(result.package_path)
    assert inspection.valid and inspection.compatible

    dialog = PackageDetailsDialog(inspection, allow_import=True)
    try:
        assert dialog.import_button is not None
        assert dialog.import_requested is False
        dialog.import_button.click()
        assert dialog.import_requested is True
    finally:
        dialog.deleteLater()

    inspect_only = PackageDetailsDialog(inspection, allow_import=False)
    try:
        assert inspect_only.import_button is None
    finally:
        inspect_only.deleteLater()


@pytest.mark.gui
def test_package_details_dialog_never_offers_import_for_invalid_package(tmp_path):
    """Selecting/inspecting a malformed file must never crash, never import
    a byte of it, and must never offer Import (Sec 6/8 of
    docs/specs/agent_package.md)."""

    _make_app()
    from battle_engine.agent_package import inspect_package

    from app.views.agent_package import PackageDetailsDialog

    bad_path = tmp_path / "bad.bytefray-agent"
    bad_path.write_bytes(b"not a zip")
    inspection = inspect_package(bad_path)
    assert not inspection.valid

    dialog = PackageDetailsDialog(inspection, allow_import=True)
    try:
        assert dialog.import_button is None
    finally:
        dialog.deleteLater()


# ---------------------------------------------------------------------------
# AgentDesigner wiring
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_designer_export_agent_requires_a_selection(monkeypatch, tmp_path):
    """``ensure_starter_agents()`` always populates the catalog with the
    bundled Python starters, so a real Designer session never actually has
    an empty Agent Development combo -- this test forces that combo empty
    directly to exercise the "no selection" guard clause without ever
    reaching ``QFileDialog.getExistingDirectory`` (which would otherwise
    show a real, blocking native picker under the offscreen platform)."""

    _make_app()
    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path / "designer-data"))
    designer = AgentDesigner()
    try:
        designer.development.agentCombo.clear()
        assert designer.development.selectedAgentRow() is None

        informed = []
        monkeypatch.setattr(
            agent_designer_module.QMessageBox,
            "information",
            staticmethod(lambda *a, **k: informed.append(a) or None),
        )
        designer._on_export_agent()
        assert len(informed) == 1
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_designer_construction_survives_one_malformed_bundled_starter(monkeypatch, tmp_path):
    """Phase 3 M2 product-path control: a malformed bundled starter must not
    crash Designer construction or block the other bundled starters from
    installing. Only a wholly missing/unwritable resource root still shows
    the blocking ``critical`` dialog; a single malformed starter is instead
    reported through a non-blocking ``warning`` that names it."""

    _make_app()
    from battle_engine.starters import STARTER_AGENT_NAMES

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    resources = tmp_path / "resources"
    base = resources / "battle_engine" / "data" / "starter_agents"
    for name in STARTER_AGENT_NAMES:
        agent_dir = base / name
        agent_dir.mkdir(parents=True)
        agent_dir.joinpath("agent.yaml").write_text(
            "not json" if name == "v4_scout" else json.dumps({"name": name}),
            encoding="utf-8",
        )
    monkeypatch.setattr("battle_engine.starters.get_resource_root", lambda: resources)
    data_root = tmp_path / "designer-data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))

    critical = []
    warned = []
    monkeypatch.setattr(
        agent_designer_module.QMessageBox,
        "critical",
        staticmethod(lambda *a, **k: critical.append(a) or None),
    )
    monkeypatch.setattr(
        agent_designer_module.QMessageBox,
        "warning",
        staticmethod(lambda *a, **k: warned.append(a) or None),
    )

    designer = AgentDesigner()
    try:
        assert critical == []
        assert len(warned) == 1
        assert "v4_scout" in warned[0][2]
        installed = {p.name for p in (data_root / "agents").iterdir()}
        assert installed == set(STARTER_AGENT_NAMES) - {"v4_scout"}
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_designer_export_agent_writes_a_real_package(monkeypatch, tmp_path):
    _make_app()
    from battle_engine.agent_package import inspect_package

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    data_root = tmp_path / "designer-data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    _write_python_agent(data_root, "hunter", display="Friendly Export Name")

    designer = AgentDesigner()
    try:
        designer.refresh_agents(select="hunter")
        selected = designer.development.selectedAgentRow()
        assert selected is not None
        assert selected.agent_id == "hunter"
        assert selected.name == "Friendly Export Name"
        out_dir = tmp_path / "export-out"
        out_dir.mkdir()
        monkeypatch.setattr(
            agent_designer_module.QFileDialog,
            "getExistingDirectory",
            staticmethod(lambda *a, **k: str(out_dir)),
        )
        informed = []
        monkeypatch.setattr(
            agent_designer_module.QMessageBox,
            "information",
            staticmethod(lambda *a, **k: informed.append(a) or None),
        )
        monkeypatch.setattr(
            agent_designer_module.QMessageBox,
            "critical",
            staticmethod(lambda *a, **k: pytest.fail(f"unexpected export failure dialog: {a}")),
        )

        designer._on_export_agent()

        assert len(informed) == 1
        message = informed[0][2]
        assert "Exported agent: hunter" in message
        packages = list(out_dir.glob("*.bytefray-agent"))
        assert len(packages) == 1
        inspection = inspect_package(packages[0])
        assert inspection.agent_id == "hunter"
        assert inspection.display_name == "Friendly Export Name"
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_designer_export_agent_cancelled_directory_picker_is_a_no_op(monkeypatch, tmp_path):
    _make_app()
    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    data_root = tmp_path / "designer-data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    _write_python_agent(data_root, "hunter")

    designer = AgentDesigner()
    try:
        designer.refresh_agents(select="hunter")
        monkeypatch.setattr(
            agent_designer_module.QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: "")
        )
        informed = []
        monkeypatch.setattr(
            agent_designer_module.QMessageBox,
            "information",
            staticmethod(lambda *a, **k: informed.append(a) or None),
        )

        designer._on_export_agent()  # cancelled picker -> nothing exported, nothing shown

        assert informed == []
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_designer_export_agent_reports_package_errors(monkeypatch, tmp_path):
    _make_app()
    from battle_engine.agent_package import PackageUnsupportedKindError

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    data_root = tmp_path / "designer-data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    _write_python_agent(data_root, "hunter")

    designer = AgentDesigner()
    try:
        designer.refresh_agents(select="hunter")
        monkeypatch.setattr(
            agent_designer_module.QFileDialog,
            "getExistingDirectory",
            staticmethod(lambda *a, **k: str(tmp_path)),
        )

        def _raise(*_a, **_k):
            raise PackageUnsupportedKindError("agent 'hunter' has kind 'builtin'; nothing to package")

        monkeypatch.setattr(agent_designer_module, "export_agent", _raise)
        errors = []
        monkeypatch.setattr(
            agent_designer_module.QMessageBox,
            "critical",
            staticmethod(lambda *a, **k: errors.append(a) or None),
        )

        designer._on_export_agent()

        assert len(errors) == 1
        assert "package_unsupported_kind" in errors[0][2]
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_designer_inspect_agent_package_opens_readonly_details_dialog(monkeypatch, tmp_path):
    _make_app()
    from battle_engine.agent_package import export_agent

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    data_root = tmp_path / "designer-data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    _write_python_agent(data_root, "hunter")
    result = export_agent("hunter", data_root=data_root, output=tmp_path / "out")

    designer = AgentDesigner()
    try:
        monkeypatch.setattr(
            agent_designer_module.QFileDialog,
            "getOpenFileName",
            staticmethod(lambda *a, **k: (str(result.package_path), "")),
        )
        received = {}

        class _RecordingDetailsDialog:
            def __init__(self, inspection, *, allow_import=False, parent=None):
                received["inspection"] = inspection
                received["allow_import"] = allow_import

            def exec(self):
                return None

        monkeypatch.setattr(agent_designer_module, "PackageDetailsDialog", _RecordingDetailsDialog)

        designer._on_inspect_agent_package()

        assert received["allow_import"] is False
        assert received["inspection"].agent_id == "hunter"
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_designer_inspect_agent_package_cancelled_picker_is_a_no_op(monkeypatch, tmp_path):
    _make_app()
    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path / "designer-data"))
    designer = AgentDesigner()
    try:
        monkeypatch.setattr(
            agent_designer_module.QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("", ""))
        )
        opened = []
        monkeypatch.setattr(
            agent_designer_module,
            "PackageDetailsDialog",
            lambda *a, **k: opened.append(1) or pytest.fail("must not open with no file selected"),
        )
        designer._on_inspect_agent_package()
        assert opened == []
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_designer_refuses_package_import_while_subprocess_is_running(monkeypatch, tmp_path):
    _make_app()
    from PySide6.QtCore import QProcess

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path / "designer-data"))
    designer = AgentDesigner()

    class _RunningProcess:
        def state(self):
            return QProcess.Running

    try:
        designer._proc = _RunningProcess()
        monkeypatch.setattr(
            agent_designer_module.QFileDialog,
            "getOpenFileName",
            staticmethod(lambda *a, **k: pytest.fail("busy import must not open a file picker")),
        )
        informed = []
        monkeypatch.setattr(
            agent_designer_module.QMessageBox,
            "information",
            staticmethod(lambda *a, **k: informed.append(a) or None),
        )

        designer._on_import_agent_package()

        assert len(informed) == 1
        assert "active operation" in informed[0][2]
    finally:
        designer._proc = None
        designer.deleteLater()


@pytest.mark.gui
def test_designer_import_agent_package_full_round_trip_and_refreshes_catalog(monkeypatch, tmp_path):
    """End-to-end: export from one data root, import into another isolated
    one, and confirm the Designer's own catalog refresh selects the exact
    imported discovery id even when its display label differs."""

    _make_app()
    from battle_engine.agent_package import export_agent

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    # Deliberately not one of the five bundled starter agent ids
    # (claimer/strider/hunter/wanderer/adaptive) -- AgentDesigner.__init__
    # eagerly calls ensure_starter_agents() against the destination root, so
    # reusing a starter name here would create an unrelated, unintended
    # content collision this test is not exercising (see the dedicated
    # conflict test below for that).
    source_root = tmp_path / "source-root"
    _write_python_agent(source_root, "myagent", display="Friendly Imported Name")
    export_result = export_agent("myagent", data_root=source_root, output=tmp_path / "out")

    designer_root = tmp_path / "designer-data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(designer_root))
    designer = AgentDesigner()
    try:
        monkeypatch.setattr(
            agent_designer_module.QFileDialog,
            "getOpenFileName",
            staticmethod(lambda *a, **k: (str(export_result.package_path), "")),
        )

        class _AutoImportDetailsDialog:
            def __init__(self, inspection, *, allow_import=False, parent=None):
                self.import_requested = allow_import

            def exec(self):
                return None

        monkeypatch.setattr(agent_designer_module, "PackageDetailsDialog", _AutoImportDetailsDialog)
        informed = []

        def _record_information(*args, **_kwargs):
            row = designer.development.selectedAgentRow()
            informed.append((args, row.agent_id if row is not None else None))

        monkeypatch.setattr(
            agent_designer_module.QMessageBox,
            "information",
            staticmethod(_record_information),
        )
        monkeypatch.setattr(
            agent_designer_module.QMessageBox,
            "critical",
            staticmethod(lambda *a, **k: pytest.fail(f"unexpected import failure dialog: {a}")),
        )
        monkeypatch.setattr(
            agent_designer_module.QMessageBox,
            "warning",
            staticmethod(lambda *a, **k: pytest.fail(f"unexpected incompatibility dialog: {a}")),
        )

        designer._on_import_agent_package()

        assert len(informed) == 1
        assert "Imported myagent" in informed[0][0][2]
        assert informed[0][1] == "myagent"  # refresh/select happened before success dialog
        assert (designer_root / "agents" / "myagent" / "agent.py").is_file()
        # refresh_agents(select=...) was called: the Agent Development combo
        # now shows the freshly imported agent selected.
        assert designer.development.selectedAgentRow() is not None
        assert designer.development.selectedAgentRow().agent_id == "myagent"
        assert designer.development.selectedAgentRow().name == "Friendly Imported Name"
        assert designer.development.pythonSource.toPlainText() == (
            designer_root / "agents" / "myagent" / "agent.py"
        ).read_text(encoding="utf-8")
        assert designer.development.manifestSource.toPlainText() == (
            designer_root / "agents" / "myagent" / "agent.yaml"
        ).read_text(encoding="utf-8")
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_import_collision_retry_does_not_recurse(monkeypatch, tmp_path):
    _make_app()
    from battle_engine.agent_package import ImportResult, PackageImportConflictError

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path / "designer-data"))
    designer = AgentDesigner()
    attempts = 0

    def _many_conflicts(path, *, data_root, as_agent_id=None):
        nonlocal attempts
        attempts += 1
        if attempts <= 1_050:
            raise PackageImportConflictError("simulated collision")
        return ImportResult(
            agent_id="eventual_id",
            agent_revision_id="agent-revision_" + "a" * 64,
            target_dir=data_root / "agents" / "eventual_id",
            already_present=False,
        )

    try:
        monkeypatch.setattr(agent_designer_module, "import_package", _many_conflicts)
        monkeypatch.setattr(
            agent_designer_module.QInputDialog,
            "getText",
            staticmethod(lambda *a, **k: (f"alternate_{attempts}", True)),
        )
        selected = []
        monkeypatch.setattr(designer, "refresh_agents", lambda select=None: selected.append(select))
        monkeypatch.setattr(
            agent_designer_module.QMessageBox,
            "information",
            staticmethod(lambda *a, **k: None),
        )

        designer._import_package_with_retry(tmp_path / "simulated.bytefray-agent")

        assert attempts == 1_051
        assert selected == ["eventual_id"]
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_designer_import_agent_package_conflict_retries_iteratively_and_selects_exact_id(
    monkeypatch, tmp_path
):
    """Sec 7/11 of the v1.3 task: a destination-id collision with genuinely
    different content must not silently overwrite -- the Designer offers an
    explicit alternate-id retry, mirroring the CLI's ``--as`` flag, never an
    automatic rename."""

    _make_app()
    from battle_engine.agent_package import export_agent

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    source_root = tmp_path / "source-root"
    _write_python_agent(
        source_root,
        "package_source",
        variant="from-source-root",
        display="Duplicate Friendly Name",
    )
    export_result = export_agent(
        "package_source", data_root=source_root, output=tmp_path / "out"
    )

    designer_root = tmp_path / "designer-data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(designer_root))
    # Two distinct ids already have different content, and deliberately
    # share the imported package's display label. The import must retry both
    # collisions without recursion, preserve both trees byte-for-byte, then
    # select the final discovery id rather than the duplicate display text.
    existing_source = _write_python_agent(
        designer_root,
        "package_source",
        variant="pre-existing-source-id",
        display="Duplicate Friendly Name",
    )
    existing_alias = _write_python_agent(
        designer_root,
        "taken_alias",
        variant="pre-existing-first-alternate",
        display="Duplicate Friendly Name",
    )
    source_bytes = (existing_source / "agent.py").read_bytes()
    alias_bytes = (existing_alias / "agent.py").read_bytes()

    designer = AgentDesigner()
    try:
        monkeypatch.setattr(
            agent_designer_module.QFileDialog,
            "getOpenFileName",
            staticmethod(lambda *a, **k: (str(export_result.package_path), "")),
        )

        class _AutoImportDetailsDialog:
            def __init__(self, inspection, *, allow_import=False, parent=None):
                self.import_requested = allow_import

            def exec(self):
                return None

        monkeypatch.setattr(agent_designer_module, "PackageDetailsDialog", _AutoImportDetailsDialog)
        alternate_ids = iter([("taken_alias", True), ("final_import_id", True)])
        monkeypatch.setattr(
            agent_designer_module.QInputDialog,
            "getText",
            staticmethod(lambda *a, **k: next(alternate_ids)),
        )
        informed = []
        monkeypatch.setattr(
            agent_designer_module.QMessageBox,
            "information",
            staticmethod(lambda *a, **k: informed.append(a) or None),
        )
        monkeypatch.setattr(
            agent_designer_module.QMessageBox,
            "critical",
            staticmethod(lambda *a, **k: pytest.fail(f"unexpected import failure dialog: {a}")),
        )
        monkeypatch.setattr(
            agent_designer_module.QMessageBox,
            "warning",
            staticmethod(lambda *a, **k: pytest.fail(f"unexpected incompatibility dialog: {a}")),
        )

        designer._on_import_agent_package()

        assert len(informed) == 1
        assert "Imported final_import_id" in informed[0][2]
        assert (designer_root / "agents" / "final_import_id" / "agent.py").is_file()
        assert (existing_source / "agent.py").read_bytes() == source_bytes
        assert (existing_alias / "agent.py").read_bytes() == alias_bytes
        selected = designer.development.selectedAgentRow()
        assert selected is not None
        assert selected.agent_id == "final_import_id"
        assert selected.name == "Duplicate Friendly Name"
        assert designer.development.agentCombo.currentText().endswith("(final_import_id)")
    finally:
        designer.deleteLater()
