"""Evaluation History dialogs (v1.1 "Evaluation Insight & Designer Polish").

Brings the already-shipped, Qt-free ``battle_engine.evaluation_history``/
``battle_engine.agent_revisions`` engine layer into the Designer: browse past
``agents evaluate`` runs (including legacy v1 artifacts), inspect one in
detail, compare two runs, and inspect the durable agent-revision provenance
behind a role/opponent -- the exact deferred slice
``docs/specs/evaluation_history.md`` Sec 17 and ``docs/specs/agent_revision.md``
Sec 9 both named but did not implement ("a read-only 'Evaluation History…'
action reusing ``EvaluationResultsDialog``/``TraceInspectorDialog``/replay-open
plumbing already built for evaluate").

No agent code ever executes when any dialog in this module opens -- every
read is a plain filesystem/JSON read through
``app.services.evaluation_history_workflows``, so (like ``TraceInspectorDialog``)
these dialogs run directly on the GUI thread with no ``QProcess`` involved.
"""

from __future__ import annotations

from pathlib import Path

from battle_engine.evaluation_history import AdaptedCell, DiscoveredEvaluation
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.services.designer_workflows import DesignerValidationError
from app.services.evaluation_history_workflows import (
    compare_evaluations,
    discover_evaluation_listing,
    distinct_opponent_ids,
    format_agent_revision_text,
    format_comparison_gaps_text,
    format_comparison_text,
    format_evaluation_summary_text,
    load_agent_revision,
    load_evaluation_summary,
    sorted_listing_entries,
)

_VERDICT_COLORS = {
    "improved": QColor("#1a7f37"),
    "regressed": QColor("#cf222e"),
}


def _list_row_label(entry: DiscoveredEvaluation) -> str:
    summary = entry.summary
    codes = ",".join(code.value for code in entry.health.codes) or "unknown"
    if summary is None:
        return f"UNREADABLE  {entry.location.evaluation_json_path}  [{codes}]"
    created = summary.created_at.value or f"(file mtime {entry.location.file_modified_at})"
    return (
        f"{summary.evaluation_id}  schema=v{summary.schema.schema_version}  "
        f"candidate={summary.candidate_id}  baseline={summary.baseline_id or 'none'}  "
        f"created={created}  lifecycle={summary.lifecycle_state.value}  health=[{codes}]  "
        f"cells={len(summary.cells)}/{summary.matrix_size}"
    )


def _cell_row_label(cell: AdaptedCell) -> str:
    return (
        f"[{cell.subject_role}] {cell.subject_id} vs {cell.opponent_id} "
        f"seed={cell.seed}  status={cell.status} outcome={cell.outcome}  "
        f"orientation={cell.orientation.value or 'unknown'}"
    )


class EvaluationPickerDialog(QDialog):
    """Minimal "pick one other discovered evaluation" list, used by
    "Compare with…" -- reuses the identical discovered listing the main
    dialog already has, never a second discovery scan."""

    def __init__(
        self,
        entries: tuple[DiscoveredEvaluation, ...],
        *,
        exclude: Path | None = None,
        title: str = "Choose evaluation",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(640, 420)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("This will be compared against as the newer (right-hand) run."))

        self.list = QListWidget()
        for entry in entries:
            if exclude is not None and entry.location.evaluation_json_path == exclude:
                continue
            if entry.summary is None:
                # An unreadable/malformed sibling can never be a meaningful
                # comparison target -- compare_evaluations() would just fail
                # on it immediately (safely, but pointlessly). Excluding it
                # here is a real usability fix, not merely defensive: the
                # main history list still lists it (Sec 13 of
                # docs/specs/evaluation_history.md -- discovery must never
                # hide a malformed sibling), only this narrower "pick a
                # comparison partner" picker excludes it.
                continue
            label = _list_row_label(entry)
            item = QListWidgetItem(label)
            item.setToolTip(label)
            item.setData(Qt.UserRole, entry)
            self.list.addItem(item)
        layout.addWidget(self.list, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_path(self) -> Path | None:
        item = self.list.currentItem()
        if item is None:
            return None
        entry: DiscoveredEvaluation = item.data(Qt.UserRole)
        return entry.location.evaluation_json_path


class RevisionBrowserDialog(QDialog):
    """Read-only agent-revision inspector: pick a role, see its manifest
    (files, omissions, completeness) and a live verification result --
    mirrors ``bytefray agents revisions show`` exactly (Sec 7.1 of
    ``docs/specs/agent_revision.md``)."""

    def __init__(
        self,
        roles: list[tuple[str, str]],
        *,
        data_root: Path,
        parent: QWidget | None = None,
    ) -> None:
        """``roles`` is ``(label, agent_id, revision_id)`` triples -- only
        roles with a known, non-``unknown`` revision id should be passed in.
        ``agent_id`` is the role's own evaluation-time agent id (e.g.
        ``candidate_id``), used to live-compare against that agent's
        *current* on-disk source (Area D: "does this still match current
        source")."""

        super().__init__(parent)
        self.setWindowTitle("Agent Revision")
        self.resize(560, 480)
        self._data_root = data_root

        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("Role"))
        self.roleCombo = QComboBox()
        for label, agent_id, revision_id in roles:
            self.roleCombo.addItem(label, (agent_id, revision_id))
        row.addWidget(self.roleCombo, 1)
        showButton = QPushButton("Show")
        row.addWidget(showButton)
        layout.addLayout(row)

        self.detailText = QPlainTextEdit()
        self.detailText.setReadOnly(True)
        layout.addWidget(self.detailText, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        showButton.clicked.connect(self._on_show)
        if roles:
            self._on_show()

    def _on_show(self) -> None:
        data = self.roleCombo.currentData()
        if not data or not data[1]:
            self.detailText.setPlainText("No revision id recorded for this role.")
            return
        agent_id, revision_id = data
        try:
            revision = load_agent_revision(revision_id, data_root=self._data_root, current_agent_id=agent_id)
        except DesignerValidationError as exc:
            self.detailText.setPlainText(str(exc))
            return
        self.detailText.setPlainText(format_agent_revision_text(revision))


class EvaluationComparisonDialog(QDialog):
    """Read-only right-relative-to-left comparison view (Sec 5/6 of the
    v1.1 task): comparability disclosure first, then a verdict-highlighted
    per-opponent table -- never a bare performance delta without the
    conditions that produced it."""

    def __init__(self, result, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._result = result
        self.setWindowTitle(
            f"Compare Evaluations — {result.left.candidate_id} → {result.right.candidate_id}"
        )
        self.resize(760, 600)

        layout = QVBoxLayout(self)

        summaryText = QPlainTextEdit()
        summaryText.setReadOnly(True)
        summaryText.setPlainText(format_comparison_text(result))
        summaryText.setMaximumHeight(220)
        layout.addWidget(summaryText)

        layout.addWidget(QLabel("Per-opponent rows (right relative to left)"))
        self.rowsList = QListWidget()
        for row in result.comparison.rows:
            delta = ""
            if row.left_score is not None and row.right_score is not None:
                delta = f"  score: {row.left_score:g} -> {row.right_score:g} ({row.right_score - row.left_score:+g})"
            label = (
                f"{row.verdict.upper():<11} opponent={row.opponent_id} seed={row.seed}  "
                f"left={row.left_outcome} right={row.right_outcome}{delta}"
            )
            if row.reproducibility_anomaly:
                label += "  [REPRODUCIBILITY ANOMALY]"
            item = QListWidgetItem(label)
            color = _VERDICT_COLORS.get(row.verdict)
            if color is not None:
                item.setForeground(color)
            elif row.verdict == "inconclusive":
                item.setForeground(QColor("#6e7781"))
            item.setData(Qt.UserRole, row)
            self.rowsList.addItem(item)
        layout.addWidget(self.rowsList, 1)

        self.detailText = QPlainTextEdit()
        self.detailText.setReadOnly(True)
        self.detailText.setMaximumHeight(120)
        layout.addWidget(self.detailText)

        gapsButton = QPushButton("Show Unmatched / Changed-Condition / Ambiguous Details")
        gapsButton.setCheckable(True)
        self.gapsText = QPlainTextEdit()
        self.gapsText.setReadOnly(True)
        self.gapsText.setVisible(False)
        layout.addWidget(gapsButton)
        layout.addWidget(self.gapsText)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        self.rowsList.currentItemChanged.connect(self._on_row_selected)
        gapsButton.toggled.connect(self._on_toggle_gaps)

    def _on_row_selected(self) -> None:
        item = self.rowsList.currentItem()
        if item is None:
            self.detailText.setPlainText("")
            return
        row = item.data(Qt.UserRole)
        lines = [
            f"opponent: {row.opponent_id}",
            f"seed: {row.seed}",
            f"verdict: {row.verdict}" + (f"  ({row.reason})" if row.reason else ""),
            f"left outcome: {row.left_outcome}   right outcome: {row.right_outcome}",
        ]
        if row.left_territory is not None or row.right_territory is not None:
            lines.append(f"territory: left={row.left_territory}  right={row.right_territory}")
        self.detailText.setPlainText("\n".join(lines))

    def _on_toggle_gaps(self, checked: bool) -> None:
        if checked and not self.gapsText.toPlainText():
            self.gapsText.setPlainText(format_comparison_gaps_text(self._result.comparison))
        self.gapsText.setVisible(checked)


class EvaluationHistoryDialog(QDialog):
    """Main entry point: browse discovered evaluations, inspect one in
    detail (with optional deep verification), drill into a cell's replay or
    rerun it in Agent Lab, inspect agent-revision provenance, and open a
    two-run comparison. Deliberately read-only and process-free -- see the
    module docstring.
    """

    testInAgentLabRequested = Signal(str, str, int)
    openReplayRequested = Signal(Path)

    def __init__(self, battle_root: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._battle_root = battle_root
        self._entries: tuple[DiscoveredEvaluation, ...] = ()
        self._current_summary = None
        self._current_verify_error: str | None = None
        self.setWindowTitle("Evaluation History")
        self.resize(1000, 680)

        layout = QVBoxLayout(self)

        topRow = QHBoxLayout()
        refreshButton = QPushButton("Refresh")
        self.verifyCheck = QCheckBox("Verify (deep, cross-checks nested replay/result/revision evidence)")
        topRow.addWidget(refreshButton)
        topRow.addWidget(self.verifyCheck)
        topRow.addStretch(1)
        layout.addLayout(topRow)

        # A dedicated, always-visible status line for the Verify outcome --
        # found necessary during interactive qualification: the same fact
        # is also appended as the last line of the (long, scrollable)
        # detail text below, where it was easy to miss entirely without
        # scrolling down. This label is redundant with that line by design
        # (never the *only* place the fact appears), not a replacement for it.
        self.verifyStatusLabel = QLabel("")
        layout.addWidget(self.verifyStatusLabel)

        splitter = QSplitter()
        self.list = QListWidget()
        splitter.addWidget(self.list)

        detailPane = QWidget()
        detailLayout = QVBoxLayout(detailPane)
        detailLayout.setContentsMargins(0, 0, 0, 0)
        self.detailText = QPlainTextEdit()
        self.detailText.setReadOnly(True)
        detailLayout.addWidget(self.detailText, 2)

        detailLayout.addWidget(QLabel("Cells"))
        self.cellsList = QListWidget()
        detailLayout.addWidget(self.cellsList, 1)

        cellActions = QHBoxLayout()
        self.testAgentLabButton = QPushButton("Test in Agent Lab")
        self.testAgentLabButton.setEnabled(False)
        self.openReplayButton = QPushButton("Open Replay")
        self.openReplayButton.setEnabled(False)
        cellActions.addWidget(self.testAgentLabButton)
        cellActions.addWidget(self.openReplayButton)
        cellActions.addStretch(1)
        detailLayout.addLayout(cellActions)

        roleActions = QHBoxLayout()
        self.revisionButton = QPushButton("Show Revision…")
        self.revisionButton.setEnabled(False)
        self.compareButton = QPushButton("Compare With…")
        self.compareButton.setEnabled(False)
        roleActions.addWidget(self.revisionButton)
        roleActions.addWidget(self.compareButton)
        roleActions.addStretch(1)
        detailLayout.addLayout(roleActions)

        splitter.addWidget(detailPane)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        # Explicit initial sizes -- found necessary during interactive
        # qualification: stretch factors alone left the list column too
        # narrow by default (~1/3 of 920px) to show a row's created-at/
        # health/candidate fields without truncation. The user can still
        # drag the splitter; this only changes the out-of-the-box default.
        splitter.setSizes([420, 500])
        layout.addWidget(splitter, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        refreshButton.clicked.connect(self.refresh)
        self.list.currentItemChanged.connect(self._on_selection_changed)
        self.verifyCheck.toggled.connect(self._on_selection_changed)
        self.cellsList.currentItemChanged.connect(self._on_cell_selection_changed)
        self.testAgentLabButton.clicked.connect(self._on_test_agent_lab)
        self.openReplayButton.clicked.connect(self._on_open_replay)
        self.revisionButton.clicked.connect(self._on_show_revision)
        self.compareButton.clicked.connect(self._on_compare)

        self.refresh()

    # ---- Discovery / selection ----
    def refresh(self) -> None:
        # Scoped to this Designer's own resolved battle_root, never the
        # ambient default -- the same "make the dependency visible at the
        # call site" practice used throughout app/agent_designer.py (Sec 3
        # of docs/specs/agent_designer_workflow.md), and required here in
        # particular since ``discover()``'s own default silently resolves
        # against whatever ``get_data_root()`` returns in the *current*
        # process, which is not guaranteed to equal ``battle_root`` (e.g. a
        # test constructing this dialog against an isolated data root).
        listing = discover_evaluation_listing(roots=(self._battle_root / "runs" / "evaluations",))
        self._entries = sorted_listing_entries(listing)
        self.list.clear()
        for entry in self._entries:
            label = _list_row_label(entry)
            item = QListWidgetItem(label)
            # A row's single-line label packs several fields (id, schema,
            # candidate, baseline, created, lifecycle, health, cell count)
            # and can run wider than the list column at the default window
            # size -- the tooltip is the full text regardless of truncation
            # (found via interactive qualification, not merely theoretical).
            item.setToolTip(label)
            item.setData(Qt.UserRole, entry)
            self.list.addItem(item)
        if not self._entries:
            self.detailText.setPlainText(
                "No evaluations found. Run \"Evaluate…\" from the Agent Development tab first."
            )

    def _selected_entry(self) -> DiscoveredEvaluation | None:
        item = self.list.currentItem()
        if item is None:
            return None
        return item.data(Qt.UserRole)

    def _on_selection_changed(self) -> None:
        entry = self._selected_entry()
        self.cellsList.clear()
        self._current_summary = None
        self._current_verify_error = None
        self.revisionButton.setEnabled(False)
        self.compareButton.setEnabled(False)
        self.verifyStatusLabel.setText("")
        if entry is None:
            self.detailText.setPlainText("")
            return
        if entry.summary is None:
            codes = ", ".join(code.value for code in entry.health.codes) or "unknown"
            details = "\n".join(f"  - {d}" for d in entry.health.detail)
            self.detailText.setPlainText(
                f"This evaluation could not be read.\npath: {entry.location.evaluation_json_path}\n"
                f"health: {codes}\n{details}"
            )
            return

        try:
            summary, verify_error = load_evaluation_summary(
                entry.location.evaluation_json_path,
                verify=self.verifyCheck.isChecked(),
                data_root=self._battle_root,
            )
        except DesignerValidationError as exc:
            self.detailText.setPlainText(f"Could not read this evaluation: {exc}")
            return

        self._current_summary = summary
        self._current_verify_error = verify_error
        verified = verify_error is None if self.verifyCheck.isChecked() else None
        self.detailText.setPlainText(
            format_evaluation_summary_text(summary, verified=verified, verify_error=verify_error)
        )
        self._update_verify_status_label(verified, verify_error)
        for cell in summary.cells:
            item = QListWidgetItem(_cell_row_label(cell))
            item.setData(Qt.UserRole, cell)
            self.cellsList.addItem(item)
        self.revisionButton.setEnabled(True)
        self.compareButton.setEnabled(True)

    def _update_verify_status_label(self, verified: bool | None, verify_error: str | None) -> None:
        """Always-visible restatement of the Verify outcome (see the label's
        own construction comment) -- text-first, color only as an accent,
        never the sole signal (Sec 8)."""

        if verified is None:
            self.verifyStatusLabel.setText("")
        elif verified:
            self.verifyStatusLabel.setText("Verify: PASSED — deep-verified against nested replay/result/revision evidence")
            self.verifyStatusLabel.setStyleSheet("color: #1a7f37;")
        else:
            self.verifyStatusLabel.setText(f"Verify: FAILED — {verify_error}")
            self.verifyStatusLabel.setStyleSheet("color: #cf222e;")

    # ---- Cell drill-down (reuses the exact signals EvaluationResultsDialog already uses) ----
    def _selected_cell(self) -> AdaptedCell | None:
        item = self.cellsList.currentItem()
        if item is None:
            return None
        return item.data(Qt.UserRole)

    def _on_cell_selection_changed(self) -> None:
        cell = self._selected_cell()
        self.testAgentLabButton.setEnabled(cell is not None)
        self.openReplayButton.setEnabled(
            cell is not None and (self._current_summary.location.directory / cell.artifact_dir / "replay.jsonl").is_file()
        )

    def _on_test_agent_lab(self) -> None:
        cell = self._selected_cell()
        if cell is None:
            return
        self.testInAgentLabRequested.emit(cell.subject_id, cell.opponent_id, cell.seed)

    def _on_open_replay(self) -> None:
        cell = self._selected_cell()
        if cell is None or self._current_summary is None:
            return
        self.openReplayRequested.emit(self._current_summary.location.directory / cell.artifact_dir / "replay.jsonl")

    # ---- Revision drill-down ----
    def _on_show_revision(self) -> None:
        summary = self._current_summary
        if summary is None:
            return
        roles: list[tuple[str, str, str]] = []
        if summary.candidate_agent_revision_id.value:
            roles.append(
                (f"candidate: {summary.candidate_id}", summary.candidate_id, summary.candidate_agent_revision_id.value)
            )
        if summary.baseline_id is not None and summary.baseline_agent_revision_id.value:
            roles.append(
                (f"baseline: {summary.baseline_id}", summary.baseline_id, summary.baseline_agent_revision_id.value)
            )
        seen: dict[str, str] = {}
        for opponent_id in distinct_opponent_ids(summary):
            for cell in summary.cells:
                if cell.opponent_id == opponent_id and cell.opponent_agent_revision_id.value:
                    seen[opponent_id] = cell.opponent_agent_revision_id.value
                    break
        for opponent_id, revision_id in seen.items():
            roles.append((f"opponent: {opponent_id}", opponent_id, revision_id))

        if not roles:
            QMessageBox.information(
                self,
                "Agent Revision",
                "No agent-revision provenance is recorded on this evaluation "
                "(it predates schema v3, or archival failed for every role).",
            )
            return

        dialog = RevisionBrowserDialog(roles, data_root=self._battle_root, parent=self)
        dialog.exec()

    # ---- Comparison ----
    def _on_compare(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        picker = EvaluationPickerDialog(
            self._entries,
            exclude=entry.location.evaluation_json_path,
            title="Compare With…",
            parent=self,
        )
        if not picker.exec():
            return
        right_path = picker.selected_path()
        if right_path is None:
            return

        try:
            result = compare_evaluations(
                entry.location.evaluation_json_path,
                right_path,
                verify=self.verifyCheck.isChecked(),
                data_root=self._battle_root,
            )
        except DesignerValidationError as exc:
            QMessageBox.warning(self, "Compare Evaluations", str(exc))
            return

        dialog = EvaluationComparisonDialog(result, parent=self)
        dialog.exec()


__all__ = [
    "EvaluationComparisonDialog",
    "EvaluationHistoryDialog",
    "EvaluationPickerDialog",
    "RevisionBrowserDialog",
]
