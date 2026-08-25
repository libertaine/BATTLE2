"""Local Reactive Defender -- the locality port of ``reactive_core_defender``.

EXPERIMENTAL. Runs only under ``bytefray-rules-3-alpha1``, the v3 research
Phase 2 bounded-locality Ruleset, which is not a stable Ruleset identity.
See docs/V3_PHASE2_LOCALITY_FEASIBILITY.md.

Lineage: ``reactive_core_defender`` (reference,
``agent-revision_51152cd2df94...``), the frozen Phase-0 benchmark
population's reactive/efficient defense archetype.

Strategy, unchanged in spirit: sign every cell of one's own core, patrol it
by *reading* rather than blindly rewriting it, and spend actions on repair
only when a read actually disagrees with what was written. Everything else
goes to expansion.

Changes required purely by locality:

* The ancestor could patrol its core from anywhere, because ``READ`` took an
  absolute address. Here a core cell can only be inspected from within ``R``
  of it, so this agent binds itself to a **guard band**: it never lets its
  locus stray more than ``R - CORE_SIZE`` cells from its own core anchor. In
  exchange, every one of its eight core cells is reachable on every single
  action, so its detect-and-repair latency is exactly the ancestor's.
* That bound is the whole design. It is what makes this agent the honest
  counterpart to Local Core Defender: the two differ in *nothing* except how
  much absence from the core they are willing to buy territory with. Local
  Core Defender ranges freely and pays in latency; this one keeps zero
  latency and pays in reach.
* Expansion therefore covers roughly ``4R`` cells around the core rather
  than the whole arena. The ancestor's stride-131 sweep is gone; a local
  sweep is contiguous, so there is no stride.
* ``DEFENDED_RADIUS`` stays 8 and ``REFRESH_EVERY`` stays 4, both exactly as
  the ancestor set them. The defense duty cycle is unchanged.

Unavoidable strategic redesign: none. This is the one v2 defense archetype
that ports without compromise, because its ancestor's behaviour was already
spatially local -- it simply had no way to say so.
"""

from battle_engine.agent_api import ActionKind, AgentAction, MatchContext, Observation

DEFENDED_RADIUS = 8  # mirrors the Ruleset's own CORE_SIZE
REFRESH_EVERY = 4  # 1 action in every 4 patrols (READ); the other 3 expand


class LocalReactiveDefenderAgent:
    def reset(self, context: MatchContext) -> None:
        self.rng = context.rng  # unused by this strategy, but always available
        self.arena_size = context.arena_size
        self.reach = context.locality_reach
        self.signature = 0xC7
        self.core: int | None = None
        # How far the locus may ever stray from the core. Chosen so that the
        # furthest core cell (anchor + DEFENDED_RADIUS - 1) stays inside R
        # from anywhere in the band, on either side.
        self.band = 1
        self.expected: dict[int, int] = {}
        self.phase = "sign"
        self.sign_index = 0
        self.patrol_cursor = 0
        self.patrol_actions = 0
        self.alert_queue: list[int] = []
        self.pending_check_address: int | None = None
        self.expand_offset = DEFENDED_RADIUS
        self.expand_step = 1

    # -- geometry ----------------------------------------------------------

    def _offset_to(self, address: int, locus: int) -> int:
        forward = (address - locus) % self.arena_size
        if forward <= self.arena_size // 2:
            return forward
        return forward - self.arena_size

    def _distance_from_core(self, address: int) -> int:
        assert self.core is not None
        forward = (address - self.core) % self.arena_size
        return min(forward, self.arena_size - forward)

    def _core_cells(self) -> tuple[int, ...]:
        assert self.core is not None
        return tuple(
            (self.core + offset) % self.arena_size for offset in range(DEFENDED_RADIUS)
        )

    # -- lifecycle ---------------------------------------------------------

    def act(self, observation: Observation) -> AgentAction:
        if self.reach is None or observation.locus is None:
            # See local_claimer/agent.py: forfeit visibly off-Ruleset.
            return AgentAction(ActionKind.MOVE, 0)
        locus = observation.locus
        if self.core is None:
            self.core = locus
            self.band = max(1, self.reach - DEFENDED_RADIUS)

        if self.pending_check_address is not None:
            checked_address = self.pending_check_address
            self.pending_check_address = None
            if observation.last_read != self.expected.get(checked_address):
                return self._begin_repair(checked_address, locus)
            if self.phase == "alert" and not self.alert_queue:
                self._return_to_patrol()

        if self.phase == "sign":
            return self._sign_next(locus)
        if self.phase == "alert":
            return self._alert_next(locus)
        return self._patrol_next(locus)

    def _return_to_patrol(self) -> None:
        self.phase = "patrol"
        self.patrol_cursor = 0
        self.patrol_actions = 0

    def _sign_next(self, locus: int) -> AgentAction:
        address = self._core_cells()[self.sign_index]
        self.sign_index += 1
        self.expected[address] = self.signature
        if self.sign_index >= DEFENDED_RADIUS:
            self._return_to_patrol()
        return AgentAction(
            ActionKind.LOCAL_WRITE, self._offset_to(address, locus), self.signature
        )

    def _begin_repair(self, address: int, locus: int) -> AgentAction:
        if self.phase != "alert":
            self.phase = "alert"
            self.alert_queue = [cell for cell in self._core_cells() if cell != address]
        self.expected[address] = self.signature
        return AgentAction(
            ActionKind.LOCAL_WRITE, self._offset_to(address, locus), self.signature
        )

    def _alert_next(self, locus: int) -> AgentAction:
        if not self.alert_queue:
            self._return_to_patrol()
            return self._patrol_next(locus)
        address = self.alert_queue.pop(0)
        self.pending_check_address = address
        return AgentAction(ActionKind.LOCAL_READ, self._offset_to(address, locus))

    def _patrol_next(self, locus: int) -> AgentAction:
        self.patrol_actions += 1
        if self.patrol_actions % REFRESH_EVERY == 0:
            address = self._core_cells()[self.patrol_cursor]
            self.patrol_cursor = (self.patrol_cursor + 1) % DEFENDED_RADIUS
            self.pending_check_address = address
            return AgentAction(ActionKind.LOCAL_READ, self._offset_to(address, locus))
        return self._expand_next(locus)

    # -- expansion, bounded by the guard band -------------------------------

    def _expand_next(self, locus: int) -> AgentAction:
        assert self.core is not None
        assert self.reach is not None
        address = (self.core + self.expand_offset) % self.arena_size
        offset = self._offset_to(address, locus)
        if abs(offset) <= self.reach:
            self._advance_expansion()
            return AgentAction(ActionKind.LOCAL_WRITE, offset, self.signature)
        return self._step_toward(address, locus)

    def _advance_expansion(self) -> None:
        assert self.reach is not None
        self.expand_offset += self.expand_step
        if abs(self.expand_offset) > self.band + self.reach:
            self.expand_step = -self.expand_step
            self.expand_offset = self.expand_step * DEFENDED_RADIUS

    def _step_toward(self, address: int, locus: int) -> AgentAction:
        """Move toward ``address`` without ever leaving the guard band."""

        assert self.core is not None
        assert self.reach is not None
        offset = self._offset_to(address, locus)
        direction = 1 if offset > 0 else -1
        step = direction * min(self.reach, abs(offset))
        while step != 0 and self._distance_from_core((locus + step) % self.arena_size) > self.band:
            step -= direction
        if step == 0:
            # The frontier has outrun the band in this direction; restart
            # expansion on the other side rather than stalling.
            self.expand_step = -self.expand_step
            self.expand_offset = self.expand_step * DEFENDED_RADIUS
            return AgentAction(ActionKind.LOCAL_WRITE, 0, self.signature)
        return AgentAction(ActionKind.MOVE, step)


def create_agent() -> LocalReactiveDefenderAgent:
    return LocalReactiveDefenderAgent()
