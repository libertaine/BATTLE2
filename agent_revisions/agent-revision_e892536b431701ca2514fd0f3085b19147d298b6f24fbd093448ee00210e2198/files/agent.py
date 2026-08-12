"""Hunter -- a disperser that stakes scattered claims before filling in.

Strategy, and why it changed:
An earlier version of this agent was a "scanner that bursts on contested
ground" -- the classic Redcode-bomber idea of aggression. It lost
consistently, for a structural reason specific to this engine, not a
tuning mistake: score accumulates *every tick* an entrant owns a cell
(``ScoringPolicy.score_territory``), Python agents never destroy each
other (``WRITE`` claims a cell, it never kills), and ``Observation``
exposes no ownership map -- so "scanning for enemies" is expensive (a
``READ`` that could have been a ``WRITE``) for no benefit worth the cost,
and "aggression" in the combat sense doesn't really exist here (see
Claimer's docstring for the underlying reasoning). A second attempt --
spreading sparse clusters across the arena with a large gap between them
-- also lost: the gaps between clusters never got revisited at all, so
most of the "spread out" range stayed permanently blank, which is worse
than just sweeping densely from the start.

What actually works: score is cumulative per tick, so being the first
entrant present in a given region is worth something even before that
region is fully claimed -- but only if "spread out" is followed by
"fill in," not left sparse forever. Hunter now does exactly that in two
phases: first, a short *sparse* pass using a stride chosen so that any
prefix of the sequence -- not just a full lap -- is evenly spread across
the whole arena (a golden-ratio step; see `sparse_stride` below), giving
it a scattered early presence in regions no single-origin sweep (like
Claimer's or Strider's, both starting at address 0) reaches for a long
time. Then it switches to an ordinary *dense* sweep with a different stride,
continuing from wherever the sparse phase's cursor happened to land
(deliberately *not* reset to address 0) -- an early version reset it,
which made the dense phase retrace Claimer's exact path and turned this
agent into "Claimer plus a free bonus," strictly better than Claimer with
no real tradeoff, in every single matchup. Continuing from the sparse
phase's landing point means the dense sweep covers a genuinely different
-- not superset -- portion of the arena within the match's time limit.
Both phases are pure blind writing, every action -- no reading, for the
same reason Claimer never reads (see its docstring). Watch a replay of
this agent: scattered points light up across the whole arena in the first
few ticks, then a solid region starts filling in from wherever that
scatter left off -- a visibly different pattern from every other bundled
agent's steady single-origin growth.

Important state this agent tracks:
- `signature`: this agent's own claim byte.
- `sparse_stride` / `dense_stride`: the two phases' step sizes.
- `cursor`: current sweep position, continuous across both phases.
- `actions_taken`: how many calls this agent has made -- the only clock
  it needs to know when to switch phases.

What you might reasonably change:
- `SPARSE_ACTIONS`: a longer sparse phase spreads wider before settling
  into dense coverage, at the cost of the dense phase starting later.
"""

from battle_engine.agent_api import ActionKind, AgentAction, MatchContext, Observation

SPARSE_ACTIONS = 20

# The golden ratio's fractional part has the property that every prefix of
# the sequence (n * GOLDEN_RATIO) mod 1 is low-discrepancy -- spread
# roughly evenly over [0, 1) no matter how short the prefix is. Scaled to
# the arena and rounded to an odd integer, the same property holds for
# addresses: even the first few dozen sparse-phase writes land in
# well-separated parts of the arena, not clustered near the start the way
# a small fixed stride would be early on.
GOLDEN_RATIO_CONJUGATE = 0.6180339887498949


class HunterAgent:
    def reset(self, context: MatchContext) -> None:
        self.rng = context.rng
        self.arena_size = context.arena_size
        self.signature = 0xE3
        self.sparse_stride = int(context.arena_size * GOLDEN_RATIO_CONJUGATE) | 1
        # Deliberately not the same stride Claimer/Strider use (101): two
        # entrants sweeping with an identical stride are really walking
        # the same cyclic sequence of addresses, just entered at
        # different points -- depending on the phase offset between them,
        # one can end up systematically trailing the other through nearly
        # every shared cell for the whole match (whoever arrives at a
        # given address *later* in wall-clock time wins it), which has
        # nothing to do with either strategy. A different stride makes
        # this a genuinely different sweep, not the same one offset.
        self.dense_stride = 173
        self.cursor = 0
        self.actions_taken = 0

    def act(self, observation: Observation) -> AgentAction:
        self.actions_taken += 1
        if self.actions_taken <= SPARSE_ACTIONS:
            address = self.cursor
            self.cursor = (self.cursor + self.sparse_stride) % self.arena_size
            return AgentAction(ActionKind.WRITE, address, self.signature)

        address = self.cursor
        self.cursor = (self.cursor + self.dense_stride) % self.arena_size
        return AgentAction(ActionKind.WRITE, address, self.signature)


def create_agent() -> HunterAgent:
    return HunterAgent()
