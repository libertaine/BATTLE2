"""Strider -- Claimer's sweep, plus one idea: defend on a rolling schedule.

Strategy, and why it changed:
Strider starts from the exact same address as Claimer, so both begin by
covering the same busy region rather than immediately splitting off into
separate territory -- but with a *different* stride, not the same one.
Two agents sweeping with an identical stride are really walking the same
cyclic sequence of addresses, just entered at the same or a different
point; a first version of this agent used Claimer's exact stride, which
meant every cell either agent had ever touched was, by construction, also
touched by the other at the *same* moment -- so Strider's defend phase
(below) wasn't defending genuinely contested ground, it was trivially
re-winning cells that were never really at risk, since perfect lockstep
guarantees perfect overlap. A different stride means the two sweeps
genuinely diverge over time, and only some ground actually ends up
fought over.

Every `CYCLE_ADVANCE` actions of forward expansion, Strider pauses
advancing and spends `CYCLE_DEFEND` actions replaying the *immediately
preceding* block of its own stride sequence -- the ground it claimed just
before this cycle, and therefore the ground that has had the least time
to be stolen relative to how likely it is to still matter. This repeats
as a rolling cycle for the whole match, not just once at the end: Claimer
never looks back at all, Strider periodically does.

An even earlier version tried to earn an advantage a third way: reading
each cell before re-claiming it (lost badly -- see Claimer's docstring
for why a first-time write is never wasted, so reading pays for itself
only once revisiting owned ground is common, which rarely happens within
realistic tick budgets). See
`bytefray agents evaluate strider --baseline claimer --opponents
hunter,wanderer,adaptive --seeds 1,2,3,4,5` for a real comparison, and try
a held-out seed range too before trusting a small sample.

Important state this agent tracks:
- `signature` / `stride`: the byte it writes and the sweep step size (a
  different stride from Claimer's -- see above).
- `cursor`: the forward sweep position.
- `phase` / `phase_step`: which part of the advance/defend cycle is in
  progress, and how far into it.
- `block_start_cursor`: where the *current* advance block began -- this
  becomes the defend target once that block ends and the next one
  starts, so each defend pass always reinforces the block just completed.
- `defend_anchor` / `defend_step`: the recorded start of the block being
  defended, and position within that replay.

What you might reasonably change:
- `CYCLE_ADVANCE` / `CYCLE_DEFEND`: a longer advance stretch expands
  further between defenses (and spreads each defend pass thinner, since
  `DEFEND_SPACING` is derived from both); a longer defend stretch
  reinforces more cells per cycle but expands less overall.
"""

from battle_engine.agent_api import ActionKind, AgentAction, MatchContext, Observation

CYCLE_ADVANCE = 900
CYCLE_DEFEND = 40
# Spacing between defended cells within the preceding block, so the
# CYCLE_DEFEND actions available spread evenly across the whole block
# instead of concentrating on just its first few cells. An earlier
# version set an independent DEFEND_WINDOW larger than CYCLE_DEFEND,
# which meant only the first CYCLE_DEFEND cells of each block were ever
# reinforced -- the rest of the block was never defended at all.
DEFEND_SPACING = max(1, CYCLE_ADVANCE // CYCLE_DEFEND)


class StriderAgent:
    def reset(self, context: MatchContext) -> None:
        self.rng = context.rng
        self.arena_size = context.arena_size
        self.signature = 0xC2
        self.stride = 131
        self.cursor = 0
        self.block_start_cursor = 0
        self.phase = "advance"
        self.phase_step = 0
        self.defend_anchor = 0
        self.defend_step = 0

    def act(self, observation: Observation) -> AgentAction:
        if self.phase == "advance":
            address = self.cursor
            self.cursor = (self.cursor + self.stride) % self.arena_size
            self.phase_step += 1
            if self.phase_step >= CYCLE_ADVANCE:
                self.phase = "defend"
                self.phase_step = 0
                self.defend_anchor = self.block_start_cursor
                self.defend_step = 0
            return AgentAction(ActionKind.WRITE, address, self.signature)

        # self.phase == "defend"
        offset = self.defend_step * DEFEND_SPACING
        address = (self.defend_anchor + offset * self.stride) % self.arena_size
        self.defend_step += 1
        self.phase_step += 1
        if self.phase_step >= CYCLE_DEFEND:
            self.phase = "advance"
            self.phase_step = 0
            self.block_start_cursor = self.cursor
        return AgentAction(ActionKind.WRITE, address, self.signature)


def create_agent() -> StriderAgent:
    return StriderAgent()
