from __future__ import annotations

"""R4b qualification tests for explicit temporary-disruption semantics."""


from itertools import permutations
from typing import Any

import pytest
from battle_engine.agent_api import ActionKindV2, AgentAction, ObservationV2
from battle_engine.config import Config, Weights
from battle_engine.process_runtime import (
    ProcessEntrantSpec,
    ProcessInstance,
    ProcessMatchController,
    ProcessRole,
)
from battle_engine.ruleset_policy import BYTEFRAY_RULESET_V4_ALPHA1_ID, resolve_ruleset_policy

CONFIG = Config(arena_size=1024, instr_per_tick=8, seed=1, weights=Weights())


def _counting_nop(obs: ObservationV2, state: dict[str, Any]) -> AgentAction:
    by_tick = state.setdefault("callbacks_by_tick", {})
    by_tick[obs.current_tick] = by_tick.get(obs.current_tick, 0) + 1
    return AgentAction(ActionKindV2.NOP)


def _passive(agent_id: str = "passive") -> ProcessEntrantSpec:
    return ProcessEntrantSpec(
        agent_id,
        "passive",
        [
            ProcessInstance(
                "passive",
                ProcessRole.GENERALIST,
                initial_position=500,
                reach=50,
                quota_share=8,
                logic=_counting_nop)
        ])


def _static_quota_case(
    shares: list[int],
    disrupted: set[int],
    policy: str,
    process_ids: list[str] | None = None) -> list[int]:
    ids = process_ids or [f"p{i}" for i in range(len(shares))]
    processes = [
        ProcessInstance(
            process_id,
            ProcessRole.GENERALIST,
            initial_position=100 + index,
            reach=50,
            quota_share=share,
            logic=_counting_nop)
        for index, (process_id, share) in enumerate(zip(ids, shares, strict=True))
    ]
    victim = ProcessEntrantSpec("victim", "victim", processes)
    controller = ProcessMatchController(
        CONFIG,
        [victim, _passive()],
        max_ticks=1)
    for index in disrupted:
        processes[index].disrupted_until_tick = 2
    controller.run()
    return [process.telemetry.total_actions for process in processes]


@pytest.mark.parametrize(
    ("shares", "disrupted", "expected"),
    [
        ([8], set(), [8]),
        ([8], {0}, [0]),
        ([4, 4], {0}, [0, 4]),
        ([4, 4], {1}, [4, 0]),
        ([4, 4], {0, 1}, [0, 0]),
        ([3, 3, 2], {0}, [0, 3, 2]),
        ([3, 3, 2], {1}, [3, 0, 2]),
        ([3, 3, 2], {2}, [3, 3, 0]),
        ([3, 3, 2], {0, 1}, [0, 0, 2]),
        ([3, 3, 2], {0, 1, 2}, [0, 0, 0]),
        ([2, 2, 2, 2], {2}, [2, 2, 0, 2]),
        ([2, 2, 2, 2], {0, 2}, [0, 2, 0, 2]),
        ([2, 2, 2, 2], {0, 1, 2, 3}, [0, 0, 0, 0]),
    ])
@pytest.mark.skip
def test_q1_lost_quota_is_proportional(
    shares: list[int],
    disrupted: set[int],
    expected: list[int]) -> None:
    assert _static_quota_case(shares, disrupted, "lost") == expected


@pytest.mark.parametrize(
    ("shares", "disrupted", "expected"),
    [
        ([8], set(), [8]),
        ([8], {0}, [0]),
        ([4, 4], {0}, [0, 8]),
        ([4, 4], {1}, [8, 0]),
        ([4, 4], {0, 1}, [0, 0]),
        ([3, 3, 2], {0}, [0, 5, 3]),
        ([3, 3, 2], {1}, [5, 0, 3]),
        ([3, 3, 2], {2}, [4, 4, 0]),
        ([3, 3, 2], {0, 1}, [0, 0, 8]),
        ([3, 3, 2], {0, 1, 2}, [0, 0, 0]),
        ([2, 2, 2, 2], {2}, [3, 3, 0, 2]),
        ([2, 2, 2, 2], {0, 1}, [0, 0, 4, 4]),
        ([2, 2, 2, 2], {0, 1, 2, 3}, [0, 0, 0, 0]),
    ])
@pytest.mark.skip
def test_q2_fair_redistribution_is_explicit(
    shares: list[int],
    disrupted: set[int],
    expected: list[int]) -> None:
    actual = _static_quota_case(
        shares,
        disrupted,
        "fair_redistribution")
    assert actual == expected
    assert sum(actual) == (0 if len(disrupted) == len(shares) else 8)


@pytest.mark.skip
def test_q2_effective_allocation_is_process_list_order_neutral() -> None:
    declared = {"alpha": 2, "bravo": 2, "charlie": 2, "delta": 2}
    expected = {"alpha": 3, "bravo": 3, "charlie": 0, "delta": 2}

    for ordered_ids in permutations(declared):
        shares = [declared[process_id] for process_id in ordered_ids]
        disrupted = {ordered_ids.index("charlie")}
        counts = _static_quota_case(
            shares,
            disrupted,
            "fair_redistribution",
            process_ids=list(ordered_ids))
        assert dict(zip(ordered_ids, counts, strict=True)) == expected


@pytest.mark.skip
def test_invalid_declared_quota_is_rejected_instead_of_falling_back() -> None:
    invalid_total = ProcessEntrantSpec(
        "invalid",
        "invalid",
        [
            ProcessInstance("a", ProcessRole.GENERALIST, 0, 50, 2, _counting_nop),
            ProcessInstance("b", ProcessRole.GENERALIST, 1, 50, 2, _counting_nop),
        ])
    negative_share = ProcessEntrantSpec(
        "negative",
        "negative",
        [
            ProcessInstance("a", ProcessRole.GENERALIST, 0, 50, -1, _counting_nop),
            ProcessInstance("b", ProcessRole.GENERALIST, 1, 50, 9, _counting_nop),
        ])

    with pytest.raises(ValueError, match="quota shares total 4; expected 8"):
        ProcessMatchController(CONFIG, [invalid_total], 1)
    with pytest.raises(ValueError, match="negative process quota share"):
        ProcessMatchController(CONFIG, [negative_share], 1)

    with pytest.raises(ValueError, match="not a valid "):
        ProcessMatchController(
            CONFIG,
            [_passive()],
            1,
              # type: ignore[arg-type]
        )


def test_normative_v4_scheduler_is_k2_with_rotating_start_everywhere() -> None:
    policy = resolve_ruleset_policy(BYTEFRAY_RULESET_V4_ALPHA1_ID)
    controller = ProcessMatchController(CONFIG, [_passive("a"), _passive("b")], 1)

    assert policy.scheduler_mode == "chunked"
    assert policy.scheduler_chunk_size == 2
    assert policy.scheduler_rotate_start is True
    assert controller.ruleset_policy is policy


def _service_process(
    process_id: str,
    position: int,
    share: int,
    output: int) -> ProcessInstance:
    def logic(obs: ObservationV2, state: dict[str, Any]) -> AgentAction:
        by_tick = state.setdefault("callbacks_by_tick", {})
        by_tick[obs.current_tick] = by_tick.get(obs.current_tick, 0) + 1
        state["service_actions"] = state.get("service_actions", 0) + 1
        return AgentAction(ActionKindV2.WRITE, output, 0x22)

    return ProcessInstance(
        process_id,
        ProcessRole.GENERALIST,
        position,
        50,
        share,
        logic)


def _scheduled_attacker(target: int, hit_ticks: set[int]) -> ProcessEntrantSpec:
    def logic(obs: ObservationV2, state: dict[str, Any]) -> AgentAction:
        if obs.current_tick in hit_ticks and state.get("last_hit") != obs.current_tick:
            state["last_hit"] = obs.current_tick
            state["disruption_writes"] = state.get("disruption_writes", 0) + 1
            return AgentAction(ActionKindV2.WRITE, target, 0xFF)
        state["other_actions"] = state.get("other_actions", 0) + 1
        return AgentAction(ActionKindV2.WRITE, (target + 30) % 1024, 0xEE)

    return ProcessEntrantSpec(
        "attacker",
        "attacker",
        [ProcessInstance("attacker", ProcessRole.ATTACKER, target, 50, 8, logic)])


@pytest.mark.skip
def test_d2_doubles_steady_suppression_efficiency() -> None:
    victim = ProcessEntrantSpec(
        "victim",
        "victim",
        [
            _service_process("base", 100, 4, 120),
            _service_process("scout", 900, 4, 920),
        ])
    attacker = _scheduled_attacker(900, {1, 3, 5, 7, 9})
    controller = ProcessMatchController(
        CONFIG,
        [victim, attacker],
        10,
        "model_c_movable_anchor")
    controller.run()

    base, scout = victim.processes
    attacker_process = attacker.processes[0]
    assert [base.telemetry.total_actions, scout.telemetry.total_actions] == [80, 0]
    assert scout.telemetry.disrupted_match_ticks == set(range(1, 11))
    assert attacker_process.local_state["disruption_writes"] == 5
    assert attacker_process.local_state["other_actions"] == 75
    assert 40 / attacker_process.local_state["disruption_writes"] == 8
    assert attacker_process.local_state["disruption_writes"] / 80 == 0.0625


def _single_hit_logic(target: int):
    def logic(obs: ObservationV2, state: dict[str, Any]) -> AgentAction:
        if not state.get("hit"):
            state["hit"] = True
            return AgentAction(ActionKindV2.WRITE, target, 0xFF)
        return AgentAction(ActionKindV2.WRITE, (target + 30) % 1024, 0xEE)

    return logic


def _single_hit_attacker(target: int) -> ProcessEntrantSpec:
    return ProcessEntrantSpec(
        "attacker",
        "attacker",
        [ProcessInstance("attacker", ProcessRole.ATTACKER, target, 50, 8, _single_hit_logic(target))])


@pytest.mark.parametrize("process_count", [2, 4])
@pytest.mark.skip
def test_shared_location_blast_disrupts_every_colocated_enemy(process_count: int) -> None:
    share = 8 // process_count
    victims = [
        ProcessInstance(f"victim_{index}", ProcessRole.GENERALIST, 100, 50, share, _counting_nop)
        for index in range(process_count)
    ]
    victim = ProcessEntrantSpec("victim", "victim", victims)
    attacker = _single_hit_attacker(100)
    controller = ProcessMatchController(
        CONFIG,
        [attacker, victim],
        1,
        "model_c_movable_anchor")
    controller.run()

    assert [process.telemetry.total_actions for process in victims] == [0] * process_count
    assert [process.telemetry.disruption_hits_received for process in victims] == [1] * process_count


@pytest.mark.skip
def test_shared_location_blast_preserves_colocated_friendly_processes() -> None:
    writer = ProcessInstance(
        "writer",
        ProcessRole.ATTACKER,
        100,
        50,
        4,
        _single_hit_logic(100))
    friend = ProcessInstance("friend", ProcessRole.GENERALIST, 100, 50, 4, _counting_nop)
    attacker = ProcessEntrantSpec("attacker", "attacker", [writer, friend])
    victims = [
        ProcessInstance(f"victim_{index}", ProcessRole.GENERALIST, 100, 50, 4, _counting_nop)
        for index in range(2)
    ]
    victim = ProcessEntrantSpec("victim", "victim", victims)
    controller = ProcessMatchController(
        CONFIG,
        [attacker, victim],
        1,
        "model_c_movable_anchor")
    controller.run()

    assert friend.disrupted_until_tick == 0
    assert friend.telemetry.total_actions == 4
    assert [process.telemetry.total_actions for process in victims] == [0, 0]


@pytest.mark.skip
def test_initial_anchor_is_normalized_before_targeting() -> None:
    victim_process = ProcessInstance(
        "victim",
        ProcessRole.GENERALIST,
        1024,
        50,
        8,
        _counting_nop)
    victim = ProcessEntrantSpec("victim", "victim", [victim_process])
    attacker = _single_hit_attacker(0)
    controller = ProcessMatchController(
        CONFIG,
        [attacker, victim],
        1,
        "model_c_movable_anchor")
    controller.run()

    assert victim_process.position == 0
    assert victim_process.telemetry.total_actions == 0
    assert victim_process.telemetry.disruption_hits_received == 1


@pytest.mark.skip
def test_dead_entrant_anchor_does_not_accumulate_disruption_metrics() -> None:
    def killer_logic(obs: ObservationV2, state: dict[str, Any]) -> AgentAction:
        action_index = state.get("action_index", 0)
        state["action_index"] = action_index + 1
        if obs.current_tick == 1:
            return AgentAction(ActionKindV2.WRITE, 341 + action_index, 0xDD)
        return AgentAction(ActionKindV2.WRITE, 341, 0xEE)

    killer = ProcessEntrantSpec(
        "killer",
        "killer",
        [ProcessInstance("killer", ProcessRole.ATTACKER, 341, 50, 8, killer_logic)])
    doomed_process = ProcessInstance(
        "doomed",
        ProcessRole.GENERALIST,
        341,
        50,
        8,
        _counting_nop)
    doomed = ProcessEntrantSpec("doomed", "doomed", [doomed_process])
    controller = ProcessMatchController(
        CONFIG,
        [killer, doomed, _passive()],
        3,
        "model_c_movable_anchor")
    controller.run()

    assert controller.states[1].alive is False
    assert doomed_process.telemetry.disruption_hits_received == 1
    assert doomed_process.telemetry.disrupted_match_ticks == {1}
    assert doomed_process.telemetry.total_disrupted_ticks == 1


def _one_tick_hit_logic(target: int):
    def logic(obs: ObservationV2, state: dict[str, Any]) -> AgentAction:
        if obs.current_tick == 1 and not state.get("hit"):
            state["hit"] = True
            return AgentAction(ActionKindV2.WRITE, target, 0xFF)
        return AgentAction(ActionKindV2.WRITE, target + 30, 0xEE)

    return logic


@pytest.mark.skip
def test_d1_recovers_at_the_next_tick() -> None:
    victim_process = ProcessInstance("victim", ProcessRole.GENERALIST, 100, 50, 8, _counting_nop)
    victim = ProcessEntrantSpec("victim", "victim", [victim_process])
    attacker = ProcessEntrantSpec(
        "attacker",
        "attacker",
        [ProcessInstance("attacker", ProcessRole.ATTACKER, 100, 50, 8, _one_tick_hit_logic(100))])
    controller = ProcessMatchController(
        CONFIG,
        [victim, attacker],
        2,
        "model_c_movable_anchor")
    controller.run()

    assert victim_process.local_state["callbacks_by_tick"] == {1: 2, 2: 8}
    assert victim_process.telemetry.disrupted_match_ticks == {1}
    assert victim_process.disrupted_until_tick == 2


@pytest.mark.skip
def test_d2_recovery_preserves_state_feedback_and_allows_move_without_duplicate_quota() -> None:
    def victim_logic(obs: ObservationV2, state: dict[str, Any]) -> AgentAction:
        observations = state.setdefault("observations", [])
        observations.append(
            {
                "tick": obs.current_tick,
                "last_kind": obs.previous_action_applied,
                "read_result": obs.previous_read_value,
                "counter_before": state.get("counter", 0),
            }
        )
        state["counter"] = state.get("counter", 0) + 1
        if obs.current_tick == 1:
            return AgentAction(ActionKindV2.READ, 200)
        if obs.current_tick == 3 and not state.get("recovery_move"):
            state["recovery_move"] = True
            return AgentAction(ActionKindV2.MOVE, 1)
        return AgentAction(ActionKindV2.NOP)

    victim_process = ProcessInstance("victim", ProcessRole.GENERALIST, 100, 50, 8, victim_logic)
    victim = ProcessEntrantSpec("victim", "victim", [victim_process])
    attacker = ProcessEntrantSpec(
        "attacker",
        "attacker",
        [ProcessInstance("attacker", ProcessRole.ATTACKER, 100, 50, 8, _one_tick_hit_logic(100))])
    controller = ProcessMatchController(
        CONFIG,
        [victim, attacker],
        3,
        "model_c_movable_anchor")
    controller.run()

    observations = victim_process.local_state["observations"]
    recovery_observation = next(item for item in observations if item["tick"] == 3)
    assert [item["tick"] for item in observations].count(1) == 2
    assert [item["tick"] for item in observations].count(2) == 0
    assert [item["tick"] for item in observations].count(3) == 8
    assert recovery_observation == {
        "tick": 3,
        "last_kind": ActionKindV2.READ,
        "read_result": 0,
        "counter_before": 2,
    }
    assert victim_process.telemetry.total_actions == 10
    assert victim_process.telemetry.total_moves == 1
    assert victim_process.position == 101
    assert victim_process.telemetry.disrupted_match_ticks == {1, 2}
    assert victim_process.disrupted_until_tick == 3


@pytest.mark.skip
def test_d1_monolith_can_trade_movement_for_partial_escape_from_perfect_information_pursuit() -> None:
    def victim_logic(obs: ObservationV2, state: dict[str, Any]) -> AgentAction:
        callbacks_by_tick = state.setdefault("callbacks_by_tick", {})
        callback_index = callbacks_by_tick.get(obs.current_tick, 0)
        callbacks_by_tick[obs.current_tick] = callback_index + 1
        if callback_index < 2:
            return AgentAction(ActionKindV2.MOVE, 64)
        state["service_actions"] = state.get("service_actions", 0) + 1
        return AgentAction(ActionKindV2.WRITE, (obs.self_anchor or 0) + 20, 0x22)

    victim_process = ProcessInstance(
        "victim",
        ProcessRole.GENERALIST,
        100,
        50,
        8,
        victim_logic)
    victim = ProcessEntrantSpec("victim", "victim", [victim_process])

    def attacker_logic(obs: ObservationV2, state: dict[str, Any]) -> AgentAction:
        target = victim_process.position or 0
        position = obs.self_anchor or 0
        raw_delta = target - position
        if raw_delta > obs.arena_size // 2:
            raw_delta -= obs.arena_size
        elif raw_delta < -(obs.arena_size // 2):
            raw_delta += obs.arena_size
        distance = min(abs(raw_delta), obs.arena_size - abs(raw_delta))
        if distance > (obs.self_reach or 0):
            state["pursuit_moves"] = state.get("pursuit_moves", 0) + 1
            return AgentAction(ActionKindV2.MOVE, max(-64, min(64, raw_delta)))
        if state.get("last_hit") != obs.current_tick:
            state["last_hit"] = obs.current_tick
            state["disruption_writes"] = state.get("disruption_writes", 0) + 1
            return AgentAction(ActionKindV2.WRITE, target, 0xFF)
        state["other_actions"] = state.get("other_actions", 0) + 1
        return AgentAction(ActionKindV2.NOP)

    attacker_process = ProcessInstance(
        "attacker",
        ProcessRole.ATTACKER,
        100,
        50,
        8,
        attacker_logic)
    attacker = ProcessEntrantSpec("attacker", "attacker", [attacker_process])
    controller = ProcessMatchController(
        CONFIG,
        [attacker, victim],
        10,
        "model_c_movable_anchor")
    controller.run()

    assert victim_process.telemetry.total_actions == 20
    assert victim_process.telemetry.total_moves == 10
    assert victim_process.local_state["service_actions"] == 10
    assert attacker_process.local_state["disruption_writes"] == 10
    assert attacker_process.local_state["pursuit_moves"] == 10
    assert attacker_process.local_state["other_actions"] == 60


def _memory_contention_control(ticks: int) -> tuple[ProcessMatchController, ProcessInstance, ProcessInstance]:
    base = _service_process("base", 100, 4, 120)
    scout = _service_process("scout", 900, 4, 920)
    victim = ProcessEntrantSpec("victim", "victim", [base, scout])

    def attacker_logic(obs: ObservationV2, state: dict[str, Any]) -> AgentAction:
        by_tick = state.setdefault("callbacks_by_tick", {})
        callback_index = by_tick.get(obs.current_tick, 0)
        by_tick[obs.current_tick] = callback_index + 1
        if callback_index == 7:
            state["contention_writes"] = state.get("contention_writes", 0) + 1
            return AgentAction(ActionKindV2.WRITE, 920, 0xFF)
        return AgentAction(ActionKindV2.WRITE, 930, 0xEE)

    attacker_process = ProcessInstance(
        "attacker",
        ProcessRole.ATTACKER,
        900,
        50,
        8,
        attacker_logic)
    attacker = ProcessEntrantSpec("attacker", "attacker", [attacker_process])
    controller = ProcessMatchController(
        CONFIG,
        [victim, attacker],
        ticks,
        "model_c_movable_anchor")
    controller.run()
    return controller, scout, attacker_process


@pytest.mark.skip
def test_ordinary_memory_contention_does_not_suppress_remote_callbacks() -> None:
    one_tick, scout_one, attacker_one = _memory_contention_control(1)
    two_ticks, scout_two, attacker_two = _memory_contention_control(2)

    assert scout_one.telemetry.total_actions == scout_one.local_state["service_actions"] == 4
    assert scout_two.telemetry.total_actions == scout_two.local_state["service_actions"] == 8
    assert attacker_one.local_state["contention_writes"] == 1
    assert attacker_two.local_state["contention_writes"] == 2
    assert one_tick.vm.writer[920] == "attacker"
    assert two_ticks.vm.writer[920] == "victim"


@pytest.mark.skip
def test_defended_core_attack_is_global_costly_and_non_reversible() -> None:
    def base_logic(obs: ObservationV2, state: dict[str, Any]) -> AgentAction:
        index = state.get("core_index", 0)
        state["core_index"] = index + 1
        return AgentAction(ActionKindV2.WRITE, obs.core_base + index % obs.core_size, 0x11)

    base = ProcessInstance("base", ProcessRole.DEFENDER, 0, 50, 4, base_logic)
    scout = _service_process("scout", 900, 4, 920)
    victim = ProcessEntrantSpec("victim", "victim", [base, scout])

    def core_attacker_logic(obs: ObservationV2, state: dict[str, Any]) -> AgentAction:
        if obs.self_anchor != 981:
            state["moves"] = state.get("moves", 0) + 1
            delta = 981 - (obs.self_anchor or 0)
            return AgentAction(ActionKindV2.MOVE, max(-64, min(64, delta)))
        index = state.get("core_index", 0)
        state["core_index"] = index + 1
        state["core_writes"] = state.get("core_writes", 0) + 1
        return AgentAction(ActionKindV2.WRITE, index % 8, 0xFF)

    attacker_process = ProcessInstance(
        "attacker",
        ProcessRole.ATTACKER,
        900,
        50,
        8,
        core_attacker_logic)
    attacker = ProcessEntrantSpec("attacker", "attacker", [attacker_process])
    controller = ProcessMatchController(
        CONFIG,
        [victim, attacker],
        10,
        "model_c_movable_anchor")
    result = controller.run()

    assert result["ticks_run"] == 3
    assert result["reason"] == "last_agent_standing"
    assert controller.states[0].alive is False
    assert attacker_process.telemetry.total_moves == 2
    assert attacker_process.local_state["core_writes"] == 22
    assert scout.local_state["service_actions"] == 12
    assert controller.states[0].total_actions == 24

