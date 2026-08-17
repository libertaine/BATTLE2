"""GUI regression coverage for the v0.6 Agent Evaluation Designer UX.

Covers: the Development tab's "Evaluate…" button enablement, the
``EvaluationDialog`` input collector, the read-only
``EvaluationResultsDialog`` (comparison-mode and single-candidate/cells-only
mode, selection-driven detail text, and its two drill-down signals), and
``AgentDesigner`` wiring (opening the dialog, building/launching the
``bytefray agents evaluate`` command, and handling the "Test in Agent Lab"/
"Open Replay" drill-down actions). Real (not mocked)
``battle_engine.agent_evaluation.EvaluationService`` runs are used to
produce the ``evaluation.json`` fixtures the results-dialog tests read,
per the existing Designer test suite's convention of exercising the real
backend rather than duplicating its behavior in a mock.

Marked ``gui`` like the existing Designer tests: excluded from the default
headless run, exercised by the dedicated display-backed workflow.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _make_app():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _write_python_agent(root: Path, name: str, action: str = "AgentAction(ActionKind.NOP)") -> None:
    directory = root / "agents" / name
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


def _run_real_evaluation(tmp_path: Path, *, baseline: bool) -> Path:
    """Produce a real ``evaluation.json`` via the actual service (no mocking)."""

    from battle_engine.agent_evaluation import EvaluationRequest, EvaluationService

    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    if baseline:
        _write_python_agent(tmp_path, "baseline")

    service = EvaluationService()
    request = EvaluationRequest(
        candidate_id="candidate",
        baseline_id="baseline" if baseline else None,
        opponent_ids=("opponent",),
        seeds=(1,),
        output_dir=tmp_path / "eval-out",
        ticks=15,
        data_root=tmp_path,
    )
    result = service.run(request)
    return result.state_path


# ---------------------------------------------------------------------------
# Development panel: Evaluate button
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_evaluate_button_enablement_mirrors_test_and_validate():
    _make_app()
    from app.services.agent_catalog import AgentRow
    from app.views.development import AgentDevelopmentPanel

    panel = AgentDevelopmentPanel()
    try:
        assert not panel.btnEvaluate.isEnabled()
        row = AgentRow(name="candidate", path="agents/candidate", blob_path=None, meta={"kind": "python"})
        panel.setAgents([row])
        panel.selectAgent("candidate")
        assert panel.btnEvaluate.isEnabled()
        assert panel.btnTest.isEnabled()
        panel.setBusy(True)
        assert not panel.btnEvaluate.isEnabled()
        panel.setBusy(False)
        assert panel.btnEvaluate.isEnabled()
    finally:
        panel.deleteLater()


@pytest.mark.gui
def test_python_agent_names_reflects_catalog():
    _make_app()
    from app.services.agent_catalog import AgentRow
    from app.views.development import AgentDevelopmentPanel

    panel = AgentDevelopmentPanel()
    try:
        rows = [
            AgentRow(name="A", path="agents/a", blob_path=None, meta={"kind": "python"}, agent_id="a"),
            AgentRow(name="B", path="agents/b", blob_path=None, meta={"kind": "python"}, agent_id="b"),
            AgentRow(name="vm", path="agents/vm", blob_path=None, meta={"kind": "builtin"}, agent_id="vm"),
        ]
        panel.setAgents(rows)
        assert panel.python_agent_names() == [("A", "a"), ("B", "b")]
    finally:
        panel.deleteLater()


@pytest.mark.gui
def test_python_agent_names_returns_discovery_id_when_display_name_differs():
    """Regression for docs/specs/evaluation_history.md Sec 17: a manifest's
    display name (``AgentRow.name``) must never be mistaken for its discovery
    id (``AgentRow.agent_id``, == directory name)."""
    _make_app()
    from app.services.agent_catalog import AgentRow
    from app.views.development import AgentDevelopmentPanel

    panel = AgentDevelopmentPanel()
    try:
        rows = [
            AgentRow(
                name="My Fancy Candidate",
                path="agents/candidate_dir",
                blob_path=None,
                meta={"kind": "python"},
                agent_id="candidate_dir",
            ),
        ]
        panel.setAgents(rows)
        assert panel.python_agent_names() == [("My Fancy Candidate", "candidate_dir")]
    finally:
        panel.deleteLater()


# ---------------------------------------------------------------------------
# EvaluationDialog
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_evaluation_dialog_collects_fields(tmp_path):
    _make_app()
    from app.views.evaluation import EvaluationDialog

    dialog = EvaluationDialog(
        [("Candidate", "candidate"), ("Opponent A", "opponent_a"), ("Opponent B", "opponent_b")],
        default_candidate="candidate",
        default_output=tmp_path / "out",
    )
    try:
        assert dialog.candidate_id() == "candidate"
        assert dialog.baseline_id() is None
        dialog.baselineCombo.setCurrentIndex(dialog.baselineCombo.findData("opponent_a"))
        assert dialog.baseline_id() == "opponent_a"

        for index in range(dialog.opponentsList.count()):
            item = dialog.opponentsList.item(index)
            if item.text() in ("Opponent A", "Opponent B"):
                item.setSelected(True)
        assert set(dialog.opponent_ids()) == {"opponent_a", "opponent_b"}

        dialog.seedsEdit.setText("1,2,3")
        assert dialog.seeds_text() == "1,2,3"
        dialog.ticksSpin.setValue(50)
        assert dialog.ticks() == 50
        assert dialog.output_path() == tmp_path / "out"
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_evaluation_dialog_both_orientations_checkbox_defaults_checked(tmp_path):
    """v0.9 Phase 6 (Phase 5 spec Sec P): checked by default ("recommended")."""

    _make_app()
    from app.views.evaluation import EvaluationDialog

    dialog = EvaluationDialog(
        [("Candidate", "candidate"), ("Opponent", "opponent")],
        default_candidate="candidate",
        default_output=tmp_path / "out",
    )
    try:
        assert dialog.both_orientations() is True
        dialog.bothOrientationsCheck.setChecked(False)
        assert dialog.both_orientations() is False
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_designer_evaluate_command_includes_single_orientation_flag_only_when_unchecked(
    monkeypatch, tmp_path
):
    """v0.9 Phase 6: unchecking the checkbox must pass the CLI-equivalent
    ``--single-orientation``; checked (the default) must not add any flag."""

    _make_app()
    from app.agent_designer import AgentDesigner
    from app.services.agent_catalog import AgentRow

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path / "data"))
    designer = AgentDesigner()
    try:
        designer.development.setAgents(
            [
                AgentRow(name="candidate", path="agents/candidate", blob_path=None, meta={"kind": "python"}),
                AgentRow(name="opponent", path="agents/opponent", blob_path=None, meta={"kind": "python"}),
            ]
        )
        designer.development.selectAgent("candidate")

        captured_commands = []

        class _RecordingDialog:
            both_orientations_value = True

            def __init__(self, *a, **k):
                pass

            def exec(self):
                return True

            def candidate_id(self):
                return "candidate"

            def baseline_id(self):
                return None

            def opponent_ids(self):
                return ("opponent",)

            def seeds_text(self):
                return "1"

            def seed_range_text(self):
                return ""

            def ticks(self):
                return 10

            def both_orientations(self):
                return _RecordingDialog.both_orientations_value

            def output_path(self):
                return tmp_path / "designer-eval-out"

        monkeypatch.setattr("app.agent_designer.EvaluationDialog", _RecordingDialog)

        class _FakeProc:
            def start(self):
                pass

        def _fake_start_process(command, env, working_directory, *, label):
            captured_commands.append(command)
            designer._proc = _FakeProc()
            return designer._proc

        monkeypatch.setattr(designer, "_start_process", _fake_start_process)

        _RecordingDialog.both_orientations_value = True
        designer._on_evaluate()
        assert "--single-orientation" not in captured_commands[0]

        designer._proc = None
        designer._active_workflow = None
        _RecordingDialog.both_orientations_value = False
        designer._on_evaluate()
        assert "--single-orientation" in captured_commands[1]
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_results_dialog_shows_orientation_methodology_and_per_cell_orientation(tmp_path):
    """v0.9 Phase 6 (Phase 5 spec Sec P): results presentation exposes both
    the shared methodology disclosure and each cell's own orientation."""

    _make_app()
    from battle_engine.agent_evaluation import EvaluationRequest, EvaluationService

    from app.services.designer_workflows import read_evaluation_presentation
    from app.views.evaluation import EvaluationResultsDialog

    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")

    service = EvaluationService()
    request = EvaluationRequest(
        candidate_id="candidate",
        opponent_ids=("opponent",),
        seeds=(1,),
        output_dir=tmp_path / "eval-out",
        ticks=10,
        data_root=tmp_path,
    )
    result = service.run(request)
    presentation = read_evaluation_presentation(result.state_path)
    assert presentation.orientation_mode == "both"
    assert {cell.orientation for cell in presentation.cells} == {"candidate_first", "opponent_first"}

    dialog = EvaluationResultsDialog(presentation)
    try:
        from PySide6.QtWidgets import QLabel

        header_label = dialog.findChildren(QLabel)[0]
        assert "Entrant orientation: both" in header_label.text()
        assert "Arena alignment: fixed" in header_label.text()

        labels = [dialog.resultsList.item(i).text() for i in range(dialog.resultsList.count())]
        assert any("orientation=candidate_first" in label for label in labels)
        assert any("orientation=opponent_first" in label for label in labels)
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_evaluation_dialog_returns_discovery_id_when_display_name_differs(tmp_path):
    """Regression: selecting an agent whose display text differs from its
    discovery id must still return the discovery id (Sec 17)."""
    _make_app()
    from app.views.evaluation import EvaluationDialog

    dialog = EvaluationDialog(
        [("My Fancy Candidate", "candidate_dir"), ("Some Opponent", "opponent_dir")],
        default_candidate="candidate_dir",
        default_output=tmp_path / "out",
    )
    try:
        assert dialog.candidate_id() == "candidate_dir"
        item = dialog.opponentsList.item(1)
        assert item.text() == "Some Opponent"
        item.setSelected(True)
        assert dialog.opponent_ids() == ("opponent_dir",)
        dialog.baselineCombo.setCurrentIndex(dialog.baselineCombo.findData("opponent_dir"))
        assert dialog.baseline_id() == "opponent_dir"
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_evaluation_dialog_defaults_to_no_preselected_candidate_when_absent(tmp_path):
    _make_app()
    from app.views.evaluation import EvaluationDialog

    dialog = EvaluationDialog(
        [("Only Agent", "only_agent")], default_candidate=None, default_output=tmp_path / "out"
    )
    try:
        assert dialog.candidate_id() == "only_agent"
    finally:
        dialog.deleteLater()


# ---------------------------------------------------------------------------
# EvaluationResultsDialog
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_results_dialog_comparison_mode_selection_and_signals(tmp_path):
    _make_app()
    from app.services.designer_workflows import read_evaluation_presentation
    from app.views.evaluation import EvaluationResultsDialog

    state_path = _run_real_evaluation(tmp_path, baseline=True)
    presentation = read_evaluation_presentation(state_path)
    assert presentation.comparison  # sanity: paired evaluation produced comparison rows

    dialog = EvaluationResultsDialog(presentation)
    try:
        assert dialog.resultsList.count() == len(presentation.comparison)
        dialog.resultsList.setCurrentRow(0)
        assert dialog.btnTestAgentLab.isEnabled()
        assert "candidate" in dialog.detailText.toPlainText()

        captured_lab: list[tuple[str, str, int, int, str]] = []
        captured_replay: list[Path] = []
        dialog.testInAgentLabRequested.connect(
            lambda s, o, seed, ticks, orientation: captured_lab.append(
                (s, o, seed, ticks, orientation)
            )
        )
        dialog.openReplayRequested.connect(lambda p: captured_replay.append(p))

        dialog._on_test_agent_lab()
        assert captured_lab == [("candidate", "opponent", 1, 15, "candidate_first")]

        dialog._on_open_replay()
        assert captured_replay
        assert captured_replay[0].name == "replay.jsonl"
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_results_dialog_duplicate_seed_open_replay_resolves_correct_duplicate(tmp_path):
    """Regression: a repeated (opponent, seed) pair produces two comparison
    rows (engine-side fix ab54a87). Before candidate_schedule_id was threaded
    through ComparisonEntry/EvaluationComparisonPresentation, ``_find_cell``
    resolved a selected comparison row's candidate cell by
    ``(role, opponent_id, seed)`` alone, which always returned the *first*
    matching duplicate cell regardless of which row was actually selected --
    reintroducing, in the Designer's drill-down, the exact class of bug
    ab54a87 fixed at the engine layer. Selecting the second duplicate's row
    and clicking "Open Replay" must resolve to the second duplicate's own
    artifact_dir, not the first's."""
    _make_app()
    from battle_engine.agent_evaluation import EvaluationRequest, EvaluationService

    from app.services.designer_workflows import read_evaluation_presentation
    from app.views.evaluation import EvaluationResultsDialog

    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "baseline")
    _write_python_agent(tmp_path, "opponent")

    service = EvaluationService()
    request = EvaluationRequest(
        candidate_id="candidate",
        baseline_id="baseline",
        opponent_ids=("opponent",),
        seeds=(1, 1),
        output_dir=tmp_path / "eval-out",
        ticks=15,
        data_root=tmp_path,
        # This test predates entrant orientation (v0.9 Phase 6) and is about
        # duplicate-seed drill-down resolution, orthogonal to it -- pinned
        # to the legacy single-orientation matrix shape/size.
        both_orientations=False,
    )
    result = service.run(request)
    presentation = read_evaluation_presentation(result.state_path)
    assert len(presentation.comparison) == 2  # one entry per duplicate, not collapsed to one

    candidate_cells = [cell for cell in presentation.cells if cell.subject_role == "candidate"]
    assert len(candidate_cells) == 2
    assert candidate_cells[0].artifact_dir != candidate_cells[1].artifact_dir
    assert candidate_cells[0].schedule_id != candidate_cells[1].schedule_id

    dialog = EvaluationResultsDialog(presentation)
    try:
        captured_replay: list[Path] = []
        dialog.openReplayRequested.connect(lambda p: captured_replay.append(p))

        dialog.resultsList.setCurrentRow(1)  # the second duplicate's comparison row
        dialog._on_open_replay()
        assert captured_replay
        assert captured_replay[0].parent == candidate_cells[1].artifact_dir
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_results_dialog_cells_only_mode_without_baseline(tmp_path):
    _make_app()
    from app.services.designer_workflows import read_evaluation_presentation
    from app.views.evaluation import EvaluationResultsDialog

    state_path = _run_real_evaluation(tmp_path, baseline=False)
    presentation = read_evaluation_presentation(state_path)
    assert not presentation.comparison

    dialog = EvaluationResultsDialog(presentation)
    try:
        assert dialog.resultsList.count() == len(presentation.cells)
        dialog.resultsList.setCurrentRow(0)
        assert dialog.btnTestAgentLab.isEnabled()
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_results_dialog_no_selection_disables_actions(tmp_path):
    _make_app()
    from app.services.designer_workflows import read_evaluation_presentation
    from app.views.evaluation import EvaluationResultsDialog

    state_path = _run_real_evaluation(tmp_path, baseline=False)
    presentation = read_evaluation_presentation(state_path)

    dialog = EvaluationResultsDialog(presentation)
    try:
        assert not dialog.btnTestAgentLab.isEnabled()
        assert not dialog.btnOpenReplay.isEnabled()
    finally:
        dialog.deleteLater()


# ---------------------------------------------------------------------------
# AgentDesigner wiring
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_designer_evaluate_is_noop_without_python_agents(monkeypatch, tmp_path):
    _make_app()
    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path / "data"))
    designer = AgentDesigner()
    try:
        # Force an empty Python-agent catalog, even though Bytefray now
        # seeds Python starter agents by default (see
        # battle_engine.starters) -- _on_evaluate's "no Python agents yet"
        # guard is still real production behavior (app.agent_designer
        # ._on_evaluate) and needs its own coverage independent of startup
        # seeding.
        designer.development.setAgents([])

        opened = []
        informed = []
        monkeypatch.setattr(
            "app.agent_designer.EvaluationDialog",
            lambda *a, **k: opened.append(1) or pytest.fail("must not open with no agents"),
        )
        monkeypatch.setattr(
            agent_designer_module.QMessageBox,
            "information",
            staticmethod(lambda *a, **k: informed.append(1)),
        )
        designer._on_evaluate()
        assert not opened
        assert informed  # the "no Python agents yet" notice was shown
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_designer_evaluate_launches_process_on_accept(monkeypatch, tmp_path):
    _make_app()
    from app.agent_designer import AgentDesigner
    from app.services.agent_catalog import AgentRow

    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    designer = AgentDesigner()
    try:
        designer.development.setAgents(
            [
                AgentRow(name="candidate", path="agents/candidate", blob_path=None, meta={"kind": "python"}),
                AgentRow(name="opponent", path="agents/opponent", blob_path=None, meta={"kind": "python"}),
            ]
        )
        designer.development.selectAgent("candidate")

        class _AcceptingDialog:
            def __init__(self, *a, **k):
                pass

            def exec(self):
                return True

            def candidate_id(self):
                return "candidate"

            def baseline_id(self):
                return None

            def opponent_ids(self):
                return ("opponent",)

            def seeds_text(self):
                return "1,2"

            def seed_range_text(self):
                return ""

            def ticks(self):
                return 30

            def both_orientations(self):
                return True

            def output_path(self):
                return tmp_path / "designer-eval-out"

        monkeypatch.setattr("app.agent_designer.EvaluationDialog", _AcceptingDialog)

        started = []

        class _FakeProc:
            def start(self):
                started.append(True)

        def _fake_start_process(command, env, working_directory, *, label):
            assert label == "Evaluate"
            assert command[0]  # non-empty program
            assert "evaluate" in command
            designer._proc = _FakeProc()
            return designer._proc

        monkeypatch.setattr(designer, "_start_process", _fake_start_process)

        designer._on_evaluate()

        assert designer._active_workflow == "evaluate"
        assert started == [True]
        assert designer._evaluation_output == (tmp_path / "designer-eval-out").resolve()
        assert designer._evaluation_ticks == 30
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_designer_evaluate_shows_warning_on_invalid_request(monkeypatch, tmp_path):
    _make_app()
    import app.agent_designer as agent_designer_module
    from app.agent_designer import AgentDesigner
    from app.services.agent_catalog import AgentRow

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path / "data"))
    designer = AgentDesigner()
    try:
        designer.development.setAgents(
            [AgentRow(name="candidate", path="agents/candidate", blob_path=None, meta={"kind": "python"})]
        )
        designer.development.selectAgent("candidate")

        class _EmptyOpponentsDialog:
            def __init__(self, *a, **k):
                pass

            def exec(self):
                return True

            def candidate_id(self):
                return "candidate"

            def baseline_id(self):
                return None

            def opponent_ids(self):
                return ()  # invalid: no opponents selected

            def seeds_text(self):
                return "1"

            def seed_range_text(self):
                return ""

            def ticks(self):
                return 30

            def both_orientations(self):
                return True

            def output_path(self):
                return tmp_path / "out"

        monkeypatch.setattr("app.agent_designer.EvaluationDialog", _EmptyOpponentsDialog)

        warned = []
        monkeypatch.setattr(
            agent_designer_module.QMessageBox,
            "warning",
            staticmethod(lambda *a, **k: warned.append(a)),
        )

        designer._active_workflow = "match"
        designer._on_evaluate()

        assert warned
        assert designer._active_workflow == "match"  # unchanged: never launched
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_designer_present_evaluation_result_opens_results_dialog(monkeypatch, tmp_path):
    _make_app()
    from app.agent_designer import AgentDesigner

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path / "designer-data"))
    designer = AgentDesigner()
    try:
        state_path = _run_real_evaluation(tmp_path, baseline=True)
        designer._evaluation_output = state_path.parent
        designer._log_target = designer.advanced

        received = []

        class _RecordingResultsDialog:
            def __init__(self, presentation, parent=None):
                received.append(presentation)
                self.testInAgentLabRequested = _NullSignal()
                self.openReplayRequested = _NullSignal()

            def exec(self):
                return None

        class _NullSignal:
            def connect(self, *_a, **_k):
                pass

        monkeypatch.setattr("app.agent_designer.EvaluationResultsDialog", _RecordingResultsDialog)

        designer._present_evaluation_result(0)

        assert len(received) == 1
        assert received[0].candidate_id == "candidate"
        assert received[0].baseline_id == "baseline"
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_designer_evaluation_test_in_agent_lab_reproduces_ticks_and_orientation(
    monkeypatch, tmp_path
):
    _make_app()
    from app.agent_designer import AgentDesigner

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path / "data"))
    designer = AgentDesigner()
    try:
        designer._evaluation_ticks = 999  # selected-cell ticks must win over stale state
        captured = {}

        class _FakeProc:
            def start(self):
                captured["started"] = True

        def _fake_start_process(command, env, working_directory, *, label):
            captured["command"] = command
            captured["label"] = label
            return _FakeProc()

        monkeypatch.setattr(designer, "_start_process", _fake_start_process)

        designer._on_evaluation_test_in_agent_lab(
            "candidate", "opponent", 7, 40, "opponent_first"
        )

        assert captured["label"] == "AgentLabTest"
        assert captured["started"] is True
        assert designer._active_workflow == "evaluation_agent_lab_test"
        command = captured["command"]
        test_index = command.index("test")
        assert command[test_index + 1 :] == [
            "opponent",
            "--opponent",
            "candidate",
            "--seed",
            "7",
            "--ticks",
            "40",
        ]
        assert designer._test_agent_id == "opponent"
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_designer_evaluate_uses_discovery_id_not_display_name_when_they_differ(monkeypatch, tmp_path):
    """End-to-end regression for docs/specs/evaluation_history.md Sec 17:
    a real on-disk agent whose manifest ``display`` differs from its
    directory (discovery id) must reach ``bytefray agents evaluate`` by
    discovery id, via the real (not mocked) ``EvaluationDialog``."""
    _make_app()
    from app.agent_designer import AgentDesigner

    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))

    def _write_agent(directory_name: str, display_name: str) -> None:
        directory = data_root / "agents" / directory_name
        directory.mkdir(parents=True)
        (directory / "agent.yaml").write_text(
            json.dumps(
                {
                    "display": display_name,
                    "kind": "python",
                    "api_version": 1,
                    "entrypoint": "agent.py:create_agent",
                    "version": "1.0",
                }
            ),
            encoding="utf-8",
        )
        (directory / "agent.py").write_text(
            "from battle_engine.agent_api import ActionKind, AgentAction\n"
            "class Agent:\n"
            "    def reset(self, context): pass\n"
            "    def act(self, observation): return AgentAction(ActionKind.NOP)\n"
            "def create_agent(): return Agent()\n",
            encoding="utf-8",
        )

    _write_agent("candidate_dir", "My Fancy Candidate")
    _write_agent("opponent_dir", "Some Opponent")

    designer = AgentDesigner()
    try:
        designer.refresh_agents()
        designer.development.selectAgent("My Fancy Candidate")

        class _RealDialogSpy:
            """Wraps the real EvaluationDialog, auto-selecting the opponent."""

            def __init__(self, agents, **kwargs):
                from app.views.evaluation import EvaluationDialog

                self._dialog = EvaluationDialog(agents, **kwargs)
                for index in range(self._dialog.opponentsList.count()):
                    item = self._dialog.opponentsList.item(index)
                    if item.text() == "Some Opponent":
                        item.setSelected(True)
                self._dialog.seedsEdit.setText("1")

            def exec(self):
                return True

            def __getattr__(self, item):
                return getattr(self._dialog, item)

        monkeypatch.setattr("app.agent_designer.EvaluationDialog", _RealDialogSpy)

        started = []

        class _FakeProc:
            def start(self):
                started.append(True)

        captured = {}

        def _fake_start_process(command, env, working_directory, *, label):
            captured["command"] = command
            designer._proc = _FakeProc()
            return designer._proc

        monkeypatch.setattr(designer, "_start_process", _fake_start_process)

        designer._on_evaluate()

        assert started == [True]
        command = captured["command"]
        joined = " ".join(command)
        assert "candidate_dir" in command  # the candidate id is its own positional argument
        assert "opponent_dir" in joined  # joined into the comma-separated --opponents value
        assert "My Fancy Candidate" not in joined
        assert "Some Opponent" not in joined
        # The fixed-output collision fix: this plan's own content-addressed
        # default, not a single fixed "designer-evaluation" path shared by
        # every plan.
        assert designer._evaluation_output.name != "designer-evaluation"
        assert designer._evaluation_output.parent.name == "evaluations"
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_designer_evaluation_open_replay_delegates_to_launcher(monkeypatch, tmp_path):
    _make_app()
    from app.agent_designer import AgentDesigner

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path / "data"))
    designer = AgentDesigner()
    try:
        launched = []
        monkeypatch.setattr(
            "app.agent_designer.open_pygame_client_direct",
            lambda root, replay: launched.append((root, replay)),
        )
        replay_path = tmp_path / "replay.jsonl"
        designer._on_evaluation_open_replay(replay_path)
        assert launched == [(designer.battle_root, replay_path)]
    finally:
        designer.deleteLater()
