"""v1.6 Phase 3 -- Designer preset integration
(docs/V1_6_PHASE3_EVALUATION_PRESETS.md).

Covers preset discovery/selection/prefill in ``EvaluationDialog`` and
end-to-end ``AgentDesigner`` wiring: the dialog never parses/resolves
preset YAML itself (the caller loads presets via
``battle_engine.evaluation_presets`` and hands over already-typed objects
purely for display), and the constructed ``bytefray agents evaluate`` argv
carries both the fully explicit resolved values *and* ``--preset <name>``
for the CLI's own authoritative resolution.

Marked ``gui`` like every other Designer test: excluded from the default
headless run.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml

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


def _write_preset(root: Path, name: str, body: dict) -> None:
    from battle_engine.evaluation_presets import SCHEMA_NAME, SCHEMA_VERSION, presets_root

    directory = presets_root(root)
    directory.mkdir(parents=True, exist_ok=True)
    payload = {"schema": SCHEMA_NAME, "schema_version": SCHEMA_VERSION}
    payload.update(body)
    (directory / f"{name}.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")


# ---------------------------------------------------------------------------
# EvaluationDialog: discovery / selection / prefill
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_dialog_without_presets_hides_combo(tmp_path):
    _make_app()
    from app.views.evaluation import EvaluationDialog

    dialog = EvaluationDialog(
        [("Candidate", "candidate"), ("Opponent", "opponent")],
        default_candidate="candidate",
        default_output=tmp_path / "out",
    )
    try:
        assert dialog.presetCombo is None
        assert dialog.preset_name() is None
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_dialog_lists_discovered_preset_names(tmp_path):
    _make_app()
    from battle_engine.evaluation_presets import load_preset

    _write_preset(tmp_path, "standard", {"opponents": ["opponent"], "seeds": [1]})
    _write_preset(tmp_path, "smoke", {"opponents": ["opponent"], "seeds": [2]})
    from app.views.evaluation import EvaluationDialog

    presets = {name: load_preset(tmp_path, name) for name in ("standard", "smoke")}
    dialog = EvaluationDialog(
        [("Candidate", "candidate"), ("Opponent", "opponent")],
        default_candidate="candidate",
        default_output=tmp_path / "out",
        presets=presets,
    )
    try:
        assert dialog.presetCombo is not None
        items = [dialog.presetCombo.itemText(i) for i in range(dialog.presetCombo.count())]
        assert items == ["(none)", "smoke", "standard"]
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_selecting_preset_populates_fields(tmp_path):
    _make_app()
    from battle_engine.evaluation_presets import load_preset

    _write_preset(
        tmp_path,
        "standard",
        {
            "candidate": "candidate",
            "baseline": "baseline",
            "opponents": ["opponent"],
            "seeds": [5, 6],
            "ticks": 42,
            "orientation": "candidate_first_only",
        },
    )
    from app.views.evaluation import EvaluationDialog

    presets = {"standard": load_preset(tmp_path, "standard")}
    dialog = EvaluationDialog(
        [("Candidate", "candidate"), ("Baseline", "baseline"), ("Opponent", "opponent")],
        default_candidate=None,
        default_output=tmp_path / "out",
        presets=presets,
    )
    try:
        assert dialog.both_orientations() is True  # default before selection
        index = dialog.presetCombo.findData("standard")
        dialog.presetCombo.setCurrentIndex(index)

        assert dialog.candidate_id() == "candidate"
        assert dialog.baseline_id() == "baseline"
        assert dialog.opponent_ids() == ("opponent",)
        assert dialog.seeds_text() == "5, 6"
        assert dialog.ticks() == 42
        assert dialog.both_orientations() is False
        assert dialog.preset_name() == "standard"
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_selecting_preset_then_editing_field_overrides_prefill(tmp_path):
    """Prefill is a convenience, never a binding -- the user can still edit
    any field after selecting a preset."""

    _make_app()
    from battle_engine.evaluation_presets import load_preset

    _write_preset(tmp_path, "standard", {"opponents": ["opponent"], "seeds": [5], "ticks": 42})
    from app.views.evaluation import EvaluationDialog

    presets = {"standard": load_preset(tmp_path, "standard")}
    dialog = EvaluationDialog(
        [("Candidate", "candidate"), ("Opponent", "opponent")],
        default_candidate="candidate",
        default_output=tmp_path / "out",
        presets=presets,
    )
    try:
        dialog.presetCombo.setCurrentIndex(dialog.presetCombo.findData("standard"))
        assert dialog.ticks() == 42
        dialog.ticksSpin.setValue(99)
        assert dialog.ticks() == 99
        assert dialog.preset_name() == "standard"  # selection itself is unaffected by the edit
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_reselecting_none_keeps_preset_name_none(tmp_path):
    _make_app()
    from battle_engine.evaluation_presets import load_preset

    _write_preset(tmp_path, "standard", {"opponents": ["opponent"], "seeds": [1]})
    from app.views.evaluation import EvaluationDialog

    presets = {"standard": load_preset(tmp_path, "standard")}
    dialog = EvaluationDialog(
        [("Candidate", "candidate"), ("Opponent", "opponent")],
        default_candidate="candidate",
        default_output=tmp_path / "out",
        presets=presets,
    )
    try:
        dialog.presetCombo.setCurrentIndex(dialog.presetCombo.findData("standard"))
        assert dialog.preset_name() == "standard"
        dialog.presetCombo.setCurrentIndex(dialog.presetCombo.findData(None))
        assert dialog.preset_name() is None
    finally:
        dialog.deleteLater()


# ---------------------------------------------------------------------------
# build_designer_evaluate_command: --preset threading
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_build_command_includes_preset_flag_when_given(tmp_path):
    from app.services.designer_workflows import build_designer_evaluate_command

    command = build_designer_evaluate_command(
        candidate_id="candidate",
        baseline_id=None,
        opponent_ids=("opponent",),
        seeds_text="1",
        seed_range_text="",
        ticks=10,
        output_dir=tmp_path / "out",
        preset_name="standard",
    )
    assert command[command.index("--preset") + 1] == "standard"


@pytest.mark.gui
def test_build_command_omits_preset_flag_when_none(tmp_path):
    from app.services.designer_workflows import build_designer_evaluate_command

    command = build_designer_evaluate_command(
        candidate_id="candidate",
        baseline_id=None,
        opponent_ids=("opponent",),
        seeds_text="1",
        seed_range_text="",
        ticks=10,
        output_dir=tmp_path / "out",
    )
    assert "--preset" not in command


# ---------------------------------------------------------------------------
# AgentDesigner: end-to-end discovery, selection, launch
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_designer_evaluate_discovers_and_launches_with_selected_preset(monkeypatch, tmp_path):
    _make_app()
    from app.agent_designer import AgentDesigner
    from app.services.agent_catalog import AgentRow

    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    _write_python_agent(data_root, "candidate")
    _write_python_agent(data_root, "opponent")
    _write_preset(data_root, "standard", {"opponents": ["opponent"], "seeds": [3], "ticks": 11})

    designer = AgentDesigner()
    try:
        designer.development.setAgents(
            [
                AgentRow(name="candidate", path="agents/candidate", blob_path=None, meta={"kind": "python"}),
                AgentRow(name="opponent", path="agents/opponent", blob_path=None, meta={"kind": "python"}),
            ]
        )
        designer.development.selectAgent("candidate")

        class _RealDialogSpy:
            def __init__(self, agents, **kwargs):
                from app.views.evaluation import EvaluationDialog

                self._dialog = EvaluationDialog(agents, **kwargs)
                assert self._dialog.presetCombo is not None
                index = self._dialog.presetCombo.findData("standard")
                assert index >= 0
                self._dialog.presetCombo.setCurrentIndex(index)

            def exec(self):
                return True

            def __getattr__(self, item):
                return getattr(self._dialog, item)

        monkeypatch.setattr("app.agent_designer.EvaluationDialog", _RealDialogSpy)

        captured = {}

        class _FakeProc:
            def start(self):
                captured["started"] = True

        def _fake_start_process(command, env, working_directory, *, label):
            captured["command"] = command
            designer._proc = _FakeProc()
            return designer._proc

        monkeypatch.setattr(designer, "_start_process", _fake_start_process)

        designer._on_evaluate()

        assert captured.get("started") is True
        command = captured["command"]
        assert command[command.index("--preset") + 1] == "standard"
        assert command[command.index("--opponents") + 1] == "opponent"
        assert command[command.index("--seeds") + 1] == "3"
        assert command[command.index("--ticks") + 1] == "11"
    finally:
        designer.deleteLater()


@pytest.mark.gui
def test_designer_evaluate_with_invalid_preset_on_disk_still_opens(monkeypatch, tmp_path):
    """An invalid preset must not block the whole Evaluate dialog -- it is
    silently omitted from the dropdown ('evaluation-presets validate' is
    the diagnostic tool for why)."""

    _make_app()
    from battle_engine.evaluation_presets import presets_root

    from app.agent_designer import AgentDesigner
    from app.services.agent_catalog import AgentRow

    data_root = tmp_path / "data"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(data_root))
    _write_python_agent(data_root, "candidate")
    _write_python_agent(data_root, "opponent")
    directory = presets_root(data_root)
    directory.mkdir(parents=True)
    (directory / "broken.yaml").write_text("schema: [unterminated", encoding="utf-8")

    designer = AgentDesigner()
    try:
        designer.development.setAgents(
            [
                AgentRow(name="candidate", path="agents/candidate", blob_path=None, meta={"kind": "python"}),
                AgentRow(name="opponent", path="agents/opponent", blob_path=None, meta={"kind": "python"}),
            ]
        )
        designer.development.selectAgent("candidate")

        opened: dict = {}

        class _CapturingDialog:
            def __init__(self, agents, **kwargs):
                from app.views.evaluation import EvaluationDialog

                self._dialog = EvaluationDialog(agents, **kwargs)
                opened["presets"] = kwargs.get("presets")

            def exec(self):
                return False  # cancel immediately -- this test is about opening cleanly

            def __getattr__(self, item):
                return getattr(self._dialog, item)

        monkeypatch.setattr("app.agent_designer.EvaluationDialog", _CapturingDialog)
        designer._on_evaluate()

        assert opened["presets"] == {}
    finally:
        designer.deleteLater()


# ---------------------------------------------------------------------------
# v3.0.0-alpha2: pairwise Ruleset selector and its preset interaction
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_pairwise_ruleset_defaults_to_v2_and_group_stays_v2_only(tmp_path):
    """Both modes now state their Ruleset; only pairwise is selectable."""

    _make_app()
    from battle_engine.ruleset_policy import BYTEFRAY_RULESET_V2_ID

    from app.services.designer_workflows import EVALUATION_MODE_GROUP
    from app.views.evaluation import EvaluationDialog

    dialog = EvaluationDialog(
        [("Candidate", "candidate"), ("Opponent", "opponent"), ("Third", "third")],
        default_candidate="candidate",
        default_output=tmp_path / "out",
    )
    try:
        assert dialog.pairwise_ruleset_id() == BYTEFRAY_RULESET_V2_ID
        assert dialog.pairwiseRulesetCombo.isVisibleTo(dialog)
        assert not dialog.rulesetValue.isVisibleTo(dialog)

        index = dialog.modeCombo.findData(EVALUATION_MODE_GROUP)
        dialog.modeCombo.setCurrentIndex(index)
        # Group mode swaps the selector for the fixed v2-only statement.
        assert not dialog.pairwiseRulesetCombo.isVisibleTo(dialog)
        assert dialog.rulesetValue.isVisibleTo(dialog)
        assert BYTEFRAY_RULESET_V2_ID in dialog.rulesetValue.text()
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_preset_ruleset_is_surfaced_into_the_selector(tmp_path):
    """A preset's own Ruleset must be shown, not silently overridden.

    The launch path always sends ``--ruleset`` explicitly now, and an
    explicit CLI ``--ruleset`` outranks a preset's own ``ruleset`` field, so
    the dialog has to adopt the preset's value for it to survive.
    """

    _make_app()
    from battle_engine.evaluation_presets import load_preset
    from battle_engine.rules import BYTEFRAY_RULESET_ID

    _write_preset(
        tmp_path,
        "v1compat",
        {"opponents": ["opponent"], "seeds": [1], "ruleset": BYTEFRAY_RULESET_ID},
    )
    from app.views.evaluation import EvaluationDialog

    dialog = EvaluationDialog(
        [("Candidate", "candidate"), ("Opponent", "opponent")],
        default_candidate="candidate",
        default_output=tmp_path / "out",
        presets={"v1compat": load_preset(tmp_path, "v1compat")},
    )
    try:
        dialog.presetCombo.setCurrentIndex(dialog.presetCombo.findData("v1compat"))
        assert dialog.pairwise_ruleset_id() == BYTEFRAY_RULESET_ID
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_preset_without_a_ruleset_leaves_the_selection_alone(tmp_path):
    """Nothing to preserve, so the user's own choice governs."""

    _make_app()
    from battle_engine.evaluation_presets import load_preset
    from battle_engine.ruleset_policy import BYTEFRAY_RULESET_V2_ID

    _write_preset(tmp_path, "plain", {"opponents": ["opponent"], "seeds": [1]})
    from app.views.evaluation import EvaluationDialog

    dialog = EvaluationDialog(
        [("Candidate", "candidate"), ("Opponent", "opponent")],
        default_candidate="candidate",
        default_output=tmp_path / "out",
        presets={"plain": load_preset(tmp_path, "plain")},
    )
    try:
        dialog.presetCombo.setCurrentIndex(dialog.presetCombo.findData("plain"))
        assert dialog.pairwise_ruleset_id() == BYTEFRAY_RULESET_V2_ID
    finally:
        dialog.deleteLater()


@pytest.mark.gui
def test_designer_sends_the_dialogs_pairwise_ruleset(monkeypatch, tmp_path):
    """End-to-end: the selection reaches the launched argv."""

    _make_app()
    from battle_engine.rules import BYTEFRAY_RULESET_ID

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
                return tmp_path / "eval-out"

            def preset_name(self):
                return None

            def pairwise_ruleset_id(self):
                return BYTEFRAY_RULESET_ID

        monkeypatch.setattr("app.agent_designer.EvaluationDialog", _AcceptingDialog)

        launched: list[list[str]] = []

        class _FakeProc:
            def start(self):
                pass

        def _fake_start_process(command, env, working_directory, *, label):
            launched.append(list(command))
            designer._proc = _FakeProc()
            return designer._proc

        monkeypatch.setattr(designer, "_start_process", _fake_start_process)
        designer._on_evaluate()

        command = launched[0]
        assert command[command.index("--ruleset") + 1] == BYTEFRAY_RULESET_ID
    finally:
        designer.deleteLater()
