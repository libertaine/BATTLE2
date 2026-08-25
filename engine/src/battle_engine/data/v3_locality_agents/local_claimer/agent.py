"""Local Claimer -- the bounded-locality port of ``claimer``.

EXPERIMENTAL. Runs only under ``bytefray-rules-3-alpha1``, the v3 research
Phase 2 bounded-locality Ruleset, which is not a stable Ruleset identity.
See docs/V3_PHASE2_LOCALITY_FEASIBILITY.md.

Lineage: ``claimer`` (starter, ``agent-revision_4b7b55c2ab0c...``), the
frozen Phase-0 benchmark population's blind-expansion archetype.

Strategy, unchanged in spirit: claim ground steadily and never stop to look
at what was there. No reading, no reacting to the opponent.

Changes required purely by locality, and nothing else:

* ``claimer`` swept the whole arena with a fixed absolute stride of 101,
  writing one cell per action wherever it liked. Under bounded locality an
  entrant can only write within ``R`` cells of its locus, so a sweep becomes
  fill-then-step: write the ``R`` cells at displacements ``0 .. R-1``, then
  ``MOVE`` forward exactly ``R``. That tiles the arena with no overlap and
  no gap, so coverage per *written* cell is identical to ``claimer``'s.
* The one genuinely new cost is the step itself: one action in every
  ``R + 1`` now buys movement rather than territory. That tax is the
  hypothesis under test, not something to engineer away.
* Stride 101 is gone. It has no meaning here -- a local sweep is contiguous
  by construction, so there is no stride to be coprime with anything.

No strategic redesign. This agent still cannot see, cannot react, and
cannot defend; what it now also cannot do is be in two places at once,
which is exactly the property Phase 2 exists to measure.
"""

from battle_engine.agent_api import ActionKind, AgentAction, MatchContext, Observation


class LocalClaimerAgent:
    def reset(self, context: MatchContext) -> None:
        self.rng = context.rng  # unused by this strategy, but always available
        self.arena_size = context.arena_size
        self.reach = context.locality_reach
        self.signature = 0xC1
        self.fill_offset = 0

    def act(self, observation: Observation) -> AgentAction:
        if self.reach is None or observation.locus is None:
            # Not a bounded-locality match. Emit a locality action anyway so
            # the runtime rejects it and this entrant forfeits visibly,
            # rather than silently behaving like some other agent.
            return AgentAction(ActionKind.MOVE, 0)

        if self.fill_offset >= self.reach:
            self.fill_offset = 0
            return AgentAction(ActionKind.MOVE, self.reach)

        offset = self.fill_offset
        self.fill_offset += 1
        return AgentAction(ActionKind.LOCAL_WRITE, offset, self.signature)


def create_agent() -> LocalClaimerAgent:
    return LocalClaimerAgent()
