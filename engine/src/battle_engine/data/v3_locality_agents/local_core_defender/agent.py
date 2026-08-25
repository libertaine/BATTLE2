"""Local Core Defender -- the bounded-locality port of ``core_defender``.

EXPERIMENTAL. Runs only under ``bytefray-rules-3-alpha1``, the v3 research
Phase 2 bounded-locality Ruleset, which is not a stable Ruleset identity.
See docs/V3_PHASE2_LOCALITY_FEASIBILITY.md.

Lineage: ``core_defender`` (reference, ``agent-revision_c0e6fb0847b3...``),
the frozen Phase-0 benchmark population's unconditional (blind) defense
archetype.

Strategy, unchanged in spirit: pay a fixed fraction of total throughput to
keep ownership of one's own core, and spend the rest expanding. Still
blind -- it reads nothing and reacts to nothing, exactly like its ancestor.

Changes required purely by locality:

* ``core_defender`` interleaved defense and expansion action by action
  (every fourth action refreshed one core cell; the other three swept at
  stride 131). Absolute addressing made that free: the core was always one
  ``WRITE`` away no matter where the sweep had reached. Under bounded
  locality it is not. Refreshing the core requires *standing near it*, so
  the interleave has to become a cycle: travel out, claim, travel back,
  refresh.
* This is the single most important consequence of the mechanic for this
  archetype, and it is deliberately not engineered around. Defense now costs
  travel, and the further this agent has expanded, the longer its core is
  unattended -- which is the tradeoff Phase 2 is measuring.
* ``DEFENDED_RADIUS`` stays 8, still matching the Ruleset's own
  ``CORE_SIZE``. That is public Ruleset knowledge, exactly as it was for the
  ancestor -- not privileged information about any opponent.
* Stride 131 is gone; a local sweep is contiguous, so there is no stride.

Unavoidable strategic redesign: one, and it is disclosed rather than hidden.
The ancestor's defense duty cycle was *uniform in time* (one action in four,
forever). This agent's is *periodic in space* (a burst of eight refreshes at
the end of each excursion). No locality-respecting agent can reproduce the
uniform version, because uniformity in time would require being adjacent to
the core at all times, which is the Local Reactive Defender's strategy, not
this one's. The two together bracket the tradeoff.

Important state this agent tracks:

- ``core``: its own core anchor, captured once from ``observation.locus`` on
  the first ``act()`` call. Before any ``MOVE``, the engine-owned locus is
  exactly this entrant's spawn address, which is also where its core is
  anchored (see ``python_runtime``'s ``locus=entrant.start % arena_size``).
  Ordinary self-knowledge, the direct analogue of the ancestor's identical
  trick with ``observation.pc``.
- ``frontier``: how many ``R``-wide windows it has already claimed in each
  direction, so successive excursions claim new ground instead of
  re-claiming the last one's.
"""

from battle_engine.agent_api import ActionKind, AgentAction, MatchContext, Observation

DEFENDED_RADIUS = 8  # mirrors the Ruleset's own CORE_SIZE
EXCURSION_WINDOWS = 4  # R-wide windows claimed before returning to refresh


class LocalCoreDefenderAgent:
    def reset(self, context: MatchContext) -> None:
        self.rng = context.rng  # unused by this strategy, but always available
        self.arena_size = context.arena_size
        self.reach = context.locality_reach
        self.signature = 0xD3
        self.core: int | None = None
        self.direction = 1
        self.frontier = {1: 0, -1: 0}
        self.phase = "refresh"
        self.refresh_index = 0
        self.travel_remaining = 0
        self.windows_remaining = 0
        self.fill_offset = 0
        self.return_remaining = 0

    # -- geometry ----------------------------------------------------------

    def _offset_to(self, address: int, locus: int) -> int:
        """Shortest signed displacement from ``locus`` to ``address``."""

        forward = (address - locus) % self.arena_size
        if forward <= self.arena_size // 2:
            return forward
        return forward - self.arena_size

    def _excursion_would_lap(self, direction: int) -> bool:
        """Whether the next excursion would carry this agent past the far
        side of the arena and back toward its own core from behind."""

        assert self.reach is not None
        distance = (self.frontier[direction] + EXCURSION_WINDOWS) * self.reach
        return distance >= self.arena_size // 2

    # -- lifecycle ---------------------------------------------------------

    def act(self, observation: Observation) -> AgentAction:
        if self.reach is None or observation.locus is None:
            # See local_claimer/agent.py: forfeit visibly off-Ruleset.
            return AgentAction(ActionKind.MOVE, 0)
        locus = observation.locus
        if self.core is None:
            self.core = locus

        if self.phase == "refresh":
            return self._refresh_step(locus)
        if self.phase == "travel_out":
            return self._travel_out_step()
        if self.phase == "fill":
            return self._fill_step()
        return self._return_step()

    # -- phases ------------------------------------------------------------

    def _refresh_step(self, locus: int) -> AgentAction:
        assert self.core is not None
        address = (self.core + self.refresh_index) % self.arena_size
        self.refresh_index += 1
        if self.refresh_index >= DEFENDED_RADIUS:
            self.refresh_index = 0
            self._begin_excursion()
        return AgentAction(
            ActionKind.LOCAL_WRITE, self._offset_to(address, locus), self.signature
        )

    def _begin_excursion(self) -> None:
        if self._excursion_would_lap(self.direction):
            # Start this direction over from the core rather than lapping
            # into the far side of the arena. Re-claiming already-held ground
            # is exactly what the ancestor's sweep did once it wrapped.
            self.frontier[self.direction] = 0
        self.phase = "travel_out"
        self.travel_remaining = self.frontier[self.direction]
        self.windows_remaining = EXCURSION_WINDOWS
        self.fill_offset = 0

    def _travel_out_step(self) -> AgentAction:
        assert self.reach is not None
        if self.travel_remaining > 0:
            self.travel_remaining -= 1
            return AgentAction(ActionKind.MOVE, self.direction * self.reach)
        self.phase = "fill"
        return self._fill_step()

    def _fill_step(self) -> AgentAction:
        assert self.reach is not None
        if self.fill_offset >= self.reach:
            self.fill_offset = 0
            self.windows_remaining -= 1
            if self.windows_remaining <= 0:
                self.frontier[self.direction] += EXCURSION_WINDOWS
                self.phase = "return"
                self.return_remaining = self.frontier[self.direction]
            return AgentAction(ActionKind.MOVE, self.direction * self.reach)

        offset = self.fill_offset
        self.fill_offset += 1
        signed = offset if self.direction > 0 else -offset
        return AgentAction(ActionKind.LOCAL_WRITE, signed, self.signature)

    def _return_step(self) -> AgentAction:
        assert self.reach is not None
        if self.return_remaining > 0:
            self.return_remaining -= 1
            return AgentAction(ActionKind.MOVE, -self.direction * self.reach)
        self.direction = -self.direction
        self.phase = "refresh"
        self.refresh_index = 0
        return self._refresh_step_after_return()

    def _refresh_step_after_return(self) -> AgentAction:
        # A separate entry point only so `_return_step` never has to invent a
        # locus it does not have; the next `act()` supplies the real one.
        assert self.core is not None
        self.refresh_index = 1
        return AgentAction(ActionKind.LOCAL_WRITE, 0, self.signature)


def create_agent() -> LocalCoreDefenderAgent:
    return LocalCoreDefenderAgent()
