"""Evaluation History dialogs (v1.1 "Evaluation Insight & Designer Polish";
comparison drill-down and revision restore added in v1.3 "Designer Workflow
Completion").

Brings the already-shipped, Qt-free ``battle_engine.evaluation_history``/
``battle_engine.agent_revisions`` engine layer into the Designer: browse past
``agents evaluate`` runs (including legacy v1 artifacts), inspect one in
detail, compare two runs, and inspect the durable agent-revision provenance
behind a role/opponent -- the exact deferred slice
``docs/specs/evaluation_history.md`` Sec 17 and ``docs/specs/agent_revision.md``
Sec 9 both named but did not implement ("a read-only 'Evaluation History…'
action reusing ``EvaluationResultsDialog``/``TraceInspectorDialog``/replay-open
plumbing already built for evaluate").

v1.3 closes the two capabilities both specs explicitly deferred out of that
slice: ``EvaluationComparisonDialog`` gains "Test in Agent Lab"/"Open
Replay" drill-down from a comparison row (never guessing when a row does
not uniquely identify a real cell -- see ``EvaluationComparisonDialog``'s
own docstring), and ``RevisionBrowserDialog`` gains an explicit "Restore Files…"
action wrapping the authoritative, unmodified
``agent_revisions.restore_revision`` (see ``RestoreRevisionDialog``).

No agent code ever executes when any dialog in this module opens -- every
read is a plain filesystem/JSON read through
``app.services.evaluation_history_workflows``, so (like ``TraceInspectorDialog``)
these dialogs run directly on the GUI thread with no ``QProcess`` involved.
Restore is the one mutation this module performs; it writes only to an
explicit target directory the user reviews before confirming, and only
through the same store/verification/containment code path the CLI's own
``bytefray agents revisions restore`` already uses -- never a second,
Qt-side reimplementation of restore safety.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from battle_engine.agent_evaluation import (
    ORIENTATION_CANDIDATE_FIRST,
    ORIENTATION_OPPONENT_FIRST,
)
from battle_engine.agent_revisions import (
    RevisionNotFoundError,
    RevisionRestoreError,
    agent_revisions_root,
    restore_revision,
)
from battle_engine.evaluation_history import AdaptedCell, DiscoveredEvaluation, EvaluationSummary
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.services.designer_workflows import DesignerValidationError
from app.services.evaluation_history_workflows import (
    behavior_analysis_for_summary,
    capture_analysis_for_summary,
    compare_evaluations,
    discover_evaluation_listing,
    distinct_opponent_ids,
    find_candidate_cell,
    format_agent_revision_text,
    format_comparison_text,
    format_evaluation_summary_text,
    format_group_cell_condition,
    group_analysis_for_summary,
    load_agent_revision,
    load_evaluation_summary,
    sorted_listing_entries,
    summary_is_group,
)
from app.widgets.evaluation_visuals import (
    COLOR_LOSS,
    COLOR_WIN,
    DimensionDeltaRow,
    InteractionMatrixGrid,
    ProportionBar,
    ordered_behavior_deltas,
    plain_rate_bar_data,
    rate_stat_bar_data,
    win_rate_bar_data,
)

_HISTORICAL_AGENT_LAB_TOOLTIP = (
    "Reruns the selected seed, ticks, and orientation against the currently "
    "installed agents. Historical agent source is not restored."
)


def _affected_live_agent_id(data_root: Path, target: Path) -> str | None:
    """Return the live catalog agent affected by ``target``, if any.

    ``""`` means the catalog root itself or conservative catalog-wide impact
    when lexical and resolved aliases name different agents. Check both the
    lexical absolute path and the resolved path: the former catches a catalog
    child that is a symlink/junction to elsewhere, while the latter catches
    an outside path that aliases back into the live catalog. This is
    warning/refresh logic, never a replacement for ``restore_revision``'s
    containment checks.
    """

    lexical_root = Path(os.path.abspath(data_root.expanduser() / "agents"))
    lexical_target = Path(os.path.abspath(target.expanduser()))
    pairs = [(lexical_root, lexical_target)]
    try:
        pairs.append((lexical_root.resolve(strict=False), lexical_target.resolve(strict=False)))
    except (OSError, RuntimeError):
        pass

    affected: set[str] = set()
    for agents_root, candidate in pairs:
        try:
            relative = candidate.relative_to(agents_root)
        except ValueError:
            continue
        affected.add(relative.parts[0] if relative.parts else "")
    if not affected:
        return None
    # A lexical in-catalog alias may resolve onto a different live agent.
    # One string signal cannot faithfully name both, so invalidate/refresh
    # the whole catalog rather than under-reporting either affected source.
    return next(iter(affected)) if len(affected) == 1 else ""

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
    if summary_is_group(summary):
        roster = ",".join(summary.roster_agent_ids.value or ())
        identity = f"mode=Group  focus={summary.candidate_id}  roster=[{roster}]"
    else:
        identity = f"candidate={summary.candidate_id}  baseline={summary.baseline_id or 'none'}"
    return (
        f"{summary.evaluation_id}  schema=v{summary.schema.schema_version}  {identity}  "
        f"created={created}  lifecycle={summary.lifecycle_state.value}  health=[{codes}]  "
        f"cells={len(summary.cells)}/{summary.matrix_size}"
    )


def _cell_row_label(cell: AdaptedCell, *, group: bool = False) -> str:
    if group:
        return (
            f"{format_group_cell_condition(cell)}  status={cell.status} "
            f"focus outcome={cell.outcome}"
        )
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
        layout.addWidget(QLabel("The selected evaluation will be the right-hand comparison side."))

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
    """Agent-revision inspector: browsing is read-only; restoring files is
    a separate, explicit action.  Pick a role to see its manifest (files,
    omissions, completeness) and live verification result, mirroring
    ``bytefray agents revisions show`` (Sec 7.1 of
    ``docs/specs/agent_revision.md``).

    v1.3 adds an explicit "Restore Files…" action (Sec 12/13 of the v1.3 task),
    the one deliberately-still-unimplemented capability
    ``docs/specs/agent_revision.md`` Sec 9's v1.1 note named: "the Designer
    only ever reads the store; writing to it ... stays a CLI-only
    operation." Restore itself is performed entirely by the authoritative,
    unmodified ``agent_revisions.restore_revision`` -- this dialog only
    collects the same two inputs the CLI's ``restore`` subcommand already
    takes (target directory, ``--force``) and presents its confirmation."""

    liveAgentFilesChanged = Signal(str)

    def __init__(
        self,
        roles: list[tuple[str, str, str]],
        *,
        data_root: Path,
        allow_restore: bool = True,
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
        self.resize(560, 520)
        self._data_root = data_root
        self._allow_restore = allow_restore
        self._current_agent_id: str | None = None
        self._current_revision: object | None = None  # AgentRevisionPresentation | None

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

        self.restoreButton = QPushButton("Restore Files…")
        self.restoreButton.setEnabled(False)
        self.restoreButton.setToolTip(
            "Copy this archived revision's files to an explicit target directory. "
            "The safe default is a separate restored-files directory; live agent source "
            "is touched only if you explicitly choose a path inside agents/."
        )
        if not allow_restore:
            self.restoreButton.setToolTip(
                "Restore Files is disabled because a Designer-owned match, validation, "
                "test, tournament, or evaluation was already active when this History "
                "session opened, or an Agent Lab run was launched from it. Close and "
                "reopen History after the operation finishes; browsing remains available."
            )
        layout.addWidget(self.restoreButton)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        showButton.clicked.connect(self._on_show)
        self.restoreButton.clicked.connect(self._on_restore)
        if roles:
            self._on_show()

    def _on_show(self) -> None:
        data = self.roleCombo.currentData()
        self._current_agent_id = None
        self._current_revision = None
        self.restoreButton.setEnabled(False)
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
        self._current_agent_id = agent_id
        self._current_revision = revision
        self.restoreButton.setEnabled(revision.verified and self._allow_restore)

    def _on_restore(self) -> None:
        if (
            not self._allow_restore
            or self._current_revision is None
            or self._current_agent_id is None
        ):
            return
        restored_revision_id = self._current_revision.revision_id
        dialog = RestoreRevisionDialog(
            self._current_revision,
            agent_id=self._current_agent_id,
            data_root=self._data_root,
            parent=self,
        )
        if dialog.exec() and dialog.restored_target is not None:
            affected = dialog.affected_live_agent_id
            if affected is not None:
                self.liveAgentFilesChanged.emit(affected)
                # Recompute the browser's own current-source status after
                # the successful write instead of leaving stale drift text.
                self._on_show()
            box = QMessageBox(self)
            box.setWindowTitle("Restore Revision Files")
            box.setIcon(QMessageBox.Information)
            message = (
                f"Copied archived files from {restored_revision_id} "
                f"to {dialog.restored_target}.\n\n"
                "Files already present at unrelated paths were not removed."
            )
            if affected is not None:
                message += (
                    "\n\nLive agent files changed. The Designer was notified to refresh "
                    "the catalog and clear stale validation/test state."
                )
            box.setText(message)
            open_button = box.addButton("Open Folder", QMessageBox.ActionRole)
            box.addButton(QMessageBox.Ok)
            box.exec()
            if box.clickedButton() is open_button:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(dialog.restored_target)))


class RestoreRevisionDialog(QDialog):
    """Explicit confirmation + target/force controls for one revision restore.

    Mirrors ``bytefray agents revisions restore``'s own default target
    (``<data_root>/agent_revisions_restored/<revision_id>/``) and
    ``--force`` semantics exactly -- the Designer must not make restore any
    less safe than the CLI (Sec 13 of the v1.3 task): the default target is
    always a separate staging directory, never an existing
    ``agents/<id>/`` directory, so an ordinary restore can never overwrite
    live agent source by accident. A user who wants to restore directly
    over ``agents/<id>/`` can still type that path into the target field
    explicitly -- exactly as capable, and exactly as deliberate, as running
    the CLI with an explicit ``--to``.  ``--force`` overwrites only archived
    file paths; it does not delete unrelated files and does not provide an
    all-or-nothing rollback or hidden backup for an I/O failure.
    """

    _LIVE_SOURCE_LABELS: ClassVar[dict[str, str]] = {
        "unknown": "Current source: not checked.",
        "agent_missing": "Current source: this agent id no longer exists in this installation's catalog.",
        "matches_current_source": "Current source: matches this archived revision (unchanged since it was archived).",
        "changed_since_evaluation": "Current source: has CHANGED since this revision was archived.",
    }

    def __init__(self, presentation, *, agent_id: str, data_root: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Restore Revision Files — {presentation.revision_id}")
        self._data_root = data_root
        self._revision_id = presentation.revision_id
        self.restored_target: Path | None = None
        self.affected_live_agent_id: str | None = None

        layout = QVBoxLayout(self)

        completeness = (
            "complete"
            if presentation.complete
            else f"INCOMPLETE ({len(presentation.omitted)} omission(s))"
        )
        info_lines = [
            f"Archived revision: {presentation.revision_id}",
            f"Recorded for agent id: {agent_id}",
            f"Completeness: {completeness}",
            self._LIVE_SOURCE_LABELS.get(presentation.live_source_status, presentation.live_source_status),
            "",
            (
                "Restore Files copies the archived files above to the target directory "
                "below. The default is a separate restored-files directory; live source "
                "is modified only if you explicitly target a path inside agents/."
            ),
            (
                "Allowing a non-empty target overwrites matching file paths only. "
                "Unrelated files remain, no backup is created, and an ordinary I/O "
                "failure can leave a partially updated target."
            ),
        ]
        if not presentation.complete:
            info_lines.append(
                "WARNING: this revision is INCOMPLETE -- restoring it reproduces less "
                "than the original tree (see Show Revision's omitted-files list)."
            )
        infoLabel = QLabel("\n".join(info_lines))
        infoLabel.setWordWrap(True)
        layout.addWidget(infoLabel)

        targetRow = QHBoxLayout()
        targetRow.addWidget(QLabel("Target directory"))
        self.targetEdit = QLineEdit(
            str(data_root / "agent_revisions_restored" / presentation.revision_id)
        )
        targetRow.addWidget(self.targetEdit, 1)
        browseButton = QPushButton("Browse…")
        targetRow.addWidget(browseButton)
        layout.addLayout(targetRow)

        self.forceCheck = QCheckBox(
            "Allow a non-empty target (matching files overwritten; unrelated files remain)"
        )
        layout.addWidget(self.forceCheck)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        okButton = buttons.button(QDialogButtonBox.Ok)
        okButton.setText("Restore Files")
        buttons.accepted.connect(self._on_restore_clicked)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        browseButton.clicked.connect(self._on_browse)
        self.resize(680, 400)

    def _on_browse(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Choose restore target directory", self.targetEdit.text()
        )
        if directory:
            self.targetEdit.setText(directory)

    def _on_restore_clicked(self) -> None:
        self.restored_target = None
        self.affected_live_agent_id = None
        target_text = self.targetEdit.text().strip()
        if not target_text:
            QMessageBox.warning(
                self, "Restore Revision Files", "Target directory must not be empty."
            )
            return
        try:
            target_dir = Path(target_text).expanduser()
            affected = _affected_live_agent_id(self._data_root, target_dir)
        except (OSError, RuntimeError) as exc:
            QMessageBox.critical(
                self,
                "Restore Revision Files",
                f"Could not resolve the restore target: {exc}",
            )
            return
        if affected is not None:
            live_label = (
                "the live agents catalog root"
                if not affected
                else f"live agent {affected!r} (including one of its subdirectories)"
            )
            answer = QMessageBox.question(
                self,
                "Write Archived Files into Live Agent Source?",
                f"The selected target is inside {live_label}.\n\n"
                "Continuing can immediately change the code Bytefray runs. Matching "
                "archived file paths may be overwritten; unrelated files are NOT "
                "removed; no backup is created; and an I/O failure may leave partial "
                "changes.\n\nContinue with Restore Files?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        store_root = agent_revisions_root(self._data_root)
        try:
            restore_revision(store_root, self._revision_id, target_dir, force=self.forceCheck.isChecked())
        except (RevisionNotFoundError, RevisionRestoreError, OSError) as exc:
            QMessageBox.critical(self, "Restore Revision Files", str(exc))
            return
        self.restored_target = target_dir
        self.affected_live_agent_id = affected
        self.accept()


@dataclass(frozen=True)
class _GapEntry:
    """One selectable "could not be directly compared" item (Sec 11 of the
    v1.3 task): an unmatched cell (one real side), a changed-condition pair
    (two real sides, deliberately not aligned as one row), or an ambiguous
    duplicate group (no reliable cell reference on either side -- never
    actionable, per the task's explicit "do not guess" instruction)."""

    label: str
    left_cell: AdaptedCell | None
    right_cell: AdaptedCell | None
    actionable: bool


class EvaluationComparisonDialog(QDialog):
    """Read-only right-relative-to-left comparison view (Sec 5/6 of the
    v1.1 task): comparability disclosure first, then a verdict-highlighted
    per-opponent table -- never a bare performance delta without the
    conditions that produced it.

    v1.3 adds comparison-row drill-down ("Test in Agent Lab"/"Open Replay"),
    reusing the exact same two signals and Designer handlers
    ``EvaluationHistoryDialog``'s own per-cell drill-down already uses --
    no second execution/replay-launch path. Actions are only ever enabled
    for a selection that uniquely identifies a real underlying
    ``AdaptedCell`` on the chosen side:

    - a directly-comparable row (``comparison.rows``) always resolves both
      a left and a right cell (``find_candidate_cell``), so both sides are
      selectable via the Side control (the right side is the default);
    - an unmatched cell (``unmatched_left``/``unmatched_right``) resolves
      exactly one side -- the Side control offers only that one;
    - a changed-condition pair (``changed_condition``) resolves both sides,
      but they are explicitly *not* the same match (effective conditions,
      rules, methodology, or opponent revision differ), so choosing a side is
      required, never defaulted silently the way a directly-comparable row's
      default is;
    - an ambiguous duplicate group (``ambiguous_duplicate_groups``) never
      resolves a cell at all -- no action is ever enabled for one.
    """

    testInAgentLabRequested = Signal(str, str, int, int, str)
    openReplayRequested = Signal(Path)

    def __init__(self, result, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._result = result
        self._group_comparison = summary_is_group(result.left) or summary_is_group(result.right)
        self._active_left_cell: AdaptedCell | None = None
        self._active_right_cell: AdaptedCell | None = None
        self.setWindowTitle(
            f"Compare Evaluations — {result.left.candidate_id} → {result.right.candidate_id}"
        )
        self.resize(820, 700)

        layout = QVBoxLayout(self)

        summaryText = QPlainTextEdit()
        summaryText.setReadOnly(True)
        summaryText.setPlainText(format_comparison_text(result))
        summaryText.setMaximumHeight(220)
        layout.addWidget(summaryText)

        layout.addWidget(
            QLabel(
                "Comparable roster/layout/seat-assignment cells (right relative to left) — select to inspect"
                if self._group_comparison
                else "Per-opponent rows (right relative to left) — select to inspect"
            )
        )
        self.rowsList = QListWidget()
        for row in result.comparison.rows:
            left_cell = find_candidate_cell(result.left, row, side="left")
            right_cell = find_candidate_cell(result.right, row, side="right")
            if right_cell is not None:
                orientation = right_cell.orientation.value
            elif left_cell is not None:
                orientation = left_cell.orientation.value
            else:
                orientation = "unknown"
            delta = ""
            if row.left_score is not None and row.right_score is not None:
                delta = f"  score: {row.left_score:g} -> {row.right_score:g} ({row.right_score - row.left_score:+g})"
            if self._group_comparison:
                condition_cell = right_cell or left_cell
                condition = (
                    format_group_cell_condition(condition_cell)
                    if condition_cell is not None
                    else f"seed={row.seed} condition=unresolved"
                )
                label = (
                    f"{row.verdict.upper():<11} {condition}  "
                    f"left focus={row.left_outcome} right focus={row.right_outcome}{delta}"
                )
            else:
                label = (
                    f"{row.verdict.upper():<11} opponent={row.opponent_id} seed={row.seed}  "
                    f"orientation={orientation or 'unknown'}  "
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

        gapsButton = QPushButton("Show Unmatched / Changed-Condition / Ambiguous Details")
        gapsButton.setCheckable(True)
        layout.addWidget(gapsButton)

        self._gap_entries = self._build_gap_entries()
        self.gapsList = QListWidget()
        self.gapsList.setVisible(False)
        for entry in self._gap_entries:
            item = QListWidgetItem(entry.label)
            item.setData(Qt.UserRole, entry)
            if not entry.actionable:
                item.setForeground(QColor("#6e7781"))
            self.gapsList.addItem(item)
        layout.addWidget(self.gapsList)

        self.detailText = QPlainTextEdit()
        self.detailText.setReadOnly(True)
        self.detailText.setMaximumHeight(120)
        layout.addWidget(self.detailText)

        actionsRow = QHBoxLayout()
        actionsRow.addWidget(QLabel("Side"))
        self.sideCombo = QComboBox()
        actionsRow.addWidget(self.sideCombo)
        self.testAgentLabButton = QPushButton("Test in Agent Lab")
        self.testAgentLabButton.setToolTip(_HISTORICAL_AGENT_LAB_TOOLTIP)
        if self._group_comparison:
            self.testAgentLabButton.setToolTip(
                "Agent Lab reruns only pairwise cells. Group cells remain available through Open Replay."
            )
        self.testAgentLabButton.setEnabled(False)
        self.openReplayButton = QPushButton("Open Replay")
        self.openReplayButton.setEnabled(False)
        actionsRow.addWidget(self.testAgentLabButton)
        actionsRow.addWidget(self.openReplayButton)
        actionsRow.addStretch(1)
        layout.addLayout(actionsRow)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        self.rowsList.currentItemChanged.connect(self._on_row_selected)
        self.gapsList.currentItemChanged.connect(self._on_gap_selected)
        self.sideCombo.currentIndexChanged.connect(self._update_action_enablement)
        gapsButton.toggled.connect(self.gapsList.setVisible)
        self.testAgentLabButton.clicked.connect(self._on_test_agent_lab)
        self.openReplayButton.clicked.connect(self._on_open_replay)

    # ---- Gap entry construction ----
    def _build_gap_entries(self) -> list[_GapEntry]:
        comparison = self._result.comparison
        entries: list[_GapEntry] = []
        for cell in comparison.unmatched_left:
            condition = (
                format_group_cell_condition(cell)
                if summary_is_group(self._result.left)
                else f"opponent={cell.opponent_id} seed={cell.seed} orientation={cell.orientation.value or 'unknown'}"
            )
            entries.append(
                _GapEntry(
                    label=(
                        f"UNMATCHED (left only)   {condition} status={cell.status}"
                    ),
                    left_cell=cell,
                    right_cell=None,
                    actionable=True,
                )
            )
        for cell in comparison.unmatched_right:
            condition = (
                format_group_cell_condition(cell)
                if summary_is_group(self._result.right)
                else f"opponent={cell.opponent_id} seed={cell.seed} orientation={cell.orientation.value or 'unknown'}"
            )
            entries.append(
                _GapEntry(
                    label=(
                        f"UNMATCHED (right only)  {condition} status={cell.status}"
                    ),
                    left_cell=None,
                    right_cell=cell,
                    actionable=True,
                )
            )
        for left_cell, right_cell in comparison.changed_condition:
            if self._group_comparison:
                condition_text = (
                    f"left {format_group_cell_condition(left_cell)} status={left_cell.status}; "
                    f"right {format_group_cell_condition(right_cell)} status={right_cell.status}  "
                )
            else:
                condition_text = (
                    f"opponent={left_cell.opponent_id} seed={left_cell.seed}  "
                    f"left ticks={self._result.left.ticks} "
                    f"orientation={left_cell.orientation.value or 'unknown'} status={left_cell.status}; "
                    f"right ticks={self._result.right.ticks} "
                    f"orientation={right_cell.orientation.value or 'unknown'} status={right_cell.status}  "
                )
            entries.append(
                _GapEntry(
                    label=(
                        f"CHANGED CONDITION       {condition_text}"
                        "(effective conditions, rules, methodology, or opponent revision differ -- "
                        "not a like-for-like match)"
                    ),
                    left_cell=left_cell,
                    right_cell=right_cell,
                    actionable=True,
                )
            )
        for opponent_id, seed, left_ids, right_ids in comparison.ambiguous_duplicate_groups:
            entries.append(
                _GapEntry(
                    label=(
                        f"AMBIGUOUS GROUP         opponent={opponent_id} seed={seed}  "
                        f"left_schedule_ids={list(left_ids)} right_schedule_ids={list(right_ids)}"
                    ),
                    left_cell=None,
                    right_cell=None,
                    actionable=False,
                )
            )
        return entries

    # ---- Selection handling ----
    def _on_row_selected(self) -> None:
        item = self.rowsList.currentItem()
        self.gapsList.blockSignals(True)
        self.gapsList.setCurrentRow(-1)
        self.gapsList.blockSignals(False)
        if item is None:
            self.detailText.setPlainText("")
            self._set_active_cells(None, None)
            return
        row = item.data(Qt.UserRole)
        left_cell = find_candidate_cell(self._result.left, row, side="left")
        right_cell = find_candidate_cell(self._result.right, row, side="right")
        if self._group_comparison:
            condition_cell = right_cell or left_cell
            lines = [
                "condition: "
                + (
                    format_group_cell_condition(condition_cell)
                    if condition_cell is not None
                    else "unresolved"
                ),
                f"verdict: {row.verdict}" + (f"  ({row.reason})" if row.reason else ""),
                f"left focus outcome: {row.left_outcome}   right focus outcome: {row.right_outcome}",
                "Pairwise orientation: not applicable",
            ]
        else:
            lines = [
                f"opponent: {row.opponent_id}",
                f"seed: {row.seed}",
                (
                    "orientation: "
                    f"left={left_cell.orientation.value if left_cell is not None else 'unresolved'}  "
                    f"right={right_cell.orientation.value if right_cell is not None else 'unresolved'}"
                ),
                f"verdict: {row.verdict}" + (f"  ({row.reason})" if row.reason else ""),
                f"left outcome: {row.left_outcome}   right outcome: {row.right_outcome}",
            ]
        if row.left_territory is not None or row.right_territory is not None:
            lines.append(f"territory: left={row.left_territory}  right={row.right_territory}")
        self.detailText.setPlainText("\n".join(lines))
        self._set_active_cells(left_cell, right_cell)

    def _on_gap_selected(self) -> None:
        item = self.gapsList.currentItem()
        self.rowsList.blockSignals(True)
        self.rowsList.setCurrentRow(-1)
        self.rowsList.blockSignals(False)
        if item is None:
            self.detailText.setPlainText("")
            self._set_active_cells(None, None)
            return
        entry: _GapEntry = item.data(Qt.UserRole)
        if not entry.actionable:
            self.detailText.setPlainText(
                "Ambiguous duplicate group: more than one match on each/either side shares "
                "this (opponent, seed) pair with no reliable evidence for which one "
                "corresponds to which. Bytefray does not guess a pairing here. Close this "
                "comparison and select a concrete cell from each evaluation's Cells list, "
                "or run 'bytefray agents evaluations show <id> --json' and locate its "
                "schedule_id/artifact_dir."
            )
            self._set_active_cells(None, None)
            return
        self.detailText.setPlainText(entry.label)
        self._set_active_cells(
            entry.left_cell,
            entry.right_cell,
            require_explicit_side=entry.left_cell is not None and entry.right_cell is not None,
        )

    def _set_active_cells(
        self,
        left_cell: AdaptedCell | None,
        right_cell: AdaptedCell | None,
        *,
        require_explicit_side: bool = False,
    ) -> None:
        self._active_left_cell = left_cell
        self._active_right_cell = right_cell
        self.sideCombo.blockSignals(True)
        self.sideCombo.clear()
        if require_explicit_side:
            self.sideCombo.addItem("Choose side…", None)
        if left_cell is not None:
            self.sideCombo.addItem("Left (selected)", "left")
        if right_cell is not None:
            self.sideCombo.addItem("Right (comparison)", "right")
        if not require_explicit_side:
            preferred = "right" if right_cell is not None else "left"
            self.sideCombo.setCurrentIndex(self.sideCombo.findData(preferred))
        self.sideCombo.blockSignals(False)
        self._update_action_enablement()

    def _selected_side_cell(self) -> tuple[EvaluationSummary, AdaptedCell] | tuple[None, None]:
        side = self.sideCombo.currentData()
        if side == "left" and self._active_left_cell is not None:
            return self._result.left, self._active_left_cell
        if side == "right" and self._active_right_cell is not None:
            return self._result.right, self._active_right_cell
        return None, None

    def _update_action_enablement(self) -> None:
        summary, cell = self._selected_side_cell()
        if summary is None or cell is None:
            self.testAgentLabButton.setEnabled(False)
            self.openReplayButton.setEnabled(False)
            return
        orientation = cell.orientation.value
        self.testAgentLabButton.setEnabled(
            not summary_is_group(summary)
            and orientation in (ORIENTATION_CANDIDATE_FIRST, ORIENTATION_OPPONENT_FIRST)
        )
        self.openReplayButton.setEnabled(
            (summary.location.directory / cell.artifact_dir / "replay.jsonl").is_file()
        )

    # ---- Drill-down (reuses the exact signals/handlers EvaluationHistoryDialog uses) ----
    def _on_test_agent_lab(self) -> None:
        summary, cell = self._selected_side_cell()
        if cell is None or summary is None:
            return
        orientation = cell.orientation.value
        if summary_is_group(summary) or orientation not in (
            ORIENTATION_CANDIDATE_FIRST,
            ORIENTATION_OPPONENT_FIRST,
        ):
            return
        self.testInAgentLabRequested.emit(
            cell.subject_id,
            cell.opponent_id,
            cell.seed,
            summary.ticks,
            orientation,
        )

    def _on_open_replay(self) -> None:
        summary, cell = self._selected_side_cell()
        if cell is None:
            return
        self.openReplayRequested.emit(summary.location.directory / cell.artifact_dir / "replay.jsonl")


def _build_history_visual_panel(summary: EvaluationSummary) -> QWidget | None:
    """v3.0 Phase 3: the historical-read counterpart to
    ``app.views.evaluation._build_visual_evidence_panel`` -- this dialog was
    previously the *thinnest* of the four evaluation-presentation surfaces
    (no Wilson interval, no behavior, no capture, no seat/layout
    sensitivity, no interaction matrix), despite being the "drill deeper"
    workflow. This brings it to the same visual depth the live-run results
    dialog and ``evaluations show --json`` already have, from the same
    ``evaluation_analysis``/``evaluation_behavior``/``evaluation_capture``/
    ``evaluation_group_analysis`` dataclasses -- nothing new is computed
    here.
    """

    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(4, 4, 4, 4)
    added = False

    if summary_is_group(summary):
        analysis = group_analysis_for_summary(summary)
        if analysis is not None:
            focus = analysis.summary_for(summary.candidate_id)
            ordered = ([focus] if focus is not None else []) + [
                entrant for entrant in analysis.entrant_summaries if entrant.agent_id != summary.candidate_id
            ]
            for entrant in ordered:
                role = "Focus" if entrant.agent_id == summary.candidate_id else "Roster"
                layout.addWidget(QLabel(f"[{role}] {entrant.agent_id}"))
                layout.addWidget(ProportionBar(rate_stat_bar_data("winner", entrant.winner, color=COLOR_WIN)))
                layout.addWidget(ProportionBar(rate_stat_bar_data("survival", entrant.survival, color=COLOR_WIN)))
                layout.addWidget(
                    ProportionBar(rate_stat_bar_data("eliminated", entrant.elimination, color=COLOR_LOSS))
                )
                added = True
            matrix = analysis.interaction_matrix
            if matrix.pairs or matrix.unattributed_captures:
                layout.addWidget(QLabel("Captures (captor → victim)"))
                grid = InteractionMatrixGrid(matrix)
                layout.addWidget(grid)
                caption_label = QLabel(grid.caption())
                caption_label.setWordWrap(True)
                layout.addWidget(caption_label)
                added = True
    else:
        if summary.analysis is not None:
            layout.addWidget(QLabel("Win rate"))
            layout.addWidget(ProportionBar(win_rate_bar_data(summary.analysis.candidate_overall)))
            if summary.analysis.baseline_overall is not None:
                layout.addWidget(ProportionBar(win_rate_bar_data(summary.analysis.baseline_overall)))
            added = True
        capture = capture_analysis_for_summary(summary)
        if capture is not None:
            overall = capture.candidate_overall
            if overall.available_count:
                layout.addWidget(QLabel("Core capture"))
                layout.addWidget(
                    ProportionBar(
                        plain_rate_bar_data(
                            "captured",
                            overall.capture_rate_suffered,
                            count=overall.captures_suffered,
                            total=overall.available_count,
                            color=COLOR_LOSS,
                        )
                    )
                )
                layout.addWidget(
                    ProportionBar(
                        plain_rate_bar_data(
                            "caused",
                            overall.capture_rate_caused,
                            count=overall.captures_caused,
                            total=overall.available_count,
                            color=COLOR_WIN,
                        )
                    )
                )
                added = True
        behavior = behavior_analysis_for_summary(summary)
        if behavior is not None:
            label = "Behavior vs. baseline (★ = largest difference)" if summary.baseline_id else "Behavior"
            layout.addWidget(QLabel(label))
            for delta, highlighted in ordered_behavior_deltas(behavior):
                layout.addWidget(DimensionDeltaRow(delta, highlighted=highlighted))
            added = True

    layout.addStretch(1)
    return container if added else None


class EvaluationHistoryDialog(QDialog):
    """Main entry point: browse discovered evaluations, inspect one in
    detail (with optional deep verification), drill into a cell's replay or
    rerun it in Agent Lab, inspect agent-revision provenance, and open a
    two-run comparison. Browsing and comparison are read-only and
    process-free; revision restore is the sole explicit nested mutation --
    see the module docstring.
    """

    testInAgentLabRequested = Signal(str, str, int, int, str)
    openReplayRequested = Signal(Path)
    agentCatalogChanged = Signal(str)

    def __init__(
        self,
        data_root: Path,
        *,
        allow_restore: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._data_root = data_root
        self._allow_restore = allow_restore
        self._entries: tuple[DiscoveredEvaluation, ...] = ()
        self._current_summary: EvaluationSummary | None = None
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

        self.visualPanelScroll = QScrollArea()
        self.visualPanelScroll.setWidgetResizable(True)
        self.visualPanelScroll.setMaximumHeight(260)
        detailLayout.addWidget(self.visualPanelScroll)

        detailLayout.addWidget(QLabel("Cells"))
        self.cellsList = QListWidget()
        detailLayout.addWidget(self.cellsList, 1)

        cellActions = QHBoxLayout()
        self.testAgentLabButton = QPushButton("Test in Agent Lab")
        self.testAgentLabButton.setToolTip(_HISTORICAL_AGENT_LAB_TOOLTIP)
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
        # Scoped to this Designer's own resolved data_root, never the
        # ambient default -- the same "make the dependency visible at the
        # call site" practice used throughout app/agent_designer.py (Sec 3
        # of docs/specs/agent_designer_workflow.md), and required here in
        # particular since ``discover()``'s own default silently resolves
        # against whatever ``get_data_root()`` returns in the *current*
        # process, which is not guaranteed to equal ``data_root`` (e.g. a
        # test constructing this dialog against an isolated data root).
        listing = discover_evaluation_listing(roots=(self._data_root / "runs" / "evaluations",))
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

    def _refresh_visual_panel(self, summary: EvaluationSummary | None) -> None:
        old = self.visualPanelScroll.takeWidget()
        if old is not None:
            old.deleteLater()
        if summary is None:
            return
        panel = _build_history_visual_panel(summary)
        if panel is not None:
            self.visualPanelScroll.setWidget(panel)

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
            self._refresh_visual_panel(None)
            return
        if entry.summary is None:
            codes = ", ".join(code.value for code in entry.health.codes) or "unknown"
            details = "\n".join(f"  - {d}" for d in entry.health.detail)
            self.detailText.setPlainText(
                f"This evaluation could not be read.\npath: {entry.location.evaluation_json_path}\n"
                f"health: {codes}\n{details}"
            )
            self._refresh_visual_panel(None)
            return

        try:
            summary, verify_error = load_evaluation_summary(
                entry.location.evaluation_json_path,
                verify=self.verifyCheck.isChecked(),
                data_root=self._data_root,
            )
        except DesignerValidationError as exc:
            self.detailText.setPlainText(f"Could not read this evaluation: {exc}")
            self._refresh_visual_panel(None)
            return

        self._current_summary = summary
        self._current_verify_error = verify_error
        verified = verify_error is None if self.verifyCheck.isChecked() else None
        self.detailText.setPlainText(
            format_evaluation_summary_text(summary, verified=verified, verify_error=verify_error)
        )
        self._refresh_visual_panel(summary)
        self._update_verify_status_label(verified, verify_error)
        for cell in summary.cells:
            item = QListWidgetItem(_cell_row_label(cell, group=summary_is_group(summary)))
            item.setData(Qt.UserRole, cell)
            self.cellsList.addItem(item)
        self.testAgentLabButton.setToolTip(
            "Agent Lab reruns only pairwise cells. Group cells remain available through Open Replay."
            if summary_is_group(summary)
            else _HISTORICAL_AGENT_LAB_TOOLTIP
        )
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
        orientation = cell.orientation.value if cell is not None else None
        self.testAgentLabButton.setEnabled(
            cell is not None
            and self._current_summary is not None
            and not summary_is_group(self._current_summary)
            and orientation in (ORIENTATION_CANDIDATE_FIRST, ORIENTATION_OPPONENT_FIRST)
        )
        self.openReplayButton.setEnabled(
            cell is not None and (self._current_summary.location.directory / cell.artifact_dir / "replay.jsonl").is_file()
        )

    def _on_test_agent_lab(self) -> None:
        cell = self._selected_cell()
        if cell is None or self._current_summary is None:
            return
        orientation = cell.orientation.value
        if summary_is_group(self._current_summary) or orientation not in (
            ORIENTATION_CANDIDATE_FIRST,
            ORIENTATION_OPPONENT_FIRST,
        ):
            return
        # This signal starts a Designer-owned QProcess while the modal
        # History dialog itself remains open. Conservatively disable restore
        # for the rest of this dialog session so the user cannot subsequently
        # overwrite live source underneath that process. Reopening History
        # after the process finishes restores the normal availability check.
        self._allow_restore = False
        self.testInAgentLabRequested.emit(
            cell.subject_id,
            cell.opponent_id,
            cell.seed,
            self._current_summary.ticks,
            orientation,
        )

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
        if (
            not summary_is_group(summary)
            and summary.baseline_id is not None
            and summary.baseline_agent_revision_id.value
        ):
            roles.append(
                (f"baseline: {summary.baseline_id}", summary.baseline_id, summary.baseline_agent_revision_id.value)
            )
        if not summary_is_group(summary):
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

        dialog = RevisionBrowserDialog(
            roles,
            data_root=self._data_root,
            allow_restore=self._allow_restore,
            parent=self,
        )
        dialog.liveAgentFilesChanged.connect(self.agentCatalogChanged.emit)
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
                data_root=self._data_root,
            )
        except DesignerValidationError as exc:
            QMessageBox.warning(self, "Compare Evaluations", str(exc))
            return

        dialog = EvaluationComparisonDialog(result, parent=self)
        # Forward the comparison dialog's own drill-down signals through
        # this dialog's identical, already-connected signals (Sec 10/11 of
        # the v1.3 task) -- AgentDesigner._on_evaluation_history already
        # wires testInAgentLabRequested/openReplayRequested to the exact
        # shared handlers every other drill-down path uses, so no new
        # AgentDesigner-level wiring is needed for comparison rows either.
        dialog.testInAgentLabRequested.connect(self._forward_comparison_agent_lab)
        dialog.openReplayRequested.connect(self.openReplayRequested.emit)
        dialog.exec()

    def _forward_comparison_agent_lab(
        self,
        subject_id: str,
        opponent_id: str,
        seed: int,
        ticks: int,
        orientation: str,
    ) -> None:
        """Forward through the shared handler and lock out restore this session."""

        self._allow_restore = False
        self.testInAgentLabRequested.emit(
            subject_id,
            opponent_id,
            seed,
            ticks,
            orientation,
        )


__all__ = [
    "EvaluationComparisonDialog",
    "EvaluationHistoryDialog",
    "EvaluationPickerDialog",
    "RestoreRevisionDialog",
    "RevisionBrowserDialog",
]
