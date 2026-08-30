"""Bytefray v4 Research R4 Process Disruption Challenge."""
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


def build_distributed_entrant(name: str = "Multi") -> ProcessEntrantSpec:
    """Two processes: Base Defender (at 100) and Remote Scout (at 900)."""
    def def_logic(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
        state["runs"] = state.get("runs", 0) + 1
        return AgentAction(ActionKind.WRITE, operand=120, value=0x11)
        
    def scout_logic(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
        state["runs"] = state.get("runs", 0) + 1
        return AgentAction(ActionKind.WRITE, operand=920, value=0x22)
        
    return ProcessEntrantSpec(name, "multi_proc", [
        ProcessInstance("base", ProcessRole.DEFENDER, initial_position=100, reach=50, quota_share=4, logic=def_logic),
        ProcessInstance("scout", ProcessRole.SCOUT, initial_position=900, reach=50, quota_share=4, logic=scout_logic),
    ])


def build_mono_entrant(name: str = "Mono") -> ProcessEntrantSpec:
    """One concentrated process: Base Defender (at 100) with Q=8."""
    def mono_logic(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
        state["runs"] = state.get("runs", 0) + 1
        return AgentAction(ActionKind.WRITE, operand=120, value=0x33)
        
    return ProcessEntrantSpec(name, "mono_proc", [
        ProcessInstance("mono", ProcessRole.DEFENDER, initial_position=100, reach=50, quota_share=8, logic=mono_logic),
    ])


def build_attacker(target_anchor: int, delay_ticks: int = 0) -> ProcessEntrantSpec:
    """Attacker that writes exactly to the opponent's anchor to disrupt them."""
    def atk_logic(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
        if obs.tick <= delay_ticks:
            return AgentAction(ActionKind.NOP)
        # Spam disruption at target anchor
        return AgentAction(ActionKind.WRITE, operand=target_anchor, value=0xFF)
        
    return ProcessEntrantSpec("Attacker", "atk", [
        ProcessInstance("atk_proc", ProcessRole.ATTACKER, initial_position=target_anchor, reach=50, quota_share=8, logic=atk_logic),
    ])


def test_r4_disruption_tradeoff() -> None:
    config = Config(arena_size=1024, instr_per_tick=8, seed=1, weights=Weights())
    
    # 1. Multi vs Attacker (Attacker targets the Scout at 900 starting tick 2)
    # The scout gets disrupted every tick after tick 1.
    multi = build_distributed_entrant()
    atk_multi = build_attacker(target_anchor=900, delay_ticks=1)
    
    ctrl_multi = ProcessMatchController(
        config, 
        [multi, atk_multi], 
        max_ticks=5, 
        model=ProcessModel.MODEL_C_MOVABLE_ANCHOR,
        disruption_duration=1,  # Disrupted through end of current/next tick
    )
    ctrl_multi.run()
    
    base_runs = multi.processes[0].telemetry.total_actions
    scout_runs = multi.processes[1].telemetry.total_actions
    total_multi_runs = base_runs + scout_runs
    scout_disrupted = multi.processes[1].telemetry.total_disrupted_ticks
    
    print("\n--- Distributed vs Attacker ---")
    print(f"Total Actions: {total_multi_runs} (Base: {base_runs}, Scout: {scout_runs})")
    print(f"Scout Disrupted Ticks: {scout_disrupted}")
    
    # Assert quota reallocation: The total actions should still be 40 (5 ticks * 8)
    # Even though the scout was disrupted from tick 2 onwards.
    assert total_multi_runs == 40
    # Scout should only have acted in tick 1 (4 actions)
    # Wait, the attacker writes on tick 2. Disruption applies to tick 2 (if written early enough) or tick 3.
    assert scout_runs < 20
    assert base_runs > 20
    
    # 2. Mono vs Attacker (Attacker targets the Mono at 100 starting tick 2)
    mono = build_mono_entrant()
    atk_mono = build_attacker(target_anchor=100, delay_ticks=1)
    
    ctrl_mono = ProcessMatchController(
        config, 
        [mono, atk_mono], 
        max_ticks=5, 
        model=ProcessModel.MODEL_C_MOVABLE_ANCHOR,
        disruption_duration=1,
    )
    ctrl_mono.run()
    
    mono_runs = mono.processes[0].telemetry.total_actions
    mono_disrupted = mono.processes[0].telemetry.total_disrupted_ticks
    
    print("\n--- Monolithic vs Attacker ---")
    print(f"Total Actions: {mono_runs}")
    print(f"Mono Disrupted Ticks: {mono_disrupted}")
    
    # Mono has no backup process. When disrupted, its quota is lost completely!
    assert mono_runs < 40


if __name__ == "__main__":
    test_r4_disruption_tradeoff()
