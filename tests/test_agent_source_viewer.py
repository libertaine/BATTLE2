"""Read-only Agent Development source-viewer regressions."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.services.agent_catalog import AgentRow
from app.services.agent_source import load_agent_source


def _row(directory: Path, *, agent_id: str, display: str = "Friendly") -> AgentRow:
    return AgentRow(
        name=display,
        path=str(directory),
        blob_path=None,
        meta={"kind": "python"},
        agent_id=agent_id,
    )


def _write_agent(directory: Path, python_text: str, yaml_text: str) -> AgentRow:
    directory.mkdir(parents=True)
    (directory / "agent.py").write_text(python_text, encoding="utf-8")
    (directory / "agent.yaml").write_text(yaml_text, encoding="utf-8")
    return _row(directory, agent_id=directory.name)


def _make_app():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_loader_preserves_utf8_file_contents_exactly(tmp_path):
    python_text = "# café λ\nclass Agent:\n    pass\n"
    yaml_text = "display: 漢字\nkind: python\n"
    row = _write_agent(tmp_path / "unicode_agent", python_text, yaml_text)

    source = load_agent_source(row)

    assert source.python_text == python_text
    assert source.manifest_text == yaml_text


def test_loader_reports_missing_files_and_malformed_directory(tmp_path):
    directory = tmp_path / "partial"
    directory.mkdir()
    (directory / "agent.py").write_text("present\n", encoding="utf-8")

    partial = load_agent_source(_row(directory, agent_id="partial"))
    malformed = load_agent_source(_row(tmp_path / "absent", agent_id="absent"))

    assert partial.python_text == "present\n"
    assert partial.manifest_text == "agent.yaml is not available for this agent."
    assert malformed.python_text.startswith("Unable to read agent.py:")
    assert malformed.manifest_text.startswith("Unable to read agent.yaml:")


def test_loader_reports_read_error_without_raising(monkeypatch, tmp_path):
    row = _write_agent(tmp_path / "unreadable", "hidden\n", "kind: python\n")
    original_read_text = Path.read_text

    def _read_text(path: Path, *args, **kwargs):
        if path.name == "agent.py":
            raise PermissionError("permission denied")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _read_text)

    source = load_agent_source(row)

    assert source.python_text == "Unable to read agent.py: permission denied"
    assert source.manifest_text == "kind: python\n"


def test_loader_rejects_source_symlink_that_escapes_agent_directory(tmp_path):
    outside = tmp_path / "outside.py"
    outside.write_text("do_not_show = True\n", encoding="utf-8")
    directory = tmp_path / "agent"
    directory.mkdir()
    try:
        (directory / "agent.py").symlink_to(outside)
    except OSError:
        pytest.skip("Symlink creation is not permitted in this environment.")

    source = load_agent_source(_row(directory, agent_id="agent"))

    assert "leaves the agent directory" in source.python_text
    assert "do_not_show" not in source.python_text


def test_loader_rejects_row_outside_authoritative_catalog_root(tmp_path):
    catalog_root = tmp_path / "agents"
    catalog_root.mkdir()
    outside = _write_agent(tmp_path / "outside", "SECRET\n", "kind: python\n")

    source = load_agent_source(outside, agents_root=catalog_root)

    assert "leaves the agent catalog" in source.python_text
    assert "SECRET" not in source.python_text


@pytest.mark.gui
def test_panel_switches_canonical_rows_and_viewers_are_read_only(tmp_path):
    _make_app()
    from app.views.development import AgentDevelopmentPanel

    first = _write_agent(tmp_path / "first_id", "FIRST_SOURCE\n", "name: first\n")
    second = _write_agent(tmp_path / "second_id", "SECOND_SOURCE\n", "name: second\n")
    # Duplicate display names ensure selection cannot use display text as identity.
    panel = AgentDevelopmentPanel()
    panel.setAgents([first, second])

    panel.selectAgent("second_id")
    assert panel.pythonSource.toPlainText() == "SECOND_SOURCE\n"
    assert panel.manifestSource.toPlainText() == "name: second\n"
    assert panel.pythonSource.isReadOnly()
    assert panel.manifestSource.isReadOnly()

    panel.selectAgent("first_id")
    assert panel.pythonSource.toPlainText() == "FIRST_SOURCE\n"
    assert panel.manifestSource.toPlainText() == "name: first\n"


@pytest.mark.gui
def test_panel_refresh_reloads_external_changes_and_clears_without_agents(tmp_path):
    _make_app()
    from app.views.development import AgentDevelopmentPanel

    row = _write_agent(tmp_path / "refreshable", "before\n", "kind: python\n")
    panel = AgentDevelopmentPanel()
    panel.setAgents([row])
    assert panel.pythonSource.toPlainText() == "before\n"

    (Path(row.path) / "agent.py").write_text("after\n", encoding="utf-8")
    panel.setAgents([row])
    assert panel.pythonSource.toPlainText() == "after\n"

    panel.setAgents([])
    assert panel.pythonSource.toPlainText() == "No Python agent selected."
    assert panel.manifestSource.toPlainText() == "No Python agent selected."
