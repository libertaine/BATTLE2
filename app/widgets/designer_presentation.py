"""Small, native-Qt presentation widgets for Agent Designer."""

from __future__ import annotations

from battle_engine.paths import get_branding_icon_path
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


def _apply_optional_branding_icon(label: QLabel, size: int) -> bool:
    """Load the shared square icon, degrading silently to text-only UI."""

    icon_path = get_branding_icon_path()
    if icon_path is None:
        label.hide()
        return False

    pixmap = QPixmap(str(icon_path))
    if pixmap.isNull():
        label.hide()
        return False

    label.setPixmap(
        pixmap.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    )
    label.setFixedSize(size, size)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    # The adjacent text supplies identity; the image itself is decorative.
    label.setAccessibleName("")
    return True


class DesignerIdentityHeader(QFrame):
    """Compact application identity shown above the Designer's existing tabs."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("designerIdentityHeader")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(12)

        self.iconLabel = QLabel(self)
        self.iconLabel.setObjectName("designerIdentityIcon")
        _apply_optional_branding_icon(self.iconLabel, 36)
        layout.addWidget(self.iconLabel, 0, Qt.AlignmentFlag.AlignVCenter)

        copy = QVBoxLayout()
        copy.setSpacing(1)
        self.titleLabel = QLabel("Bytefray Agent Designer", self)
        self.titleLabel.setObjectName("designerIdentityTitle")
        title_font = self.titleLabel.font()
        title_font.setBold(True)
        title_font.setPointSizeF(title_font.pointSizeF() + 2.0)
        self.titleLabel.setFont(title_font)
        self.titleLabel.setAccessibleName("Application")

        self.purposeLabel = QLabel(
            "Build, test, and compare programmable agents.", self
        )
        self.purposeLabel.setObjectName("designerIdentityPurpose")
        self.purposeLabel.setAccessibleName("Application purpose")
        copy.addWidget(self.titleLabel)
        copy.addWidget(self.purposeLabel)
        layout.addLayout(copy, 1)


class MatchOutputView(QStackedWidget):
    """Explicit ready/live state for the Simple panel's match output."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("matchOutputStack")

        self.emptyState = QWidget(self)
        self.emptyState.setObjectName("matchOutputEmptyState")
        empty_layout = QVBoxLayout(self.emptyState)
        empty_layout.setContentsMargins(24, 24, 24, 24)
        empty_layout.setSpacing(8)

        self.emptyIcon = QLabel(self.emptyState)
        self.emptyIcon.setObjectName("matchOutputEmptyIcon")
        _apply_optional_branding_icon(self.emptyIcon, 56)

        self.readyLabel = QLabel("Ready to run a match", self.emptyState)
        self.readyLabel.setObjectName("matchOutputReadyHeading")
        ready_font = self.readyLabel.font()
        ready_font.setBold(True)
        ready_font.setPointSizeF(ready_font.pointSizeF() + 2.0)
        self.readyLabel.setFont(ready_font)
        self.readyLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.readyLabel.setAccessibleName("Match output status")

        self.matchupLabel = QLabel(self.emptyState)
        self.matchupLabel.setObjectName("matchOutputMatchup")
        matchup_font = self.matchupLabel.font()
        matchup_font.setBold(True)
        self.matchupLabel.setFont(matchup_font)
        self.matchupLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.matchupLabel.setWordWrap(True)
        self.matchupLabel.setAccessibleName("Selected matchup")

        self.guidanceLabel = QLabel(
            "Choose two compatible agents, then Run Match.", self.emptyState
        )
        self.guidanceLabel.setObjectName("matchOutputGuidance")
        self.guidanceLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.guidanceLabel.setWordWrap(True)
        self.guidanceLabel.setAccessibleName("Next action")

        empty_layout.addStretch(1)
        empty_layout.addWidget(
            self.emptyIcon, 0, Qt.AlignmentFlag.AlignHCenter
        )
        empty_layout.addWidget(self.readyLabel)
        empty_layout.addWidget(self.matchupLabel)
        empty_layout.addWidget(self.guidanceLabel)
        empty_layout.addStretch(1)

        self.log = QPlainTextEdit(self)
        self.log.setObjectName("matchOutputLog")
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(10000)
        self.log.setAccessibleName("Match output log")

        self.addWidget(self.emptyState)
        self.addWidget(self.log)
        self.setCurrentWidget(self.emptyState)

    def set_matchup(self, agent_a: str, agent_b: str) -> None:
        """Update ready-state copy from the combos' disambiguated labels."""

        if agent_a and agent_b and "(none found)" not in (agent_a, agent_b):
            summary = f"{agent_a} vs {agent_b}"
        else:
            summary = "No compatible agents selected"
        self.matchupLabel.setText(summary)

    def append_log(self, line: str) -> None:
        """Append real output and reveal the log on its first meaningful text."""

        text = line.rstrip("\n")
        self.log.appendPlainText(text)
        if text.strip():
            self.setCurrentWidget(self.log)

    def clear_log(self) -> None:
        """Clear genuine output and restore the ready presentation state."""

        self.log.clear()
        self.setCurrentWidget(self.emptyState)

    def is_showing_empty_state(self) -> bool:
        return self.currentWidget() is self.emptyState
