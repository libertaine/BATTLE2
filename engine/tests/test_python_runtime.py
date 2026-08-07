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
    PythonMatchExecutionError,
    UnsupportedMatchCompositionError,
)
from battle_engine.python_runtime import (
    InvalidPythonActionError,
    PythonEntrantController,
    PythonEntrantInitializationError,
    PythonEntrantState,
    TerminationReason,
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
        ("raise RuntimeError('boom')", "agent_action_failed"),
        ("return object()", "agent_action_invalid"),
        ("return AgentAction('future')", "agent_action_invalid"),
        ("return AgentAction(ActionKind.WRITE, 'bad', 1)", "agent_action_invalid"),
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
    assert failure.stage == "action"
    assert failure.agent_id == "A"
    assert failure.slot == 0
    assert failure.tick == 1
    assert failure.action_slot == 0
    assert result.winner == "B"
    assert result.termination_reason is TerminationReason.LAST_AGENT_STANDING
    assert result.agents_by_id["A"].termination_reason == "forfeit"
    assert result.agents_by_id["A"].kills == 0
    records = [json.loads(line) for line in replay.read_text().splitlines()]
    assert records[1]["events"][0] == {
        "type": "forfeit",
        "victim": "A",
        "reason": code,
        "stage": "action",
        "tick": 1,
        "action_slot": 0,
    }
    assert "Traceback" not in replay.read_text()


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

    assert caught.value.diagnostic.code == "agent_reset_failed"
    assert caught.value.diagnostic.stage == "reset"
    assert caught.value.diagnostic.agent_id == "A"
    assert caught.value.diagnostic.slot == 0
    assert caught.value.diagnostic.exception_type == "RuntimeError"
    assert "RuntimeError: reset boom" in str(caught.value)
    assert not replay.exists()


def test_reset_rejection_removes_stale_success_artifacts(tmp_path):
    broken = """
class Agent:
    def reset(self, context): raise RuntimeError("reset boom")
    def act(self, observation): return None
def create_agent(): return Agent()
"""
    entrants = _entrants(tmp_path, {"broken": broken, "passive": PASSIVE_SOURCE})
    replay = tmp_path / "replay.jsonl"
    summary = tmp_path / "summary.json"
    replay.write_text("stale replay", encoding="utf-8")
    summary.write_text("stale summary", encoding="utf-8")

    with pytest.raises(PythonEntrantInitializationError):
        NativeMatchService().run(
            MatchRequest(Config(arena_size=64), entrants, 1, replay, False)
        )

    assert not replay.exists()
    assert not summary.exists()


def test_halt_and_tick_limit_have_explicit_termination_reasons(tmp_path):
    halt = """
from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, context): pass
    def act(self, observation): return AgentAction(ActionKind.HALT)
def create_agent(): return Agent()
"""
    halt_result = NativeMatchService().run(
        MatchRequest(
            Config(arena_size=64),
            _entrants(tmp_path / "halt", {"halt": halt, "passive": PASSIVE_SOURCE}),
            3,
            tmp_path / "halt.jsonl",
            False,
        )
    )
    assert halt_result.termination_reason is TerminationReason.LAST_AGENT_STANDING
    assert halt_result.agents_by_id["A"].termination_reason == "normal_halt"
    assert halt_result.agents_by_id["A"].diagnostic is None

    limit_result = NativeMatchService().run(
        MatchRequest(
            Config(arena_size=64, instr_per_tick=2),
            _entrants(
                tmp_path / "limit", {"alpha": PASSIVE_SOURCE, "beta": PASSIVE_SOURCE}
            ),
            2,
            tmp_path / "limit.jsonl",
            False,
        )
    )
    assert limit_result.termination_reason is TerminationReason.TICK_LIMIT
    assert [agent.cpu_total for agent in limit_result.agents] == [4, 4]


def test_both_forfeits_are_ordered_and_have_no_false_kills(tmp_path):
    failing = """
class Agent:
    def reset(self, context): pass
    def act(self, observation): raise RuntimeError("same failure")
def create_agent(): return Agent()
"""
    replay = tmp_path / "both.jsonl"
    result = NativeMatchService().run(
        MatchRequest(
            Config(arena_size=64),
            _entrants(tmp_path, {"alpha": failing, "beta": failing}),
            3,
            replay,
            False,
        )
    )

    assert result.termination_reason is TerminationReason.ALL_AGENTS_DEAD
    assert result.winner == "tie"
    assert [(agent.cpu_total, agent.kills, agent.deaths) for agent in result.agents] == [
        (1, 0, 1),
        (1, 0, 1),
    ]
    events = json.loads(replay.read_text().splitlines()[1])["events"]
    assert [event["victim"] for event in events] == ["A", "B"]


def test_repeated_service_runs_reload_modules_and_do_not_leak_state(tmp_path):
    source = """
from battle_engine.agent_api import ActionKind, AgentAction
factory_calls = 0
class Agent:
    def reset(self, context): self.calls = 0
    def act(self, observation):
        self.calls += 1
        return AgentAction(ActionKind.NOP if factory_calls == 1 else ActionKind.HALT)
def create_agent():
    global factory_calls
    factory_calls += 1
    return Agent()
"""
    entrants = _entrants(tmp_path, {"alpha": source, "beta": source})
    request = MatchRequest(Config(arena_size=64), entrants, 1, tmp_path / "same.jsonl", False)

    first = NativeMatchService().run(request)
    second = NativeMatchService().run(request)

    assert first.termination_reason is TerminationReason.TICK_LIMIT
    assert second.termination_reason is TerminationReason.TICK_LIMIT
    assert [agent.cpu_total for agent in first.agents] == [8, 8]
    assert [agent.cpu_total for agent in second.agents] == [8, 8]


def test_internal_reproducibility_metadata_is_stable(tmp_path):
    entrants = _entrants(tmp_path, {"alpha": PASSIVE_SOURCE, "beta": PASSIVE_SOURCE})
    first = PythonEntrantController(Config(arena_size=64, seed=12), entrants, 1)
    second = PythonEntrantController(Config(arena_size=64, seed=12), entrants, 1)

    assert [(s.slot, s.derived_seed, s.source_digest) for s in first.states] == [
        (s.slot, s.derived_seed, s.source_digest) for s in second.states
    ]
    assert all(len(state.source_digest) == 64 for state in first.states)
    assert first.states[0].derived_seed != first.states[1].derived_seed


def test_invalid_configuration_is_structured_and_removes_stale_outputs(tmp_path):
    entrants = _entrants(tmp_path, {"alpha": PASSIVE_SOURCE, "beta": PASSIVE_SOURCE})
    replay = tmp_path / "invalid.jsonl"
    replay.write_text("stale", encoding="utf-8")

    with pytest.raises(PythonEntrantInitializationError) as caught:
        NativeMatchService().run(
            MatchRequest(Config(arena_size=64), entrants, 0, replay, False)
        )

    assert caught.value.diagnostic.code == "match_configuration_invalid"
    assert caught.value.diagnostic.stage == "configuration"
    assert not replay.exists()


def test_contract_failure_is_preflighted_with_structured_diagnostic(tmp_path):
    invalid = """
class Agent:
    def reset(self, context): pass
def create_agent(): return Agent()
"""
    entrants = _entrants(tmp_path, {"invalid": invalid, "passive": PASSIVE_SOURCE})

    with pytest.raises(PythonEntrantInitializationError) as caught:
        NativeMatchService().run(
            MatchRequest(Config(arena_size=64), entrants, 1, tmp_path / "bad.jsonl", False)
        )

    diagnostic = caught.value.diagnostic
    assert diagnostic.code == "agent_contract_invalid"
    assert diagnostic.stage == "load"
    assert diagnostic.agent_id == "A"
    assert diagnostic.slot == 0
    assert diagnostic.exception_type == "AgentContractError"


def test_late_action_failure_counts_only_callbacks_and_publishes_completed_replay(tmp_path):
    late = """
from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, context): self.calls = 0
    def act(self, observation):
        self.calls += 1
        if self.calls == 3: raise RuntimeError("late failure")
        return AgentAction(ActionKind.WRITE, self.calls, self.calls)
def create_agent(): return Agent()
"""
    replay = tmp_path / "late.jsonl"
    result = NativeMatchService().run(
        MatchRequest(
            Config(arena_size=64, instr_per_tick=4),
            _entrants(tmp_path, {"late": late, "passive": PASSIVE_SOURCE}),
            3,
            replay,
            False,
        )
    )

    failed = result.agents_by_id["A"]
    assert (failed.cpu_total, failed.mem_writes, failed.kills, failed.deaths) == (3, 2, 0, 1)
    assert failed.diagnostic is not None
    assert (failed.diagnostic.tick, failed.diagnostic.action_slot) == (1, 2)
    assert replay.exists()


def test_replay_writer_failure_leaves_no_final_or_temporary_artifact(tmp_path, monkeypatch):
    entrants = _entrants(tmp_path, {"alpha": PASSIVE_SOURCE, "beta": PASSIVE_SOURCE})
    replay = tmp_path / "failed.jsonl"

    class FailingSink:
        def __init__(self, path):
            self.path = path

        def emit(self, record):
            raise OSError("disk unavailable")

        def close(self):
            pass

    monkeypatch.setattr("battle_engine.match_service.JSONLSink", FailingSink)

    with pytest.raises(PythonMatchExecutionError) as caught:
        NativeMatchService().run(
            MatchRequest(Config(arena_size=64), entrants, 1, replay, False)
        )

    assert caught.value.diagnostic.code == "artifact_write_failed"
    assert caught.value.diagnostic.stage == "artifact"
    assert not replay.exists()
    assert not list(tmp_path.glob(".failed.jsonl.*.tmp"))


def test_engine_failure_is_structured_and_cleans_artifacts(tmp_path, monkeypatch):
    entrants = _entrants(tmp_path, {"alpha": PASSIVE_SOURCE, "beta": PASSIVE_SOURCE})
    replay = tmp_path / "engine-failed.jsonl"
    summary = tmp_path / "summary.json"
    summary.write_text("stale", encoding="utf-8")

    def fail_run(self, sink, *, verbose):
        raise RuntimeError("internal failure")

    monkeypatch.setattr(PythonEntrantController, "run", fail_run)

    with pytest.raises(PythonMatchExecutionError) as caught:
        NativeMatchService().run(
            MatchRequest(Config(arena_size=64), entrants, 1, replay, False)
        )

    assert caught.value.diagnostic.code == "engine_failed"
    assert caught.value.diagnostic.stage == "execution"
    assert caught.value.diagnostic.exception_type == "RuntimeError"
    assert not replay.exists()
    assert not summary.exists()
    assert not list(tmp_path.glob(".engine-failed.jsonl.*.tmp"))


def test_mixed_vm_python_match_is_rejected_before_artifacts(tmp_path):
    spec = _spec(tmp_path, "python")
    entrants = (
        MatchEntrant("A", "runner", 0, build_agent("runner", 0)),
        MatchEntrant.python("B", "python", 32, spec),
    )
    replay = tmp_path / "replay.jsonl"

    with pytest.raises(UnsupportedMatchCompositionError, match="Mixed VM/Python") as caught:
        NativeMatchService().run(
            MatchRequest(Config(arena_size=64), entrants, 1, replay, False)
        )

    assert caught.value.diagnostic.code == "unsupported_match_composition"
    assert caught.value.diagnostic.stage == "configuration"
    assert not replay.exists()
