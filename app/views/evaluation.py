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

from battle_engine.agent_evaluation import (
    ORIENTATION_CANDIDATE_FIRST,
    ORIENTATION_MODE_BOTH,
    ORIENTATION_OPPONENT_FIRST,
    methodology_lines,
)
from battle_engine.evaluation_analysis import EvaluationAnalysis, EvidenceState
from battle_engine.evaluation_presets import ORIENTATION_BOTH as PRESET_ORIENTATION_BOTH
from battle_engine.evaluation_presets import EvaluationPreset
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
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
        python_agents: list[tuple[str, str]],
        *,
        default_candidate: str | None,
        default_output: Path,
        presets: dict[str, EvaluationPreset] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """``python_agents`` is ``(display name, discovery id)`` pairs.

        Every combo/list widget below shows the display name but carries
        the discovery id as its associated data -- ``candidate_id()``/
        ``baseline_id()``/``opponent_ids()`` return only discovery ids, the
        identifiers ``resolve_agent``/``bytefray agents evaluate`` actually
        understand (docs/specs/evaluation_history.md Sec 17).
        ``default_candidate`` is a discovery id, matching the value
        ``candidate_id()`` itself returns.

        ``presets`` (v1.6 Phase 3, docs/V1_6_PHASE3_EVALUATION_PRESETS.md)
        is a name -> already-loaded :class:`EvaluationPreset` mapping --
        this dialog never parses/resolves preset YAML itself (that would be
        a second, GUI-side preset implementation, exactly what the
        governing spec forbids); the caller (``AgentDesigner``) does the
        loading via ``battle_engine.evaluation_presets`` and hands over
        already-typed objects purely for display/prefill.
        """
        super().__init__(parent)
        self.setWindowTitle("Evaluate")
        self._agents = list(python_agents)
        self._presets = dict(presets) if presets else {}

        layout = QVBoxLayout(self)
        form = QFormLayout()

        if self._presets:
            self.presetCombo = QComboBox()
            self.presetCombo.addItem("(none)", None)
            for name in sorted(self._presets):
                self.presetCombo.addItem(name, name)
            self.presetCombo.currentIndexChanged.connect(self._on_preset_selected)
            form.addRow("Preset", self.presetCombo)
        else:
            self.presetCombo = None

        self.candidateCombo = QComboBox()
        for display, agent_id in self._agents:
            self.candidateCombo.addItem(display, agent_id)
        if default_candidate is not None:
            index = self.candidateCombo.findData(default_candidate)
            if index >= 0:
                self.candidateCombo.setCurrentIndex(index)
        form.addRow("Candidate", self.candidateCombo)

        self.baselineCombo = QComboBox()
        self.baselineCombo.addItem("(none)", None)
        for display, agent_id in self._agents:
            self.baselineCombo.addItem(display, agent_id)
        form.addRow("Baseline", self.baselineCombo)

        layout.addLayout(form)

        layout.addWidget(QLabel("Opponents (select one or more)"))
        self.opponentsList = QListWidget()
        self.opponentsList.setSelectionMode(QAbstractItemView.ExtendedSelection)
        for display, agent_id in self._agents:
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, agent_id)
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

        # v0.9 Phase 6 (Phase 5 spec Sec P): the one minimal Designer UX
        # addition -- checked by default, mirroring the CLI's own default
        # (unchecked passes the CLI-equivalent --single-orientation).
        self.bothOrientationsCheck = QCheckBox("Run both entrant orientations (recommended)")
        self.bothOrientationsCheck.setChecked(True)
        layout.addWidget(self.bothOrientationsCheck)

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

    def _on_preset_selected(self) -> None:
        """Populate fields for display -- never binding, always overridable.

        Reused by ``preset_name()``/the launch path only as the *value*
        that was selected; resolution/validation of that value against
        whatever the user edited afterward happens exclusively in the CLI
        subprocess this dialog's own command eventually launches (Sec 14).
        """

        if self.presetCombo is None:
            return
        name = self.presetCombo.currentData()
        if name is None:
            return
        preset = self._presets.get(name)
        if preset is None:
            return
        if preset.candidate_id is not None:
            index = self.candidateCombo.findData(preset.candidate_id)
            if index >= 0:
                self.candidateCombo.setCurrentIndex(index)
        index = self.baselineCombo.findData(preset.baseline_id)
        self.baselineCombo.setCurrentIndex(max(index, 0))
        if preset.opponent_ids is not None:
            wanted = set(preset.opponent_ids)
            for row in range(self.opponentsList.count()):
                item = self.opponentsList.item(row)
                item.setSelected(item.data(Qt.UserRole) in wanted)
        if preset.seeds is not None:
            self.seedsEdit.setText(", ".join(str(s) for s in preset.seeds))
            self.seedRangeEdit.setText("")
        elif preset.seed_range is not None:
            self.seedRangeEdit.setText(f"{preset.seed_range[0]}:{preset.seed_range[1]}")
            self.seedsEdit.setText("")
        if preset.ticks is not None:
            self.ticksSpin.setValue(preset.ticks)
        if preset.orientation is not None:
            self.bothOrientationsCheck.setChecked(preset.orientation == PRESET_ORIENTATION_BOTH)

    def preset_name(self) -> str | None:
        if self.presetCombo is None:
            return None
        return self.presetCombo.currentData()

    def candidate_id(self) -> str:
        return self.candidateCombo.currentData()

    def baseline_id(self) -> str | None:
        return self.baselineCombo.currentData()

    def opponent_ids(self) -> tuple[str, ...]:
        return tuple(item.data(Qt.UserRole) for item in self.opponentsList.selectedItems())

    def seeds_text(self) -> str:
        return self.seedsEdit.text()

    def seed_range_text(self) -> str:
        return self.seedRangeEdit.text()

    def ticks(self) -> int:
        return self.ticksSpin.value()

    def both_orientations(self) -> bool:
        return self.bothOrientationsCheck.isChecked()

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


def _evidence_summary_line(analysis: EvaluationAnalysis) -> str:
    """v1.6 Phase 4 (docs/V1_6_PHASE4_EVALUATION_ANALYSIS.md Sec 14): one
    concise line -- candidate/baseline win-rate interval plus overall
    paired evidence -- from an already-computed ``EvaluationAnalysis``.
    No statistics are computed here, only plain string formatting of
    values the shared ``evaluation_analysis`` module already derived.
    """

    overall = analysis.candidate_overall
    interval = overall.win_interval
    parts = [
        f"candidate {overall.wins}/{overall.matches_played}"
        + (
            f" ({100.0 * (overall.observed_win_rate or 0.0):.0f}%, "
            f"{round(interval.confidence_level * 100)}% CI "
            f"[{100.0 * interval.lower:.0f}%, {100.0 * interval.upper:.0f}%])"
            if interval is not None
            else " (insufficient data)"
        )
    ]
    paired = analysis.overall_paired
    if paired is not None:
        if paired.state == EvidenceState.EVALUATED and paired.exact_p_value is not None:
            parts.append(
                f"better in {paired.improved}/{paired.discordant} discordant pairs  "
                f"exact p={paired.exact_p_value:.3g}"
            )
        elif paired.state == EvidenceState.NO_DISCORDANT_PAIRS:
            parts.append("no discordant pairs")
    return "evidence: " + "  |  ".join(parts)


def _find_cell(
    presentation: EvaluationPresentation, schedule_id: str
) -> EvaluationCellPresentation | None:
    for cell in presentation.cells:
        if cell.schedule_id == schedule_id:
            return cell
    return None


class EvaluationResultsDialog(QDialog):
    """Read-only results viewer: aggregate summary, per-cell/comparison list, drill-down.

    Reads only the already-parsed ``EvaluationPresentation`` -- no agent
    code executes when this dialog opens, exactly like ``TraceInspectorDialog``.
    """

    # subject_id, opponent_id, seed, ticks, orientation
    testInAgentLabRequested = Signal(str, str, int, int, str)
    openReplayRequested = Signal(Path)

    def __init__(self, presentation: EvaluationPresentation, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._presentation = presentation
        self.setWindowTitle(f"Evaluation Results — {presentation.candidate_id}")
        self.resize(720, 560)

        layout = QVBoxLayout(self)

        orientation_line, alignment_line = methodology_lines(presentation.orientation_mode)
        header = QLabel(
            f"evaluation: {presentation.evaluation_id}\n"
            f"candidate: {presentation.candidate_id}\n"
            f"baseline: {presentation.baseline_id or 'none'}\n"
            f"ticks: {presentation.ticks}\n"
            f"{orientation_line}\n"
            f"{alignment_line}"
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
        if presentation.analysis is not None:
            evidence_label = QLabel(_evidence_summary_line(presentation.analysis))
            evidence_label.setWordWrap(True)
            layout.addWidget(evidence_label)

        layout.addWidget(QLabel("Cells" if not presentation.comparison else "Comparison"))
        self.resultsList = QListWidget()
        show_orientation = presentation.orientation_mode == ORIENTATION_MODE_BOTH
        if presentation.comparison:
            for entry in presentation.comparison:
                label = (
                    f"{_classification_label(entry.classification)}  "
                    f"opponent={entry.opponent_id} seed={entry.seed}  "
                    f"candidate={entry.candidate_outcome} baseline={entry.baseline_outcome}"
                )
                if show_orientation:
                    label += f"  orientation={entry.orientation}"
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, entry)
                self.resultsList.addItem(item)
        else:
            for cell in presentation.cells:
                label = (
                    f"[{cell.subject_role}] {cell.subject_id} vs {cell.opponent_id} "
                    f"seed={cell.seed}  status={cell.status} outcome={cell.outcome}"
                )
                if show_orientation:
                    label += f"  orientation={cell.orientation}"
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, cell)
                self.resultsList.addItem(item)
        layout.addWidget(self.resultsList, 1)

        self.detailText = QPlainTextEdit()
        self.detailText.setReadOnly(True)
        layout.addWidget(self.detailText, 1)

        actions = QHBoxLayout()
        self.btnTestAgentLab = QPushButton("Test in Agent Lab")
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
                f"orientation: {payload.orientation}",
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
                f"orientation: {payload.orientation}",
                f"status: {payload.status}",
                f"outcome: {payload.outcome}",
                f"score: subject={payload.score_subject} opponent={payload.score_opponent}",
            ]
        self.detailText.setPlainText("\n".join(lines))
        cell = self._candidate_cell(payload)
        self.btnTestAgentLab.setEnabled(
            cell is not None
            and cell.orientation in (ORIENTATION_CANDIDATE_FIRST, ORIENTATION_OPPONENT_FIRST)
        )
        self.btnOpenReplay.setEnabled(
            cell is not None and (cell.artifact_dir / "replay.jsonl").is_file()
        )

    def _candidate_cell(
        self, payload: EvaluationComparisonPresentation | EvaluationCellPresentation
    ) -> EvaluationCellPresentation | None:
        if isinstance(payload, EvaluationCellPresentation):
            return payload
        if payload.candidate_schedule_id is None:
            return None
        return _find_cell(self._presentation, payload.candidate_schedule_id)

    def _on_test_agent_lab(self) -> None:
        payload = self._selected_payload()
        if payload is None:
            return
        cell = self._candidate_cell(payload)
        if cell is None or cell.orientation not in (
            ORIENTATION_CANDIDATE_FIRST,
            ORIENTATION_OPPONENT_FIRST,
        ):
            return
        self.testInAgentLabRequested.emit(
            cell.subject_id,
            cell.opponent_id,
            cell.seed,
            self._presentation.ticks,
            cell.orientation,
        )

    def _on_open_replay(self) -> None:
        payload = self._selected_payload()
        if payload is None:
            return
        cell = self._candidate_cell(payload)
        if cell is None:
            return
        self.openReplayRequested.emit(cell.artifact_dir / "replay.jsonl")


__all__ = ["EvaluationDialog", "EvaluationResultsDialog"]
