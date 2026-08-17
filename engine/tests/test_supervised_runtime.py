from __future__ import annotations

import json
from pathlib import Path

from _hang_safety import hang_safety_timeout
from battle_engine.agents import resolve_agent
from battle_engine.config import Config
from battle_engine.match_service import MatchEntrant
from battle_engine.python_runtime import (
    PythonEntrantController,
    PythonEntrantInitializationError,
    TerminationReason,
)
from battle_engine.supervised_runtime import SupervisedPythonEntrantController
from battle_engine.telemetry import JSONLSink

PASSIVE_SOURCE = """
from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        pass

    def act(self, observation):
        return AgentAction(ActionKind.NOP)

def create_agent():
    return Agent()
"""

ACT_HANGS_SOURCE = """
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
        os._exit(9)

def create_agent():
    return Agent()
"""

# Deliberately exercises the RNG (context.rng), memory writes, and a
# HALT-driven death -- the same shape as the golden corpus's RANDOM_WRITER
# fixture (test_ruleset_v1_equivalence.py) -- so the equivalence test below
# is a genuine cross-check of engine-owned semantics (action application,
# derived-seed RNG, scoring/statistics), not just of two controllers that
# happen to both do nothing.
RANDOM_WRITER_SOURCE = """
from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        self.rng = context.rng
        self.arena_size = context.arena_size
        self.calls = 0

    def act(self, observation):
        self.calls += 1
        if self.calls == 4:
            return AgentAction(ActionKind.HALT)
        return AgentAction(
            ActionKind.WRITE,
            self.rng.randrange(self.arena_size),
            self.rng.randrange(256),
        )

def create_agent():
    return Agent()
"""


def _spec(root: Path, name: str, source: str):
    directory = root / "agents" / name
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text(
        json.dumps(
            {"kind": "python", "api_version": 1, "entrypoint": "agent.py:create_agent", "version": "1.0"}
        ),
        encoding="utf-8",
    )
    (directory / "agent.py").write_text(source, encoding="utf-8")
    return resolve_agent(root, name)


def _entrants(root: Path, sources: dict[str, str]) -> tuple[MatchEntrant, ...]:
    return tuple(
        MatchEntrant.python(chr(ord("A") + slot), name, slot * 32, _spec(root, name, source))
        for slot, (name, source) in enumerate(sources.items())
    )


def test_normal_supervised_match_completes(tmp_path: Path) -> None:
    entrants = _entrants(tmp_path, {"a": PASSIVE_SOURCE, "b": PASSIVE_SOURCE})
    replay_path = tmp_path / "replay.jsonl"
    with hang_safety_timeout(30):
        controller = SupervisedPythonEntrantController(
            Config(seed=1337), entrants, 5, agent_call_timeout=5.0
        )
        try:
            result = controller.run(JSONLSink(str(replay_path)), verbose=False)
        finally:
            controller._close_all_handles()

    assert result.termination_reason is TerminationReason.TICK_LIMIT
    assert result.ticks_run == 5
    for state in result.states:
        assert state.alive
        assert state.diagnostic is None
    for handle in controller.handles.values():
        assert handle.exit_code is not None


def test_hung_act_forfeits_only_that_entrant(tmp_path: Path) -> None:
    entrants = _entrants(tmp_path, {"hangy": ACT_HANGS_SOURCE, "passive": PASSIVE_SOURCE})
    replay_path = tmp_path / "replay.jsonl"
    with hang_safety_timeout(30):
        controller = SupervisedPythonEntrantController(
            Config(seed=1337), entrants, 5, agent_call_timeout=1.0
        )
        try:
            result = controller.run(JSONLSink(str(replay_path)), verbose=False)
        finally:
            controller._close_all_handles()

    assert result.termination_reason is TerminationReason.LAST_AGENT_STANDING
    states_by_id = {state.agent_id: state for state in result.states}
    assert states_by_id["A"].alive is False
    assert states_by_id["A"].diagnostic is not None
    assert states_by_id["A"].diagnostic.code == "agent_action_timeout"
    assert states_by_id["B"].alive is True
    for handle in controller.handles.values():
        assert handle.exit_code is not None


def test_hung_reset_aborts_initialization(tmp_path: Path) -> None:
    entrants = _entrants(tmp_path, {"broken": RESET_HANGS_SOURCE, "passive": PASSIVE_SOURCE})
    with hang_safety_timeout(30):
        try:
            SupervisedPythonEntrantController(Config(seed=1337), entrants, 5, agent_call_timeout=1.0)
            raised = None
        except PythonEntrantInitializationError as exc:
            raised = exc

    assert raised is not None
    assert raised.diagnostic.code == "agent_reset_timeout"
    assert raised.diagnostic.agent_id == "A"


def test_worker_exit_during_act_forfeits_entrant(tmp_path: Path) -> None:
    entrants = _entrants(tmp_path, {"crashy": ACT_EXITS_SOURCE, "passive": PASSIVE_SOURCE})
    replay_path = tmp_path / "replay.jsonl"
    with hang_safety_timeout(30):
        controller = SupervisedPythonEntrantController(
            Config(seed=1337), entrants, 5, agent_call_timeout=5.0
        )
        try:
            result = controller.run(JSONLSink(str(replay_path)), verbose=False)
        finally:
            controller._close_all_handles()

    states_by_id = {state.agent_id: state for state in result.states}
    assert states_by_id["A"].diagnostic is not None
    assert states_by_id["A"].diagnostic.code == "agent_worker_exited"
    assert states_by_id["B"].alive is True


def test_initialization_failure_cleans_up_already_started_workers(tmp_path: Path, monkeypatch) -> None:
    """The first entrant's worker must not be left running when the second fails to load."""

    entrants = _entrants(tmp_path, {"passive": PASSIVE_SOURCE, "broken": RESET_HANGS_SOURCE})
    captured_handles: list[dict] = []
    original_close_all = SupervisedPythonEntrantController._close_all_handles

    def _capture_then_close(self) -> None:
        captured_handles.append(dict(self.handles))
        original_close_all(self)

    monkeypatch.setattr(SupervisedPythonEntrantController, "_close_all_handles", _capture_then_close)

    with hang_safety_timeout(30):
        try:
            SupervisedPythonEntrantController(Config(seed=1337), entrants, 5, agent_call_timeout=1.0)
            raise AssertionError("expected PythonEntrantInitializationError")
        except PythonEntrantInitializationError:
            pass

    assert len(captured_handles) == 1
    handles = captured_handles[0]
    assert "A" in handles  # the first (passive) entrant's worker was started
    for handle in handles.values():
        assert handle.exit_code is not None


def test_supervised_and_unsupervised_controllers_agree_on_outcome(tmp_path: Path) -> None:
    """Same entrants/config through both controllers must reach the same state.

    ``supervised_runtime``'s module docstring claims "same authoritative
    match semantics" as ``python_runtime.PythonEntrantController`` --
    action application, tick scheduling, and scoring are the identical
    engine-owned code, only *production* (load/reset/act) is relocated
    into a worker subprocess. Nothing in the existing suite actually
    proves that claim end-to-end; this does, using a deterministic
    RNG-driven agent (derived seed depends only on
    ``config.seed``/slot/``agent_id``/API version, identical for both
    controllers) so a real divergence in action handling, scheduling
    order, or RNG derivation between the two implementations would fail
    this test rather than only surfacing as an unexplained golden-corpus
    difference after a future refactor.
    """

    entrants = _entrants(
        tmp_path, {"alpha": RANDOM_WRITER_SOURCE, "beta": RANDOM_WRITER_SOURCE}
    )
    config = Config(arena_size=64, instr_per_tick=2, seed=2024)

    unsupervised = PythonEntrantController(config, entrants, 6)
    unsupervised_result = unsupervised.run(
        JSONLSink(str(tmp_path / "unsupervised.jsonl")), verbose=False
    )

    with hang_safety_timeout(30):
        supervised = SupervisedPythonEntrantController(
            config, entrants, 6, agent_call_timeout=5.0
        )
        try:
            supervised_result = supervised.run(
                JSONLSink(str(tmp_path / "supervised.jsonl")), verbose=False
            )
        finally:
            supervised._close_all_handles()

    assert supervised_result.winner == unsupervised_result.winner
    assert supervised_result.termination_reason == unsupervised_result.termination_reason
    assert supervised_result.ticks_run == unsupervised_result.ticks_run
    assert dict(supervised_result.score) == dict(unsupervised_result.score)
    assert bytes(supervised.vm.arena) == bytes(unsupervised.vm.arena)
    assert list(supervised.vm.writer) == list(unsupervised.vm.writer)
    assert supervised_result.statistics == unsupervised_result.statistics
    for supervised_state, unsupervised_state in zip(
        supervised_result.states, unsupervised_result.states
    ):
        assert supervised_state.agent_id == unsupervised_state.agent_id
        assert supervised_state.derived_seed == unsupervised_state.derived_seed
        assert supervised_state.alive == unsupervised_state.alive
        assert supervised_state.cpu_used == unsupervised_state.cpu_used
        assert supervised_state.mem_writes == unsupervised_state.mem_writes
        assert supervised_state.entrant_termination == unsupervised_state.entrant_termination
