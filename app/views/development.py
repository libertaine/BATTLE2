"""Agent Development tab: Python agent catalog, creation, folder access, validation, test.

Phase 4a scope: agent selection, ``New Agent`` (a direct, in-process call to
``battle_engine.agent_scaffold.create_agent``), and ``Open Agent Folder``.
Phase 4b adds ``Validate``: an out-of-process (QProcess) run of ``bytefray
agents validate <agent-id>``, reusing the exact Phase 2 CLI/service
semantics with no reimplemented diagnostic taxonomy (see
``docs/specs/agent_designer_workflow.md`` Sec 5/Sec 10 and
``app/services/agent_workflows.py``). Phase 4c adds ``Test``: an
out-of-process run of ``bytefray agents test <agent-id> [options]``,
reusing the same process-boundary reasoning plus the exact Phase 3
CLI/service semantics for the three outcome shapes (completed match,
initialization failure, tool failure -- Sec 11/Sec 12 of the Designer
spec). Development Test's own "Open Replay" reuses the existing external
Pygame launcher (``app/services/engine_commands.py``); it is deliberately
independent of the Designer's Simple/Advanced "Open Last Replay" state
(Sec 13 of the spec).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from battle_engine.agent_scaffold import (
    AGENT_ID_PATTERN,
    MAX_AGENT_ID_LENGTH,
    AgentScaffoldError,
    ScaffoldResult,
    create_agent,
)
from battle_engine.agent_test import DEFAULT_AGENT_TIMEOUT, DEFAULT_TICKS
from battle_engine.config import Config
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.services.agent_catalog import AgentRow
from app.services.agent_workflows import DevelopmentTestPresentation, ValidationPresentation

_INVALID_STYLE = "color: #b00020;"
_TOOL_FAILURE_STYLE = "color: #b06000;"
_NEUTRAL_STYLE = ""

_DEFAULT_TEST_SEED = Config().seed
_DEFAULT_TEST_TICKS = DEFAULT_TICKS
_MAX_SPINBOX_INT = 2_147_483_647


def _is_python_agent(row: AgentRow) -> bool:
    meta = row.meta if isinstance(row.meta, dict) else {}
    return meta.get("kind") == "python"


class NewAgentDialog(QDialog):
    """Minimal 'New Agent' dialog: a single agent-id field.

    Calls ``create_agent`` directly and synchronously on OK (Sec 5/Sec 8 of
    the Phase 4 spec -- scaffolding executes no agent-author code, so no
    process boundary or progress indicator is needed). On an expected
    ``AgentScaffoldError``/``OSError`` (invalid id, duplicate, unwritable
    root), the error is shown inline and the dialog stays open so the user
    can correct the id and retry.
    """

    def __init__(self, battle_root: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Agent")
        self._battle_root = battle_root
        self.result: Optional[ScaffoldResult] = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Agent ID"))
        self.agentId = QLineEdit()
        layout.addWidget(self.agentId)

        hint = QLabel(
            f"Must match {AGENT_ID_PATTERN.pattern} "
            f"(max {MAX_AGENT_ID_LENGTH} characters)."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.errorLabel = QLabel("")
        self.errorLabel.setStyleSheet(_INVALID_STYLE)
        self.errorLabel.setWordWrap(True)
        self.errorLabel.setVisible(False)
        layout.addWidget(self.errorLabel)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(420, 200)

    def _on_ok(self) -> None:
        agent_id = self.agentId.text().strip()
        if not agent_id:
            self._show_error("Agent ID is required.")
            return
        try:
            self.result = create_agent(agent_id, data_root=self._battle_root)
        except (AgentScaffoldError, OSError) as exc:
            self._show_error(str(exc))
            return
        self.accept()

    def _show_error(self, message: str) -> None:
        self.errorLabel.setText(message)
        self.errorLabel.setVisible(True)


class AgentDevelopmentPanel(QWidget):
    """Agent Development tab: catalog selection, New Agent, Open Folder, Validate.

    Only ``kind: python`` agents are shown -- v0.4 authoring (create,
    validate, development-test) applies to Agent API v1 Python agents only,
    and ``Open Agent Folder``/``Validate`` must only ever be available for a
    real, user-owned Python agent directory (never a VM built-in/starter or
    the internal reference opponent, which is never discoverable through
    the catalog at all).
    """

    refreshAgentsRequested = Signal()
    newAgentRequested = Signal()
    openFolderRequested = Signal()
    validateRequested = Signal()
    testRequested = Signal()
    openTestReplayRequested = Signal()
    inspectTraceRequested = Signal()
    evaluateRequested = Signal()

    def __init__(self, catalog=None) -> None:  # catalog kept for parity with other panels
        super().__init__()
        self._rows: List[AgentRow] = []
        self._busy = False
        self._current_agent_name: Optional[str] = None
        self._last_validation: Optional[ValidationPresentation] = None
        self._last_test: Optional[DevelopmentTestPresentation] = None
        self._last_test_replay: Optional[Path] = None
        self._last_test_trace: Optional[Path] = None

        root = QVBoxLayout(self)

        header = QGroupBox("Agent")
        header_row = QHBoxLayout(header)
        header_row.addWidget(QLabel("Agent"))
        self.agentCombo = QComboBox()
        header_row.addWidget(self.agentCombo, 1)
        self.btnRefresh = QPushButton("Refresh")
        self.btnNewAgent = QPushButton("New Agent…")
        self.btnOpenFolder = QPushButton("Open Folder")
        self.btnOpenFolder.setEnabled(False)
        header_row.addWidget(self.btnRefresh)
        header_row.addWidget(self.btnNewAgent)
        header_row.addWidget(self.btnOpenFolder)
        root.addWidget(header)

        validation = QGroupBox("Validation")
        validation_layout = QVBoxLayout(validation)
        self.btnValidate = QPushButton("Validate")
        self.btnValidate.setEnabled(False)
        validation_layout.addWidget(self.btnValidate)
        root.addWidget(validation)

        test = QGroupBox("Development Test")
        test_layout = QVBoxLayout(test)
        options_row = QHBoxLayout()
        options_row.addWidget(QLabel("Opponent"))
        self.opponentCombo = QComboBox()
        options_row.addWidget(self.opponentCombo, 1)
        options_row.addWidget(QLabel("Seed"))
        self.seedSpin = QSpinBox()
        self.seedSpin.setRange(0, _MAX_SPINBOX_INT)
        self.seedSpin.setValue(_DEFAULT_TEST_SEED)
        options_row.addWidget(self.seedSpin)
        options_row.addWidget(QLabel("Ticks"))
        self.ticksSpin = QSpinBox()
        self.ticksSpin.setRange(1, _MAX_SPINBOX_INT)
        self.ticksSpin.setValue(_DEFAULT_TEST_TICKS)
        options_row.addWidget(self.ticksSpin)
        options_row.addWidget(QLabel("Timeout (s)"))
        self.timeoutSpin = QDoubleSpinBox()
        self.timeoutSpin.setDecimals(1)
        self.timeoutSpin.setRange(0.1, 300.0)
        self.timeoutSpin.setValue(DEFAULT_AGENT_TIMEOUT)
        self.timeoutSpin.setToolTip(
            "Per-call load/reset/act timeout for supervised worker execution.\n"
            "Development-time hang containment only -- not a security sandbox."
        )
        options_row.addWidget(self.timeoutSpin)
        test_layout.addLayout(options_row)

        self.btnTest = QPushButton("Test")
        self.btnTest.setEnabled(False)
        test_layout.addWidget(self.btnTest)

        self.testStatusLabel = QLabel("No agent selected.")
        self.testStatusLabel.setWordWrap(True)
        test_layout.addWidget(self.testStatusLabel)

        replay_row = QHBoxLayout()
        self.btnOpenTestReplay = QPushButton("Open Replay")
        self.btnOpenTestReplay.setEnabled(False)
        replay_row.addWidget(self.btnOpenTestReplay)
        self.btnInspectTrace = QPushButton("Inspect Trace")
        self.btnInspectTrace.setEnabled(False)
        replay_row.addWidget(self.btnInspectTrace)
        test_layout.addLayout(replay_row)
        root.addWidget(test)

        evaluation = QGroupBox("Evaluation")
        evaluation_layout = QVBoxLayout(evaluation)
        self.btnEvaluate = QPushButton("Evaluate…")
        self.btnEvaluate.setEnabled(False)
        self.btnEvaluate.setToolTip(
            "Run a deterministic candidate/baseline evaluation matrix against "
            "explicit opponents and seeds. See docs/AGENT_LAB.md."
        )
        evaluation_layout.addWidget(self.btnEvaluate)
        root.addWidget(evaluation)

        status = QGroupBox("Status")
        status_layout = QVBoxLayout(status)
        self.statusLabel = QLabel("No agent selected.")
        self.statusLabel.setWordWrap(True)
        status_layout.addWidget(self.statusLabel)
        root.addWidget(status, 1)

        self.btnRefresh.clicked.connect(self.refreshAgentsRequested.emit)
        self.btnNewAgent.clicked.connect(self.newAgentRequested.emit)
        self.btnOpenFolder.clicked.connect(self.openFolderRequested.emit)
        self.btnValidate.clicked.connect(self.validateRequested.emit)
        self.btnTest.clicked.connect(self.testRequested.emit)
        self.btnOpenTestReplay.clicked.connect(self.openTestReplayRequested.emit)
        self.btnInspectTrace.clicked.connect(self.inspectTraceRequested.emit)
        self.btnEvaluate.clicked.connect(self.evaluateRequested.emit)
        self.agentCombo.currentTextChanged.connect(self._on_combo_changed)

        self.opponentCombo.addItem("Reference", None)
        self._update_enablement()

    # ---- API consumed by AgentDesigner ----
    def setAgents(self, rows: List[AgentRow]) -> None:
        """Repopulate the combo from the full catalog, keeping python agents only."""
        self._rows = [row for row in rows if _is_python_agent(row)]
        names = [row.name for row in self._rows]
        prev = self.agentCombo.currentText()
        self.agentCombo.blockSignals(True)
        self.agentCombo.clear()
        self.agentCombo.addItems(names)
        if prev:
            idx = self.agentCombo.findText(prev)
            if idx >= 0:
                self.agentCombo.setCurrentIndex(idx)
        self.agentCombo.blockSignals(False)
        self._refresh_opponent_combo()
        self._on_combo_changed(self.agentCombo.currentText())

    def _refresh_opponent_combo(self) -> None:
        """Repopulate the opponent combo: 'Reference' plus every Python agent.

        The CLI permits testing an agent against itself
        (``docs/specs/agent_designer_workflow.md`` Sec 23 item 3); this
        picker does not narrow that -- the currently tested agent stays
        selectable as its own opponent.
        """
        prev_data = self.opponentCombo.currentData()
        self.opponentCombo.blockSignals(True)
        self.opponentCombo.clear()
        self.opponentCombo.addItem("Reference", None)
        for row in self._rows:
            self.opponentCombo.addItem(row.name, row.name)
        index = 0
        if prev_data is not None:
            found = self.opponentCombo.findData(prev_data)
            if found >= 0:
                index = found
        self.opponentCombo.setCurrentIndex(index)
        self.opponentCombo.blockSignals(False)

    def selected_opponent_id(self) -> Optional[str]:
        """The ``--opponent`` value to pass, or ``None`` for the internal reference."""
        return self.opponentCombo.currentData()

    def selected_seed(self) -> int:
        return self.seedSpin.value()

    def selected_ticks(self) -> int:
        return self.ticksSpin.value()

    def selected_timeout(self) -> float:
        return self.timeoutSpin.value()

    def last_test_trace_path(self) -> Optional[Path]:
        """The last completed test's trace path, or ``None`` if unavailable."""
        return self._last_test_trace

    def last_test_replay_path(self) -> Optional[Path]:
        """The last completed test's replay path, or ``None`` if unavailable.

        Independent of ``AgentDesigner._last_replay`` (Sec 13 of the Phase
        4 spec): a development test's replay is never promoted to the
        Designer's Simple/Advanced "Open Last Replay" target, so switching
        tabs never surprises a user with a replay they did not expect.
        """
        return self._last_test_replay

    def selectAgent(self, agent_id: str) -> None:
        idx = self.agentCombo.findText(agent_id)
        if idx >= 0:
            self.agentCombo.setCurrentIndex(idx)
        self._on_combo_changed(self.agentCombo.currentText())

    def selectedAgentRow(self) -> Optional[AgentRow]:
        name = self.agentCombo.currentText()
        for row in self._rows:
            if row.name == name:
                return row
        return None

    def setStatus(self, message: str) -> None:
        """Used by the New Agent creation-success message (Phase 4a)."""
        self.statusLabel.setStyleSheet(_NEUTRAL_STYLE)
        self.statusLabel.setText(message)

    def setBusy(self, busy: bool) -> None:
        """Disable interactive controls while any Designer process is active.

        Shared with match/tournament launch in Simple/Advanced (Sec 14.1 of
        the Phase 4 spec): exactly one Designer-owned process may run at a
        time, so Validate is disabled while a match/tournament runs, and
        Simple/Advanced's Run buttons are disabled while a validation runs
        (wired by ``AgentDesigner``, not this panel).
        """
        self._busy = busy
        self.agentCombo.setEnabled(not busy)
        self.btnNewAgent.setEnabled(not busy)
        self.btnRefresh.setEnabled(not busy)
        self.opponentCombo.setEnabled(not busy)
        self.seedSpin.setEnabled(not busy)
        self.ticksSpin.setEnabled(not busy)
        self.timeoutSpin.setEnabled(not busy)
        self._update_enablement()

    def python_agent_names(self) -> list[tuple[str, str]]:
        """Every discovered Python agent as ``(display name, discovery id)``.

        The Evaluate dialog must display ``row.name`` (display) but always
        hand ``row.agent_id`` (discovery id) back to the CLI --
        ``resolve_agent`` looks agents up by discovery id, not display name,
        and the two can differ (docs/specs/evaluation_history.md Sec 17).
        """
        return [(row.name, row.agent_id) for row in self._rows]

    def showValidating(self, agent_id: str) -> None:
        self.statusLabel.setStyleSheet(_NEUTRAL_STYLE)
        self.statusLabel.setText(f"Validating {agent_id}…")

    def show_validation_result(self, presentation: ValidationPresentation) -> None:
        self._last_validation = presentation
        if presentation.is_tool_failure:
            lines = ["Last validation: Could not be completed"]
            if presentation.error:
                lines.append(presentation.error)
            if presentation.raw_output.strip():
                lines.append("")
                lines.append(presentation.raw_output.strip())
            self.statusLabel.setStyleSheet(_TOOL_FAILURE_STYLE)
            self.statusLabel.setText("\n".join(lines))
        elif presentation.valid:
            lines = ["Last validation: Valid"]
            if presentation.api_version is not None:
                lines.append(f"API: {presentation.api_version}")
            if presentation.dry_run_action:
                lines.append(f"Dry-run action: {presentation.dry_run_action}")
            self.statusLabel.setStyleSheet(_NEUTRAL_STYLE)
            self.statusLabel.setText("\n".join(lines))
        else:
            lines = ["Last validation: Invalid"]
            if presentation.stage:
                lines.append(f"Stage: {presentation.stage}")
            if presentation.code:
                lines.append(f"Code: {presentation.code}")
            if presentation.error:
                lines.append(f"Error: {presentation.error}")
            if presentation.detail:
                lines.append(f"Detail: {presentation.detail}")
            self.statusLabel.setStyleSheet(_INVALID_STYLE)
            self.statusLabel.setText("\n".join(lines))

    def show_tool_failure(self, agent_id: str, message: str) -> None:
        self.show_validation_result(
            ValidationPresentation(agent_id=agent_id, valid=False, error=message, is_tool_failure=True)
        )

    def show_stopped(self, agent_id: str) -> None:
        self._last_validation = None
        self.statusLabel.setStyleSheet(_NEUTRAL_STYLE)
        self.statusLabel.setText(f"Last validation: Stopped by user ({agent_id}).")

    def showTesting(self, agent_id: str, opponent_label: str) -> None:
        self.testStatusLabel.setStyleSheet(_NEUTRAL_STYLE)
        self.testStatusLabel.setText(f"Testing {agent_id} vs {opponent_label}…")
        self.btnOpenTestReplay.setEnabled(False)
        self.btnInspectTrace.setEnabled(False)

    def show_test_result(self, presentation: DevelopmentTestPresentation) -> None:
        self._last_test = presentation
        if presentation.outcome == "tool_error":
            self._last_test_replay = None
            self._last_test_trace = None
            lines = ["Last development test: Could not be completed"]
            if presentation.error:
                lines.append(presentation.error)
            if presentation.raw_output.strip():
                lines.append("")
                lines.append(presentation.raw_output.strip())
            self.testStatusLabel.setStyleSheet(_TOOL_FAILURE_STYLE)
            self.testStatusLabel.setText("\n".join(lines))
        elif presentation.outcome == "initialization_failed":
            self._last_test_replay = None
            self._last_test_trace = (
                presentation.trace_path
                if presentation.trace_path is not None and presentation.trace_path.is_file()
                else None
            )
            lines = ["Last development test: Initialization failed", f"Agent: {presentation.agent_id}"]
            if presentation.opponent:
                lines.append(f"Opponent: {presentation.opponent}")
            if presentation.stage:
                lines.append(f"Stage: {presentation.stage}")
            if presentation.code:
                lines.append(f"Code: {presentation.code}")
            if presentation.error:
                lines.append(f"Error: {presentation.error}")
            if presentation.detail:
                lines.append(f"Detail: {presentation.detail}")
            lines.append("No replay was created because the match did not start.")
            self.testStatusLabel.setStyleSheet(_NEUTRAL_STYLE)
            self.testStatusLabel.setText("\n".join(lines))
        else:  # "completed"
            match = presentation.match
            replay_path = match.replay_path if match else None
            self._last_test_replay = (
                replay_path if replay_path is not None and Path(replay_path).is_file() else None
            )
            self._last_test_trace = (
                presentation.trace_path
                if presentation.trace_path is not None and presentation.trace_path.is_file()
                else None
            )
            lines = ["Last development test: Complete", f"Agent: {presentation.agent_id}"]
            if presentation.opponent:
                lines.append(f"Opponent: {presentation.opponent}")
            if presentation.seed is not None:
                lines.append(f"Seed: {presentation.seed}")
            if presentation.ticks_run is not None and presentation.ticks_requested is not None:
                lines.append(f"Ticks: {presentation.ticks_run}/{presentation.ticks_requested}")
            if match is not None:
                lines.append(f"Winner: {match.winner}")
                lines.append(f"Termination: {match.termination_reason}")
            for forfeit in presentation.forfeits:
                lines.append(f"Forfeit: {forfeit.agent}")
                lines.append(f"Stage: {forfeit.stage}")
                lines.append(f"Code: {forfeit.code}")
            self.testStatusLabel.setStyleSheet(_NEUTRAL_STYLE)
            self.testStatusLabel.setText("\n".join(lines))
        self.btnOpenTestReplay.setEnabled(self._last_test_replay is not None)
        self.btnInspectTrace.setEnabled(self._last_test_trace is not None)

    def show_test_tool_failure(self, agent_id: str, message: str) -> None:
        self.show_test_result(
            DevelopmentTestPresentation(
                agent_id=agent_id, outcome="tool_error", error=message, is_tool_failure=True
            )
        )

    def show_test_stopped(self, agent_id: str) -> None:
        self._last_test = None
        self._last_test_replay = None
        self._last_test_trace = None
        self.testStatusLabel.setStyleSheet(_NEUTRAL_STYLE)
        self.testStatusLabel.setText(f"Last development test: Stopped by user ({agent_id}).")
        self.btnOpenTestReplay.setEnabled(False)
        self.btnInspectTrace.setEnabled(False)

    # ---- Internal ----
    def _update_enablement(self) -> None:
        row = self.selectedAgentRow()
        name = self.agentCombo.currentText()
        has_agent = bool(name) and row is not None
        can_open_folder = has_agent and Path(row.path).is_dir() if row else False
        self.btnOpenFolder.setEnabled(can_open_folder and not self._busy)
        self.btnTest.setEnabled(has_agent and not self._busy)
        self.btnValidate.setEnabled(has_agent and not self._busy)
        self.btnEvaluate.setEnabled(has_agent and not self._busy)

    def _render_idle_status(self) -> None:
        if self._current_agent_name:
            self.statusLabel.setStyleSheet(_NEUTRAL_STYLE)
            self.statusLabel.setText(f"Agent '{self._current_agent_name}' selected. No validation run yet.")
        else:
            self.statusLabel.setStyleSheet(_NEUTRAL_STYLE)
            self.statusLabel.setText("No agent selected.")

    def _render_idle_test_status(self) -> None:
        if self._current_agent_name:
            self.testStatusLabel.setStyleSheet(_NEUTRAL_STYLE)
            self.testStatusLabel.setText(
                f"Agent '{self._current_agent_name}' selected. No development test run yet."
            )
        else:
            self.testStatusLabel.setStyleSheet(_NEUTRAL_STYLE)
            self.testStatusLabel.setText("No agent selected.")

    def _on_combo_changed(self, name: str) -> None:
        self._update_enablement()
        changed = name != self._current_agent_name
        self._current_agent_name = name or None
        if changed:
            self._last_validation = None
            self._render_idle_status()
            self._last_test = None
            self._last_test_replay = None
            self._last_test_trace = None
            self.btnOpenTestReplay.setEnabled(False)
            self.btnInspectTrace.setEnabled(False)
            self._render_idle_test_status()
