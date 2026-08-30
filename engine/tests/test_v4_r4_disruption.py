"""Corrected R4 disruption economics under the normative v4 scheduler."""

from __future__ import annotations

from typing import Any

from battle_engine.agent_api import ActionKind, AgentAction
from battle_engine.config import Config, Weights
from battle_engine.process_runtime import (
    DisruptedQuotaPolicy,
    ProcessEntrantSpec,
    ProcessInstance,
    ProcessMatchController,
    ProcessModel,
    ProcessObservation,
    ProcessRole,
)

CONFIG = Config(arena_size=1024, instr_per_tick=8, seed=1, weights=Weights())
R4B_DURATION = 1


def _service_writer(address: int, value: int):
    def logic(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
        by_tick = state.setdefault("callbacks_by_tick", {})
        by_tick[obs.tick] = by_tick.get(obs.tick, 0) + 1
        state["service_actions"] = state.get("service_actions", 0) + 1
        return AgentAction(ActionKind.WRITE, operand=address, value=value)

    return logic


def _distributed_entrant() -> ProcessEntrantSpec:
    return ProcessEntrantSpec(
        "victim",
        "distributed",
        [
            ProcessInstance(
                "base",
                ProcessRole.DEFENDER,
                initial_position=100,
                reach=50,
                quota_share=4,
                logic=_service_writer(120, 0x11),
            ),
            ProcessInstance(
                "scout",
                ProcessRole.SCOUT,
                initial_position=900,
                reach=50,
                quota_share=4,
                logic=_service_writer(920, 0x22),
            ),
        ],
    )


def _monolithic_entrant() -> ProcessEntrantSpec:
    return ProcessEntrantSpec(
        "victim",
        "monolith",
        [
            ProcessInstance(
                "mono",
                ProcessRole.GENERALIST,
                initial_position=100,
                reach=50,
                quota_share=8,
                logic=_service_writer(120, 0x33),
            )
        ],
    )


def _optimized_attacker(target_anchor: int, hit_ticks: set[int]) -> ProcessEntrantSpec:
    def logic(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
        if obs.tick in hit_ticks and state.get("last_hit_tick") != obs.tick:
            state["last_hit_tick"] = obs.tick
            state["disruption_writes"] = state.get("disruption_writes", 0) + 1
            return AgentAction(ActionKind.WRITE, operand=target_anchor, value=0xFF)
        state["other_actions"] = state.get("other_actions", 0) + 1
        return AgentAction(ActionKind.WRITE, operand=(target_anchor + 30) % 1024, value=0xEE)

    return ProcessEntrantSpec(
        "attacker",
        "optimized_attacker",
        [
            ProcessInstance(
                "attacker",
                ProcessRole.ATTACKER,
                initial_position=target_anchor,
                reach=50,
                quota_share=8,
                logic=logic,
            )
        ],
    )


def _run(
    victim: ProcessEntrantSpec,
    attacker: ProcessEntrantSpec,
    *,
    duration: int,
    ticks: int = 10,
) -> ProcessMatchController:
    controller = ProcessMatchController(
        CONFIG,
        [victim, attacker],
        max_ticks=ticks,
        model=ProcessModel.MODEL_C_MOVABLE_ANCHOR,
        disruption_duration=duration,
        disrupted_quota_policy=DisruptedQuotaPolicy.FAIR_REDISTRIBUTION,
    )
    controller.run()
    return controller


def test_d1_optimized_suppression_denies_remote_service_without_losing_victim_quota() -> None:
    control = _distributed_entrant()
    control_attacker = _optimized_attacker(900, set(range(1, 11)))
    _run(control, control_attacker, duration=0)

    victim = _distributed_entrant()
    attacker = _optimized_attacker(900, set(range(1, 11)))
    _run(victim, attacker, duration=R4B_DURATION)

    base, scout = victim.processes
    attacker_process = attacker.processes[0]
    callbacks_denied = control.processes[1].telemetry.total_actions - scout.telemetry.total_actions
    disruption_writes = attacker_process.local_state["disruption_writes"]

    assert [base.telemetry.total_actions, scout.telemetry.total_actions] == [80, 0]
    assert base.telemetry.total_actions + scout.telemetry.total_actions == 80
    assert scout.local_state.get("service_actions", 0) == 0
    assert scout.telemetry.disrupted_match_ticks == set(range(1, 11))
    assert scout.telemetry.disruption_hits_received == 10
    assert callbacks_denied == 40
    assert disruption_writes == 10
    assert callbacks_denied / disruption_writes == 4
    assert attacker_process.local_state["other_actions"] == 70
    assert disruption_writes / attacker_process.telemetry.total_actions == 0.125


def test_d1_monolith_is_severely_but_not_totally_suppressed_under_rotation() -> None:
    control = _monolithic_entrant()
    control_attacker = _optimized_attacker(100, set(range(1, 11)))
    _run(control, control_attacker, duration=0)

    victim = _monolithic_entrant()
    attacker = _optimized_attacker(100, set(range(1, 11)))
    _run(victim, attacker, duration=R4B_DURATION)

    process = victim.processes[0]
    attacker_process = attacker.processes[0]
    callbacks_denied = control.processes[0].telemetry.total_actions - process.telemetry.total_actions
    disruption_writes = attacker_process.local_state["disruption_writes"]

    assert process.local_state["callbacks_by_tick"] == {1: 2, 3: 2, 5: 2, 7: 2, 9: 2}
    assert process.telemetry.total_actions == 10
    assert callbacks_denied == 70
    assert disruption_writes == 10
    assert callbacks_denied / disruption_writes == 7
    assert process.telemetry.disrupted_match_ticks == set(range(1, 11))
