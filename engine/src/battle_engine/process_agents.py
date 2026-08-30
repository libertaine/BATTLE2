"""Research Agent Factories for Bytefray v4 Process Semantics Investigation.

Provides specialized single-process and multi-process entrant architectures
for evaluating Model A (Cursors), Model B (Static Loci), Model C (Movable Anchors),
and Stage 4 Disruption.
"""

from __future__ import annotations

from typing import Any

from battle_engine.agent_api import ActionKind, AgentAction
from battle_engine.process_runtime import (
    ProcessEntrantSpec,
    ProcessInstance,
    ProcessObservation,
    ProcessRole,
)


def _defender_logic(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
    """Core Defender: checks own 8-cell core sequentially and repairs any corrupted cells."""
    idx = state.get("idx", 0)
    phase = state.get("phase", "READ")
    core_addr = (obs.core_base + idx) % obs.arena_size

    if phase == "READ":
        state["phase"] = "EVAL"
        state["check_addr"] = core_addr
        return AgentAction(ActionKind.READ, core_addr)
    else:
        state["phase"] = "READ"
        state["idx"] = (idx + 1) % obs.core_size
        # If core cell was corrupted or not owned by us, repair it
        if obs.read_owner != obs.agent_id or obs.read_result != 0xCE:
            return AgentAction(ActionKind.WRITE, state["check_addr"], 0xCE)
        return AgentAction(ActionKind.NOP)


def _hunter_logic(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
    """Hunter / Attacker: scans for enemy territory/cores and writes offensive payloads."""
    scan_offset = state.get("scan_offset", 100)
    phase = state.get("phase", "READ")
    target_addr = (obs.core_base + scan_offset) % obs.arena_size

    if phase == "READ":
        state["phase"] = "EVAL"
        state["target_addr"] = target_addr
        return AgentAction(ActionKind.READ, target_addr)
    else:
        state["phase"] = "READ"
        state["scan_offset"] = (scan_offset + 32) % obs.arena_size
        if obs.read_owner is not None and obs.read_owner != obs.agent_id:
            # Found enemy! Overwrite
            return AgentAction(ActionKind.WRITE, state["target_addr"], 0xAA)
        return AgentAction(ActionKind.NOP)


def _scout_logic(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
    """Scout: scans broadly for non-own activity and shares targets with team."""
    scan_offset = state.get("scan_offset", 64)
    target_addr = (obs.core_base + scan_offset) % obs.arena_size
    state["scan_offset"] = (scan_offset + 128) % obs.arena_size

    # Check previous read
    if obs.read_owner is not None and obs.read_owner != obs.agent_id:
        obs.shared_memory["enemy_target"] = obs.last_action_operand

    return AgentAction(ActionKind.READ, target_addr)


def _coordinated_attacker_logic(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
    """Coordinated Attacker: reads targets posted to shared_memory by Scouts and strikes."""
    target = obs.shared_memory.get("enemy_target")
    strike_idx = state.get("strike_idx", 0)

    if target is not None:
        strike_addr = (target + strike_idx) % obs.arena_size
        state["strike_idx"] = (strike_idx + 1) % 8
        return AgentAction(ActionKind.WRITE, strike_addr, 0xEE)
    else:
        # Fallback local sweep
        sweep_offset = state.get("sweep_offset", 200)
        state["sweep_offset"] = (sweep_offset + 16) % obs.arena_size
        return AgentAction(ActionKind.WRITE, (obs.core_base + sweep_offset) % obs.arena_size, 0xBB)


def _claimer_logic(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
    """Fast Expander: claims contiguous arena territory."""
    offset = state.get("offset", 8)
    write_addr = (obs.core_base + offset) % obs.arena_size
    state["offset"] = (offset + 1) % obs.arena_size
    return AgentAction(ActionKind.WRITE, write_addr, 0xC1)


def _sweeper_left_logic(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
    """Sweeper Left: claims territory in counter-clockwise direction."""
    offset = state.get("offset", 1)
    write_addr = (obs.core_base - offset) % obs.arena_size
    state["offset"] = offset + 1
    return AgentAction(ActionKind.WRITE, write_addr, 0x55)


def _sweeper_right_logic(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
    """Sweeper Right: claims territory in clockwise direction."""
    offset = state.get("offset", 8)
    write_addr = (obs.core_base + offset) % obs.arena_size
    state["offset"] = offset + 1
    return AgentAction(ActionKind.WRITE, write_addr, 0x77)


def _movable_scout_logic(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
    """Model C Movable Scout: alternates moving outward and scanning local radius."""
    step_count = state.get("step_count", 0)
    state["step_count"] = step_count + 1

    if step_count % 3 == 0:
        # Move forward by step
        return AgentAction(ActionKind.MOVE, 32)
    else:
        # Local read
        scan_idx = state.get("scan_idx", 0)
        state["scan_idx"] = (scan_idx + 1) % 16
        pos = obs.position if obs.position is not None else obs.core_base
        target = (pos + scan_idx * 4) % obs.arena_size
        return AgentAction(ActionKind.READ, target)


def _movable_hunter_logic(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
    """Model C Movable Hunter: moves toward detected enemies and strikes locally."""
    step = state.get("step", 0)
    state["step"] = step + 1
    pos = obs.position if obs.position is not None else obs.core_base

    if step % 2 == 0:
        return AgentAction(ActionKind.MOVE, 32)
    else:
        return AgentAction(ActionKind.WRITE, pos, 0xEE)


# ---------------------------------------------------------------------------
# Entrant Composition Factories
# ---------------------------------------------------------------------------


def make_single_process_claimer(agent_id: str, reach: int | None = None) -> ProcessEntrantSpec:
    """1 Process: Claimer (8 actions/tick)."""
    p = ProcessInstance(
        process_id="proc_0",
        role=ProcessRole.EXPANDER,
        initial_position=None,
        reach=reach,
        quota_share=8,
        logic=_claimer_logic,
    )
    return ProcessEntrantSpec(agent_id=agent_id, name="single_claimer", processes=[p])


def make_single_process_defender(agent_id: str, reach: int | None = None) -> ProcessEntrantSpec:
    """1 Process: Pure Defender (8 actions/tick)."""
    p = ProcessInstance(
        process_id="proc_0",
        role=ProcessRole.DEFENDER,
        initial_position=None,
        reach=reach,
        quota_share=8,
        logic=_defender_logic,
    )
    return ProcessEntrantSpec(agent_id=agent_id, name="single_defender", processes=[p])


def make_single_process_hunter(agent_id: str, reach: int | None = None) -> ProcessEntrantSpec:
    """1 Process: Pure Hunter (8 actions/tick)."""
    p = ProcessInstance(
        process_id="proc_0",
        role=ProcessRole.HUNTER,
        initial_position=None,
        reach=reach,
        quota_share=8,
        logic=_hunter_logic,
    )
    return ProcessEntrantSpec(agent_id=agent_id, name="single_hunter", processes=[p])


def make_dual_process_defender_hunter(
    agent_id: str,
    alloc: tuple[int, int] = (4, 4),
    reach: int | None = None,
    p0_pos: int | None = None,
    p1_pos: int | None = None,
) -> ProcessEntrantSpec:
    """2 Processes: Defender (alloc[0]) + Hunter (alloc[1])."""
    p0 = ProcessInstance(
        process_id="proc_def",
        role=ProcessRole.DEFENDER,
        initial_position=p0_pos,
        reach=reach,
        quota_share=alloc[0],
        logic=_defender_logic,
    )
    p1 = ProcessInstance(
        process_id="proc_hunt",
        role=ProcessRole.HUNTER,
        initial_position=p1_pos,
        reach=reach,
        quota_share=alloc[1],
        logic=_hunter_logic,
    )
    return ProcessEntrantSpec(agent_id=agent_id, name=f"dual_def_hunt_{alloc[0]}_{alloc[1]}", processes=[p0, p1])


def make_dual_process_dual_sweeper(
    agent_id: str,
    alloc: tuple[int, int] = (4, 4),
    reach: int | None = None,
    p0_pos: int | None = None,
    p1_pos: int | None = None,
) -> ProcessEntrantSpec:
    """2 Processes: Expander Left (alloc[0]) + Expander Right (alloc[1])."""
    p0 = ProcessInstance(
        process_id="proc_left",
        role=ProcessRole.EXPANDER,
        initial_position=p0_pos,
        reach=reach,
        quota_share=alloc[0],
        logic=_sweeper_left_logic,
    )
    p1 = ProcessInstance(
        process_id="proc_right",
        role=ProcessRole.EXPANDER,
        initial_position=p1_pos,
        reach=reach,
        quota_share=alloc[1],
        logic=_sweeper_right_logic,
    )
    return ProcessEntrantSpec(agent_id=agent_id, name="dual_sweeper", processes=[p0, p1])


def make_triple_process_def_scout_atk(
    agent_id: str,
    alloc: tuple[int, int, int] = (4, 2, 2),
    reach: int | None = None,
    p0_pos: int | None = None,
    p1_pos: int | None = None,
    p2_pos: int | None = None,
) -> ProcessEntrantSpec:
    """3 Processes: Defender + Scout + Coordinated Attacker."""
    p0 = ProcessInstance(
        process_id="proc_def",
        role=ProcessRole.DEFENDER,
        initial_position=p0_pos,
        reach=reach,
        quota_share=alloc[0],
        logic=_defender_logic,
    )
    p1 = ProcessInstance(
        process_id="proc_scout",
        role=ProcessRole.SCOUT,
        initial_position=p1_pos,
        reach=reach,
        quota_share=alloc[1],
        logic=_scout_logic,
    )
    p2 = ProcessInstance(
        process_id="proc_atk",
        role=ProcessRole.ATTACKER,
        initial_position=p2_pos,
        reach=reach,
        quota_share=alloc[2],
        logic=_coordinated_attacker_logic,
    )
    return ProcessEntrantSpec(agent_id=agent_id, name=f"triple_def_scout_atk_{alloc[0]}_{alloc[1]}_{alloc[2]}", processes=[p0, p1, p2])


def make_quad_process_quad_sweeper(
    agent_id: str,
    alloc: tuple[int, int, int, int] = (2, 2, 2, 2),
    reach: int | None = None,
) -> ProcessEntrantSpec:
    """4 Processes: 4 concurrent sweepers (equal 2/2/2/2 allocation)."""
    procs = []
    for i in range(4):
        p = ProcessInstance(
            process_id=f"proc_sweep_{i}",
            role=ProcessRole.EXPANDER,
            initial_position=None,
            reach=reach,
            quota_share=alloc[i],
            logic=_claimer_logic,
        )
        procs.append(p)
    return ProcessEntrantSpec(agent_id=agent_id, name="quad_sweeper", processes=procs)


def make_movable_dual_scout_hunter(
    agent_id: str,
    alloc: tuple[int, int] = (4, 4),
    reach: int = 256,
    p0_pos: int | None = None,
    p1_pos: int | None = None,
) -> ProcessEntrantSpec:
    """Model C Movable 2-Process Entrant."""
    p0 = ProcessInstance(
        process_id="proc_mov_scout",
        role=ProcessRole.SCOUT,
        initial_position=p0_pos,
        reach=reach,
        quota_share=alloc[0],
        logic=_movable_scout_logic,
    )
    p1 = ProcessInstance(
        process_id="proc_mov_hunt",
        role=ProcessRole.HUNTER,
        initial_position=p1_pos,
        reach=reach,
        quota_share=alloc[1],
        logic=_movable_hunter_logic,
    )
    return ProcessEntrantSpec(agent_id=agent_id, name="movable_dual_scout_hunt", processes=[p0, p1])


def _monolithic_triple_logic(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
    """Monolithic control trying to simulate TripleProcess (4 Def, 2 Scout, 2 Atk)."""
    # Track which action we are on within the tick (0 to 7)
    tick_action = state.get("tick_action", 0)
    state["tick_action"] = (tick_action + 1) % 8

    # Ensure sub-states exist
    if "def_state" not in state:
        state["def_state"] = {}
    if "scout_state" not in state:
        state["scout_state"] = {}
    if "atk_state" not in state:
        state["atk_state"] = {}

    # Map the action to the corresponding role (4 Def, 2 Scout, 2 Atk)
    # The chunked scheduler K=2 executes:
    # 0, 1 -> Def
    # 2, 3 -> Def
    # 4, 5 -> Scout
    # 6, 7 -> Atk
    if tick_action < 4:
        return _defender_logic(obs, state["def_state"])
    elif tick_action < 6:
        return _scout_logic(obs, state["scout_state"])
    else:
        return _coordinated_attacker_logic(obs, state["atk_state"])


def make_monolithic_triple_sim(
    agent_id: str,
    reach: int | None = None,
) -> ProcessEntrantSpec:
    """1 Process attempting to replicate 3-Process Def/Scout/Atk via time-slicing."""
    p = ProcessInstance(
        process_id="proc_monolithic",
        role=ProcessRole.GENERALIST,
        initial_position=None,
        reach=reach,
        quota_share=8,
        logic=_monolithic_triple_logic,
    )
    return ProcessEntrantSpec(agent_id=agent_id, name="monolithic_triple_sim", processes=[p])
