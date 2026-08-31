from battle_engine.agent_api import (
    ActionKindV2,
    AgentAction,
    MatchContextV2,
    ObservationV2,
    ProcessDeclaration,
)


class DefenderScoutAgent:
    def reset(self, context: MatchContextV2) -> None:
        self.context = context

    def declare_processes(self) -> list[ProcessDeclaration]:
        return [
            ProcessDeclaration(id="defender", reach=2, share=0.5),
            ProcessDeclaration(id="scout", reach=8, share=0.5),
        ]

    def act(self, observation: ObservationV2) -> AgentAction:
        if observation.self_process_id == "defender":
            if observation.visible_enemy_anchor_addresses:
                target = observation.visible_enemy_anchor_addresses[0]
                diff = self._shortest_delta(target, observation.self_anchor)
                if abs(diff) <= observation.self_reach:
                    return AgentAction(
                        kind=ActionKindV2.WRITE, operand=target, value=0xDD
                    )

            core_center = observation.own_core_base + observation.own_core_size // 2
            diff = self._shortest_delta(core_center, observation.self_anchor)
            if abs(diff) > 5:
                move_dist = min(abs(diff), observation.self_reach) * (
                    1 if diff > 0 else -1
                )
                return AgentAction(kind=ActionKindV2.MOVE, operand=move_dist)

            return AgentAction(
                kind=ActionKindV2.WRITE,
                operand=observation.self_anchor,
                value=0xDD,
            )

        if observation.visible_enemy_anchor_addresses:
            target = observation.visible_enemy_anchor_addresses[0]
            diff = self._shortest_delta(target, observation.self_anchor)
            if abs(diff) <= observation.self_reach:
                return AgentAction(kind=ActionKindV2.WRITE, operand=target, value=0x5C)

        return AgentAction(kind=ActionKindV2.MOVE, operand=observation.self_reach)

    def _shortest_delta(self, target: int, anchor: int) -> int:
        diff = target - anchor
        half = self.context.arena_size // 2
        if diff > half:
            diff -= self.context.arena_size
        elif diff < -half:
            diff += self.context.arena_size
        return diff


def create_agent():
    return DefenderScoutAgent()
