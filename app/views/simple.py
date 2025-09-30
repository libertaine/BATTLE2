from __future__ import annotations
from dataclasses import dataclass
from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QPushButton,
    QLabel,
    QPlainTextEdit,
    QGroupBox,
)

from app.services.engine import RunConfig


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

        root = QVBoxLayout(self)

        # Top controls
        controls = QGroupBox("Quick Match")
        grid = QHBoxLayout(controls)

        grid.addWidget(QLabel("Agent A"))
        self.agentA = QComboBox()
        grid.addWidget(self.agentA)

        grid.addWidget(QLabel("Agent B"))
        self.agentB = QComboBox()
        grid.addWidget(self.agentB)

        grid.addWidget(QLabel("Grid"))
        self.gridSize = QComboBox()
        for k in GRID_PRESETS:
            self.gridSize.addItem(k)
        self.gridSize.setCurrentIndex(1)  # Medium
        grid.addWidget(self.gridSize)

        grid.addWidget(QLabel("Ticks"))
        self.ticks = QComboBox()
        for t in TICK_PRESETS:
            self.ticks.addItem(str(t), userData=t)
        self.ticks.setCurrentIndex(1)
        grid.addWidget(self.ticks)

        self.btnRun = QPushButton("Run Match")
        self.btnStop = QPushButton("Stop")
        self.btnOpen = QPushButton("Open Last Replay")
        self.btnOpen.setEnabled(False)
        self.btnRefresh = QPushButton("Refresh Agents")

        grid.addWidget(self.btnRun)
        grid.addWidget(self.btnStop)
        grid.addWidget(self.btnOpen)
        grid.addWidget(self.btnRefresh)

        root.addWidget(controls)

        # Log area
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(10000)
        root.addWidget(self.log, 1)

        # Signals
        self.btnRun.clicked.connect(self._emit_run)
        self.btnStop.clicked.connect(self.stopRequested.emit)
        self.btnOpen.clicked.connect(self.openReplayRequested.emit)
        self.btnRefresh.clicked.connect(self.refreshAgentsRequested.emit)

    # API consumed by MainWindow
    def setAgents(self, names: List[str]) -> None:
        for cb in (self.agentA, self.agentB):
            prev = cb.currentText()
            cb.blockSignals(True)
            cb.clear()
            cb.addItems(names)
            if prev:
                idx = cb.findText(prev)
                if idx >= 0:
                    cb.setCurrentIndex(idx)
            cb.blockSignals(False)

    def setBusy(self, busy: bool) -> None:
        for w in (
            self.btnRun,
            self.btnRefresh,
            self.agentA,
            self.agentB,
            self.gridSize,
            self.ticks,
        ):
            w.setEnabled(not busy)
        self.btnStop.setEnabled(busy)

    def enableOpenReplay(self, enable: bool) -> None:
        self.btnOpen.setEnabled(enable)

    def appendLog(self, line: str) -> None:
        self.log.appendPlainText(line.rstrip("\n"))

    # Helpers
    def _emit_run(self) -> None:
        arena = GRID_PRESETS[self.gridSize.currentText()]
        ticks = int(self.ticks.currentText())
        cfg = RunConfig(
            a_type=self.agentA.currentText() or "runner",
            b_type=self.agentB.currentText() or "writer",
            arena=arena,
            ticks=ticks,
        )
        self.runRequested.emit(cfg)
