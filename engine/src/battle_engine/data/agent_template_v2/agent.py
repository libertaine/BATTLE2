"""Starting point for a Bytefray Agent API v2 process agent."""

from battle_engine.agent_api import (
    ActionKindV2,
    AgentAction,
    MatchContextV2,
    ObservationV2,
    ProcessDeclaration,
)


class Agent:
    def reset(self, context: MatchContextV2) -> None:
        # Called once before tick 0. Save whatever state your strategy needs.
        self.rng = context.rng
        self.signature = 0xA5

    def declare_processes(self) -> list[ProcessDeclaration]:
        # Called once after reset. Declares the processes this agent runs and
        # how its per-tick action budget is split between them; shares must
        # total 1.0. One process is the simplest thing that works.
        return [ProcessDeclaration(id="main", reach=1, share=1.0)]

    def act(self, observation: ObservationV2) -> AgentAction:
        # Called once per scheduled action; must return exactly one
        # AgentAction. Strategy goes here. This starting point claims the
        # cell the active process currently occupies.
        return AgentAction(
            kind=ActionKindV2.WRITE,
            operand=observation.self_anchor,
            value=self.signature,
        )


def create_agent() -> Agent:
    return Agent()
