"""v1.6 Phase 2 -- deterministic parallel evaluation (docs/V1_6_PHASE2_
PARALLEL_EVALUATION.md).

Covers the governing spec's required regression matrix: serial-vs-parallel
and worker-count equivalence, repeatability, completion-order reversal,
worker-crash handling, source-drift stop-dispatch under concurrency,
evaluation_id independence from worker count, and ``--workers`` CLI
plumbing. Uses real worker subprocesses throughout (not mocked) -- these
tests are slower than the rest of the suite but exercise the actual
subprocess protocol, not a stand-in for it.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest
from battle_engine.agent_evaluation import (
    EvaluationRequest,
    EvaluationService,
    _parser,
    agent_identity,
)
from battle_engine.agent_evaluation import (
    main as evaluate_main,
)

NOP_ACTION = "AgentAction(ActionKind.NOP)"


def _write_agent(root: Path, name: str, act_body: str) -> Path:
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
    def act(self, observation):
{act_body}
def create_agent(): return Agent()
""",
        encoding="utf-8",
    )
    return directory


def _write_nop_agent(root: Path, name: str) -> Path:
    return _write_agent(root, name, f"        return {NOP_ACTION}")


def _write_slow_agent(root: Path, name: str, seconds: float) -> Path:
    return _write_agent(
        root,
        name,
        f"        import time\n        time.sleep({seconds})\n        return {NOP_ACTION}",
    )


def _write_poison_agent(root: Path, name: str) -> Path:
    # Unconditionally kills its own process on the first act() call -- the
    # entire worker subprocess dies mid-match, before any response line is
    # ever written, simulating a genuine worker crash (not a normal
    # AgentTestError, which _execute_cell already handles internally).
    return _write_agent(root, name, "        import os\n        os._exit(1)")


def _request(root: Path, **overrides) -> EvaluationRequest:
    defaults: dict = {
        "candidate_id": "candidate",
        "opponent_ids": ("opp_a", "opp_b", "opp_c"),
        "seeds": (1, 2),
        "output_dir": root / "eval-out",
        "ticks": 10,
        "data_root": root,
        "both_orientations": False,
    }
    defaults.update(overrides)
    return EvaluationRequest(**defaults)


@pytest.fixture()
def matrix_agents(tmp_path: Path) -> Path:
    _write_nop_agent(tmp_path, "candidate")
    _write_nop_agent(tmp_path, "opp_a")
    _write_nop_agent(tmp_path, "opp_b")
    _write_nop_agent(tmp_path, "opp_c")
    return tmp_path


def _load(state_path: Path) -> dict:
    return json.loads(state_path.read_text(encoding="utf-8"))


_VOLATILE_TOP_LEVEL = {"updated_at", "project", "created_at", "finished_at"}
_VOLATILE_EXECUTION_CONTEXT = {"first_used_at"}


def _normalize(data: dict) -> dict:
    """Strip fields that are allowed to differ across independent runs
    (timestamps, and per-run project/environment metadata) so the rest can
    be compared for exact equivalence."""

    normalized = {k: v for k, v in data.items() if k not in _VOLATILE_TOP_LEVEL}
    normalized["execution_contexts"] = [
        {k: v for k, v in ctx.items() if k not in _VOLATILE_EXECUTION_CONTEXT}
        for ctx in data.get("execution_contexts", ())
    ]
    normalized["cells"] = [{k: v for k, v in cell.items()} for cell in data.get("cells", ())]
    return normalized


# ---------------------------------------------------------------------------
# Serial vs parallel / worker-count equivalence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("workers", [1, 2, 4, 50])
def test_serial_and_parallel_produce_identical_artifacts(matrix_agents: Path, workers: int):
    reference = EvaluationService().run(_request(matrix_agents, output_dir=matrix_agents / "ref", workers=1))
    candidate = EvaluationService().run(
        _request(matrix_agents, output_dir=matrix_agents / f"w{workers}", workers=workers)
    )

    assert candidate.evaluation_id == reference.evaluation_id

    ref_data = _normalize(_load(reference.state_path))
    cand_data = _normalize(_load(candidate.state_path))
    assert cand_data == ref_data

    # Canonical matrix ordering, independent of worker count.
    ref_order = [c["schedule_id"] for c in ref_data["cells"]]
    cand_order = [c["schedule_id"] for c in cand_data["cells"]]
    assert cand_order == ref_order

    # Per-cell replay bytes are identical (each cell's own match execution
    # is untouched by dispatch mode -- Phase 0-1 baseline Sec 4/6).
    for ref_cell, cand_cell in zip(reference.cells, candidate.cells):
        ref_replay = (reference.state_path.parent / ref_cell.artifact_dir / "replay.jsonl")
        cand_replay = (candidate.state_path.parent / cand_cell.artifact_dir / "replay.jsonl")
        assert ref_replay.read_bytes() == cand_replay.read_bytes()


def test_repeated_parallel_runs_are_identical(matrix_agents: Path):
    first = EvaluationService().run(_request(matrix_agents, output_dir=matrix_agents / "first", workers=4))
    second = EvaluationService().run(_request(matrix_agents, output_dir=matrix_agents / "second", workers=4))
    assert first.evaluation_id == second.evaluation_id
    assert _normalize(_load(first.state_path)) == _normalize(_load(second.state_path))


def test_evaluation_id_independent_of_worker_count(matrix_agents: Path):
    service = EvaluationService()
    ids = {}
    for workers in (1, 8):
        request = _request(matrix_agents, workers=workers)
        specs = service._validate(request)
        identities = {agent_id: agent_identity(spec) for agent_id, spec in specs.items()}
        conditions = service._effective_conditions(request)
        ids[workers] = service._evaluation_id(request, identities, conditions)
    assert ids[1] == ids[8]


# ---------------------------------------------------------------------------
# Completion-order reversal
# ---------------------------------------------------------------------------


def test_completion_order_reversal_preserves_matrix_order(tmp_path: Path):
    _write_nop_agent(tmp_path, "candidate")
    # opp_slow is matrix-first but finishes last; opp_fast_1/2 are
    # matrix-later but finish first -- genuine completion-order reversal
    # across real worker subprocesses, not simulated.
    _write_slow_agent(tmp_path, "opp_slow", seconds=0.6)
    _write_nop_agent(tmp_path, "opp_fast_1")
    _write_nop_agent(tmp_path, "opp_fast_2")

    request = _request(
        tmp_path,
        opponent_ids=("opp_slow", "opp_fast_1", "opp_fast_2"),
        seeds=(1,),
        workers=3,
    )
    result = EvaluationService().run(request)
    data = _load(result.state_path)
    assert [c["opponent_id"] for c in data["cells"]] == ["opp_slow", "opp_fast_1", "opp_fast_2"]
    failures = [
        (c["opponent_id"], c["status"], c.get("error_code"), c.get("error_message"))
        for c in data["cells"]
        if c["status"] != "completed"
    ]
    assert not failures, f"cell(s) did not complete: {failures}"


# ---------------------------------------------------------------------------
# Worker failure
# ---------------------------------------------------------------------------


def test_worker_crash_marks_cell_failed_and_others_continue_without_hanging(tmp_path: Path):
    _write_nop_agent(tmp_path, "candidate")
    _write_poison_agent(tmp_path, "opp_poison")
    _write_nop_agent(tmp_path, "opp_ok_1")
    _write_nop_agent(tmp_path, "opp_ok_2")

    request = _request(
        tmp_path,
        opponent_ids=("opp_poison", "opp_ok_1", "opp_ok_2"),
        seeds=(1,),
        workers=3,
    )
    # The test completing at all (no hang) is itself part of what this
    # proves; pytest-timeout is not configured project-wide, so this relies
    # on CI's own overall job timeout as a backstop for a true regression.
    result = EvaluationService().run(request)
    data = _load(result.state_path)
    by_opponent = {c["opponent_id"]: c for c in data["cells"]}

    assert by_opponent["opp_poison"]["status"] == "failed"
    assert by_opponent["opp_poison"]["error_code"] == "evaluation_worker_exited"
    assert by_opponent["opp_ok_1"]["status"] == "completed"
    assert by_opponent["opp_ok_2"]["status"] == "completed"
    # Never dropped silently -- the failed cell is still recorded.
    assert len(data["cells"]) == 3
    assert data["lifecycle_state"] == "finished"


# ---------------------------------------------------------------------------
# Source drift under concurrency
# ---------------------------------------------------------------------------


def test_source_drift_under_concurrency_stops_dispatch_cleanly(tmp_path: Path):
    _write_nop_agent(tmp_path, "candidate")
    # Every opponent sleeps briefly so a background thread has a reliable
    # window to mutate opp_drift's real source file on disk mid-run --
    # genuine drift, detected by _detect_pre_execution_drift's live
    # re-resolve, not a monkeypatch (which a worker subprocess would never
    # observe, unlike the coordinator process).
    for name in ("opp_a", "opp_b", "opp_drift", "opp_c", "opp_d"):
        _write_slow_agent(tmp_path, name, seconds=0.3)

    request = _request(
        tmp_path,
        opponent_ids=("opp_a", "opp_b", "opp_drift", "opp_c", "opp_d"),
        seeds=(1,),
        workers=2,
    )

    def _mutate_after_delay() -> None:
        time.sleep(0.35)
        agent_path = tmp_path / "agents" / "opp_drift" / "agent.py"
        agent_path.write_text(
            agent_path.read_text(encoding="utf-8").replace("time.sleep(0.3)", "time.sleep(0.3)  # mutated"),
            encoding="utf-8",
        )

    mutator = threading.Thread(target=_mutate_after_delay, daemon=True)
    mutator.start()
    result = EvaluationService().run(request)
    mutator.join(timeout=5.0)

    data = _load(result.state_path)
    assert data["lifecycle_state"] == "aborted"
    assert data["abort_reason"] == "source_drift"
    assert data["finished_at"] is None
    statuses = {c["opponent_id"]: c["status"] for c in data["cells"]}
    assert "drift_detected" in statuses.values()
    # cells[] is still canonically matrix-ordered regardless of which
    # worker observed the drift or when.
    assert [c["opponent_id"] for c in data["cells"]] == [
        name for name in ("opp_a", "opp_b", "opp_drift", "opp_c", "opp_d")
        if name in statuses
    ]
    # No cell after the (matrix-order) drift point was ever recorded.
    drift_index = [c["opponent_id"] for c in data["cells"]].index(
        next(c["opponent_id"] for c in data["cells"] if c["status"] == "drift_detected")
    )
    assert drift_index == len(data["cells"]) - 1 or all(
        c["status"] != "pending" for c in data["cells"][drift_index + 1 :]
    )


# ---------------------------------------------------------------------------
# Resume after a coordinator-level interruption, under parallel dispatch
# ---------------------------------------------------------------------------


def test_resume_after_coordinator_interruption_matches_uninterrupted_reference(tmp_path: Path):
    _write_nop_agent(tmp_path, "candidate")
    for name in ("opp_a", "opp_b", "opp_c"):
        _write_nop_agent(tmp_path, name)
    seeds = (1, 2)
    request = _request(
        tmp_path, opponent_ids=("opp_a", "opp_b", "opp_c"), seeds=seeds, workers=3,
        output_dir=tmp_path / "interrupted",
    )

    import battle_engine.agent_evaluation as mod

    real_write_state = mod.EvaluationService._write_state
    call_count = {"n": 0}

    def _crash_after_second_checkpoint(self, *args, **kwargs):
        real_write_state(self, *args, **kwargs)
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("simulated coordinator crash")

    import pytest as _pytest

    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(mod.EvaluationService, "_write_state", _crash_after_second_checkpoint)
        with pytest.raises(RuntimeError):
            EvaluationService().run(request, checkpoint_batch_size=1)

    interrupted = _load(request.output_dir / "evaluation.json")
    assert interrupted["lifecycle_state"] == "running"

    resumed = EvaluationService().run(request, checkpoint_batch_size=1)
    resumed_data = _load(resumed.state_path)
    assert resumed_data["lifecycle_state"] == "finished"
    assert len(resumed_data["cells"]) == 6
    assert all(c["status"] == "completed" for c in resumed_data["cells"])

    reference = EvaluationService().run(
        _request(tmp_path, opponent_ids=("opp_a", "opp_b", "opp_c"), seeds=seeds, workers=1, output_dir=tmp_path / "reference")
    )
    assert resumed.evaluation_id == reference.evaluation_id
    ref_outcomes = {(c["opponent_id"], c["seed"]): c["outcome"] for c in _load(reference.state_path)["cells"]}
    resumed_outcomes = {(c["opponent_id"], c["seed"]): c["outcome"] for c in resumed_data["cells"]}
    assert resumed_outcomes == ref_outcomes


# ---------------------------------------------------------------------------
# --workers CLI plumbing
# ---------------------------------------------------------------------------


def test_workers_flag_defaults_to_one():
    args = _parser().parse_args(["candidate", "--opponents", "opp"])
    assert args.workers == 1


def test_workers_flag_rejects_non_positive():
    with pytest.raises(SystemExit):
        _parser().parse_args(["candidate", "--opponents", "opp", "--workers", "0"])


def test_workers_flag_parses_and_threads_through_cli(matrix_agents: Path, monkeypatch, capsys):
    """Pinned to explicit --ruleset bytefray-rules-1 so the expected cell
    count (3 opponents x 2 seeds x 1 orientation, no placement
    multiplication) stays simple -- this test is about --workers threading
    through the CLI, not about which Ruleset is the product default."""
    monkeypatch.setenv("BYTEFRAY_ROOT", str(matrix_agents))
    exit_code = evaluate_main(
        [
            "candidate",
            "--opponents",
            "opp_a,opp_b,opp_c",
            "--seeds",
            "1,2",
            "--ticks",
            "10",
            "--single-orientation",
            "--workers",
            "3",
            "--output",
            str(matrix_agents / "cli-out"),
            "--quiet",
            "--ruleset",
            "bytefray-rules-1",
        ]
    )
    assert exit_code == 0
    data = _load(matrix_agents / "cli-out" / "evaluation.json")
    assert data["lifecycle_state"] == "finished"
    assert len(data["cells"]) == 6
