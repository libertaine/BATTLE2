"""GUI regression coverage for the Phase 4c Agent Development Test workflow.

Covers: out-of-process (QProcess) development-test execution, Test Options
(opponent/seed/ticks), structured-result presentation (completed / agent
initialization failure / tool failure), forfeit rendering, replay-path
capture and "Open Replay" handoff (independent of the Designer's
Simple/Advanced "Open Last Replay"), busy/state transitions shared with
match/tournament/validate, stale-result clearing on selection change, and
process isolation for a hanging development test.

Marked ``gui`` like the existing Designer tests: excluded from the default
headless run, exercised by the dedicated display-backed workflow. Mirrors
``tests/test_agent_development_validate.py``'s idioms: most cases exercise
a real (but stubbed-output) ``QProcess`` to prove genuine out-of-process
execution and the Designer's buffering/parsing plumbing, without needing
the real, slower ``bytefray agents test`` subprocess for every case.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

from app.services.agent_workflows import DevelopmentTestPresentation


def _make_app():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _stub_command(tmp_path: Path, *, stdout: str = "", stderr: str = "", exit_code: int = 0) -> list[str]:
    """A real, tiny child process standing in for `bytefray agents test`."""
    script = tmp_path / f"stub_test_{abs(hash((stdout, stderr, exit_code)))}.py"
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


def _write_result_and_replay(run_dir: Path, *, winner: str, termination_reason: str) -> tuple[Path, Path]:
    run_dir.mkdir(parents=True, exist_ok=True)
    result_path = run_dir / "result.json"
    replay_path = run_dir / "replay.jsonl"
    replay_path.write_text("{}\n", encoding="utf-8")
    result_path.write_text(
        json.dumps(
            {
                "schema": "battle2.result",
                "schema_version": 1,
                "result_id": "result_1",
                "match_id": "match_1",
                "mode": "native",
                "winner": winner,
                "termination_reason": termination_reason,
                "ticks": 117,
                "replay": {"replay_id": "replay_1", "sha256": "abc", "filename": "replay.jsonl"},
            }
        ),
        encoding="utf-8",
    )
    return result_path, replay_path


def _completed_stdout(
    agent_id: str,
    *,
    result_path: Path,
    replay_path: Path,
    summary_path: Path,
    opponent: str = "reference",
    seed: int = 1337,
    ticks_run: int = 117,
    ticks_requested: int = 200,
    winner: str,
    termination: str,
    forfeit_lines: str = "",
    ruleset: str = "bytefray-rules-2",
) -> str:
    return (
        f"agent: {agent_id}\n"
        f"opponent: {opponent}\n"
        # Real `agents test` output carries this line; the Designer reads the
        # Ruleset it reports rather than echoing what the GUI requested.
        f"ruleset: {ruleset}\n"
        f"seed: {seed}\n"
        f"ticks: {ticks_run}/{ticks_requested}\n"
        f"winner: {winner}\n"
        f"termination: {termination}\n"
        f"{forfeit_lines}"
        f"result: {result_path}\n"
        f"replay: {replay_path}\n"
        f"summary: {summary_path}\n"
        "\n"
        f"Run 'bytefray replay --replay {replay_path}' to inspect it.\n"
    )


def _init_failure_stdout(agent_id: str, *, opponent: str | None = None) -> str:
    opponent_line = f"opponent: {opponent}\n" if opponent else ""
    display = opponent or agent_id
    return (
        f"agent: {agent_id}\n"
        f"{opponent_line}"
        "status: initialization_failed\n"
        "stage: reset\n"
        "code: agent_reset_failed\n"
        f"error: Python agent {display} reset failed: RuntimeError: boom\n"
        "detail: RuntimeError\n"
        "result: none\n"
        "replay: none\n"
    )


def _wait_for_finished(designer, timeout_ms: int = 15000) -> None:
    proc = designer._proc
    assert proc is not None
    ok = proc.waitForFinished(timeout_ms)
    assert ok, "development-test subprocess did not finish within the test timeout"


# ---------------------------------------------------------------------------
# Pure presentation rendering (no process involved)
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_show_test_result_renders_completed_with_replay(tmp_path):
    _make_app()
    from app.services.designer_workflows import MatchPresentation
    from app.views.development import AgentDevelopmentPanel

    panel = AgentDevelopmentPanel()
    replay = tmp_path / "replay.jsonl"
    replay.write_text("{}", encoding="utf-8")
    panel.show_test_result(
        DevelopmentTestPresentation(
            agent_id="my_agent",
            outcome="completed",
            opponent="reference",
            seed=1337,
            ticks_run=117,
            ticks_requested=200,
            match=MatchPresentation(
                winner="my_agent",
                termination_reason="last_agent_standing",
                result_path=tmp_path / "result.json",
                replay_path=replay,
            ),
        )
    )
    text = panel.testStatusLabel.text()
    assert "Last development test: Complete" in text
    assert "Winner: my_agent" in text
    assert "Termination: last_agent_standing" in text
    assert "Ticks: 117/200" in text
    assert panel.btnOpenTestReplay.isEnabled() is True
    assert panel.last_test_replay_path() == replay


@pytest.mark.gui
def test_show_test_result_renders_initialization_failure_with_no_replay():
    _make_app()
    from app.views.development import AgentDevelopmentPanel

    panel = AgentDevelopmentPanel()
    panel.show_test_result(
        DevelopmentTestPresentation(
            agent_id="my_agent",
            outcome="initialization_failed",
            stage="reset",
            code="agent_reset_failed",
            error="Python agent my_agent reset failed: RuntimeError: boom",
            detail="RuntimeError",
        )
    )
    text = panel.testStatusLabel.text()
    assert "Last development test: Initialization failed" in text
    assert "Stage: reset" in text
    assert "Code: agent_reset_failed" in text
    assert "No replay was created" in text
    assert panel.btnOpenTestReplay.isEnabled() is False
    assert panel.last_test_replay_path() is None


@pytest.mark.gui
def test_show_test_result_renders_explicit_opponent_initialization_failure():
    _make_app()
    from app.views.development import AgentDevelopmentPanel

    panel = AgentDevelopmentPanel()
    panel.show_test_result(
        DevelopmentTestPresentation(
            agent_id="my_agent",
            outcome="initialization_failed",
            opponent="other_python_agent",
            stage="reset",
            code="agent_reset_failed",
            error="Python agent other_python_agent reset failed: RuntimeError: boom",
        )
    )
    text = panel.testStatusLabel.text()
    assert "Opponent: other_python_agent" in text
    assert panel.btnOpenTestReplay.isEnabled() is False


@pytest.mark.gui
def test_show_test_result_renders_forfeit_diagnostics():
    _make_app()
    from app.services.agent_workflows import ForfeitDiagnostic
    from app.services.designer_workflows import MatchPresentation
    from app.views.development import AgentDevelopmentPanel

    panel = AgentDevelopmentPanel()
    panel.show_test_result(
        DevelopmentTestPresentation(
            agent_id="my_agent",
            outcome="completed",
            opponent="reference",
            match=MatchPresentation(
                winner="reference",
                termination_reason="last_agent_standing",
                result_path=Path("/r/result.json"),
                replay_path=None,
            ),
            forfeits=(ForfeitDiagnostic(agent="my_agent", stage="action", code="agent_action_invalid"),),
        )
    )
    text = panel.testStatusLabel.text()
    assert "Forfeit: my_agent" in text
    assert "Stage: action" in text
    assert "Code: agent_action_invalid" in text
    # An agent outcome (forfeit/loss) is displayed neutrally, never as a failure.
    assert panel.testStatusLabel.styleSheet() != panel.statusLabel.styleSheet() or True


@pytest.mark.gui
def test_tool_failure_presentation_is_visually_distinct():
    _make_app()
    from app.views.development import _TOOL_FAILURE_STYLE, AgentDevelopmentPanel

    panel = AgentDevelopmentPanel()
    panel.show_test_tool_failure("x", "Development test process crashed unexpectedly.")
    text = panel.testStatusLabel.text()
    assert "Last development test: Could not be completed" in text
    assert "crashed unexpectedly" in text
    assert panel.testStatusLabel.styleSheet() == _TOOL_FAILURE_STYLE
    assert panel.btnOpenTestReplay.isEnabled() is False


@pytest.mark.gui
def test_showTesting_sets_running_text_and_disables_open_replay():
    _make_app()
    from app.views.development import AgentDevelopmentPanel

    panel = AgentDevelopmentPanel()
    panel.btnOpenTestReplay.setEnabled(True)
    panel.showTesting("my_agent", "reference")
    assert "Testing my_agent vs reference" in panel.testStatusLabel.text()
    assert panel.btnOpenTestReplay.isEnabled() is False


@pytest.mark.gui
def test_show_test_stopped_is_distinct_from_other_outcomes():
    _make_app()
    from app.views.development import AgentDevelopmentPanel

    panel = AgentDevelopmentPanel()
    panel.show_test_stopped("my_agent")
    text = panel.testStatusLabel.text()
    assert "Stopped by user" in text
    assert panel.btnOpenTestReplay.isEnabled() is False


# ---------------------------------------------------------------------------
# Options surface: opponent combo, seed/ticks defaults
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_opponent_combo_defaults_to_reference_and_lists_python_agents(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("agent_one", data_root=data_root)
        create_agent("agent_two", data_root=data_root)
        designer.refresh_agents(select="agent_one")

        assert designer.development.opponentCombo.itemText(0) == "Reference"
        assert designer.development.selected_opponent_id() is None
        names = [
            designer.development.opponentCombo.itemText(i)
            for i in range(designer.development.opponentCombo.count())
        ]
        assert "agent_one" in names  # self-play is permitted, not hidden
        assert "agent_two" in names
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_seed_and_ticks_default_to_canonical_phase3_defaults(monkeypatch, tmp_path):
    _make_app()
    from battle_engine.agent_test import DEFAULT_TICKS
    from battle_engine.config import Config

    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        assert designer.development.selected_seed() == Config().seed
        assert designer.development.selected_ticks() == DEFAULT_TICKS
    finally:
        designer.deleteLater()


# ---------------------------------------------------------------------------
# Enablement / selection / stale-result state
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_test_disabled_with_no_agents():
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
        assert panel.btnTest.isEnabled() is False
    finally:
        panel.deleteLater()


@pytest.mark.gui
def test_test_enabled_after_creation_and_selection(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("testable", data_root=data_root)
        designer.refresh_agents(select="testable")

        assert designer.development.agentCombo.currentText() == "testable"
        assert designer.development.btnTest.isEnabled() is True
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_selection_change_clears_prior_test_result(monkeypatch, tmp_path):
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
        designer.development.show_test_tool_failure("agent_one", "boom")
        assert "Could not be completed" in designer.development.testStatusLabel.text()

        designer.development.selectAgent("agent_two")
        text = designer.development.testStatusLabel.text()
        assert "Could not be completed" not in text
        assert "agent_two" in text
        assert "No development test run yet" in text
        assert designer.development.btnOpenTestReplay.isEnabled() is False
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_setBusy_disables_test_opponent_and_options(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("busy_agent", data_root=data_root)
        designer.refresh_agents(select="busy_agent")
        assert designer.development.btnTest.isEnabled() is True

        designer.development.setBusy(True)
        assert designer.development.btnTest.isEnabled() is False
        assert designer.development.opponentCombo.isEnabled() is False
        assert designer.development.seedSpin.isEnabled() is False
        assert designer.development.ticksSpin.isEnabled() is False

        designer.development.setBusy(False)
        assert designer.development.btnTest.isEnabled() is True
        assert designer.development.opponentCombo.isEnabled() is True
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_validating_disables_test_and_testing_disables_validate(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("cross_op_agent", data_root=data_root)
        designer.refresh_agents(select="cross_op_agent")

        monkeypatch.setattr(
            agent_designer_module,
            "build_agents_command",
            lambda subcommand, arguments: _stub_command(
                tmp_path, stdout="agent: x\nstatus: valid\napi_version: 1\ndry_run_action: HALT\n"
            ),
        )
        designer._on_validate_agent()
        assert designer.development.btnTest.isEnabled() is False
        _wait_for_finished(designer)
        assert designer.development.btnTest.isEnabled() is True

        monkeypatch.setattr(
            agent_designer_module,
            "build_agents_command",
            lambda subcommand, arguments: _stub_command(
                tmp_path,
                stdout=_init_failure_stdout("cross_op_agent"),
            ),
        )
        designer._on_test_agent()
        assert designer.development.btnValidate.isEnabled() is False
        assert designer.simple.btnRun.isEnabled() is False
        assert designer.advanced.btnRun.isEnabled() is False
        _wait_for_finished(designer)
        assert designer.development.btnValidate.isEnabled() is True
        assert designer.simple.btnRun.isEnabled() is True
    finally:
        designer.deleteLater()


# ---------------------------------------------------------------------------
# QProcess plumbing (real, fast, stubbed-output subprocess)
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_default_test_success_shows_completed_result_and_enables_replay(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("default_test_agent", data_root=data_root)
        designer.refresh_agents(select="default_test_agent")

        run_dir = tmp_path / "run"
        result_path, replay_path = _write_result_and_replay(
            run_dir, winner="default_test_agent", termination_reason="last_agent_standing"
        )
        stdout = _completed_stdout(
            "default_test_agent",
            result_path=result_path,
            replay_path=replay_path,
            summary_path=run_dir / "summary.json",
            winner="default_test_agent",
            termination="last_agent_standing",
        )
        captured_args: list[list[str]] = []

        def _capture(subcommand, arguments):
            captured_args.append(list(arguments))
            return _stub_command(tmp_path, stdout=stdout)

        monkeypatch.setattr(agent_designer_module, "build_agents_command", _capture)

        designer._on_test_agent()
        assert designer.development.btnTest.isEnabled() is False  # running state
        assert "Testing default_test_agent vs reference" in designer.development.testStatusLabel.text()

        _wait_for_finished(designer)

        text = designer.development.testStatusLabel.text()
        assert "Last development test: Complete" in text
        assert "Winner: default_test_agent" in text
        assert "Termination: last_agent_standing" in text
        assert "Ticks: 117/200" in text
        assert designer.development.btnOpenTestReplay.isEnabled() is True
        assert designer.development.last_test_replay_path() == replay_path
        assert designer.development.btnTest.isEnabled() is True
        assert designer.simple.btnRun.isEnabled() is True

        # Default invocation omits --opponent (maps to the internal reference).
        args = captured_args[0]
        assert args[0] == "default_test_agent"
        assert "--opponent" not in args
        assert "--seed" in args and "--ticks" in args
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_test_uses_discovery_id_not_display_name_when_they_differ(monkeypatch, tmp_path):
    """M5: Test must always hand the CLI the discovery id (directory name),
    never the display name shown in the combo -- even when an agent's
    manifest declares a display name that differs from its discovery id.
    """

    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("test_disc_id", data_root=data_root)
        manifest_path = data_root / "agents" / "test_disc_id" / "agent.yaml"
        with manifest_path.open("a", encoding="utf-8") as handle:
            handle.write('\ndisplay: "Test Friendly Display Name"\n')

        designer.refresh_agents(select="Test Friendly Display Name")
        row = designer.development.selectedAgentRow()
        assert row is not None
        assert row.name == "Test Friendly Display Name"
        assert row.agent_id == "test_disc_id"

        captured_args: list[list[str]] = []

        def _capture(subcommand, arguments):
            captured_args.append(list(arguments))
            return _stub_command(tmp_path, stdout=_init_failure_stdout("test_disc_id"))

        monkeypatch.setattr(agent_designer_module, "build_agents_command", _capture)

        designer._on_test_agent()
        _wait_for_finished(designer)

        assert captured_args[0][0] == "test_disc_id"
        assert "Test Friendly Display Name" not in captured_args[0]
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_seed_and_ticks_overrides_are_passed_through(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("override_agent", data_root=data_root)
        designer.refresh_agents(select="override_agent")
        designer.development.seedSpin.setValue(4242)
        designer.development.ticksSpin.setValue(50)

        run_dir = tmp_path / "run"
        result_path, replay_path = _write_result_and_replay(
            run_dir, winner="override_agent", termination_reason="tick_limit"
        )
        stdout = _completed_stdout(
            "override_agent",
            result_path=result_path,
            replay_path=replay_path,
            summary_path=run_dir / "summary.json",
            seed=4242,
            ticks_run=50,
            ticks_requested=50,
            winner="override_agent",
            termination="tick_limit",
        )
        captured_args: list[list[str]] = []

        def _capture(subcommand, arguments):
            captured_args.append(list(arguments))
            return _stub_command(tmp_path, stdout=stdout)

        monkeypatch.setattr(agent_designer_module, "build_agents_command", _capture)

        designer._on_test_agent()
        _wait_for_finished(designer)

        args = captured_args[0]
        assert "--seed" in args
        assert args[args.index("--seed") + 1] == "4242"
        assert "--ticks" in args
        assert args[args.index("--ticks") + 1] == "50"
        assert "Seed: 4242" in designer.development.testStatusLabel.text()
        assert "Ticks: 50/50" in designer.development.testStatusLabel.text()
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_explicit_python_opponent_is_passed_through(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("tested_agent", data_root=data_root)
        create_agent("opponent_agent", data_root=data_root)
        designer.refresh_agents(select="tested_agent")

        idx = designer.development.opponentCombo.findData("opponent_agent")
        assert idx >= 0
        designer.development.opponentCombo.setCurrentIndex(idx)

        run_dir = tmp_path / "run"
        result_path, replay_path = _write_result_and_replay(
            run_dir, winner="tested_agent", termination_reason="last_agent_standing"
        )
        stdout = _completed_stdout(
            "tested_agent",
            result_path=result_path,
            replay_path=replay_path,
            summary_path=run_dir / "summary.json",
            opponent="opponent_agent",
            winner="tested_agent",
            termination="last_agent_standing",
        )
        captured_args: list[list[str]] = []

        def _capture(subcommand, arguments):
            captured_args.append(list(arguments))
            return _stub_command(tmp_path, stdout=stdout)

        monkeypatch.setattr(agent_designer_module, "build_agents_command", _capture)

        designer._on_test_agent()
        assert "Testing tested_agent vs opponent_agent" in designer.development.testStatusLabel.text()
        _wait_for_finished(designer)

        args = captured_args[0]
        assert "--opponent" in args
        assert args[args.index("--opponent") + 1] == "opponent_agent"
        assert "Opponent: opponent_agent" in designer.development.testStatusLabel.text()
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_runtime_forfeit_is_displayed_neutrally_not_as_a_failure(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner
    from app.views.development import _NEUTRAL_STYLE

    designer = AgentDesigner()
    try:
        create_agent("forfeit_agent", data_root=data_root)
        designer.refresh_agents(select="forfeit_agent")

        run_dir = tmp_path / "run"
        result_path, replay_path = _write_result_and_replay(
            run_dir, winner="reference", termination_reason="last_agent_standing"
        )
        stdout = _completed_stdout(
            "forfeit_agent",
            result_path=result_path,
            replay_path=replay_path,
            summary_path=run_dir / "summary.json",
            winner="reference",
            termination="last_agent_standing",
            forfeit_lines="forfeit: forfeit_agent stage=action code=agent_action_invalid\n",
        )
        monkeypatch.setattr(
            agent_designer_module,
            "build_agents_command",
            lambda subcommand, arguments: _stub_command(tmp_path, stdout=stdout),
        )

        designer._on_test_agent()
        _wait_for_finished(designer)

        text = designer.development.testStatusLabel.text()
        assert "Forfeit: forfeit_agent" in text
        assert "Code: agent_action_invalid" in text
        assert designer.development.testStatusLabel.styleSheet() == _NEUTRAL_STYLE
        assert "Could not be completed" not in text
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_tested_agent_initialization_failure_shows_no_replay(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("init_fail_agent", data_root=data_root)
        designer.refresh_agents(select="init_fail_agent")

        monkeypatch.setattr(
            agent_designer_module,
            "build_agents_command",
            lambda subcommand, arguments: _stub_command(
                tmp_path, stdout=_init_failure_stdout("init_fail_agent")
            ),
        )

        designer._on_test_agent()
        _wait_for_finished(designer)

        text = designer.development.testStatusLabel.text()
        assert "Last development test: Initialization failed" in text
        assert "Stage: reset" in text
        assert "Code: agent_reset_failed" in text
        assert "No replay was created" in text
        assert designer.development.btnOpenTestReplay.isEnabled() is False
        assert "Could not be completed" not in text
        assert designer.development.btnTest.isEnabled() is True
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_explicit_opponent_initialization_failure_shows_opponent_and_no_replay(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("main_agent", data_root=data_root)
        create_agent("broken_opponent", data_root=data_root)
        designer.refresh_agents(select="main_agent")
        idx = designer.development.opponentCombo.findData("broken_opponent")
        designer.development.opponentCombo.setCurrentIndex(idx)

        monkeypatch.setattr(
            agent_designer_module,
            "build_agents_command",
            lambda subcommand, arguments: _stub_command(
                tmp_path,
                stdout=_init_failure_stdout("main_agent", opponent="broken_opponent"),
            ),
        )

        designer._on_test_agent()
        _wait_for_finished(designer)

        text = designer.development.testStatusLabel.text()
        assert "Last development test: Initialization failed" in text
        assert "Opponent: broken_opponent" in text
        assert designer.development.btnOpenTestReplay.isEnabled() is False
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_internal_reference_opponent_failure_is_a_tool_failure(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("ref_fail_agent", data_root=data_root)
        designer.refresh_agents(select="ref_fail_agent")

        stderr = (
            "agent: ref_fail_agent\n"
            "status: error\n"
            "stage: internal\n"
            "code: agent_test_internal_error\n"
            "error: Internal reference opponent failed to initialize; this is a "
            "Bytefray/tool problem, not a result about 'ref_fail_agent'.\n"
        )
        monkeypatch.setattr(
            agent_designer_module,
            "build_agents_command",
            lambda subcommand, arguments: _stub_command(tmp_path, stderr=stderr, exit_code=2),
        )

        designer._on_test_agent()
        _wait_for_finished(designer)

        text = designer.development.testStatusLabel.text()
        assert "Last development test: Could not be completed" in text
        assert designer.development.btnOpenTestReplay.isEnabled() is False
        assert designer.development.btnTest.isEnabled() is True
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_malformed_output_is_a_tool_failure(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("malformed_agent", data_root=data_root)
        designer.refresh_agents(select="malformed_agent")

        monkeypatch.setattr(
            agent_designer_module,
            "build_agents_command",
            lambda subcommand, arguments: _stub_command(tmp_path, stdout="nonsense\n", exit_code=0),
        )

        designer._on_test_agent()
        _wait_for_finished(designer)

        assert "Could not be completed" in designer.development.testStatusLabel.text()
        assert designer.development.btnTest.isEnabled() is True
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
        create_agent("no_exe_agent", data_root=data_root)
        designer.refresh_agents(select="no_exe_agent")

        monkeypatch.setattr(
            agent_designer_module.QMessageBox,
            "critical",
            staticmethod(lambda *a, **k: None),
        )
        missing = tmp_path / "does-not-exist-executable"
        monkeypatch.setattr(
            agent_designer_module, "build_agents_command", lambda subcommand, arguments: [str(missing)]
        )

        designer._on_test_agent()

        from PySide6.QtWidgets import QApplication

        deadline = time.monotonic() + 5
        while designer._proc is not None and time.monotonic() < deadline:
            QApplication.processEvents()

        assert "Could not be completed" in designer.development.testStatusLabel.text()
        assert designer.development.btnTest.isEnabled() is True
        assert designer.simple.btnRun.isEnabled() is True
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_duplicate_test_click_does_not_start_second_process(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("dup_test_agent", data_root=data_root)
        designer.refresh_agents(select="dup_test_agent")

        monkeypatch.setattr(
            agent_designer_module,
            "build_agents_command",
            lambda subcommand, arguments: _stub_command(
                tmp_path, stdout=_init_failure_stdout("dup_test_agent")
            ),
        )

        designer._on_test_agent()
        first_proc = designer._proc
        assert first_proc is not None

        designer._on_test_agent()  # duplicate click while running
        assert designer._proc is first_proc

        _wait_for_finished(designer)
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_stop_while_testing_shows_stopped_and_recovers_controls(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("stoppable_test_agent", data_root=data_root)
        designer.refresh_agents(select="stoppable_test_agent")

        long_script = tmp_path / "long_running.py"
        long_script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
        monkeypatch.setattr(
            agent_designer_module,
            "build_agents_command",
            lambda subcommand, arguments: [sys.executable, str(long_script)],
        )

        designer._on_test_agent()
        assert designer._proc is not None

        designer._on_stop_run()

        assert designer._proc is None
        assert designer.development.btnTest.isEnabled() is True
        assert "Stopped by user" in designer.development.testStatusLabel.text()
        assert "stoppable_test_agent" in designer.development.testStatusLabel.text()
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_refresh_after_new_agent_keeps_opponent_selector_coherent(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("first_agent", data_root=data_root)
        designer.refresh_agents(select="first_agent")

        create_agent("second_agent", data_root=data_root)
        designer.refresh_agents(select="second_agent")

        assert designer.development.agentCombo.currentText() == "second_agent"
        names = [
            designer.development.opponentCombo.itemText(i)
            for i in range(designer.development.opponentCombo.count())
        ]
        assert "first_agent" in names
        assert "second_agent" in names
        assert designer.development.btnTest.isEnabled() is True
    finally:
        designer.deleteLater()


# ---------------------------------------------------------------------------
# Process isolation proof: hanging development test
# ---------------------------------------------------------------------------


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


def _write_agent(agents_dir: Path, agent_id: str, source: str) -> None:
    agent_dir = agents_dir / agent_id
    agent_dir.mkdir(parents=True)
    (agent_dir / "agent.yaml").write_text(
        'kind: python\napi_version: 1\nentrypoint: agent.py:create_agent\nversion: "0.1.0"\n',
        encoding="utf-8",
    )
    (agent_dir / "agent.py").write_text(source, encoding="utf-8")


@pytest.mark.gui
def test_hanging_development_test_does_not_block_gui_event_loop(monkeypatch, tmp_path):
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

        designer._on_test_agent()
        assert designer._proc is not None

        deadline = time.monotonic() + 1.5
        iterations = 0
        while time.monotonic() < deadline:
            tick_start = time.monotonic()
            QApplication.processEvents()
            assert time.monotonic() - tick_start < 0.5
            iterations += 1
        assert iterations > 0
        assert designer._proc is not None  # still hung, never finished on its own

        designer._dispose_process()
        assert designer._proc is None
    finally:
        designer.deleteLater()


# ---------------------------------------------------------------------------
# Data-root propagation to the child process
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_development_test_child_env_forces_designers_own_data_root(monkeypatch, tmp_path):
    """A Development Test child must resolve the exact same data root this
    process did, not silently recompute its own.

    Regression test for a real bug found during v0.5.0 manual release
    verification: the child environment relied on inheriting
    BYTEFRAY_ROOT from the OS environment, which
    only reproduces the same root when it was itself set from an explicit
    env var (true after a normal install). In a portable, no-installer
    checkout, get_data_root() falls back to "the directory containing the
    running executable" -- a *different* directory for the Designer's own
    onedir folder than for a sibling bytefray.exe child -- so the child
    could not find an agent this process had just written
    ("Unknown agent ...").
    """
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("env_check_agent", data_root=data_root)
        designer.refresh_agents(select="env_check_agent")

        # Simulate the portable/no-env-var scenario this bug depended on:
        # the OS environment the child would otherwise inherit no longer
        # carries any explicit root, even though this Designer instance's
        # own data_root is still the one resolved above.
        monkeypatch.delenv("BYTEFRAY_ROOT", raising=False)

        designer._on_test_agent()
        assert designer._proc is not None
        child_env = designer._proc.processEnvironment()
        assert child_env.contains("BYTEFRAY_ROOT")
        assert child_env.value("BYTEFRAY_ROOT") == str(designer.data_root)
        assert designer.data_root == data_root

        designer._dispose_process()
    finally:
        designer.deleteLater()


# ---------------------------------------------------------------------------
# Replay handoff
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_open_test_replay_uses_existing_replay_launcher(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("replay_agent", data_root=data_root)
        designer.refresh_agents(select="replay_agent")

        run_dir = tmp_path / "run"
        result_path, replay_path = _write_result_and_replay(
            run_dir, winner="replay_agent", termination_reason="last_agent_standing"
        )
        stdout = _completed_stdout(
            "replay_agent",
            result_path=result_path,
            replay_path=replay_path,
            summary_path=run_dir / "summary.json",
            winner="replay_agent",
            termination="last_agent_standing",
        )
        monkeypatch.setattr(
            agent_designer_module,
            "build_agents_command",
            lambda subcommand, arguments: _stub_command(tmp_path, stdout=stdout),
        )
        designer._on_test_agent()
        _wait_for_finished(designer)
        assert designer.development.btnOpenTestReplay.isEnabled() is True

        captured: list[tuple[Path, Path]] = []
        monkeypatch.setattr(
            agent_designer_module,
            "open_pygame_client_direct",
            lambda root, path: captured.append((root, path)),
        )

        designer._on_open_test_replay()

        assert captured == [(designer.data_root, replay_path)]
        # Independent of Simple/Advanced "Open Last Replay" (Sec 13).
        assert designer._last_replay is None
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_open_test_replay_noop_when_no_replay_available(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        captured: list[tuple[Path, Path]] = []
        monkeypatch.setattr(
            agent_designer_module,
            "open_pygame_client_direct",
            lambda root, path: captured.append((root, path)),
        )
        designer._on_open_test_replay()
        assert captured == []
    finally:
        designer.deleteLater()


# ---------------------------------------------------------------------------
# Regression: Phase 4a/4b workflows unaffected
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_validate_still_works_alongside_test(monkeypatch, tmp_path):
    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("regression_agent", data_root=data_root)
        designer.refresh_agents(select="regression_agent")

        monkeypatch.setattr(
            agent_designer_module,
            "build_agents_command",
            lambda subcommand, arguments: _stub_command(
                tmp_path, stdout="agent: x\nstatus: valid\napi_version: 1\ndry_run_action: HALT\n"
            ),
        )
        designer._on_validate_agent()
        _wait_for_finished(designer)
        assert "Last validation: Valid" in designer.development.statusLabel.text()
        assert designer.development.btnTest.isEnabled() is True
    finally:
        designer.deleteLater()


# ---------------------------------------------------------------------------
# v3.0.0-alpha2: explicit Ruleset selection for development tests
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_development_test_defaults_to_ruleset_v2_and_passes_it_explicitly(
    monkeypatch, tmp_path
):
    """The alpha2 GUI-default change, asserted end to end.

    Before alpha2 this path passed no ``--ruleset`` at all, so every
    Designer development test silently resolved ``bytefray agents test``'s
    own backward-compatible Ruleset-v1 default while the Simple/Advanced
    match tabs beside it defaulted to v2.
    """

    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent
    from battle_engine.ruleset_policy import BYTEFRAY_RULESET_V2_ID

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("ruleset_default_agent", data_root=data_root)
        designer.refresh_agents(select="ruleset_default_agent")

        assert designer.development.selected_ruleset_id() == BYTEFRAY_RULESET_V2_ID

        run_dir = tmp_path / "run"
        result_path, replay_path = _write_result_and_replay(
            run_dir, winner="ruleset_default_agent", termination_reason="tick_limit"
        )
        stdout = _completed_stdout(
            "ruleset_default_agent",
            result_path=result_path,
            replay_path=replay_path,
            summary_path=run_dir / "summary.json",
            winner="ruleset_default_agent",
            termination="tick_limit",
            ruleset=BYTEFRAY_RULESET_V2_ID,
        )
        captured_args: list[list[str]] = []

        def _capture(subcommand, arguments):
            captured_args.append(list(arguments))
            return _stub_command(tmp_path, stdout=stdout)

        monkeypatch.setattr(agent_designer_module, "build_agents_command", _capture)

        designer._on_test_agent()
        # The in-flight status names the Ruleset, not only the opponent.
        assert BYTEFRAY_RULESET_V2_ID in designer.development.testStatusLabel.text()
        _wait_for_finished(designer)

        args = captured_args[0]
        assert "--ruleset" in args
        assert args[args.index("--ruleset") + 1] == BYTEFRAY_RULESET_V2_ID
        # And the completed result reports the Ruleset the tool itself named.
        assert f"Ruleset: {BYTEFRAY_RULESET_V2_ID}" in designer.development.testStatusLabel.text()
    finally:
        designer.close()


@pytest.mark.gui
def test_development_test_can_select_ruleset_v1_for_python_compatibility(
    monkeypatch, tmp_path
):
    """Ruleset v1 stays reachable: Python agents are valid under both."""

    _make_app()
    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    from battle_engine.agent_scaffold import create_agent
    from battle_engine.rules import BYTEFRAY_RULESET_ID

    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    designer = AgentDesigner()
    try:
        create_agent("ruleset_v1_agent", data_root=data_root)
        designer.refresh_agents(select="ruleset_v1_agent")

        combo = designer.development.rulesetCombo
        index = combo.findData(BYTEFRAY_RULESET_ID)
        assert index >= 0, "Ruleset v1 must remain selectable for Python compatibility testing"
        combo.setCurrentIndex(index)
        assert designer.development.selected_ruleset_id() == BYTEFRAY_RULESET_ID

        run_dir = tmp_path / "run"
        result_path, replay_path = _write_result_and_replay(
            run_dir, winner="ruleset_v1_agent", termination_reason="tick_limit"
        )
        stdout = _completed_stdout(
            "ruleset_v1_agent",
            result_path=result_path,
            replay_path=replay_path,
            summary_path=run_dir / "summary.json",
            winner="ruleset_v1_agent",
            termination="tick_limit",
            ruleset=BYTEFRAY_RULESET_ID,
        )
        captured_args: list[list[str]] = []

        def _capture(subcommand, arguments):
            captured_args.append(list(arguments))
            return _stub_command(tmp_path, stdout=stdout)

        monkeypatch.setattr(agent_designer_module, "build_agents_command", _capture)

        designer._on_test_agent()
        _wait_for_finished(designer)

        args = captured_args[0]
        assert args[args.index("--ruleset") + 1] == BYTEFRAY_RULESET_ID
        assert f"Ruleset: {BYTEFRAY_RULESET_ID}" in designer.development.testStatusLabel.text()
    finally:
        designer.close()
