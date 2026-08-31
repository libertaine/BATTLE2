from battle_engine.agent_api import (
    ActionKindV2,
    AgentAction,
    MatchContextV2,
    ObservationV2,
    ProcessDeclaration,
)


class ConcentratedAttackerAgent:
    def reset(self, context: MatchContextV2) -> None:
        self.context = context
        self.signature = 0xAA

    def declare_processes(self) -> list[ProcessDeclaration]:
        return [ProcessDeclaration(id="attacker", reach=4, share=1.0)]

    def act(self, observation: ObservationV2) -> AgentAction:
        if observation.visible_enemy_anchor_addresses:
            target = observation.visible_enemy_anchor_addresses[0]
            diff = target - observation.self_anchor
            half = self.context.arena_size // 2
            if diff > half:
                diff -= self.context.arena_size
            elif diff < -half:
                diff += self.context.arena_size

            if abs(diff) <= observation.self_reach:
                return AgentAction(
                    kind=ActionKindV2.WRITE,
                    operand=target,
                    value=self.signature,
                )
            move_dist = min(abs(diff), observation.self_reach) * (
                1 if diff > 0 else -1
            )
            return AgentAction(kind=ActionKindV2.MOVE, operand=move_dist)

        return AgentAction(kind=ActionKindV2.MOVE, operand=observation.self_reach)


def create_agent():
    return ConcentratedAttackerAgent()
