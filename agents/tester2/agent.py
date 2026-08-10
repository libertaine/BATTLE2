"""Starting point for a Bytefray Agent API v1 agent."""

from battle_engine.agent_api import ActionKind, AgentAction, MatchContext, Observation


class Agent:
    def reset(self, context: MatchContext) -> None:
        # Called once before tick 0. Save whatever state your strategy needs.
        self.rng = context.rng

    def act(self, observation: Observation) -> AgentAction:
        # Called once per tick; must return exactly one AgentAction.
        # Strategy goes here. This starting point writes a fixed byte to a
        # random address using the match's deterministic per-entrant RNG.
        address = self.rng.randrange(256)
        return AgentAction(ActionKind.WRITE, address, 0xA5)


def create_agent() -> Agent:
    return Agent()
