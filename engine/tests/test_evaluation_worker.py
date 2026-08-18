"""``battle_engine.evaluation_worker`` -- the v1.6 Phase 2 parallel-evaluation
worker protocol (docs/V1_6_PHASE2_PARALLEL_EVALUATION.md).

Mirrors ``test_agent_worker.py``'s structure: white-box tests of
``EvaluationCellWorkerHandle._call``'s response parsing (no subprocess),
in-process tests of the worker-side ``run_worker`` loop (via ``stdin``/
``stdout`` injection, no subprocess), and a small number of real-subprocess
round-trip tests for the parts that only a genuine child process can prove
(actual worker death, actual containment).
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from _hang_safety import hang_safety_timeout
from battle_engine.agent_evaluation import EvaluationCell
from battle_engine.agent_worker import WorkerCallResult, WorkerCallStatus
from battle_engine.evaluation_worker import (
    EvaluationCellWorkerHandle,
    _cell_from_wire,
    _cell_to_wire,
    run_worker,
)

NOP_SOURCE = """
from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        pass

    def act(self, observation):
        return AgentAction(ActionKind.NOP)

def create_agent():
    return Agent()
"""


def _write_agent(root: Path, name: str, source: str = NOP_SOURCE) -> None:
    directory = root / "agents" / name
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text(
        json.dumps(
            {"kind": "python", "api_version": 1, "entrypoint": "agent.py:create_agent", "version": "1.0"}
        ),
        encoding="utf-8",
    )
    (directory / "agent.py").write_text(source, encoding="utf-8")


def _cell(tmp_path: Path, schedule_id: str = "sched-1") -> EvaluationCell:
    return EvaluationCell(
        schedule_id=schedule_id,
        subject_role="candidate",
        subject_id="candidate",
        opponent_id="opponent",
        seed=1,
        artifact_dir=tmp_path / "matches" / schedule_id,
    )


# ---------------------------------------------------------------------------
# Wire (de)serialization
# ---------------------------------------------------------------------------


def test_cell_wire_round_trip(tmp_path: Path):
    cell = _cell(tmp_path)
    payload = _cell_to_wire(cell)
    assert payload["artifact_dir"] == str(cell.artifact_dir)
    restored = _cell_from_wire(payload)
    assert restored == cell


# ---------------------------------------------------------------------------
# Parent-side response parsing (white-box, no subprocess -- mirrors
# test_agent_worker.py's identical technique for AgentWorkerHandle._call)
# ---------------------------------------------------------------------------


class _FakeStdin:
    def write(self, _data: str) -> None:
        pass

    def flush(self) -> None:
        pass


class _FakeProc:
    stdin = _FakeStdin()

    def poll(self) -> int | None:
        return None


def test_call_reports_protocol_error_on_malformed_response(tmp_path: Path):
    handle = EvaluationCellWorkerHandle()
    handle._proc = _FakeProc()  # type: ignore[assignment]

    handle._queue.put("not valid json\n")
    result: WorkerCallResult = handle._call({"cmd": "run_cell"}, timeout=1.0)
    assert result.status is WorkerCallStatus.PROTOCOL_ERROR

    handle._queue.put('{"no_ok_key": true}\n')
    result = handle._call({"cmd": "run_cell"}, timeout=1.0)
    assert result.status is WorkerCallStatus.PROTOCOL_ERROR


def test_call_reports_exited_on_eof(tmp_path: Path):
    from battle_engine.evaluation_worker import _EOF

    handle = EvaluationCellWorkerHandle()
    handle._proc = _FakeProc()  # type: ignore[assignment]
    handle._queue.put(_EOF)
    result = handle._call({"cmd": "run_cell"}, timeout=1.0)
    assert result.status is WorkerCallStatus.EXITED


def test_call_reports_failed_on_well_formed_ok_false(tmp_path: Path):
    handle = EvaluationCellWorkerHandle()
    handle._proc = _FakeProc()  # type: ignore[assignment]
    handle._queue.put(json.dumps({"ok": False, "diagnostic": {"code": "x", "message": "y"}}) + "\n")
    result = handle._call({"cmd": "run_cell"}, timeout=1.0)
    assert result.status is WorkerCallStatus.FAILED


# ---------------------------------------------------------------------------
# Worker-side loop (in-process, via stdin/stdout injection -- no subprocess)
# ---------------------------------------------------------------------------


def _run_worker_once(request: dict) -> dict:
    stdin = io.StringIO(json.dumps(request) + "\n" + json.dumps({"cmd": "shutdown"}) + "\n")
    stdout = io.StringIO()
    run_worker(stdin=stdin, stdout=stdout)
    lines = [line for line in stdout.getvalue().splitlines() if line.strip()]
    assert len(lines) == 1
    return json.loads(lines[0])


def test_run_worker_rejects_malformed_json():
    stdin = io.StringIO("not json at all\n" + json.dumps({"cmd": "shutdown"}) + "\n")
    stdout = io.StringIO()
    run_worker(stdin=stdin, stdout=stdout)
    lines = [line for line in stdout.getvalue().splitlines() if line.strip()]
    response = json.loads(lines[0])
    assert response["ok"] is False
    assert response["diagnostic"]["code"] == "evaluation_worker_protocol_error"


def test_run_worker_rejects_unknown_command():
    response = _run_worker_once({"cmd": "not_a_real_command"})
    assert response["ok"] is False
    assert response["diagnostic"]["code"] == "evaluation_worker_protocol_error"


def test_run_worker_shutdown_returns_cleanly_with_no_response():
    stdin = io.StringIO(json.dumps({"cmd": "shutdown"}) + "\n")
    stdout = io.StringIO()
    exit_code = run_worker(stdin=stdin, stdout=stdout)
    assert exit_code == 0
    assert stdout.getvalue() == ""


def test_run_worker_executes_run_cell_and_responds(tmp_path: Path):
    _write_agent(tmp_path, "candidate")
    _write_agent(tmp_path, "opponent")
    cell = _cell(tmp_path)
    response = _run_worker_once(
        {
            "cmd": "run_cell",
            "cell": _cell_to_wire(cell),
            "ticks": 10,
            "data_root": str(tmp_path),
            "planned_identities": {},
        }
    )
    assert response["ok"] is True
    assert response["cell"]["status"] == "completed"
    assert response["cell"]["schedule_id"] == "sched-1"
    assert response["execution_context"] is not None
    assert response["execution_context"]["context_id"]


# ---------------------------------------------------------------------------
# Real subprocess round trip
# ---------------------------------------------------------------------------


def test_submit_cell_real_subprocess_round_trip(tmp_path: Path):
    _write_agent(tmp_path, "candidate")
    _write_agent(tmp_path, "opponent")
    cell = _cell(tmp_path)
    handle = EvaluationCellWorkerHandle()
    with hang_safety_timeout(30):
        try:
            handle.start()
            result = handle.submit_cell(cell, ticks=10, data_root=tmp_path, planned_identities={})
            assert result.status is WorkerCallStatus.OK
            assert result.payload is not None
            resolved = _cell_from_wire(result.payload["cell"])
            assert resolved.status == "completed"
            assert resolved.schedule_id == cell.schedule_id
        finally:
            handle.close()


def test_worker_exit_mid_cell_is_reported_as_exited(tmp_path: Path):
    _write_agent(tmp_path, "candidate")
    _write_agent(
        tmp_path,
        "opponent",
        source="""
import os

class Agent:
    def reset(self, context):
        pass

    def act(self, observation):
        os._exit(1)

def create_agent():
    return Agent()
""",
    )
    cell = _cell(tmp_path)
    handle = EvaluationCellWorkerHandle()
    with hang_safety_timeout(30):
        try:
            handle.start()
            result = handle.submit_cell(cell, ticks=10, data_root=tmp_path, planned_identities={})
            assert result.status is WorkerCallStatus.EXITED
        finally:
            handle.close()


def test_close_without_start_is_a_no_op():
    EvaluationCellWorkerHandle().close()


def test_multiple_handles_all_terminate_on_close(tmp_path: Path):
    _write_agent(tmp_path, "candidate")
    _write_agent(tmp_path, "opponent")
    handles = [EvaluationCellWorkerHandle() for _ in range(3)]
    with hang_safety_timeout(30):
        try:
            for handle in handles:
                handle.start()
            for handle in handles:
                cell = _cell(tmp_path, schedule_id=f"sched-{id(handle)}")
                result = handle.submit_cell(cell, ticks=5, data_root=tmp_path, planned_identities={})
                assert result.status is WorkerCallStatus.OK
        finally:
            for handle in handles:
                handle.close()
        for handle in handles:
            assert handle.exit_code is not None


def test_worker_main_rejects_unexpected_arguments():
    from battle_engine.evaluation_worker import main

    assert main(["unexpected"]) == 2
