"""Core Defender -- a v2.0.0-alpha.1 "Vulnerable Core" reference agent.

Experimental/reference only, not a claim of optimal strategy -- see
docs/V2_0_ALPHA_ARCHITECTURE.md Sec 6 and docs/V2_0_ALPHA1_EVALUATION.md
for the research question this agent exists to probe: does defending a
fixed core region against ``bytefray-rules-2-alpha1``'s vulnerable-core
mechanic ever pay for itself against Ruleset v1's historically dominant
"never stop expanding" strategies (Claimer, Hunter, ...)?

Strategy:
Every fourth action refreshes one cell of this agent's own core region
(re-``WRITE``ing its own signature there, cycling through all
``DEFENDED_RADIUS`` cells in order) instead of expanding outward. The
other three of every four actions are an ordinary Claimer-style blind
sweep, starting just past the defended region rather than from address 0
so the defended cells and the expansion sweep never fight over the same
ground. This is a deliberate trade: roughly a quarter of this agent's
total territory-claiming throughput is spent maintaining ownership of a
small region instead of claiming new ground, in exchange for the region
never staying undefended long enough for an opponent's ordinary sweep to
fully overwrite it.

``DEFENDED_RADIUS`` is fixed at 8, matching ``bytefray-rules-2-alpha1``'s
own fixed ``CORE_SIZE`` (``battle_engine.python_runtime.CORE_SIZE``) --
this is public knowledge about the Ruleset's rules, exactly like knowing
the arena wraps or how scoring works, not privileged information about
any specific opponent or match. Nothing here reads the opponent's
position, identity, or core address; ``Observation`` exposes none of
that, so there would be nothing to read even if this agent wanted to.

Important state this agent tracks:
- ``core_start``: this agent's own core anchor, captured once from
  ``observation.pc`` on the very first ``act()`` call -- before any
  action (this agent never jumps) that Bytefray-controlled value is
  exactly the entrant's original spawn address (see
  ``python_runtime.PythonEntrantState.pc``'s construction). Captured
  rather than hardcoded so this agent works correctly under whatever
  start address a given match actually assigns it.
- ``defend_index``: which of the ``DEFENDED_RADIUS`` core cells to
  refresh next; cycles ``0 .. DEFENDED_RADIUS - 1``.
- ``expand_cursor``/``expand_stride``: an ordinary outward sweep, seeded
  to start right after this agent's own defended region.
- ``actions_taken``: the only clock needed to decide, each call, whether
  this is a "defend" or "expand" turn.

What you might reasonably change:
- ``REFRESH_EVERY``: a smaller value defends more aggressively at a
  higher expansion cost; a larger value is closer to pure Claimer.
"""

from battle_engine.agent_api import ActionKind, AgentAction, MatchContext, Observation

DEFENDED_RADIUS = 8  # mirrors bytefray-rules-2-alpha1's CORE_SIZE
REFRESH_EVERY = 4  # 1 action in every 4 defends; the other 3 expand


class CoreDefenderAgent:
    def reset(self, context: MatchContext) -> None:
        self.rng = context.rng  # unused by this strategy, but always available
        self.arena_size = context.arena_size
        self.signature = 0xD3
        self.core_start: int | None = None
        self.defend_index = 0
        self.expand_stride = 131
        self.expand_cursor = 0
        self.actions_taken = 0

    def act(self, observation: Observation) -> AgentAction:
        if self.core_start is None:
            # First call, before this agent has ever moved its own pc:
            # observation.pc is exactly this entrant's original spawn
            # address (see this module's docstring).
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


def create_agent() -> CoreDefenderAgent:
    return CoreDefenderAgent()
