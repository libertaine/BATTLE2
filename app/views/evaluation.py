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
    seat_label,
)
from battle_engine.evaluation_analysis import EvaluationAnalysis, EvidenceState
from battle_engine.evaluation_behavior import BehaviorAnalysis
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
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.services.designer_workflows import (
    EVALUATION_MODE_GROUP,
    EVALUATION_MODE_PAIRWISE,
    DesignerValidationError,
    EvaluationCellPresentation,
    EvaluationComparisonPresentation,
    EvaluationPresentation,
    build_designer_evaluation_plan,
)
from app.services.ruleset_options import RULESET_DESCRIPTION
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
from app.widgets.ruleset_combo import populate_ruleset_combo, selected_ruleset_id


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
        data_root: Path | None = None,
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
        self._data_root = data_root

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.modeCombo = QComboBox()
        self.modeCombo.addItem("Pairwise", EVALUATION_MODE_PAIRWISE)
        self.modeCombo.addItem("Group (3+ entrants)", EVALUATION_MODE_GROUP)
        form.addRow("Evaluation mode", self.modeCombo)

        if self._presets:
            self.presetLabel = QLabel("Preset")
            self.presetCombo = QComboBox()
            self.presetCombo.addItem("(none)", None)
            for name in sorted(self._presets):
                self.presetCombo.addItem(name, name)
            self.presetCombo.currentIndexChanged.connect(self._on_preset_selected)
            form.addRow(self.presetLabel, self.presetCombo)
        else:
            self.presetLabel = None
            self.presetCombo = None

        self.candidateCombo = QComboBox()
        for display, agent_id in self._agents:
            self.candidateCombo.addItem(display, agent_id)
        if default_candidate is not None:
            index = self.candidateCombo.findData(default_candidate)
            if index >= 0:
                self.candidateCombo.setCurrentIndex(index)
        self.candidateLabel = QLabel("Candidate")
        form.addRow(self.candidateLabel, self.candidateCombo)

        self.baselineCombo = QComboBox()
        self.baselineCombo.addItem("(none)", None)
        for display, agent_id in self._agents:
            self.baselineCombo.addItem(display, agent_id)
        self.baselineLabel = QLabel("Baseline")
        form.addRow(self.baselineLabel, self.baselineCombo)

        # Group evaluation is Ruleset-v2-only by construction, so it shows a
        # fixed label. Pairwise gets a real selector: before v3.0.0-alpha2 it
        # passed no --ruleset at all and silently inherited `bytefray agents
        # evaluate`'s backward-compatible v1 methodology without disclosing
        # it, while group mode beside it announced v2. Both modes now state
        # their Ruleset, and pairwise defaults to the current gameplay one.
        self.rulesetLabel = QLabel("Ruleset")
        self.rulesetValue = QLabel("bytefray-rules-2 (required for group evaluation)")
        self.rulesetValue.setAccessibleName("Group evaluation ruleset")
        form.addRow(self.rulesetLabel, self.rulesetValue)

        self.pairwiseRulesetLabel = QLabel("Ruleset")
        self.pairwiseRulesetCombo = QComboBox()
        populate_ruleset_combo(self.pairwiseRulesetCombo)
        self.pairwiseRulesetCombo.setToolTip(RULESET_DESCRIPTION)
        self.pairwiseRulesetCombo.setAccessibleName("Pairwise evaluation ruleset")
        form.addRow(self.pairwiseRulesetLabel, self.pairwiseRulesetCombo)

        layout.addLayout(form)

        self.opponentsLabel = QLabel("Opponents (select one or more)")
        layout.addWidget(self.opponentsLabel)
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
        # v3.0 Phase 4: GUI parity for the CLI's `agents evaluate --workers`
        # (docs/V1_6_PHASE2_PARALLEL_EVALUATION.md) -- bounded subprocess
        # worker parallelism, execution speed only. Default 1 matches the
        # CLI's own serial-equivalent default; never part of `evaluation_id`
        # (see `EvaluationRequest.workers`'s own comment), so changing it
        # never changes what an evaluation means or its result.
        self.workersSpin = QSpinBox()
        self.workersSpin.setRange(1, 64)
        self.workersSpin.setValue(1)
        self.workersSpin.setToolTip(
            "Number of evaluation cells to run concurrently (long-lived worker "
            "subprocesses). Speeds up large evaluations only -- never affects "
            "results or evaluation identity."
        )
        options_row.addRow("Workers", self.workersSpin)
        layout.addLayout(options_row)

        # v0.9 Phase 6 (Phase 5 spec Sec P): the one minimal Designer UX
        # addition -- checked by default, mirroring the CLI's own default
        # (unchecked passes the CLI-equivalent --single-orientation).
        self.bothOrientationsCheck = QCheckBox("Run both entrant orientations (recommended)")
        self.bothOrientationsCheck.setChecked(True)
        layout.addWidget(self.bothOrientationsCheck)

        self.groupMethodologyLabel = QLabel(
            "Group mode fields the focus agent and selected roster members together. "
            "Every distinct seat assignment is scheduled; pairwise orientation does not apply."
        )
        self.groupMethodologyLabel.setWordWrap(True)
        self.groupMethodologyLabel.setAccessibleName("Group seat assignment methodology")
        layout.addWidget(self.groupMethodologyLabel)

        self.previewLabel = QLabel("Authoritative matrix preview")
        self.previewText = QPlainTextEdit()
        self.previewText.setReadOnly(True)
        self.previewText.setAccessibleName("Authoritative group evaluation matrix preview")
        self.previewText.setMaximumHeight(170)
        layout.addWidget(self.previewLabel)
        layout.addWidget(self.previewText)

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
        self.runButton = buttons.button(QDialogButtonBox.Ok)
        self.runButton.setText("Run")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.modeCombo.currentIndexChanged.connect(self._on_mode_changed)
        self.candidateCombo.currentIndexChanged.connect(self._update_group_preview)
        self.baselineCombo.currentIndexChanged.connect(self._update_group_preview)
        self.opponentsList.itemSelectionChanged.connect(self._update_group_preview)
        self.seedsEdit.textChanged.connect(self._update_group_preview)
        self.seedRangeEdit.textChanged.connect(self._update_group_preview)
        self.ticksSpin.valueChanged.connect(self._update_group_preview)
        self.outputEdit.textChanged.connect(self._update_group_preview)
        self._on_mode_changed()
        self.resize(620, 720)

    def _on_mode_changed(self) -> None:
        group = self.mode() == EVALUATION_MODE_GROUP
        self.candidateLabel.setText("Focus agent" if group else "Candidate")
        self.baselineLabel.setVisible(not group)
        self.baselineCombo.setVisible(not group)
        self.rulesetLabel.setVisible(group)
        self.rulesetValue.setVisible(group)
        self.pairwiseRulesetLabel.setVisible(not group)
        self.pairwiseRulesetCombo.setVisible(not group)
        self.opponentsLabel.setText(
            "Roster members (select at least two; focus is included automatically)"
            if group
            else "Opponents (select one or more)"
        )
        self.bothOrientationsCheck.setVisible(not group)
        self.groupMethodologyLabel.setVisible(group)
        self.previewLabel.setVisible(group)
        self.previewText.setVisible(group)
        if self.presetCombo is not None:
            self.presetCombo.setVisible(not group)
        if self.presetLabel is not None:
            self.presetLabel.setVisible(not group)
        self._update_group_preview()

    def _update_group_preview(self) -> None:
        if self.mode() != EVALUATION_MODE_GROUP:
            self.runButton.setEnabled(True)
            self.previewText.clear()
            return
        if self._data_root is None:
            self.previewText.setPlainText("Matrix preview unavailable: no data root was supplied.")
            self.runButton.setEnabled(False)
            return
        try:
            plan = build_designer_evaluation_plan(
                candidate_id=self.candidate_id(),
                baseline_id=None,
                opponent_ids=self.opponent_ids(),
                seeds_text=self.seeds_text(),
                seed_range_text=self.seed_range_text(),
                ticks=self.ticks(),
                output_dir=self.output_path(),
                data_root=self._data_root,
                both_orientations=True,
                mode=EVALUATION_MODE_GROUP,
            )
        except (DesignerValidationError, OSError) as exc:
            self.previewText.setPlainText(f"Configuration invalid: {exc}")
            self.runButton.setEnabled(False)
            return
        self.previewText.setPlainText(plan.preview_text())
        self.runButton.setEnabled(True)

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
        # A preset that names its own Ruleset is surfaced into the selector
        # rather than silently overridden: the launch path now always passes
        # --ruleset explicitly, and an explicit CLI --ruleset takes
        # precedence over a preset's own value (see agent_evaluation.py's
        # `if ruleset_id is None and preset is not None`). Showing it here
        # keeps the preset faithful *and* visible. A preset that names no
        # Ruleset leaves the user's current selection alone -- there is no
        # preset intention to preserve in that case.
        if preset.ruleset_id is not None:
            index = self.pairwiseRulesetCombo.findData(preset.ruleset_id)
            if index >= 0:
                self.pairwiseRulesetCombo.setCurrentIndex(index)

    def pairwise_ruleset_id(self) -> str:
        """The Ruleset to pass explicitly for a pairwise evaluation.

        Group mode ignores this: it is Ruleset-v2-only by construction.
        """
        return selected_ruleset_id(self.pairwiseRulesetCombo)

    def preset_name(self) -> str | None:
        if self.presetCombo is None or self.mode() == EVALUATION_MODE_GROUP:
            return None
        return self.presetCombo.currentData()

    def mode(self) -> str:
        return str(self.modeCombo.currentData())

    def candidate_id(self) -> str:
        return self.candidateCombo.currentData()

    def baseline_id(self) -> str | None:
        if self.mode() == EVALUATION_MODE_GROUP:
            return None
        return self.baselineCombo.currentData()

    def opponent_ids(self) -> tuple[str, ...]:
        return tuple(item.data(Qt.UserRole) for item in self.opponentsList.selectedItems())

    def seeds_text(self) -> str:
        return self.seedsEdit.text()

    def seed_range_text(self) -> str:
        return self.seedRangeEdit.text()

    def ticks(self) -> int:
        return self.ticksSpin.value()

    def workers(self) -> int:
        return self.workersSpin.value()

    def both_orientations(self) -> bool:
        if self.mode() == EVALUATION_MODE_GROUP:
            return True
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


def _behavior_summary_line(behavior: BehaviorAnalysis) -> str:
    """v1.6 Phase 5 (docs/V1_6_PHASE5_BEHAVIOR_ANALYSIS.md Sec 20): one
    concise line -- survival, write activity, territory retention -- from
    an already-computed ``BehaviorAnalysis``. No behavioral measurement
    happens here, only plain string formatting of values the shared
    ``evaluation_behavior`` module already derived. Deliberately a
    separate line from ``_evidence_summary_line`` above -- behavior (how
    the candidate played) and evidence (whether it won) stay visually
    distinct, never merged into one line.
    """

    overall = behavior.candidate_overall
    if overall.sample_count == 0:
        return "behavior: insufficient data (0 scored cells)"
    survival = overall.dimension("survival_fraction")
    writes = overall.dimension("writes_per_tick")
    retention = overall.dimension("territory_retention")
    parts = [
        f"survival {100.0 * survival.mean:.0f}%" if survival.mean is not None else "survival n/a",
        f"writes/tick {writes.mean:.2f}" if writes.mean is not None else "writes/tick n/a",
        f"territory retention {100.0 * retention.mean:.0f}%" if retention.mean is not None else "retention n/a",
    ]
    if behavior.candidate_vs_baseline_largest:
        parts.append("largest vs. baseline: " + ", ".join(behavior.candidate_vs_baseline_largest))
    return "behavior: " + "  |  ".join(parts)


def _seat_assignment_text(agent_ids: tuple[str, ...]) -> str:
    return ", ".join(f"{seat_label(index)}={agent_id}" for index, agent_id in enumerate(agent_ids))


def _group_summary_lines(presentation: EvaluationPresentation) -> tuple[str, ...]:
    analysis = presentation.group_analysis
    if analysis is None:
        return ("Group analysis: no scored cells are available yet.",)
    lines = [
        (
            f"Group analysis: {analysis.available_cells}/{analysis.cells_analyzed} cells available; "
            "rates use physical entrant instances."
        )
    ]
    focus = analysis.summary_for(presentation.candidate_id)
    ordered = ([focus] if focus is not None else []) + [
        summary
        for summary in analysis.entrant_summaries
        if summary.agent_id != presentation.candidate_id
    ]
    for summary in ordered:
        role = "Focus" if summary.agent_id == presentation.candidate_id else "Roster"
        winner_rate = (
            f"{summary.winner.successes}/{summary.winner.trials} "
            f"({100.0 * (summary.winner.rate or 0.0):.0f}%)"
            if summary.winner.trials
            else "0/0 (n/a)"
        )
        survival_rate = (
            f"{summary.survival.successes}/{summary.survival.trials} "
            f"({100.0 * (summary.survival.rate or 0.0):.0f}%)"
            if summary.survival.trials
            else "0/0 (n/a)"
        )
        multiplicity = analysis.roster_multiplicity.get(summary.agent_id, 0)
        lines.append(
            f"[{role}] {summary.agent_id} ×{multiplicity}: winner={winner_rate}; "
            f"survival={survival_rate}; physical samples={summary.available_count}"
        )
    return tuple(lines)


def _find_cell(
    presentation: EvaluationPresentation, schedule_id: str
) -> EvaluationCellPresentation | None:
    for cell in presentation.cells:
        if cell.schedule_id == schedule_id:
            return cell
    return None


def _build_visual_evidence_panel(presentation: EvaluationPresentation) -> QWidget | None:
    """v3.0 Phase 3: a genuinely visual rendering of already-computed
    evidence -- win-rate bars with their own Wilson interval, per-dimension
    behavior bars (candidate vs. baseline where one exists), core-capture
    rates, and (for a group evaluation) per-entrant rate bars plus the
    captor -> victim interaction matrix. Every value here already exists on
    ``presentation``'s own analysis/behavior/capture/group_analysis fields
    -- nothing is computed in this function; it only chooses how to draw
    values ``designer_workflows.read_evaluation_presentation`` already
    derived via the shared engine analysis modules.
    """

    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(4, 4, 4, 4)
    added = False

    if presentation.group:
        analysis = presentation.group_analysis
        if analysis is not None:
            focus = analysis.summary_for(presentation.candidate_id)
            ordered = ([focus] if focus is not None else []) + [
                summary for summary in analysis.entrant_summaries if summary.agent_id != presentation.candidate_id
            ]
            for summary in ordered:
                role = "Focus" if summary.agent_id == presentation.candidate_id else "Roster"
                layout.addWidget(QLabel(f"[{role}] {summary.agent_id}"))
                layout.addWidget(ProportionBar(rate_stat_bar_data("winner", summary.winner, color=COLOR_WIN)))
                layout.addWidget(ProportionBar(rate_stat_bar_data("survival", summary.survival, color=COLOR_WIN)))
                layout.addWidget(ProportionBar(rate_stat_bar_data("eliminated", summary.elimination, color=COLOR_LOSS)))
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
        if presentation.analysis is not None:
            layout.addWidget(QLabel("Win rate"))
            layout.addWidget(ProportionBar(win_rate_bar_data(presentation.analysis.candidate_overall)))
            if presentation.analysis.baseline_overall is not None:
                layout.addWidget(ProportionBar(win_rate_bar_data(presentation.analysis.baseline_overall)))
            added = True
        if presentation.capture is not None:
            overall = presentation.capture.candidate_overall
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
        if presentation.behavior is not None:
            label = "Behavior vs. baseline (★ = largest difference)" if presentation.baseline_id else "Behavior"
            layout.addWidget(QLabel(label))
            for delta, highlighted in ordered_behavior_deltas(presentation.behavior):
                layout.addWidget(DimensionDeltaRow(delta, highlighted=highlighted))
            added = True

    layout.addStretch(1)
    return container if added else None


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

        if presentation.group:
            header_text = (
                f"evaluation: {presentation.evaluation_id}\n"
                f"mode: Group\n"
                f"focus agent: {presentation.candidate_id}\n"
                f"roster: {', '.join(presentation.roster_agent_ids)}\n"
                f"ruleset: {presentation.rules_compatibility_id or 'unknown'}\n"
                f"ticks: {presentation.ticks}\n"
                f"Arena alignment: {presentation.arena_alignment_mode}"
            )
        else:
            orientation_line, alignment_line = methodology_lines(
                presentation.orientation_mode,
                arena_alignment_mode=presentation.arena_alignment_mode,
            )
            header_text = (
                f"evaluation: {presentation.evaluation_id}\n"
                f"candidate: {presentation.candidate_id}\n"
                f"baseline: {presentation.baseline_id or 'none'}\n"
                f"ticks: {presentation.ticks}\n"
                f"{orientation_line}\n"
                f"{alignment_line}"
            )
        header = QLabel(header_text)
        header.setWordWrap(True)
        layout.addWidget(header)

        if presentation.group:
            for line in _group_summary_lines(presentation):
                summary_label = QLabel(line)
                summary_label.setWordWrap(True)
                layout.addWidget(summary_label)
        else:
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
        if presentation.behavior is not None:
            behavior_label = QLabel(_behavior_summary_line(presentation.behavior))
            behavior_label.setWordWrap(True)
            layout.addWidget(behavior_label)

        visual_panel = _build_visual_evidence_panel(presentation)
        if visual_panel is not None:
            scroll = QScrollArea()
            scroll.setWidget(visual_panel)
            scroll.setWidgetResizable(True)
            scroll.setMaximumHeight(280)
            layout.addWidget(scroll)

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
                if presentation.group:
                    label = (
                        f"layout={cell.layout_id} seed={cell.seed}  "
                        f"seats: {_seat_assignment_text(cell.seat_agent_ids)}  "
                        f"status={cell.status} focus outcome={cell.outcome}"
                    )
                else:
                    label = (
                        f"[{cell.subject_role}] {cell.subject_id} vs {cell.opponent_id} "
                        f"seed={cell.seed}  status={cell.status} outcome={cell.outcome}"
                    )
                if show_orientation and not presentation.group:
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
        if presentation.group:
            self.btnTestAgentLab.setToolTip(
                "Agent Lab reruns only pairwise cells. Group cells must be inspected via their canonical replay."
            )
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
            if self._presentation.group:
                lines = [
                    f"focus agent: {payload.subject_id}",
                    f"roster: {', '.join(payload.roster_agent_ids)}",
                    f"layout: {payload.layout_id}",
                    f"seat assignment: {_seat_assignment_text(payload.seat_agent_ids)}",
                    f"seat starts: {', '.join(str(value) for value in payload.seat_starts)}",
                    f"seed: {payload.seed}",
                    f"status: {payload.status}",
                    f"focus outcome: {payload.outcome}",
                    "Agent Lab rerun: unavailable for multi-entrant cells",
                ]
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
            and not self._presentation.group
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
        if self._presentation.group or cell is None or cell.orientation not in (
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
