"""Nemesis Alpha2 -- a search-capable Nemesis derivative for bytefray-rules-4-alpha2.

A separate agent from ``Nemesis``, not an upgrade of it. Historical Nemesis is
a frozen control for the v4 alpha1 ecology and its source is unchanged.

Historical Nemesis opens every callback with ``enemy_core = (own_core_base +
arena // 2) % arena`` (``agents/Nemesis/agent.py``) and aims its four
siege writes per tick -- half its entire quota -- at that address whether or
not it has ever seen the opponent. Under alpha2's seed-derived placement that
expression is wrong for essentially every seed, so those writes land on empty
memory for the whole match.

This agent keeps Nemesis's shape exactly -- three processes, the same
0.250/0.500/0.250 shares, the same global reach, the same core-offset visiting
orders -- and replaces only the assumption. It acquires targets from
``visible_enemy_anchor_addresses`` when the Ruleset offers them, and otherwise
spends siege quota on ``READ`` probes, reading ``previous_read_owner`` to tell
enemy ground from unclaimed memory. Both are ordinary Agent API v2
observations; nothing here touches engine internals, research seams, match
metadata, or replays.

Because it keeps historical Nemesis's structure, a paired alpha1/alpha2
comparison between the two isolates target acquisition rather than measuring a
different agent.
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


class NemesisAlpha2Agent:
    _SIEGE_OFFSETS = (0, 7, 3, 4, 1, 6, 2, 5)
    _GUARD_OFFSETS = (0, 7, 4, 3, 1, 6, 5, 2)

    #: Cells either side of a confirmed enemy address that siege sweeps. A
    #: sighting can land anywhere inside an 8-cell core, so +/- 7 covers the
    #: whole core without ever having to locate its base exactly.
    _SIEGE_SPAN = 7

    def reset(self, context: MatchContextV2) -> None:
        self.context = context
        self.arena = context.arena_size

        self.target: int | None = None
        self.target_confirmed = False

        self.siege_index = 0
        self.guard_step = 0

        self.search_step = 0
        self.search_stride = self._coprime_stride(self.arena)
        self.pending_probe: int | None = None

        self.last_tick = -1
        self.disrupted_anchors: list[int] = []

    def declare_processes(self) -> list[ProcessDeclaration]:
        global_reach = max(1, self.arena // 2)
        return [
            ProcessDeclaration(id="disruptor", reach=global_reach, share=0.250),
            ProcessDeclaration(id="siege", reach=global_reach, share=0.500),
            ProcessDeclaration(id="guardian", reach=global_reach, share=0.250),
        ]

    def act(self, observation: ObservationV2) -> AgentAction:
        if observation.current_tick != self.last_tick:
            self.last_tick = observation.current_tick
            self.disrupted_anchors = []

        self._absorb_sighting(observation)
        self._absorb_probe_result(observation)

        if observation.self_process_id == "disruptor":
            return self._act_disruptor(observation)
        if observation.self_process_id == "siege":
            return self._act_siege(observation)
        if observation.self_process_id == "guardian":
            return self._act_guardian(observation)
        return AgentAction(kind=ActionKindV2.MOVE, operand=0)

    # ------------------------------------------------------------------
    # Target acquisition
    # ------------------------------------------------------------------

    def _absorb_sighting(self, obs: ObservationV2) -> None:
        """A live enemy anchor is the best evidence available; take it."""

        if not obs.visible_enemy_anchor_addresses:
            return
        self.target = min(
            sorted(obs.visible_enemy_anchor_addresses),
            key=lambda address: (self._distance(address, obs.own_core_base), address),
        )
        self.target_confirmed = True

    def _absorb_probe_result(self, obs: ObservationV2) -> None:
        """Promote a READ that landed on enemy-owned memory into a target.

        Weaker evidence than a sighting -- a cell records where an entrant has
        *been*, not where it is -- so it never displaces a confirmed one.
        """

        if self.pending_probe is None:
            return
        probed, self.pending_probe = self.pending_probe, None
        if self.target_confirmed or not obs.previous_action_applied:
            return
        owner = obs.previous_read_owner
        if owner is not None and owner != self.context.agent_id:
            self.target = probed

    def _search_action(self, obs: ObservationV2) -> AgentAction:
        self.search_step += 1
        probe = (obs.own_core_base + self.search_step * self.search_stride) % self.arena
        self.pending_probe = probe
        return AgentAction(kind=ActionKindV2.READ, operand=probe)

    def _siege_cell(self) -> int:
        assert self.target is not None
        step = self.siege_index % (2 * self._SIEGE_SPAN + 1)
        self.siege_index += 1
        return (self.target - self._SIEGE_SPAN + step) % self.arena

    # ------------------------------------------------------------------
    # Role behaviour
    # ------------------------------------------------------------------

    def _act_disruptor(self, obs: ObservationV2) -> AgentAction:
        """Neutralise distinct visible anchors first, exactly as Nemesis does."""

        visible = [
            address
            for address in sorted(obs.visible_enemy_anchor_addresses)
            if address not in self.disrupted_anchors
        ]
        if visible:
            target = visible[0]
            self.disrupted_anchors.append(target)
            return AgentAction(kind=ActionKindV2.WRITE, operand=target, value=0xFF)
        if self.target is None:
            return self._search_action(obs)
        return AgentAction(kind=ActionKindV2.WRITE, operand=self._siege_cell(), value=0xDE)

    def _act_siege(self, obs: ObservationV2) -> AgentAction:
        """Half the entrant's quota: pressure a known target, or find one.

        Historical Nemesis spends these four slots per tick on a predicted
        address regardless of evidence. Spending them on search instead, while
        no target is known, is the entire adaptation.
        """

        if self.target is None:
            return self._search_action(obs)
        return AgentAction(kind=ActionKindV2.WRITE, operand=self._siege_cell(), value=0xDE)

    def _act_guardian(self, obs: ObservationV2) -> AgentAction:
        """Repair own core cells, unchanged from historical Nemesis."""

        offset = self._GUARD_OFFSETS[self.guard_step % len(self._GUARD_OFFSETS)]
        self.guard_step += 1
        return AgentAction(
            kind=ActionKindV2.WRITE,
            operand=(obs.own_core_base + offset) % self.arena,
            value=0x01,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _distance(self, a: int, b: int) -> int:
        delta = abs(a - b) % self.arena
        return min(delta, self.arena - delta)

    @staticmethod
    def _coprime_stride(arena_size: int) -> int:
        ceiling = min(63, max(1, arena_size - 1))
        for stride in range(ceiling, 0, -1):
            if stride % 2 and math.gcd(stride, arena_size) == 1:
                return stride
        return 1


def create_agent():
    return NemesisAlpha2Agent()
