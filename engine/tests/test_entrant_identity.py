"""Characterization tests for v1.5 Phase 5's entrant-identity/execution-state split.

See ``docs/V1_5_PHASE5_ENTRANT_IDENTITY_EXECUTION_STATE.md``. These tests
protect the specific structural risks that refactor introduced -- that
``EntrantIdentity`` is the sole authoritative store on ``MatchEntrant``/
``Agent``/``PythonEntrantState`` rather than a value duplicated alongside
flat ``agent_id``/``name`` fields, that entrant order and per-entrant
identity distinctness survive end-to-end, and that VM's synthetic
``Agent.identity.name`` (VM execution state never tracked a real display
name) cannot silently leak into persisted output in place of the real
``MatchEntrant.name``. General Ruleset-v1 gameplay behavior is already
covered unchanged by the golden corpus and every pre-existing suite.
"""

from __future__ import annotations

import json
import random
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from battle_engine.agent_state import Agent
from battle_engine.agents import resolve_agent
from battle_engine.builtins import build_agent
from battle_engine.config import Config
from battle_engine.core import NOP, Kernel, enc
from battle_engine.entrant_identity import EntrantIdentity
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.python_runtime import PythonEntrantController, PythonEntrantState
from battle_engine.telemetry import NullSummarySink


class _NullSink:
    def emit(self, record: dict[str, Any]) -> None:
        pass

    def close(self) -> None:
        pass


def _config(**overrides: Any) -> Config:
    return Config(arena_size=64, instr_per_tick=2, **overrides)


def test_entrant_identity_is_frozen_hashable_and_value_comparable():
    identity = EntrantIdentity(agent_id="A", name="Alpha")
    with pytest.raises(FrozenInstanceError):
        identity.agent_id = "B"  # type: ignore[misc]
    assert identity == EntrantIdentity(agent_id="A", name="Alpha")
    assert hash(identity) == hash(EntrantIdentity(agent_id="A", name="Alpha"))


def test_match_entrant_agent_id_and_name_derive_from_identity_not_duplicated_storage():
    entrant = MatchEntrant("A", "Alpha", 0, enc(NOP))
    assert entrant.identity == EntrantIdentity(agent_id="A", name="Alpha")
    assert entrant.agent_id == "A"
    assert entrant.name == "Alpha"
    # `identity` is the sole authoritative store: no separate `agent_id`/
    # `name` instance attribute exists alongside it (both are read-only
    # properties derived from `identity`, not stored fields).
    assert "agent_id" not in vars(entrant)
    assert "name" not in vars(entrant)


def test_match_entrant_python_classmethod_builds_the_same_identity_shape():
    entrant = MatchEntrant.python("B", "Beta", 32, object())
    assert entrant.identity == EntrantIdentity(agent_id="B", name="Beta")
    assert entrant.kind == "python"


def test_vm_agent_agent_id_derives_from_identity_not_duplicated_storage():
    agent = Agent(agent_id="A", pc=0)
    assert agent.identity == EntrantIdentity(agent_id="A", name="A")
    assert agent.agent_id == "A"
    assert "agent_id" not in vars(agent)


def test_python_entrant_state_agent_id_and_name_derive_from_identity_not_duplicated_storage():
    state = PythonEntrantState("A", "Alpha", loaded=SimpleNamespace(), rng=random.Random(1))
    assert state.identity == EntrantIdentity(agent_id="A", name="Alpha")
    assert state.agent_id == "A"
    assert state.name == "Alpha"
    assert "agent_id" not in vars(state)
    assert "name" not in vars(state)


def test_duplicate_display_names_remain_distinct_entrant_identities():
    first = EntrantIdentity(agent_id="A", name="Same")
    second = EntrantIdentity(agent_id="B", name="Same")
    assert first != second
    assert first.name == second.name
    assert first.agent_id != second.agent_id


def test_vm_match_preserves_entrant_order_and_one_identity_per_execution_state():
    kernel = Kernel(_config(), sink=_NullSink(), summary_sink=NullSummarySink())  # type: ignore[arg-type]
    kernel.spawn("A", 0, enc(NOP))
    kernel.spawn("B", 16, enc(NOP))
    kernel.spawn("C", 32, enc(NOP))
    kernel.run(max_ticks=1, verbose=False)

    assert [agent.agent_id for agent in kernel.agents] == ["A", "B", "C"]
    identities = [agent.identity for agent in kernel.agents]
    assert len({id(identity) for identity in identities}) == 3
    assert len(set(identities)) == 3


def test_vm_native_result_name_comes_from_match_entrant_not_synthetic_agent_identity(tmp_path):
    """VM ``Agent.identity.name`` synthesizes to ``agent_id`` (the VM has never

    tracked a separate display name on its execution state -- see
    ``agent_state.Agent``'s docstring). Persisted results must keep sourcing
    the real display name from ``MatchEntrant``/``_build_result``'s existing
    lookup, not from ``Agent.identity.name``, or a real display name would
    silently regress to the bare ``agent_id``.
    """

    entrants = (
        MatchEntrant("A", "Real Display Name", 0, enc(NOP)),
        MatchEntrant("B", "B", 16, enc(NOP)),
    )
    result = NativeMatchService().run(
        MatchRequest(_config(), entrants, 2, tmp_path / "replay.jsonl", False)
    )
    assert result.agents_by_id["A"].name == "Real Display Name"


def _python_spec(root: Path, name: str) -> Any:
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
    (directory / "agent.py").write_text(
        """
from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        pass

    def act(self, observation):
        return AgentAction(ActionKind.NOP)

def create_agent():
    return Agent()
""",
        encoding="utf-8",
    )
    return resolve_agent(root, name)


def test_python_match_preserves_entrant_order_and_one_identity_per_execution_state(tmp_path):
    entrants = tuple(
        MatchEntrant.python(chr(ord("A") + slot), name, slot * 16, _python_spec(tmp_path, name))
        for slot, name in enumerate(["alpha", "beta", "gamma"])
    )
    controller = PythonEntrantController(Config(arena_size=64, instr_per_tick=2), entrants, 1)

    assert [state.agent_id for state in controller.states] == ["A", "B", "C"]
    identities = [state.identity for state in controller.states]
    assert identities == [
        EntrantIdentity(agent_id="A", name="alpha"),
        EntrantIdentity(agent_id="B", name="beta"),
        EntrantIdentity(agent_id="C", name="gamma"),
    ]
    assert len(set(identities)) == 3


def test_vm_agent_identity_does_not_leak_into_ownership_key_namespace():
    """``EntrantIdentity`` must not casually become a dict key replacing

    the existing ``agent_id``-string-keyed structures the engine already
    uses (ownership counts, writer map, score, statistics) -- see the phase
    brief's "Do not turn EntrantIdentity into a dictionary key casually."
    """

    kernel = Kernel(_config(), sink=_NullSink(), summary_sink=NullSummarySink())  # type: ignore[arg-type]
    kernel.spawn("A", 0, build_agent("writer", 0, offset=32, byte=0x7A))
    kernel.spawn("B", 32, enc(NOP))
    kernel.run(max_ticks=3, verbose=False)

    assert all(isinstance(key, str) for key in kernel.vm.ownership_counts)
    assert all(isinstance(key, str) for key in kernel.score)
    assert all(isinstance(key, str) for key in kernel.stats)
