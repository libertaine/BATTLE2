"""Hunter -- an aggressor that hunts for contested ground and seizes it.

Strategy:
Hunter's default action is a blind write along its own fixed-stride sweep
-- the same throughput-efficient default Claimer uses, and for the same
reason: a first-time write is never wasted in this scoring model, so
there's nothing to gain checking a cell before claiming it (see Claimer's
docstring). What makes Hunter an aggressor rather than a plain sweeper is
that occasionally, instead of writing, it reads the next cell to sample
whether it's already contested -- and whenever one turns out to be
neither blank nor its own claim byte (the only signal available --
Observation exposes no ownership map, only raw byte values), it stops
sweeping and spends a short burst of writes seizing that spot and the
cells immediately after it, on the theory that ground an opponent
bothered to take is worth taking back.

An earlier version of this agent read every single cell it revisited
after an initial blind phase, rather than only occasionally -- that traded
away enough throughput that it lost consistently even against agents doing
comparatively little else right, the same lesson Strider and Adaptive both
ran into (see their docstrings). Sampling only a small fraction of the
time keeps Hunter close to Claimer's raw coverage speed while still
reacting to what it finds.

Hunter starts its sweep a third of the way into the arena rather than at
address 0, so its sweep covers different ground than Claimer's and
Strider's early on, instead of retracing the exact same cells in the exact
same order.

Important state this agent tracks:
- `signature`: this agent's own claim byte, used both to write and to
  recognize "that's already mine, not worth a burst."
- `cursor` / `stride`: the sweep position and step, like Claimer's.
- `_scanned_addr`: which address a pending READ result belongs to (see
  Strider's docstring for why this bookkeeping is necessary).
- `_burst_remaining` / `_burst_addr`: how many more burst writes are left
  and where the next one goes, once a target has been found.

What you might reasonably change:
- `SCAN_PROBABILITY`: how often a call samples instead of claiming
  outright.
- `BURST_LENGTH`: a longer burst denies more ground around a find but
  spends more of the tick budget not scanning; a shorter one returns to
  hunting faster.
- The trigger condition (`value not in (0, self.signature)`) treats every
  non-blank, non-own byte as worth attacking. A pickier version could
  require the same foreign byte to show up more than once before
  committing a burst, at the cost of reacting more slowly.
"""

from battle_engine.agent_api import ActionKind, AgentAction, MatchContext, Observation

SCAN_PROBABILITY = 0.1
BURST_LENGTH = 4


class HunterAgent:
    def reset(self, context: MatchContext) -> None:
        self.rng = context.rng
        self.arena_size = context.arena_size
        self.signature = 0xE3
        self.stride = 173
        self.cursor = context.arena_size // 3
        self._scanned_addr: int | None = None
        self._burst_remaining = 0
        self._burst_addr = 0

    def act(self, observation: Observation) -> AgentAction:
        if self._burst_remaining > 0:
            address = self._burst_addr
            self._burst_addr = (self._burst_addr + 1) % self.arena_size
            self._burst_remaining -= 1
            return AgentAction(ActionKind.WRITE, address, self.signature)

        if self._scanned_addr is not None:
            address = self._scanned_addr
            self._scanned_addr = None
            value = observation.last_read
            if value != 0 and value != self.signature:
                # Found contested ground: seize it now, then keep seizing
                # the next couple of cells before returning to the sweep.
                self._burst_remaining = BURST_LENGTH - 1
                self._burst_addr = (address + 1) % self.arena_size
                return AgentAction(ActionKind.WRITE, address, self.signature)

        address = self.cursor
        self.cursor = (self.cursor + self.stride) % self.arena_size
        if self.rng.random() < SCAN_PROBABILITY:
            self._scanned_addr = address
            return AgentAction(ActionKind.READ, address)
        return AgentAction(ActionKind.WRITE, address, self.signature)


def create_agent() -> HunterAgent:
    return HunterAgent()
