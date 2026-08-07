"""Small tournament-launch dialog for the existing Designer."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QAbstractItemView,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)


class TournamentDialog(QDialog):
    def __init__(self, rows, default_output: Path, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Run Tournament")
        self._rows = tuple(rows)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select at least two agents from one runtime kind."))
        self.agents = QListWidget()
        self.agents.setSelectionMode(QAbstractItemView.ExtendedSelection)
        for index, row in enumerate(self._rows):
            item = QListWidgetItem(f"{row.name} ({row.meta.get('kind', 'vm')})")
            item.setData(Qt.UserRole, index)
            self.agents.addItem(item)
        layout.addWidget(self.agents)

        form = QFormLayout()
        self.rounds = QSpinBox()
        self.rounds.setRange(1, 1000)
        self.rounds.setValue(1)
        self.seed = QSpinBox()
        self.seed.setRange(0, 2_147_483_647)
        self.seed.setValue(1337)
        output_row = QHBoxLayout()
        self.output = QLineEdit(str(default_output))
        choose = QPushButton("Choose…")
        choose.clicked.connect(self._choose_output)
        output_row.addWidget(self.output, 1)
        output_row.addWidget(choose)
        form.addRow("Rounds", self.rounds)
        form.addRow("Seed", self.seed)
        form.addRow("Output", output_row)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Run")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(560, 430)

    def selected_rows(self):
        return tuple(self._rows[item.data(Qt.UserRole)] for item in self.agents.selectedItems())

    def output_path(self) -> Path:
        return Path(self.output.text())

    def _choose_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Tournament Output", self.output.text())
        if path:
            self.output.setText(path)
