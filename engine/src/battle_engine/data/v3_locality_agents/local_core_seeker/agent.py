"""Local Core Seeker -- the bounded-locality port of ``core_seeker``.

EXPERIMENTAL. Runs only under ``bytefray-rules-3-alpha1``, the v3 research
Phase 2 bounded-locality Ruleset, which is not a stable Ruleset identity.
See docs/V3_PHASE2_LOCALITY_FEASIBILITY.md.

Lineage: ``core_seeker`` (reference, ``agent-revision_d38b09bde99d...``),
the frozen Phase-0 benchmark population's historical search-and-destroy
control.

Strategy, unchanged in spirit: spend one action in every three looking, the
other two claiming ground, and when two foreign readings turn up close
together, stop expanding and burst-write the region to take whatever core is
hiding there.

Changes required purely by locality:

* ``core_seeker`` scanned with an absolute golden-ratio stride, sampling the
  whole arena sparsely from wherever it happened to be. Bounded reach makes
  that impossible: an entrant can only inspect the ``2R + 1`` cells around
  its locus, so scanning becomes *sweeping* -- read the cells you pass,
  advance one window, repeat. This is the single most consequential change
  the mechanic forces on the search archetype, and it is deliberately not
  compensated for: remote information is now genuinely unavailable rather
  than merely expensive.
* ``SCAN_EVERY`` stays 3, so the look-versus-claim cost ratio is exactly the
  ancestor's and the two remain comparable on action economy. One cursor
  walks the forward window and each cell it passes costs exactly one action,
  a read on every third and a claim otherwise.
* An assault can no longer be launched from wherever the hit was noticed.
  ``ASSAULT_WINDOW`` is 16 and a hit may be up to ``R`` away, so this agent
  must physically **approach** the target before it can strike -- one action
  per hop of at most ``R``, then the burst. That approach is the honest new
  cost of offense under locality.
* ``LOCK_RADIUS`` stays 12 and ``ASSAULT_WINDOW`` stays 16, unchanged.
* ``_in_own_core`` is inherited from ``core_tracker``'s Beta1 cleanup rather
  than from this agent's own ancestor. It has to be: this agent now *starts
  standing on its own core*, whose beacon bytes would otherwise read as a
  foreign contact on its very first scan and send it assaulting itself.
  That is a locality-created false positive, not a strategy improvement.

Unavoidable strategic redesign: none. The search loop -- look, notice,
confirm by proximity, commit -- is the ancestor's, with travel inserted where
absolute addressing used to be free.
"""

from battle_engine.agent_api import ActionKind, AgentAction, MatchContext, Observation

SCAN_EVERY = 3  # 1 action in every 3 scans; the other 2 expand
LOCK_RADIUS = 12  # how close two foreign hits must be to count as one cluster
ASSAULT_WINDOW = 16  # width of the LOCAL_WRITE burst once locked on
CORE_SIZE_HINT = 8  # public ruleset knowledge (the Ruleset's own CORE_SIZE)


class LocalCoreSeekerAgent:
    def reset(self, context: MatchContext) -> None:
        self.rng = context.rng  # unused by this strategy, but always available
        self.arena_size = context.arena_size
        self.reach = context.locality_reach
        self.signature = 0x5E
        self.core: int | None = None
        self.direction = 1
        self.cursor = 0
        self.actions_taken = 0
        self.mode = "scan"
        self.pending_read_address: int | None = None
        self.last_foreign_address: int | None = None
        self.approach_target: int | None = None
        self.assault_offset = 0
        self.assault_remaining = 0

    # -- geometry ----------------------------------------------------------

    def _offset_to(self, address: int, locus: int) -> int:
        forward = (address - locus) % self.arena_size
        if forward <= self.arena_size // 2:
            return forward
        return forward - self.arena_size

    def _in_own_core(self, address: int) -> bool:
        if self.core is None:
            return False
        offset = (address - self.core) % self.arena_size
        return offset < CORE_SIZE_HINT

    def _looks_foreign(self, address: int, value: int | None) -> bool:
        if value is None or value == 0 or value == self.signature:
            return False
        return not self._in_own_core(address)

    def _within_lock_radius(self, a: int, b: int) -> bool:
        forward = (a - b) % self.arena_size
        backward = (b - a) % self.arena_size
        return min(forward, backward) <= LOCK_RADIUS

    # -- lifecycle ---------------------------------------------------------

    def act(self, observation: Observation) -> AgentAction:
        if self.reach is None or observation.locus is None:
            # See local_claimer/agent.py: forfeit visibly off-Ruleset.
            return AgentAction(ActionKind.MOVE, 0)
        locus = observation.locus
        if self.core is None:
            self.core = locus

        if self.mode == "assault":
            return self._assault_step()
        if self.mode == "approach":
            return self._approach_step(locus)

        read_address = self.pending_read_address
        self.pending_read_address = None
        if read_address is not None and self._looks_foreign(
            read_address, observation.last_read
        ):
            if self.last_foreign_address is not None and self._within_lock_radius(
                read_address, self.last_foreign_address
            ):
                return self._begin_approach(read_address, locus)
            self.last_foreign_address = read_address
        return self._scan_step(locus)

    # -- sweep -------------------------------------------------------------

    def _scan_step(self, locus: int) -> AgentAction:
        assert self.reach is not None
        if self.cursor >= self.reach:
            self.cursor = 0
            return AgentAction(ActionKind.MOVE, self.direction * self.reach)

        offset = self.cursor if self.direction > 0 else -self.cursor
        address = (locus + offset) % self.arena_size
        self.cursor += 1
        self.actions_taken += 1
        if self.actions_taken % SCAN_EVERY == 0:
            self.pending_read_address = address
            return AgentAction(ActionKind.LOCAL_READ, offset)
        return AgentAction(ActionKind.LOCAL_WRITE, offset, self.signature)

    # -- approach and assault ----------------------------------------------

    def _begin_approach(self, hit_address: int, locus: int) -> AgentAction:
        anchor = (
            hit_address
            if self.last_foreign_address is None
            else min(hit_address, self.last_foreign_address)
        )
        self.last_foreign_address = None
        self.approach_target = anchor
        self.mode = "approach"
        return self._approach_step(locus)

    def _approach_step(self, locus: int) -> AgentAction:
        assert self.reach is not None
        assert self.approach_target is not None
        offset = self._offset_to(self.approach_target, locus)
        if offset == 0:
            return self._begin_assault()
        direction = 1 if offset > 0 else -1
        return AgentAction(ActionKind.MOVE, direction * min(self.reach, abs(offset)))

    def _begin_assault(self) -> AgentAction:
        assert self.reach is not None
        self.approach_target = None
        self.mode = "assault"
        # Clamp the burst to what is actually reachable from one position.
        # At every reach this experiment treats as viable (R >= CORE_SIZE)
        # this is a no-op and the burst is the ancestor's full 16 cells. At a
        # smaller reach it is the minimal locality-forced adaptation: strike
        # as wide as the Ruleset allows rather than spend the difference on
        # guaranteed reach misses, so a too-small-R condition is rejected for
        # the mechanic's reason and not for an agent's arithmetic.
        half = min(ASSAULT_WINDOW // 2, self.reach)
        self.assault_offset = -half
        self.assault_remaining = 2 * half
        return self._assault_step()

    def _assault_step(self) -> AgentAction:
        offset = self.assault_offset
        self.assault_offset += 1
        self.assault_remaining -= 1
        if self.assault_remaining <= 0:
            self.mode = "scan"
            self.cursor = 0
            self.actions_taken = 0
        return AgentAction(ActionKind.LOCAL_WRITE, offset, self.signature)


def create_agent() -> LocalCoreSeekerAgent:
    return LocalCoreSeekerAgent()
