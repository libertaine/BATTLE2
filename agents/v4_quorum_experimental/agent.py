"""Quorum -- an intentionally ambitious Bytefray v4 Agent API v2 experiment.

Quorum is not a starter and is not meant to be "the recommended way" to
write an agent.  It is a boundary-pushing consumer of the public v4 API.

The agent declares six fixed processes but treats them as one coordinated
system.  It combines:

* a global-reach "oracle" that turns entrant-shared visibility into a sensor
  network and can disrupt one live anchor anywhere in the arena;
* a two-slot breaker that travels toward remembered enemy start positions and
  sweeps likely core cells;
* a two-slot guardian that READs its own vulnerable core and repairs cells
  whose ownership changed;
* two independently moving flankers that bracket a strategic target;
* an adaptive reserve that falls back to core defense after pressure or a
  detected callback gap, otherwise reinforces the attack;
* shared contact memory, weak READ-derived evidence, deterministic target
  selection, per-tick attack de-duplication, and recovery inference from the
  temporal observation fields.

Everything here uses only MatchContextV2, ObservationV2, ProcessDeclaration,
AgentAction, and ActionKindV2.  No replay access, engine introspection, match
metadata, filesystem state, networking, or global randomness is used.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from battle_engine.agent_api import (
    ActionKindV2,
    AgentAction,
    MatchContextV2,
    ObservationV2,
    ProcessDeclaration,
)


@dataclass
class Contact:
    """A remembered address that was observed or inferred to be enemy-held."""

    address: int
    first_tick: int
    last_tick: int
    sightings: int = 1
    live_anchor: bool = True


class QuorumAgent:
    """Six-process coordinated v4 agent with offense, defense, and memory."""

    _CORE_ORDER = (0, 7, 3, 4, 1, 6, 2, 5)
    _SIEGE_ORDER = (0, 7, 3, 4, 1, 6, 2, 5, -1, 8, -2, 9, -3, 10, -4, 11)
    _SIGNATURES = {
        "oracle": 0x91,
        "breaker": 0xB4,
        "guardian": 0xD3,
        "flank_left": 0x4C,
        "flank_right": 0x4D,
        "reserve": 0x6E,
    }

    def reset(self, context: MatchContextV2) -> None:
        self.context = context
        self.arena = context.arena_size

        self.contacts: dict[int, Contact] = {}
        self.core_candidates: dict[int, int] = {}
        self.weak_targets: dict[int, int] = {}
        self.current_visible: tuple[int, ...] = ()
        self.initial_contact_tick: int | None = None

        self.pending_reads: dict[str, int] = {}
        self.repair_queue: list[int] = []

        self.deployed: set[str] = set()
        self.siege_index: dict[str, int] = {
            "oracle": 0,
            "breaker": 0,
            "flank_left": 0,
            "flank_right": 8,
            "reserve": 0,
        }
        self.guard_index = 0
        self.search_step = 0
        self.search_stride = self._coprime_stride(self.arena)

        self.tick_marker = -1
        self.attacked_anchors: set[int] = set()
        self.pressure_until = -1
        self.recovery_alarm_until = -1
        self.recovery_events: list[tuple[int, str]] = []

        self.patrol_direction = -1 if context.rng.randrange(2) else 1

    def declare_processes(self) -> list[ProcessDeclaration]:
        global_reach = max(1, min(self.arena - 1, self.arena // 2))
        return [
            ProcessDeclaration(id="oracle", reach=global_reach, share=0.125),
            ProcessDeclaration(id="breaker", reach=self._reach(48), share=0.250),
            ProcessDeclaration(id="guardian", reach=self._reach(12), share=0.250),
            ProcessDeclaration(id="flank_left", reach=self._reach(32), share=0.125),
            ProcessDeclaration(id="flank_right", reach=self._reach(32), share=0.125),
            ProcessDeclaration(id="reserve", reach=self._reach(24), share=0.125),
        ]

    def act(self, observation: ObservationV2) -> AgentAction:
        self._begin_tick(observation.current_tick)
        self._consume_feedback(observation)
        self._observe(observation)
        self._infer_recovery(observation)

        deployment = self._deployment_action(observation)
        if deployment is not None:
            return deployment

        pid = observation.self_process_id
        if pid == "oracle":
            return self._act_oracle(observation)
        if pid == "breaker":
            return self._act_breaker(observation)
        if pid == "guardian":
            return self._act_guardian(observation)
        if pid == "flank_left":
            return self._act_flanker(observation, side=-1)
        if pid == "flank_right":
            return self._act_flanker(observation, side=1)
        if pid == "reserve":
            return self._act_reserve(observation)
        return AgentAction(kind=ActionKindV2.MOVE, operand=0)

    def _begin_tick(self, tick: int) -> None:
        if tick == self.tick_marker:
            return
        self.tick_marker = tick
        self.attacked_anchors.clear()
        for contact in self.contacts.values():
            contact.live_anchor = False
        self.weak_targets = {
            address: seen_tick
            for address, seen_tick in self.weak_targets.items()
            if tick - seen_tick <= 64
        }

    def _consume_feedback(self, obs: ObservationV2) -> None:
        pending = self.pending_reads.pop(obs.self_process_id, None)
        if pending is None or not obs.previous_action_applied:
            return

        owner = obs.previous_read_owner
        if obs.self_process_id == "guardian":
            if owner != self.context.agent_id and pending not in self.repair_queue:
                self.repair_queue.append(pending)
            return

        if owner is not None and owner != self.context.agent_id:
            self.weak_targets[pending] = obs.current_tick
            self._remember_contact(pending, obs.current_tick, live_anchor=False)

    def _observe(self, obs: ObservationV2) -> None:
        visible = tuple(sorted(set(obs.visible_enemy_anchor_addresses)))
        self.current_visible = visible

        for address in visible:
            self._remember_contact(address, obs.current_tick, live_anchor=True)

        if visible:
            if self.initial_contact_tick is None:
                self.initial_contact_tick = obs.current_tick
            if obs.current_tick <= self.initial_contact_tick + 1:
                confidence = 100 if obs.current_tick == self.initial_contact_tick else 70
                for address in visible:
                    self.core_candidates[address] = max(
                        confidence, self.core_candidates.get(address, 0)
                    )

        pressure_radius = max(16, obs.own_core_size * 3)
        if any(
            self._distance(address, obs.own_core_base) <= pressure_radius
            for address in visible
        ):
            self.pressure_until = max(self.pressure_until, obs.current_tick + 3)

    def _remember_contact(self, address: int, tick: int, *, live_anchor: bool) -> None:
        address %= self.arena
        contact = self.contacts.get(address)
        if contact is None:
            self.contacts[address] = Contact(
                address=address,
                first_tick=tick,
                last_tick=tick,
                live_anchor=live_anchor,
            )
            return
        if contact.last_tick != tick:
            contact.sightings += 1
        contact.last_tick = tick
        contact.live_anchor = contact.live_anchor or live_anchor

    def _infer_recovery(self, obs: ObservationV2) -> None:
        if obs.last_callback_tick < 0:
            return
        if obs.current_tick - obs.last_callback_tick <= 1:
            return
        event = (obs.current_tick, obs.self_process_id)
        if event not in self.recovery_events:
            self.recovery_events.append(event)
        self.recovery_alarm_until = max(
            self.recovery_alarm_until, obs.current_tick + 3
        )

    def _deployment_action(self, obs: ObservationV2) -> AgentAction | None:
        pid = obs.self_process_id
        if pid == "guardian" or pid in self.deployed:
            return None

        unit = max(1, min(16, self.arena // 32))
        desired = {
            "oracle": 4 * unit,
            "breaker": 3 * unit,
            "flank_left": -3 * unit,
            "flank_right": 2 * unit,
            "reserve": -2 * unit,
        }[pid]
        self.deployed.add(pid)
        return AgentAction(kind=ActionKindV2.MOVE, operand=self._clamp_move(desired))

    def _act_oracle(self, obs: ObservationV2) -> AgentAction:
        live = self._best_live_anchor(obs)
        if live is not None:
            self.attacked_anchors.add(live)
            return AgentAction(
                kind=ActionKindV2.WRITE,
                operand=live,
                value=self._SIGNATURES["oracle"],
            )

        target = self._strategic_target(obs.current_tick)
        if target is not None:
            return self._siege_write(obs, target, "oracle")

        probe = self._next_probe(obs.own_core_base)
        self.pending_reads["oracle"] = probe
        return AgentAction(kind=ActionKindV2.READ, operand=probe)

    def _act_breaker(self, obs: ObservationV2) -> AgentAction:
        live = self._best_live_anchor(obs)
        if live is not None and self._within_reach(obs, live):
            self.attacked_anchors.add(live)
            return AgentAction(
                kind=ActionKindV2.WRITE,
                operand=live,
                value=self._SIGNATURES["breaker"],
            )

        target = self._strategic_target(obs.current_tick)
        if target is None:
            return self._patrol(obs, multiplier=1)
        if not self._within_reach(obs, target):
            return self._move_toward(obs, target)
        return self._siege_write(obs, target, "breaker")

    def _act_guardian(self, obs: ObservationV2) -> AgentAction:
        live = self._best_live_anchor(obs)
        if live is not None and self._within_reach(obs, live):
            self.attacked_anchors.add(live)
            self.pressure_until = max(self.pressure_until, obs.current_tick + 2)
            return AgentAction(
                kind=ActionKindV2.WRITE,
                operand=live,
                value=self._SIGNATURES["guardian"],
            )

        if self.repair_queue:
            address = self.repair_queue.pop(0)
            return AgentAction(
                kind=ActionKindV2.WRITE,
                operand=address,
                value=self._SIGNATURES["guardian"],
            )

        offset = self._CORE_ORDER[self.guard_index % len(self._CORE_ORDER)]
        self.guard_index += 1
        address = (obs.own_core_base + offset) % self.arena
        self.pending_reads["guardian"] = address
        return AgentAction(kind=ActionKindV2.READ, operand=address)

    def _act_flanker(self, obs: ObservationV2, *, side: int) -> AgentAction:
        pid = obs.self_process_id
        live = self._best_live_anchor(obs)
        if live is not None and self._within_reach(obs, live):
            self.attacked_anchors.add(live)
            return AgentAction(
                kind=ActionKindV2.WRITE,
                operand=live,
                value=self._SIGNATURES[pid],
            )

        target = self._strategic_target(obs.current_tick)
        if target is None:
            return self._patrol(obs, multiplier=side)

        standoff = max(4, obs.self_reach // 2)
        desired_anchor = (target + side * standoff) % self.arena
        if self._distance(obs.self_anchor, desired_anchor) > max(2, standoff // 2):
            return self._move_toward(obs, desired_anchor)
        if self._within_reach(obs, target):
            return self._siege_write(obs, target, pid)
        return self._patrol(obs, multiplier=side)

    def _act_reserve(self, obs: ObservationV2) -> AgentAction:
        defensive = (
            obs.current_tick <= self.pressure_until
            or obs.current_tick <= self.recovery_alarm_until
        )
        if defensive:
            live = self._best_live_anchor(obs, reference=obs.own_core_base)
            if live is not None and self._within_reach(obs, live):
                self.attacked_anchors.add(live)
                return AgentAction(
                    kind=ActionKindV2.WRITE,
                    operand=live,
                    value=self._SIGNATURES["reserve"],
                )

            core_center = (
                obs.own_core_base + max(0, obs.own_core_size // 2)
            ) % self.arena
            if self._distance(obs.self_anchor, core_center) > max(4, obs.self_reach // 2):
                return self._move_toward(obs, core_center)

            offset = self._CORE_ORDER[
                self.siege_index["reserve"] % len(self._CORE_ORDER)
            ]
            self.siege_index["reserve"] += 1
            return AgentAction(
                kind=ActionKindV2.WRITE,
                operand=(obs.own_core_base + offset) % self.arena,
                value=self._SIGNATURES["reserve"],
            )

        live = self._best_live_anchor(obs)
        if live is not None and self._within_reach(obs, live):
            self.attacked_anchors.add(live)
            return AgentAction(
                kind=ActionKindV2.WRITE,
                operand=live,
                value=self._SIGNATURES["reserve"],
            )

        target = self._strategic_target(obs.current_tick)
        if target is None:
            return self._patrol(obs, multiplier=-1)
        if not self._within_reach(obs, target):
            return self._move_toward(obs, target)
        return self._siege_write(obs, target, "reserve")

    def _best_live_anchor(
        self,
        obs: ObservationV2,
        *,
        reference: int | None = None,
    ) -> int | None:
        candidates = [
            address
            for address in self.current_visible
            if address not in self.attacked_anchors
        ]
        if not candidates:
            return None
        anchor = obs.self_anchor if reference is None else reference
        return min(
            candidates,
            key=lambda address: (self._distance(address, anchor), address),
        )

    def _strategic_target(self, tick: int) -> int | None:
        if self.core_candidates:
            ordered = sorted(
                self.core_candidates,
                key=lambda address: (-self.core_candidates[address], address),
            )
            best_score = self.core_candidates[ordered[0]]
            best = [a for a in ordered if self.core_candidates[a] == best_score]
            return best[(tick // 24) % len(best)]

        if self.weak_targets:
            return max(
                self.weak_targets,
                key=lambda address: (self.weak_targets[address], -address),
            )

        if self.contacts:
            return max(
                self.contacts.values(),
                key=lambda c: (c.last_tick, c.sightings, -c.address),
            ).address

        return None

    def _siege_write(
        self,
        obs: ObservationV2,
        target: int,
        pid: str,
    ) -> AgentAction:
        index = self.siege_index[pid] % len(self._SIEGE_ORDER)
        self.siege_index[pid] += 1
        address = (target + self._SIEGE_ORDER[index]) % self.arena

        if not self._within_reach(obs, address):
            return self._move_toward(obs, target)

        return AgentAction(
            kind=ActionKindV2.WRITE,
            operand=address,
            value=self._SIGNATURES[pid],
        )

    def _move_toward(self, obs: ObservationV2, target: int) -> AgentAction:
        delta = self._shortest_delta(target, obs.self_anchor)
        return AgentAction(
            kind=ActionKindV2.MOVE,
            operand=self._clamp_move(delta),
        )

    def _patrol(self, obs: ObservationV2, *, multiplier: int) -> AgentAction:
        direction = self.patrol_direction * (1 if multiplier >= 0 else -1)
        magnitude = min(64, max(1, obs.self_reach))
        return AgentAction(
            kind=ActionKindV2.MOVE,
            operand=direction * magnitude,
        )

    def _next_probe(self, origin: int) -> int:
        self.search_step += 1
        return (origin + self.search_step * self.search_stride) % self.arena

    def _reach(self, desired: int) -> int:
        return max(1, min(desired, self.arena - 1))

    def _within_reach(self, obs: ObservationV2, address: int) -> bool:
        return self._distance(obs.self_anchor, address) <= obs.self_reach

    def _distance(self, a: int, b: int) -> int:
        delta = abs((a - b) % self.arena)
        return min(delta, self.arena - delta)

    def _shortest_delta(self, target: int, anchor: int) -> int:
        forward = (target - anchor) % self.arena
        backward = forward - self.arena
        if abs(backward) < abs(forward):
            return backward
        return forward

    @staticmethod
    def _clamp_move(delta: int) -> int:
        return max(-64, min(64, delta))

    @staticmethod
    def _coprime_stride(arena_size: int) -> int:
        ceiling = min(63, max(1, arena_size - 1))
        for stride in range(ceiling, 0, -1):
            if math.gcd(stride, arena_size) == 1:
                return stride
        return 1


def create_agent():
    return QuorumAgent()
