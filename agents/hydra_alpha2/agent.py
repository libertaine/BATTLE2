"""Hydra Alpha2 -- a search-capable Hydra derivative for bytefray-rules-4-alpha2.

A separate agent from ``hydra``, not an upgrade of it. Historical Hydra is a
frozen control for the v4 alpha1 ecology and its source is unchanged; this
agent exists to answer the Phase 5 question historical Hydra cannot:

    can an agent that actually acquires its target through the Agent API v2
    observation contract, instead of computing it from alpha1's placement
    rule, still play Hydra's game under alpha2?

The only strategic difference is target acquisition. Historical Hydra derives
the opposing core as ``own_core_base + arena_size // 2`` and only accepts a
visible enemy anchor when it already sits within 8 cells of that prediction
(``agents/hydra/agent.py``'s ``_update_enemy_core_hypothesis``) -- which under
alpha2's seed-derived placement is a filter that rejects the truth in favour
of a guess. This agent never computes that expression at all. It acquires
targets two ways, both entirely within the published API v2 contract:

* **passively**, from ``visible_enemy_anchor_addresses``, which the Ruleset
  already reports for every enemy process within reach of any of our own
  eligible processes; and
* **actively**, by spending quota on ``READ`` and inspecting
  ``previous_read_owner`` -- a genuine, costly search that works even when
  nothing is visible, because a cell an enemy owns is evidence of where that
  enemy lives.

Roles, shares, reach declarations, and the offset cycles are deliberately
carried over from historical Hydra unchanged, so a paired alpha1/alpha2
comparison isolates acquisition rather than measuring a general redesign.

Uses no research-only introspection, no engine internals, no MatchRequest
metadata, and no replay access: every input is a field of ``ObservationV2``
or ``MatchContextV2``.
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


class HydraAlpha2Agent:
    """Four-role API-v2 agent that finds its target instead of assuming it."""

    _SIEGE_OFFSETS = (0, 7, 3, 4, 1, 6, 2, 5)
    _GUARD_OFFSETS = (0, 7, 4, 3, 1, 6, 5, 2)

    #: How far either side of a confirmed enemy address the siege pattern
    #: sweeps. An enemy core is ``own_core_size`` cells wide and a sighting
    #: may land anywhere inside it, so covering +/- 7 cells guarantees the
    #: whole core is hit without ever needing to locate its exact base.
    _SIEGE_SPAN = 7

    def reset(self, context: MatchContextV2) -> None:
        self.context = context
        self.arena = context.arena_size

        # Target knowledge, shared across process callbacks. API v2 gives
        # every process the same agent object, so this is deliberate
        # coordination between our own processes, not hidden engine state.
        self.target: int | None = None
        self.target_confirmed = False

        self.siege_index = 0
        self.guard_index = 0

        # Search state: a deterministic stride sweep of the arena, used only
        # while no target is known.
        self.search_step = 0
        self.search_stride = self._coprime_stride(self.arena)
        self.pending_probe: int | None = None

        self.intercept_tick = -1
        self.intercepted: list[int] = []

        self.rover_direction = -1 if context.rng.randrange(2) else 1
        self.rover_stride = self._coprime_stride(self.arena)

    def declare_processes(self) -> list[ProcessDeclaration]:
        # Identical to historical Hydra's declaration: same four roles, same
        # shares, same reach. Alpha2 changes how the target is found, not what
        # the agent is made of.
        global_reach = max(1, self.arena // 2)
        rover_reach = max(1, min(12, global_reach))
        return [
            ProcessDeclaration(id="interceptor", reach=global_reach, share=0.250),
            ProcessDeclaration(id="siege", reach=global_reach, share=0.375),
            ProcessDeclaration(id="sentinel", reach=global_reach, share=0.250),
            ProcessDeclaration(id="rover", reach=rover_reach, share=0.125),
        ]

    def act(self, observation: ObservationV2) -> AgentAction:
        self._absorb_sighting(observation)
        self._absorb_probe_result(observation)

        if observation.self_process_id == "interceptor":
            return self._act_interceptor(observation)
        if observation.self_process_id == "siege":
            return self._act_siege(observation)
        if observation.self_process_id == "sentinel":
            return self._act_sentinel(observation)
        if observation.self_process_id == "rover":
            return self._act_rover(observation)
        return AgentAction(kind=ActionKindV2.MOVE, operand=0)

    # ------------------------------------------------------------------
    # Target acquisition -- the whole of the alpha2 adaptation
    # ------------------------------------------------------------------

    def _absorb_sighting(self, obs: ObservationV2) -> None:
        """Take the target straight from the visibility contract when offered.

        A sighting always wins over a search probe: an enemy *process anchor*
        is a live position, while an enemy-owned *cell* is only a trace it
        left behind. Sightings are sorted before being reduced so the choice
        cannot depend on tuple ordering the engine does not promise.
        """

        if not obs.visible_enemy_anchor_addresses:
            return
        nearest = min(
            sorted(obs.visible_enemy_anchor_addresses),
            key=lambda address: (self._distance(address, obs.own_core_base), address),
        )
        self.target = nearest
        self.target_confirmed = True

    def _absorb_probe_result(self, obs: ObservationV2) -> None:
        """Turn the previous READ into knowledge, if it found enemy ground.

        ``previous_read_owner`` is ``None`` for unclaimed memory and our own
        agent id for ground we hold; anything else is an entrant we are not,
        and the address it was read at is somewhere that entrant has been.
        That is weaker evidence than a live sighting, so it never overwrites a
        confirmed one.
        """

        if self.pending_probe is None:
            return
        probed, self.pending_probe = self.pending_probe, None
        if self.target_confirmed or not obs.previous_action_applied:
            return
        owner = obs.previous_read_owner
        if owner is not None and owner != self.context.agent_id:
            self.target = probed

    def _next_probe(self, obs: ObservationV2) -> int:
        """The next address in the deterministic search sweep.

        Anchored at our own core and advanced by a stride coprime with the
        arena, so repeated probes visit every address exactly once before
        repeating rather than cycling through a small divisor orbit.
        """

        self.search_step += 1
        return (obs.own_core_base + self.search_step * self.search_stride) % self.arena

    def _search_action(self, obs: ObservationV2) -> AgentAction:
        probe = self._next_probe(obs)
        self.pending_probe = probe
        return AgentAction(kind=ActionKindV2.READ, operand=probe)

    def _siege_cell(self) -> int:
        """The next cell of the sweep across the known enemy position."""

        assert self.target is not None
        step = self.siege_index % (2 * self._SIEGE_SPAN + 1)
        self.siege_index += 1
        return (self.target - self._SIEGE_SPAN + step) % self.arena

    # ------------------------------------------------------------------
    # Role behaviour
    # ------------------------------------------------------------------

    def _act_interceptor(self, obs: ObservationV2) -> AgentAction:
        """Disrupt distinct visible enemy anchors, then add core pressure."""

        if self.intercept_tick != obs.current_tick:
            self.intercept_tick = obs.current_tick
            self.intercepted = []

        candidates = [
            address
            for address in sorted(obs.visible_enemy_anchor_addresses)
            if address not in self.intercepted
        ]
        if candidates:
            target = min(
                candidates,
                key=lambda address: (
                    self._distance(address, obs.own_core_base),
                    address,
                ),
            )
            self.intercepted.append(target)
            return AgentAction(kind=ActionKindV2.WRITE, operand=target, value=0xA5)

        if self.target is None:
            return self._search_action(obs)
        return AgentAction(kind=ActionKindV2.WRITE, operand=self._siege_cell(), value=0xA5)

    def _act_siege(self, obs: ObservationV2) -> AgentAction:
        """Pound the known enemy position, or spend the slot looking for one.

        This is the concrete behavioural difference from historical Hydra: a
        siege slot with no target is a *search* slot, not a write into a
        guessed address that alpha2 makes wrong.
        """

        if self.target is None:
            return self._search_action(obs)
        return AgentAction(kind=ActionKindV2.WRITE, operand=self._siege_cell(), value=0xE7)

    def _act_sentinel(self, obs: ObservationV2) -> AgentAction:
        """Rewrite widely separated own-core cells, unchanged from Hydra."""

        offset = self._GUARD_OFFSETS[self.guard_index % len(self._GUARD_OFFSETS)]
        self.guard_index += 1
        return AgentAction(
            kind=ActionKindV2.WRITE,
            operand=(obs.own_core_base + offset) % self.arena,
            value=0xD3,
        )

    def _act_rover(self, obs: ObservationV2) -> AgentAction:
        """Keep moving, fight what comes into local reach, unchanged from Hydra."""

        local = [
            address
            for address in sorted(obs.visible_enemy_anchor_addresses)
            if self._distance(address, obs.self_anchor) <= obs.self_reach
        ]
        if local:
            target = min(
                local,
                key=lambda address: (self._distance(address, obs.self_anchor), address),
            )
            return AgentAction(kind=ActionKindV2.WRITE, operand=target, value=0x6B)
        if obs.current_tick % 3:
            return AgentAction(
                kind=ActionKindV2.MOVE,
                operand=self.rover_direction * self.rover_stride,
            )
        return AgentAction(kind=ActionKindV2.WRITE, operand=obs.self_anchor, value=0x6B)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _distance(self, a: int, b: int) -> int:
        delta = abs(a - b) % self.arena
        return min(delta, self.arena - delta)

    @staticmethod
    def _coprime_stride(arena_size: int) -> int:
        """The largest odd stride under the engine's move clamp coprime with
        the arena, so a sweep or a walk covers every address before repeating."""

        ceiling = min(63, max(1, arena_size - 1))
        for stride in range(ceiling, 0, -1):
            if stride % 2 and math.gcd(stride, arena_size) == 1:
                return stride
        return 1


def create_agent():
    return HydraAlpha2Agent()
