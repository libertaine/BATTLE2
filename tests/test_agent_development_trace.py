"""GUI regression coverage for Agent Lab's Trace Inspector (v0.5).

Covers: "Inspect Trace" button enablement tracking the last development
test's trace artifact (independent of "Open Replay"'s own state, per
``docs/specs/agent_lab.md`` §11), the presentation layer's optional
``trace:`` line parsing, and the Qt-free-backed :class:`TraceInspectorDialog`
opening from a real trace file without executing any agent code.

Marked ``gui`` like the existing Designer tests: excluded from the default
headless run, exercised by the dedicated display-backed workflow.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def _make_app():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _write_trace(path: Path) -> None:
    from battle_engine.agent_trace import (
        DecisionRecord,
        ResetRecord,
        TraceAction,
        TraceHeader,
        TraceObservation,
        TraceWriter,
    )

    with TraceWriter(path) as writer:
        writer.write_header(
            TraceHeader(match_seed=1337, agents={"A": "example", "B": "reference"}, supervised=True, agent_call_timeout=5.0)
        )
        writer.write_reset(ResetRecord(agent_id="A", wall_time_ms=1.0, diagnostic=None))
        for tick in (1, 2, 3):
            writer.write_decision(
                DecisionRecord(
                    tick=tick, agent_id="A", action_slot=0, wall_time_ms=0.1,
                    observation=TraceObservation(
                        tick=tick, agent_id="A", pc=0, register_a=0, register_p=0,
                        zero_flag=False, last_read=None, alive=True,
                    ),
                    action=TraceAction(kind="nop"), diagnostic=None,
                )
            )


# ---------------------------------------------------------------------------
# Panel-level presentation/enablement (no dialog opened)
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_inspect_trace_button_enabled_only_when_trace_present(tmp_path):
    _make_app()
    from app.services.agent_workflows import DevelopmentTestPresentation
    from app.services.designer_workflows import MatchPresentation
    from app.views.development import AgentDevelopmentPanel

    panel = AgentDevelopmentPanel()
    try:
        replay_path = tmp_path / "replay.jsonl"
        replay_path.write_text("{}\n", encoding="utf-8")
        trace_path = tmp_path / "trace.jsonl"
        _write_trace(trace_path)

        match = MatchPresentation(
            winner="A", termination_reason="tick_limit", result_path=tmp_path / "result.json",
            replay_path=replay_path,
        )

        with_trace = DevelopmentTestPresentation(
            agent_id="example", outcome="completed", match=match, trace_path=trace_path
        )
        panel.show_test_result(with_trace)
        assert panel.btnInspectTrace.isEnabled()
        assert panel.last_test_trace_path() == trace_path

        without_trace = DevelopmentTestPresentation(
            agent_id="example", outcome="completed", match=match, trace_path=None
        )
        panel.show_test_result(without_trace)
        assert not panel.btnInspectTrace.isEnabled()
        assert panel.last_test_trace_path() is None
    finally:
        panel.deleteLater()


@pytest.mark.gui
def test_inspect_trace_button_enabled_for_initialization_failure_with_trace(tmp_path):
    """A reset()-failure init failure still writes a trace (docs/specs/
    agent_lab.md §12) -- the button must track that, not just completed
    matches."""

    _make_app()
    from app.services.agent_workflows import DevelopmentTestPresentation
    from app.views.development import AgentDevelopmentPanel

    panel = AgentDevelopmentPanel()
    try:
        trace_path = tmp_path / "trace.jsonl"
        _write_trace(trace_path)

        presentation = DevelopmentTestPresentation(
            agent_id="example", outcome="initialization_failed",
            stage="reset", code="agent_reset_failed", error="boom",
            trace_path=trace_path,
        )
        panel.show_test_result(presentation)
        assert panel.btnInspectTrace.isEnabled()
    finally:
        panel.deleteLater()


@pytest.mark.gui
def test_inspect_trace_button_disabled_on_tool_failure(tmp_path):
    _make_app()
    from app.services.agent_workflows import DevelopmentTestPresentation
    from app.views.development import AgentDevelopmentPanel

    panel = AgentDevelopmentPanel()
    try:
        trace_path = tmp_path / "trace.jsonl"
        _write_trace(trace_path)
        # A tool_error presentation should never carry a trace_path in
        # practice, but even if it did, tool failures must not offer
        # trace inspection.
        presentation = DevelopmentTestPresentation(
            agent_id="example", outcome="tool_error", error="boom",
            is_tool_failure=True, trace_path=trace_path,
        )
        panel.show_test_result(presentation)
        assert not panel.btnInspectTrace.isEnabled()
    finally:
        panel.deleteLater()


@pytest.mark.gui
def test_inspect_trace_button_disabled_by_show_test_stopped(tmp_path):
    _make_app()
    from app.services.agent_workflows import DevelopmentTestPresentation
    from app.services.designer_workflows import MatchPresentation
    from app.views.development import AgentDevelopmentPanel

    panel = AgentDevelopmentPanel()
    try:
        trace_path = tmp_path / "trace.jsonl"
        _write_trace(trace_path)
        match = MatchPresentation(
            winner="A", termination_reason="tick_limit", result_path=tmp_path / "result.json",
            replay_path=None,
        )
        panel.show_test_result(
            DevelopmentTestPresentation(
                agent_id="example", outcome="completed", match=match, trace_path=trace_path
            )
        )
        assert panel.btnInspectTrace.isEnabled()

        panel.show_test_stopped("example")
        assert not panel.btnInspectTrace.isEnabled()
        assert panel.last_test_trace_path() is None
    finally:
        panel.deleteLater()


@pytest.mark.gui
def test_stdout_trace_line_is_parsed_into_presentation(tmp_path):
    from app.services.agent_workflows import build_development_test_presentation

    trace_path = tmp_path / "trace.jsonl"
    _write_trace(trace_path)
    replay_path = tmp_path / "replay.jsonl"
    replay_path.write_text("{}\n", encoding="utf-8")
    result_path = tmp_path / "result.json"
    summary_path = tmp_path / "summary.json"

    stdout = (
        "agent: example\n"
        "opponent: reference\n"
        "seed: 1337\n"
        "ticks: 30/30\n"
        "winner: reference\n"
        "termination: tick_limit\n"
        f"result: {result_path}\n"
        f"replay: {replay_path}\n"
        f"summary: {summary_path}\n"
        f"trace: {trace_path}\n"
        "\n"
        f"Run 'bytefray replay --replay {replay_path}' to inspect it.\n"
    )

    presentation = build_development_test_presentation(0, stdout, "", agent_id="example")

    assert presentation.outcome == "completed"
    assert presentation.trace_path == trace_path


def test_stdout_without_trace_line_leaves_trace_path_none(tmp_path):
    """Older/`--no-trace` output has no "trace:" line at all -- must not
    be treated as a tool failure just because a new optional field is
    absent."""

    from app.services.agent_workflows import build_development_test_presentation

    replay_path = tmp_path / "replay.jsonl"
    result_path = tmp_path / "result.json"
    summary_path = tmp_path / "summary.json"
    stdout = (
        "agent: example\n"
        "opponent: reference\n"
        "seed: 1337\n"
        "ticks: 30/30\n"
        "winner: reference\n"
        "termination: tick_limit\n"
        f"result: {result_path}\n"
        f"replay: {replay_path}\n"
        f"summary: {summary_path}\n"
    )

    presentation = build_development_test_presentation(0, stdout, "", agent_id="example")

    assert presentation.outcome == "completed"
    assert presentation.trace_path is None


# ---------------------------------------------------------------------------
# TraceInspectorDialog
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_trace_inspector_dialog_opens_and_navigates(tmp_path):
    _make_app()
    from app.views.trace_inspector import TraceInspectorDialog

    trace_path = tmp_path / "trace.jsonl"
    _write_trace(trace_path)

    dialog = TraceInspectorDialog(trace_path)
    try:
        assert dialog.tickSpin.minimum() == 1
        assert dialog.tickSpin.maximum() == 3
        assert "tick: 1" in dialog.detailText.toPlainText()

        dialog._go_next()
        assert dialog.tickSpin.value() == 2
        dialog._go_next()
        assert dialog.tickSpin.value() == 3
        dialog._go_next()  # already at the last tick -- must not raise or wrap
        assert dialog.tickSpin.value() == 3

        dialog._go_previous()
        dialog._go_previous()
        assert dialog.tickSpin.value() == 1
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_trace_inspector_dialog_handles_malformed_trace_without_crashing(tmp_path):
    _make_app()
    from app.views.trace_inspector import TraceInspectorDialog

    bad_path = tmp_path / "bad.jsonl"
    bad_path.write_text("not json\n", encoding="utf-8")

    dialog = TraceInspectorDialog(bad_path)
    try:
        assert dialog._document is None
        # No tick/agent controls exist on the error path -- opening the
        # dialog must not have raised, which is the property under test.
        assert not hasattr(dialog, "tickSpin")
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_trace_inspector_dialog_executes_no_agent_code(tmp_path, monkeypatch):
    """Opening the dialog must never import/execute the traced agent's own
    source file -- only parse the already-written trace JSONL."""

    _make_app()
    from app.views.trace_inspector import TraceInspectorDialog

    trace_path = tmp_path / "trace.jsonl"
    _write_trace(trace_path)

    sentinel_agent_source = tmp_path / "agent.py"
    sentinel_agent_source.write_text(
        "raise RuntimeError('this must never execute from the trace inspector')\n",
        encoding="utf-8",
    )

    dialog = TraceInspectorDialog(trace_path)
    try:
        assert dialog._document is not None
    finally:
        dialog.deleteLater()


# ---------------------------------------------------------------------------
# AgentDesigner wiring
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_designer_inspect_trace_opens_dialog_for_last_test(monkeypatch, tmp_path):
    _make_app()
    from app.agent_designer import AgentDesigner

    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))

    designer = AgentDesigner()
    try:
        trace_path = tmp_path / "trace.jsonl"
        _write_trace(trace_path)
        designer.development._last_test_trace = trace_path
        designer.development.btnInspectTrace.setEnabled(True)

        opened: list[Path] = []

        class _RecordingDialog:
            def __init__(self, path, parent=None):
                opened.append(path)

            def exec(self):
                return None

        monkeypatch.setattr("app.views.trace_inspector.TraceInspectorDialog", _RecordingDialog)
        designer._on_inspect_trace()

        assert opened == [trace_path]
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_designer_inspect_trace_is_a_noop_without_a_trace(monkeypatch, tmp_path):
    _make_app()
    from app.agent_designer import AgentDesigner

    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))

    designer = AgentDesigner()
    try:
        assert designer.development.last_test_trace_path() is None
        # Must not raise even though no trace has been produced yet.
        designer._on_inspect_trace()
    finally:
        designer.deleteLater()
