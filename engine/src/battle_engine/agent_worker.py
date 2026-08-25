"""Whole-match-lifetime worker subprocess for supervised Python agent execution.

Development-time hang **containment**, not a security sandbox -- see
``docs/specs/agent_lab.md`` §17. Worker code runs with the same OS
privileges as the parent; the only guarantee this module provides is that
Bytefray's own tooling stops *waiting* on a stalled ``load``/``reset``/
``act`` call and reports which one stalled.

Architecture (``docs/specs/agent_lab.md`` §6): the parent
(:class:`AgentWorkerHandle`) spawns one child process per Python entrant
via :func:`battle_engine.launchers.build_agents_command` -- the same
spawn-safe, argument-list-only, frozen-or-source resolution every other
child process in this codebase already uses, reached through a hidden
``bytefray agents _worker`` verb (:data:`WORKER_SUBCOMMAND`). No
``multiprocessing`` is used anywhere, so there is no Windows
``freeze_support()`` concern: the worker is just another invocation of the
already-frozen executable.

Wire protocol: newline-delimited JSON on the worker's stdin (parent ->
worker requests) and stdout (worker -> parent responses), one object per
line, flushed immediately. The worker's own ``sys.stdout`` is redirected
to ``sys.stderr`` *before* any agent code ever runs, so an agent's own
``print()`` calls cannot corrupt the protocol stream; only this module's
own :func:`_respond` writes to the real stdout pipe. Symmetrically,
agent-visible ``sys.stdin`` is rebound to a closed/empty stream before any
agent code runs (see :func:`run_worker`): the protocol loop keeps reading
requests from the real pipe via a local reference captured first, so an
agent that calls ``input()`` gets an immediate, well-behaved ``EOFError``
instead of stealing the next line the parent meant as a protocol request
-- see the module-level note in :func:`run_worker` for why this matters.
The child's stderr is drained by a dedicated thread into a small ring
buffer (crash context only) so a chatty agent cannot deadlock the child on
a full OS pipe buffer.

Because Windows pipes to a child process are not portably ``select()``-able,
timeouts are implemented with one dedicated reader thread per worker that
blocks on ``readline()`` and pushes decoded lines onto a ``queue.Queue``;
the parent calls ``queue.get(timeout=...)`` for each request/response round
trip. This is the one pattern that is spawn-safe and identical on Windows
and POSIX without new native dependencies.
"""

from __future__ import annotations

import io
import json
import queue
import random
import subprocess
import sys
import threading
from collections import deque
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from battle_engine.agent_api import (
    ActionKind,
    AgentAction,
    AgentValidationError,
    MatchContext,
    Observation,
    load_python_agent,
)
from battle_engine.agents import AgentSpec
from battle_engine.launchers import build_agents_command
from battle_engine.process_containment import (
    ChildLifetimeBinding,
    bind_child_to_parent_lifetime,
    die_with_parent,
)
from battle_engine.python_runtime import (
    RuntimeDiagnostic,
    derive_agent_seed,
    diagnose_action_exception,
    diagnose_load_failure,
    diagnose_reset_failure,
)

WORKER_SUBCOMMAND = "_worker"

_EOF = object()


class WorkerCallStatus(str, Enum):
    """The outcome of one request/response round trip with a worker."""

    OK = "ok"
    FAILED = "failed"
    TIMEOUT = "timeout"
    EXITED = "exited"
    PROTOCOL_ERROR = "protocol_error"


@dataclass
class WorkerCallResult:
    status: WorkerCallStatus
    payload: dict[str, Any] | None = None


def agent_spec_to_payload(spec: AgentSpec) -> dict[str, Any]:
    """Serialize the ``AgentSpec`` fields ``load_python_agent`` actually reads."""

    return {
        "name": spec.name,
        "display": spec.display,
        "dir": str(spec.dir),
        "kind": spec.kind,
        "api_version": spec.api_version,
        "version": spec.version,
        "entry_point": spec.entry_point,
    }


class AgentWorkerHandle:
    """Parent-side handle to one whole-match-lifetime worker subprocess."""

    def __init__(self, *, agent_id: str, slot: int) -> None:
        self.agent_id = agent_id
        self.slot = slot
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
        # Tie the worker's lifetime to this parent process (Windows Job
        # Object / POSIX PDEATHSIG, see battle_engine.process_containment)
        # so a hung worker cannot outlive a parent that is itself
        # force-killed -- e.g. the Designer's QProcess._dispose_process()
        # killing a supervised `agents test` while its worker is mid-hang.
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

    def _call(self, request: dict[str, Any], *, timeout: float) -> WorkerCallResult:
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

    def load(self, spec: AgentSpec, *, timeout: float) -> WorkerCallResult:
        return self._call(
            {
                "cmd": "load",
                "agent_id": self.agent_id,
                "slot": self.slot,
                "spec": agent_spec_to_payload(spec),
            },
            timeout=timeout,
        )

    def reset(
        self,
        *,
        match_seed: int,
        api_version: int,
        arena_size: int,
        tick_limit: int,
        action_budget: int,
        timeout: float,
        locality_reach: int | None = None,
    ) -> WorkerCallResult:
        return self._call(
            {
                "cmd": "reset",
                "match_seed": match_seed,
                "api_version": api_version,
                "arena_size": arena_size,
                "tick_limit": tick_limit,
                "action_budget": action_budget,
                # v3 research Phase 2: additive, `None` for every Ruleset
                # whose addressing is absolute. A worker built before this
                # key existed reads it back through `.get(...)`, so the wire
                # stays backward-tolerant in both directions.
                "locality_reach": locality_reach,
            },
            timeout=timeout,
        )

    def act(
        self, observation: Observation, *, action_slot: int, timeout: float
    ) -> WorkerCallResult:
        return self._call(
            {
                "cmd": "act",
                "action_slot": action_slot,
                "observation": {
                    "tick": observation.tick,
                    "agent_id": observation.agent_id,
                    "pc": observation.pc,
                    "register_a": observation.register_a,
                    "register_p": observation.register_p,
                    "zero_flag": observation.zero_flag,
                    "last_read": observation.last_read,
                    "alive": observation.alive,
                    "locus": observation.locus,
                },
            },
            timeout=timeout,
        )

    def kill(self) -> None:
        """Unconditional kill, no grace period -- for a call that timed out.

        Mirrors the Designer's own documented ``_dispose_process`` policy
        (``docs/specs/agent_designer_workflow.md`` §2.6): once a call has
        already missed its deadline, there is no softer recovery available
        anywhere in this codebase.
        """

        if self._proc is not None and self._proc.poll() is None:
            try:
                self._proc.kill()
            except OSError:
                pass

    def close(self, *, timeout: float = 2.0) -> None:
        """Best-effort graceful shutdown, force-kill on any doubt.

        Safe to call after :meth:`kill` (idempotent) and safe to call
        multiple times. Never raises -- this is cleanup code and must not
        itself become a new source of failure.
        """

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
        # Release last: the process is already confirmed terminated (or
        # was force-killed above) by this point, so releasing the lifetime
        # binding here can only ever close a handle for an already-dead
        # process -- never accidentally trigger kill-on-close against a
        # process this call intended to keep alive.
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


def _protocol_diagnostic(
    message: str, *, agent_id: str | None, slot: int | None
) -> RuntimeDiagnostic:
    return RuntimeDiagnostic(
        code="agent_worker_protocol_error",
        stage="protocol",
        message=message,
        agent_id=agent_id,
        slot=slot,
    )


@dataclass
class _WorkerState:
    agent_id: str | None = None
    slot: int | None = None
    loaded: Any = None


def _handle_load(state: _WorkerState, request: dict[str, Any], out: Any) -> None:
    agent_id: str = request.get("agent_id") or ""
    slot: int = request.get("slot") or 0
    state.agent_id, state.slot = agent_id, slot
    payload = request.get("spec") or {}
    spec = AgentSpec(
        name=payload.get("name", ""),
        display=payload.get("display", ""),
        dir=Path(payload.get("dir", ".")),
        blob=None,
        defaults={},
        kind=payload.get("kind") or "",
        api_version=payload.get("api_version"),
        version=payload.get("version"),
        source_path=None,
        entry_point=payload.get("entry_point"),
    )
    try:
        loaded = load_python_agent(spec)
    except AgentValidationError as exc:
        diagnostic = diagnose_load_failure(exc, agent_id=agent_id, slot=slot)
        _respond(out, {"ok": False, "diagnostic": asdict(diagnostic)})
        return
    state.loaded = loaded
    _respond(
        out,
        {
            "ok": True,
            "metadata": {
                "name": loaded.metadata.name,
                "version": loaded.metadata.version,
                "api_version": loaded.metadata.api_version,
            },
            "source_path": str(loaded.source_path),
        },
    )


def _handle_reset(state: _WorkerState, request: dict[str, Any], out: Any) -> None:
    if state.loaded is None:
        diagnostic = _protocol_diagnostic(
            "reset requested before a successful load", agent_id=state.agent_id, slot=state.slot
        )
        _respond(out, {"ok": False, "diagnostic": asdict(diagnostic)})
        return
    match_seed = request["match_seed"]
    api_version = request["api_version"]
    seed = derive_agent_seed(match_seed, state.slot or 0, state.agent_id or "", api_version)
    context = MatchContext(
        agent_id=state.agent_id or "",
        seed=seed,
        arena_size=request["arena_size"],
        tick_limit=request["tick_limit"],
        action_budget=request["action_budget"],
        rng=random.Random(seed),
        locality_reach=request.get("locality_reach"),
    )
    try:
        state.loaded.instance.reset(context)
    except Exception as exc:
        diagnostic = diagnose_reset_failure(exc, agent_id=state.agent_id or "", slot=state.slot or 0)
        _respond(out, {"ok": False, "diagnostic": asdict(diagnostic)})
        return
    _respond(out, {"ok": True})


def _handle_act(state: _WorkerState, request: dict[str, Any], out: Any) -> None:
    if state.loaded is None:
        diagnostic = _protocol_diagnostic(
            "act requested before a successful load", agent_id=state.agent_id, slot=state.slot
        )
        _respond(out, {"ok": False, "diagnostic": asdict(diagnostic)})
        return
    observation_payload = request["observation"]
    observation = Observation(
        tick=observation_payload["tick"],
        agent_id=observation_payload["agent_id"],
        pc=observation_payload["pc"],
        register_a=observation_payload["register_a"],
        register_p=observation_payload["register_p"],
        zero_flag=observation_payload["zero_flag"],
        last_read=observation_payload.get("last_read"),
        alive=observation_payload["alive"],
        locus=observation_payload.get("locus"),
    )
    action_slot = request.get("action_slot", 0)
    try:
        action = state.loaded.instance.act(observation)
    except Exception as exc:
        diagnostic = diagnose_action_exception(
            exc,
            agent_id=state.agent_id or "",
            slot=state.slot or 0,
            tick=observation.tick,
            action_slot=action_slot,
        )
        _respond(out, {"ok": False, "diagnostic": asdict(diagnostic)})
        return
    if isinstance(action, AgentAction) and isinstance(action.kind, ActionKind):
        _respond(
            out,
            {
                "ok": True,
                "action": {
                    "kind": action.kind.value,
                    "operand": action.operand,
                    "value": action.value,
                },
            },
        )
    else:
        # Not a valid AgentAction shape at all: forward as "no action",
        # which validate_action rejects on the parent identically to an
        # in-process call returning the same malformed value -- see
        # docs/specs/agent_lab.md §6 and this module's docstring.
        _respond(out, {"ok": True, "action": None})


def run_worker(*, stdin: Any = None, stdout: Any = None) -> int:
    """Run the worker's request/response loop until ``shutdown`` or EOF.

    Redirects ``sys.stdout`` to ``sys.stderr`` before any agent code can
    possibly run, so agent ``print()`` output cannot corrupt the protocol
    stream on the real stdout pipe (``out``, captured before redirection).

    Protocol ownership of stdin is exclusive the same way: this function's
    own read loop iterates the real stdin pipe through the local
    ``in_stream`` reference captured *before* ``sys.stdin`` is rebound, so
    the loop keeps working normally, but any agent code that reads
    ``sys.stdin`` directly or calls the builtin ``input()`` -- both of
    which would otherwise race the protocol loop for the *same* underlying
    line -- now hits an empty, already-at-EOF stream instead (``input()``
    raises ``EOFError`` immediately). Without this, an agent calling
    ``input()`` mid-``act()`` could silently consume the next line the
    parent meant as a protocol request (e.g. the next ``act``/``shutdown``
    request), permanently desynchronizing the wire protocol -- see
    ``docs/specs/agent_lab.md``'s worker-protocol-ownership note. stderr is
    left untouched and available to agent code for diagnostics.

    Also asks the OS (best-effort) to end this process if its parent dies
    -- see :func:`battle_engine.process_containment.die_with_parent`; on
    Windows this is instead handled by the parent's Job Object.
    """

    die_with_parent()
    in_stream = stdin if stdin is not None else sys.stdin
    out_stream = stdout if stdout is not None else sys.stdout
    sys.stdout = sys.stderr
    sys.stdin = io.StringIO()

    state = _WorkerState()
    for raw_line in in_stream:
        line = raw_line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            diagnostic = _protocol_diagnostic(
                "invalid JSON request", agent_id=state.agent_id, slot=state.slot
            )
            _respond(out_stream, {"ok": False, "diagnostic": asdict(diagnostic)})
            continue
        cmd = request.get("cmd")
        if cmd == "shutdown":
            return 0
        if cmd == "load":
            _handle_load(state, request, out_stream)
        elif cmd == "reset":
            _handle_reset(state, request, out_stream)
        elif cmd == "act":
            _handle_act(state, request, out_stream)
        else:
            diagnostic = _protocol_diagnostic(
                f"unknown command {cmd!r}", agent_id=state.agent_id, slot=state.slot
            )
            _respond(out_stream, {"ok": False, "diagnostic": asdict(diagnostic)})
    return 0


def main(argv: list[str] | None = None) -> int:
    """``bytefray agents _worker`` entry point (internal, undocumented).

    Takes no arguments -- :func:`battle_engine.launchers.build_agents_command`
    always spawns it with an empty argument list. Rejecting anything else
    outright (rather than silently ignoring it) means a stray or malformed
    direct invocation fails fast and visibly instead of blocking forever
    on stdin, which would otherwise look identical to the worker doing its
    job normally.
    """

    if argv:
        print(
            "bytefray agents _worker is an internal, undocumented worker "
            "protocol entry point; it takes no arguments.",
            file=sys.stderr,
        )
        return 2
    return run_worker()


__all__ = [
    "WORKER_SUBCOMMAND",
    "AgentWorkerHandle",
    "WorkerCallResult",
    "WorkerCallStatus",
    "agent_spec_to_payload",
    "main",
    "run_worker",
]
