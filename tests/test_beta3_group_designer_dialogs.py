"""Beta3 Phase 4 display-backed group-evaluation Designer coverage."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


def _app():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _write_agent(root: Path, agent_id: str) -> None:
    directory = root / "agents" / agent_id
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text(
        json.dumps(
            {
                "kind": "python",
                "api_version": 1,
                "entrypoint": "agent.py:create_agent",
                "version": "1.0",
            }
        ),
        encoding="utf-8",
    )
    (directory / "agent.py").write_text(
        """from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, context): pass
    def act(self, observation): return AgentAction(ActionKind.NOP)
def create_agent(): return Agent()
""",
        encoding="utf-8",
    )


def _select(dialog, *agent_ids: str) -> None:
    wanted = list(agent_ids)
    for row in range(dialog.opponentsList.count()):
        item = dialog.opponentsList.item(row)
        if item.data(256) in wanted:  # Qt.UserRole
            item.setSelected(True)


def _group_result(root: Path, output: Path):
    from battle_engine.agent_evaluation import EvaluationService

    from app.services.designer_workflows import (
        EVALUATION_MODE_GROUP,
        build_designer_evaluation_plan,
    )

    plan = build_designer_evaluation_plan(
        candidate_id="focus",
        baseline_id=None,
        opponent_ids=("a", "b"),
        seeds_text="3",
        seed_range_text="",
        ticks=2,
        output_dir=output,
        data_root=root,
        mode=EVALUATION_MODE_GROUP,
    )
    return EvaluationService().run(plan.request)


@pytest.mark.gui
def test_group_mode_updates_fields_preview_validation_and_accessibility(tmp_path: Path) -> None:
    _app()
    from app.services.designer_workflows import EVALUATION_MODE_GROUP, EVALUATION_MODE_PAIRWISE
    from app.views.evaluation import EvaluationDialog

    for agent_id in ("focus", "a", "b"):
        _write_agent(tmp_path, agent_id)
    dialog = EvaluationDialog(
        [("Focus", "focus"), ("A", "a"), ("B", "b")],
        default_candidate="focus",
        default_output=tmp_path / "out",
        data_root=tmp_path,
    )
    try:
        assert dialog.mode() == EVALUATION_MODE_PAIRWISE
        assert dialog.baselineCombo.isVisibleTo(dialog) is True
        dialog.modeCombo.setCurrentIndex(dialog.modeCombo.findData(EVALUATION_MODE_GROUP))
        assert dialog.mode() == EVALUATION_MODE_GROUP
        assert dialog.baseline_id() is None
        assert dialog.baselineCombo.isHidden()
        assert dialog.bothOrientationsCheck.isHidden()
        assert not dialog.runButton.isEnabled()
        assert "at least two roster members" in dialog.previewText.toPlainText()

        dialog.seedsEdit.setText("1")
        _select(dialog, "a", "b")
        assert dialog.runButton.isEnabled()
        preview = dialog.previewText.toPlainText()
        assert "Roster (3 physical entrants): focus, a, b" in preview
        assert "Distinct seat assignments: 6" in preview
        assert "Planned cells: 18" in preview
        assert dialog.rulesetValue.accessibleName() == "Group evaluation ruleset"
        assert "matrix preview" in dialog.previewText.accessibleName().lower()
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_group_results_use_roster_layout_seat_language_and_safe_actions(tmp_path: Path) -> None:
    _app()
    for agent_id in ("focus", "a", "b"):
        _write_agent(tmp_path, agent_id)
    result = _group_result(tmp_path, tmp_path / "result-view")

    from app.services.designer_workflows import read_evaluation_presentation
    from app.views.evaluation import EvaluationResultsDialog

    dialog = EvaluationResultsDialog(read_evaluation_presentation(result.state_path))
    try:
        assert dialog.resultsList.count() == 18
        first_text = dialog.resultsList.item(0).text()
        assert "layout=" in first_text
        assert "seats:" in first_text
        assert " vs " not in first_text
        assert "orientation=" not in first_text
        dialog.resultsList.setCurrentRow(0)
        assert not dialog.btnTestAgentLab.isEnabled()
        assert "only pairwise" in dialog.btnTestAgentLab.toolTip()
        assert dialog.btnOpenReplay.isEnabled()
        detail = dialog.detailText.toPlainText()
        assert "roster:" in detail
        assert "seat assignment:" in detail
        assert "opponent:" not in detail
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_group_results_dialog_shows_visual_rate_bars_per_entrant(tmp_path: Path) -> None:
    """v3.0 Phase 3: the results dialog's visual evidence panel renders a
    winner/survival/eliminated rate bar per roster entrant (focus first),
    matching CLI's ``_print_entrant_summary`` depth -- the GUI previously
    stopped at winner/survival only and never showed elimination at all.
    """

    _app()
    for agent_id in ("focus", "a", "b"):
        _write_agent(tmp_path, agent_id)
    result = _group_result(tmp_path, tmp_path / "result-view")

    from app.services.designer_workflows import read_evaluation_presentation
    from app.views.evaluation import EvaluationResultsDialog
    from app.widgets.evaluation_visuals import ProportionBar

    dialog = EvaluationResultsDialog(read_evaluation_presentation(result.state_path))
    try:
        captions = [bar.data.caption for bar in dialog.findChildren(ProportionBar)]
        for label in ("winner", "survival", "eliminated"):
            matches = [caption for caption in captions if caption.startswith(f"{label}:")]
            assert len(matches) == 3, f"expected one '{label}' bar per roster entrant, got {matches}"
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_group_history_classifies_from_persisted_mode_and_disables_agent_lab(tmp_path: Path) -> None:
    _app()
    for agent_id in ("focus", "a", "b"):
        _write_agent(tmp_path, agent_id)
    seed_result = _group_result(tmp_path, tmp_path / "seed")
    target = tmp_path / "runs" / "evaluations" / seed_result.evaluation_id
    # Produce the discoverable artifact through the real service, not a copy.
    _group_result(tmp_path, target)

    from app.views.evaluation_history import EvaluationHistoryDialog

    dialog = EvaluationHistoryDialog(tmp_path, allow_restore=False)
    try:
        assert dialog.list.count() == 1
        assert "mode=Group" in dialog.list.item(0).text()
        dialog.list.setCurrentRow(0)
        assert "mode: Group" in dialog.detailText.toPlainText()
        assert "rate denominator=physical entrant instance" in dialog.detailText.toPlainText()
        assert "layout=" in dialog.cellsList.item(0).text()
        assert " vs " not in dialog.cellsList.item(0).text()
        dialog.cellsList.setCurrentRow(0)
        assert not dialog.testAgentLabButton.isEnabled()
        assert "only pairwise" in dialog.testAgentLabButton.toolTip()
        assert dialog.openReplayButton.isEnabled()
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_group_comparison_uses_condition_language_and_preserves_replay_action(tmp_path: Path) -> None:
    _app()
    for agent_id in ("focus", "a", "b"):
        _write_agent(tmp_path, agent_id)
    left = _group_result(tmp_path, tmp_path / "left")
    right = _group_result(tmp_path, tmp_path / "right")

    from PySide6.QtWidgets import QLabel

    from app.services.evaluation_history_workflows import compare_evaluations
    from app.views.evaluation_history import EvaluationComparisonDialog

    comparison = compare_evaluations(left.state_path, right.state_path)
    dialog = EvaluationComparisonDialog(comparison)
    try:
        headings = "\n".join(label.text() for label in dialog.findChildren(QLabel))
        assert "roster/layout/seat-assignment cells" in headings
        assert "Per-opponent rows" not in headings
        assert dialog.rowsList.count() == 18
        assert "layout=" in dialog.rowsList.item(0).text()
        assert "opponent=" not in dialog.rowsList.item(0).text()
        dialog.rowsList.setCurrentRow(0)
        assert not dialog.testAgentLabButton.isEnabled()
        assert dialog.openReplayButton.isEnabled()
        assert "Pairwise orientation: not applicable" in dialog.detailText.toPlainText()
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_agent_designer_launches_group_plan_as_canonical_cli_command(
    tmp_path: Path, monkeypatch
) -> None:
    _app()
    for agent_id in ("focus", "a", "b"):
        _write_agent(tmp_path, agent_id)

    from app.agent_designer import AgentDesigner
    from app.services.designer_workflows import EVALUATION_MODE_GROUP

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    output = tmp_path / "designer-group"
    captured: list[str] = []

    class _GroupDialog:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return True

        def mode(self):
            return EVALUATION_MODE_GROUP

        def candidate_id(self):
            return "focus"

        def baseline_id(self):
            return None

        def opponent_ids(self):
            return ("a", "b")

        def seeds_text(self):
            return "11"

        def seed_range_text(self):
            return ""

        def ticks(self):
            return 4

        def both_orientations(self):
            return True

        def output_path(self):
            return output

        def preset_name(self):
            return None

    class _FakeProcess:
        def start(self):
            pass

    designer = AgentDesigner()
    try:
        monkeypatch.setattr("app.agent_designer.EvaluationDialog", _GroupDialog)

        def _start(command, env, working_directory, *, label):
            captured.extend(command)
            designer._proc = _FakeProcess()
            return designer._proc

        monkeypatch.setattr(designer, "_start_process", _start)
        designer._on_evaluate()

        assert "--group" in captured
        assert captured[captured.index("--ruleset") + 1] == "bytefray-rules-2"
        assert captured[captured.index("--opponents") + 1] == "a,b"
        assert captured[captured.index("--seeds") + 1] == "11"
        assert captured[captured.index("--ticks") + 1] == "4"
        assert captured[captured.index("--output") + 1] == str(output.resolve())
        assert "--single-orientation" not in captured
        assert "--baseline" not in captured
    finally:
        designer._proc = None
        designer.deleteLater()
