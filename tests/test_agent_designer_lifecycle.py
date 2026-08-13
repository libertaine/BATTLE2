"""GUI regression coverage for Designer QProcess lifecycle correctness.

These tests exercise AgentDesigner's process-lifecycle slots directly as
plain Python method calls -- no QTimer/event-loop timing is involved. Qt
signals are only ever emitted manually, synchronously, to prove that
_dispose_process's disconnect actually detaches a handler rather than
relying on object-identity checks alone.

Marked ``gui`` like the existing Designer smoke test: excluded from the
default headless run, exercised by the dedicated display-backed workflow.
"""

from __future__ import annotations

import json
import os

import pytest


@pytest.mark.gui
def test_stale_process_signals_do_not_mutate_current_run_state(monkeypatch, tmp_path):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QProcess
    from PySide6.QtWidgets import QApplication

    from app.agent_designer import AgentDesigner

    monkeypatch.setenv("BATTLE2_ROOT", str(tmp_path / "data"))
    QApplication.instance() or QApplication([])
    designer = AgentDesigner()

    current_proc = QProcess(designer)
    stale_proc = QProcess(designer)
    designer._proc = current_proc
    sentinel_result_path = tmp_path / "current-run" / "result.json"
    designer._result_path = sentinel_result_path
    designer._active_workflow = "match"
    designer.simple.setBusy(True)
    designer.advanced.setBusy(True)

    # A "finished" arriving from a process that is no longer self._proc
    # (e.g. one Stop()-killed and replaced by a new run) must be a no-op.
    designer._on_proc_finished(stale_proc, 0, QProcess.ExitStatus.NormalExit)

    assert designer._result_path == sentinel_result_path
    assert designer._proc is current_proc
    assert designer.simple.btnStop.isEnabled() is True  # still busy
    assert designer.advanced.btnStop.isEnabled() is True

    # Same guard for the error-signal handler.
    designer._on_proc_error(stale_proc, "RunMatch", "battle2", QProcess.ProcessError.Crashed)
    assert designer.simple.btnStop.isEnabled() is True

    # And for output piping -- a stale process's buffered output must not
    # be appended to a log that now belongs to a different run.
    designer._log_target = designer.simple
    before = designer.simple.log.toPlainText()
    designer._pipe_proc_output(stale_proc)
    assert designer.simple.log.toPlainText() == before

    designer.deleteLater()


@pytest.mark.gui
def test_current_process_finished_clears_busy_state(monkeypatch, tmp_path):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QProcess
    from PySide6.QtWidgets import QApplication

    from app.agent_designer import AgentDesigner

    monkeypatch.setenv("BATTLE2_ROOT", str(tmp_path / "data"))
    QApplication.instance() or QApplication([])
    designer = AgentDesigner()

    proc = QProcess(designer)
    designer._proc = proc
    designer._active_workflow = "match"
    designer._result_path = tmp_path / "missing" / "result.json"  # deliberately absent
    designer.simple.setBusy(True)
    designer.advanced.setBusy(True)

    designer._on_proc_finished(proc, 0, QProcess.ExitStatus.NormalExit)

    assert designer.simple.btnStop.isEnabled() is False
    assert designer.advanced.btnStop.isEnabled() is False
    assert designer.simple.btnRun.isEnabled() is True

    designer.deleteLater()


@pytest.mark.gui
def test_dispose_process_disconnect_prevents_stale_finished_from_firing(monkeypatch, tmp_path):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QProcess, QProcessEnvironment
    from PySide6.QtWidgets import QApplication

    from app.agent_designer import AgentDesigner

    monkeypatch.setenv("BATTLE2_ROOT", str(tmp_path / "data"))
    QApplication.instance() or QApplication([])
    designer = AgentDesigner()

    # Wire up a process exactly as a real run would (never started -- this
    # only tests signal plumbing, not process execution).
    proc = designer._start_process(
        ["true"], QProcessEnvironment.systemEnvironment(), tmp_path, label="RunMatch"
    )
    sentinel_result_path = tmp_path / "before-dispose" / "result.json"
    designer._result_path = sentinel_result_path
    designer._active_workflow = "match"
    designer.simple.setBusy(True)
    designer.advanced.setBusy(True)

    designer._dispose_process()
    assert designer._proc is None

    # If disconnect() genuinely detached the handler, manually emitting the
    # signal the (now-orphaned) process would still be capable of emitting
    # has no observable effect -- proving disconnection, not merely relying
    # on the proc-identity guard tested above.
    proc.finished.emit(0, QProcess.ExitStatus.NormalExit)

    assert designer._result_path == sentinel_result_path
    assert designer.simple.btnStop.isEnabled() is True  # untouched, still "busy"

    designer.deleteLater()


@pytest.mark.gui
def test_start_process_disposes_any_prior_process_first(monkeypatch, tmp_path):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QProcessEnvironment
    from PySide6.QtWidgets import QApplication

    from app.agent_designer import AgentDesigner

    monkeypatch.setenv("BATTLE2_ROOT", str(tmp_path / "data"))
    QApplication.instance() or QApplication([])
    designer = AgentDesigner()

    env = QProcessEnvironment.systemEnvironment()
    first = designer._start_process(["true"], env, tmp_path, label="RunMatch")
    assert designer._proc is first

    second = designer._start_process(["true"], env, tmp_path, label="RunMatch")
    assert designer._proc is second
    assert second is not first

    # The first process's finished signal (now disconnected by the second
    # _start_process call's internal _dispose_process) must be inert.
    designer._result_path = tmp_path / "second-run" / "result.json"
    designer.simple.setBusy(True)
    from PySide6.QtCore import QProcess

    first.finished.emit(0, QProcess.ExitStatus.NormalExit)
    assert designer._result_path == tmp_path / "second-run" / "result.json"
    assert designer.simple.btnStop.isEnabled() is True

    designer.deleteLater()


@pytest.mark.gui
def test_close_event_disposes_active_process_without_raising(monkeypatch, tmp_path):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QProcessEnvironment
    from PySide6.QtWidgets import QApplication

    from app.agent_designer import AgentDesigner

    monkeypatch.setenv("BATTLE2_ROOT", str(tmp_path / "data"))
    application = QApplication.instance() or QApplication([])
    designer = AgentDesigner()

    designer._start_process(
        ["python3", "-c", "import time; time.sleep(5)"],
        QProcessEnvironment.systemEnvironment(),
        tmp_path,
        label="RunMatch",
    )
    designer._proc.start()

    designer.close()  # invokes closeEvent, which must kill the child

    assert designer._proc is None
    designer.deleteLater()
    application.processEvents()


@pytest.mark.gui
def test_advanced_run_exports_agent_params_json_to_child_env(monkeypatch, tmp_path):
    """Advanced tab's per-agent "Agent Params" JSON editors (RunConfig.a_params/
    b_params) must reach the launched match process as BATTLE_AGENT_A_PARAMS_JSON/
    BATTLE_AGENT_B_PARAMS_JSON -- previously the JSON was validated locally and
    then silently discarded (docs/specs/agent_designer_workflow.md Sec 2.8), never
    reaching the child process for either agent.
    """
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from app.agent_designer import AgentDesigner
    from app.services.engine import RunConfig

    monkeypatch.setenv("BATTLE2_ROOT", str(tmp_path / "data"))
    QApplication.instance() or QApplication([])
    designer = AgentDesigner()

    captured = {}

    class _FakeProc:
        def start(self):
            pass

    def _fake_start_process(command, env, working_directory, *, label):
        captured["env"] = env
        return _FakeProc()

    monkeypatch.setattr(designer, "_start_process", _fake_start_process)

    cfg = RunConfig(
        a_type="Runner (Starter)",
        b_type="Writer (Starter)",
        arena=256,
        ticks=100,
        a_params={"byte": 7, "stride": 3},
        b_params=None,
    )
    designer._on_advanced_run(cfg)

    env = captured["env"]
    assert env.value("BATTLE_AGENT_A_PARAMS_JSON") == json.dumps({"byte": 7, "stride": 3})
    assert env.contains("BATTLE_AGENT_B_PARAMS_JSON") is False

    designer.deleteLater()
