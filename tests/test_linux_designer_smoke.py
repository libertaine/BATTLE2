from __future__ import annotations

import pytest


@pytest.mark.gui
def test_agent_designer_window_starts_and_closes(monkeypatch, tmp_path):
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from app.agent_designer import AgentDesigner

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path / "data"))
    application = QApplication.instance() or QApplication([])
    window = AgentDesigner()
    window.show()
    assert window.isVisible()
    QTimer.singleShot(50, window.close)
    QTimer.singleShot(60, application.quit)
    assert application.exec() == 0
    assert not window.isVisible()
