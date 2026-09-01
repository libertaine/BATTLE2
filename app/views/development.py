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

from collections import Counter
from pathlib import Path

from battle_engine.agent_scaffold import (
    AGENT_ID_PATTERN,
    DEFAULT_TEMPLATE,
    MAX_AGENT_ID_LENGTH,
    TEMPLATE_DIRECTORIES,
    AgentScaffoldError,
    ScaffoldResult,
    create_agent,
)
from battle_engine.agent_test import DEFAULT_AGENT_TIMEOUT, DEFAULT_TICKS
from battle_engine.config import Config
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.services.agent_catalog import AgentRow
from app.services.agent_source import load_agent_source
from app.services.agent_workflows import DevelopmentTestPresentation, ValidationPresentation
from app.services.ruleset_options import RULESET_DESCRIPTION, agent_row_metadata
from app.widgets.ruleset_combo import (
    populate_ruleset_combo,
    selected_ruleset_id,
    sync_ruleset_choices_for_metadata,
)

_INVALID_STYLE = "color: #b00020;"
_TOOL_FAILURE_STYLE = "color: #b06000;"
_NEUTRAL_STYLE = ""

_DEFAULT_TEST_SEED = Config().seed
_DEFAULT_TEST_TICKS = DEFAULT_TICKS
_MAX_SPINBOX_INT = 2_147_483_647

# Display labels for battle_engine.agent_scaffold.TEMPLATE_DIRECTORIES'
# keys, in the order offered -- "Blank" first and pre-selected, so the
# default GUI choice is byte-identical to omitting --template on the CLI.
_TEMPLATE_LABELS = {
    "blank": "Blank",
    "annotated": "Annotated Example (commented)",
}


def _is_python_agent(row: AgentRow) -> bool:
    meta = row.meta if isinstance(row.meta, dict) else {}
    return meta.get("kind") == "python"


def _agent_row_id(row: AgentRow) -> str:
    """Return the catalog/discovery id, retaining legacy-row compatibility."""

    return row.agent_id or row.name


def _agent_labels(rows: list[AgentRow]) -> list[str]:
    """Make duplicate display names unambiguous without decorating unique ones."""

    counts = Counter(row.name for row in rows)
    return [
        f"{row.name} ({_agent_row_id(row)})" if counts[row.name] > 1 else row.name
        for row in rows
    ]


class NewAgentDialog(QDialog):
    """Minimal 'New Agent' dialog: a single agent-id field.

    Calls ``create_agent`` directly and synchronously on OK (Sec 5/Sec 8 of
    the Phase 4 spec -- scaffolding executes no agent-author code, so no
    process boundary or progress indicator is needed). On an expected
    ``AgentScaffoldError``/``OSError`` (invalid id, duplicate, unwritable
    root), the error is shown inline and the dialog stays open so the user
    can correct the id and retry.
    """

    def __init__(self, data_root: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Agent")
        self._data_root = data_root
        self.result: ScaffoldResult | None = None

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

        layout.addWidget(QLabel("Starting point"))
        self.templateCombo = QComboBox()
        for key in TEMPLATE_DIRECTORIES:
            self.templateCombo.addItem(_TEMPLATE_LABELS.get(key, key), key)
        self.templateCombo.setCurrentIndex(self.templateCombo.findData(DEFAULT_TEMPLATE))
        layout.addWidget(self.templateCombo)

        self.errorLabel = QLabel("")
        self.errorLabel.setStyleSheet(_INVALID_STYLE)
        self.errorLabel.setWordWrap(True)
        self.errorLabel.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.errorLabel.setVisible(False)
        layout.addWidget(self.errorLabel)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(420, 240)

    def selected_template(self) -> str:
        return self.templateCombo.currentData() or DEFAULT_TEMPLATE

    def _on_ok(self) -> None:
        agent_id = self.agentId.text().strip()
        if not agent_id:
            self._show_error("Agent ID is required.")
            return
        try:
            self.result = create_agent(
                agent_id, data_root=self._data_root, template=self.selected_template()
            )
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
    exportAgentRequested = Signal()
    validateRequested = Signal()
    testRequested = Signal()
    openTestReplayRequested = Signal()
    inspectTraceRequested = Signal()
    evaluateRequested = Signal()

    def __init__(self, catalog=None) -> None:  # catalog kept for parity with other panels
        super().__init__()
        self._catalog = catalog
        self._rows: list[AgentRow] = []
        self._busy = False
        # Whether the selected agent/opponent pairing has any compatible
        # Ruleset; recomputed by _sync_ruleset and gating Test.
        self._has_compatible_ruleset = True
        self._current_agent_id: str | None = None
        self._current_agent_name: str | None = None
        self._last_validation: ValidationPresentation | None = None
        self._last_test: DevelopmentTestPresentation | None = None
        self._last_test_replay: Path | None = None
        self._last_test_trace: Path | None = None

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
        self.btnExportAgent = QPushButton("Export Agent…")
        self.btnExportAgent.setEnabled(False)
        self.btnExportAgent.setToolTip(
            "Package this agent's current source into a portable .bytefray-agent "
            "file via the authoritative v1.2 package engine (docs/specs/agent_package.md)."
        )
        header_row.addWidget(self.btnRefresh)
        header_row.addWidget(self.btnNewAgent)
        header_row.addWidget(self.btnOpenFolder)
        header_row.addWidget(self.btnExportAgent)
        root.addWidget(header)

        source = QGroupBox("Source")
        source_layout = QVBoxLayout(source)
        source_hint_row = QHBoxLayout()
        source_hint = QLabel(
            "Source is read-only. Use Open Folder to edit the agent externally, "
            "then Reload to refresh this view."
        )
        source_hint.setWordWrap(True)
        source_hint_row.addWidget(source_hint, 1)
        self.btnReloadSource = QPushButton("Reload")
        self.btnReloadSource.setToolTip(
            "Re-read agent.py/agent.yaml from disk. Validate and Test always run "
            "against the current on-disk source regardless of this view -- Reload "
            "only refreshes what is shown here."
        )
        source_hint_row.addWidget(self.btnReloadSource)
        source_layout.addLayout(source_hint_row)
        self.sourceTabs = QTabWidget()
        fixed_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self.pythonSource = QPlainTextEdit()
        self.manifestSource = QPlainTextEdit()
        for viewer in (self.pythonSource, self.manifestSource):
            viewer.setReadOnly(True)
            viewer.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
            viewer.setFont(fixed_font)
            viewer.setToolTip(
                "Source is read-only. Use Open Folder to edit externally."
            )
        self.sourceTabs.addTab(self.pythonSource, "agent.py")
        self.sourceTabs.addTab(self.manifestSource, "agent.yaml")
        self.sourceTabs.setMinimumHeight(180)
        source_layout.addWidget(self.sourceTabs)
        root.addWidget(source)

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

        # Ruleset is an explicit, visible choice here, never an inherited
        # CLI default. Before v3.0.0-alpha2 this tab passed no --ruleset at
        # all, so every development test silently resolved `bytefray agents
        # test`'s own backward-compatible Ruleset-v1 default while the
        # Simple/Advanced match tabs beside it defaulted to v2. Agent
        # Development is Bytefray v3's primary Python-authoring workflow, so
        # it now defaults to the current gameplay Ruleset and says which one
        # it used. This tab filters to Python agents only (see
        # _is_python_agent), and Python entrants are valid under both
        # identities, so no entrant-kind gating is needed on this selector --
        # unlike Simple/Advanced, whose combos also carry VM agents.
        ruleset_row = QHBoxLayout()
        ruleset_row.addWidget(QLabel("Ruleset"))
        self.rulesetCombo = QComboBox()
        populate_ruleset_combo(self.rulesetCombo)
        self.rulesetCombo.setToolTip(RULESET_DESCRIPTION)
        self.rulesetCombo.setAccessibleName("Development test ruleset")
        ruleset_row.addWidget(self.rulesetCombo, 1)
        test_layout.addLayout(ruleset_row)

        self.btnTest = QPushButton("Test")
        self.btnTest.setEnabled(False)
        test_layout.addWidget(self.btnTest)

        self.testStatusLabel = QLabel("No agent selected.")
        self.testStatusLabel.setWordWrap(True)
        self.testStatusLabel.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
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
        self.statusLabel.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        status_layout.addWidget(self.statusLabel)
        root.addWidget(status, 1)

        self.btnRefresh.clicked.connect(self.refreshAgentsRequested.emit)
        self.btnNewAgent.clicked.connect(self.newAgentRequested.emit)
        self.btnOpenFolder.clicked.connect(self.openFolderRequested.emit)
        self.btnExportAgent.clicked.connect(self.exportAgentRequested.emit)
        self.btnReloadSource.clicked.connect(self.reloadSource)
        # Validate/Test already run against whatever is on disk regardless
        # of this view (see reloadSource's docstring) -- refreshing the
        # read-only preview first just means what a user sees here never
        # lags behind what they just asked the Designer to do, without
        # requiring a combo-box reselect as the only way to force it.
        self.btnValidate.clicked.connect(self.reloadSource)
        self.btnValidate.clicked.connect(self.validateRequested.emit)
        self.btnTest.clicked.connect(self.reloadSource)
        self.btnTest.clicked.connect(self.testRequested.emit)
        self.btnOpenTestReplay.clicked.connect(self.openTestReplayRequested.emit)
        self.btnInspectTrace.clicked.connect(self.inspectTraceRequested.emit)
        self.btnEvaluate.clicked.connect(self.evaluateRequested.emit)
        self.agentCombo.currentIndexChanged.connect(self._on_combo_changed)
        # An explicitly selected opponent is a real entrant, so it
        # participates in Ruleset compatibility exactly like the tested
        # agent does.
        self.opponentCombo.currentIndexChanged.connect(self._on_opponent_changed)

        self.opponentCombo.addItem("Reference", None)
        self._update_enablement()

    # ---- API consumed by AgentDesigner ----
    def setAgents(self, rows: list[AgentRow]) -> None:
        """Repopulate the combo from the full catalog, keeping python agents only."""
        previous_id = self.agentCombo.currentData()
        self._rows = [row for row in rows if _is_python_agent(row)]
        self.agentCombo.blockSignals(True)
        self.agentCombo.clear()
        for label, row in zip(_agent_labels(self._rows), self._rows, strict=True):
            self.agentCombo.addItem(label, _agent_row_id(row))
        if previous_id:
            idx = self.agentCombo.findData(previous_id)
            if idx >= 0:
                self.agentCombo.setCurrentIndex(idx)
        self.agentCombo.blockSignals(False)
        self._refresh_opponent_combo()
        self._on_combo_changed()

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
        for label, row in zip(_agent_labels(self._rows), self._rows, strict=True):
            self.opponentCombo.addItem(label, _agent_row_id(row))
        index = 0
        if prev_data is not None:
            found = self.opponentCombo.findData(prev_data)
            if found >= 0:
                index = found
        self.opponentCombo.setCurrentIndex(index)
        self.opponentCombo.blockSignals(False)

    def selected_opponent_id(self) -> str | None:
        """The ``--opponent`` value to pass, or ``None`` for the internal reference."""
        return self.opponentCombo.currentData()

    def selected_seed(self) -> int:
        return self.seedSpin.value()

    def selected_ticks(self) -> int:
        return self.ticksSpin.value()

    def selected_timeout(self) -> float:
        return self.timeoutSpin.value()

    def selected_ruleset_id(self) -> str:
        """The Ruleset identity to pass explicitly to ``bytefray agents test``.

        Always a concrete identity, never ``None``: this tab must not let the
        CLI's own backward-compatible default decide which Ruleset a
        development test ran under.
        """
        return selected_ruleset_id(self.rulesetCombo)

    def last_test_trace_path(self) -> Path | None:
        """The last completed test's trace path, or ``None`` if unavailable."""
        return self._last_test_trace

    def last_test_replay_path(self) -> Path | None:
        """The last completed test's replay path, or ``None`` if unavailable.

        Independent of ``AgentDesigner._last_replay`` (Sec 13 of the Phase
        4 spec): a development test's replay is never promoted to the
        Designer's Simple/Advanced "Open Last Replay" target, so switching
        tabs never surprises a user with a replay they did not expect.
        """
        return self._last_test_replay

    def selectAgent(self, agent_id: str) -> None:
        idx = self.agentCombo.findData(agent_id)
        if idx < 0:
            # Compatibility for callers/tests that predate AgentRow.agent_id
            # and still pass a unique display label.
            idx = self.agentCombo.findText(agent_id)
        if idx >= 0:
            self.agentCombo.setCurrentIndex(idx)
        self._on_combo_changed()

    def selectedAgentRow(self) -> AgentRow | None:
        index = self.agentCombo.currentIndex()
        return self._rows[index] if 0 <= index < len(self._rows) else None

    def reloadSource(self) -> None:
        """Re-read the selected agent's agent.py/agent.yaml from disk.

        The Designer never caches source for Validate/Test -- both already
        launch a fresh out-of-process run that reads whatever is on disk at
        that moment, regardless of what this method has or hasn't been
        called. This only refreshes the read-only preview panes, which
        otherwise show whatever was on disk the last time the agent was
        (re)selected -- stale after an external edit until now. Safe to
        call with no agent selected (clears both panes); safe to call
        repeatedly.
        """
        row = self.selectedAgentRow()
        agents_root = self._catalog.agents_dir() if self._catalog is not None else None
        source = load_agent_source(row, agents_root=agents_root)
        self.pythonSource.setPlainText(source.python_text)
        self.manifestSource.setPlainText(source.manifest_text)

    def invalidateAgentState(self, agent_id: str, reason: str) -> None:
        """Clear cached evidence when the selected agent's source changes."""

        row = self.selectedAgentRow()
        if row is None or _agent_row_id(row) != agent_id:
            return
        self.reloadSource()
        detail = reason.strip() or "The selected agent's source changed."
        self._last_validation = None
        self._last_test = None
        self._last_test_replay = None
        self._last_test_trace = None
        self.btnOpenTestReplay.setEnabled(False)
        self.btnInspectTrace.setEnabled(False)
        self.statusLabel.setStyleSheet(_NEUTRAL_STYLE)
        self.statusLabel.setText(
            f"Source changed for '{row.name}': {detail} Re-run validation."
        )
        self.testStatusLabel.setStyleSheet(_NEUTRAL_STYLE)
        self.testStatusLabel.setText(
            f"Source changed for '{row.name}': previous development-test results were cleared."
        )

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
        self.btnReloadSource.setEnabled(not busy)
        self.opponentCombo.setEnabled(not busy)
        self.seedSpin.setEnabled(not busy)
        self.ticksSpin.setEnabled(not busy)
        self.timeoutSpin.setEnabled(not busy)
        self.rulesetCombo.setEnabled(not busy)
        self._update_enablement()

    def python_agent_names(self) -> list[tuple[str, str]]:
        """Every discovered Python agent as ``(display name, discovery id)``.

        The Evaluate dialog must display ``row.name`` (display) but always
        hand ``row.agent_id`` (discovery id) back to the CLI --
        ``resolve_agent`` looks agents up by discovery id, not display name,
        and the two can differ (docs/specs/evaluation_history.md Sec 17).
        """
        return [(row.name, _agent_row_id(row)) for row in self._rows]

    def python_agent_metadata(self) -> dict[str, object]:
        """Every discovered Python agent's compatibility metadata by id.

        Lets the Evaluate dialog ask the same Ruleset-compatibility question
        this tab and the engine do, instead of offering Rulesets that the
        selected roster cannot actually run under.
        """
        return {_agent_row_id(row): agent_row_metadata(row) for row in self._rows}

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
        # Name the Ruleset while the test is in flight, so the effective
        # gameplay semantics are visible without waiting for the result.
        self.testStatusLabel.setText(
            f"Testing {agent_id} vs {opponent_label} under {self.selected_ruleset_id()}…"
        )
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
            # The Ruleset the tool itself reported, not the one the combo
            # requested -- so a user can always see which gameplay semantics
            # produced this result.
            lines.append(f"Ruleset: {presentation.ruleset_id or 'not reported'}")
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
    def _opponent_row(self) -> AgentRow | None:
        """The explicitly selected opponent's row, or ``None`` for Reference.

        The internal reference opponent deliberately imposes no Ruleset
        constraint: ``agents test`` supplies whichever Agent API generation
        the resolved Ruleset needs, so it can never be the incompatible
        entrant.
        """

        opponent_id = self.selected_opponent_id()
        if opponent_id is None:
            return None
        return next(
            (row for row in self._rows if _agent_row_id(row) == opponent_id), None
        )

    def _sync_ruleset(self) -> None:
        """Offer only Rulesets compatible with the selected entrants.

        Only the *Ruleset* choices narrow here -- the agent catalog itself
        keeps listing every discovered Python agent, so this tab stays
        usable for historical Agent API v1 agents and current Agent API v2
        ones alike.
        """

        rows = [row for row in (self.selectedAgentRow(), self._opponent_row()) if row is not None]
        self._has_compatible_ruleset = sync_ruleset_choices_for_metadata(
            self.rulesetCombo, [agent_row_metadata(row) for row in rows]
        )

    def _update_enablement(self) -> None:
        row = self.selectedAgentRow()
        has_agent = row is not None
        can_open_folder = has_agent and Path(row.path).is_dir() if row else False
        self.btnOpenFolder.setEnabled(can_open_folder and not self._busy)
        self.btnExportAgent.setEnabled(has_agent and not self._busy)
        # Testing is disabled outright when the selected pairing has no
        # compatible Ruleset, rather than launching a run the engine would
        # reject as a configuration error.
        self.btnTest.setEnabled(
            has_agent and not self._busy and self._has_compatible_ruleset
        )
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

    def _on_opponent_changed(self, _index: int | None = None) -> None:
        self._sync_ruleset()
        self._update_enablement()

    def _on_combo_changed(self, _index: int | None = None) -> None:
        self._sync_ruleset()
        self._update_enablement()
        row = self.selectedAgentRow()
        self.reloadSource()
        agent_id = _agent_row_id(row) if row is not None else None
        changed = agent_id != self._current_agent_id
        self._current_agent_id = agent_id
        self._current_agent_name = row.name if row is not None else None
        if changed:
            self._last_validation = None
            self._render_idle_status()
            self._last_test = None
            self._last_test_replay = None
            self._last_test_trace = None
            self.btnOpenTestReplay.setEnabled(False)
            self.btnInspectTrace.setEnabled(False)
            self._render_idle_test_status()
