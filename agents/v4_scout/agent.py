from battle_engine.agent_api import (
    ActionKindV2,
    AgentAction,
    MatchContextV2,
    ObservationV2,
    ProcessDeclaration,
)


class ScoutAgent:
    def reset(self, context: MatchContextV2) -> None:
        self.context = context

    def declare_processes(self) -> list[ProcessDeclaration]:
        return [ProcessDeclaration(id="scout", reach=8, share=1.0)]

    def act(self, observation: ObservationV2) -> AgentAction:
        if observation.visible_enemy_anchor_addresses:
            target = observation.visible_enemy_anchor_addresses[0]
            diff = target - observation.self_anchor
            half = self.context.arena_size // 2
            if diff > half: diff -= self.context.arena_size
            elif diff < -half: diff += self.context.arena_size
            
            if abs(diff) <= observation.self_reach:
                return AgentAction(kind=ActionKindV2.WRITE, operand=diff, value=0x5C)
                
        return AgentAction(kind=ActionKindV2.MOVE, operand=observation.self_reach)

def create_agent():
    return ScoutAgent()
