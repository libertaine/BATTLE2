"""Hydra -- competitive Bytefray Agent API v2 stress agent.

Hydra deliberately exercises several v4 alpha1 mechanics at once:

* entrant-wide anchor visibility through a long-reach interceptor;
* early-tick disruption of enemy process anchors;
* sustained pressure against the likely opposing core in pairwise matches;
* late-tick defensive rewrites across its own eight-cell core; and
* a mobile rover that continually changes spatial position.

The design is deterministic for a given engine-supplied match seed.
"""

from __future__ import annotations

import math

from battle_engine.agent_api import (
    ActionKindV2,
    AgentAction,
    MatchContextV2,
    ObservationV2,
    ProcessDeclaration,
)


class HydraAgent:
    """Four-role API-v2 agent built for competitive pairwise testing."""

    # Core visitation orders are deliberately spread across the eight-cell
    # block so attack/repair pressure is not concentrated on adjacent cells.
    _SIEGE_OFFSETS = (0, 7, 3, 4, 1, 6, 2, 5)
    _GUARD_OFFSETS = (0, 7, 4, 3, 1, 6, 5, 2)
    _PRESSURE_OFFSETS = (1, 6, 2, 5, 4, 3, 7, 0)

    def reset(self, context: MatchContextV2) -> None:
        self.context = context

        # Offensive state shared across process callbacks.  API v2 gives every
        # process the same agent object, so this is intentional coordination,
        # not hidden engine state.
        self.enemy_core_base: int | None = None
        self.siege_index = 0
        self.pressure_index = 0

        # Prevent the interceptor from spending all of its same-tick quota on
        # repeatedly disrupting one already-hit anchor.
        self.intercept_tick = -1
        self.intercepted_positions: set[int] = set()

        # Defensive and rover state.
        self.guard_index = 0
        self.rover_direction = -1 if context.rng.randrange(2) else 1
        self.rover_stride = self._choose_rover_stride(context.arena_size)

    def declare_processes(self) -> list[ProcessDeclaration]:
        # On a circular arena the greatest possible shortest-path distance is
        # floor(N/2).  API v2 alpha1 currently charges no quota/resource cost
        # for reach, so the two offensive processes intentionally declare that
        # full-arena effective reach.  This is a stress test of the rules as
        # published, not an accidental starter-agent convention.
        global_reach = max(1, self.context.arena_size // 2)
        rover_reach = max(1, min(12, global_reach))

        # Q=8 divides exactly into 2 / 3 / 2 / 1 callbacks per tick.
        # Declaration order is strategic: disrupt first, siege second, repair
        # late, and move/claim with the final slot.
        return [
            ProcessDeclaration(id="interceptor", reach=global_reach, share=0.250),
            ProcessDeclaration(id="siege", reach=global_reach, share=0.375),
            ProcessDeclaration(id="sentinel", reach=global_reach, share=0.250),
            ProcessDeclaration(id="rover", reach=rover_reach, share=0.125),
        ]

    def act(self, observation: ObservationV2) -> AgentAction:
        self._update_enemy_core_hypothesis(observation)

        if observation.self_process_id == "interceptor":
            return self._act_interceptor(observation)
        if observation.self_process_id == "siege":
            return self._act_siege(observation)
        if observation.self_process_id == "sentinel":
            return self._act_sentinel(observation)
        if observation.self_process_id == "rover":
            return self._act_rover(observation)

        # Declarations are fixed, so this is defensive only.  MOVE 0 remains a
        # valid API-v2 action if a future loader somehow supplies an unknown ID.
        return AgentAction(kind=ActionKindV2.MOVE, operand=0)

    # ------------------------------------------------------------------
    # Role behavior
    # ------------------------------------------------------------------

    def _act_interceptor(self, obs: ObservationV2) -> AgentAction:
        """Disrupt distinct visible enemy anchors as early as possible."""
        if self.intercept_tick != obs.current_tick:
            self.intercept_tick = obs.current_tick
            self.intercepted_positions.clear()

        candidates = [
            address
            for address in obs.visible_enemy_anchor_addresses
            if address not in self.intercepted_positions
        ]
        if candidates:
            # Prioritize processes closest to our core: a nearby anchor can
            # directly threaten the core with even modest reach.
            target = min(
                candidates,
                key=lambda address: (
                    self._circular_distance(address, obs.own_core_base),
                    address,
                ),
            )
            self.intercepted_positions.add(target)
            return AgentAction(kind=ActionKindV2.WRITE, operand=target, value=0xA5)

        # If every currently visible anchor was already hit this tick, convert
        # spare interceptor quota into additional core-capture pressure.
        target = self._next_pressure_cell(obs)
        return AgentAction(kind=ActionKindV2.WRITE, operand=target, value=0xA5)

    def _act_siege(self, obs: ObservationV2) -> AgentAction:
        """Continuously cycle writes across the hypothesized enemy core."""
        base = self._enemy_core_target(obs)
        offset = self._SIEGE_OFFSETS[self.siege_index % len(self._SIEGE_OFFSETS)]
        self.siege_index += 1
        target = (base + offset) % self.context.arena_size
        return AgentAction(kind=ActionKindV2.WRITE, operand=target, value=0xE7)

    def _act_sentinel(self, obs: ObservationV2) -> AgentAction:
        """Rewrite two widely separated own-core cells late in each tick."""
        offset = self._GUARD_OFFSETS[self.guard_index % len(self._GUARD_OFFSETS)]
        self.guard_index += 1
        target = (obs.own_core_base + offset) % self.context.arena_size
        return AgentAction(kind=ActionKindV2.WRITE, operand=target, value=0xD3)

    def _act_rover(self, obs: ObservationV2) -> AgentAction:
        """Create persistent movement while opportunistically fighting locally."""
        local_targets = [
            address
            for address in obs.visible_enemy_anchor_addresses
            if self._circular_distance(address, obs.self_anchor) <= obs.self_reach
        ]
        if local_targets:
            target = min(
                local_targets,
                key=lambda address: (
                    self._circular_distance(address, obs.self_anchor),
                    address,
                ),
            )
            return AgentAction(kind=ActionKindV2.WRITE, operand=target, value=0x6B)

        # With one callback/tick, move on two of every three callbacks and
        # claim the current anchor on the third.  The odd, arena-aware stride
        # avoids getting trapped in a tiny divisor cycle on common arena sizes.
        if obs.current_tick % 3:
            return AgentAction(
                kind=ActionKindV2.MOVE,
                operand=self.rover_direction * self.rover_stride,
            )
        return AgentAction(kind=ActionKindV2.WRITE, operand=obs.self_anchor, value=0x6B)

    # ------------------------------------------------------------------
    # Shared strategy helpers
    # ------------------------------------------------------------------

    def _update_enemy_core_hypothesis(self, obs: ObservationV2) -> None:
        if self.enemy_core_base is not None:
            return

        arena = self.context.arena_size
        opposite = (obs.own_core_base + arena // 2) % arena

        # v4 alpha1's default two-entrant placement puts the opposing core
        # opposite our own.  Long reach normally exposes its initial process
        # anchor as well.  Prefer the visible anchor nearest that expected
        # location, but keep the exact opposite as a robust pairwise fallback
        # if the opponent moved before our first callback.
        if obs.visible_enemy_anchor_addresses:
            visible = min(
                obs.visible_enemy_anchor_addresses,
                key=lambda address: (
                    self._circular_distance(address, opposite),
                    address,
                ),
            )
            if self._circular_distance(visible, opposite) <= 8:
                self.enemy_core_base = visible
                return

        self.enemy_core_base = opposite

    def _enemy_core_target(self, obs: ObservationV2) -> int:
        if self.enemy_core_base is not None:
            return self.enemy_core_base

        # This should only be reachable during unusual lifecycle use, but keep
        # a deterministic target rather than emitting an invalid/no-op action.
        if obs.visible_enemy_anchor_addresses:
            return obs.visible_enemy_anchor_addresses[0]
        return (obs.own_core_base + self.context.arena_size // 2) % self.context.arena_size

    def _next_pressure_cell(self, obs: ObservationV2) -> int:
        base = self._enemy_core_target(obs)
        offset = self._PRESSURE_OFFSETS[self.pressure_index % len(self._PRESSURE_OFFSETS)]
        self.pressure_index += 1
        return (base + offset) % self.context.arena_size

    def _circular_distance(self, a: int, b: int) -> int:
        arena = self.context.arena_size
        distance = abs(a - b) % arena
        return min(distance, arena - distance)

    @staticmethod
    def _choose_rover_stride(arena_size: int) -> int:
        # Runtime clamps movement to +/-64. Prefer a large odd stride coprime
        # with the arena so repeated moves explore many distinct anchors.
        ceiling = min(63, max(1, arena_size - 1))
        for stride in range(ceiling, 0, -1):
            if stride % 2 and math.gcd(stride, arena_size) == 1:
                return stride
        return 1


def create_agent():
    return HydraAgent()
