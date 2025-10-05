# app/agent_designer.py
from __future__ import annotations
import os
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QMessageBox

from app.views.simple import SimplePanel
from app.views.advanced import AdvancedPanel

def _resolve_battle_root() -> Path:
    # 1) allow override via env
    env = os.getenv("BATTLE2_ROOT")
    if env:
        return Path(env).resolve()
    # 2) default to project root (parent of app/)
    return Path(__file__).resolve().parent.parent

class AgentDesigner(QMainWindow):
    """Main window combining Simple and Advanced tabs."""
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("BATTLE2 – Agent Designer")

        tabs = QTabWidget()
        # Simple tab (no battle_root required)
        try:
            tabs.addTab(SimplePanel(catalog=None), "Simple")
        except Exception as e:
            QMessageBox.critical(self, "Simple Panel Error", str(e))

        # Advanced tab (requires battle_root)
        battle_root = _resolve_battle_root()
        try:
            tabs.addTab(AdvancedPanel(catalog=None, battle_root=battle_root), "Advanced")
        except Exception as e:
            # Don’t crash the whole app; show Simple tab and inform the user
            QMessageBox.warning(self, "Advanced Panel Unavailable",
                                f"Failed to initialize Advanced panel with battle_root={battle_root}\n\n{e}")

        self.setCentralWidget(tabs)
        self.resize(1000, 720)

def main() -> int:
    app = QApplication(sys.argv)
    win = AgentDesigner()
    win.show()
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
