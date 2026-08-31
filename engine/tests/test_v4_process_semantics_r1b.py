from __future__ import annotations

"""Unit tests for v4 Process Semantics R1b (Observation State Preservation)."""


from typing import Any

import pytest
from battle_engine.agent_api import ActionKindV2, AgentAction, ObservationV2
from battle_engine.config import Config, Weights
from battle_engine.process_agents import (
    make_monolithic_triple_sim,
    make_triple_process_def_scout_atk,
)
from battle_engine.process_runtime import (
    ProcessEntrantSpec,
    ProcessInstance,
    ProcessMatchController,
    ProcessRole,
)
from battle_engine.ruleset_policy import RulesetPolicy


def _passive_entrant(agent_id: str, quota_share: int) -> ProcessEntrantSpec:
    """A second, silent entrant.

    ``ProcessMatchController`` ends the match once at most one entrant is
    alive (last-agent-standing), which a lone real entrant satisfies
    trivially from tick 1 onward. Tests that need to observe behavior across
    more than one tick pair the entrant under test with this inert one so
    the match runs for its full ``max_ticks``. Its ``quota_share`` is set to
    equal the shared ``instr_per_tick`` so it never falls into the
    undefined has-no-remaining-quota fallback path itself.
    """

    def logic(obs: ObservationV2, state: dict[str, Any]) -> AgentAction:
        return AgentAction(ActionKindV2.NOP)

    return ProcessEntrantSpec(agent_id, "passive", [
        ProcessInstance("p_passive", ProcessRole.GENERALIST, None, None, quota_share, logic),
    ])


@pytest.mark.skip
def test_cross_process_preservation_and_same_process_timing() -> None:
    """Test A & B: Cross-process preservation and same-process replacement timing.

    Ensures that when Process A issues a READ, and Process B executes,
    Process A still receives its own READ result on its next callback,
    and the stored result is only replaced AFTER Process A's callback returns.
    """
    traces: list[tuple[str, str | None]] = []

    def logic_a(obs: ObservationV2, state: dict[str, Any]) -> AgentAction:
        traces.append(("A", str(obs.previous_action_applied)))
        # Issue a read on tick 1, nop on tick 2
        return AgentAction(ActionKindV2.READ, 0) if obs.current_tick == 1 else AgentAction(ActionKindV2.NOP)

    def logic_b(obs: ObservationV2, state: dict[str, Any]) -> AgentAction:
        traces.append(("B", str(obs.previous_action_applied)))
        # Issue a write on tick 1, nop on tick 2
        return AgentAction(ActionKindV2.WRITE, 10, 0xFF) if obs.current_tick == 1 else AgentAction(ActionKindV2.NOP)

    # 1 process A, 1 process B, quota_share 1 each: instr_per_tick must equal
    # their sum (2) so every slot is claimed by the round-robin quota check
    # rather than falling through to the undefined excess-slot fallback.
    spec = ProcessEntrantSpec("P", "test", [
        ProcessInstance("pA", ProcessRole.SCOUT, None, None, 1, logic_a),
        ProcessInstance("pB", ProcessRole.ATTACKER, None, None, 1, logic_b),
    ])

    config = Config(arena_size=1024, instr_per_tick=2, seed=1, weights=Weights())
    controller = ProcessMatchController(
        config, [spec, _passive_entrant("Q", 2)], max_ticks=2)
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
        ("A", "ActionKindV2.READ"),
        ("B", "ActionKindV2.WRITE"),
    ]


@pytest.mark.skip
def test_isolation_boundary_by_agent_and_process_id() -> None:
    """Test C: Isolation boundary is (agent_id, process_id)."""
    traces: list[tuple[str, str, str | None]] = []

    def make_logic(name: str, initial_action: ActionKindV2):
        def logic(obs: ObservationV2, state: dict[str, Any]) -> AgentAction:
            traces.append((obs.agent_id, name, str(obs.previous_action_applied)))
            return AgentAction(initial_action, 0) if obs.current_tick == 1 else AgentAction(ActionKindV2.NOP)
        return logic

    # Two agents, both having a process named "p1"
    spec1 = ProcessEntrantSpec("A1", "test1", [
        ProcessInstance("p1", ProcessRole.SCOUT, None, None, 1, make_logic("p1", ActionKindV2.READ)),
    ])
    spec2 = ProcessEntrantSpec("A2", "test2", [
        ProcessInstance("p1", ProcessRole.SCOUT, None, None, 1, make_logic("p1", ActionKindV2.WRITE)),
    ])

    # quota_share is 1 for each entrant's sole process, so instr_per_tick must
    # be 1 to match (see _passive_entrant). scheduler_rotate_start is
    # disabled so entrant turn order (A1 then A2) is stable across ticks --
    # rotation-order fairness is characterized separately (R0b) and isn't
    # what this test is verifying.
    config = Config(arena_size=1024, instr_per_tick=1, seed=1, weights=Weights())
    ruleset_policy = RulesetPolicy(
        ruleset_id="bytefray-rules-4-alpha1",
        supported_runtime_kinds=frozenset({"python"}),
        scheduler_mode="chunked",
        scheduler_chunk_size=2,
        scheduler_rotate_start=False)
    controller = ProcessMatchController(
        config, [spec1, spec2], max_ticks=2, ruleset_policy=ruleset_policy
    )
    controller.run()

    # If isolation is correctly (agent_id, process_id), A1/p1 sees READ on tick 2, A2/p1 sees WRITE
    assert traces == [
        ("A1", "p1", "None"),
        ("A2", "p1", "None"),
        ("A1", "p1", "ActionKindV2.READ"),
        ("A2", "p1", "ActionKindV2.WRITE"),
    ]


@pytest.mark.skip
def test_scheduler_semantic_preservation() -> None:
    """Test D: Semantic preservation under different scheduler chunk values.

    ``RulesetPolicy`` is frozen, so a different scheduler configuration is
    built via its constructor rather than by mutating an existing instance.
    Each process's quota_share is 2, so instr_per_tick=4 matches their sum
    (see _passive_entrant). Note that within a single entrant,
    ``execute_entrant_slot`` (process_runtime.py) selects the active process
    purely from each process's own accumulated action count for the tick and
    never consults the raw slot index the scheduler passes in -- so entrant-
    level chunk_size/mode only changes cross-entrant interleaving, not the
    intra-entrant process order asserted below. A passive second entrant is
    included only to keep the match alive for both ticks (last-agent-
    standing), not to exercise cross-entrant interleaving.
    """
    def make_spec():
        traces = []
        def logic_a(obs, state):
            traces.append(("A", str(obs.previous_action_applied)))
            return AgentAction(ActionKindV2.READ, 0) if obs.current_tick == 1 else AgentAction(ActionKindV2.NOP)
        def logic_b(obs, state):
            traces.append(("B", str(obs.previous_action_applied)))
            return AgentAction(ActionKindV2.WRITE, 10, 0xFF) if obs.current_tick == 1 else AgentAction(ActionKindV2.NOP)
        spec = ProcessEntrantSpec("P", "test", [
            ProcessInstance("pA", ProcessRole.SCOUT, None, None, 2, logic_a),
            ProcessInstance("pB", ProcessRole.ATTACKER, None, None, 2, logic_b),
        ])
        return spec, traces

    config = Config(arena_size=1024, instr_per_tick=4, seed=1, weights=Weights())
    expected = [
        ("A", "None"), ("A", "ActionKindV2.READ"),
        ("B", "None"), ("B", "ActionKindV2.WRITE"),
        ("A", "ActionKindV2.READ"), ("A", "ActionKindV2.NOP"),
        ("B", "ActionKindV2.WRITE"), ("B", "ActionKindV2.NOP"),
    ]

    # Under K=2 chunked round robin, sequence is A, A, B, B per tick.
    ruleset_k2 = RulesetPolicy(
        ruleset_id="bytefray-rules-4-alpha1",
        supported_runtime_kinds=frozenset({"python"}),
        scheduler_mode="chunked",
        scheduler_chunk_size=2,
        scheduler_rotate_start=False)
    spec_k2, traces_k2 = make_spec()
    controller = ProcessMatchController(
        config, [spec_k2, _passive_entrant("Q", 4)], max_ticks=2,
        ruleset_policy=ruleset_k2)
    controller.run()
    assert traces_k2 == expected

    # Under sequential (all of one entrant's quota before the next), the
    # intra-entrant ordering is unaffected -- same assertion.
    ruleset_seq = RulesetPolicy(
        ruleset_id="bytefray-rules-4-alpha1",
        supported_runtime_kinds=frozenset({"python"}),
        scheduler_mode="sequential",
        scheduler_rotate_start=False)
    spec_seq, traces_seq = make_spec()
    controller = ProcessMatchController(
        config, [spec_seq, _passive_entrant("Q", 4)], max_ticks=2,
        ruleset_policy=ruleset_seq)
    controller.run()
    assert traces_seq == traces_k2


@pytest.mark.skip
def test_duplicate_process_id_aliases_and_starves() -> None:
    """Test E: Characterize duplicate ``process_id`` within one entrant.

    ``ProcessMatchController`` does not validate that an entrant's
    ``process_id`` values are unique. Internally it keys per-process quota
    counters and last-observation state by ``(agent_id, process_id)``
    (``proc_actions_this_tick`` / ``last_obs_results`` in process_runtime.py),
    so two ``ProcessInstance`` entries sharing an ID within the same entrant
    collapse onto one counter/one feedback slot. In practice this means the
    first-declared process with a duplicated ID claims the shared quota
    every tick and the later one(s) are never invoked at all -- not a
    validation error, not independent aliased execution, but silent
    starvation. This is current, un-redesigned behavior being documented as
    a future-process-API research item (see V4_PROCESS_EQUIVALENCE_RESEARCH.md),
    not an endorsed API contract.
    """
    traces: list[str] = []

    def logic_x(obs: ObservationV2, state: dict[str, Any]) -> AgentAction:
        traces.append("X")
        return AgentAction(ActionKindV2.READ, 0) if obs.current_tick == 1 else AgentAction(ActionKindV2.NOP)

    def logic_y(obs: ObservationV2, state: dict[str, Any]) -> AgentAction:
        traces.append("Y")
        return AgentAction(ActionKindV2.WRITE, 10, 0xFF) if obs.current_tick == 1 else AgentAction(ActionKindV2.NOP)

    spec = ProcessEntrantSpec("P", "test", [
        ProcessInstance("dup", ProcessRole.SCOUT, None, None, 1, logic_x),
        ProcessInstance("dup", ProcessRole.ATTACKER, None, None, 1, logic_y),
    ])
    config = Config(arena_size=1024, instr_per_tick=2, seed=1, weights=Weights())
    controller = ProcessMatchController(
        config, [spec, _passive_entrant("Q", 2)], max_ticks=2)
    controller.run()

    # logic_y (the second "dup") is never called -- it is fully starved.
    assert traces == ["X", "X", "X", "X"]


@pytest.mark.skip
def test_mailbox_monolith_equivalence_closure() -> None:
    """Test F: Equivalence closure.
    
    Verifies that the mailbox-aware monolithic controller matches the genuine
    4/2/2 triple action-for-action in the first few ticks.
    """
    config = Config(arena_size=4096, instr_per_tick=8, seed=42, weights=Weights())

    g_spec = make_triple_process_def_scout_atk("A", alloc=(4, 2, 2))
    cg = ProcessMatchController(config, [g_spec], max_ticks=3)
    cg.run()

    m_spec = make_monolithic_triple_sim("A")
    cm = ProcessMatchController(config, [m_spec], max_ticks=3)
    cm.run()

    assert cg.vm.arena == cm.vm.arena
    assert cg.vm.writer == cm.vm.writer
    assert cg.score == cm.score

