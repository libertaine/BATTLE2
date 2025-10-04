from __future__ import annotations
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QStackedWidget,
    QToolBar,
    QMessageBox,
    QFileDialog,
    QLabel,
)

from app.services.osutil import get_battle_root
from app.services.engine import EngineRunner, RunConfig
from app.services.agents import AgentCatalog
from app.views.simple import SimplePanel
from app.views.advanced import AdvancedPanel


class MainWindow(QMainWindow):
    """Main window for Battle Agent Designer.

    Provides a mode toggle between Simple and Advanced panels and hosts a single EngineRunner.
    """

    MODE_SIMPLE = 0
    MODE_ADVANCED = 1

    engine_started = Signal()
    engine_finished = Signal(int)

    def __init__(self, battle_root: Optional[Path] = None) -> None:
        super().__init__()
        self.setWindowTitle("Battle Agent Designer")
        self.resize(1100, 720)

        self._battle_root = battle_root or get_battle_root()
        if not self._battle_root:
            QMessageBox.critical(self, "Error", "Unable to resolve <BATTLE_ROOT>.")
            sys.exit(2)

        # Services
        self.catalog = AgentCatalog(self._battle_root)
        self.engine = EngineRunner(self._battle_root)
        self.engine.output_line.connect(self._on_engine_output)
        self.engine.finished.connect(self._on_engine_finished)
        self.engine.error.connect(self._on_engine_error)

        # Center stack
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        # Panels
        self.simple_panel = SimplePanel(self.catalog)
        self.advanced_panel = AdvancedPanel(self.catalog, self._battle_root)
        self.stack.addWidget(self.simple_panel)
        self.stack.addWidget(self.advanced_panel)

        # Wiring Simple
        self.simple_panel.runRequested.connect(self._on_run_requested)
        self.simple_panel.stopRequested.connect(self._on_stop_requested)
        self.simple_panel.openReplayRequested.connect(self._on_open_replay)
        self.simple_panel.refreshAgentsRequested.connect(self._refresh_agents)

        # Wiring Advanced
        self.advanced_panel.runRequested.connect(self._on_run_requested)
        self.advanced_panel.stopRequested.connect(self._on_stop_requested)
        self.advanced_panel.openReplayRequested.connect(self._on_open_replay)
        self.advanced_panel.refreshAgentsRequested.connect(self._refresh_agents)

        # Toolbar / Mode toggle
        self._setup_toolbar()
        self._status_label = QLabel("Mode: Simple")
        self.statusBar().addPermanentWidget(self._status_label)

        # Initial data
        self._refresh_agents()

    def _setup_toolbar(self) -> None:
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, tb)

        self.actionSimple = QAction(QIcon(), "Simple", self)
        self.actionSimple.setCheckable(True)
        self.actionSimple.setChecked(True)
        self.actionSimple.triggered.connect(lambda: self._set_mode(self.MODE_SIMPLE))

        self.actionAdvanced = QAction(QIcon(), "Advanced", self)
        self.actionAdvanced.setCheckable(True)
        self.actionAdvanced.setChecked(False)
        self.actionAdvanced.triggered.connect(
            lambda: self._set_mode(self.MODE_ADVANCED)
        )

        self.modeGroup = [self.actionSimple, self.actionAdvanced]

        def _exclusive(action: QAction):
            for a in self.modeGroup:
                a.setChecked(a is action)

        self.actionSimple.triggered.connect(lambda _: _exclusive(self.actionSimple))
        self.actionAdvanced.triggered.connect(lambda _: _exclusive(self.actionAdvanced))

        tb.addAction(self.actionSimple)
        tb.addAction(self.actionAdvanced)

        # File menu for opening arbitrary replay
        openReplay = QAction("Open Replay…", self)
        openReplay.triggered.connect(self._choose_and_open_replay)
        tb.addSeparator()
        tb.addAction(openReplay)

    # ---- Mode ----
    def _set_mode(self, mode: int) -> None:
        self.stack.setCurrentIndex(mode)
        text = "Simple" if mode == self.MODE_SIMPLE else "Advanced"
        self._status_label.setText(f"Mode: {text}")

    # ---- Engine flow ----
    @Slot(RunConfig)
    def _on_run_requested(self, cfg: RunConfig) -> None:
        if self.engine.is_running:
            QMessageBox.information(self, "Busy", "Engine already running.")
            return
        self.simple_panel.setBusy(True)
        self.advanced_panel.setBusy(True)
        self.engine.run(cfg)

    @Slot()
    def _on_stop_requested(self) -> None:
        self.engine.stop()

    @Slot(str)
    def _on_engine_output(self, line: str) -> None:
        # Append to logs on both panels (simple has visible log; advanced can mirror silently)
        self.simple_panel.appendLog(line)
        self.advanced_panel.appendLog(line)

    @Slot(int)
    def _on_engine_finished(self, code: int) -> None:
        self.simple_panel.setBusy(False)
        self.advanced_panel.setBusy(False)
        self.advanced_panel.load_results()  # refresh Results tab from summary.json
        # Enable "Open Last Replay" on both panels
        self.simple_panel.enableOpenReplay(True)
        self.advanced_panel.enableOpenReplay(True)

    @Slot(str)
    def _on_engine_error(self, message: str) -> None:
        QMessageBox.critical(self, "Engine Error", message)

    # ---- Replay open ----
    def _choose_and_open_replay(self) -> None:
        start_dir = str(self._battle_root / "runs" / "_loose")
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Replay", start_dir, "Replay JSONL (*.jsonl)"
        )
        if path:
            self._open_replay(Path(path))

    @Slot()
    def _on_open_replay(self) -> None:
        from app.services.osutil import get_default_paths

        paths = get_default_paths(self._battle_root)
        self._open_replay(paths.replay_path)

    def _open_replay(self, replay_path: Path) -> None:
        try:
            self.engine.open_pygame_client(replay_path)
        except FileNotFoundError as e:
            QMessageBox.warning(self, "Missing", str(e))
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Launch Error", str(e))

    # ---- Agents ----
    def _refresh_agents(self) -> None:
        self.catalog.refresh()
        agents = self.catalog.list_names()
        self.simple_panel.setAgents(agents)
        self.advanced_panel.setAgents(agents)


def main() -> int:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()



if __name__ == "__main__":
    raise SystemExit(main())
