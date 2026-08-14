"""GUI regression coverage for the v1.1 Designer "Evaluation History" browser.

Covers: ``EvaluationHistoryDialog`` (empty-history messaging, list population,
selection-driven detail rendering including a malformed sibling, deep
``Verify`` toggling, cell drill-down button enablement and its two reused
signals), ``RevisionBrowserDialog`` (role-scoped manifest/verification/
current-source-drift text), the "Compare With…" flow
(``EvaluationPickerDialog`` + ``EvaluationComparisonDialog``), and
``AgentDesigner`` wiring (the Tools-menu action opens the dialog against the
Designer's own ``battle_root`` and reuses the exact same "Test in Agent
Lab"/"Open Replay" handlers ``EvaluationResultsDialog`` already uses).

Marked ``gui`` like the existing Designer tests: excluded from the default
headless run, exercised by the dedicated display-backed workflow.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

NOP_ACTION = "AgentAction(ActionKind.NOP)"


def _make_app():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _write_python_agent(root: Path, name: str, action: str = NOP_ACTION) -> None:
    directory = root / "agents" / name
    if (directory / "agent.py").is_file():
        return  # idempotent: callers may write the same shared agent twice
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text(
        json.dumps(
            {"kind": "python", "api_version": 1, "entrypoint": "agent.py:create_agent", "version": "1.0"}
        ),
        encoding="utf-8",
    )
    (directory / "agent.py").write_text(
        f"""
from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, context): pass
    def act(self, observation): return {action}
def create_agent(): return Agent()
""",
        encoding="utf-8",
    )


def _run_real_evaluation(tmp_path: Path, *, output_name: str = "eval-out", baseline: bool = True, **overrides) -> Path:
    from battle_engine.agent_evaluation import EvaluationRequest, EvaluationService

    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    if baseline:
        _write_python_agent(tmp_path, "baseline")

    defaults = {
        "candidate_id": "candidate",
        "baseline_id": "baseline" if baseline else None,
        "opponent_ids": ("opponent",),
        "seeds": (1,),
        "output_dir": tmp_path / "runs" / "evaluations" / output_name,
        "ticks": 12,
        "data_root": tmp_path,
        "both_orientations": False,
    }
    defaults.update(overrides)
    result = EvaluationService().run(EvaluationRequest(**defaults))
    return result.state_path


class _NullSignal:
    def connect(self, *_a, **_k):
        pass


# ---------------------------------------------------------------------------
# EvaluationHistoryDialog
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_history_dialog_shows_friendly_message_when_no_evaluations(tmp_path):
    _make_app()
    from app.views.evaluation_history import EvaluationHistoryDialog

    dialog = EvaluationHistoryDialog(tmp_path)
    try:
        assert dialog.list.count() == 0
        assert "No evaluations found" in dialog.detailText.toPlainText()
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_history_dialog_lists_and_renders_selected_evaluation(tmp_path):
    _make_app()
    from app.views.evaluation_history import EvaluationHistoryDialog

    _run_real_evaluation(tmp_path)

    dialog = EvaluationHistoryDialog(tmp_path)
    try:
        assert dialog.list.count() == 1
        dialog.list.setCurrentRow(0)
        text = dialog.detailText.toPlainText()
        assert "candidate: candidate" in text
        assert "baseline: baseline" in text
        assert dialog.cellsList.count() > 0
        assert dialog.revisionButton.isEnabled()
        assert dialog.compareButton.isEnabled()
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_history_dialog_verify_checkbox_reruns_deep_verification(tmp_path):
    _make_app()
    from app.views.evaluation_history import EvaluationHistoryDialog

    _run_real_evaluation(tmp_path, baseline=False)

    dialog = EvaluationHistoryDialog(tmp_path)
    try:
        dialog.list.setCurrentRow(0)
        assert "verified:" not in dialog.detailText.toPlainText()
        assert dialog.verifyStatusLabel.text() == ""

        dialog.verifyCheck.setChecked(True)
        text = dialog.detailText.toPlainText()
        assert "verified: True" in text
        # Regression for the interactive-qualification finding: the
        # confirmation must also be surfaced somewhere always-visible, not
        # only as the last line of a long, scrollable detail block.
        assert "PASSED" in dialog.verifyStatusLabel.text()

        dialog.verifyCheck.setChecked(False)
        assert dialog.verifyStatusLabel.text() == ""
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_history_dialog_list_rows_have_full_text_tooltip(tmp_path):
    """Regression for an interactive-qualification finding: a row's
    single-line label (id + schema + candidate + baseline + created +
    lifecycle + health + cell count) routinely runs wider than the list
    column at the default window size and gets visually truncated -- the
    tooltip must always carry the complete, untruncated text."""

    _make_app()
    from app.views.evaluation_history import EvaluationHistoryDialog

    _run_real_evaluation(tmp_path, baseline=False)

    dialog = EvaluationHistoryDialog(tmp_path)
    try:
        item = dialog.list.item(0)
        assert item.toolTip() == item.text()
        assert item.toolTip() != ""
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_history_dialog_malformed_sibling_reports_diagnostic_not_crash(tmp_path):
    _make_app()
    from app.views.evaluation_history import EvaluationHistoryDialog

    bad_dir = tmp_path / "runs" / "evaluations" / "bad-eval"
    bad_dir.mkdir(parents=True)
    (bad_dir / "evaluation.json").write_text("not json {{{", encoding="utf-8")

    dialog = EvaluationHistoryDialog(tmp_path)
    try:
        assert dialog.list.count() == 1
        dialog.list.setCurrentRow(0)
        text = dialog.detailText.toPlainText()
        assert "could not be read" in text
        assert dialog.cellsList.count() == 0
        assert not dialog.revisionButton.isEnabled()
        assert not dialog.compareButton.isEnabled()
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_history_dialog_cell_selection_enables_drilldown_and_emits_signals(tmp_path):
    _make_app()
    from app.views.evaluation_history import EvaluationHistoryDialog

    _run_real_evaluation(tmp_path, baseline=False)

    dialog = EvaluationHistoryDialog(tmp_path)
    try:
        dialog.list.setCurrentRow(0)
        assert not dialog.testAgentLabButton.isEnabled()
        assert not dialog.openReplayButton.isEnabled()

        dialog.cellsList.setCurrentRow(0)
        assert dialog.testAgentLabButton.isEnabled()
        assert dialog.openReplayButton.isEnabled()

        lab_calls = []
        replay_calls = []
        dialog.testInAgentLabRequested.connect(lambda s, o, seed: lab_calls.append((s, o, seed)))
        dialog.openReplayRequested.connect(lambda path: replay_calls.append(path))

        dialog.testAgentLabButton.click()
        dialog.openReplayButton.click()

        assert lab_calls == [("candidate", "opponent", 1)]
        assert len(replay_calls) == 1
        assert replay_calls[0].name == "replay.jsonl"
        assert replay_calls[0].is_file()
    finally:
        dialog.deleteLater()


# ---------------------------------------------------------------------------
# Revision browser
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_revision_browser_dialog_shows_manifest_and_live_source_status(tmp_path):
    _make_app()
    from app.services.evaluation_history_workflows import load_evaluation_summary
    from app.views.evaluation_history import RevisionBrowserDialog

    state_path = _run_real_evaluation(tmp_path, baseline=False)
    summary, _ = load_evaluation_summary(state_path)
    revision_id = summary.candidate_agent_revision_id.value
    assert revision_id

    dialog = RevisionBrowserDialog(
        [("candidate: candidate", "candidate", revision_id)], data_root=tmp_path
    )
    try:
        text = dialog.detailText.toPlainText()
        assert revision_id in text
        assert "MATCHES the agent's current on-disk source" in text
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_history_dialog_show_revision_opens_browser_with_expected_roles(monkeypatch, tmp_path):
    _make_app()
    import app.views.evaluation_history as evaluation_history_view
    from app.views.evaluation_history import EvaluationHistoryDialog

    _run_real_evaluation(tmp_path, baseline=True)

    dialog = EvaluationHistoryDialog(tmp_path)
    try:
        dialog.list.setCurrentRow(0)

        received = []

        class _RecordingRevisionDialog:
            def __init__(self, roles, *, data_root, parent=None):
                received.append((roles, data_root))

            def exec(self):
                return None

        monkeypatch.setattr(evaluation_history_view, "RevisionBrowserDialog", _RecordingRevisionDialog)
        dialog._on_show_revision()

        assert len(received) == 1
        roles, data_root = received[0]
        role_labels = {label for label, _agent_id, _revision_id in roles}
        assert "candidate: candidate" in role_labels
        assert "baseline: baseline" in role_labels
        assert "opponent: opponent" in role_labels
        assert data_root == tmp_path
    finally:
        dialog.deleteLater()


# ---------------------------------------------------------------------------
# Compare With…
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_evaluation_picker_dialog_excludes_unreadable_entries(tmp_path):
    """Regression for an interactive-qualification finding: an unreadable
    sibling always fails as a comparison target (safely -- ``compare_evaluations``
    raises ``DesignerValidationError``, caught and shown as a warning), but
    offering it in the picker at all is pointless friction. The main
    history list must still show it (Sec 13 of
    docs/specs/evaluation_history.md forbids hiding a malformed sibling from
    discovery) -- only this narrower "pick a comparison partner" picker
    excludes it."""

    _make_app()
    from app.services.evaluation_history_workflows import (
        discover_evaluation_listing,
        sorted_listing_entries,
    )
    from app.views.evaluation_history import EvaluationPickerDialog

    _run_real_evaluation(tmp_path, output_name="eval-good", baseline=False)
    bad_dir = tmp_path / "runs" / "evaluations" / "eval-bad"
    bad_dir.mkdir(parents=True)
    (bad_dir / "evaluation.json").write_text("not json {{{", encoding="utf-8")

    listing = discover_evaluation_listing(roots=(tmp_path / "runs" / "evaluations",))
    entries = sorted_listing_entries(listing)
    assert len(entries) == 2  # both are discovered

    picker = EvaluationPickerDialog(entries)
    try:
        assert picker.list.count() == 1  # only the readable one is offered
        assert "UNREADABLE" not in picker.list.item(0).text()
    finally:
        picker.deleteLater()


@pytest.mark.gui
def test_history_dialog_compare_flow_opens_comparison_with_picked_right_side(monkeypatch, tmp_path):
    _make_app()
    import app.views.evaluation_history as evaluation_history_view
    from app.views.evaluation_history import EvaluationHistoryDialog

    left_path = _run_real_evaluation(tmp_path, output_name="eval-left", baseline=False, seeds=(1,))
    right_path = _run_real_evaluation(tmp_path, output_name="eval-right", baseline=False, seeds=(2,))

    dialog = EvaluationHistoryDialog(tmp_path)
    try:
        # Select the left-side evaluation (list order is most-recent-first,
        # so "eval-left" is the second/older entry).
        from PySide6.QtCore import Qt

        target_row = None
        for row in range(dialog.list.count()):
            entry = dialog.list.item(row).data(Qt.UserRole)
            if entry.location.evaluation_json_path == left_path.resolve():
                target_row = row
        assert target_row is not None
        dialog.list.setCurrentRow(target_row)

        class _StubPicker:
            def __init__(self, entries, *, exclude=None, title="", parent=None):
                self._entries = entries
                self._exclude = exclude

            def exec(self):
                return 1

            def selected_path(self):
                return right_path.resolve()

        received = []

        class _RecordingComparisonDialog:
            def __init__(self, result, parent=None):
                received.append(result)

            def exec(self):
                return None

        monkeypatch.setattr(evaluation_history_view, "EvaluationPickerDialog", _StubPicker)
        monkeypatch.setattr(evaluation_history_view, "EvaluationComparisonDialog", _RecordingComparisonDialog)

        dialog._on_compare()

        assert len(received) == 1
        result = received[0]
        assert result.left.evaluation_id != result.right.evaluation_id
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_history_dialog_handles_evaluation_deleted_after_dialog_opened(tmp_path):
    """Section 10 error-handling requirement: an artifact that was present
    at discovery time but is gone by the time the user acts on it (deleted
    externally, or by a concurrent process) must degrade to a clear,
    in-place error -- never an uncaught exception, and never a stale/
    silently-reinterpreted result."""

    _make_app()
    from app.views.evaluation_history import EvaluationHistoryDialog

    path = _run_real_evaluation(tmp_path, baseline=False)

    dialog = EvaluationHistoryDialog(tmp_path)
    try:
        dialog.list.setCurrentRow(0)
        assert "candidate: candidate" in dialog.detailText.toPlainText()

        path.unlink()  # the artifact vanishes while the dialog is still open
        dialog.list.setCurrentRow(-1)
        dialog.list.setCurrentRow(0)  # re-select the now-missing artifact

        text = dialog.detailText.toPlainText()
        assert "Could not read this evaluation" in text
        assert dialog.cellsList.count() == 0
        assert not dialog.compareButton.isEnabled()

        # And attempting Compare With… against the now-vanished selection
        # must fail gracefully (a warning dialog is suppressed here by the
        # button already being disabled -- this asserts the underlying
        # service call itself doesn't raise uncaught).
        from app.services.designer_workflows import DesignerValidationError
        from app.services.evaluation_history_workflows import load_evaluation_summary

        with pytest.raises(DesignerValidationError):
            load_evaluation_summary(path)
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_evaluation_comparison_dialog_renders_rows_and_gaps(tmp_path):
    _make_app()
    from app.services.evaluation_history_workflows import compare_evaluations
    from app.views.evaluation_history import EvaluationComparisonDialog

    left_path = _run_real_evaluation(tmp_path, output_name="eval-left", baseline=False, seeds=(1,))
    result = compare_evaluations(left_path, left_path, verify=True, data_root=tmp_path)

    dialog = EvaluationComparisonDialog(result)
    try:
        assert dialog.rowsList.count() == len(result.comparison.rows)
        dialog.rowsList.setCurrentRow(0)
        assert "opponent:" in dialog.detailText.toPlainText()
    finally:
        dialog.deleteLater()


# ---------------------------------------------------------------------------
# AgentDesigner wiring
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_designer_evaluation_history_action_opens_dialog_against_battle_root(monkeypatch, tmp_path):
    _make_app()
    from app.agent_designer import AgentDesigner

    monkeypatch.setenv("BATTLE2_ROOT", str(tmp_path / "designer-data"))
    designer = AgentDesigner()
    try:
        received = {}

        class _RecordingHistoryDialog:
            def __init__(self, battle_root, parent=None):
                received["battle_root"] = battle_root
                received["parent"] = parent
                self.testInAgentLabRequested = _NullSignal()
                self.openReplayRequested = _NullSignal()

            def exec(self):
                return None

        monkeypatch.setattr("app.agent_designer.EvaluationHistoryDialog", _RecordingHistoryDialog)

        designer._on_evaluation_history()

        assert received["battle_root"] == designer.battle_root
        assert received["parent"] is designer
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_designer_evaluation_history_reuses_existing_drilldown_handlers(monkeypatch, tmp_path):
    """The History dialog's cell drill-down must connect to the exact same
    handlers ``EvaluationResultsDialog`` already uses -- one execution/
    replay-launch path, not a second one."""

    _make_app()
    from app.agent_designer import AgentDesigner

    monkeypatch.setenv("BATTLE2_ROOT", str(tmp_path / "designer-data"))
    designer = AgentDesigner()
    try:
        connected = {}

        class _RecordingSignal:
            def __init__(self, key):
                self._key = key

            def connect(self, handler):
                connected[self._key] = handler

        class _RecordingHistoryDialog:
            def __init__(self, battle_root, parent=None):
                self.testInAgentLabRequested = _RecordingSignal("lab")
                self.openReplayRequested = _RecordingSignal("replay")

            def exec(self):
                return None

        monkeypatch.setattr("app.agent_designer.EvaluationHistoryDialog", _RecordingHistoryDialog)

        designer._on_evaluation_history()

        assert connected["lab"] == designer._on_evaluation_test_in_agent_lab
        assert connected["replay"] == designer._on_evaluation_open_replay
    finally:
        designer.deleteLater()
