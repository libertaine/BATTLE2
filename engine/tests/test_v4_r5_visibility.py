"""Stage 5 research tests for deterministic process-anchor visibility."""

from __future__ import annotations

from typing import Any

import pytest
from battle_engine.agent_api import ActionKind, AgentAction
from battle_engine.config import Config, Weights
from battle_engine.process_runtime import (
    AnchorVisibilityModel,
    ProcessEntrantSpec,
    ProcessInstance,
    ProcessMatchController,
    ProcessModel,
    ProcessObservation,
    ProcessRole,
)

CONFIG = Config(arena_size=1024, instr_per_tick=8, seed=1, weights=Weights())
REACH = 50


def _counting_nop(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
    state["callbacks"] = state.get("callbacks", 0) + 1
    state.setdefault("visibility", []).append((obs.tick, obs.visible_enemy_anchors))
    return AgentAction(ActionKind.NOP)


def _process(
    process_id: str,
    position: int,
    share: int,
    logic=_counting_nop,
) -> ProcessInstance:
    return ProcessInstance(
        process_id,
        ProcessRole.GENERALIST,
        initial_position=position,
        reach=REACH,
        quota_share=share,
        logic=logic,
    )


def _signed_delta(source: int, target: int, arena_size: int) -> int:
    delta = target - source
    if delta > arena_size // 2:
        delta -= arena_size
    elif delta < -(arena_size // 2):
        delta += arena_size
    return delta


def _searching_attacker(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
    action_index = state.get("action_index", 0) + 1
    state["action_index"] = action_index

    if obs.visible_enemy_anchors:
        if "first_detection_tick" not in state:
            state["first_detection_tick"] = obs.tick
            state["first_detection_action"] = action_index
        target = min(
            obs.visible_enemy_anchors,
            key=lambda address: abs(_signed_delta(obs.position or 0, address, obs.arena_size)),
        )
        state["last_known"] = target

    target = state.get("last_known")
    if target is None:
        state["search_moves"] = state.get("search_moves", 0) + 1
        return AgentAction(ActionKind.MOVE, 64)

    delta = _signed_delta(obs.position or 0, target, obs.arena_size)
    if abs(delta) > (obs.reach or 0):
        state["pursuit_moves"] = state.get("pursuit_moves", 0) + 1
        return AgentAction(ActionKind.MOVE, max(-64, min(64, delta)))

    if state.get("last_attempt_tick") != obs.tick:
        state["last_attempt_tick"] = obs.tick
        state["attempts"] = state.get("attempts", 0) + 1
        return AgentAction(ActionKind.WRITE, target, 0xFF)

    state["other_actions"] = state.get("other_actions", 0) + 1
    return AgentAction(ActionKind.NOP)


def _run_static_search(
    model: AnchorVisibilityModel,
    target_position: int,
) -> tuple[ProcessInstance, ProcessInstance]:
    attacker_process = _process("attacker", 0, 8, _searching_attacker)
    target_process = _process("target", target_position, 8)
    controller = ProcessMatchController(
        CONFIG,
        [
            ProcessEntrantSpec("attacker", "attacker", [attacker_process]),
            ProcessEntrantSpec("victim", "victim", [target_process]),
        ],
        max_ticks=2,
        model=ProcessModel.MODEL_C_MOVABLE_ANCHOR,
        disruption_duration=1,
        anchor_visibility_model=model,
        detection_radius=REACH,
    )
    controller.run()
    return attacker_process, target_process


@pytest.mark.parametrize(
    (
        "target_position",
        "public_pursuit",
        "local_search",
        "local_tick",
        "local_action",
        "local_hits",
        "local_callbacks",
        "local_other_actions",
    ),
    [
        (256, 4, 4, 1, 5, 2, 6, 10),
        (768, 4, 12, 2, 13, 1, 14, 3),
    ],
)
def test_static_target_public_control_vs_local_clockwise_search(
    target_position: int,
    public_pursuit: int,
    local_search: int,
    local_tick: int,
    local_action: int,
    local_hits: int,
    local_callbacks: int,
    local_other_actions: int,
) -> None:
    public_attacker, public_target = _run_static_search(
        AnchorVisibilityModel.PUBLIC,
        target_position,
    )
    local_attacker, local_target = _run_static_search(
        AnchorVisibilityModel.LOCAL_DETECTION,
        target_position,
    )

    assert public_attacker.local_state["first_detection_tick"] == 1
    assert public_attacker.local_state["first_detection_action"] == 1
    assert public_attacker.local_state.get("search_moves", 0) == 0
    assert public_attacker.local_state["pursuit_moves"] == public_pursuit
    assert public_attacker.local_state["attempts"] == 2
    assert public_attacker.local_state["other_actions"] == 10
    assert public_target.telemetry.disruption_hits_received == 2
    assert public_target.telemetry.total_actions == 6
    assert 16 - public_target.telemetry.total_actions == 10

    assert local_attacker.local_state["first_detection_tick"] == local_tick
    assert local_attacker.local_state["first_detection_action"] == local_action
    assert local_attacker.local_state["search_moves"] == local_search
    assert local_attacker.local_state.get("pursuit_moves", 0) == 0
    assert local_attacker.local_state["attempts"] == local_hits
    assert local_attacker.local_state["other_actions"] == local_other_actions
    assert local_target.telemetry.disruption_hits_received == local_hits
    assert local_target.telemetry.total_actions == local_callbacks
    assert 16 - local_target.telemetry.total_actions == 16 - local_callbacks


@pytest.mark.parametrize(
    ("radius", "expected"),
    [
        (25, ()),
        (50, (40,)),
        (75, (40, 75)),
    ],
)
def test_detection_radius_below_equal_and_above_reach(
    radius: int,
    expected: tuple[int, ...],
) -> None:
    observer = _process("observer", 0, 8)
    near = _process("near", 40, 4)
    far = _process("far", 75, 4)
    controller = ProcessMatchController(
        CONFIG,
        [
            ProcessEntrantSpec("observer", "observer", [observer]),
            ProcessEntrantSpec("victim", "victim", [near, far]),
        ],
        max_ticks=1,
        model=ProcessModel.MODEL_C_MOVABLE_ANCHOR,
        anchor_visibility_model=AnchorVisibilityModel.LOCAL_DETECTION,
        detection_radius=radius,
    )
    controller.run()

    assert observer.local_state["visibility"][0] == (1, expected)


def test_local_detection_is_current_exact_and_entrant_wide() -> None:
    scout = _process("scout", 0, 4)
    attacker = _process("attacker", 500, 4)
    targets = [_process("one", 40, 4), _process("two", 40, 4)]
    controller = ProcessMatchController(
        CONFIG,
        [
            ProcessEntrantSpec("observer", "observer", [scout, attacker]),
            ProcessEntrantSpec("victim", "victim", targets),
        ],
        max_ticks=1,
        model=ProcessModel.MODEL_C_MOVABLE_ANCHOR,
        anchor_visibility_model=AnchorVisibilityModel.LOCAL_DETECTION,
        detection_radius=REACH,
    )
    controller.run()

    assert scout.local_state["visibility"][0] == (1, (40,))
    assert attacker.local_state["visibility"][0] == (1, (40,))


def test_detection_is_evaluated_before_each_callback_after_movement() -> None:
    def observer_logic(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
        state.setdefault("trace", []).append((obs.position, obs.visible_enemy_anchors))
        if not obs.visible_enemy_anchors:
            return AgentAction(ActionKind.MOVE, 10)
        return AgentAction(ActionKind.NOP)

    observer = _process("observer", 0, 8, observer_logic)
    target = _process("target", 60, 8)
    controller = ProcessMatchController(
        CONFIG,
        [
            ProcessEntrantSpec("observer", "observer", [observer]),
            ProcessEntrantSpec("victim", "victim", [target]),
        ],
        max_ticks=1,
        model=ProcessModel.MODEL_C_MOVABLE_ANCHOR,
        anchor_visibility_model=AnchorVisibilityModel.LOCAL_DETECTION,
        detection_radius=REACH,
    )
    controller.run()

    assert observer.local_state["trace"][:2] == [(0, ()), (10, (60,))]


def _run_moving_target(
    model: AnchorVisibilityModel,
) -> tuple[ProcessInstance, ProcessInstance, ProcessInstance]:
    def scout_logic(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
        state.setdefault("trace", []).append(
            (obs.tick, obs.position, obs.visible_enemy_anchors)
        )
        if obs.visible_enemy_anchors:
            obs.shared_memory["last_known"] = obs.visible_enemy_anchors[0]
            obs.shared_memory["last_seen_tick"] = obs.tick
            return AgentAction(ActionKind.NOP)
        if obs.tick >= 2:
            state["search_moves"] = state.get("search_moves", 0) + 1
            return AgentAction(ActionKind.MOVE, 64)
        return AgentAction(ActionKind.NOP)

    def attacker_logic(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
        state.setdefault("trace", []).append(
            (
                obs.tick,
                obs.position,
                obs.visible_enemy_anchors,
                obs.shared_memory.get("last_known"),
            )
        )
        if obs.visible_enemy_anchors:
            obs.shared_memory["last_known"] = obs.visible_enemy_anchors[0]
            obs.shared_memory["last_seen_tick"] = obs.tick
        target = obs.shared_memory.get("last_known")
        if target is None:
            state["other_actions"] = state.get("other_actions", 0) + 1
            return AgentAction(ActionKind.NOP)

        delta = _signed_delta(obs.position or 0, target, obs.arena_size)
        if abs(delta) > (obs.reach or 0):
            state["pursuit_moves"] = state.get("pursuit_moves", 0) + 1
            return AgentAction(ActionKind.MOVE, max(-64, min(64, delta)))
        if state.get("last_attempt_tick") != obs.tick:
            state["last_attempt_tick"] = obs.tick
            state["attempts"] = state.get("attempts", 0) + 1
            return AgentAction(ActionKind.WRITE, target, 0xFF)
        state["other_actions"] = state.get("other_actions", 0) + 1
        return AgentAction(ActionKind.NOP)

    def target_logic(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
        callback_by_tick = state.setdefault("callback_by_tick", {})
        callback_index = callback_by_tick.get(obs.tick, 0)
        callback_by_tick[obs.tick] = callback_index + 1
        if callback_index == 0:
            return AgentAction(ActionKind.MOVE, 64)
        return AgentAction(ActionKind.NOP)

    scout = _process("scout", 50, 2, scout_logic)
    attacker = _process("attacker", 100, 6, attacker_logic)
    target = _process("target", 100, 8, target_logic)
    controller = ProcessMatchController(
        CONFIG,
        [
            ProcessEntrantSpec("observer", "observer", [scout, attacker]),
            ProcessEntrantSpec("victim", "victim", [target]),
        ],
        max_ticks=2,
        model=ProcessModel.MODEL_C_MOVABLE_ANCHOR,
        disruption_duration=1,
        anchor_visibility_model=model,
        detection_radius=REACH,
    )
    controller.run()
    return scout, attacker, target


def test_moving_target_public_tracking_vs_local_staleness_and_reacquisition() -> None:
    public_scout, public_attacker, public_target = _run_moving_target(
        AnchorVisibilityModel.PUBLIC
    )
    local_scout, local_attacker, local_target = _run_moving_target(
        AnchorVisibilityModel.LOCAL_DETECTION
    )

    assert public_scout.telemetry.total_moves == 0
    assert public_attacker.local_state["attempts"] == 2
    assert public_attacker.local_state["pursuit_moves"] == 2
    assert public_attacker.local_state["other_actions"] == 8
    assert public_target.telemetry.disruption_hits_received == 2
    assert public_target.telemetry.total_actions == 6
    assert 16 - public_target.telemetry.total_actions == 10

    assert local_scout.local_state["search_moves"] == 2
    assert local_attacker.local_state["attempts"] == 2
    assert local_attacker.local_state["pursuit_moves"] == 2
    assert local_attacker.local_state["other_actions"] == 8
    assert local_target.telemetry.disruption_hits_received == 1
    assert local_target.telemetry.total_actions == 14
    assert local_attacker.local_state["attempts"] - local_target.telemetry.disruption_hits_received == 1
    assert 16 - local_target.telemetry.total_actions == 2
    assert local_attacker.local_state["trace"][0] == (1, 100, (), 100)
    assert next(item for item in local_attacker.local_state["trace"] if item[0] == 2) == (
        2,
        100,
        (228,),
        100,
    )


def test_local_detection_selects_spatial_targets_without_structural_metadata() -> None:
    observer = _process("observer", 750, 8)
    defender = _process("defender", 100, 4)
    scout = _process("scout", 800, 4)
    controller = ProcessMatchController(
        CONFIG,
        [
            ProcessEntrantSpec("observer", "observer", [observer]),
            ProcessEntrantSpec("victim", "victim", [defender, scout]),
        ],
        max_ticks=1,
        model=ProcessModel.MODEL_C_MOVABLE_ANCHOR,
        anchor_visibility_model=AnchorVisibilityModel.LOCAL_DETECTION,
        detection_radius=REACH,
    )
    controller.run()

    assert observer.local_state["visibility"][0] == (1, (800,))
    assert {
        "enemy_process_ids",
        "enemy_process_counts",
        "enemy_quota_shares",
        "enemy_reaches",
        "enemy_disruption_states",
    }.isdisjoint(ProcessObservation.__dataclass_fields__)


def test_nearby_enemy_anchors_are_exact_addresses_while_colocation_collapses() -> None:
    observer = _process("observer", 0, 8)
    targets = [
        _process("one", 40, 2),
        _process("two", 45, 2),
        _process("three", 45, 2),
        _process("four", 60, 2),
    ]
    controller = ProcessMatchController(
        CONFIG,
        [
            ProcessEntrantSpec("observer", "observer", [observer]),
            ProcessEntrantSpec("victim", "victim", targets),
        ],
        max_ticks=1,
        model=ProcessModel.MODEL_C_MOVABLE_ANCHOR,
        anchor_visibility_model=AnchorVisibilityModel.LOCAL_DETECTION,
        detection_radius=REACH,
    )
    controller.run()

    assert observer.local_state["visibility"][0] == (1, (40, 45))


def test_hidden_default_and_circular_detection_do_not_leak_internal_positions() -> None:
    hidden_observer = _process("hidden", 1000, 8)
    hidden_target = _process("target", 20, 8)
    hidden = ProcessMatchController(
        CONFIG,
        [
            ProcessEntrantSpec("observer", "observer", [hidden_observer]),
            ProcessEntrantSpec("victim", "victim", [hidden_target]),
        ],
        max_ticks=1,
        model=ProcessModel.MODEL_C_MOVABLE_ANCHOR,
    )
    hidden.run()
    assert hidden_observer.local_state["visibility"][0] == (1, ())

    local_observer = _process("local", 1000, 8)
    local_target = _process("target", 1044, 8)
    local = ProcessMatchController(
        CONFIG,
        [
            ProcessEntrantSpec("observer", "observer", [local_observer]),
            ProcessEntrantSpec("victim", "victim", [local_target]),
        ],
        max_ticks=1,
        model=ProcessModel.MODEL_C_MOVABLE_ANCHOR,
        anchor_visibility_model=AnchorVisibilityModel.LOCAL_DETECTION,
        detection_radius=REACH,
    )
    local.run()
    assert local_target.position == 20
    assert local_observer.local_state["visibility"][0] == (1, (20,))


def test_local_detection_defaults_to_each_sensor_action_reach() -> None:
    observer = _process("observer", 0, 8)
    target = _process("target", REACH, 8)
    controller = ProcessMatchController(
        CONFIG,
        [
            ProcessEntrantSpec("observer", "observer", [observer]),
            ProcessEntrantSpec("victim", "victim", [target]),
        ],
        max_ticks=1,
        model=ProcessModel.MODEL_C_MOVABLE_ANCHOR,
        anchor_visibility_model=AnchorVisibilityModel.LOCAL_DETECTION,
    )
    controller.run()

    assert observer.local_state["visibility"][0] == (1, (REACH,))


def test_disrupted_friendly_anchor_is_not_a_passive_detection_sensor() -> None:
    scout = _process("scout", 0, 4)
    observer = _process("observer", 500, 4)
    target = _process("target", 40, 8)
    controller = ProcessMatchController(
        CONFIG,
        [
            ProcessEntrantSpec("observer", "observer", [scout, observer]),
            ProcessEntrantSpec("victim", "victim", [target]),
        ],
        max_ticks=1,
        model=ProcessModel.MODEL_C_MOVABLE_ANCHOR,
        anchor_visibility_model=AnchorVisibilityModel.LOCAL_DETECTION,
    )
    scout.disrupted_until_tick = 2
    controller.run()

    assert scout.telemetry.total_actions == 0
    assert observer.local_state["visibility"][0] == (1, ())


def test_enemy_activity_does_not_reveal_an_anchor_under_hidden_control() -> None:
    observer = _process("observer", 0, 8)

    def active_target(obs: ProcessObservation, state: dict[str, Any]) -> AgentAction:
        return AgentAction(ActionKind.WRITE, 25, 0xAA)

    target = _process("target", 40, 8, active_target)
    controller = ProcessMatchController(
        CONFIG,
        [
            ProcessEntrantSpec("observer", "observer", [observer]),
            ProcessEntrantSpec("victim", "victim", [target]),
        ],
        max_ticks=1,
        model=ProcessModel.MODEL_C_MOVABLE_ANCHOR,
    )
    controller.run()

    assert all(visible == () for _, visible in observer.local_state["visibility"])


def test_dead_enemy_anchor_is_not_visible() -> None:
    observer = _process("observer", 0, 8)
    target = _process("target", 40, 8)
    controller = ProcessMatchController(
        CONFIG,
        [
            ProcessEntrantSpec("observer", "observer", [observer]),
            ProcessEntrantSpec("victim", "victim", [target]),
        ],
        max_ticks=1,
        model=ProcessModel.MODEL_C_MOVABLE_ANCHOR,
        anchor_visibility_model=AnchorVisibilityModel.PUBLIC,
    )
    controller.states[1].alive = False
    controller.run()

    assert observer.local_state["visibility"][0] == (1, ())


def test_invalid_visibility_configuration_is_rejected() -> None:
    entrant = ProcessEntrantSpec("observer", "observer", [_process("observer", 0, 8)])

    with pytest.raises(ValueError, match="not a valid AnchorVisibilityModel"):
        ProcessMatchController(
            CONFIG,
            [entrant],
            1,
            anchor_visibility_model="omniscient_debug",  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="detection_radius must be non-negative"):
        ProcessMatchController(CONFIG, [entrant], 1, detection_radius=-1)
