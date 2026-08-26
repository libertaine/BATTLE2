"""Annotated starting point for a Bytefray Agent API v1 agent.

Unlike the blank template, this one is deliberately commented to explain
the concepts a first strategy usually needs -- reading before writing,
address wraparound, and the once-per-tick action budget -- right where
you would use them, without needing to leave the file. It is not tied to
any specific bundled agent; treat it as a starting point to replace, not
as a strategy worth keeping.
"""

from battle_engine.agent_api import ActionKind, AgentAction, MatchContext, Observation


class Agent:
    def reset(self, context: MatchContext) -> None:
        # Called once before tick 0. context carries this match's fixed
        # facts: your own deterministic RNG stream (context.rng -- shared
        # with no other entrant), the arena size, the tick limit, and your
        # per-tick action budget. Save whatever your strategy needs here.
        self.rng = context.rng
        self.arena_size = context.arena_size
        # A cursor this agent sweeps forward through the arena. Every
        # address the engine sees is taken modulo the arena size, so the
        # cursor can run past arena_size without any special-case code.
        self.cursor = self.rng.randrange(self.arena_size)
        self._waiting_on_read = False

    def act(self, observation: Observation) -> AgentAction:
        # Called once per tick; must return exactly one AgentAction. Only
        # one action happens per call -- there is no "read and write in
        # the same tick" -- so a strategy that wants to look before it
        # writes has to spread that decision across two calls, the way
        # this one does with self._waiting_on_read.
        if self._waiting_on_read:
            self._waiting_on_read = False
            # observation.last_read is the byte this agent's own most
            # recent READ returned (None only if it has never read
            # anything yet). This starting point claims the cell either
            # way; a less trivial strategy could branch on the value here.
            address = self.cursor
            self.cursor += 1
            return AgentAction(ActionKind.WRITE, address, 0xA5)

        self._waiting_on_read = True
        return AgentAction(ActionKind.READ, self.cursor)


def create_agent() -> Agent:
    return Agent()
