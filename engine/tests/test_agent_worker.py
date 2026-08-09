from __future__ import annotations

import json
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
