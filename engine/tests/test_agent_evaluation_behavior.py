"""Phase 5 behavior-profile integration tests against real ``EvaluationService``
runs and the live ``agents evaluate`` CLI (docs/V1_6_PHASE5_BEHAVIOR_ANALYSIS.md).

Complements ``test_evaluation_behavior.py`` (pure unit tests against
hand-built fixtures): this file exercises real match execution -- a tiny,
scripted always-write agent whose write count is exactly known -- so
dimension values can be cross-checked against an independently computed
expectation, not merely against the module's own arithmetic.
"""

from __future__ import annotations

import json
from pathlib import Path

from battle_engine.agent_evaluation import (
    EvaluationRequest,
    EvaluationService,
)
from battle_engine.agent_evaluation import (
    main as evaluate_main,
)
from battle_engine.evaluation_behavior import analyze_behavior, cell_ref_from_evaluation_cell
from battle_engine.result_model import read_result

WRITE_ACTION = "AgentAction(ActionKind.WRITE, 0, 1)"
NOP_ACTION = "AgentAction(ActionKind.NOP)"


def _write_agent(root: Path, name: str, action: str) -> None:
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


def _request(root: Path, output_dir: Path, **overrides) -> EvaluationRequest:
    defaults: dict = {
        "candidate_id": "writer_agent",
        "opponent_ids": ("opp_a",),
        "seeds": (1, 2),
        "output_dir": output_dir,
        "ticks": 20,
        "data_root": root,
        "both_orientations": False,
    }
    defaults.update(overrides)
    return EvaluationRequest(**defaults)


def test_writes_per_tick_matches_independently_read_result_json(tmp_path: Path):
    """The always-write candidate's writes_per_tick must equal
    mem_writes/ticks_run computed by reading each cell's own result.json
    directly in the test -- an independent oracle, not the module's own
    arithmetic reused against itself."""

    _write_agent(tmp_path, "writer_agent", WRITE_ACTION)
    _write_agent(tmp_path, "opp_a", NOP_ACTION)
    output_dir = tmp_path / "eval-out"
    result = EvaluationService().run(_request(tmp_path, output_dir))
    assert not result.failed_cells

    refs = [cell_ref_from_evaluation_cell(cell) for cell in result.cells if cell.is_scored]
    analysis = analyze_behavior("writer_agent", None, refs)

    expected_writes = []
    expected_ticks = []
    for cell in result.cells:
        envelope = read_result(cell.artifact_dir / "result.json")
        subject_entrant = next(e for e in envelope.entrants if e["agent_id"] == "A")
        expected_writes.append(subject_entrant["statistics"]["mem_writes"])
        expected_ticks.append(envelope.ticks)
    expected_writes_per_tick = sum(expected_writes) / sum(expected_ticks)

    writes_per_tick = analysis.candidate_overall.dimension("writes_per_tick")
    # mean-of-ratios (per-cell writes/ticks then averaged) vs.
    # ratio-of-sums (aggregate then divide) can differ when ticks_run
    # varies per cell; both cells here run the full fixed tick budget
    # (no early termination for a NOP opponent that never dies), so they
    # coincide -- assert the per-cell values agree individually too, not
    # just the aggregate mean.
    for expected in (w / t for w, t in zip(expected_writes, expected_ticks, strict=True)):
        assert expected == writes_per_tick.mean
    assert writes_per_tick.mean == expected_writes_per_tick


def test_kills_are_structurally_zero_for_python_agents(tmp_path: Path):
    """Python-kind Ruleset-v1 matches have no kill mechanic (no WRITE-based
    attack; ActionKind exposes no combat verb) -- this is a documented
    structural fact of the engine (see agents/hunter/agent.py's own
    docstring), not a data-quality problem Phase 5 should paper over.
    Recorded here as a real, disclosed validation finding."""

    _write_agent(tmp_path, "writer_agent", WRITE_ACTION)
    _write_agent(tmp_path, "opp_a", WRITE_ACTION)
    output_dir = tmp_path / "eval-out"
    result = EvaluationService().run(_request(tmp_path, output_dir))
    refs = [cell_ref_from_evaluation_cell(cell) for cell in result.cells if cell.is_scored]
    analysis = analyze_behavior("writer_agent", None, refs)
    kills = analysis.candidate_overall.dimension("kills_per_match")
    deaths = analysis.candidate_overall.dimension("deaths_per_match")
    assert kills.mean == 0.0
    assert deaths.mean == 0.0


def test_survival_fraction_is_one_when_agent_never_halts(tmp_path: Path):
    _write_agent(tmp_path, "writer_agent", WRITE_ACTION)
    _write_agent(tmp_path, "opp_a", NOP_ACTION)
    output_dir = tmp_path / "eval-out"
    result = EvaluationService().run(_request(tmp_path, output_dir))
    refs = [cell_ref_from_evaluation_cell(cell) for cell in result.cells if cell.is_scored]
    analysis = analyze_behavior("writer_agent", None, refs)
    survival = analysis.candidate_overall.dimension("survival_fraction")
    assert survival.mean == 1.0


def test_workers_1_and_workers_2_produce_identical_behavior_profile(tmp_path: Path):
    """Determinism under concurrency (Sec 23 of the design doc): behavior
    analysis is derived purely from already-written per-cell artifacts, so
    it must be byte-identical (as JSON) regardless of how many worker
    subprocesses actually produced them."""

    _write_agent(tmp_path, "writer_agent", WRITE_ACTION)
    _write_agent(tmp_path, "opp_a", NOP_ACTION)
    _write_agent(tmp_path, "opp_b", NOP_ACTION)

    request_serial = _request(
        tmp_path, tmp_path / "eval-serial",
        opponent_ids=("opp_a", "opp_b"), seeds=(1, 2, 3), workers=1,
    )
    request_parallel = _request(
        tmp_path, tmp_path / "eval-parallel",
        opponent_ids=("opp_a", "opp_b"), seeds=(1, 2, 3), workers=2,
    )
    result_serial = EvaluationService().run(request_serial)
    result_parallel = EvaluationService().run(request_parallel)

    refs_serial = [cell_ref_from_evaluation_cell(c) for c in result_serial.cells if c.is_scored]
    refs_parallel = [cell_ref_from_evaluation_cell(c) for c in result_parallel.cells if c.is_scored]
    analysis_serial = analyze_behavior("writer_agent", None, refs_serial).to_json()
    analysis_parallel = analyze_behavior("writer_agent", None, refs_parallel).to_json()
    assert analysis_serial == analysis_parallel


def test_live_cli_prints_behavior_block(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    _write_agent(tmp_path, "writer_agent", WRITE_ACTION)
    _write_agent(tmp_path, "opp_a", NOP_ACTION)
    code = evaluate_main(
        [
            "writer_agent",
            "--opponents", "opp_a",
            "--seeds", "1",
            "--ticks", "20",
            "--single-orientation",
            "--output", str(tmp_path / "eval-out"),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "behavior:" in out
    assert "survival:" in out
    assert "kills: 0.00/match" in out


def test_live_cli_behavior_block_present_without_baseline(tmp_path: Path, capsys, monkeypatch):
    """Behavior must not be gated behind --baseline the way evidence: is --
    it is a description of the candidate alone, computable with or without
    a baseline (Sec 6 of the design doc: outcome-comparison concerns
    should never gate a behavior-only measurement).

    Pinned to explicit --ruleset bytefray-rules-1: v2 methodology prints its
    own unrelated "capture/core evidence:" block regardless of --baseline,
    which would collide with this test's substring check on "evidence:" --
    this test is about Phase 4's baseline-gated comparison block, not v2's
    capture evidence.
    """

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    _write_agent(tmp_path, "writer_agent", WRITE_ACTION)
    _write_agent(tmp_path, "opp_a", NOP_ACTION)
    code = evaluate_main(
        [
            "writer_agent",
            "--opponents", "opp_a",
            "--seeds", "1",
            "--ticks", "20",
            "--single-orientation",
            "--output", str(tmp_path / "eval-out"),
            "--ruleset", "bytefray-rules-1",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "behavior:" in out
    assert "evidence:" not in out  # no baseline -> Phase 4's evidence block is absent
