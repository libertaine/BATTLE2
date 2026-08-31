"""Research Agent Factories for Bytefray v4 Process Semantics Investigation.

Provides specialized single-process and multi-process entrant architectures
for evaluating Model A (Cursors), Model B (Static Loci), Model C (Movable Anchors),
and Stage 4 Disruption.
"""

from __future__ import annotations

from typing import Any

from battle_engine.agent_api import ActionKindV2, AgentAction, ObservationV2
from battle_engine.process_runtime import (
    ProcessEntrantSpec,
    ProcessInstance,
    ProcessRole,
)


def _defender_logic(obs: ObservationV2, state: dict[str, Any]) -> AgentAction:
    """Core Defender: checks own 8-cell core sequentially and repairs any corrupted cells."""
    idx = state.get("idx", 0)
    phase = state.get("phase", "READ")
    core_addr = (obs.own_core_base + idx) % obs.arena_size  # type: ignore

    if phase == "READ":
        state["phase"] = "EVAL"
        state["check_addr"] = core_addr
        return AgentAction(ActionKindV2.READ, core_addr)
    else:
        state["phase"] = "READ"
        state["idx"] = (idx + 1) % obs.own_core_size
        # If core cell was corrupted or not owned by us, repair it
        if obs.previous_read_owner != obs.agent_id or obs.previous_read_value != 0xCE:  # type: ignore
            return AgentAction(ActionKindV2.WRITE, state["check_addr"], 0xCE)
        return AgentAction(ActionKindV2.READ)


def _hunter_logic(obs: ObservationV2, state: dict[str, Any]) -> AgentAction:
    """Hunter / Attacker: scans for enemy territory/cores and writes offensive payloads."""
    scan_offset = state.get("scan_offset", 100)
    phase = state.get("phase", "READ")
    target_addr = (obs.own_core_base + scan_offset) % obs.arena_size  # type: ignore

    if phase == "READ":
        state["phase"] = "EVAL"
        state["target_addr"] = target_addr
        return AgentAction(ActionKindV2.READ, target_addr)
    else:
        state["phase"] = "READ"
        state["scan_offset"] = (scan_offset + 32) % obs.arena_size  # type: ignore
        if obs.previous_read_owner is not None and obs.previous_read_owner != obs.agent_id:  # type: ignore
            # Found enemy! Overwrite
            return AgentAction(ActionKindV2.WRITE, state["target_addr"], 0xAA)
        return AgentAction(ActionKindV2.READ)


def _scout_logic(obs: ObservationV2, state: dict[str, Any]) -> AgentAction:
    """Scout: scans broadly for non-own activity and shares targets with team."""
    scan_offset = state.get("scan_offset", 64)
    target_addr = (obs.own_core_base + scan_offset) % obs.arena_size  # type: ignore
    state["scan_offset"] = (scan_offset + 128) % obs.arena_size  # type: ignore

    # Check previous read
    if obs.previous_read_owner is not None and obs.previous_read_owner != obs.agent_id:  # type: ignore
        obs.shared_memory["enemy_target"] = obs.last_action_operand  # type: ignore

    return AgentAction(ActionKindV2.READ, target_addr)


def _coordinated_attacker_logic(obs: ObservationV2, state: dict[str, Any]) -> AgentAction:
    """Coordinated Attacker: reads targets posted to shared_memory by Scouts and strikes."""
    target = obs.shared_memory.get("enemy_target")  # type: ignore
    strike_idx = state.get("strike_idx", 0)

    if target is not None:
        strike_addr = (target + strike_idx) % obs.arena_size  # type: ignore
        state["strike_idx"] = (strike_idx + 1) % 8
        return AgentAction(ActionKindV2.WRITE, strike_addr, 0xEE)
    else:
        # Fallback local sweep
        sweep_offset = state.get("sweep_offset", 200)
        state["sweep_offset"] = (sweep_offset + 16) % obs.arena_size  # type: ignore
        return AgentAction(ActionKindV2.WRITE, (obs.own_core_base + sweep_offset) % obs.arena_size, 0xBB)  # type: ignore


def _claimer_logic(obs: ObservationV2, state: dict[str, Any]) -> AgentAction:
    """Fast Expander: claims contiguous arena territory."""
    offset = state.get("offset", 8)
    write_addr = (obs.own_core_base + offset) % obs.arena_size  # type: ignore
    state["offset"] = (offset + 1) % obs.arena_size  # type: ignore
    return AgentAction(ActionKindV2.WRITE, write_addr, 0xC1)


def _sweeper_left_logic(obs: ObservationV2, state: dict[str, Any]) -> AgentAction:
    """Sweeper Left: claims territory in counter-clockwise direction."""
    offset = state.get("offset", 1)
    write_addr = (obs.own_core_base - offset) % obs.arena_size  # type: ignore
    state["offset"] = offset + 1
    return AgentAction(ActionKindV2.WRITE, write_addr, 0x55)


def _sweeper_right_logic(obs: ObservationV2, state: dict[str, Any]) -> AgentAction:
    """Sweeper Right: claims territory in clockwise direction."""
    offset = state.get("offset", 8)
    write_addr = (obs.own_core_base + offset) % obs.arena_size  # type: ignore
    state["offset"] = offset + 1
    return AgentAction(ActionKindV2.WRITE, write_addr, 0x77)


def _movable_scout_logic(obs: ObservationV2, state: dict[str, Any]) -> AgentAction:
    """Model C Movable Scout: alternates moving outward and scanning local radius."""
    step_count = state.get("step_count", 0)
    state["step_count"] = step_count + 1

    if step_count % 3 == 0:
        # Move forward by step
        return AgentAction(ActionKindV2.MOVE, 32)
    else:
        # Local read
        scan_idx = state.get("scan_idx", 0)
        state["scan_idx"] = (scan_idx + 1) % 16
        pos = obs.self_anchor if obs.self_anchor is not None else obs.own_core_base
        target = (pos + scan_idx * 4) % obs.arena_size  # type: ignore
        return AgentAction(ActionKindV2.READ, target)


def _movable_hunter_logic(obs: ObservationV2, state: dict[str, Any]) -> AgentAction:
    """Model C Movable Hunter: moves toward detected enemies and strikes locally."""
    step = state.get("step", 0)
    state["step"] = step + 1
    pos = obs.self_anchor if obs.self_anchor is not None else obs.own_core_base

    if step % 2 == 0:
        return AgentAction(ActionKindV2.MOVE, 32)
    else:
        return AgentAction(ActionKindV2.WRITE, pos, 0xEE)


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


def _monolithic_triple_logic(obs: ObservationV2, state: dict[str, Any]) -> AgentAction:
    """Monolithic control simulating TripleProcess via time-slicing and mailboxes."""
    # Initialize on first call
    if "init" not in state:
        state["init"] = True
        state["ta"] = 0  # tick action counter
        state["prev"] = None  # previous role key
        state["ct"] = obs.current_tick  # current tick
        for r in ("def", "scout", "atk"):
            state[f"s_{r}"] = {}  # role-local state
            state[f"mb_{r}"] = {}  # mailbox

    # Route feedback from previous action to previous role's mailbox
    prev = state["prev"]
    if prev is not None:
        state[f"mb_{prev}"] = {
            "action_kind": obs.last_action_kind,  # type: ignore
            "operand": obs.last_action_operand,  # type: ignore
            "value": obs.last_action_value,  # type: ignore
            "read_val": obs.previous_read_value,
            "read_owner": obs.previous_read_owner,
        }

    # Detect tick boundary, reset action counter
    if obs.current_tick != state["ct"]:
        state["ta"] = 0
        state["ct"] = obs.current_tick

    ta = state["ta"]
    state["ta"] = ta + 1

    # Map the action to the corresponding role (4 Def, 2 Scout, 2 Atk)
    if ta < 4:
        role = "def"
        logic_func = _defender_logic
    elif ta < 6:
        role = "scout"
        logic_func = _scout_logic
    else:
        role = "atk"
        logic_func = _coordinated_attacker_logic

    # Build role observation from its own mailbox
    mb = state[f"mb_{role}"]
    role_obs = ObservationV2(  # type: ignore
        tick=obs.current_tick, agent_id=obs.agent_id, process_id=obs.self_process_id,  # type: ignore
        role=obs.role, position=obs.self_anchor, reach=obs.reach,  # type: ignore
        core_base=obs.own_core_base, core_size=obs.own_core_size,
        arena_size=obs.arena_size,  # type: ignore
        last_action_kind=mb.get("action_kind"),
        last_action_operand=mb.get("operand"),
        last_action_value=mb.get("value"),
        read_result=mb.get("read_val"),
        read_owner=mb.get("read_owner"),
        shared_memory=obs.shared_memory,  # type: ignore
    )

    state["prev"] = role
    return logic_func(role_obs, state[f"s_{role}"])

def make_monolithic_triple_sim(
    agent_id: str,
    reach: int | None = None,
) -> ProcessEntrantSpec:
    """1 Process accurately replicating 3-Process Def/Scout/Atk via time-slicing and mailboxes."""
    p = ProcessInstance(
        process_id="proc_monolithic",
        role=ProcessRole.GENERALIST,
        initial_position=None,
        reach=reach,
        quota_share=8,
        logic=_monolithic_triple_logic,
    )
    return ProcessEntrantSpec(agent_id=agent_id, name="monolithic_triple_sim", processes=[p])
