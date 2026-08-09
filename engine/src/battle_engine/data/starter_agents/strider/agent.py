"""Strider -- Claimer's sweep, plus one idea: defend early gains late.

Strategy:
For most of the match, Strider is Claimer with a different starting
point: the identical fixed-stride blind write sweep (see
claimer/agent.py), just starting on the opposite side of the arena (see
`cursor`'s initializer below for why). For the final stretch, it stops
advancing into new ground and instead replays the *first quarter* of that
same stride sequence again, re-writing those specific cells. The idea:
cells claimed early in
the match have had the whole rest of the match for an opponent's own
sweep to wander through and steal, so by the end they're the most likely
to be stale. A blind re-write costs nothing extra to justify (see
Claimer's docstring -- a write is never wasted in this scoring model,
whether the cell turns out to already be Strider's or not), so this is
pure upside if it reclaims anything and pure neutral if it doesn't.

This is the "improved" half of a two-agent progression with Claimer. Two
earlier versions of this agent tried to earn that improvement by reading
each cell before re-claiming it, on the theory that skipping already-owned
ground would let the saved actions reach further. Both lost consistently
in evaluation, including one version that ended up the single weakest
agent in the whole bundle. The lesson, confirmed repeatedly across several
agents in this bundle: reading costs a full action and a first-time write
is *never* wasted, so in this scoring model reading only pays for itself
once revisiting the same already-owned cell would otherwise be genuinely
common -- and within the tick budgets `bytefray agents test`/`evaluate`
actually use, blind coverage essentially never gets that far. Defending a
specific, likely-contested region blind, on a schedule, captures a real
tactical idea without paying that tax. See
`bytefray agents evaluate strider --baseline claimer --opponents
hunter,wanderer,adaptive --seeds 1,2,3,4,5` for a real comparison, and try
a held-out seed range too before trusting a small sample.

Important state this agent tracks:
- `signature`: the byte it writes everywhere.
- `cursor` / `stride`: the sweep position and step size (same stride as
  Claimer's, different starting point).
- `start_cursor`: where the sweep began -- the defend stretch replays
  this exact same stride sequence from here, so it revisits cells this
  agent actually claimed early rather than an unrelated fixed region.
- `defend_size`: how many steps of that early sequence get reinforced
  during the defend stretch -- fixed once at reset, from the arena size.
- `defend_steps`: position within that reinforcement loop.

What you might reasonably change:
- `DEFEND_AFTER_FRACTION`: how late the defend stretch starts (a smaller
  fraction spends more of the match defending, less expanding).
- `DEFEND_REGION_FRACTION`: how much of the earliest-claimed ground gets
  reinforced.
"""

from battle_engine.agent_api import ActionKind, AgentAction, MatchContext, Observation

DEFEND_AFTER_FRACTION = 0.85  # spend the final 15% of the match defending, not expanding
DEFEND_REGION_FRACTION = 4  # defend the first 1/DEFEND_REGION_FRACTION of the arena claimed


class StriderAgent:
    def reset(self, context: MatchContext) -> None:
        self.rng = context.rng
        self.arena_size = context.arena_size
        self.tick_limit = max(1, context.tick_limit)
        self.signature = 0xC2
        self.stride = 101
        # Start on the opposite side of the arena from Claimer's identical
        # stride -- otherwise the two sweeps stay in perfect lockstep for
        # most of the match (same stride, same cells, same order), and
        # whichever of the two ends up in the second-mover slot for a
        # given match wins every contested cell regardless of strategy.
        # Starting from a different point means their claims are offset
        # instead of identical, so the defend stretch actually matters.
        self.start_cursor = context.arena_size // 2
        self.cursor = self.start_cursor
        self.defend_size = max(1, context.arena_size // DEFEND_REGION_FRACTION)
        self.defend_steps = 0

    def act(self, observation: Observation) -> AgentAction:
        if observation.tick / self.tick_limit >= DEFEND_AFTER_FRACTION:
            step = self.defend_steps % self.defend_size
            self.defend_steps += 1
            address = (self.start_cursor + step * self.stride) % self.arena_size
            return AgentAction(ActionKind.WRITE, address, self.signature)

        address = self.cursor
        self.cursor = (self.cursor + self.stride) % self.arena_size
        return AgentAction(ActionKind.WRITE, address, self.signature)


def create_agent() -> StriderAgent:
    return StriderAgent()
