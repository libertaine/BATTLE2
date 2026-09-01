"""Local Hunter -- research probe, retained unchanged for Phase 5 (v4 alpha2).

Every line of behaviour below the docstring is byte-identical to the Phase 4
research branch's copy (``tools/v4_alpha2_research_agents/agents/local_hunter/
agent.py``, whole-file SHA-256
1f83dca9cdbe9868b8c6a2e20c59669669a093dec6ac78105086c9778858ac98) -- only
this docstring gained the Phase 5 preamble -- so its Phase 4 and Phase 5
results are directly comparable. It is
deliberately NOT promoted into the ``agents/`` catalogue or the bundled
starters: it is a mechanism probe, not a competitor.

Phase 5 keeps it for one specific measurement the alpha2 release decision
needs. Phase 4 discovered that a single-process pursuer which gets close
enough to detect a reactive opponent, but not close enough to win, can be
permanently disruption-locked with no way to disengage -- a disrupted
process cannot even issue a retreating MOVE. Local Hunter is the minimal
agent that reproduces that situation on demand, so the alpha2 ecology can
measure how often it actually happens rather than reasoning about it.

Phase 4's original purpose statement follows unchanged.

Purpose: test whether limited reach plus active, decisive movement can
produce viable pursuit/contact gameplay -- i.e. whether the roster's poor
showing under a reach cap (see the Phase 4 report's reach experiment) is
because these particular agents were written for global reach, or because
the game itself does not reward local strategies.

Not a competitive upgrade to any shipped starter -- deliberately as simple
as possible. Declares one process, reach 12 (within the 8-16 range the
governing task specifies), full share. When an enemy is visible: attacks
if in range, otherwise moves directly toward it (clipped to its own
reach) -- unlike the shipped `v4_scout`/`v4_defender_scout` starters,
which fall back to their fixed blind sweep even when a target is visible
but momentarily out of range. When no enemy is visible but one was
recently seen, continues moving toward that last-known position instead of
resuming a blind sweep. Never infers the opponent's core from its own
placement -- only from what `visible_enemy_anchor_addresses` actually
reports.
"""

from battle_engine.agent_api import (
    ActionKindV2,
    AgentAction,
    MatchContextV2,
    ObservationV2,
    ProcessDeclaration,
)

REACH = 12


class LocalHunterAgent:
    def reset(self, context: MatchContextV2) -> None:
        self.context = context
        self.last_seen: int | None = None

    def declare_processes(self) -> list[ProcessDeclaration]:
        return [ProcessDeclaration(id="hunter", reach=REACH, share=1.0)]

    def act(self, observation: ObservationV2) -> AgentAction:
        if observation.visible_enemy_anchor_addresses:
            target = observation.visible_enemy_anchor_addresses[0]
            self.last_seen = target
            return self._engage_or_close(observation, target)

        if self.last_seen is not None:
            diff = self._shortest_delta(self.last_seen, observation.self_anchor)
            if diff == 0:
                self.last_seen = None
            else:
                return AgentAction(kind=ActionKindV2.MOVE, operand=self._clip(diff, observation.self_reach))

        return AgentAction(kind=ActionKindV2.MOVE, operand=observation.self_reach)

    def _engage_or_close(self, observation: ObservationV2, target: int) -> AgentAction:
        diff = self._shortest_delta(target, observation.self_anchor)
        if abs(diff) <= observation.self_reach:
            return AgentAction(kind=ActionKindV2.WRITE, operand=target, value=0x4E)
        return AgentAction(kind=ActionKindV2.MOVE, operand=self._clip(diff, observation.self_reach))

    def _shortest_delta(self, target: int, anchor: int) -> int:
        diff = target - anchor
        half = self.context.arena_size // 2
        if diff > half:
            diff -= self.context.arena_size
        elif diff < -half:
            diff += self.context.arena_size
        return diff

    @staticmethod
    def _clip(value: int, limit: int) -> int:
        return max(-limit, min(value, limit))


def create_agent():
    return LocalHunterAgent()
