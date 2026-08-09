"""Adaptive -- a hybrid that changes strategic mode as the match progresses.

Strategy:
Three phases, entered in order as the match clock advances, each a plain
blind-write sweep like Claimer (see claimer/agent.py for why blind writing
is the throughput-efficient default -- a first-time write is never
wasted, so there's nothing to gain by reading first):

    CLAIM   (first half)    -- sweep from address 0 with one stride.
    CONTEST (next 40%)      -- jump to a fresh region on the opposite side
                                of the arena and sweep it with a different
                                stride, so the second half of the match
                                claims new ground instead of only
                                re-touching CLAIM's territory.
    DEFEND  (final 10%)     -- stop advancing into new ground; spend every
                                action cycling back over a large core
                                region built up so far, so a late push
                                can't cheaply erase most of the match's
                                gains.

Two earlier versions of this agent spent CONTEST and DEFEND reading each
cell before deciding whether to (re-)claim it, on the theory that this
would let the budget concentrate on contested ground. In evaluation both
lost consistently and sometimes lost *ground* over time (see the module's
git history / CHANGELOG for the numbers) -- reading only pays for itself
once revisiting the same already-owned cell would otherwise be common,
and within the tick budgets `bytefray agents test`/`evaluate` actually use
that point is rarely reached (see Strider's docstring for the same
lesson). Pure blind writing every action, all match, is simply hard to
beat in this scoring model; Adaptive's real distinguishing idea is
*where* it points that blind writing over time, not whether it reads
first.

A demonstration of PC/JUMP as a real state machine:
This agent stores which phase it's in using the engine's own `pc` field
(`Observation.pc`), moved with `JUMP`, rather than a private Python
attribute. Whenever the match clock says it's time for a new phase, the
*next* action is a `JUMP` to that phase number instead of a sweep action
-- one action per tick spent on the transition itself. Every other agent
in this bundle just uses a plain Python attribute for state like this
instead, which persists for the whole match for free and never touches
the per-tick action budget -- prefer that for anything
performance-sensitive. This agent uses PC/JUMP specifically to show what
the alternative pattern looks like end to end.

Important state this agent tracks:
- `signature`: this agent's own claim byte.
- `claim_cursor` / `claim_stride`: CLAIM's sweep position and step.
- `contest_cursor` / `contest_stride`: CONTEST's independent sweep
  position (started on the opposite side of the arena) and step.
- `core_size`: how much of the arena DEFEND cycles back over -- computed
  from how far CLAIM and CONTEST actually got, not a fixed guess.
- Its current phase lives in the engine's `pc`, not in a Python attribute
  -- read via `observation.pc`, changed via `AgentAction(ActionKind.JUMP,
  ...)`.

What you might reasonably change:
- The phase boundaries (`0.5`, `0.9`) -- simple fixed fractions of the
  match, not reactions to how the match is actually going. A more
  sophisticated version could switch phases based on observed progress
  instead of a schedule.
- `CONTEST_START_FRACTION`: where CONTEST's independent sweep begins.
"""

from battle_engine.agent_api import ActionKind, AgentAction, MatchContext, Observation

PHASE_CLAIM = 0
PHASE_CONTEST = 1
PHASE_DEFEND = 2

CONTEST_START_FRACTION = 2  # CONTEST starts halfway around the arena from CLAIM


class AdaptiveAgent:
    def reset(self, context: MatchContext) -> None:
        self.rng = context.rng
        self.arena_size = context.arena_size
        self.tick_limit = max(1, context.tick_limit)
        self.signature = 0x99
        self.claim_stride = 131
        self.claim_cursor = 0
        self.contest_stride = 197
        self.contest_cursor = context.arena_size // CONTEST_START_FRACTION
        self.core_size = max(1, context.arena_size // 8)
        self.defend_cursor = 0

    def _phase_for(self, tick: int) -> int:
        progress = tick / self.tick_limit
        if progress < 0.5:
            return PHASE_CLAIM
        if progress < 0.9:
            return PHASE_CONTEST
        return PHASE_DEFEND

    def act(self, observation: Observation) -> AgentAction:
        target_phase = self._phase_for(observation.tick)
        if observation.pc != target_phase:
            if target_phase == PHASE_DEFEND and self.claim_cursor:
                # DEFEND reinforces everything CLAIM actually swept, not a
                # fixed guess -- claim_cursor is frozen at its final value
                # once CLAIM's phase ends, so it marks exactly how far
                # that sweep got.
                self.core_size = self.claim_cursor
            return AgentAction(ActionKind.JUMP, target_phase)

        if target_phase == PHASE_CLAIM:
            address = self.claim_cursor
            self.claim_cursor = (self.claim_cursor + self.claim_stride) % self.arena_size
            return AgentAction(ActionKind.WRITE, address, self.signature)

        if target_phase == PHASE_CONTEST:
            address = self.contest_cursor
            self.contest_cursor = (self.contest_cursor + self.contest_stride) % self.arena_size
            return AgentAction(ActionKind.WRITE, address, self.signature)

        # PHASE_DEFEND
        address = self.defend_cursor % self.core_size
        self.defend_cursor += 1
        return AgentAction(ActionKind.WRITE, address, self.signature)


def create_agent() -> AdaptiveAgent:
    return AdaptiveAgent()
