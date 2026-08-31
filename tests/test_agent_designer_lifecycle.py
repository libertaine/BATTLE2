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


def _capture_match_launch(monkeypatch, designer):
    captured = {"started": False}

    class _FakeProc:
        def start(self):
            captured["started"] = True

    def _fake_start_process(command, env, working_directory, *, label):
        captured.update(
            command=command,
            env=env,
            working_directory=working_directory,
            label=label,
        )
        return _FakeProc()

    monkeypatch.setattr(designer, "_start_process", _fake_start_process)
    return captured


def _argument_value(command: list[str], flag: str) -> str:
    return command[command.index(flag) + 1]


@pytest.mark.gui
@pytest.mark.parametrize(
    ("panel_name", "agent_a", "agent_b"),
    [
        ("simple", "adaptive", "hunter"),
        ("advanced", "runner", "writer"),
    ],
)
def test_designer_panels_launch_starter_agents_by_discovery_id(
    monkeypatch, tmp_path, panel_name, agent_a, agent_b
):
    """The combo's canonical discovery ids must cross the Designer boundary."""
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from app.agent_designer import AgentDesigner

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path / "data"))
    QApplication.instance() or QApplication([])
    designer = AgentDesigner()
    captured = _capture_match_launch(monkeypatch, designer)
    panel = getattr(designer, panel_name)

    panel.agentA.setCurrentIndex(panel.agentA.findData(agent_a))
    panel.agentB.setCurrentIndex(panel.agentB.findData(agent_b))
    panel._emit_run()

    assert captured["started"] is True
    assert captured["label"] == "RunMatch"
    assert _argument_value(captured["command"], "--a-type") == agent_a
    assert _argument_value(captured["command"], "--b-type") == agent_b
    expected_ruleset = "bytefray-rules-2" if agent_a == "adaptive" else "bytefray-rules-1"
    assert _argument_value(captured["command"], "--ruleset") == expected_ruleset
    assert "could not resolve agents" not in panel.log.toPlainText()
    designer.deleteLater()


@pytest.mark.gui
def test_designer_resolves_duplicate_displays_by_id_and_allows_self_match(monkeypatch, tmp_path):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from app.agent_designer import AgentDesigner
    from app.services.agent_catalog import AgentRow

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path / "data"))
    QApplication.instance() or QApplication([])
    designer = AgentDesigner()
    rows = [
        AgentRow(
            name="Friendly",
            path=str(tmp_path / "agents" / agent_id),
            blob_path=None,
            meta={
                "name": agent_id,
                "display": "Friendly",
                "kind": "python",
                "api_version": 1,
            },
            agent_id=agent_id,
        )
        for agent_id in ("alpha_id", "beta_id")
    ]
    monkeypatch.setattr(designer.catalog, "list_agents", lambda: rows)
    designer.refresh_agents()
    captured = _capture_match_launch(monkeypatch, designer)

    assert designer._resolve_agent_row(rows, "Friendly") is None
    assert designer._resolve_agent_row(rows[:1], "Friendly") is rows[0]

    designer.simple.agentA.setCurrentIndex(designer.simple.agentA.findData("beta_id"))
    designer.simple.agentB.setCurrentIndex(designer.simple.agentB.findData("beta_id"))
    designer.simple._emit_run()

    assert captured["started"] is True
    assert _argument_value(captured["command"], "--a-type") == "beta_id"
    assert _argument_value(captured["command"], "--b-type") == "beta_id"
    designer.deleteLater()


@pytest.mark.gui
def test_refresh_discovers_once_and_passes_full_catalog_to_every_panel(
    monkeypatch, tmp_path
):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from app.agent_designer import AgentDesigner
    from app.services.agent_catalog import AgentRow

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path / "data"))
    QApplication.instance() or QApplication([])
    designer = AgentDesigner()
    rows = [
        AgentRow("VM", "/agents/vm", None, {"kind": "builtin"}, "vm"),
        AgentRow(
            "Legacy",
            "/agents/legacy",
            None,
            {"kind": "python", "api_version": 1},
            "legacy",
        ),
        AgentRow(
            "Process",
            "/agents/process",
            None,
            {"kind": "python", "api_version": 2},
            "process",
        ),
    ]
    calls = 0

    def list_agents():
        nonlocal calls
        calls += 1
        return rows

    received = {}
    monkeypatch.setattr(designer.catalog, "list_agents", list_agents)
    monkeypatch.setattr(designer.simple, "setAgents", lambda value: received.setdefault("simple", value))
    monkeypatch.setattr(
        designer.advanced, "setAgents", lambda value: received.setdefault("advanced", value)
    )
    monkeypatch.setattr(
        designer.development,
        "setAgents",
        lambda value: received.setdefault("development", value),
    )

    designer.refresh_agents()

    assert calls == 1
    assert received == {"simple": rows, "advanced": rows, "development": rows}
    designer.deleteLater()


@pytest.mark.gui
def test_stale_process_signals_do_not_mutate_current_run_state(monkeypatch, tmp_path):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QProcess
    from PySide6.QtWidgets import QApplication

    from app.agent_designer import AgentDesigner

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path / "data"))
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
    designer._on_proc_error(stale_proc, "RunMatch", "bytefray", QProcess.ProcessError.Crashed)
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

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path / "data"))
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

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path / "data"))
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

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path / "data"))
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

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path / "data"))
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
    b_params) must reach the launched match process as BYTEFRAY_AGENT_A_PARAMS_JSON/
    BYTEFRAY_AGENT_B_PARAMS_JSON -- previously the JSON was validated locally and
    then silently discarded (docs/specs/agent_designer_workflow.md Sec 2.8), never
    reaching the child process for either agent.
    """
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from app.agent_designer import AgentDesigner
    from app.services.engine import RunConfig

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path / "data"))
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
    assert env.value("BYTEFRAY_AGENT_A_PARAMS_JSON") == json.dumps({"byte": 7, "stride": 3})
    assert env.contains("BYTEFRAY_AGENT_B_PARAMS_JSON") is False

    designer.deleteLater()
