"""Agent package Designer dialogs (v1.3 "Designer Workflow Completion").

Thin presentation over the authoritative, already-shipped v1.2 engine layer
(``battle_engine.agent_package``): export, inspect, and import. No package
validation, ZIP extraction, safe-path containment, or compatibility logic
lives here -- this module only calls ``export_agent``/``inspect_package``/
``import_package`` and formats their already-typed results, mirroring
``agent_package_cli.py``'s own field selection and wording exactly so the
Designer and the CLI never disclose two different descriptions of the same
package (docs/specs/agent_package.md; v1.3 task Sec 5-9/16).

Selecting or inspecting a ``.bytefray-agent`` file never imports, executes,
or syntax-checks a single byte of the packaged agent's code --
``inspect_package`` itself is guaranteed execution-free by the domain layer
(Sec 6 of the spec), so ``PackageDetailsDialog`` runs directly on the GUI
thread with no ``QProcess`` involved, exactly like ``TraceInspectorDialog``/
``RevisionBrowserDialog``. Only an explicit "Import…" click ever calls
``import_package`` -- selecting a package for inspection is always safe to
do freely, including for an untrusted file.
"""

from __future__ import annotations

from battle_engine.agent_package import ExportResult, ImportResult, PackageInspection
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QPlainTextEdit, QVBoxLayout, QWidget

_TRUST_DISCLOSURE = (
    "This reports package structure and self-consistency/integrity only; it "
    "does not authenticate who created the package. It is not a safety or "
    "trust statement about the contained agent's code -- "
    "Python and blob agents are executable/loadable content, and Bytefray "
    "does not sandbox agent execution (see docs/AGENT_LAB.md)."
)


def _safe_value(value: object) -> str:
    """Render untrusted metadata without allowing terminal/UI control text."""

    rendered = str(value)
    return rendered if not rendered or rendered.isprintable() else ascii(rendered)


def format_export_result_text(result: ExportResult) -> str:
    """Mirrors ``agent_package_cli.py``'s ``_cmd_export`` human-output field selection."""

    lines = [
        f"Exported agent: {_safe_value(result.agent_id)}",
        f"Revision: {_safe_value(result.agent_revision_id)}",
    ]
    if not result.complete:
        lines.append(
            f"WARNING: revision is INCOMPLETE ({result.omitted_count} omission(s)) "
            "-- see Show Revision for details."
        )
    lines.append(f"Files: {result.file_count}")
    lines.append(f"Package: {_safe_value(result.package_path)}")
    lines.append(f"SHA-256: {_safe_value(result.package_sha256)}")
    if result.local_archive_error:
        lines.append(
            "NOTE: local revision-store archival did not succeed "
            f"({_safe_value(result.local_archive_error)}); the package itself is unaffected."
        )
    return "\n".join(lines)


def format_package_inspection_text(inspection: PackageInspection) -> str:
    """Mirrors ``agent_package_cli.py``'s ``_print_inspection`` field selection exactly."""

    if not inspection.valid:
        return (
            f"package: {_safe_value(inspection.package_path)}\n"
            f"valid: False ({_safe_value(inspection.error)})"
        )
    lines = [
        f"package: {_safe_value(inspection.package_path)}",
        "valid: True",
        f"agent_id: {_safe_value(inspection.agent_id)}",
        f"display_name: {_safe_value(inspection.display_name)}",
        f"kind: {_safe_value(inspection.kind)}",
        f"agent_version: {_safe_value(inspection.agent_version)}",
        f"entry_point: {_safe_value(inspection.entry_point)}",
        f"agent_api_version: {inspection.agent_api_version}",
        f"revision: {_safe_value(inspection.agent_revision_id)}",
    ]
    completeness = (
        "complete"
        if inspection.revision_complete
        else f"INCOMPLETE ({inspection.revision_omitted_count} omission(s))"
    )
    lines.append(f"revision completeness: {completeness}")
    lines.append(f"file_count: {inspection.file_count}")
    lines.append(f"exported_at: {_safe_value(inspection.exported_at)}")
    lines.append(
        "bytefray_version (informational breadcrumb, not enforced): "
        f"{_safe_value(inspection.bytefray_version)}"
    )
    lines.append(
        f"integrity verified (recomputed live from packaged bytes): {inspection.integrity_verified}"
    )
    lines.append(f"importable on this installation: {inspection.compatible}")
    for note in inspection.compatibility_notes:
        lines.append(f"  - {_safe_value(note)}")
    lines.append("")
    lines.append(_TRUST_DISCLOSURE)
    return "\n".join(lines)


def format_import_result_text(result: ImportResult) -> str:
    """Mirrors ``agent_package_cli.py``'s ``_cmd_import`` human-output field selection."""

    if result.already_present:
        return (
            f"Agent {_safe_value(result.agent_id)!r} already present with this exact revision "
            f"({_safe_value(result.agent_revision_id)}); nothing imported."
        )
    lines = [
        f"Imported {_safe_value(result.agent_id)} -> {_safe_value(result.target_dir)}",
        f"Revision: {_safe_value(result.agent_revision_id)}",
        "",
        _TRUST_DISCLOSURE,
    ]
    if result.local_archive_error:
        lines.append(
            "NOTE: local revision-store archival did not succeed "
            f"({_safe_value(result.local_archive_error)}); the imported agent itself is unaffected."
        )
    return "\n".join(lines)


class PackageDetailsDialog(QDialog):
    """Read-only package inspection, reused by "Inspect Agent Package…" and
    the import flow's mandatory pre-import review step.

    Constructing or showing this dialog never executes packaged agent code
    -- it only renders an already-computed, execution-free
    ``PackageInspection`` (Sec 6/8 of docs/specs/agent_package.md). When
    ``allow_import=True`` and the inspected package is both structurally
    valid and compatible with this installation, an "Import…" button is
    offered; clicking it sets ``import_requested`` and closes the dialog
    without performing the import itself -- the caller (``AgentDesigner``)
    performs the actual, authoritative ``import_package`` call afterward,
    so this dialog never becomes a second place import logic could drift.
    """

    def __init__(
        self,
        inspection: PackageInspection,
        *,
        allow_import: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Package: {_safe_value(inspection.package_path.name)}")
        self.inspection = inspection
        self.import_requested = False
        self.import_button: QWidget | None = None

        layout = QVBoxLayout(self)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(format_package_inspection_text(inspection))
        layout.addWidget(text)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        if allow_import and inspection.valid and inspection.compatible:
            self.import_button = buttons.addButton("Import…", QDialogButtonBox.AcceptRole)
            self.import_button.clicked.connect(self._on_import_clicked)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(560, 480)

    def _on_import_clicked(self) -> None:
        self.import_requested = True
        self.accept()


__all__ = [
    "PackageDetailsDialog",
    "format_export_result_text",
    "format_import_result_text",
    "format_package_inspection_text",
]
