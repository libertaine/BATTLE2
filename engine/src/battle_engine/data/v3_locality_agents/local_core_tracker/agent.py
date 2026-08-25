"""Local Core Tracker -- the bounded-locality port of ``core_tracker``.

EXPERIMENTAL. Runs only under ``bytefray-rules-3-alpha1``, the v3 research
Phase 2 bounded-locality Ruleset, which is not a stable Ruleset identity.
See docs/V3_PHASE2_LOCALITY_FEASIBILITY.md.

Lineage: ``core_tracker`` (reference, ``agent-revision_307b9385af77...``),
the frozen Phase-0 benchmark population's placement-agnostic
search-and-destroy benchmark -- and, per Phase 0 Sec 9, the agent that is the
*decisive* factor in every roster it joins despite rarely leading on raw win
rate.

Strategy, unchanged in spirit: sweep cheaply, and when something foreign
turns up, do not commit immediately -- spend a few reads probing around the
candidate first, and only assault if the evidence holds up. That
coarse-to-fine discipline is what distinguishes this agent from Local Core
Seeker, and it is preserved exactly.

Changes required purely by locality:

* Same sweep change as Local Core Seeker: an absolute equidistribution
  stride becomes a contiguous forward sweep of the reachable window, because
  remote cells cannot be inspected at all. ``SCAN_EVERY`` stays 3.
* ``PROBE_OFFSETS`` stays ``(-8, -4, 4, 8)`` and ``CONFIRM_MIN_HITS`` stays
  2, but the probes are now issued **from on top of the candidate**: this
  agent approaches the hit first, then probes. Its ancestor could probe a
  remote address from where it stood; bounded reach means a candidate up to
  ``R`` away has probe points up to ``R + 8`` away, outside reach. Moving
  first is the minimal fix and costs one action per hop.
* Approaching before probing has a real strategic consequence, and it is
  the interesting one: a *rejected* candidate has already cost this agent
  the trip. Under Ruleset v2 a false positive cost four reads; here it costs
  four reads plus the travel there and the sweep restarted from a new
  position. Cautious search is genuinely more expensive under locality, and
  that is a finding rather than a defect.
* The scan anchor is no longer drawn from ``context.rng``. An anchor is an
  absolute address and a locality entrant cannot choose where to start
  looking -- it starts where it spawned. The RNG instead chooses this
  agent's **sweep direction**, which is the locality analogue: it is the one
  remaining degree of freedom that decorrelates which region this agent
  reaches first from placement alone, preserving the ancestor's
  placement-agnostic intent through the only channel the mechanic leaves.
* ``ASSAULT_WINDOW``/``ASSAULT_ACTIONS`` stay 16, clamped to the reachable
  window for the same reason documented in Local Core Seeker.

Unavoidable strategic redesign: none beyond the anchor-to-direction change
above, which is disclosed rather than absorbed.
"""

from battle_engine.agent_api import ActionKind, AgentAction, MatchContext, Observation

CORE_SIZE_HINT = 8  # public ruleset knowledge (the Ruleset's own CORE_SIZE)
SCAN_EVERY = 3  # 1 action in every 3 scans -- matches local_core_seeker's cost
PROBE_OFFSETS: tuple[int, ...] = (-8, -4, 4, 8)  # probed around a candidate hit
CONFIRM_MIN_HITS = 2  # candidate hit + this many total foreign observations
ASSAULT_WINDOW = 16  # width of the LOCAL_WRITE burst once confirmed


class LocalCoreTrackerAgent:
    def reset(self, context: MatchContext) -> None:
        self.rng = context.rng
        self.arena_size = context.arena_size
        self.reach = context.locality_reach
        self.signature = 0xA5
        self.core: int | None = None
        # Direction, not anchor: see this module's docstring. Drawn from this
        # match's own RNG, so which side of the arena this agent investigates
        # first is not a pure function of its placement.
        self.direction = 1 if context.rng.randrange(2) else -1
        self.cursor = 0
        self.actions_taken = 0

        self.mode = "scan"
        self.pending_read_address: int | None = None

        self.candidate_address: int | None = None
        self.probe_offsets_remaining: list[int] = []
        self.probe_confirmed_offsets: list[int] = []
        self._pending_probe_offset: int | None = None
        self.after_approach = "probe"

        self.assault_offset = 0
        self.assault_remaining = 0

    # -- geometry ----------------------------------------------------------

    def _offset_to(self, address: int, locus: int) -> int:
        forward = (address - locus) % self.arena_size
        if forward <= self.arena_size // 2:
            return forward
        return forward - self.arena_size

    def _in_own_core(self, address: int) -> bool:
        """Whether ``address`` falls inside this entrant's own core region.

        Uses only ``self.core`` -- captured from this agent's own
        ``observation.locus`` on its first ``act()`` call, which before any
        ``MOVE`` is exactly its spawn address and therefore its own core
        anchor -- and the public ``CORE_SIZE_HINT``. Ordinary,
        already-legitimate self-knowledge, never an opponent's coordinates.
        """

        if self.core is None:
            return False
        offset = (address - self.core) % self.arena_size
        return offset < CORE_SIZE_HINT

    def _looks_foreign(self, address: int, value: int | None) -> bool:
        if value is None or value == 0 or value == self.signature:
            return False
        return not self._in_own_core(address)

    # -- lifecycle ---------------------------------------------------------

    def act(self, observation: Observation) -> AgentAction:
        if self.reach is None or observation.locus is None:
            # See local_claimer/agent.py: forfeit visibly off-Ruleset.
            return AgentAction(ActionKind.MOVE, 0)
        locus = observation.locus
        if self.core is None:
            self.core = locus

        read_address: int | None = None
        read_result: int | None = None
        if self.pending_read_address is not None:
            read_address = self.pending_read_address
            read_result = observation.last_read
            self.pending_read_address = None  # consumed exactly once

        if self.mode == "assault":
            return self._assault_step()
        if self.mode == "approach":
            return self._approach_step(locus)
        if self.mode == "probe":
            return self._probe_step(read_address, read_result, locus)
        return self._scan_step(read_address, read_result, locus)

    # -- scan --------------------------------------------------------------

    def _scan_step(
        self, read_address: int | None, read_result: int | None, locus: int
    ) -> AgentAction:
        assert self.reach is not None
        if read_address is not None and self._looks_foreign(read_address, read_result):
            return self._begin_investigation(read_address, locus)

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

    # -- approach (the locality-forced insertion) ---------------------------

    def _begin_investigation(self, hit_address: int, locus: int) -> AgentAction:
        self.candidate_address = hit_address
        self.mode = "approach"
        self.after_approach = "probe"
        return self._approach_step(locus)

    def _approach_step(self, locus: int) -> AgentAction:
        assert self.reach is not None
        assert self.candidate_address is not None
        offset = self._offset_to(self.candidate_address, locus)
        if offset == 0:
            if self.after_approach == "assault":
                return self._begin_assault()
            return self._begin_probe()
        direction = 1 if offset > 0 else -1
        return AgentAction(ActionKind.MOVE, direction * min(self.reach, abs(offset)))

    # -- probe (coarse-to-fine confirmation) --------------------------------

    def _begin_probe(self) -> AgentAction:
        assert self.reach is not None
        self.mode = "probe"
        self.probe_confirmed_offsets = [0]  # the original hit counts as evidence
        self.probe_offsets_remaining = [
            offset for offset in PROBE_OFFSETS if abs(offset) <= self.reach
        ]
        if not self.probe_offsets_remaining:
            # Reach is smaller than the tightest probe: no confirmation is
            # possible at all, so fall back to the single-hit evidence and
            # let the corpus record what that does.
            return self._resolve_probe()
        return self._probe_issue_next()

    def _probe_issue_next(self) -> AgentAction:
        offset = self.probe_offsets_remaining.pop(0)
        self.pending_read_address = (
            (self.candidate_address or 0) + offset
        ) % self.arena_size
        self._pending_probe_offset = offset
        return AgentAction(ActionKind.LOCAL_READ, offset)

    def _probe_step(
        self, read_address: int | None, read_result: int | None, locus: int
    ) -> AgentAction:
        if read_address is not None:
            if (
                self._looks_foreign(read_address, read_result)
                and self._pending_probe_offset is not None
            ):
                self.probe_confirmed_offsets.append(self._pending_probe_offset)
            self._pending_probe_offset = None

        if self.probe_offsets_remaining:
            return self._probe_issue_next()
        return self._resolve_probe(locus)

    def _resolve_probe(self, locus: int | None = None) -> AgentAction:
        if len(self.probe_confirmed_offsets) >= CONFIRM_MIN_HITS:
            mid = (
                min(self.probe_confirmed_offsets) + max(self.probe_confirmed_offsets)
            ) // 2
            self.candidate_address = (
                (self.candidate_address or 0) + mid
            ) % self.arena_size
            self.mode = "approach"
            self.after_approach = "assault"
            if locus is None:
                # Only reachable from `_begin_probe`'s degenerate branch,
                # where no probe was ever issued and the locus is exactly the
                # candidate already.
                return self._begin_assault()
            return self._approach_step(locus)
        self._abandon_candidate()
        assert locus is not None
        return self._scan_step(None, None, locus)

    def _abandon_candidate(self) -> None:
        self.mode = "scan"
        self.candidate_address = None
        self.probe_confirmed_offsets = []
        self.probe_offsets_remaining = []
        # The sweep restarts from wherever the abandoned trip left this
        # agent -- the cost of a false positive under bounded locality.
        self.cursor = 0
        self.actions_taken = 0

    # -- assault -------------------------------------------------------------

    def _begin_assault(self) -> AgentAction:
        assert self.reach is not None
        self.candidate_address = None
        self.probe_confirmed_offsets = []
        self.probe_offsets_remaining = []
        self.mode = "assault"
        # Clamped exactly as local_core_seeker clamps it, and for the same
        # reason: at every reach this experiment treats as viable this is a
        # no-op.
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


def create_agent() -> LocalCoreTrackerAgent:
    return LocalCoreTrackerAgent()
