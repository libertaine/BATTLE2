from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from _hang_safety import hang_safety_timeout
from battle_engine.agent_api import Observation
from battle_engine.agent_worker import AgentWorkerHandle, WorkerCallResult, WorkerCallStatus
from battle_engine.agents import resolve_agent

PASSIVE_SOURCE = """
from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        self.seed = context.seed

    def act(self, observation):
        return AgentAction(ActionKind.WRITE, observation.pc, 42)

def create_agent():
    return Agent()
"""

ACT_HANGS_SOURCE = """
from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        pass

    def act(self, observation):
        while True:
            pass

def create_agent():
    return Agent()
"""

RESET_HANGS_SOURCE = """
class Agent:
    def reset(self, context):
        while True:
            pass

    def act(self, observation):
        return None

def create_agent():
    return Agent()
"""

ACT_EXITS_SOURCE = """
import os

class Agent:
    def reset(self, context):
        pass

    def act(self, observation):
        os._exit(7)

def create_agent():
    return Agent()
"""

FACTORY_RAISES_SOURCE = """
class Agent:
    def reset(self, context):
        pass
    def act(self, observation):
        return None

def create_agent():
    raise LookupError("factory exploded")
"""

INVALID_ACTION_SOURCE = """
class Agent:
    def reset(self, context):
        pass

    def act(self, observation):
        return "not an action"

def create_agent():
    return Agent()
"""

READS_STDIN_SOURCE = """
from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        pass

    def act(self, observation):
        # An agent calling input() must not be able to steal the next
        # protocol request line off the real stdin pipe -- it should see
        # an immediate EOFError against the worker's rebound, empty
        # agent-visible stdin instead. Report which happened via the
        # write value so the test can assert on it without any extra
        # channel.
        try:
            input()
            saw_eof = False
        except EOFError:
            saw_eof = True
        return AgentAction(ActionKind.WRITE, observation.pc, 1 if saw_eof else 0)

def create_agent():
    return Agent()
"""


def _spec(root: Path, name: str, source: str):
    directory = root / "agents" / name
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text(
        json.dumps(
            {
                "kind": "python",
                "api_version": 1,
                "entrypoint": "agent.py:create_agent",
                "name": name,
                "version": "1.0",
            }
        ),
        encoding="utf-8",
    )
    (directory / "agent.py").write_text(source, encoding="utf-8")
    return resolve_agent(root, name)


def _observation(tick: int = 1) -> Observation:
    return Observation(
        tick=tick, agent_id="A", pc=0, register_a=0, register_p=0,
        zero_flag=False, last_read=None, alive=True,
    )


def test_load_reset_act_round_trip(tmp_path: Path) -> None:
    spec = _spec(tmp_path, "passive", PASSIVE_SOURCE)
    handle = AgentWorkerHandle(agent_id="A", slot=0)
    with hang_safety_timeout(30):
        try:
            handle.start()
            load_result = handle.load(spec, timeout=10.0)
            assert load_result.status is WorkerCallStatus.OK
            assert load_result.payload is not None
            assert load_result.payload["metadata"]["api_version"] == 1

            reset_result = handle.reset(
                match_seed=1337, api_version=1, arena_size=4096, tick_limit=10,
                action_budget=8, timeout=10.0,
            )
            assert reset_result.status is WorkerCallStatus.OK

            act_result = handle.act(_observation(), action_slot=0, timeout=10.0)
            assert act_result.status is WorkerCallStatus.OK
            assert act_result.payload is not None
            assert act_result.payload["action"] == {"kind": "write", "operand": 0, "value": 42}
        finally:
            handle.close()

    assert handle.exit_code == 0


def test_agent_calling_input_does_not_desync_the_protocol(tmp_path: Path) -> None:
    """Regression test for the worker-protocol-ownership hardening: an
    agent's own ``input()`` call must hit the worker's rebound,
    already-at-EOF agent-visible stdin (an immediate ``EOFError``), never
    the real stdin pipe carrying the next protocol request. Two
    consecutive ``act()`` calls (not just one) prove the protocol stays
    in sync afterward -- a desync would either hang the second call or
    have it observe the wrong response.
    """

    spec = _spec(tmp_path, "reads_stdin", READS_STDIN_SOURCE)
    handle = AgentWorkerHandle(agent_id="A", slot=0)
    with hang_safety_timeout(30):
        try:
            handle.start()
            assert handle.load(spec, timeout=10.0).status is WorkerCallStatus.OK
            assert handle.reset(
                match_seed=1, api_version=1, arena_size=4096, tick_limit=2, action_budget=1, timeout=10.0
            ).status is WorkerCallStatus.OK

            first = handle.act(_observation(1), action_slot=0, timeout=10.0)
            assert first.status is WorkerCallStatus.OK
            assert first.payload is not None
            assert first.payload["action"] == {"kind": "write", "operand": 0, "value": 1}

            second = handle.act(_observation(2), action_slot=0, timeout=10.0)
            assert second.status is WorkerCallStatus.OK
            assert second.payload is not None
            assert second.payload["action"] == {"kind": "write", "operand": 0, "value": 1}
        finally:
            handle.close()

    assert handle.exit_code == 0


def test_worker_main_rejects_unexpected_arguments() -> None:
    from battle_engine.agent_worker import main as worker_main

    assert worker_main(["--bogus"]) == 2


def test_load_failure_reports_diagnostic(tmp_path: Path) -> None:
    spec = _spec(tmp_path, "bad_factory", FACTORY_RAISES_SOURCE)
    handle = AgentWorkerHandle(agent_id="A", slot=0)
    with hang_safety_timeout(30):
        try:
            handle.start()
            result = handle.load(spec, timeout=10.0)
            assert result.status is WorkerCallStatus.FAILED
            assert result.payload is not None
            assert result.payload["diagnostic"]["code"] == "agent_factory_failed"
        finally:
            handle.close()


def test_invalid_returned_action_is_forwarded_as_none(tmp_path: Path) -> None:
    spec = _spec(tmp_path, "invalid_action", INVALID_ACTION_SOURCE)
    handle = AgentWorkerHandle(agent_id="A", slot=0)
    with hang_safety_timeout(30):
        try:
            handle.start()
            assert handle.load(spec, timeout=10.0).status is WorkerCallStatus.OK
            assert handle.reset(
                match_seed=1, api_version=1, arena_size=4096, tick_limit=1, action_budget=1, timeout=10.0
            ).status is WorkerCallStatus.OK

            act_result = handle.act(_observation(), action_slot=0, timeout=10.0)
            assert act_result.status is WorkerCallStatus.OK
            assert act_result.payload is not None
            assert act_result.payload["action"] is None
        finally:
            handle.close()


def test_act_timeout_is_reported_and_worker_is_killable(tmp_path: Path) -> None:
    spec = _spec(tmp_path, "act_hangs", ACT_HANGS_SOURCE)
    handle = AgentWorkerHandle(agent_id="A", slot=0)
    with hang_safety_timeout(30):
        try:
            handle.start()
            assert handle.load(spec, timeout=10.0).status is WorkerCallStatus.OK
            assert handle.reset(
                match_seed=1, api_version=1, arena_size=4096, tick_limit=1, action_budget=1, timeout=10.0
            ).status is WorkerCallStatus.OK

            act_result = handle.act(_observation(), action_slot=0, timeout=1.0)
            assert act_result.status is WorkerCallStatus.TIMEOUT

            # A timed-out call does not self-terminate the worker -- the
            # caller decides whether/when to kill it (docs/specs/agent_lab.md
            # §6). Confirm the process really is still alive here, then
            # confirm kill() actually ends it.
            assert handle.exit_code is None
            handle.kill()
        finally:
            handle.close()

    assert handle.exit_code is not None


def test_reset_timeout_is_reported(tmp_path: Path) -> None:
    spec = _spec(tmp_path, "reset_hangs", RESET_HANGS_SOURCE)
    handle = AgentWorkerHandle(agent_id="A", slot=0)
    with hang_safety_timeout(30):
        try:
            handle.start()
            assert handle.load(spec, timeout=10.0).status is WorkerCallStatus.OK
            reset_result = handle.reset(
                match_seed=1, api_version=1, arena_size=4096, tick_limit=1, action_budget=1, timeout=1.0
            )
            assert reset_result.status is WorkerCallStatus.TIMEOUT
            handle.kill()
        finally:
            handle.close()


def test_worker_exit_during_act_is_reported_as_exited(tmp_path: Path) -> None:
    spec = _spec(tmp_path, "act_exits", ACT_EXITS_SOURCE)
    handle = AgentWorkerHandle(agent_id="A", slot=0)
    with hang_safety_timeout(30):
        try:
            handle.start()
            assert handle.load(spec, timeout=10.0).status is WorkerCallStatus.OK
            assert handle.reset(
                match_seed=1, api_version=1, arena_size=4096, tick_limit=1, action_budget=1, timeout=10.0
            ).status is WorkerCallStatus.OK

            act_result = handle.act(_observation(), action_slot=0, timeout=10.0)
            assert act_result.status is WorkerCallStatus.EXITED
        finally:
            handle.close()

    assert handle.exit_code == 7


def test_close_is_idempotent(tmp_path: Path) -> None:
    spec = _spec(tmp_path, "passive2", PASSIVE_SOURCE)
    handle = AgentWorkerHandle(agent_id="A", slot=0)
    with hang_safety_timeout(30):
        handle.start()
        assert handle.load(spec, timeout=10.0).status is WorkerCallStatus.OK
        handle.close()
        handle.close()  # must not raise
        handle.kill()  # must not raise even though already dead


def test_close_without_start_is_a_no_op() -> None:
    handle = AgentWorkerHandle(agent_id="A", slot=0)
    handle.close()  # never started -- must not raise
    handle.kill()


def test_close_after_start_without_any_call_cleans_up(tmp_path: Path) -> None:
    """A worker that was started but never got as far as a load/reset/act
    call (e.g. the caller decided not to proceed) must still be cleanly
    closeable -- close() must not assume any prior call happened.
    """

    handle = AgentWorkerHandle(agent_id="A", slot=0)
    with hang_safety_timeout(30):
        handle.start()
        handle.close()

    assert handle.exit_code is not None


def test_close_recovers_a_hung_worker_without_an_explicit_kill(tmp_path: Path) -> None:
    """Exercises close()'s own graceful-shutdown-then-force-kill fallback
    directly, rather than relying on the caller to have already called
    kill() (every other hang-related test above calls kill() explicitly
    first). A worker stuck in a tight ``act()`` loop cannot read the
    ``shutdown`` request off its own stdin, so close() must fall through
    to its force-kill path and still leave no process behind.
    """

    spec = _spec(tmp_path, "act_hangs2", ACT_HANGS_SOURCE)
    handle = AgentWorkerHandle(agent_id="A", slot=0)
    with hang_safety_timeout(30):
        handle.start()
        assert handle.load(spec, timeout=10.0).status is WorkerCallStatus.OK
        assert handle.reset(
            match_seed=1, api_version=1, arena_size=4096, tick_limit=1, action_budget=1, timeout=10.0
        ).status is WorkerCallStatus.OK

        act_result = handle.act(_observation(), action_slot=0, timeout=1.0)
        assert act_result.status is WorkerCallStatus.TIMEOUT

        handle.close(timeout=2.0)  # no explicit kill() first

    assert handle.exit_code is not None


def test_call_reports_protocol_error_on_malformed_response(tmp_path: Path) -> None:
    """White-box test of the response-parsing path.

    Exercising a real worker emitting a malformed line would require a
    second, non-production worker script; instead this directly drives
    AgentWorkerHandle._call's parsing logic by pre-seeding its response
    queue and stubbing just enough of ``_proc`` for the request-write
    half to succeed, which is enough to prove PROTOCOL_ERROR is reported
    for both invalid JSON and well-formed JSON missing the required "ok"
    key, without spawning any subprocess.
    """

    class _FakeStdin:
        def write(self, _data: str) -> None:
            pass

        def flush(self) -> None:
            pass

    class _FakeProc:
        stdin = _FakeStdin()

        def poll(self) -> int | None:
            return None

    handle = AgentWorkerHandle(agent_id="A", slot=0)
    handle._proc = _FakeProc()  # type: ignore[assignment]

    handle._queue.put("not valid json\n")
    result: WorkerCallResult = handle._call({"cmd": "act"}, timeout=1.0)
    assert result.status is WorkerCallStatus.PROTOCOL_ERROR

    handle._queue.put('{"no_ok_key": true}\n')
    result = handle._call({"cmd": "act"}, timeout=1.0)
    assert result.status is WorkerCallStatus.PROTOCOL_ERROR


def _pid_is_alive(pid: int) -> bool:
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True, check=False
        )
        return str(pid) in result.stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def test_worker_does_not_survive_a_hard_kill_of_its_own_parent(tmp_path: Path) -> None:
    """Regression test for a real orphan-process bug found during Agent Lab
    development: a worker stuck in a hung reset()/act() cannot notice its
    parent died via EOF-on-stdin (it never returns to the read loop), so
    without OS-level containment (Windows Job Object / POSIX PDEATHSIG,
    see battle_engine.process_containment) it survives forever as an
    orphan when its immediate parent is abruptly killed -- exactly what
    the Designer's QProcess._dispose_process()'s unconditional kill() does
    to a supervised ``agents test`` process. Reproduced here with a
    second, disposable Python process standing in for that parent: it
    starts a worker, prints the worker's PID, and then blocks forever so
    the test can kill it out from under the worker.
    """

    engine_src = str(Path(__file__).resolve().parents[1] / "engine" / "src")
    client_src = str(Path(__file__).resolve().parents[1] / "client" / "src")
    directory = tmp_path / "agents" / "hangy"
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text(
        json.dumps(
            {"kind": "python", "api_version": 1, "entrypoint": "agent.py:create_agent", "version": "1.0"}
        ),
        encoding="utf-8",
    )
    (directory / "agent.py").write_text(RESET_HANGS_SOURCE, encoding="utf-8")

    parent_script = f"""
import sys, threading, time
from pathlib import Path
sys.path.insert(0, {engine_src!r})
sys.path.insert(0, {client_src!r})
from battle_engine.agents import resolve_agent
from battle_engine.agent_worker import AgentWorkerHandle

spec = resolve_agent(Path({str(tmp_path)!r}), "hangy")
handle = AgentWorkerHandle(agent_id="A", slot=0)
handle.start()
print(handle._proc.pid, flush=True)
handle.load(spec, timeout=10.0)
threading.Thread(
    target=lambda: handle.reset(
        match_seed=1, api_version=1, arena_size=4096, tick_limit=1, action_budget=1, timeout=60.0
    ),
    daemon=True,
).start()
time.sleep(60)
"""

    with hang_safety_timeout(30):
        parent = subprocess.Popen(
            [sys.executable, "-c", parent_script], stdout=subprocess.PIPE, text=True
        )
        try:
            worker_pid_line = parent.stdout.readline()
            worker_pid = int(worker_pid_line.strip())
            time.sleep(1.5)  # let the worker genuinely enter the hung reset()
            assert _pid_is_alive(worker_pid), "worker should still be running before the kill"

            parent.kill()  # the abrupt kill under test, standing in for QProcess.kill()
            parent.wait(timeout=10)

            deadline = time.time() + 10
            while time.time() < deadline and _pid_is_alive(worker_pid):
                time.sleep(0.2)
            assert not _pid_is_alive(worker_pid), (
                f"worker pid {worker_pid} outlived its abruptly killed parent"
            )
        finally:
            if parent.poll() is None:
                parent.kill()


def test_call_reports_exited_on_eof(tmp_path: Path) -> None:
    from battle_engine.agent_worker import _EOF

    class _FakeStdin:
        def write(self, _data: str) -> None:
            pass

        def flush(self) -> None:
            pass

    class _FakeProc:
        stdin = _FakeStdin()

    handle = AgentWorkerHandle(agent_id="A", slot=0)
    handle._proc = _FakeProc()  # type: ignore[assignment]
    handle._queue.put(_EOF)

    result = handle._call({"cmd": "act"}, timeout=1.0)
    assert result.status is WorkerCallStatus.EXITED
