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
def test_history_dialog_cell_selection_enables_drilldown_and_emits_signals(
    monkeypatch, tmp_path
):
    _make_app()
    import app.views.evaluation_history as evaluation_history_view
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
        assert "currently installed agents" in dialog.testAgentLabButton.toolTip()
        assert "Historical agent source is not restored" in (
            dialog.testAgentLabButton.toolTip()
        )

        lab_calls = []
        replay_calls = []
        dialog.testInAgentLabRequested.connect(
            lambda s, o, seed, ticks, orientation: lab_calls.append(
                (s, o, seed, ticks, orientation)
            )
        )
        dialog.openReplayRequested.connect(lambda path: replay_calls.append(path))

        dialog.testAgentLabButton.click()
        dialog.openReplayButton.click()

        assert lab_calls == [("candidate", "opponent", 1, 12, "candidate_first")]
        assert len(replay_calls) == 1
        assert replay_calls[0].name == "replay.jsonl"
        assert replay_calls[0].is_file()

        restore_policy = []

        class _RecordingRevisionDialog:
            def __init__(
                self, roles, *, data_root, allow_restore=True, parent=None
            ):
                restore_policy.append(allow_restore)
                self.liveAgentFilesChanged = _NullSignal()

            def exec(self):
                return None

        monkeypatch.setattr(
            evaluation_history_view,
            "RevisionBrowserDialog",
            _RecordingRevisionDialog,
        )
        dialog._on_show_revision()
        assert restore_policy == [False]
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
            def __init__(
                self, roles, *, data_root, allow_restore=True, parent=None
            ):
                received.append((roles, data_root, allow_restore))
                self.liveAgentFilesChanged = _NullSignal()

            def exec(self):
                return None

        monkeypatch.setattr(evaluation_history_view, "RevisionBrowserDialog", _RecordingRevisionDialog)
        dialog._on_show_revision()

        assert len(received) == 1
        roles, data_root, allow_restore = received[0]
        role_labels = {label for label, _agent_id, _revision_id in roles}
        assert "candidate: candidate" in role_labels
        assert "baseline: baseline" in role_labels
        assert "opponent: opponent" in role_labels
        assert data_root == tmp_path
        assert allow_restore is True
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
                self.testInAgentLabRequested = _NullSignal()
                self.openReplayRequested = _NullSignal()

            def exec(self):
                return None

        monkeypatch.setattr(evaluation_history_view, "EvaluationPickerDialog", _StubPicker)
        monkeypatch.setattr(evaluation_history_view, "EvaluationComparisonDialog", _RecordingComparisonDialog)

        dialog._on_compare()

        assert len(received) == 1
        result = received[0]
        assert result.left.evaluation_id != result.right.evaluation_id
        assert result.left.location.evaluation_json_path == left_path.resolve()
        assert result.right.location.evaluation_json_path == right_path.resolve()
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


@pytest.mark.gui
def test_evaluation_comparison_dialog_row_drilldown_offers_both_sides(tmp_path):
    """A directly-comparable row (Sec 11 of the v1.3 task: "direct
    comparable match -> actions may be available") always resolves a real
    cell on both sides, so both are offered via the Side control, defaulting
    to the right side -- never an arbitrary, unlabeled pick.  The production
    default has two orientations sharing an occurrence index; each row must
    retain its own exact replay identity."""

    _make_app()
    from app.services.evaluation_history_workflows import compare_evaluations
    from app.views.evaluation_history import EvaluationComparisonDialog

    left_path = _run_real_evaluation(
        tmp_path,
        output_name="eval-left",
        baseline=False,
        seeds=(1,),
        both_orientations=True,
    )
    right_path = _run_real_evaluation(
        tmp_path,
        output_name="eval-right",
        baseline=False,
        seeds=(1,),
        both_orientations=True,
    )
    result = compare_evaluations(left_path, right_path, verify=False, data_root=tmp_path)
    assert len(result.comparison.rows) == 2
    assert result.left.location.directory != result.right.location.directory

    dialog = EvaluationComparisonDialog(result)
    try:
        assert not dialog.testAgentLabButton.isEnabled()
        assert not dialog.openReplayButton.isEnabled()

        assert any("orientation=candidate_first" in dialog.rowsList.item(i).text() for i in range(2))
        opponent_first_row = next(
            i
            for i in range(dialog.rowsList.count())
            if "orientation=opponent_first" in dialog.rowsList.item(i).text()
        )
        dialog.rowsList.setCurrentRow(opponent_first_row)
        assert dialog.sideCombo.count() == 2
        assert dialog.sideCombo.currentData() == "right"
        assert dialog.sideCombo.currentText() == "Right (comparison)"
        assert dialog.testAgentLabButton.isEnabled()
        assert dialog.openReplayButton.isEnabled()
        assert dialog._active_left_cell.orientation.value == "opponent_first"
        assert dialog._active_right_cell.orientation.value == "opponent_first"

        lab_calls = []
        replay_calls = []
        dialog.testInAgentLabRequested.connect(
            lambda s, o, seed, ticks, orientation: lab_calls.append(
                (s, o, seed, ticks, orientation)
            )
        )
        dialog.openReplayRequested.connect(lambda path: replay_calls.append(path))

        dialog.testAgentLabButton.click()
        dialog.openReplayButton.click()
        assert lab_calls == [("candidate", "opponent", 1, 12, "opponent_first")]
        assert len(replay_calls) == 1
        right_replay = (
            result.right.location.directory / dialog._active_right_cell.artifact_dir / "replay.jsonl"
        )
        assert replay_calls[0] == right_replay

        # Switching to the left side must retarget both actions, not just
        # relabel the combo -- the emitted replay path changes to the
        # left-side artifact directory.
        left_index = dialog.sideCombo.findData("left")
        assert left_index >= 0
        dialog.sideCombo.setCurrentIndex(left_index)
        assert dialog.sideCombo.currentText() == "Left (selected)"
        replay_calls.clear()
        dialog.openReplayButton.click()
        left_replay = (
            result.left.location.directory / dialog._active_left_cell.artifact_dir / "replay.jsonl"
        )
        assert replay_calls[0] == left_replay
        assert left_replay != right_replay
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_evaluation_comparison_dialog_unmatched_gap_offers_only_the_real_side(tmp_path):
    """An unmatched cell (Sec 11: "unmatched -> perhaps one side only")
    resolves exactly one real cell -- the Side control must never offer the
    side that has no match, and the resolved cell's own replay must be a
    real, existing file."""

    _make_app()
    from app.services.evaluation_history_workflows import compare_evaluations
    from app.views.evaluation_history import EvaluationComparisonDialog

    left_path = _run_real_evaluation(tmp_path, output_name="eval-left", baseline=False, seeds=(1,))
    right_path = _run_real_evaluation(tmp_path, output_name="eval-right", baseline=False, seeds=(2,))
    result = compare_evaluations(left_path, right_path, verify=False, data_root=tmp_path)
    assert not result.comparison.rows  # different seeds never align as one row
    assert result.comparison.unmatched_left
    assert result.comparison.unmatched_right

    dialog = EvaluationComparisonDialog(result)
    try:
        target_row = next(
            row
            for row in range(dialog.gapsList.count())
            if "UNMATCHED (left only)" in dialog.gapsList.item(row).text()
        )
        dialog.gapsList.setCurrentRow(target_row)

        assert dialog.sideCombo.count() == 1
        assert dialog.sideCombo.currentData() == "left"
        assert dialog.testAgentLabButton.isEnabled()

        replay_calls = []
        dialog.openReplayRequested.connect(lambda path: replay_calls.append(path))
        dialog.openReplayButton.click()
        assert len(replay_calls) == 1
        assert replay_calls[0].is_file()

        right_row = next(
            row
            for row in range(dialog.gapsList.count())
            if "UNMATCHED (right only)" in dialog.gapsList.item(row).text()
        )
        dialog.gapsList.setCurrentRow(right_row)
        assert dialog.sideCombo.count() == 1
        assert dialog.sideCombo.currentData() == "right"
        replay_calls.clear()
        dialog.openReplayButton.click()
        assert len(replay_calls) == 1
        assert replay_calls[0].is_file()
        assert replay_calls[0].is_relative_to(result.right.location.directory)
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_evaluation_comparison_dialog_changed_condition_requires_explicit_side(tmp_path):
    _make_app()
    from app.services.evaluation_history_workflows import compare_evaluations
    from app.views.evaluation_history import EvaluationComparisonDialog

    left_path = _run_real_evaluation(
        tmp_path,
        output_name="eval-short",
        baseline=False,
        ticks=10,
        both_orientations=False,
    )
    right_path = _run_real_evaluation(
        tmp_path,
        output_name="eval-long",
        baseline=False,
        ticks=25,
        both_orientations=False,
    )
    result = compare_evaluations(left_path, right_path, verify=False, data_root=tmp_path)
    assert len(result.comparison.changed_condition) == 1

    dialog = EvaluationComparisonDialog(result)
    try:
        changed_row = next(
            row
            for row in range(dialog.gapsList.count())
            if "CHANGED CONDITION" in dialog.gapsList.item(row).text()
        )
        dialog.gapsList.setCurrentRow(changed_row)

        assert dialog.sideCombo.count() == 3
        assert dialog.sideCombo.currentData() is None
        assert dialog.sideCombo.currentText() == "Choose side…"
        assert not dialog.testAgentLabButton.isEnabled()
        assert not dialog.openReplayButton.isEnabled()
        assert "currently installed agents" in dialog.testAgentLabButton.toolTip()
        assert "Historical agent source is not restored" in (
            dialog.testAgentLabButton.toolTip()
        )
        assert "effective conditions, rules, methodology, or opponent revision differ" in (
            dialog.detailText.toPlainText()
        )

        lab_calls = []
        replay_calls = []
        dialog.testInAgentLabRequested.connect(
            lambda s, o, seed, ticks, orientation: lab_calls.append(
                (s, o, seed, ticks, orientation)
            )
        )
        dialog.openReplayRequested.connect(replay_calls.append)

        dialog.sideCombo.setCurrentIndex(dialog.sideCombo.findData("left"))
        dialog.testAgentLabButton.click()
        dialog.openReplayButton.click()
        assert lab_calls[-1] == ("candidate", "opponent", 1, 10, "candidate_first")
        assert replay_calls[-1].is_relative_to(result.left.location.directory)

        dialog.sideCombo.setCurrentIndex(dialog.sideCombo.findData("right"))
        dialog.testAgentLabButton.click()
        dialog.openReplayButton.click()
        assert lab_calls[-1] == ("candidate", "opponent", 1, 25, "candidate_first")
        assert replay_calls[-1].is_relative_to(result.right.location.directory)
        assert replay_calls[-1] != replay_calls[-2]
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_evaluation_comparison_dialog_ambiguous_group_never_enables_actions(tmp_path):
    """Sec 11 of the v1.3 task, verbatim: "ambiguous duplicate group -> do
    not guess." A real both-orientation comparison under changed ticks
    produces an ambiguous group; selecting it must clear a previously active
    cell and disable both drill-down actions."""

    _make_app()
    from app.services.evaluation_history_workflows import compare_evaluations
    from app.views.evaluation_history import EvaluationComparisonDialog

    left_path = _run_real_evaluation(
        tmp_path,
        output_name="eval-short",
        baseline=False,
        ticks=10,
        both_orientations=True,
    )
    right_path = _run_real_evaluation(
        tmp_path,
        output_name="eval-long",
        baseline=False,
        ticks=25,
        both_orientations=True,
    )
    result = compare_evaluations(left_path, right_path, verify=False, data_root=tmp_path)
    assert result.comparison.ambiguous_duplicate_groups

    dialog = EvaluationComparisonDialog(result)
    try:
        dialog._set_active_cells(
            result.left.cells[0],
            result.right.cells[0],
        )
        assert dialog.testAgentLabButton.isEnabled()
        ambiguous_row = next(
            row
            for row in range(dialog.gapsList.count())
            if "AMBIGUOUS GROUP" in dialog.gapsList.item(row).text()
        )
        dialog.gapsList.setCurrentRow(ambiguous_row)

        assert dialog.sideCombo.count() == 0
        assert not dialog.testAgentLabButton.isEnabled()
        assert not dialog.openReplayButton.isEnabled()
        detail = dialog.detailText.toPlainText()
        assert "does not guess" in detail
        assert "evaluations show <id> --json" in detail
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_history_dialog_compare_forwards_comparison_drilldown_signals(monkeypatch, tmp_path):
    """The comparison dialog's own drill-down signals must reach the exact
    same shared handlers the per-cell drill-down already uses -- forwarded
    through ``EvaluationHistoryDialog``'s already-connected signals, not a
    second, independent wiring path."""

    _make_app()
    import app.views.evaluation_history as evaluation_history_view
    from app.views.evaluation_history import EvaluationHistoryDialog

    left_path = _run_real_evaluation(tmp_path, output_name="eval-left", baseline=False, seeds=(1,))
    right_path = _run_real_evaluation(tmp_path, output_name="eval-right", baseline=False, seeds=(2,))

    dialog = EvaluationHistoryDialog(tmp_path)
    try:
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
                pass

            def exec(self):
                return 1

            def selected_path(self):
                return right_path.resolve()

        lab_calls = []
        replay_calls = []
        dialog.testInAgentLabRequested.connect(
            lambda s, o, seed, ticks, orientation: lab_calls.append(
                (s, o, seed, ticks, orientation)
            )
        )
        dialog.openReplayRequested.connect(replay_calls.append)
        emitted_replay = tmp_path / "forwarded-replay.jsonl"

        def _emit_real_dialog_signals(comparison_dialog):
            comparison_dialog.testInAgentLabRequested.emit(
                "candidate", "opponent", 1, 12, "candidate_first"
            )
            comparison_dialog.openReplayRequested.emit(emitted_replay)
            return 0

        monkeypatch.setattr(evaluation_history_view, "EvaluationPickerDialog", _StubPicker)
        monkeypatch.setattr(
            evaluation_history_view.EvaluationComparisonDialog,
            "exec",
            _emit_real_dialog_signals,
        )

        dialog._on_compare()

        assert lab_calls == [("candidate", "opponent", 1, 12, "candidate_first")]
        assert replay_calls == [emitted_replay]
        assert dialog._allow_restore is False
    finally:
        dialog.deleteLater()


# ---------------------------------------------------------------------------
# Revision restore (v1.3)
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_revision_browser_dialog_restore_button_enabled_only_for_verified_revision(tmp_path):
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
        assert dialog.restoreButton.isEnabled()
        assert dialog.restoreButton.text() == "Restore Files…"
    finally:
        dialog.deleteLater()

    busy_dialog = RevisionBrowserDialog(
        [("candidate: candidate", "candidate", revision_id)],
        data_root=tmp_path,
        allow_restore=False,
    )
    try:
        assert not busy_dialog.restoreButton.isEnabled()
        assert "Restore Files is disabled" in busy_dialog.restoreButton.toolTip()
        assert "Close and reopen History" in busy_dialog.restoreButton.toolTip()
    finally:
        busy_dialog.deleteLater()


@pytest.mark.gui
def test_revision_browser_dialog_restore_button_disabled_with_no_recorded_revision(tmp_path):
    _make_app()
    from app.views.evaluation_history import RevisionBrowserDialog

    dialog = RevisionBrowserDialog([("candidate: candidate", "candidate", "")], data_root=tmp_path)
    try:
        assert not dialog.restoreButton.isEnabled()
        assert "No revision id recorded" in dialog.detailText.toPlainText()
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_restore_revision_dialog_default_target_matches_cli_restore_convention(tmp_path):
    """``bytefray agents revisions restore`` defaults to
    ``<data_root>/agent_revisions_restored/<revision_id>/`` -- the Designer
    must offer the identical default so restore is never less safe (or
    differently scoped) than the CLI (Sec 13 of the v1.3 task)."""

    _make_app()
    from app.services.evaluation_history_workflows import (
        load_agent_revision,
        load_evaluation_summary,
    )
    from app.views.evaluation_history import RestoreRevisionDialog

    state_path = _run_real_evaluation(tmp_path, baseline=False)
    summary, _ = load_evaluation_summary(state_path)
    revision_id = summary.candidate_agent_revision_id.value
    presentation = load_agent_revision(revision_id, data_root=tmp_path, current_agent_id="candidate")

    dialog = RestoreRevisionDialog(presentation, agent_id="candidate", data_root=tmp_path)
    try:
        expected = str(tmp_path / "agent_revisions_restored" / revision_id)
        assert dialog.targetEdit.text() == expected
        assert not dialog.forceCheck.isChecked()
        assert "unrelated files remain" in dialog.forceCheck.text()
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_restore_revision_dialog_writes_files_and_round_trips(tmp_path):
    _make_app()
    from battle_engine.agent_revisions import agent_revision_fingerprint, agent_revision_id

    from app.services.evaluation_history_workflows import (
        load_agent_revision,
        load_evaluation_summary,
    )
    from app.views.evaluation_history import RestoreRevisionDialog

    state_path = _run_real_evaluation(tmp_path, baseline=False)
    summary, _ = load_evaluation_summary(state_path)
    revision_id = summary.candidate_agent_revision_id.value
    presentation = load_agent_revision(revision_id, data_root=tmp_path, current_agent_id="candidate")

    dialog = RestoreRevisionDialog(presentation, agent_id="candidate", data_root=tmp_path)
    try:
        target = tmp_path / "restored-target"
        dialog.targetEdit.setText(str(target))
        dialog._on_restore_clicked()

        assert dialog.restored_target == target
        assert (target / "agent.py").is_file()
        restored_fingerprint = agent_revision_fingerprint(target)
        assert agent_revision_id(restored_fingerprint) == revision_id
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_restore_revision_dialog_refuses_non_empty_target_without_force(monkeypatch, tmp_path):
    """The GUI must not be less safe than the CLI: a non-empty target
    directory is refused, with nothing written, exactly like
    ``restore_revision`` itself already refuses (never a GUI-only
    reimplementation of this check)."""

    _make_app()
    import app.views.evaluation_history as evaluation_history_view
    from app.services.evaluation_history_workflows import (
        load_agent_revision,
        load_evaluation_summary,
    )
    from app.views.evaluation_history import RestoreRevisionDialog

    state_path = _run_real_evaluation(tmp_path, baseline=False)
    summary, _ = load_evaluation_summary(state_path)
    revision_id = summary.candidate_agent_revision_id.value
    presentation = load_agent_revision(revision_id, data_root=tmp_path, current_agent_id="candidate")

    dialog = RestoreRevisionDialog(presentation, agent_id="candidate", data_root=tmp_path)
    try:
        target = tmp_path / "occupied"
        target.mkdir()
        (target / "existing.txt").write_text("keep me", encoding="utf-8")
        dialog.targetEdit.setText(str(target))

        errors = []
        monkeypatch.setattr(
            evaluation_history_view.QMessageBox,
            "critical",
            staticmethod(lambda *a, **k: errors.append(a) or None),
        )

        dialog._on_restore_clicked()

        assert dialog.restored_target is None
        assert len(errors) == 1
        assert (target / "existing.txt").is_file()  # untouched
        assert not (target / "agent.py").exists()  # nothing written
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_restore_revision_dialog_presents_unwritable_target_error(monkeypatch, tmp_path):
    _make_app()
    import app.views.evaluation_history as evaluation_history_view
    from app.services.evaluation_history_workflows import (
        load_agent_revision,
        load_evaluation_summary,
    )
    from app.views.evaluation_history import RestoreRevisionDialog

    state_path = _run_real_evaluation(tmp_path, baseline=False)
    summary, _ = load_evaluation_summary(state_path)
    revision_id = summary.candidate_agent_revision_id.value
    presentation = load_agent_revision(
        revision_id, data_root=tmp_path, current_agent_id="candidate"
    )
    dialog = RestoreRevisionDialog(
        presentation, agent_id="candidate", data_root=tmp_path
    )
    try:
        dialog.targetEdit.setText(str(tmp_path / "outside-live-catalog"))
        errors = []

        def _raise_permission_error(*args, **kwargs):
            raise PermissionError("target is not writable")

        monkeypatch.setattr(
            evaluation_history_view,
            "restore_revision",
            _raise_permission_error,
        )
        monkeypatch.setattr(
            evaluation_history_view.QMessageBox,
            "critical",
            staticmethod(lambda *args, **kwargs: errors.append(args[2]) or None),
        )

        dialog._on_restore_clicked()
        assert dialog.restored_target is None
        assert dialog.affected_live_agent_id is None
        assert errors == ["target is not writable"]
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_restore_revision_dialog_live_target_requires_confirmation_and_preserves_unrelated_files(
    monkeypatch, tmp_path
):
    """Writing into live source is possible only through an explicit path,
    force opt-in, and a second warning.  The warning must describe the real
    merge semantics: matching paths are overwritten, unrelated paths stay,
    and no backup/transaction is implied."""

    _make_app()
    import app.views.evaluation_history as evaluation_history_view
    from app.services.evaluation_history_workflows import (
        load_agent_revision,
        load_evaluation_summary,
    )
    from app.views.evaluation_history import RestoreRevisionDialog

    state_path = _run_real_evaluation(tmp_path, baseline=False)
    summary, _ = load_evaluation_summary(state_path)
    revision_id = summary.candidate_agent_revision_id.value
    live_target = tmp_path / "agents" / "candidate"
    original_source = (live_target / "agent.py").read_bytes()
    (live_target / "agent.py").write_text("# changed live source\n", encoding="utf-8")
    unrelated = live_target / "keep-me.txt"
    unrelated.write_text("unrelated", encoding="utf-8")
    presentation = load_agent_revision(
        revision_id, data_root=tmp_path, current_agent_id="candidate"
    )

    dialog = RestoreRevisionDialog(
        presentation, agent_id="candidate", data_root=tmp_path
    )
    try:
        dialog.targetEdit.setText(str(live_target))
        dialog.forceCheck.setChecked(True)
        prompts = []
        answers = iter(
            [
                evaluation_history_view.QMessageBox.StandardButton.Cancel,
                evaluation_history_view.QMessageBox.StandardButton.Yes,
            ]
        )

        def _question(*args, **kwargs):
            prompts.append(args[2])
            return next(answers)

        monkeypatch.setattr(
            evaluation_history_view.QMessageBox,
            "question",
            staticmethod(_question),
        )

        dialog._on_restore_clicked()
        assert dialog.restored_target is None
        assert (live_target / "agent.py").read_text(encoding="utf-8") == "# changed live source\n"

        dialog._on_restore_clicked()
        assert dialog.restored_target == live_target
        assert dialog.affected_live_agent_id == "candidate"
        assert (live_target / "agent.py").read_bytes() == original_source
        assert unrelated.read_text(encoding="utf-8") == "unrelated"
        assert len(prompts) == 2
        assert "unrelated files are NOT removed" in prompts[-1]
        assert "no backup is created" in prompts[-1]
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_restore_revision_dialog_identifies_any_path_inside_live_agent(monkeypatch, tmp_path):
    _make_app()
    from app.views.evaluation_history import _affected_live_agent_id

    assert _affected_live_agent_id(tmp_path, tmp_path / "agents") == ""
    assert (
        _affected_live_agent_id(
            tmp_path, tmp_path / "agents" / "candidate" / "nested" / "target"
        )
        == "candidate"
    )
    assert _affected_live_agent_id(tmp_path, tmp_path / "restored-copy") is None

    # A catalog child may be a symlink/junction to a different catalog
    # child.  Exercise that disagreement without requiring Windows symlink
    # privileges: the helper must conservatively report catalog-wide impact
    # rather than invalidate only the lexical alias.
    lexical_root = Path(os.path.abspath(tmp_path / "agents"))
    lexical_target = Path(os.path.abspath(tmp_path / "agents" / "alias"))
    resolved_root = tmp_path / "resolved-agents"
    real_resolve = Path.resolve

    def _resolve(path: Path, strict: bool = False) -> Path:
        if path == lexical_root:
            return resolved_root
        if path == lexical_target:
            return resolved_root / "actual"
        return real_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", _resolve)
    assert _affected_live_agent_id(tmp_path, lexical_target) == ""


@pytest.mark.gui
def test_revision_browser_emits_live_catalog_change_after_success(monkeypatch, tmp_path):
    _make_app()
    import app.views.evaluation_history as evaluation_history_view
    from app.services.evaluation_history_workflows import (
        load_evaluation_summary,
    )
    from app.views.evaluation_history import RevisionBrowserDialog

    state_path = _run_real_evaluation(tmp_path, baseline=False)
    summary, _ = load_evaluation_summary(state_path)
    revision_id = summary.candidate_agent_revision_id.value

    class _SuccessfulRestore:
        def __init__(self, *args, **kwargs):
            self.restored_target = tmp_path / "agents" / "candidate"
            self.affected_live_agent_id = "candidate"

        def exec(self):
            return 1

    monkeypatch.setattr(
        evaluation_history_view, "RestoreRevisionDialog", _SuccessfulRestore
    )
    monkeypatch.setattr(
        evaluation_history_view.QMessageBox, "exec", lambda self: 0
    )

    dialog = RevisionBrowserDialog(
        [("candidate: candidate", "candidate", revision_id)], data_root=tmp_path
    )
    try:
        changed = []
        dialog.liveAgentFilesChanged.connect(changed.append)
        dialog._on_restore()
        assert changed == ["candidate"]
    finally:
        dialog.deleteLater()


# ---------------------------------------------------------------------------
# AgentDesigner wiring
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_designer_evaluation_history_action_opens_dialog_against_battle_root(monkeypatch, tmp_path):
    _make_app()
    from app.agent_designer import AgentDesigner

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path / "designer-data"))
    designer = AgentDesigner()
    try:
        received = {}

        class _RecordingHistoryDialog:
            def __init__(self, battle_root, *, allow_restore=True, parent=None):
                received["battle_root"] = battle_root
                received["allow_restore"] = allow_restore
                received["parent"] = parent
                self.testInAgentLabRequested = _NullSignal()
                self.openReplayRequested = _NullSignal()
                self.agentCatalogChanged = _NullSignal()

            def exec(self):
                return None

        monkeypatch.setattr("app.agent_designer.EvaluationHistoryDialog", _RecordingHistoryDialog)

        designer._on_evaluation_history()

        assert received["battle_root"] == designer.battle_root
        assert received["allow_restore"] is True
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

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path / "designer-data"))
    designer = AgentDesigner()
    try:
        connected = {}

        class _RecordingSignal:
            def __init__(self, key):
                self._key = key

            def connect(self, handler):
                connected[self._key] = handler

        class _RecordingHistoryDialog:
            def __init__(self, battle_root, *, allow_restore=True, parent=None):
                self.testInAgentLabRequested = _RecordingSignal("lab")
                self.openReplayRequested = _RecordingSignal("replay")
                self.agentCatalogChanged = _RecordingSignal("catalog")

            def exec(self):
                return None

        monkeypatch.setattr("app.agent_designer.EvaluationHistoryDialog", _RecordingHistoryDialog)

        designer._on_evaluation_history()

        assert connected["lab"] == designer._on_evaluation_test_in_agent_lab
        assert connected["replay"] == designer._on_evaluation_open_replay
        assert connected["catalog"] == designer._on_agent_catalog_changed
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_designer_history_disables_restore_while_process_is_active(monkeypatch, tmp_path):
    _make_app()
    from PySide6.QtCore import QProcess

    from app.agent_designer import AgentDesigner

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path / "designer-data"))
    designer = AgentDesigner()
    try:
        received = {}

        class _ActiveProcess:
            @staticmethod
            def state():
                return QProcess.Running

        class _RecordingHistoryDialog:
            def __init__(self, battle_root, *, allow_restore=True, parent=None):
                received["allow_restore"] = allow_restore
                self.testInAgentLabRequested = _NullSignal()
                self.openReplayRequested = _NullSignal()
                self.agentCatalogChanged = _NullSignal()

            def exec(self):
                return None

        monkeypatch.setattr(
            "app.agent_designer.EvaluationHistoryDialog", _RecordingHistoryDialog
        )
        designer._proc = _ActiveProcess()
        designer._on_evaluation_history()

        assert received["allow_restore"] is False
    finally:
        designer._proc = None
        designer.deleteLater()


@pytest.mark.gui
def test_designer_live_restore_refreshes_all_panels_and_invalidates_evidence(
    monkeypatch, tmp_path
):
    _make_app()
    from app.agent_designer import AgentDesigner

    data_root = tmp_path / "designer-data"
    _write_python_agent(data_root, "candidate")
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    designer = AgentDesigner()
    try:
        designer.development.selectAgent("candidate")
        assert designer.development.selectedAgentRow().agent_id == "candidate"

        panel = designer.development
        panel._last_validation = object()  # type: ignore[assignment]
        panel._last_test = object()  # type: ignore[assignment]
        panel._last_test_replay = tmp_path / "stale-replay.jsonl"
        panel._last_test_trace = tmp_path / "stale-trace.jsonl"
        panel.btnOpenTestReplay.setEnabled(True)
        panel.btnInspectTrace.setEnabled(True)

        refreshed = []
        for name in ("simple", "advanced", "development"):
            target = getattr(designer, name)
            original = target.setAgents

            def _record(rows, *, _name=name, _original=original):
                refreshed.append(_name)
                return _original(rows)

            monkeypatch.setattr(target, "setAgents", _record)

        designer._on_agent_catalog_changed("candidate")

        assert refreshed == ["simple", "advanced", "development"]
        assert designer.development.selectedAgentRow().agent_id == "candidate"
        assert panel._last_validation is None
        assert panel._last_test is None
        assert panel.last_test_replay_path() is None
        assert panel.last_test_trace_path() is None
        assert not panel.btnOpenTestReplay.isEnabled()
        assert not panel.btnInspectTrace.isEnabled()
        assert "Revision files were restored" in panel.statusLabel.text()

        # The empty signal is catalog-wide: preserve selection by discovery
        # id while still invalidating evidence for the visible agent.
        panel._last_validation = object()  # type: ignore[assignment]
        refreshed.clear()
        designer._on_agent_catalog_changed("")
        assert refreshed == ["simple", "advanced", "development"]
        assert designer.development.selectedAgentRow().agent_id == "candidate"
        assert panel._last_validation is None
    finally:
        designer.deleteLater()
