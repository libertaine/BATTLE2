from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.agent_catalog import AgentRow
from app.services.engine import RunConfig
from app.services.ruleset_options import (
    SIMPLE_RULESET_OPTIONS,
    agent_row_supported_by_ruleset,
)
from app.widgets.agent_combo import (
    populate_agent_combo,
    selected_agent_name,
)
from app.widgets.designer_presentation import MatchOutputView
from app.widgets.ruleset_combo import (
    populate_ruleset_combo,
    selected_ruleset_id,
)

GRID_PRESETS = {
    "Small (256)": 256,
    "Medium (512)": 512,
    "Large (1024)": 1024,
}

TICK_PRESETS = [300, 600, 1200]


class SimplePanel(QWidget):
    """Simple mode panel with minimal controls and a live log."""

    runRequested = Signal(RunConfig)
    stopRequested = Signal()
    openReplayRequested = Signal()
    refreshAgentsRequested = Signal()

    def __init__(self, catalog) -> None:  # catalog kept for future use
        super().__init__()
        self._all_rows: list[AgentRow] = []
        self._has_eligible_agents = False

        root = QVBoxLayout(self)

        # Match configuration and actions
        controls = QGroupBox("Quick Match")
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(12, 12, 12, 12)
        controls_layout.setSpacing(10)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)

        ruleset_label = QLabel("Ruleset")
        self.ruleset = QComboBox()
        populate_ruleset_combo(self.ruleset, SIMPLE_RULESET_OPTIONS)
        ruleset_label.setBuddy(self.ruleset)
        grid.addWidget(ruleset_label, 0, 0)
        grid.addWidget(self.ruleset, 1, 0, 1, 4)

        self.rulesetExplanation = QLabel()
        self.rulesetExplanation.setWordWrap(True)
        grid.addWidget(self.rulesetExplanation, 2, 0, 1, 4)

        agent_a_label = QLabel("Agent A")
        self.agentA = QComboBox()
        agent_a_label.setBuddy(self.agentA)
        grid.addWidget(agent_a_label, 3, 0)
        grid.addWidget(self.agentA, 4, 0, 1, 2)

        agent_b_label = QLabel("Agent B")
        self.agentB = QComboBox()
        agent_b_label.setBuddy(self.agentB)
        grid.addWidget(agent_b_label, 3, 2)
        grid.addWidget(self.agentB, 4, 2, 1, 2)

        grid_label = QLabel("Grid")
        self.gridSize = QComboBox()
        for k in GRID_PRESETS:
            self.gridSize.addItem(k)
        self.gridSize.setCurrentIndex(1)  # Medium
        grid_label.setBuddy(self.gridSize)
        grid.addWidget(grid_label, 5, 0)
        grid.addWidget(self.gridSize, 6, 0, 1, 2)

        ticks_label = QLabel("Ticks")
        self.ticks = QComboBox()
        for t in TICK_PRESETS:
            self.ticks.addItem(str(t), userData=t)
        self.ticks.setCurrentIndex(1)
        ticks_label.setBuddy(self.ticks)
        grid.addWidget(ticks_label, 5, 2)
        grid.addWidget(self.ticks, 6, 2, 1, 2)
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 1)
        grid.setColumnStretch(3, 1)
        controls_layout.addLayout(grid)

        self.btnRun = QPushButton("Run Match")
        run_font = self.btnRun.font()
        run_font.setBold(True)
        self.btnRun.setFont(run_font)
        self.btnRun.setMinimumWidth(120)
        self.btnRun.setAccessibleDescription(
            "Run a match using the selected agents, grid, and tick limit."
        )
        self.btnStop = QPushButton("Stop")
        self.btnOpen = QPushButton("Open Last Replay")
        self.btnOpen.setEnabled(False)
        self.btnRefresh = QPushButton("Refresh Agents")

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(self.btnRun)
        actions.addWidget(self.btnStop)
        actions.addWidget(self.btnOpen)
        actions.addStretch(1)
        actions.addWidget(self.btnRefresh)
        controls_layout.addLayout(actions)

        root.addWidget(controls)

        # Output area: a real UI empty state, never placeholder log data.
        output_group = QGroupBox("Match Output")
        output_layout = QVBoxLayout(output_group)
        self.output = MatchOutputView(output_group)
        self.log = self.output.log  # Existing MainWindow/test compatibility surface.
        output_layout.addWidget(self.output)
        root.addWidget(output_group, 1)

        # Signals
        self.btnRun.clicked.connect(self._emit_run)
        self.btnStop.clicked.connect(self.stopRequested.emit)
        self.btnOpen.clicked.connect(self.openReplayRequested.emit)
        self.btnRefresh.clicked.connect(self.refreshAgentsRequested.emit)
        self.agentA.currentIndexChanged.connect(self._on_agent_a_changed)
        self.agentB.currentIndexChanged.connect(self._update_matchup_summary)
        self.ruleset.currentIndexChanged.connect(self._on_ruleset_changed)
        self._update_matchup_summary()

    # API consumed by MainWindow
    def setAgents(self, rows: list[AgentRow]) -> None:
        self._all_rows = list(rows)
        self._refilter_agents()

    def _on_agent_a_changed(self, _index: int) -> None:
        self._update_matchup_summary()

    def _on_ruleset_changed(self, _index: int) -> None:
        self._refilter_agents()

    def _refilter_agents(self) -> None:
        """Populate both selectors from the current Ruleset's eligible rows."""

        ruleset_id = selected_ruleset_id(self.ruleset)
        previous_b = selected_agent_name(self.agentB)
        eligible = [
            row
            for row in self._all_rows
            if agent_row_supported_by_ruleset(row, ruleset_id)
        ]
        eligible_ids = {row.agent_id or row.name for row in eligible}
        populate_agent_combo(self.agentA, eligible)
        populate_agent_combo(self.agentB, eligible)

        # When B could not be preserved, prefer a deterministic opponent
        # distinct from A.  An explicit, still-valid self-match is retained.
        if previous_b not in eligible_ids and len(eligible) > 1:
            selected_a = selected_agent_name(self.agentA)
            for index in range(self.agentB.count()):
                if self.agentB.itemData(index) != selected_a:
                    self.agentB.setCurrentIndex(index)
                    break

        self._has_eligible_agents = bool(eligible)
        self.btnRun.setEnabled(self._has_eligible_agents)
        if eligible:
            self.rulesetExplanation.clear()
        else:
            self.rulesetExplanation.setText(
                "No compatible agents were found for this Ruleset. "
                "Create or import a compatible Python agent, then refresh."
            )
        self._update_matchup_summary()

    def _update_matchup_summary(self, _index: int | None = None) -> None:
        self.output.set_matchup(self.agentA.currentText(), self.agentB.currentText())

    def setBusy(self, busy: bool) -> None:
        for w in (
            self.btnRefresh,
            self.agentA,
            self.agentB,
            self.gridSize,
            self.ticks,
            self.ruleset,
        ):
            w.setEnabled(not busy)
        self.btnRun.setEnabled(not busy and self._has_eligible_agents)
        self.btnStop.setEnabled(busy)

    def enableOpenReplay(self, enable: bool) -> None:
        self.btnOpen.setEnabled(enable)

    def appendLog(self, line: str) -> None:
        self.output.append_log(line)

    def clearLog(self) -> None:
        self.output.clear_log()

    # Helpers
    def _emit_run(self) -> None:
        agent_a = selected_agent_name(self.agentA)
        agent_b = selected_agent_name(self.agentB)
        if agent_a is None or agent_b is None:
            message = "No compatible agents are available for the selected Ruleset."
            self.appendLog(f"[RunMatch] {message}\n")
            self.rulesetExplanation.setText(message)
            return
        arena = GRID_PRESETS[self.gridSize.currentText()]
        ticks = int(self.ticks.currentText())
        cfg = RunConfig(
            a_type=agent_a,
            b_type=agent_b,
            ruleset_id=selected_ruleset_id(self.ruleset),
            arena=arena,
            ticks=ticks,
        )
        self.runRequested.emit(cfg)
