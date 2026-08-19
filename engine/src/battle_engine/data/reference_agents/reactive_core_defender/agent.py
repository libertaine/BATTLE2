"""Reactive Core Defender -- a v2.0.0-alpha.2 "Vulnerable Core" reference agent.

Experimental/reference only, not a claim of optimal strategy -- see
docs/V2_0_ALPHA2_REACTIVE_DEFENSE.md for the research question this agent
exists to probe: can a defender that only spends defensive actions when it
has actual evidence of core damage do better against Core Seeker than the
original Core Defender's fixed 25%-blind-refresh schedule (see
``core_defender/agent.py``), without simply becoming a differently-shaped
periodic agent?

Why the original Core Defender's schedule is not reactive:
It refreshes one of its ``DEFENDED_RADIUS`` core cells every 4th action on
a fixed rotation, unconditionally -- whether or not that cell has been
touched by anything else since it was last refreshed. It never issues a
single ``READ``, so it has no way to *know* whether its core is intact or
already lost; "defense" for that agent is a timer, not a response.

What information an ordinary Python entrant actually has available:
``Observation`` exposes no ownership map and no opponent state -- the only
way to learn what is currently stored at an address is a ``READ``, which
returns one raw byte value, not an owner (see ``core_seeker/agent.py``'s
docstring for the identical constraint from the attacker's side). This
agent turns that constraint around and points it inward: since it always
knows exactly what it last wrote to each of its own core cells, a byte
value at one of those addresses that no longer matches what this agent
itself put there is direct, ordinary-API evidence that someone else wrote
there -- without ever knowing who, or querying ownership directly (no such
query exists in Agent API v1). This is an imperfect proxy, not a true
ownership read: an opponent who happened to write the exact byte this
agent last wrote would go undetected by content comparison alone. This
agent narrows, but does not close, that gap by writing its own distinctive
non-zero signature across its whole core immediately (see "Phase 0" below)
rather than relying on the arena's shared untouched-default byte (``0``),
so an opponent would have to coincidentally reproduce this agent's specific
signature, not just leave a cell looking untouched.

Three phases, cycled by a small state machine:

    SIGN     -- the first ``DEFENDED_RADIUS`` actions only: claim every
                core cell with this agent's own signature, one cell per
                action, before anything else happens. A one-time setup
                cost (``DEFENDED_RADIUS`` actions out of a match's full
                budget), not a recurring one -- unlike the original Core
                Defender's forever-recurring 25% refresh rate.
    PATROL   -- steady-state behavior once signed: one action in every
                ``REFRESH_EVERY`` (the same cadence the original Core
                Defender spent on blind refresh, so the two are directly
                comparable on "how often is a core-related action taken")
                is a ``READ`` at a rotating core-cell cursor, compared
                against this agent's own record of what it last wrote
                there; any mismatch is treated as damage and triggers
                ALERT. The other ``REFRESH_EVERY - 1`` of every
                ``REFRESH_EVERY`` actions are an ordinary Claimer-style
                outward sweep starting just past the defended region, so
                a healthy core costs exactly the same steady-state
                overhead as before but spends it on cheap, non-destructive
                inspection instead of unconditional rewriting.

                Known, deliberately-not-fixed limitation: the rotation is
                a fixed round-robin, not randomized. A randomized-order
                variant was built and A/B tested directly against this
                agent's own acceptance suite and against Core Seeker
                (docs/V2_0_ALPHA2_REACTIVE_DEFENSE.md) specifically to
                close a theoretical "phase-matched" evasion (an attacker
                whose write order happens to track the cursor's phase can
                in principle evade detection indefinitely). It was
                reverted: no real Agent API v1 opponent can observe this
                agent's internal inspection schedule (a ``READ`` produces
                no signal any other entrant can see -- ``Observation``
                exposes nothing about another entrant's actions), so the
                fixed order is not an exploitable weakness through the
                ordinary API this experiment is scoped to, while
                randomizing it measurably *reduced* real survival against
                the actual bundled Core Seeker (8/8 seeds survived with
                the fixed order vs. 4/8 with randomization, identical
                seed set) by decorrelating this agent's own inspection
                timing from favorable alignment. Kept fixed on that
                evidence, not by default.
    ALERT    -- entered the instant a patrol (or alert-sweep) ``READ``
                finds a mismatch. The damaged cell is repaired immediately
                (one ``WRITE``), and every other core cell is then checked
                in turn, at full priority over expansion, one ``READ`` per
                cell with an immediate repair ``WRITE`` only for the ones
                actually found mismatched -- never a blind rewrite of
                cells with no evidence against them. Once every core cell
                has been checked (and repaired if needed), this agent
                returns to PATROL rather than staying defensive forever.

Important state this agent tracks:
- ``core_start``/``core_cells``: this agent's own core anchor and the
  ``DEFENDED_RADIUS`` addresses derived from it (ordinary ``pos %
  arena_size`` wrap), captured from ``observation.pc`` on the first
  ``act()`` call exactly as ``core_defender/agent.py`` already does --
  never given for free, and never any opponent-side address.
- ``expected``: a dict from this agent's own core addresses to the byte
  value it last wrote there -- the record content-based detection is
  compared against. Only ever updated by this agent's own writes.
- ``phase``/``sign_index``/``patrol_cursor``/``patrol_actions``/
  ``alert_queue``/``pending_check_address``: which phase this agent is in,
  where a rotating cursor currently is, and (while a ``READ`` result is
  outstanding) which address that pending result belongs to, since
  ``Observation.last_read`` only reports a value, not the address it came
  from.

What you might reasonably change:
- ``REFRESH_EVERY``: a smaller value inspects more often (faster
  detection, more steady-state overhead); a larger value is cheaper but
  slower to notice damage.
"""

from battle_engine.agent_api import ActionKind, AgentAction, MatchContext, Observation

DEFENDED_RADIUS = 8  # mirrors bytefray-rules-2-alpha1's CORE_SIZE
REFRESH_EVERY = 4  # 1 action in every 4 patrols (READ); the other 3 expand


class ReactiveCoreDefenderAgent:
    def reset(self, context: MatchContext) -> None:
        self.rng = context.rng  # unused by this strategy, but always available
        self.arena_size = context.arena_size
        self.signature = 0xC7
        self.core_start: int | None = None
        self.core_cells: tuple[int, ...] = ()
        self.expected: dict[int, int] = {}
        self.phase = "sign"
        self.sign_index = 0
        self.patrol_cursor = 0
        self.patrol_actions = 0
        self.alert_queue: list[int] = []
        self.pending_check_address: int | None = None
        self.expand_stride = 131
        self.expand_cursor = 0

    def act(self, observation: Observation) -> AgentAction:
        if self.core_start is None:
            # First call, before this agent has ever moved its own pc:
            # observation.pc is exactly this entrant's original spawn
            # address (see this module's docstring, and
            # core_defender/agent.py's identical technique).
            self.core_start = observation.pc % self.arena_size
            self.core_cells = tuple(
                (self.core_start + offset) % self.arena_size for offset in range(DEFENDED_RADIUS)
            )
            self.expand_cursor = (self.core_start + DEFENDED_RADIUS) % self.arena_size

        if self.pending_check_address is not None:
            checked_address = self.pending_check_address
            self.pending_check_address = None
            if observation.last_read != self.expected.get(checked_address):
                return self._begin_repair(checked_address)
            if self.phase == "alert" and not self.alert_queue:
                self._return_to_patrol()

        if self.phase == "sign":
            return self._sign_next()
        if self.phase == "alert":
            return self._alert_next()
        return self._patrol_next()

    def _return_to_patrol(self) -> None:
        self.phase = "patrol"
        self.patrol_cursor = 0
        self.patrol_actions = 0

    def _sign_next(self) -> AgentAction:
        address = self.core_cells[self.sign_index]
        self.sign_index += 1
        self.expected[address] = self.signature
        if self.sign_index >= DEFENDED_RADIUS:
            self._return_to_patrol()
        return AgentAction(ActionKind.WRITE, address, self.signature)

    def _begin_repair(self, address: int) -> AgentAction:
        if self.phase != "alert":
            self.phase = "alert"
            self.alert_queue = [cell for cell in self.core_cells if cell != address]
        self.expected[address] = self.signature
        return AgentAction(ActionKind.WRITE, address, self.signature)

    def _alert_next(self) -> AgentAction:
        if not self.alert_queue:
            self._return_to_patrol()
            return self._patrol_next()
        address = self.alert_queue.pop(0)
        self.pending_check_address = address
        return AgentAction(ActionKind.READ, address)

    def _patrol_next(self) -> AgentAction:
        self.patrol_actions += 1
        if self.patrol_actions % REFRESH_EVERY == 0:
            address = self.core_cells[self.patrol_cursor]
            self.patrol_cursor = (self.patrol_cursor + 1) % DEFENDED_RADIUS
            self.pending_check_address = address
            return AgentAction(ActionKind.READ, address)

        address = self.expand_cursor
        self.expand_cursor = (self.expand_cursor + self.expand_stride) % self.arena_size
        return AgentAction(ActionKind.WRITE, address, self.signature)


def create_agent() -> ReactiveCoreDefenderAgent:
    return ReactiveCoreDefenderAgent()
