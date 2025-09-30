from __future__ import annotations
from dataclasses import asdict
from json import loads
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTabWidget,
    QFormLayout,
    QSpinBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QGroupBox,
    QPlainTextEdit,
)

from app.services.engine import RunConfig
from app.services.osutil import get_default_paths
from app.widgets.json_editor import JsonEditor


class AdvancedPanel(QWidget):
    """Advanced mode with tabs: Setup, Agent Params, Replay Browser, Results."""

    runRequested = Signal(RunConfig)
    stopRequested = Signal()
    openReplayRequested = Signal()
    refreshAgentsRequested = Signal()

    def __init__(self, catalog, battle_root: Path) -> None:
        super().__init__()
        self._catalog = catalog
        self._paths = get_default_paths(battle_root)

        root = QVBoxLayout(self)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)

        # ---- Match Setup ----
        setup = QWidget()
        form = QFormLayout(setup)

        self.agentA = QComboBox()
        self.agentB = QComboBox()
        form.addRow("Agent A", self.agentA)
        form.addRow("Agent B", self.agentB)

        self.arena = QSpinBox()
        self.arena.setRange(64, 8192)
        self.arena.setValue(512)
        form.addRow("Arena", self.arena)

        self.ticks = QSpinBox()
        self.ticks.setRange(1, 100000)
        self.ticks.setValue(600)
        form.addRow("Ticks", self.ticks)

        self.alive_w = QDoubleSpinBox()
        self.alive_w.setRange(0.0, 1000.0)
        self.alive_w.setDecimals(3)
        self.alive_w.setValue(1.0)
        self.kill_w = QDoubleSpinBox()
        self.kill_w.setRange(0.0, 1000.0)
        self.kill_w.setDecimals(3)
        self.kill_w.setValue(1.0)
        self.territory_w = QDoubleSpinBox()
        self.territory_w.setRange(0.0, 1000.0)
        self.territory_w.setDecimals(3)
        self.territory_w.setValue(1.0)
        form.addRow("alive_w", self.alive_w)
        form.addRow("kill_w", self.kill_w)
        form.addRow("territory_w", self.territory_w)

        self.territory_bucket = QSpinBox()
        self.territory_bucket.setRange(1, 4096)
        self.territory_bucket.setValue(32)
        form.addRow("territory_bucket", self.territory_bucket)

        self.seed = QSpinBox()
        self.seed.setRange(0, 1_000_000)
        self.seed.setValue(0)
        form.addRow("Seed (0=random)", self.seed)

        btns = QHBoxLayout()
        self.btnRun = QPushButton("Run Match")
        self.btnStop = QPushButton("Stop")
        self.btnOpen = QPushButton("Open Last Replay")
        self.btnOpen.setEnabled(False)
        self.btnRefresh = QPushButton("Refresh Agents")
        btns.addWidget(self.btnRun)
        btns.addWidget(self.btnStop)
        btns.addWidget(self.btnOpen)
        btns.addWidget(self.btnRefresh)
        form.addRow(btns)

        self.tabs.addTab(setup, "Match Setup")

        # ---- Agent Params ----
        params = QWidget()
        pv = QVBoxLayout(params)
        self.editorA = JsonEditor(title="Agent A Params (JSON)")
        self.editorB = JsonEditor(title="Agent B Params (JSON)")
        pv.addWidget(self.editorA)
        pv.addWidget(self.editorB)
        self.tabs.addTab(params, "Agent Params")

        # ---- Replay Browser ----
        replay = QWidget()
        rl = QVBoxLayout(replay)
        row = QHBoxLayout()
        self.lblReplay = QLabel(str(self._paths.replay_path))
        self.btnChooseReplay = QPushButton("Choose .jsonl…")
        self.btnOpenReplay = QPushButton("Open in Pygame")
        row.addWidget(self.lblReplay, 1)
        row.addWidget(self.btnChooseReplay)
        row.addWidget(self.btnOpenReplay)
        rl.addLayout(row)
        self.tabs.addTab(replay, "Replay Browser")

        # ---- Results ----
        results = QWidget()
        rv = QVBoxLayout(results)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Field", "Value"])
        self.table.horizontalHeader().setStretchLastSection(True)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(10000)
        group = QGroupBox("Engine Log")
        gl = QVBoxLayout(group)
        gl.addWidget(self.log)

        rv.addWidget(self.table, 1)
        rv.addWidget(group)
        self.tabs.addTab(results, "Results")

        # Signals
        self.btnRun.clicked.connect(self._emit_run)
        self.btnStop.clicked.connect(self.stopRequested.emit)
        self.btnOpen.clicked.connect(self.openReplayRequested.emit)
        self.btnRefresh.clicked.connect(self.refreshAgentsRequested.emit)
        self.btnChooseReplay.clicked.connect(self._choose_replay)
        self.btnOpenReplay.clicked.connect(self._open_replay_browser)

    # API for MainWindow
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
            self.arena,
            self.ticks,
            self.alive_w,
            self.kill_w,
            self.territory_w,
            self.territory_bucket,
            self.seed,
        ):
            w.setEnabled(not busy)
        self.btnStop.setEnabled(busy)

    def enableOpenReplay(self, enable: bool) -> None:
        self.btnOpen.setEnabled(enable)

    def appendLog(self, line: str) -> None:
        self.log.appendPlainText(line.rstrip("\n"))

    def load_results(self) -> None:
        from app.services.osutil import read_summary_json

        data = read_summary_json(self._paths.summary_path)
        if data is None:
            return
        # Populate table
        self.table.setRowCount(0)
        for k in [
            "winner",
            "ticks",
            "A_score",
            "B_score",
            "A_territory",
            "B_territory",
            "seed",
        ]:
            if k in data:
                r = self.table.rowCount()
                self.table.insertRow(r)
                self.table.setItem(r, 0, QTableWidgetItem(k))
                self.table.setItem(r, 1, QTableWidgetItem(str(data[k])))

    # Helpers
    def _emit_run(self) -> None:
        cfg = RunConfig(
            a_type=self.agentA.currentText() or "runner",
            b_type=self.agentB.currentText() or "writer",
            arena=int(self.arena.value()),
            ticks=int(self.ticks.value()),
            alive_w=float(self.alive_w.value()),
            kill_w=float(self.kill_w.value()),
            territory_w=float(self.territory_w.value()),
            territory_bucket=int(self.territory_bucket.value()),
            seed=int(self.seed.value()) or None,
            a_params=self.editorA.get_data_or_none(),
            b_params=self.editorB.get_data_or_none(),
        )
        self.runRequested.emit(cfg)

    def _choose_replay(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Replay",
            str(self._paths.replay_path.parent),
            "Replay JSONL (*.jsonl)",
        )
        if path:
            self.lblReplay.setText(path)

    def _open_replay_browser(self) -> None:
        from app.services.engine import open_pygame_client_direct

        p = Path(self.lblReplay.text())
        open_pygame_client_direct(self._paths.root, p)
