"""Sentinel -- spends part of its budget keeping its own core secured.

Provenance: derived for product use from the frozen Core Defender research
agent (``battle_engine/data/reference_agents/core_defender``). This starter
is independently maintained and is not that benchmark artifact -- it has
its own identity and its own signature byte, and may change without any
effect on the frozen v2 benchmark population.

Strategy:
Under Ruleset v2 (``bytefray-rules-2``) every entrant owns a fixed,
``DEFENDED_RADIUS``-cell core region, and an entrant that loses its core to
someone else is eliminated on the spot. Claimer, Strider, Hunter and the
other expansion starters simply ignore that -- they spend every single
action claiming new ground and never look back at the cells they must keep
to stay alive. Sentinel makes the opposite bet, explicitly and visibly:

    one action in every ``REFRESH_EVERY`` re-writes one cell of its own
    core, cycling through all ``DEFENDED_RADIUS`` of them in order; the
    other three claim new ground like any ordinary sweeper.

That is the entire idea, and the point of the agent is that the trade is
easy to see and easy to price. Roughly a quarter of Sentinel's
territory-claiming throughput is spent on maintenance instead of growth --
so it will usually finish with less territory than Claimer or Hunter. What
it buys is that its core is never left untouched long enough for an
opponent's ordinary sweep, or Raider's deliberate assault, to finish
overwriting it. Run ``bytefray agents test sentinel --opponent raider``
and then ``--opponent claimer`` to see both sides of that bargain in one
sitting.

Its expansion sweep deliberately starts just past its own defended region
rather than at address 0, so the cells it is protecting and the cells it is
claiming never fight each other for the same ground.

Note that Sentinel never issues a single ``READ``. It has no way to know
whether its core has actually been attacked -- its "defense" is a timer,
not a response. That is a real limitation and a good exercise: a reactive
version would spend its patrol actions reading its own core cells and only
repair when a byte comes back changed. Bytefray's own research found that
the reactive version does not reliably beat this simpler blind timer, so
do not assume the more complicated design is automatically better --
measure it with ``bytefray agents evaluate``.

Important Agent API behavior this agent demonstrates:
``observation.pc``, read on the very first ``act()`` call before this agent
has ever issued a ``JUMP``, is exactly this entrant's own spawn address --
which is also where its own core sits. Capturing it once (rather than
hard-coding an address) is what lets the same source work correctly under
whatever start placement a given match assigns. ``DEFENDED_RADIUS`` mirrors
the Ruleset's own fixed core size: that is public knowledge about the
rules, like knowing the arena wraps, not privileged information about any
opponent.

Important state this agent tracks:
- ``signature``: this agent's own claim byte, written both to its core and
  to the ground it claims.
- ``core_start``: its own core anchor, captured once from
  ``observation.pc``.
- ``defend_index``: which of the ``DEFENDED_RADIUS`` core cells to refresh
  next; cycles.
- ``expand_cursor``/``expand_stride``: an ordinary outward sweep, seeded to
  begin right after the defended region.
- ``actions_taken``: the only clock it needs to decide, each call, whether
  this is a defend turn or an expand turn.

What you might reasonably change:
- ``REFRESH_EVERY``: a smaller value defends harder at a higher cost in
  lost ground; a larger value converges on plain Claimer behavior. This is
  the single dial that makes the whole trade-off visible -- try 2, 4 and 8
  against the same opponent and seed.

Not a claim of optimal strategy. Bytefray's own analysis found that
defense pays a real, unavoidable action-opportunity cost while the benefit
it generates -- attacks that fail because the core was refreshed in time --
earns the defender no score of its own. Sentinel is here to make that
trade-off concrete and measurable, not to win the most matches.
"""

from battle_engine.agent_api import ActionKind, AgentAction, MatchContext, Observation

DEFENDED_RADIUS = 8  # public Ruleset knowledge: a vulnerable core is 8 contiguous cells
REFRESH_EVERY = 4  # 1 action in every 4 defends; the other 3 expand


class SentinelAgent:
    def reset(self, context: MatchContext) -> None:
        self.rng = context.rng  # unused by this strategy, but always available
        self.arena_size = context.arena_size
        self.signature = 0x5D
        self.core_start: int | None = None
        self.defend_index = 0
        self.expand_stride = 139
        self.expand_cursor = 0
        self.actions_taken = 0

    def act(self, observation: Observation) -> AgentAction:
        if self.core_start is None:
            # First call, before this agent has ever moved its own pc:
            # observation.pc is exactly this entrant's spawn address, which
            # is also where its own core sits.
            self.core_start = observation.pc % self.arena_size
            self.expand_cursor = (self.core_start + DEFENDED_RADIUS) % self.arena_size

        self.actions_taken += 1
        if self.actions_taken % REFRESH_EVERY == 0:
            address = (self.core_start + self.defend_index) % self.arena_size
            self.defend_index = (self.defend_index + 1) % DEFENDED_RADIUS
            return AgentAction(ActionKind.WRITE, address, self.signature)

        address = self.expand_cursor
        self.expand_cursor = (self.expand_cursor + self.expand_stride) % self.arena_size
        return AgentAction(ActionKind.WRITE, address, self.signature)


def create_agent() -> SentinelAgent:
    return SentinelAgent()
