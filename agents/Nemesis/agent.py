"""Nemesis v3 (Juggernaut) -- True hard-counter to Hydra for Bytefray API v2."""

from __future__ import annotations

from battle_engine.agent_api import (
    ActionKindV2,
    AgentAction,
    MatchContextV2,
    ObservationV2,
    ProcessDeclaration,
)


class NemesisAgent:
    _SIEGE_OFFSETS = (0, 7, 3, 4, 1, 6, 2, 5)
    _GUARD_OFFSETS = (0, 7, 4, 3, 1, 6, 5, 2)

    def reset(self, context: MatchContextV2) -> None:
        self.context = context
        self.siege_step = 0
        self.guard_step = 0
        self.disrupted_anchors: set[int] = set()
        self.last_tick = -1

    def declare_processes(self) -> list[ProcessDeclaration]:
        global_reach = max(1, self.context.arena_size // 2)
        # Declaration order:
        # 1. disruptor (0.250 / 2 actions): Immediately strikes Hydra's anchors on callback 1
        # 2. siege     (0.500 / 4 actions): 4 sustained writes directly onto Hydra's core
        # 3. guardian  (0.250 / 2 actions): 2 late-tick defensive repairs on own core
        return [
            ProcessDeclaration(id="disruptor", reach=global_reach, share=0.250),
            ProcessDeclaration(id="siege", reach=global_reach, share=0.500),
            ProcessDeclaration(id="guardian", reach=global_reach, share=0.250),
        ]

    def act(self, observation: ObservationV2) -> AgentAction:
        arena = self.context.arena_size
        enemy_core = (observation.own_core_base + arena // 2) % arena

        if observation.current_tick != self.last_tick:
            self.last_tick = observation.current_tick
            self.disrupted_anchors.clear()

        # Slot 1: Preemptively neutralize Hydra's anchors before it can disrupt us
        if observation.self_process_id == "disruptor":
            visible = [
                addr
                for addr in observation.visible_enemy_anchor_addresses
                if addr not in self.disrupted_anchors
            ]
            if visible:
                target = visible[0]
                self.disrupted_anchors.add(target)
                return AgentAction(kind=ActionKindV2.WRITE, operand=target, value=0xFF)
            # Fallback to enemy core if no anchors are visible
            target = (enemy_core + self._SIEGE_OFFSETS[self.siege_step % 8]) % arena
            self.siege_step += 1
            return AgentAction(kind=ActionKindV2.WRITE, operand=target, value=0xDE)

        # Slot 2: 4 writes per tick pounding Hydra's core
        if observation.self_process_id == "siege":
            offset = self._SIEGE_OFFSETS[self.siege_step % 8]
            self.siege_step += 1
            target = (enemy_core + offset) % arena
            return AgentAction(kind=ActionKindV2.WRITE, operand=target, value=0xDE)

        # Slot 3: Repair home core cells
        if observation.self_process_id == "guardian":
            offset = self._GUARD_OFFSETS[self.guard_step % 8]
            self.guard_step += 1
            target = (observation.own_core_base + offset) % arena
            return AgentAction(kind=ActionKindV2.WRITE, operand=target, value=0x01)

        return AgentAction(kind=ActionKindV2.MOVE, operand=0)


def create_agent():
    return NemesisAgent()
