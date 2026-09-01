"""Annotated starting point for a Bytefray Agent API v2 process agent.

Unlike the blank v2 template, this one is deliberately commented to
explain the concepts an Agent API v2 strategy needs -- declaring
processes, what reach and share mean, and how an action is chosen -- right
where you would use them. It is not tied to any bundled agent; treat it as
a starting point to replace, not as a strategy worth keeping.

Agent API v2 differs from v1 in one structural way: an agent is not a
single actor stepping once per tick. It declares one or more *processes*,
each occupying its own position in the arena, and the engine schedules
their actions. ``act`` is called for one process at a time, and the
observation says which.
"""

from battle_engine.agent_api import (
    ActionKindV2,
    AgentAction,
    MatchContextV2,
    ObservationV2,
    ProcessDeclaration,
)


class Agent:
    def reset(self, context: MatchContextV2) -> None:
        # Called once before tick 0. context carries this match's fixed
        # facts: your own deterministic RNG stream (context.rng -- shared
        # with no other entrant), the arena size, and the tick limit.
        self.rng = context.rng
        self.arena_size = context.arena_size
        self.signature = 0xA5
        # This agent alternates claiming the cell it stands on with moving
        # somewhere new, so it needs to remember which comes next.
        self.claimed_here = False

    def declare_processes(self) -> list[ProcessDeclaration]:
        # Called once after reset, before the match starts.
        #
        # reach:  how far from its own position a process may READ or WRITE.
        #         Must be at least 1 and less than the arena size. A small
        #         reach is cheap and local; a larger one sees more ground.
        # share:  this process's slice of the agent's per-tick action
        #         budget. Shares across all declared processes must total
        #         1.0, so a single process always declares 1.0.
        #
        # Declaring more than one process splits the same budget rather
        # than adding to it -- two processes at 0.5 each act half as often
        # apiece, in exchange for holding two places in the arena at once.
        return [ProcessDeclaration(id="main", reach=1, share=1.0)]

    def act(self, observation: ObservationV2) -> AgentAction:
        # Called once per scheduled action, for one process at a time, and
        # must return exactly one AgentAction.
        #
        # Useful fields on the observation:
        #   self_process_id  which of your processes is acting right now
        #   self_anchor      that process's current position in the arena
        #   self_reach       the reach it was declared with
        #   previous_read_value / previous_read_owner
        #                    what your last READ returned, and whose cell it
        #                    was (None until this process has read something)
        #
        # Actions are WRITE (claim a cell), READ (inspect one), and MOVE
        # (reposition this process). operand is the target address for
        # READ/WRITE and the distance to travel for MOVE; addresses wrap
        # around the arena, so arithmetic never needs a bounds check.
        if not self.claimed_here:
            self.claimed_here = True
            return AgentAction(
                kind=ActionKindV2.WRITE,
                operand=observation.self_anchor,
                value=self.signature,
            )

        # Move on by exactly this process's reach, so the ground it can
        # touch next does not overlap what it just claimed.
        self.claimed_here = False
        return AgentAction(kind=ActionKindV2.MOVE, operand=observation.self_reach)


def create_agent() -> Agent:
    return Agent()
