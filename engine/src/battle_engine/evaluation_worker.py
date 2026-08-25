"""Whole-process-lifetime worker subprocess for parallel evaluation-cell execution.

v1.6 Phase 2 (see ``docs/V1_6_PHASE2_PARALLEL_EVALUATION.md`` and the Phase
0-1 baseline it builds on, ``docs/V1_6_PHASE1_EVALUATION_SCALE_BASELINE.md``
Sec 4/Sec 7). Reuses the exact subprocess-worker pattern already proven by
:mod:`battle_engine.agent_worker` -- spawn-safe, argument-list-only, frozen-
or-source command resolution via :func:`battle_engine.launchers.
build_agents_command`, a hidden ``bytefray agents _evaluation_worker`` verb,
newline-delimited JSON on stdin/stdout, and Windows Job Object / POSIX
parent-death containment via :mod:`battle_engine.process_containment` -- but
carries a completely different, much simpler protocol: **one request is one
whole ``EvaluationCell`` job** (an entire match, executed via the existing
``EvaluationService._execute_cell``), not a live per-tick ``load``/``reset``/
``act`` exchange. No ``multiprocessing`` is used, for the same reason
``agent_worker.py`` avoids it: the worker is just another invocation of the
already-frozen executable, so there is no Windows ``freeze_support()``
concern.

Deliberately does **not** apply any protocol-level timeout to a cell-
execution round trip (``submit_cell``'s ``_call`` uses ``timeout=None``) --
this mirrors ``agent_test.test_agent(..., timeout=None, ...)``'s existing,
deliberate contract that evaluation cells are unsupervised and untraced by
design (Phase 0-1 baseline Sec 2). Worker death is detected via EOF/broken
pipe, exactly as ``agent_worker.py`` already does for its own timeout-less
failure paths, never via an artificial deadline that would silently change
what evaluation cells actually measure.

Coordinator responsibilities (matrix construction, resume-state decisions,
checkpoint persistence, execution-context deduplication, drift/failure
policy) all stay in ``agent_evaluation.EvaluationService.run`` -- this module
is intentionally "dumb": it knows how to run one cell and report the result,
nothing about evaluation-wide state.
"""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
from collections import deque
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from battle_engine.agent_worker import WorkerCallResult, WorkerCallStatus
from battle_engine.launchers import build_agents_command
from battle_engine.process_containment import (
    ChildLifetimeBinding,
    bind_child_to_parent_lifetime,
    die_with_parent,
)

WORKER_SUBCOMMAND = "_evaluation_worker"

_EOF = object()


@dataclass(frozen=True)
class WorkerFailure:
    """A dispatcher thread's own worker died (exited/broken pipe/protocol error).

    Distinct from a cell-level failure (``EvaluationCell(status="failed")``,
    produced when the worker process is alive and responded but the cell
    itself could not be executed, e.g. an ``AgentTestError`` -- that case
    never reaches this type, it is already a normal, well-formed response).
    """

    schedule_id: str
    status: WorkerCallStatus
    detail: str


def _cell_to_wire(cell: Any) -> dict[str, Any]:
    payload = asdict(cell)
    payload["artifact_dir"] = str(cell.artifact_dir)
    return payload


def _cell_from_wire(payload: Mapping[str, Any]) -> Any:
    from battle_engine.agent_evaluation import EvaluationCell

    data = dict(payload)
    data["artifact_dir"] = Path(data["artifact_dir"])
    return EvaluationCell(**data)


# --------------------------------------------------------------------------
# Parent (coordinator) side.
# --------------------------------------------------------------------------


class EvaluationCellWorkerHandle:
    """Parent-side handle to one whole-process-lifetime evaluation-cell worker.

    Structurally identical to ``agent_worker.AgentWorkerHandle`` (same
    reader-thread-plus-queue pattern, same lifetime binding, same
    kill/close discipline) -- deliberately not shared code with it, since
    that module's protocol (live per-tick calls to loaded agent code) is
    semantically a different thing from this one (one call = one whole,
    already-self-contained match). Duplicating the small amount of
    plumbing here keeps each module's protocol simple and independently
    readable, rather than forcing an abstraction that would need to bend to
    fit both shapes.
    """

    def __init__(self) -> None:
        self._proc: subprocess.Popen[str] | None = None
        self._queue: queue.Queue[Any] = queue.Queue()
        self._reader: threading.Thread | None = None
        self._stderr_tail: deque[str] = deque(maxlen=20)
        self._stderr_reader: threading.Thread | None = None
        self._lifetime_binding: ChildLifetimeBinding | None = None

    def start(self) -> None:
        command = build_agents_command(WORKER_SUBCOMMAND, [])
        self._proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._lifetime_binding = bind_child_to_parent_lifetime(self._proc)
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader.start()
        self._stderr_reader = threading.Thread(target=self._read_stderr, daemon=True)
        self._stderr_reader.start()

    def _read_stdout(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        try:
            for line in self._proc.stdout:
                self._queue.put(line)
        except (OSError, ValueError):
            pass
        self._queue.put(_EOF)

    def _read_stderr(self) -> None:
        assert self._proc is not None and self._proc.stderr is not None
        try:
            for line in self._proc.stderr:
                self._stderr_tail.append(line.rstrip("\n"))
        except (OSError, ValueError):
            pass

    @property
    def stderr_tail(self) -> tuple[str, ...]:
        return tuple(self._stderr_tail)

    @property
    def exit_code(self) -> int | None:
        return None if self._proc is None else self._proc.poll()

    def _call(self, request: dict[str, Any], *, timeout: float | None) -> WorkerCallResult:
        assert self._proc is not None and self._proc.stdin is not None
        try:
            self._proc.stdin.write(json.dumps(request))
            self._proc.stdin.write("\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            return WorkerCallResult(WorkerCallStatus.EXITED)

        try:
            line = self._queue.get(timeout=timeout)
        except queue.Empty:
            return WorkerCallResult(WorkerCallStatus.TIMEOUT)
        if line is _EOF:
            return WorkerCallResult(WorkerCallStatus.EXITED)
        try:
            response = json.loads(line)
        except json.JSONDecodeError:
            return WorkerCallResult(WorkerCallStatus.PROTOCOL_ERROR, {"raw": line})
        if not isinstance(response, dict) or "ok" not in response:
            return WorkerCallResult(WorkerCallStatus.PROTOCOL_ERROR, {"raw": line})
        status = WorkerCallStatus.OK if response.get("ok") else WorkerCallStatus.FAILED
        return WorkerCallResult(status, response)

    def submit_cell(
        self,
        cell: Any,
        *,
        ticks: int,
        data_root: Path | None,
        planned_identities: Mapping[str, dict[str, Any]],
        arena_size: int | None = None,
        instr_per_tick: int | None = None,
        locality_reach: int | None = None,
        kill_weight: float | None = None,
    ) -> WorkerCallResult:
        """One blocking round trip: run exactly one evaluation cell.

        No protocol-level timeout -- see the module docstring. Worker death
        (exit, broken pipe) is reported as ``WorkerCallStatus.EXITED``; a
        malformed response as ``PROTOCOL_ERROR``; a well-formed
        ``{"ok": false, ...}`` (the worker's own belt-and-suspenders
        catch-all, expected to be rare) as ``FAILED``.
        """

        return self._call(
            {
                "cmd": "run_cell",
                "cell": _cell_to_wire(cell),
                "ticks": ticks,
                "data_root": str(data_root) if data_root is not None else None,
                "planned_identities": dict(planned_identities),
                # v3 Phase 0D: evaluation-wide execution conditions, carried
                # as explicit wire keys exactly like `ticks` above rather
                # than folded into the cell payload -- a worker must receive
                # the identical values the coordinator resolved, so that
                # `--workers N` and `--workers 1` produce byte-identical
                # results for a non-default arena/action budget. `null` (the
                # key present with a null value, or absent on an older
                # payload) means "executor default", matching `agent_test`.
                "arena_size": arena_size,
                "instr_per_tick": instr_per_tick,
                # v3 Phase 2: additive wire key. A worker reads it back
                # through `.get(...)`, so an omitted key means "no
                # locality" exactly as it did before the key existed.
                "locality_reach": locality_reach,
                # v3 Phase 3: additive wire key, identical contract --
                # `.get(...)` on the worker side means an older coordinator
                # payload (which never sends this key) still means
                # "executor default".
                "kill_weight": kill_weight,
            },
            timeout=None,
        )

    def kill(self) -> None:
        """Unconditional kill, no grace period -- mirrors AgentWorkerHandle.kill."""

        if self._proc is not None and self._proc.poll() is None:
            try:
                self._proc.kill()
            except OSError:
                pass

    def close(self, *, timeout: float = 2.0) -> None:
        """Best-effort graceful shutdown, force-kill on any doubt. Never raises."""

        if self._proc is None:
            return
        if self._proc.poll() is None:
            try:
                if self._proc.stdin is not None:
                    self._proc.stdin.write(json.dumps({"cmd": "shutdown"}) + "\n")
                    self._proc.stdin.flush()
            except (BrokenPipeError, OSError, ValueError):
                pass
            try:
                self._proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.kill()
                try:
                    self._proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    pass
        for stream in (self._proc.stdin, self._proc.stdout, self._proc.stderr):
            try:
                if stream is not None:
                    stream.close()
            except OSError:
                pass
        if self._reader is not None:
            self._reader.join(timeout=timeout)
        if self._stderr_reader is not None:
            self._stderr_reader.join(timeout=timeout)
        if self._lifetime_binding is not None:
            self._lifetime_binding.close()
            self._lifetime_binding = None


# --------------------------------------------------------------------------
# Worker (child process) side.
# --------------------------------------------------------------------------


def _respond(stream: Any, payload: dict[str, Any]) -> None:
    stream.write(json.dumps(payload))
    stream.write("\n")
    stream.flush()


def _handle_run_cell(request: dict[str, Any], out: Any) -> None:
    # Function-local import: agent_evaluation.py needs EvaluationCellWorkerHandle
    # from this module for its coordinator (parallel dispatch), so a module-top
    # import in this direction would be a circular import. This module can
    # safely import agent_evaluation at module scope (it is the "leaf"), but
    # the worker-side dispatch function only needs it lazily, at call time.
    from battle_engine.agent_evaluation import EvaluationService

    cell = _cell_from_wire(request["cell"])
    ticks = request["ticks"]
    data_root = Path(request["data_root"]) if request.get("data_root") else None
    planned_identities = request.get("planned_identities") or {}
    # v3 Phase 0D: `.get(...)` (not `[...]`) so a payload written by an
    # older coordinator -- which never sends these keys -- still means
    # "executor default", the exact behavior it had before this phase.
    arena_size = request.get("arena_size")
    instr_per_tick = request.get("instr_per_tick")
    locality_reach = request.get("locality_reach")
    kill_weight = request.get("kill_weight")

    try:
        result = EvaluationService()._execute_cell(
            cell,
            ticks,
            data_root,
            planned_identities,
            arena_size=arena_size,
            instr_per_tick=instr_per_tick,
            locality_reach=locality_reach,
            kill_weight=kill_weight,
        )
    except Exception as exc:  # belt-and-suspenders: _execute_cell/test_agent
        # already catch nearly everything internally (agent_test.test_agent's
        # own docstring); this should rarely fire.
        _respond(
            out,
            {
                "ok": False,
                "diagnostic": {
                    "code": "evaluation_worker_internal_error",
                    "message": f"{type(exc).__name__}: {exc}"[:240],
                },
            },
        )
        return

    _respond(
        out,
        {
            "ok": True,
            "cell": _cell_to_wire(result.cell),
            "execution_context": (
                result.execution_context.to_dict() if result.execution_context is not None else None
            ),
        },
    )


def run_worker(*, stdin: Any = None, stdout: Any = None) -> int:
    """Run the worker's request/response loop until ``shutdown`` or EOF.

    Redirects ``sys.stdout``/``sys.stdin`` the same way (and for the same
    reason) ``agent_worker.run_worker`` does: evaluated agent code running
    inside ``_execute_cell`` must never be able to corrupt or desynchronize
    the protocol stream via ``print()``/``input()``.
    """

    die_with_parent()
    in_stream = stdin if stdin is not None else sys.stdin
    out_stream = stdout if stdout is not None else sys.stdout
    sys.stdout = sys.stderr
    import io

    sys.stdin = io.StringIO()

    for raw_line in in_stream:
        line = raw_line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            _respond(
                out_stream,
                {
                    "ok": False,
                    "diagnostic": {
                        "code": "evaluation_worker_protocol_error",
                        "message": "invalid JSON request",
                    },
                },
            )
            continue
        cmd = request.get("cmd")
        if cmd == "shutdown":
            return 0
        if cmd == "run_cell":
            _handle_run_cell(request, out_stream)
        else:
            _respond(
                out_stream,
                {
                    "ok": False,
                    "diagnostic": {
                        "code": "evaluation_worker_protocol_error",
                        "message": f"unknown command {cmd!r}",
                    },
                },
            )
    return 0


def main(argv: list[str] | None = None) -> int:
    """``bytefray agents _evaluation_worker`` entry point (internal, undocumented).

    Takes no arguments -- ``launchers.build_agents_command`` always spawns it
    with an empty argument list.
    """

    if argv:
        print(
            "bytefray agents _evaluation_worker is an internal, undocumented "
            "worker protocol entry point; it takes no arguments.",
            file=sys.stderr,
        )
        return 2
    return run_worker()


__all__ = [
    "WORKER_SUBCOMMAND",
    "EvaluationCellWorkerHandle",
    "WorkerFailure",
    "main",
    "run_worker",
]
