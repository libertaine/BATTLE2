from __future__ import annotations
import json
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QMessageBox,
)


class JsonEditor(QWidget):
    """Minimal JSON editor with a Validate button.

    Emits no signals; consumer pulls via get_data_or_none().
    """

    def __init__(self, title: str = "JSON") -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.addWidget(QLabel(title))
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText('{\n  "speed": 1.0,\n  "aggression": 0.2\n}')
        root.addWidget(self.text)
        self.btn = QPushButton("Validate JSON")
        self.btn.clicked.connect(self._validate)
        root.addWidget(self.btn)

    def _validate(self) -> None:
        txt = self.text.toPlainText().strip()
        if not txt:
            QMessageBox.information(self, "Validation", "Empty (treated as none).")
            return
        try:
            json.loads(txt)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Invalid JSON", f"Error: {e}")
            return
        QMessageBox.information(self, "Validation", "Looks good.")

    def get_data_or_none(self) -> Optional[dict]:
        txt = self.text.toPlainText().strip()
        if not txt:
            return None
        try:
            return json.loads(txt)
        except Exception:
            # Caller can still run; they should validate first in UI
            QMessageBox.critical(
                self, "Invalid JSON", "Please fix JSON or clear the field."
            )
            return None
