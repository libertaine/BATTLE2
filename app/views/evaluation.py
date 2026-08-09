"""Evaluation dialogs: run configuration and read-only results (v0.6).

Extends the existing Agent Development workflow rather than adding a
fourth top-level tab (``docs/specs/agent_evaluation.md`` Sec 13, mirroring
Agent Lab's own precedent of extending the Development tab rather than
inventing a new one). ``EvaluationDialog`` is a plain input collector --
structurally the existing ``TournamentDialog`` pattern -- that hands its
selections back to ``AgentDesigner``, which builds and launches the actual
``bytefray agents evaluate`` command via the existing out-of-process
``QProcess`` machinery (arbitrary user agent code runs during evaluation,
exactly like Validate/Test/Tournament). ``EvaluationResultsDialog`` is
read-only: it only formats an already-parsed
:class:`app.services.designer_workflows.EvaluationPresentation`, executes
no agent code, and offers two drill-down actions (test the exact cell in
Agent Lab; open its replay) via signals the Designer wires to its existing
launchers -- it does not invent a second execution path of its own.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.services.designer_workflows import (
    EvaluationCellPresentation,
    EvaluationComparisonPresentation,
    EvaluationPresentation,
)


class EvaluationDialog(QDialog):
    """Collects candidate/baseline/opponents/seeds/ticks/output for one run.

    Never builds or validates the ``bytefray agents evaluate`` argument
    list itself -- that is
    ``app.services.designer_workflows.build_designer_evaluate_command``'s
    job, called by ``AgentDesigner`` after this dialog is accepted, so
    there is exactly one place evaluation arguments are assembled (shared
    with any future non-GUI caller of that function).
    """

    def __init__(
        self,
        python_agent_names: list[str],
        *,
        default_candidate: str | None,
        default_output: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Evaluate")
        self._names = list(python_agent_names)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.candidateCombo = QComboBox()
        self.candidateCombo.addItems(self._names)
        if default_candidate is not None:
            index = self.candidateCombo.findText(default_candidate)
            if index >= 0:
                self.candidateCombo.setCurrentIndex(index)
        form.addRow("Candidate", self.candidateCombo)

        self.baselineCombo = QComboBox()
        self.baselineCombo.addItem("(none)", None)
        for name in self._names:
            self.baselineCombo.addItem(name, name)
        form.addRow("Baseline", self.baselineCombo)

        layout.addLayout(form)

        layout.addWidget(QLabel("Opponents (select one or more)"))
        self.opponentsList = QListWidget()
        self.opponentsList.setSelectionMode(QAbstractItemView.ExtendedSelection)
        for name in self._names:
            item = QListWidgetItem(name)
            self.opponentsList.addItem(item)
        layout.addWidget(self.opponentsList)

        seeds_row = QFormLayout()
        self.seedsEdit = QLineEdit()
        self.seedsEdit.setPlaceholderText("e.g. 1,2,3,4,5")
        seeds_row.addRow("Seeds", self.seedsEdit)
        self.seedRangeEdit = QLineEdit()
        self.seedRangeEdit.setPlaceholderText("e.g. 1000:1010 (alternative to Seeds)")
        seeds_row.addRow("Seed range", self.seedRangeEdit)
        layout.addLayout(seeds_row)

        options_row = QFormLayout()
        self.ticksSpin = QSpinBox()
        self.ticksSpin.setRange(1, 2_147_483_647)
        self.ticksSpin.setValue(200)
        options_row.addRow("Ticks", self.ticksSpin)
        layout.addLayout(options_row)

        output_row = QHBoxLayout()
        self.outputEdit = QLineEdit(str(default_output))
        choose = QPushButton("Choose…")
        choose.clicked.connect(self._choose_output)
        output_row.addWidget(self.outputEdit, 1)
        output_row.addWidget(choose)
        form2 = QFormLayout()
        form2.addRow("Output", output_row)
        layout.addLayout(form2)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Run")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(560, 520)

    def candidate_id(self) -> str:
        return self.candidateCombo.currentText()

    def baseline_id(self) -> str | None:
        return self.baselineCombo.currentData()

    def opponent_ids(self) -> tuple[str, ...]:
        return tuple(item.text() for item in self.opponentsList.selectedItems())

    def seeds_text(self) -> str:
        return self.seedsEdit.text()

    def seed_range_text(self) -> str:
        return self.seedRangeEdit.text()

    def ticks(self) -> int:
        return self.ticksSpin.value()

    def output_path(self) -> Path:
        return Path(self.outputEdit.text())

    def _choose_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Evaluation Output", self.outputEdit.text())
        if path:
            self.outputEdit.setText(path)


def _classification_label(classification: str) -> str:
    return {
        "improved": "IMPROVED",
        "regressed": "REGRESSED",
        "unchanged": "unchanged",
        "inconclusive": "inconclusive",
    }.get(classification, classification)


def _find_cell(
    presentation: EvaluationPresentation, role: str, opponent_id: str, seed: int
) -> EvaluationCellPresentation | None:
    for cell in presentation.cells:
        if cell.subject_role == role and cell.opponent_id == opponent_id and cell.seed == seed:
            return cell
    return None


class EvaluationResultsDialog(QDialog):
    """Read-only results viewer: aggregate summary, per-cell/comparison list, drill-down.

    Reads only the already-parsed ``EvaluationPresentation`` -- no agent
    code executes when this dialog opens, exactly like ``TraceInspectorDialog``.
    """

    testInAgentLabRequested = Signal(str, str, int)  # subject_id, opponent_id, seed
    openReplayRequested = Signal(Path)

    def __init__(self, presentation: EvaluationPresentation, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._presentation = presentation
        self.setWindowTitle(f"Evaluation Results — {presentation.candidate_id}")
        self.resize(720, 560)

        layout = QVBoxLayout(self)

        header = QLabel(
            f"evaluation: {presentation.evaluation_id}\n"
            f"candidate: {presentation.candidate_id}\n"
            f"baseline: {presentation.baseline_id or 'none'}\n"
            f"ticks: {presentation.ticks}"
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        for aggregate in presentation.aggregates:
            layout.addWidget(
                QLabel(
                    f"[{aggregate.subject_role}] {aggregate.subject_id}: "
                    f"{aggregate.wins}W {aggregate.losses}L {aggregate.ties}T "
                    f"({aggregate.matches_played} played)"
                )
            )

        layout.addWidget(QLabel("Cells" if not presentation.comparison else "Comparison"))
        self.resultsList = QListWidget()
        if presentation.comparison:
            for entry in presentation.comparison:
                label = (
                    f"{_classification_label(entry.classification)}  "
                    f"opponent={entry.opponent_id} seed={entry.seed}  "
                    f"candidate={entry.candidate_outcome} baseline={entry.baseline_outcome}"
                )
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, entry)
                self.resultsList.addItem(item)
        else:
            for cell in presentation.cells:
                label = (
                    f"[{cell.subject_role}] {cell.subject_id} vs {cell.opponent_id} "
                    f"seed={cell.seed}  status={cell.status} outcome={cell.outcome}"
                )
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, cell)
                self.resultsList.addItem(item)
        layout.addWidget(self.resultsList, 1)

        self.detailText = QPlainTextEdit()
        self.detailText.setReadOnly(True)
        layout.addWidget(self.detailText, 1)

        actions = QHBoxLayout()
        self.btnTestAgentLab = QPushButton("Test Candidate in Agent Lab")
        self.btnTestAgentLab.setEnabled(False)
        self.btnOpenReplay = QPushButton("Open Replay")
        self.btnOpenReplay.setEnabled(False)
        actions.addWidget(self.btnTestAgentLab)
        actions.addWidget(self.btnOpenReplay)
        actions.addStretch(1)
        layout.addLayout(actions)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        self.resultsList.currentItemChanged.connect(self._on_selection_changed)
        self.btnTestAgentLab.clicked.connect(self._on_test_agent_lab)
        self.btnOpenReplay.clicked.connect(self._on_open_replay)

    # ---- Internal ----
    def _selected_payload(self) -> EvaluationComparisonPresentation | EvaluationCellPresentation | None:
        item = self.resultsList.currentItem()
        if item is None:
            return None
        return item.data(Qt.UserRole)

    def _on_selection_changed(self) -> None:
        payload = self._selected_payload()
        if payload is None:
            self.btnTestAgentLab.setEnabled(False)
            self.btnOpenReplay.setEnabled(False)
            self.detailText.setPlainText("")
            return
        if isinstance(payload, EvaluationComparisonPresentation):
            lines = [
                f"opponent: {payload.opponent_id}",
                f"seed: {payload.seed}",
                f"classification: {payload.classification}",
                f"candidate outcome: {payload.candidate_outcome}",
                f"baseline outcome: {payload.baseline_outcome}",
                "",
                f"rerun candidate: {payload.rerun_candidate}",
            ]
            if payload.rerun_baseline:
                lines.append(f"rerun baseline:  {payload.rerun_baseline}")
        else:
            lines = [
                f"subject: [{payload.subject_role}] {payload.subject_id}",
                f"opponent: {payload.opponent_id}",
                f"seed: {payload.seed}",
                f"status: {payload.status}",
                f"outcome: {payload.outcome}",
                f"score: subject={payload.score_subject} opponent={payload.score_opponent}",
            ]
        self.detailText.setPlainText("\n".join(lines))
        cell = self._candidate_cell(payload)
        self.btnTestAgentLab.setEnabled(cell is not None)
        self.btnOpenReplay.setEnabled(
            cell is not None and (cell.artifact_dir / "replay.jsonl").is_file()
        )

    def _candidate_cell(
        self, payload: EvaluationComparisonPresentation | EvaluationCellPresentation
    ) -> EvaluationCellPresentation | None:
        if isinstance(payload, EvaluationCellPresentation):
            return payload
        return _find_cell(self._presentation, "candidate", payload.opponent_id, payload.seed)

    def _on_test_agent_lab(self) -> None:
        payload = self._selected_payload()
        if payload is None:
            return
        cell = self._candidate_cell(payload)
        if cell is None:
            return
        self.testInAgentLabRequested.emit(cell.subject_id, cell.opponent_id, cell.seed)

    def _on_open_replay(self) -> None:
        payload = self._selected_payload()
        if payload is None:
            return
        cell = self._candidate_cell(payload)
        if cell is None:
            return
        self.openReplayRequested.emit(cell.artifact_dir / "replay.jsonl")


__all__ = ["EvaluationDialog", "EvaluationResultsDialog"]
