"""Claimer -- the simplest territorial strategy.

Strategy:
Sweep the whole arena with a fixed stride, writing a claim byte at every
cell visited, and never stop to look at what was there. No reading, no
reacting to the opponent -- just steady, blind coverage.

This is deliberately the "basic" half of a two-agent progression together
with Strider (see strider/agent.py), which adds one idea on top of this
exact sweep: read before you write, so you don't waste actions re-claiming
ground you already hold. Compare the two source files side by side, then
run `bytefray agents evaluate strider --baseline claimer --opponents
hunter,sentinel --seeds 1,2,3,4,5` to see whether that one idea actually
pays off.

Important state this agent tracks:
- `signature`: the byte it writes everywhere, so a later READ of one of
  its own cells is recognizable as "already mine" (see Strider).
- `cursor`: the next address to claim; advances by `stride` every tick.

What you might reasonably change:
- `stride`: a smaller stride claims a tighter region faster; a larger one
  spreads out sooner. Any odd stride stays coprime to the default
  power-of-two arena size, so a full sweep never repeats a cell early.
- The claim byte itself is arbitrary -- it only has to be memorable to you.
"""

from battle_engine.agent_api import ActionKind, AgentAction, MatchContext, Observation


class ClaimerAgent:
    def reset(self, context: MatchContext) -> None:
        self.rng = context.rng  # unused by this strategy, but always available
        self.arena_size = context.arena_size
        self.signature = 0xC1
        self.stride = 101
        self.cursor = 0

    def act(self, observation: Observation) -> AgentAction:
        address = self.cursor
        self.cursor = (self.cursor + self.stride) % self.arena_size
        return AgentAction(ActionKind.WRITE, address, self.signature)


def create_agent() -> ClaimerAgent:
    return ClaimerAgent()
