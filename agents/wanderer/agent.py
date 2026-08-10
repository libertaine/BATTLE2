"""Wanderer -- a wildcard whose sweep order is randomized per seed.

Strategy:
Claimer and Strider sweep with the same fixed, predictable stride every
match. Wanderer picks its own stride randomly at the start of each match
(from `context.rng`, so it's unpredictable to watch but reproducible for a
given seed) -- but always an *odd* one, which keeps it coprime with the
default power-of-two arena size, so it still reaches every cell exactly
once per full pass with no wasted revisits, exactly as efficient as
Claimer's fixed stride. The only difference is the order cells are
visited in, which looks scattered rather than evenly spaced. An earlier
version of this agent picked a fresh uniformly random *address* every
single action instead of following a stride at all -- that sounds more
"random" but is measurably worse: revisiting an already-claimed cell by
chance (the birthday paradox) wastes actions that a non-repeating stride
sweep never does, and it lost every match in evaluation against the
systematic sweepers in this bundle. Ground the arena game actually
rewards is *coverage*, not literal unpredictability -- Wanderer keeps the
unpredictable-looking movement while not paying for it in lost ground.

On top of the randomized sweep, Wanderer keeps one opportunistic habit:
it occasionally reads instead of writes, purely to check whether it has
wandered into a neighborhood worth exploiting, and when it has (a
non-blank, non-own byte turns up) it stops sweeping and spends a short
burst claiming that neighborhood before moving on.

Important state this agent tracks:
- `signature`: this agent's own claim byte.
- `stride` / `cursor`: the randomized sweep step and position.
- `_scanned_addr`: which address a pending READ result belongs to (see
  Strider's docstring for why this bookkeeping is necessary).
- `_exploit_remaining` / `_exploit_anchor`: how many more local writes are
  left in the current burst, and the neighborhood they're centered on.

What you might reasonably change:
- `SCAN_PROBABILITY`: how often a call samples instead of claiming
  outright.
- `LOCAL_BURST` / `LOCAL_SPREAD`: a bigger burst or wider spread exploits a
  lucky landing harder, at the cost of more ticks not sweeping elsewhere.
- This agent uses `context.rng` for every random choice, never Python's
  global `random` module -- that's what keeps its behavior reproducible
  for a given seed. Do the same in your own agents.
"""

from battle_engine.agent_api import ActionKind, AgentAction, MatchContext, Observation

SCAN_PROBABILITY = 0.03
LOCAL_BURST = 6
LOCAL_SPREAD = 16


class WandererAgent:
    def reset(self, context: MatchContext) -> None:
        self.rng = context.rng
        self.arena_size = context.arena_size
        self.signature = 0x2C
        # An odd stride stays coprime to the default power-of-two arena
        # size, so a full sweep still visits every cell once with no
        # repeats -- only the order is randomized, not the coverage.
        half = max(1, context.arena_size // 2)
        self.stride = 2 * self.rng.randrange(half) + 1
        self.cursor = self.rng.randrange(context.arena_size)
        self._scanned_addr: int | None = None
        self._exploit_remaining = 0
        self._exploit_anchor = 0

    def act(self, observation: Observation) -> AgentAction:
        if self._exploit_remaining > 0:
            self._exploit_remaining -= 1
            offset = self.rng.randrange(LOCAL_SPREAD)
            address = (self._exploit_anchor + offset) % self.arena_size
            return AgentAction(ActionKind.WRITE, address, self.signature)

        if self._scanned_addr is not None:
            address = self._scanned_addr
            self._scanned_addr = None
            value = observation.last_read
            if value != 0 and value != self.signature:
                self._exploit_remaining = LOCAL_BURST
                self._exploit_anchor = address
                return AgentAction(ActionKind.WRITE, address, self.signature)

        address = self.cursor
        self.cursor = (self.cursor + self.stride) % self.arena_size
        if self.rng.random() < SCAN_PROBABILITY:
            self._scanned_addr = address
            return AgentAction(ActionKind.READ, address)
        return AgentAction(ActionKind.WRITE, address, self.signature)


def create_agent() -> WandererAgent:
    return WandererAgent()
