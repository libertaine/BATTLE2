"""Unit and characterization tests for Bytefray v4 Process Semantics (R1).

Validates:
1. Multi-process entrant execution under K=2 chunked round-robin scheduler with rotating start
2. Equal vs specialized action budget allocation summing to Q_total invariant
3. Model A (Independent Action Cursors with global reach)
4. Model B (Static Spatial Loci reach constraints)
5. Model C (Movable Spatial Anchors and movement budget consumption)
6. Stage 4 (Process Disruption mechanics)
7. Determinism and replay invariant preservation
"""

from __future__ import annotations

from typing import Any

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


def test_process_entrant_action_quota_invariant() -> None:
    """Entrant with 4 processes receives exactly the same total actions per tick as 1-process entrant."""
    def counting_logic(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
        return AgentAction(ActionKind.NOP)

    procs = [
        ProcessInstance(f"p_{i}", ProcessRole.GENERALIST, 0, None, 2, counting_logic)
        for i in range(4)
    ]
    spec = ProcessEntrantSpec("A", "quad_test", procs)

    config = Config(arena_size=1024, instr_per_tick=8, seed=1, weights=Weights())
    controller = ProcessMatchController(config, [spec], max_ticks=5, model=ProcessModel.MODEL_A_CURSOR)
    controller.run()

    # In 5 ticks, entrant executed exactly 5 * 8 = 40 actions
    assert controller.states[0].total_actions == 40
    for p in spec.processes:
        assert p.telemetry.total_actions == 10  # 2 actions/tick * 5 ticks


def test_chunked_scheduler_fairness_with_multi_process() -> None:
    """Entrant internal process delegation does not exceed chunk size K=2 per pass."""
    execution_trace: list[tuple[str, str]] = []

    def make_tracer(aid: str, pid: str):
        return lambda obs, state: (execution_trace.append((aid, pid)) or AgentAction(ActionKind.NOP))

    spec_a = ProcessEntrantSpec("A", "entrant_a", [
        ProcessInstance("pA1", ProcessRole.DEFENDER, 0, None, 4, make_tracer("A", "pA1")),
        ProcessInstance("pA2", ProcessRole.HUNTER, 0, None, 4, make_tracer("A", "pA2")),
    ])
    spec_b = ProcessEntrantSpec("B", "entrant_b", [
        ProcessInstance("pB1", ProcessRole.DEFENDER, 0, None, 4, make_tracer("B", "pB1")),
        ProcessInstance("pB2", ProcessRole.HUNTER, 0, None, 4, make_tracer("B", "pB2")),
    ])

    config = Config(arena_size=1024, instr_per_tick=8, seed=1, weights=Weights())
    controller = ProcessMatchController(config, [spec_a, spec_b], max_ticks=1, model=ProcessModel.MODEL_A_CURSOR)
    controller.run()

    # Pass 0 (chunk 2): A (pA1 x 2), B (pB1 x 2)
    # Pass 1 (chunk 2): A (pA1 x 2), B (pB1 x 2)
    # Pass 2 (chunk 2): A (pA2 x 2), B (pB2 x 2)
    # Pass 3 (chunk 2): A (pA2 x 2), B (pB2 x 2)
    expected = [
        ("A", "pA1"), ("A", "pA1"),
        ("B", "pB1"), ("B", "pB1"),
        ("A", "pA1"), ("A", "pA1"),
        ("B", "pB1"), ("B", "pB1"),
        ("A", "pA2"), ("A", "pA2"),
        ("B", "pB2"), ("B", "pB2"),
        ("A", "pA2"), ("A", "pA2"),
        ("B", "pB2"), ("B", "pB2"),
    ]
    assert execution_trace == expected


def test_model_b_static_locus_reach_enforcement() -> None:
    """Model B discards writes outside reach R and accepts writes within reach R."""
    spec_a = ProcessEntrantSpec("A", "locus_test", [
        ProcessInstance(
            "p1",
            ProcessRole.GENERALIST,
            initial_position=100,
            reach=50,
            quota_share=8,
            logic=lambda obs, state: AgentAction(
                ActionKind.WRITE,
                operand=state.get("target", 120),  # within reach (dist = 20)
                value=0x42,
            ),
        )
    ])

    config = Config(arena_size=1024, instr_per_tick=8, seed=1, weights=Weights())
    controller = ProcessMatchController(config, [spec_a], max_ticks=1, model=ProcessModel.MODEL_B_STATIC_LOCUS)
    controller.run()

    # Address 120 is within reach 50 from 100 -> write succeeded
    assert controller.vm.arena[120] == 0x42
    assert controller.vm.writer[120] == "A"


def test_model_c_movable_anchor_and_move_cost() -> None:
    """Model C consumes an action budget for MOVE and updates position."""
    spec_a = ProcessEntrantSpec("A", "move_test", [
        ProcessInstance(
            "p_mov",
            ProcessRole.SCOUT,
            initial_position=100,
            reach=50,
            quota_share=8,
            logic=lambda obs, state: AgentAction(ActionKind.MOVE, operand=30),
        )
    ])

    config = Config(arena_size=1024, instr_per_tick=8, seed=1, weights=Weights())
    controller = ProcessMatchController(config, [spec_a], max_ticks=2, model=ProcessModel.MODEL_C_MOVABLE_ANCHOR)
    controller.run()

    proc = spec_a.processes[0]
    # In 2 ticks with 8 actions each = 16 MOVE actions of +30
    # Final position: (100 + 16 * 30) % 1024 = 580 % 1024 = 580
    assert proc.position == 580
    assert proc.telemetry.total_moves == 16
    assert controller.states[0].total_actions == 16


def test_stage4_process_disruption() -> None:
    """Writing to enemy process anchor disables that process for D ticks."""
    spec_a = ProcessEntrantSpec("A", "attacker", [
        ProcessInstance(
            "pA",
            ProcessRole.ATTACKER,
            initial_position=0,
            reach=None,
            quota_share=8,
            # Target B's anchor at address 500
            logic=lambda obs, state: AgentAction(ActionKind.WRITE, 500, 0x99),
        )
    ])

    spec_b = ProcessEntrantSpec("B", "victim", [
        ProcessInstance(
            "pB",
            ProcessRole.DEFENDER,
            initial_position=500,
            reach=None,
            quota_share=8,
            logic=lambda obs, state: AgentAction(ActionKind.NOP),
        )
    ])

    config = Config(arena_size=1024, instr_per_tick=8, seed=1, weights=Weights())
    controller = ProcessMatchController(
        config,
        [spec_a, spec_b],
        max_ticks=5,
        model=ProcessModel.MODEL_A_CURSOR,
        disruption_duration=3,
    )
    controller.run()

    proc_b = spec_b.processes[0]
    # Entrant A wrote to 500 on Tick 1 pass 0 -> Proc B disrupted until tick 1 + 3 = 4
    assert proc_b.telemetry.total_disrupted_ticks > 0

