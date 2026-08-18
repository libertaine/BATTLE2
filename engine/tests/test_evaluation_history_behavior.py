"""Phase 5 behavior-profile integration with ``evaluations show``/``--json``
and the ``evaluations list`` cost-isolation requirement
(docs/V1_6_PHASE5_BEHAVIOR_ANALYSIS.md Sec 10/24).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from battle_engine.agent_evaluation import EvaluationRequest, EvaluationService
from battle_engine.evaluation_history.behavior_adapter import cell_refs_for_behavior
from battle_engine.evaluation_history.cli import main as evaluations_main
from battle_engine.evaluation_history.discovery import adapt_any
from battle_engine.evaluation_history.v1_adapter import adapt_v1

WRITE_ACTION = "AgentAction(ActionKind.WRITE, 0, 1)"
NOP_ACTION = "AgentAction(ActionKind.NOP)"


def _write_python_agent(root: Path, name: str, action: str = WRITE_ACTION) -> None:
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


def _run(
    tmp_path: Path,
    output_dir: Path,
    candidate: str = "candidate",
    *,
    baseline: str | None = None,
    seeds: tuple[int, ...] = (1,),
) -> str:
    if not (tmp_path / "agents" / candidate).is_dir():
        _write_python_agent(tmp_path, candidate)
    if not (tmp_path / "agents" / "opponent").is_dir():
        _write_python_agent(tmp_path, "opponent", NOP_ACTION)
    if baseline is not None and not (tmp_path / "agents" / baseline).is_dir():
        _write_python_agent(tmp_path, baseline)
    result = EvaluationService().run(
        EvaluationRequest(
            candidate_id=candidate,
            baseline_id=baseline,
            opponent_ids=("opponent",),
            seeds=seeds,
            output_dir=output_dir,
            ticks=10,
            data_root=tmp_path,
            both_orientations=False,
        )
    )
    return result.evaluation_id


def test_cli_show_human_includes_behavior_section(tmp_path: Path, capsys):
    output_dir = tmp_path / "eval-out"
    _run(tmp_path, output_dir)
    code = evaluations_main(["show", str(output_dir)])
    out = capsys.readouterr().out
    assert code == 0
    assert "behavior:" in out
    assert "candidate overall (candidate)" in out
    assert "candidate by opponent:" in out


def test_cli_show_json_includes_behavior_shape(tmp_path: Path, capsys):
    output_dir = tmp_path / "eval-out"
    _run(tmp_path, output_dir, baseline="baseline_agent")
    code = evaluations_main(["show", str(output_dir), "--json"])
    out = capsys.readouterr().out
    assert code == 0
    data = json.loads(out)
    assert "behavior" in data
    assert data["behavior"]["candidate_id"] == "candidate"
    assert data["behavior"]["baseline_id"] == "baseline_agent"
    dims = data["behavior"]["candidate_overall"]["dimensions"]
    assert "survival_fraction" in dims
    assert "kills_per_match" in dims
    assert data["behavior"]["candidate_vs_baseline_largest"] is not None


def test_cli_show_behavior_degrades_gracefully_when_result_json_missing(tmp_path: Path, capsys):
    """A cell's nested result.json can be pruned/absent on an older or
    partially-archived artifact (Sec 17 of the design doc); `show` must
    still succeed and report the affected dimensions as insufficient data,
    never crash the whole command."""

    output_dir = tmp_path / "eval-out"
    _run(tmp_path, output_dir)
    for result_json in output_dir.rglob("result.json"):
        result_json.unlink()

    code = evaluations_main(["show", str(output_dir)])
    out = capsys.readouterr().out
    assert code == 0
    assert "behavior:" in out
    assert "insufficient data" in out


def test_cli_list_does_not_read_result_json(tmp_path: Path, capsys):
    """Sec 10/24: `evaluations list` must stay cheap -- deleting every
    cell's result.json must not affect (or slow down/break) listing, since
    behavior computation is never wired into discovery/adapt_any."""

    root = tmp_path / "runs" / "evaluations"
    _run(tmp_path, root / "e1", seeds=(1, 2, 3))
    for result_json in root.rglob("result.json"):
        result_json.unlink()

    code = evaluations_main(["list", "--root", str(root)])
    out = capsys.readouterr().out
    assert code == 0
    assert "evaluation-v2_" in out
    assert "cells=3/3" in out  # cell *count* is unaffected by nested-artifact deletion


def test_adapt_any_alone_never_touches_result_json(tmp_path: Path):
    """Direct proof (not just an outcome-level list check): adapting a
    summary via the exact function `evaluations list` uses must not open
    any cell's result.json at all."""

    output_dir = tmp_path / "eval-out"
    _run(tmp_path, output_dir, seeds=(1, 2))
    state_path = output_dir / "evaluation.json"

    # Replace every result.json with a file that raises if ever opened by
    # making it a directory instead -- read_result would raise IsADirectoryError
    # (an OSError), which the behavior loader tolerates but plain adapt_any
    # must never even attempt.
    for result_json in output_dir.rglob("result.json"):
        result_json.unlink()
        result_json.mkdir()

    summary = adapt_any(state_path)  # must not raise
    assert len(summary.cells) == 2


def test_cell_refs_for_behavior_refuses_path_escape(tmp_path: Path):
    """M4-style containment: a cell whose recorded artifact_dir tries to
    escape the evaluation directory must resolve to a refused (None)
    result_path, never a followed one outside the evaluation's own tree."""

    output_dir = tmp_path / "eval-out"
    _run(tmp_path, output_dir)
    state_path = output_dir / "evaluation.json"
    data = json.loads(state_path.read_text(encoding="utf-8"))
    data["cells"][0]["artifact_dir"] = "../../escaped"
    state_path.write_text(json.dumps(data), encoding="utf-8")

    summary = adapt_any(state_path)
    refs = cell_refs_for_behavior(summary)
    escaped = next(r for r in refs if r.schedule_id == data["cells"][0]["schedule_id"])
    assert escaped.result_path is None


def _v1_fixture_with_real_result(tmp_path: Path) -> Path:
    """A hand-built v1-shaped evaluation.json (Sec 17: historical
    compatibility) whose one cell nonetheless has a real, on-disk
    result.json -- v1 never persisted territory_subject (always null in
    the raw JSON), but the underlying match artifact still carries the
    same full per-cell statistics every version's result.json has always
    carried, so behavior should recover real values from Tier 2 despite
    v1's Tier-1 gap."""

    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")

    from battle_engine.agent_test import TESTED_AGENT_SLOT, test_agent
    from battle_engine.results import WINNER_TIE_SENTINEL

    outcome = test_agent(
        "candidate", opponent="opponent", seed=1, ticks=10, timeout=None, trace=False,
        run_dir=tmp_path / "eval-out" / "matches" / "cell-1", data_root=tmp_path,
    )
    match_result = outcome.match_result
    eval_dir = tmp_path / "eval-out"
    cell = {
        "schedule_id": "evaluation-cell_deadbeef",
        "subject_role": "candidate",
        "subject_id": "candidate",
        "opponent_id": "opponent",
        "seed": 1,
        "artifact_dir": "matches/cell-1",
        "status": "completed",
        "outcome": (
            "tie" if match_result.winner == WINNER_TIE_SENTINEL
            else ("win" if match_result.winner == TESTED_AGENT_SLOT else "loss")
        ),
        "match_id": match_result.match_id,
        "result_id": match_result.result_id,
        "ticks_run": match_result.ticks_run,
        "score_subject": float(match_result.score.get(TESTED_AGENT_SLOT, 0)),
        "score_opponent": float(match_result.score.get("B", 0)),
        "territory_subject": None,  # v1 never tracked this -- Tier 1 gap
        "territory_opponent": None,
        "error_code": None,
        "error_message": None,
    }
    data = {
        "schema": "bytefray.evaluation",
        "schema_version": 1,
        "evaluation_id": "evaluation_deadbeefcafefeed00000000",
        "candidate_id": "candidate",
        "baseline_id": None,
        "opponent_ids": ["opponent"],
        "seeds": [1],
        "ticks": 10,
        "matrix_size": 1,
        "project": {"version": "0.6.1"},
        "cells": [cell],
        "aggregates": [],
        "comparison": [],
        "complete": True,
    }
    path = eval_dir / "evaluation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return path


def test_behavior_recovers_from_v1_artifact_despite_missing_tier1_territory(tmp_path: Path):
    path = _v1_fixture_with_real_result(tmp_path)
    summary = adapt_v1(path)
    assert summary.schema.schema_version == 1
    refs = cell_refs_for_behavior(summary)
    assert len(refs) == 1
    assert refs[0].territory_last_fallback is None  # confirms the v1 Tier-1 gap is real

    from battle_engine.evaluation_behavior import analyze_behavior

    analysis = analyze_behavior(summary.candidate_id, summary.baseline_id, refs)
    overall = analysis.candidate_overall
    assert overall.available_count == 1
    # Recovered from the real result.json (Tier 2), not the null Tier-1 field.
    assert overall.dimension("territory_last_pct").mean is not None
    assert overall.dimension("survival_fraction").mean is not None


def test_cli_show_no_behavior_flag_skips_computation(tmp_path: Path, capsys):
    output_dir = tmp_path / "eval-out"
    _run(tmp_path, output_dir)

    code = evaluations_main(["show", str(output_dir), "--no-behavior"])
    out = capsys.readouterr().out
    assert code == 0
    assert "behavior:" not in out

    code = evaluations_main(["show", str(output_dir), "--no-behavior", "--json"])
    out = capsys.readouterr().out
    assert code == 0
    assert json.loads(out)["behavior"] is None


def test_cli_show_is_not_dramatically_slower_with_behavior_than_without_result_json(tmp_path: Path, capsys):
    """Not a strict performance gate (machine-dependent), just a basic
    sanity bound: computing behavior for a small (12-cell) evaluation via
    `show` must complete quickly, consistent with Sec 24's "cheap per-cell
    result.json read, not a replay traversal" design."""

    output_dir = tmp_path / "eval-out"
    _run(tmp_path, output_dir, seeds=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12))
    started = time.monotonic()
    code = evaluations_main(["show", str(output_dir), "--json"])
    elapsed = time.monotonic() - started
    capsys.readouterr()
    assert code == 0
    assert elapsed < 5.0
