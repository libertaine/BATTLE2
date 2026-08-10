"""Adaptive -- a hybrid that changes strategic mode as the match progresses.

Strategy:
Three phases, entered in order as the match clock advances, each a plain
blind-write sweep like Claimer (see claimer/agent.py for why blind writing
is the throughput-efficient default -- a first-time write is never
wasted, so there's nothing to gain by reading first):

    CLAIM   (first half)    -- sweep from address 0 with one stride.
    CONTEST (next 40%)      -- jump to a fresh region on the opposite
                                side of the arena and sweep it with a
                                different stride, reaching ground CLAIM
                                hasn't gotten to yet instead of continuing
                                to fight over address 0.

An earlier version had CONTEST restart at address 0 too, on the theory
that recontesting the busy region other agents also start from would be
more valuable than claiming empty ground elsewhere. It measured
consistently worse: address 0 is where a candidate's opponent in
`bytefray agents evaluate` is also usually sweeping from, and that
opponent's writes land *after* this agent's within every tick (Python
entrants execute in fixed slot order -- the evaluated subject first, the
opponent second; see `AGENT_API_V1.md`'s scheduling notes), so it
continuously wins any cell both of them touch. Moving to fresh ground
avoids fighting a fight this agent structurally can't win and reliably
grew its total territory instead.
    DEFEND  (final 10%)     -- stop advancing into new ground; spend every
                                action replaying CLAIM's and CONTEST's
                                sequences alternately (the same stride
                                arithmetic, restarted from each phase's
                                own beginning), so a late push can't
                                cheaply erase either phase's gains. An
                                opponent that never stops expanding (see
                                Claimer) will keep passing through --
                                and, as this evaluation candidate's
                                structurally later-scheduled opponent,
                                keep winning -- cells this agent claimed
                                early and then stopped actively
                                defending; replaying both phases' actual
                                sequences, not an unrelated fixed range,
                                is what makes DEFEND worth the ground it
                                gives up by no longer expanding.

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
- `contest_cursor` / `contest_stride`: CONTEST's independent sweep,
  started on the opposite side of the arena from CLAIM with a different
  stride.
- `claim_actions` / `contest_actions`: how many writes each phase
  actually made -- since both strides are coprime with the arena size,
  these are exactly how many distinct cells each phase covered (no
  repeats within one pass). DEFEND uses them as loop bounds when
  replaying each sequence. An earlier version used the raw (wrapped)
  cursor value instead, which is not actually a count of anything and
  happened to produce only a plausible-*looking* number; an even earlier
  version used a fixed, unrelated contiguous address range instead of
  replaying either phase's real sequence at all.
- `contest_start`: CONTEST's starting address, remembered separately from
  `contest_cursor` (which moves) so DEFEND can restart that same sequence
  from its actual beginning.
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
        self.claim_stride = 149
        self.claim_cursor = 0
        self.claim_actions = 0
        self.contest_stride = 197
        self.contest_start = context.arena_size // CONTEST_START_FRACTION
        self.contest_cursor = self.contest_start
        self.contest_actions = 0
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
            return AgentAction(ActionKind.JUMP, target_phase)

        if target_phase == PHASE_CLAIM:
            address = self.claim_cursor
            self.claim_cursor = (self.claim_cursor + self.claim_stride) % self.arena_size
            self.claim_actions += 1
            return AgentAction(ActionKind.WRITE, address, self.signature)

        if target_phase == PHASE_CONTEST:
            address = self.contest_cursor
            self.contest_cursor = (self.contest_cursor + self.contest_stride) % self.arena_size
            self.contest_actions += 1
            return AgentAction(ActionKind.WRITE, address, self.signature)

        # PHASE_DEFEND: alternate replaying CLAIM's and CONTEST's actual
        # sequences from their own starting points, rather than an
        # unrelated fixed range.
        claim_span = max(self.claim_actions, 1)
        contest_span = max(self.contest_actions, 1)
        if self.defend_cursor % 2 == 0:
            step = (self.defend_cursor // 2) % claim_span
            address = (step * self.claim_stride) % self.arena_size
        else:
            step = (self.defend_cursor // 2) % contest_span
            address = (self.contest_start + step * self.contest_stride) % self.arena_size
        self.defend_cursor += 1
        return AgentAction(ActionKind.WRITE, address, self.signature)


def create_agent() -> AdaptiveAgent:
    return AdaptiveAgent()
