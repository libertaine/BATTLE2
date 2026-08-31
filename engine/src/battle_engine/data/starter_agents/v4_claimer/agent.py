from battle_engine.agent_api import (
    ActionKindV2,
    AgentAction,
    MatchContextV2,
    ObservationV2,
    ProcessDeclaration,
)


class ClaimerAgent:
    def reset(self, context: MatchContextV2) -> None:
        self.context = context
        self.signature = 0xC1
        self.state = "move"

    def declare_processes(self) -> list[ProcessDeclaration]:
        return [ProcessDeclaration(id="claimer", reach=1, share=1.0)]

    def act(self, observation: ObservationV2) -> AgentAction:
        if self.state == "move":
            self.state = "write"
            return AgentAction(kind=ActionKindV2.MOVE, operand=observation.self_reach)
        self.state = "move"
        return AgentAction(
            kind=ActionKindV2.WRITE,
            operand=observation.self_anchor,
            value=self.signature,
        )


def create_agent():
    return ClaimerAgent()
