from battle_engine.agent_api import (
    ActionKindV2,
    AgentAction,
    MatchContextV2,
    ObservationV2,
    ProcessDeclaration,
)


class LocalDefenderAgent:
    def reset(self, context: MatchContextV2) -> None:
        self.context = context
        self.signature = 0xDD
        self.patrol_offset = 0

    def declare_processes(self) -> list[ProcessDeclaration]:
        return [ProcessDeclaration(id="defender", reach=2, share=1.0)]

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
                return AgentAction(kind=ActionKindV2.WRITE, operand=diff, value=self.signature)
        
        # Patrol around the core
        core_center = observation.own_core_base + observation.own_core_size // 2
        diff = core_center - observation.self_anchor
        half = self.context.arena_size // 2
        if diff > half:
            diff -= self.context.arena_size
        elif diff < -half:
            diff += self.context.arena_size
            
        if abs(diff) > 10:
            move_dist = min(abs(diff), observation.self_reach) * (1 if diff > 0 else -1)
            return AgentAction(kind=ActionKindV2.MOVE, operand=move_dist)
            
        self.patrol_offset = (self.patrol_offset + 1) % observation.self_reach
        return AgentAction(kind=ActionKindV2.WRITE, operand=self.patrol_offset, value=self.signature)

def create_agent():
    return LocalDefenderAgent()
