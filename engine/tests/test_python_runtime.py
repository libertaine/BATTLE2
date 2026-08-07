from __future__ import annotations

import json
import random
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from battle_engine.agent_api import ActionKind, AgentAction
from battle_engine.agents import resolve_agent
from battle_engine.builtins import build_agent
from battle_engine.config import Config, Weights
from battle_engine.match_service import (
    MatchEntrant,
    MatchRequest,
    NativeMatchService,
    UnsupportedMatchCompositionError,
)
from battle_engine.python_runtime import (
    InvalidPythonActionError,
    PythonEntrantController,
    PythonEntrantInitializationError,
    PythonEntrantState,
    apply_action,
    derive_agent_seed,
    validate_action,
)
from battle_engine.telemetry import JSONLSink
from battle_engine.vm import VM


PASSIVE_SOURCE = """
from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        self.reset_calls = getattr(self, "reset_calls", 0) + 1
        self.act_calls = 0
        self.context = context

    def act(self, observation):
        self.act_calls += 1
        return AgentAction(ActionKind.NOP)

def create_agent():
    return Agent()
"""


def _spec(root: Path, name: str, source: str = PASSIVE_SOURCE):
    directory = root / "agents" / name
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text(
        json.dumps(
            {
                "kind": "python",
                "api_version": 1,
                "entrypoint": "agent.py:create_agent",
                "name": name,
                "display": name.title(),
                "version": "1.0",
            }
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


def _state() -> PythonEntrantState:
    return PythonEntrantState(
        "A",
        "Alpha",
        loaded=SimpleNamespace(),  # type: ignore[arg-type]
        rng=random.Random(1),
    )


def test_every_action_has_defined_state_and_arena_semantics():
    vm = VM(64)
    state = _state()

    apply_action(AgentAction(ActionKind.NOP), state, vm)
    apply_action(AgentAction(ActionKind.SET_A, -1), state, vm)
    assert state.register_a == 0xFFFFFFFF
    apply_action(AgentAction(ActionKind.ADD_A, 1), state, vm)
    assert state.register_a == 0 and state.zero_flag
    apply_action(AgentAction(ActionKind.SET_P, -1), state, vm)
    apply_action(AgentAction(ActionKind.ADD_P, 2), state, vm)
    assert state.register_p == 1
    apply_action(AgentAction(ActionKind.WRITE, 65, 0x1FF), state, vm)
    assert vm.arena[1] == 0xFF
    assert vm.writer[1] == "A"
    apply_action(AgentAction(ActionKind.READ, 65), state, vm)
    assert state.last_read == 0xFF
    assert state.register_a == 0xFF
    assert not state.zero_flag
    apply_action(AgentAction(ActionKind.JUMP, -1), state, vm)
    assert state.pc == 0xFFFFFFFF
    state.zero_flag = False
    apply_action(AgentAction(ActionKind.JUMP_IF_ZERO, 7), state, vm)
    assert state.pc == 0xFFFFFFFF
    state.zero_flag = True
    apply_action(AgentAction(ActionKind.JUMP_IF_ZERO, 7), state, vm)
    assert state.pc == 7
    apply_action(AgentAction(ActionKind.HALT), state, vm)
    assert not state.alive


@pytest.mark.parametrize(
    "action",
    [
        None,
        AgentAction("future"),  # type: ignore[arg-type]
        AgentAction(ActionKind.NOP, 1),
        AgentAction(ActionKind.SET_A),
        AgentAction(ActionKind.ADD_P, True),
        AgentAction(ActionKind.WRITE, "x", 1),  # type: ignore[arg-type]
        AgentAction(ActionKind.WRITE, 1, None),
        AgentAction(ActionKind.READ, 1, 2),
    ],
)
def test_invalid_actions_are_rejected(action):
    with pytest.raises(InvalidPythonActionError):
        validate_action(action)


def test_reset_once_and_action_quota_with_fresh_instances(tmp_path):
    entrants = _entrants(tmp_path, {"alpha": PASSIVE_SOURCE, "beta": PASSIVE_SOURCE})
    config = Config(arena_size=64, instr_per_tick=3, seed=9)
    first = PythonEntrantController(config, entrants, 2)
    second = PythonEntrantController(config, entrants, 2)

    first.run(JSONLSink(str(tmp_path / "first.jsonl")), verbose=False)

    for state in first.states:
        assert state.loaded.instance.reset_calls == 1  # type: ignore[attr-defined]
        assert state.loaded.instance.act_calls == 6  # type: ignore[attr-defined]
        assert state.total_actions == 6
    assert first.states[0].loaded.instance is not second.states[0].loaded.instance


def test_sequential_write_is_visible_to_later_reader_same_tick(tmp_path):
    writer = """
from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, context): pass
    def act(self, observation): return AgentAction(ActionKind.WRITE, 17, 91)
def create_agent(): return Agent()
"""
    reader = """
from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, context): self.seen = []
    def act(self, observation):
        self.seen.append(observation.last_read)
        return AgentAction(ActionKind.READ, 17)
def create_agent(): return Agent()
"""
    entrants = _entrants(tmp_path, {"writer": writer, "reader": reader})
    controller = PythonEntrantController(
        Config(arena_size=64, instr_per_tick=1), entrants, 1
    )

    result = controller.run(JSONLSink(str(tmp_path / "replay.jsonl")), verbose=False)

    assert controller.states[1].last_read == 91
    assert controller.states[1].register_a == 91
    assert result.statistics["A"]["total_mem_writes"] == 1
    records = [
        json.loads(line)
        for line in (tmp_path / "replay.jsonl").read_text().splitlines()
    ]
    assert records[1]["memory_diffs"] == [{"addr": 17, "len": 1, "owner": "A"}]


def test_halt_stops_future_callbacks(tmp_path):
    halt = """
from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, context): self.calls = 0
    def act(self, observation):
        self.calls += 1
        return AgentAction(ActionKind.HALT)
def create_agent(): return Agent()
"""
    entrants = _entrants(
        tmp_path,
        {"halt": halt, "alpha": PASSIVE_SOURCE, "beta": PASSIVE_SOURCE},
    )
    controller = PythonEntrantController(
        Config(arena_size=96, instr_per_tick=4), entrants, 3
    )

    controller.run(JSONLSink(str(tmp_path / "replay.jsonl")), verbose=False)

    assert controller.states[0].loaded.instance.calls == 1  # type: ignore[attr-defined]
    assert controller.states[0].total_actions == 1
    assert not controller.states[0].alive


def test_rng_is_deterministic_seeded_and_independent_per_entrant(tmp_path):
    random_writer = """
from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, context): self.rng = context.rng
    def act(self, observation):
        return AgentAction(ActionKind.WRITE, 3, self.rng.randrange(256))
def create_agent(): return Agent()
"""
    entrants = _entrants(tmp_path, {"alpha": random_writer, "beta": random_writer})

    def run(seed, name):
        controller = PythonEntrantController(
            Config(arena_size=64, instr_per_tick=3, seed=seed), entrants, 2
        )
        controller.run(JSONLSink(str(tmp_path / f"{name}.jsonl")), verbose=False)
        return bytes(controller.vm.arena), [state.rng.getstate() for state in controller.states]

    first = run(71, "first")
    second = run(71, "second")
    changed = run(72, "changed")
    assert first == second
    assert first != changed
    assert derive_agent_seed(71, 0, "A") != derive_agent_seed(71, 1, "B")


def test_one_agent_rng_consumption_does_not_change_another_stream(tmp_path):
    burner_template = """
from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, context): self.rng = context.rng
    def act(self, observation):
        for _ in range({draws}): self.rng.random()
        return AgentAction(ActionKind.NOP)
def create_agent(): return Agent()
"""
    recorder = """
from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, context): self.rng, self.values = context.rng, []
    def act(self, observation):
        self.values.append(self.rng.randrange(1000000))
        return AgentAction(ActionKind.NOP)
def create_agent(): return Agent()
"""

    def values(root, draws):
        entrants = _entrants(
            root,
            {"burner": burner_template.format(draws=draws), "recorder": recorder},
        )
        controller = PythonEntrantController(
            Config(arena_size=64, instr_per_tick=3, seed=81), entrants, 2
        )
        controller.run(JSONLSink(str(root / "replay.jsonl")), verbose=False)
        return controller.states[1].loaded.instance.values  # type: ignore[attr-defined]

    assert values(tmp_path / "few", 1) == values(tmp_path / "many", 20)


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ("raise RuntimeError('boom')", "python_act_failed"),
        ("return object()", "python_action_invalid"),
        ("return AgentAction('future')", "python_action_invalid"),
        ("return AgentAction(ActionKind.WRITE, 'bad', 1)", "python_action_invalid"),
    ],
)
def test_runtime_failure_forfeits_with_structured_diagnostic(tmp_path, body, code):
    failing = f"""
from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, context): pass
    def act(self, observation):
        {body}
def create_agent(): return Agent()
"""
    entrants = _entrants(tmp_path, {"failing": failing, "passive": PASSIVE_SOURCE})
    replay = tmp_path / "replay.jsonl"

    result = NativeMatchService().run(
        MatchRequest(Config(arena_size=64), entrants, 3, replay, False)
    )

    failure = result.agents_by_id["A"].diagnostic
    assert failure is not None and failure.code == code
    assert result.winner == "B"
    records = [json.loads(line) for line in replay.read_text().splitlines()]
    assert records[1]["events"][0]["reason"] == code


def test_reset_failure_rejects_match_before_artifacts(tmp_path):
    broken = """
class Agent:
    def reset(self, context): raise RuntimeError("reset boom")
    def act(self, observation): return None
def create_agent(): return Agent()
"""
    entrants = _entrants(tmp_path, {"broken": broken, "passive": PASSIVE_SOURCE})
    replay = tmp_path / "replay.jsonl"

    with pytest.raises(PythonEntrantInitializationError) as caught:
        NativeMatchService().run(
            MatchRequest(Config(arena_size=64), entrants, 1, replay, False)
        )

    assert caught.value.diagnostic.code == "python_reset_failed"
    assert "RuntimeError: reset boom" in str(caught.value)
    assert not replay.exists()


def test_mixed_vm_python_match_is_rejected_before_artifacts(tmp_path):
    spec = _spec(tmp_path, "python")
    entrants = (
        MatchEntrant("A", "runner", 0, build_agent("runner", 0)),
        MatchEntrant.python("B", "python", 32, spec),
    )
    replay = tmp_path / "replay.jsonl"

    with pytest.raises(UnsupportedMatchCompositionError, match="Mixed VM/Python"):
        NativeMatchService().run(
            MatchRequest(Config(arena_size=64), entrants, 1, replay, False)
        )

    assert not replay.exists()
