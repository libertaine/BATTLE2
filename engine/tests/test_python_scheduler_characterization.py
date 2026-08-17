"""Python-runtime counterpart to ``test_scheduler_characterization.py``.

The VM scheduler's spawn-order/quota/dead-entrant-skip behavior is pinned
directly (via a ``vm.step`` spy) in that module. ``python_runtime.
PythonEntrantController.run`` implements the identical scheduling shape
(sequential entrants, per-tick quota, dead/forfeited entrants skipped) as
its own, separately maintained loop -- see ``supervised_runtime``'s module
docstring for why it is a deliberate near-duplicate rather than a shared
base class. Before v1.5 may extract a shared scheduler abstraction behind
both runtimes, this file pins the Python-side call order with the same
directness the VM side already has, rather than relying only on the
aggregate golden-corpus digest in ``test_ruleset_v1_equivalence.py`` to
notice a reordering.
"""

from __future__ import annotations

import json
from pathlib import Path

from battle_engine.agents import resolve_agent
from battle_engine.config import Config
from battle_engine.match_service import MatchEntrant
from battle_engine.python_runtime import PythonEntrantController
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

HALTS_SECOND_CALL_SOURCE = """
from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        self.calls = 0

    def act(self, observation):
        self.calls += 1
        if self.calls == 2:
            return AgentAction(ActionKind.HALT)
        return AgentAction(ActionKind.NOP)

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


def _spy_act_order(controller: PythonEntrantController) -> list[str]:
    """Wrap each loaded instance's ``act`` to record call order, in place.

    Mirrors ``test_scheduler_characterization.py``'s ``monkeypatch.setattr``
    spy on ``kernel.vm.step`` -- an instance-attribute override rather than
    a class patch, so it never leaks across entrants or tests.
    """

    calls: list[str] = []
    for state in controller.states:
        original = state.loaded.instance.act

        def make_wrapper(agent_id: str, act):
            def wrapper(observation):
                calls.append(agent_id)
                return act(observation)

            return wrapper

        state.loaded.instance.act = make_wrapper(state.agent_id, original)  # type: ignore[method-assign]
    return calls


def test_alive_entrants_consume_full_quota_in_spawn_order(tmp_path):
    entrants = _entrants(
        tmp_path, {"alpha": PASSIVE_SOURCE, "beta": PASSIVE_SOURCE, "gamma": PASSIVE_SOURCE}
    )
    controller = PythonEntrantController(Config(arena_size=64, instr_per_tick=3), entrants, 1)
    calls = _spy_act_order(controller)

    controller.run(JSONLSink(str(tmp_path / "replay.jsonl")), verbose=False)

    assert calls == ["A", "A", "A", "B", "B", "B", "C", "C", "C"]
    assert [state.total_actions for state in controller.states] == [3, 3, 3]


def test_forfeited_entrant_is_skipped_on_later_ticks_and_next_entrant_still_gets_full_quota(
    tmp_path,
):
    entrants = _entrants(
        tmp_path,
        {"alpha": PASSIVE_SOURCE, "halts": HALTS_SECOND_CALL_SOURCE, "gamma": PASSIVE_SOURCE},
    )
    controller = PythonEntrantController(Config(arena_size=64, instr_per_tick=3), entrants, 2)
    calls = _spy_act_order(controller)

    controller.run(JSONLSink(str(tmp_path / "replay.jsonl")), verbose=False)

    assert calls == [
        "A", "A", "A",
        "B", "B",  # halts on its own second call, mid-quota; C is unaffected this tick
        "C", "C", "C",
        "A", "A", "A",
        # B (dead) is skipped entirely on tick 2
        "C", "C", "C",
    ]
    states_by_id = {state.agent_id: state for state in controller.states}
    assert states_by_id["B"].alive is False
    assert states_by_id["B"].entrant_termination == "normal_halt"
    assert states_by_id["B"].total_actions == 2
    assert states_by_id["A"].total_actions == 6
    assert states_by_id["C"].total_actions == 6
