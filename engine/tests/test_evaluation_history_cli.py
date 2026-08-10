"""``bytefray agents evaluations list|show|compare`` CLI (docs/specs/evaluation_history.md Sec 15)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from battle_engine.agent_evaluation import EvaluationRequest, EvaluationService
from battle_engine.evaluation_history.cli import main as evaluations_main

NOP_ACTION = "AgentAction(ActionKind.NOP)"


def _write_python_agent(root: Path, name: str, action: str = NOP_ACTION) -> None:
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


def _run(tmp_path: Path, output_dir: Path, candidate: str = "candidate") -> str:
    _write_python_agent(tmp_path, candidate) if not (tmp_path / "agents" / candidate).is_dir() else None
    if not (tmp_path / "agents" / "opponent").is_dir():
        _write_python_agent(tmp_path, "opponent")
    result = EvaluationService().run(
        EvaluationRequest(
            candidate_id=candidate,
            opponent_ids=("opponent",),
            seeds=(1,),
            output_dir=output_dir,
            ticks=10,
            data_root=tmp_path,
        )
    )
    return result.evaluation_id


def test_cli_list_human_output(tmp_path: Path, capsys):
    root = tmp_path / "runs" / "evaluations"
    _run(tmp_path, root / "e1")
    code = evaluations_main(["list", "--root", str(root)])
    out = capsys.readouterr().out
    assert code == 0
    assert "evaluation-v2_" in out
    assert "candidate=candidate" in out


def test_cli_list_json_output_is_stable(tmp_path: Path, capsys):
    root = tmp_path / "runs" / "evaluations"
    _run(tmp_path, root / "e1")
    code = evaluations_main(["list", "--root", str(root), "--json"])
    out = capsys.readouterr().out
    assert code == 0
    data = json.loads(out)
    assert len(data["entries"]) == 1
    assert data["entries"][0]["summary"]["candidate_id"] == "candidate"


def test_cli_list_isolates_degraded_sibling(tmp_path: Path, capsys):
    root = tmp_path / "runs" / "evaluations"
    _run(tmp_path, root / "good")
    bad = root / "bad"
    bad.mkdir(parents=True)
    (bad / "evaluation.json").write_text("not json", encoding="utf-8")

    code = evaluations_main(["list", "--root", str(root)])
    out = capsys.readouterr().out
    assert code == 0
    assert "UNREADABLE" in out
    assert "evaluation-v2_" in out


def test_cli_show_human(tmp_path: Path, capsys):
    output_dir = tmp_path / "eval-out"
    evaluation_id = _run(tmp_path, output_dir)
    code = evaluations_main(["show", str(output_dir), "--verify"])
    out = capsys.readouterr().out
    assert code == 0
    assert evaluation_id in out
    assert "verified: True" in out


def test_cli_show_json(tmp_path: Path, capsys):
    output_dir = tmp_path / "eval-out"
    _run(tmp_path, output_dir)
    code = evaluations_main(["show", str(output_dir), "--json"])
    out = capsys.readouterr().out
    assert code == 0
    data = json.loads(out)
    assert data["candidate_id"] == "candidate"


def test_cli_show_unreadable_selector_exits_1(tmp_path: Path, capsys):
    bad_dir = tmp_path / "bad"
    bad_dir.mkdir(parents=True)
    (bad_dir / "evaluation.json").write_text("not json", encoding="utf-8")
    code = evaluations_main(["show", str(bad_dir)])
    assert code == 1


def test_cli_show_missing_selector_exits_2(tmp_path: Path, capsys):
    code = evaluations_main(["show", "evaluation-v2_doesnotexist", "--root", str(tmp_path)])
    assert code == 2


def test_cli_show_ambiguous_selector_exits_2(tmp_path: Path, capsys):
    import shutil

    root = tmp_path / "runs" / "evaluations"
    original = root / "original"
    _run(tmp_path, original)
    shutil.copytree(original, root / "copy")

    evaluation_id = json.loads((original / "evaluation.json").read_text(encoding="utf-8"))["evaluation_id"]
    code = evaluations_main(["show", evaluation_id, "--root", str(root)])
    assert code == 2


def test_cli_compare_regressions_exit_zero(tmp_path: Path, capsys):
    left_dir = tmp_path / "left"
    right_dir = tmp_path / "right"
    _run(tmp_path, left_dir)
    _run(tmp_path, right_dir, candidate="candidate")

    code = evaluations_main(["compare", str(left_dir), str(right_dir)])
    out = capsys.readouterr().out
    assert code == 0  # a comparison result -- even with regressions -- is a successful command
    assert "orientation: right_relative_to_left" in out


def test_cli_compare_json_output(tmp_path: Path, capsys):
    left_dir = tmp_path / "left"
    right_dir = tmp_path / "right"
    _run(tmp_path, left_dir)
    _run(tmp_path, right_dir)

    code = evaluations_main(["compare", str(left_dir), str(right_dir), "--json"])
    out = capsys.readouterr().out
    assert code == 0
    data = json.loads(out)
    assert data["orientation"] == "right_relative_to_left"
    assert "denominators" in data


def test_cli_compare_no_comparable_cells_exits_1(tmp_path: Path, capsys):
    left_dir = tmp_path / "left"
    right_dir = tmp_path / "right"
    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent_left")
    _write_python_agent(tmp_path, "opponent_right")
    EvaluationService().run(
        EvaluationRequest(
            candidate_id="candidate", opponent_ids=("opponent_left",), seeds=(1,),
            output_dir=left_dir, ticks=10, data_root=tmp_path,
        )
    )
    EvaluationService().run(
        EvaluationRequest(
            candidate_id="candidate", opponent_ids=("opponent_right",), seeds=(1,),
            output_dir=right_dir, ticks=10, data_root=tmp_path,
        )
    )
    code = evaluations_main(["compare", str(left_dir), str(right_dir)])
    assert code == 1


def test_cli_invalid_verb_exits_2():
    with pytest.raises(SystemExit) as excinfo:
        evaluations_main(["bogus-verb"])
    assert excinfo.value.code == 2


def test_bytefray_and_battle2_dispatch_reach_evaluations(tmp_path: Path, capsys):
    """Same dispatch code path via battle_engine.command, both aliases."""

    from battle_engine.command import battle2_main
    from battle_engine.command import main as bytefray_main

    root = tmp_path / "runs" / "evaluations"
    _run(tmp_path, root / "e1")

    code = bytefray_main(["agents", "evaluations", "list", "--root", str(root), "--json"])
    out1 = capsys.readouterr().out
    assert code == 0
    assert json.loads(out1)["entries"]

    code = battle2_main(["agents", "evaluations", "list", "--root", str(root), "--json"])
    out2 = capsys.readouterr().out
    assert code == 0
    assert json.loads(out2)["entries"]
