"""Local Camper -- the deliberately trivial locality control.

EXPERIMENTAL. Runs only under ``bytefray-rules-3-alpha1``, the v3 research
Phase 2 bounded-locality Ruleset, which is not a stable Ruleset identity.
See docs/V3_PHASE2_LOCALITY_FEASIBILITY.md.

Lineage: none. This agent has no Ruleset-v2 ancestor, and that is the
point -- it is a strategy that *only becomes expressible* once presence is
scarce, so it exists to detect two specific Phase 2 failure modes rather
than to compete:

* **Immediate defensive turtling.** If never moving at all is competitive,
  bounded locality has made position so expensive that the interesting
  strategies are dominated by refusing to use it. That is an ABANDON
  signal, and this agent is the cheapest way to see it.
* **Trivial dominance by a fixed policy.** If a single, thoughtless,
  observation-free policy wins across dissimilar rosters, criterion 5 has
  failed and the mechanic has produced a universal solution.

Strategy: never move. Rewrite every cell of the reachable window
(displacements ``-R .. +R``) forever, in order, starting from ``-R``. Its
own core sits at displacements ``0 .. 7`` from its starting locus, so the
cycle happens to re-sign the core roughly once per ``2R + 1`` actions --
incidental self-defense it never reasons about, which is precisely the sort
of accidental robustness a control should expose rather than hide.

It reads nothing, reacts to nothing, and can never threaten an opponent's
core, since it cannot reach one.
"""

from battle_engine.agent_api import ActionKind, AgentAction, MatchContext, Observation


class LocalCamperAgent:
    def reset(self, context: MatchContext) -> None:
        self.rng = context.rng  # unused by this strategy, but always available
        self.arena_size = context.arena_size
        self.reach = context.locality_reach
        self.signature = 0xCB
        self.offset = 0

    def act(self, observation: Observation) -> AgentAction:
        if self.reach is None or observation.locus is None:
            # See local_claimer/agent.py: forfeit visibly off-Ruleset.
            return AgentAction(ActionKind.MOVE, 0)

        offset = self.offset - self.reach
        self.offset += 1
        if self.offset > 2 * self.reach:
            self.offset = 0
        return AgentAction(ActionKind.LOCAL_WRITE, offset, self.signature)


def create_agent() -> LocalCamperAgent:
    return LocalCamperAgent()
