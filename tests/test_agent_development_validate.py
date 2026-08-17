"""GUI regression coverage for the Phase 4b Agent Validation workflow.

Covers: out-of-process (QProcess) validation execution, structured-result
presentation (valid / invalid / tool failure), busy/state transitions
shared with match/tournament launch, stale-result clearing on selection
change, and environment/data-root handling.

Marked ``gui`` like the existing Designer tests: excluded from the default
headless run, exercised by the dedicated display-backed workflow.

Per the Phase 4b task's "Test architecture" guidance, most cases here
exercise a real (but stubbed-output) ``QProcess`` -- proving genuine
out-of-process execution and the Designer's buffering/parsing plumbing --
without needing the real, slower ``bytefray agents validate`` subprocess
for every case. A handful of true end-to-end tests at the bottom run the
real CLI against real scaffolded agents to prove the parser and the actual
CLI output never drift apart.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from app.services.agent_workflows import ValidationPresentation


def _make_app():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _stub_command(tmp_path: Path, *, stdout: str = "", stderr: str = "", exit_code: int = 0) -> list[str]:
    """A real, tiny child process standing in for `bytefray agents validate`.

    Used to test the Designer's QProcess plumbing (buffering, exit-code
    handling, parsing) deterministically and quickly, without needing the
    real CLI subprocess for every case -- this is still a genuine, separate
    OS process, not a mock.
    """
    script = tmp_path / f"stub_validate_{abs(hash((stdout, stderr, exit_code)))}.py"
    script.write_text(
        "import sys\n"
        f"sys.stdout.write({stdout!r})\n"
        f"sys.stderr.write({stderr!r})\n"
        "sys.stdout.flush()\n"
        "sys.stderr.flush()\n"
        f"sys.exit({exit_code})\n",
        encoding="utf-8",
    )
    return [sys.executable, str(script)]


def _write_agent(agents_dir: Path, agent_id: str, source: str) -> None:
    agent_dir = agents_dir / agent_id
    agent_dir.mkdir(parents=True)
    (agent_dir / "agent.yaml").write_text(
        'kind: python\napi_version: 1\nentrypoint: agent.py:create_agent\nversion: "0.1.0"\n',
        encoding="utf-8",
    )
    (agent_dir / "agent.py").write_text(source, encoding="utf-8")


_HANGING_AGENT_SOURCE = (
    "import time\n"
    "from battle_engine.agent_api import ActionKind, AgentAction, MatchContext, Observation\n\n"
    "class Agent:\n"
    "    def reset(self, context: MatchContext) -> None:\n"
    "        while True:\n"
    "            time.sleep(0.05)\n\n"
    "    def act(self, observation: Observation) -> AgentAction:\n"
    "        return AgentAction(ActionKind.HALT, None, None)\n\n"
    "def create_agent() -> Agent:\n"
    "    return Agent()\n"
)

_RESET_RAISES_SOURCE = (
    "from battle_engine.agent_api import ActionKind, AgentAction, MatchContext, Observation\n\n"
    "class Agent:\n"
    "    def reset(self, context: MatchContext) -> None:\n"
    "        raise RuntimeError('boom')\n\n"
    "    def act(self, observation: Observation) -> AgentAction:\n"
    "        return AgentAction(ActionKind.HALT, None, None)\n\n"
    "def create_agent() -> Agent:\n"
    "    return Agent()\n"
)


def _wait_for_finished(designer, timeout_ms: int = 15000) -> None:
    proc = designer._proc
    assert proc is not None
    ok = proc.waitForFinished(timeout_ms)
    assert ok, "validation subprocess did not finish within the test timeout"


# ---------------------------------------------------------------------------
# Pure presentation rendering (no process involved)
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_show_validation_result_renders_valid():
    _make_app()
    from app.views.development import AgentDevelopmentPanel

    panel = AgentDevelopmentPanel()
    panel.show_validation_result(
        ValidationPresentation(
            agent_id="my_agent", valid=True, api_version=1, dry_run_action="WRITE operand=232 value=165"
        )
    )
    text = panel.statusLabel.text()
    assert "Last validation: Valid" in text
    assert "API: 1" in text
    assert "Dry-run action: WRITE operand=232 value=165" in text


@pytest.mark.gui
def test_show_validation_result_renders_invalid_with_all_fields():
    _make_app()
    from app.views.development import AgentDevelopmentPanel

    panel = AgentDevelopmentPanel()
    panel.show_validation_result(
        ValidationPresentation(
            agent_id="broken",
            valid=False,
            stage="reset",
            code="agent_reset_failed",
            error="Python agent broken reset failed: RuntimeError: boom",
            detail="RuntimeError",
        )
    )
    text = panel.statusLabel.text()
    assert "Last validation: Invalid" in text
    assert "Stage: reset" in text
    assert "Code: agent_reset_failed" in text
    assert "Error: Python agent broken reset failed: RuntimeError: boom" in text
    assert "Detail: RuntimeError" in text


@pytest.mark.gui
def test_show_validation_result_omits_absent_detail_field():
    _make_app()
    from app.views.development import AgentDevelopmentPanel

    panel = AgentDevelopmentPanel()
    panel.show_validation_result(
        ValidationPresentation(
            agent_id="unknown_agent",
            valid=False,
            stage="discovery",
            code="agent_unknown",
            error="Unknown agent 'unknown_agent'.",
        )
    )
    text = panel.statusLabel.text()
    assert "Detail:" not in text


@pytest.mark.gui
def test_tool_failure_presentation_is_visually_distinct_from_invalid():
    _make_app()
    from app.views.development import (
        _INVALID_STYLE,
        _TOOL_FAILURE_STYLE,
        AgentDevelopmentPanel,
    )

    panel = AgentDevelopmentPanel()
    panel.show_validation_result(
        ValidationPresentation(agent_id="x", valid=False, stage="reset", code="agent_reset_failed", error="boom")
    )
    assert panel.statusLabel.styleSheet() == _INVALID_STYLE

    panel.show_tool_failure("x", "Validation process crashed unexpectedly.")
    text = panel.statusLabel.text()
    assert "Last validation: Could not be completed" in text
    assert "Validation process crashed unexpectedly." in text
    assert panel.statusLabel.styleSheet() == _TOOL_FAILURE_STYLE
    assert panel.statusLabel.styleSheet() != _INVALID_STYLE


@pytest.mark.gui
def test_showValidating_sets_running_text():
    _make_app()
    from app.views.development import AgentDevelopmentPanel

    panel = AgentDevelopmentPanel()
    panel.showValidating("my_agent")
    assert "Validating my_agent" in panel.statusLabel.text()


@pytest.mark.gui
def test_show_stopped_is_distinct_from_invalid_or_valid():
    _make_app()
    from app.views.development import AgentDevelopmentPanel

    panel = AgentDevelopmentPanel()
    panel.show_stopped("my_agent")
    text = panel.statusLabel.text()
    assert "Stopped by user" in text
    assert "Invalid" not in text
    assert "Valid" not in text.replace("Invalid", "")


# ---------------------------------------------------------------------------
# Enablement / selection / stale-result state
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_validate_disabled_with_no_agents():
    """Isolated panel unit test: no catalog means nothing is selectable.

    Uses a bare ``AgentDevelopmentPanel`` (same pattern as this file's
    presentation-only tests above) rather than a full ``AgentDesigner``,
    because Bytefray's real startup always seeds Python starter agents
    (``battle_engine.starters``) -- there is no way to observe a genuinely
    empty, nothing-selected catalog through the full Designer anymore.
    """
    _make_app()
    from app.views.development import AgentDevelopmentPanel

    panel = AgentDevelopmentPanel()
    try:
        assert panel.agentCombo.count() == 0
        assert panel.btnValidate.isEnabled() is False
    finally:
        panel.deleteLater()


@pytest.mark.gui
def test_validate_enabled_after_creation_and_selection(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("validatable", data_root=data_root)
        designer.refresh_agents(select="validatable")

        assert designer.development.agentCombo.currentText() == "validatable"
        assert designer.development.btnValidate.isEnabled() is True
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_selection_change_clears_prior_validation_result(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("agent_one", data_root=data_root)
        create_agent("agent_two", data_root=data_root)
        designer.refresh_agents()

        designer.development.selectAgent("agent_one")
        designer.development.show_validation_result(
            ValidationPresentation(agent_id="agent_one", valid=True, api_version=1, dry_run_action="HALT")
        )
        assert "Valid" in designer.development.statusLabel.text()

        designer.development.selectAgent("agent_two")
        text = designer.development.statusLabel.text()
        assert "Valid" not in text
        assert "agent_two" in text
        assert "No validation run yet" in text
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_refresh_with_same_selection_preserves_validation_result(monkeypatch, tmp_path):
    """A plain Refresh (same agent still selected) must not wipe a shown result."""
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("stable_agent", data_root=data_root)
        designer.refresh_agents(select="stable_agent")
        designer.development.show_validation_result(
            ValidationPresentation(agent_id="stable_agent", valid=True, api_version=1, dry_run_action="HALT")
        )

        designer.refresh_agents()  # same agent remains selected

        assert "Last validation: Valid" in designer.development.statusLabel.text()
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_setBusy_disables_validate_and_agent_combo(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("busy_agent", data_root=data_root)
        designer.refresh_agents(select="busy_agent")
        assert designer.development.btnValidate.isEnabled() is True

        designer.development.setBusy(True)
        assert designer.development.btnValidate.isEnabled() is False
        assert designer.development.agentCombo.isEnabled() is False
        assert designer.development.btnNewAgent.isEnabled() is False
        assert designer.development.btnRefresh.isEnabled() is False

        designer.development.setBusy(False)
        assert designer.development.btnValidate.isEnabled() is True
        assert designer.development.agentCombo.isEnabled() is True
    finally:
        designer.deleteLater()


# ---------------------------------------------------------------------------
# QProcess plumbing (real, fast, stubbed-output subprocess)
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_validate_success_via_real_qprocess_updates_ui_and_recovers(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("stub_valid_agent", data_root=data_root)
        designer.refresh_agents(select="stub_valid_agent")

        stdout = "agent: stub_valid_agent\nstatus: valid\napi_version: 1\ndry_run_action: WRITE operand=1 value=2\n"
        monkeypatch.setattr(
            agent_designer_module,
            "build_agents_command",
            lambda subcommand, arguments: _stub_command(tmp_path, stdout=stdout, exit_code=0),
        )

        designer._on_validate_agent()
        assert designer.development.btnValidate.isEnabled() is False  # running state
        assert "Validating stub_valid_agent" in designer.development.statusLabel.text()

        _wait_for_finished(designer)

        text = designer.development.statusLabel.text()
        assert "Last validation: Valid" in text
        assert "API: 1" in text
        assert designer.development.btnValidate.isEnabled() is True
        assert designer.development.agentCombo.isEnabled() is True
        assert designer.simple.btnRun.isEnabled() is True
        assert designer.advanced.btnRun.isEnabled() is True
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_validate_agent_failure_via_real_qprocess_is_not_a_tool_failure(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("stub_invalid_agent", data_root=data_root)
        designer.refresh_agents(select="stub_invalid_agent")

        stderr = (
            "agent: stub_invalid_agent\n"
            "status: invalid\n"
            "stage: reset\n"
            "code: agent_reset_failed\n"
            "error: Python agent stub_invalid_agent reset failed: RuntimeError: boom\n"
            "detail: RuntimeError\n"
        )
        monkeypatch.setattr(
            agent_designer_module,
            "build_agents_command",
            lambda subcommand, arguments: _stub_command(tmp_path, stderr=stderr, exit_code=2),
        )

        designer._on_validate_agent()
        _wait_for_finished(designer)

        text = designer.development.statusLabel.text()
        assert "Last validation: Invalid" in text
        assert "Code: agent_reset_failed" in text
        assert "Could not be completed" not in text
        assert designer.development.btnValidate.isEnabled() is True
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_validate_uses_discovery_id_not_display_name_when_they_differ(monkeypatch, tmp_path):
    """M5: Validate must always hand the CLI the discovery id (directory
    name), never the display name shown in the combo -- even when an
    agent's manifest declares a display name that differs from its
    discovery id.
    """

    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("validate_disc_id", data_root=data_root)
        manifest_path = data_root / "agents" / "validate_disc_id" / "agent.yaml"
        with manifest_path.open("a", encoding="utf-8") as handle:
            handle.write('\ndisplay: "Validate Friendly Display Name"\n')

        designer.refresh_agents(select="Validate Friendly Display Name")
        row = designer.development.selectedAgentRow()
        assert row is not None
        assert row.name == "Validate Friendly Display Name"
        assert row.agent_id == "validate_disc_id"

        captured_args: list[list[str]] = []

        def _capture(subcommand, arguments):
            captured_args.append(list(arguments))
            return _stub_command(
                tmp_path,
                stdout="agent: validate_disc_id\nstatus: valid\napi_version: 1\n",
            )

        monkeypatch.setattr(agent_designer_module, "build_agents_command", _capture)

        designer._on_validate_agent()
        _wait_for_finished(designer)

        assert captured_args == [["validate_disc_id"]]
        assert "Validate Friendly Display Name" not in captured_args[0]
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_malformed_output_from_real_qprocess_is_a_tool_failure(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("stub_agent", data_root=data_root)
        designer.refresh_agents(select="stub_agent")

        monkeypatch.setattr(
            agent_designer_module,
            "build_agents_command",
            lambda subcommand, arguments: _stub_command(tmp_path, stdout="nonsense\n", exit_code=0),
        )

        designer._on_validate_agent()
        _wait_for_finished(designer)

        text = designer.development.statusLabel.text()
        assert "Could not be completed" in text
        assert designer.development.btnValidate.isEnabled() is True
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_no_output_and_unexpected_crash_is_a_tool_failure(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("crash_agent", data_root=data_root)
        designer.refresh_agents(select="crash_agent")

        monkeypatch.setattr(
            agent_designer_module,
            "build_agents_command",
            lambda subcommand, arguments: _stub_command(tmp_path, exit_code=1),
        )

        designer._on_validate_agent()
        _wait_for_finished(designer)

        assert "Could not be completed" in designer.development.statusLabel.text()
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_process_failed_to_start_shows_tool_failure_and_recovers(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("agent_no_exe", data_root=data_root)
        designer.refresh_agents(select="agent_no_exe")

        monkeypatch.setattr(
            agent_designer_module.QMessageBox,
            "critical",
            staticmethod(lambda *a, **k: None),
        )
        missing = tmp_path / "does-not-exist-executable"
        monkeypatch.setattr(
            agent_designer_module,
            "build_agents_command",
            lambda subcommand, arguments: [str(missing)],
        )

        designer._on_validate_agent()

        from PySide6.QtWidgets import QApplication

        deadline = time.monotonic() + 5
        while designer._proc is not None and time.monotonic() < deadline:
            QApplication.processEvents()

        assert "Could not be completed" in designer.development.statusLabel.text()
        assert designer.development.btnValidate.isEnabled() is True
        assert designer.simple.btnRun.isEnabled() is True
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_build_agents_command_missing_frozen_executable_shows_tool_failure(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("frozen_missing_agent", data_root=data_root)
        designer.refresh_agents(select="frozen_missing_agent")

        def _raise(*a, **k):
            raise FileNotFoundError("Packaged executable not found: bytefray.exe")

        monkeypatch.setattr(agent_designer_module, "build_agents_command", _raise)

        designer._on_validate_agent()

        assert designer._proc is None  # never started a process
        assert "Could not be completed" in designer.development.statusLabel.text()
        assert designer.development.btnValidate.isEnabled() is True
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_duplicate_validate_click_does_not_start_second_process(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("dup_click_agent", data_root=data_root)
        designer.refresh_agents(select="dup_click_agent")

        monkeypatch.setattr(
            agent_designer_module,
            "build_agents_command",
            lambda subcommand, arguments: _stub_command(
                tmp_path, stdout="agent: x\nstatus: valid\napi_version: 1\ndry_run_action: HALT\n"
            ),
        )

        designer._on_validate_agent()
        first_proc = designer._proc
        assert first_proc is not None

        designer._on_validate_agent()  # duplicate click while running
        assert designer._proc is first_proc  # unchanged: no second process started

        _wait_for_finished(designer)
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_match_run_disables_validate_and_validate_disables_match(monkeypatch, tmp_path):
    """Cross-panel exclusivity: Sec 14.1 -- Validate and Match/Tournament share one process slot."""
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("cross_panel_agent", data_root=data_root)
        designer.refresh_agents(select="cross_panel_agent")

        monkeypatch.setattr(
            agent_designer_module,
            "build_agents_command",
            lambda subcommand, arguments: _stub_command(
                tmp_path, stdout="agent: x\nstatus: valid\napi_version: 1\ndry_run_action: HALT\n"
            ),
        )
        designer._on_validate_agent()
        assert designer.simple.btnRun.isEnabled() is False
        assert designer.advanced.btnRun.isEnabled() is False
        _wait_for_finished(designer)
        assert designer.simple.btnRun.isEnabled() is True
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_stop_while_validating_shows_stopped_and_recovers_controls(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("stoppable_agent", data_root=data_root)
        designer.refresh_agents(select="stoppable_agent")

        long_script = tmp_path / "long_running.py"
        long_script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
        monkeypatch.setattr(
            agent_designer_module,
            "build_agents_command",
            lambda subcommand, arguments: [sys.executable, str(long_script)],
        )

        designer._on_validate_agent()
        assert designer._proc is not None

        designer._on_stop_run()

        assert designer._proc is None
        assert designer.development.btnValidate.isEnabled() is True
        assert "Stopped by user" in designer.development.statusLabel.text()
        assert "stoppable_agent" in designer.development.statusLabel.text()
    finally:
        designer.deleteLater()


# ---------------------------------------------------------------------------
# Process isolation proof: no in-process/synchronous validate_agent call
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_validate_agent_is_never_imported_into_agent_designer_module():
    """Structural proof there is no in-process call path to validate_agent at all."""
    _make_app()
    import app.agent_designer as agent_designer_module

    assert "validate_agent" not in vars(agent_designer_module)


@pytest.mark.gui
def test_validate_runs_out_of_process_not_a_direct_call(monkeypatch, tmp_path):
    """A direct-call monkeypatch that would raise if invoked in-process stays inert."""
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    import battle_engine.agent_validation as agent_validation_module
    from battle_engine.agent_scaffold import create_agent

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    def _must_not_be_called_directly(*args, **kwargs):
        raise AssertionError("validate_agent must not be called synchronously on the GUI thread")

    monkeypatch.setattr(agent_validation_module, "validate_agent", _must_not_be_called_directly)

    designer = AgentDesigner()
    try:
        create_agent("isolated_agent", data_root=data_root)
        designer.refresh_agents(select="isolated_agent")

        monkeypatch.setattr(
            agent_designer_module,
            "build_agents_command",
            lambda subcommand, arguments: _stub_command(
                tmp_path,
                stdout="agent: isolated_agent\nstatus: valid\napi_version: 1\ndry_run_action: HALT\n",
            ),
        )

        designer._on_validate_agent()  # must not raise despite the monkeypatch above
        _wait_for_finished(designer)

        assert "Last validation: Valid" in designer.development.statusLabel.text()
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_hanging_validation_does_not_block_gui_event_loop(monkeypatch, tmp_path):
    """A hung child process must never freeze the Designer's own event loop."""
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from PySide6.QtWidgets import QApplication

    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        _write_agent(data_root / "agents", "hangs_forever", _HANGING_AGENT_SOURCE)
        designer.refresh_agents(select="hangs_forever")
        assert designer.development.selectedAgentRow() is not None

        designer._on_validate_agent()
        assert designer._proc is not None

        # Prove the GUI thread stays responsive: repeated processEvents()
        # calls must each return promptly while the child hangs, never
        # blocking for anywhere near the child's (never-reached) exit.
        deadline = time.monotonic() + 1.5
        iterations = 0
        while time.monotonic() < deadline:
            tick_start = time.monotonic()
            QApplication.processEvents()
            assert time.monotonic() - tick_start < 0.5
            iterations += 1
        assert iterations > 0
        assert designer._proc is not None  # still hung, never finished on its own

        # Clean up without ever waiting indefinitely for the hung child.
        designer._dispose_process()
        assert designer._proc is None
    finally:
        designer.deleteLater()


# ---------------------------------------------------------------------------
# End-to-end: real `bytefray agents validate` subprocess
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_end_to_end_real_cli_validates_a_scaffolded_agent(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("real_cli_agent", data_root=data_root)
        designer.refresh_agents(select="real_cli_agent")

        designer._on_validate_agent()
        _wait_for_finished(designer, timeout_ms=30000)

        text = designer.development.statusLabel.text()
        assert "Last validation: Valid" in text
        assert "API: 1" in text
        assert "WRITE" in text
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_end_to_end_real_cli_respects_custom_data_root_with_spaces(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "Custom Data Root With Spaces"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("spaced_root_agent", data_root=data_root)
        designer.refresh_agents(select="spaced_root_agent")

        designer._on_validate_agent()
        _wait_for_finished(designer, timeout_ms=30000)

        assert "Last validation: Valid" in designer.development.statusLabel.text()
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_end_to_end_real_cli_reports_agent_reset_failure(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        _write_agent(data_root / "agents", "reset_raises", _RESET_RAISES_SOURCE)
        designer.refresh_agents(select="reset_raises")

        designer._on_validate_agent()
        _wait_for_finished(designer, timeout_ms=30000)

        text = designer.development.statusLabel.text()
        assert "Last validation: Invalid" in text
        assert "Stage: reset" in text
        assert "Code: agent_reset_failed" in text
        assert "Could not be completed" not in text
    finally:
        designer.deleteLater()


# ---------------------------------------------------------------------------
# Regression: Phase 4a workflows unaffected
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_new_agent_and_open_folder_still_work_alongside_validate(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from app.agent_designer import AgentDesigner
    from app.views.development import NewAgentDialog

    designer = AgentDesigner()
    try:
        dialog = NewAgentDialog(designer.battle_root)
        dialog.agentId.setText("post_validate_agent")
        dialog._on_ok()
        assert dialog.result is not None

        designer.refresh_agents(select="post_validate_agent")
        assert designer.development.agentCombo.currentText() == "post_validate_agent"
        assert designer.development.btnOpenFolder.isEnabled() is True
        assert designer.development.btnValidate.isEnabled() is True
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_simple_and_advanced_run_buttons_unaffected_when_idle(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        assert designer.simple.btnRun.isEnabled() is True
        assert designer.advanced.btnRun.isEnabled() is True
    finally:
        designer.deleteLater()
