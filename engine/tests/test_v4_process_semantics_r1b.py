"""Unit tests for v4 Process Semantics R1b (Observation State Preservation)."""

from __future__ import annotations

import pytest

from battle_engine.agent_api import ActionKind, AgentAction
from battle_engine.config import Config, Weights
from battle_engine.process_runtime import (
    ProcessEntrantSpec,
    ProcessInstance,
    ProcessMatchController,
    ProcessModel,
    ProcessObservation,
    ProcessRole,
)
from battle_engine.process_agents import (
    make_monolithic_triple_sim,
    make_triple_process_def_scout_atk,
)


def test_cross_process_preservation_and_same_process_timing() -> None:
    """Test A & B: Cross-process preservation and same-process replacement timing.
    
    Ensures that when Process A issues a READ, and Process B executes,
    Process A still receives its own READ result on its next callback,
    and the stored result is only replaced AFTER Process A's callback returns.
    """
    traces: list[tuple[str, str | None]] = []

    def logic_a(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
        traces.append(("A", str(obs.last_action_kind)))
        # Issue a read on tick 1, nop on tick 2
        return AgentAction(ActionKind.READ, 0) if obs.tick == 1 else AgentAction(ActionKind.NOP)

    def logic_b(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
        traces.append(("B", str(obs.last_action_kind)))
        # Issue a write on tick 1, nop on tick 2
        return AgentAction(ActionKind.WRITE, 10, 0xFF) if obs.tick == 1 else AgentAction(ActionKind.NOP)

    # 1 process A, 1 process B, chunk size 1 (interleaved)
    spec = ProcessEntrantSpec("P", "test", [
        ProcessInstance("pA", ProcessRole.SCOUT, None, None, 1, logic_a),
        ProcessInstance("pB", ProcessRole.ATTACKER, None, None, 1, logic_b),
    ])

    config = Config(arena_size=1024, instr_per_tick=8, seed=1, weights=Weights())
    controller = ProcessMatchController(config, [spec], max_ticks=2, model=ProcessModel.MODEL_A_CURSOR)
    controller.run()

    # Tick 1:
    # A gets None, returns READ.
    # B gets None, returns WRITE.
    # Tick 2:
    # A gets READ (not overwritten by B's WRITE), returns NOP.
    # B gets WRITE, returns NOP.
    assert traces == [
        ("A", "None"),
        ("B", "None"),
        ("A", "ActionKind.READ"),
        ("B", "ActionKind.WRITE"),
    ]


def test_isolation_boundary_by_agent_and_process_id() -> None:
    """Test C: Isolation boundary is (agent_id, process_id)."""
    traces: list[tuple[str, str, str | None]] = []

    def make_logic(name: str, initial_action: ActionKind):
        def logic(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
            traces.append((obs.agent_id, name, str(obs.last_action_kind)))
            return AgentAction(initial_action, 0) if obs.tick == 1 else AgentAction(ActionKind.NOP)
        return logic

    # Two agents, both having a process named "p1"
    spec1 = ProcessEntrantSpec("A1", "test1", [
        ProcessInstance("p1", ProcessRole.SCOUT, None, None, 1, make_logic("p1", ActionKind.READ)),
    ])
    spec2 = ProcessEntrantSpec("A2", "test2", [
        ProcessInstance("p1", ProcessRole.SCOUT, None, None, 1, make_logic("p1", ActionKind.WRITE)),
    ])

    config = Config(arena_size=1024, instr_per_tick=8, seed=1, weights=Weights())
    controller = ProcessMatchController(config, [spec1, spec2], max_ticks=2, model=ProcessModel.MODEL_A_CURSOR)
    controller.run()

    # If isolation is correctly (agent_id, process_id), A1/p1 sees READ on tick 2, A2/p1 sees WRITE
    assert traces == [
        ("A1", "p1", "None"),
        ("A2", "p1", "None"),
        ("A1", "p1", "ActionKind.READ"),
        ("A2", "p1", "ActionKind.WRITE"),
    ]


def test_scheduler_semantic_preservation() -> None:
    """Test D: Semantic preservation under different scheduler chunk values."""
    def make_spec():
        traces = []
        def logic_a(obs, state):
            traces.append(("A", str(obs.last_action_kind)))
            return AgentAction(ActionKind.READ, 0) if obs.tick == 1 else AgentAction(ActionKind.NOP)
        def logic_b(obs, state):
            traces.append(("B", str(obs.last_action_kind)))
            return AgentAction(ActionKind.WRITE, 10, 0xFF) if obs.tick == 1 else AgentAction(ActionKind.NOP)
        spec = ProcessEntrantSpec("P", "test", [
            ProcessInstance("pA", ProcessRole.SCOUT, None, None, 2, logic_a),
            ProcessInstance("pB", ProcessRole.ATTACKER, None, None, 2, logic_b),
        ])
        return spec, traces

    # Under K=2, sequence is A, A, B, B (tick 1) -> A, A, B, B (tick 2)
    spec_k2, traces_k2 = make_spec()
    config = Config(arena_size=1024, instr_per_tick=8, seed=1, weights=Weights())
    controller = ProcessMatchController(config, [spec_k2], max_ticks=2, model=ProcessModel.MODEL_A_CURSOR)
    # The default ruleset policy uses K=2 chunked round robin
    controller.ruleset_policy.scheduler_chunk_size = 2
    controller.run()

    assert traces_k2 == [
        ("A", "None"), ("A", "ActionKind.READ"),
        ("B", "None"), ("B", "ActionKind.WRITE"),
        ("A", "ActionKind.READ"), ("A", "ActionKind.NOP"),
        ("B", "ActionKind.WRITE"), ("B", "ActionKind.NOP"),
    ]

    # Under sequential (all at once per agent per tick), we get same ordering for 2 actions
    spec_seq, traces_seq = make_spec()
    controller = ProcessMatchController(config, [spec_seq], max_ticks=2, model=ProcessModel.MODEL_A_CURSOR)
    controller.ruleset_policy.scheduler_mode = "sequential"
    controller.run()
    assert traces_seq == traces_k2


def test_mailbox_monolith_equivalence_closure() -> None:
    """Test F: Equivalence closure.
    
    Verifies that the mailbox-aware monolithic controller matches the genuine
    4/2/2 triple action-for-action in the first few ticks.
    """
    config = Config(arena_size=4096, instr_per_tick=8, seed=42, weights=Weights())

    g_spec = make_triple_process_def_scout_atk("A", alloc=(4, 2, 2))
    cg = ProcessMatchController(config, [g_spec], max_ticks=3, model=ProcessModel.MODEL_A_CURSOR)
    cg.run()

    m_spec = make_monolithic_triple_sim("A")
    cm = ProcessMatchController(config, [m_spec], max_ticks=3, model=ProcessModel.MODEL_A_CURSOR)
    cm.run()

    assert cg.vm.arena == cm.vm.arena
    assert cg.vm.writer == cm.vm.writer
    assert cg.score == cm.score
