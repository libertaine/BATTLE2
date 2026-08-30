"""Bytefray v4 Research R3 Spatial Challenge (Corrected)."""

from __future__ import annotations

import math
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


def _circular_dist(a: int, b: int, arena_size: int = 1024) -> int:
    d = abs(a - b)
    return min(d, arena_size - d)


def _directed_move(pos: int, target: int, max_delta: int = 64, arena_size: int = 1024) -> int:
    move_delta = target - pos
    half = arena_size // 2
    if move_delta > half:
        move_delta -= arena_size
    elif move_delta < -half:
        move_delta += arena_size
    return max(-max_delta, min(move_delta, max_delta))


def build_multi_anchor_entrant(
    name: str = "Multi",
    initial_pos: int = 100,
    reach: int = 50,
) -> ProcessEntrantSpec:
    """Multi-process entrant starting co-located. Pays deployment cost."""
    # Process 1 stays near 120 and services it
    def p1_logic(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
        return AgentAction(ActionKind.WRITE, operand=120, value=0x11)
        
    # Process 2 deploys to 920 and services it
    def p2_logic(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
        pos = obs.position
        if pos is None:
            return AgentAction(ActionKind.NOP)
        dist = _circular_dist(pos, 920)
        if dist <= reach:
            return AgentAction(ActionKind.WRITE, operand=920, value=0x22)
        # Move optimally towards 920's boundary
        return AgentAction(ActionKind.MOVE, operand=_directed_move(pos, 920))
        
    return ProcessEntrantSpec(name, "multi_proc", [
        ProcessInstance("p1", ProcessRole.DEFENDER, initial_position=initial_pos, reach=reach, quota_share=4, logic=p1_logic),
        ProcessInstance("p2", ProcessRole.HUNTER, initial_position=initial_pos, reach=reach, quota_share=4, logic=p2_logic),
    ])


def build_mono_continuing(
    name: str = "MonoCont",
    initial_pos: int = 100,
    reach: int = 50,
) -> ProcessEntrantSpec:
    """Strong monolithic controller for the continuing response objective.
    Moves boundary-to-boundary rather than center-to-center.
    """
    def mono_logic(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
        pos = obs.position
        if pos is None:
            return AgentAction(ActionKind.NOP)
        
        target = state.get("target", 120)
        tick = obs.tick
        writes_this_tick = state.setdefault("writes_this_tick", {})
        
        # If we are within reach of the CURRENT target, write to it.
        if _circular_dist(pos, target) <= reach:
            if writes_this_tick.get(target) != tick:
                writes_this_tick[target] = tick
                val = 0x11 if target == 120 else 0x22
                
                # If we've now serviced BOTH targets this tick, just stay here and farm writes
                other = 920 if target == 120 else 120
                if writes_this_tick.get(other) != tick:
                    # We still need to service the other one this tick
                    state["target"] = other
                return AgentAction(ActionKind.WRITE, operand=target, value=val)
            else:
                # We already serviced this target this tick.
                # Do we need to service the other target?
                other = 920 if target == 120 else 120
                if writes_this_tick.get(other) != tick:
                    # Switch target and fall through to move
                    target = other
                    state["target"] = target
                else:
                    # Both serviced this tick! Just farm writes on current target.
                    val = 0x11 if target == 120 else 0x22
                    return AgentAction(ActionKind.WRITE, operand=target, value=val)
                    
        # If we are here, we are not in reach of `target`.
        # Move optimally towards target's nearest boundary.
        # Target's nearest boundary depends on direction.
        # For 120 vs 920, the shortest path is across 0.
        # Target 120 boundary: 70. Target 920 boundary: 970.
        opt_target = 70 if target == 120 else 970
        return AgentAction(ActionKind.MOVE, operand=_directed_move(pos, opt_target))
            
    return ProcessEntrantSpec(name, "mono_cont", [
        ProcessInstance("p_mono", ProcessRole.GENERALIST, initial_position=initial_pos, reach=reach, quota_share=8, logic=mono_logic)
    ])


def build_mono_batched(
    name: str = "MonoBatched",
    initial_pos: int = 100,
    reach: int = 50,
) -> ProcessEntrantSpec:
    """Strong monolithic controller for final-ownership only.
    Services one, waits till the end, traverses once, services the other.
    """
    def mono_logic(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
        pos = obs.position
        if pos is None:
            return AgentAction(ActionKind.NOP)
            
        if obs.tick < 9:
            # Just hold 120
            if _circular_dist(pos, 120) <= reach:
                return AgentAction(ActionKind.WRITE, operand=120, value=0x11)
            return AgentAction(ActionKind.MOVE, operand=_directed_move(pos, 120))
        else:
            # End game: move to 920 and write
            if _circular_dist(pos, 920) <= reach:
                return AgentAction(ActionKind.WRITE, operand=920, value=0x22)
            return AgentAction(ActionKind.MOVE, operand=_directed_move(pos, 920))
            
    return ProcessEntrantSpec(name, "mono_batch", [
        ProcessInstance("p_mono", ProcessRole.GENERALIST, initial_position=initial_pos, reach=reach, quota_share=8, logic=mono_logic)
    ])


def build_passive() -> ProcessEntrantSpec:
    def passive_logic(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
        return AgentAction(ActionKind.NOP)
    return ProcessEntrantSpec("Passive", "passive", [ProcessInstance("p", ProcessRole.GENERALIST, 0, 50, 8, passive_logic)])


def test_r3_spatial_challenge() -> None:
    config = Config(arena_size=1024, instr_per_tick=8, seed=1, weights=Weights())
    
    # 1. Geometric Lower Bound Calculation
    reach = 50
    t1, t2 = 120, 920
    D = _circular_dist(t1, t2) # 224
    G = max(0, D - 2 * reach) # 124
    M = 64
    min_moves = math.ceil(G / M) if G > 0 else 0
    print(f"Geometry: D={D}, R={reach}, G={G}, M={M} -> min_moves_per_traversal={min_moves}")
    assert D == 224
    assert min_moves == 2
    
    # 2. Multi-Process
    print("\n--- Running Multi-Process ---")
    multi = build_multi_anchor_entrant()
    ctrl_multi = ProcessMatchController(config, [multi, build_passive()], max_ticks=10, model=ProcessModel.MODEL_C_MOVABLE_ANCHOR)
    ctrl_multi.run()
    
    m_p1 = multi.processes[0]
    m_p2 = multi.processes[1]
    multi_moves = m_p1.telemetry.total_moves + m_p2.telemetry.total_moves
    multi_writes = m_p1.telemetry.total_writes + m_p2.telemetry.total_writes
    print(f"Multi - Writes: {multi_writes}, Moves: {multi_moves}")
    print(f"120 Owner: {ctrl_multi.vm.writer[120]}, 920 Owner: {ctrl_multi.vm.writer[920]}")
    assert multi_moves == 3, f"Expected 3 deployment moves, got {multi_moves}"
    assert ctrl_multi.vm.writer[120] == "Multi"
    assert ctrl_multi.vm.writer[920] == "Multi"
    
    # 3. Monolithic (Continuing Bounded-Response)
    print("\n--- Running Monolithic (Continuing) ---")
    mono_cont = build_mono_continuing()
    ctrl_cont = ProcessMatchController(config, [mono_cont, build_passive()], max_ticks=10, model=ProcessModel.MODEL_C_MOVABLE_ANCHOR)
    ctrl_cont.run()
    
    mc_p = mono_cont.processes[0]
    mc_moves = mc_p.telemetry.total_moves
    mc_writes = mc_p.telemetry.total_writes
    print(f"MonoCont - Writes: {mc_writes}, Moves: {mc_moves}")
    print(f"120 Owner: {ctrl_cont.vm.writer[120]}, 920 Owner: {ctrl_cont.vm.writer[920]}")
    
    # 21 moves to try to service both every tick
    assert mc_moves >= 20, f"Expected sustained traversal tax >= 20, got {mc_moves}"

    # 4. Monolithic (Batched Final-Ownership)
    print("\n--- Running Monolithic (Batched Final) ---")
    mono_batch = build_mono_batched()
    ctrl_batch = ProcessMatchController(config, [mono_batch, build_passive()], max_ticks=10, model=ProcessModel.MODEL_C_MOVABLE_ANCHOR)
    ctrl_batch.run()
    
    mb_p = mono_batch.processes[0]
    mb_moves = mb_p.telemetry.total_moves
    mb_writes = mb_p.telemetry.total_writes
    print(f"MonoBatch - Writes: {mb_writes}, Moves: {mb_moves}")
    print(f"120 Owner: {ctrl_batch.vm.writer[120]}, 920 Owner: {ctrl_batch.vm.writer[920]}")
    assert mb_moves <= 3, f"Expected cheap batched deployment, got {mb_moves}"
    assert ctrl_batch.vm.writer[120] == "MonoBatched"
    assert ctrl_batch.vm.writer[920] == "MonoBatched"

    print("\nAssertions passed.")


