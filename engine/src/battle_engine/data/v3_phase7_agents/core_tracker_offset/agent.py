"""Core Tracker (Offset) -- a v3 Phase 7 disposable control agent.

**Not a reference agent. Not pinned to any frozen benchmark population.**
This is a byte-for-byte copy of ``reference_agents/core_tracker/agent.py``
(the real, frozen ``v2-baseline`` population member) with exactly one
behavioral line changed, to isolate one causal question raised by
``docs/V3_PHASE6_ACTIVE_DEFENSIVE_INTERVENTION_QUALIFICATION.md`` Sec 15/20:

Phase 6 found that at ``instr_per_tick=32``, real Core Tracker's own
``expand_cursor`` starts at exactly its own ``core_start`` with **no
offset** (``self.expand_cursor = observation.pc % self.arena_size``), so
its very first action after a same-tick assault takes its own core back to
"defended" -- a routine territorial claim with zero defensive intent that
this detector's reclaim clause cannot distinguish from a genuine reaction,
inflating Core Tracker's own opportunity-conditioned qualifying rate to
50.0% at that budget and eating into Q6's budget-robustness margin.

The one change below moves ``expand_cursor``'s starting point past this
agent's own core, mirroring ``core_defender/agent.py``'s own precedent
(``expand_cursor = core_start + DEFENDED_RADIUS``) exactly -- "so the
defended cells and the expansion sweep never fight over the same ground,"
in that agent's own words. Nothing else about this agent's search,
probing, assault, or cost profile is touched, so any behavioral difference
measured between this agent and real Core Tracker is attributable to this
one line, not to a bundle of changes.

This agent is disposable research tooling for Phase 7's confound-isolation
experiment (see ``docs/V3_PHASE7_HIGH_BUDGET_CONFOUND_ISOLATION.md`` and
``tools/v3_phase7_confound_isolation.py``), never registered in any
``BenchmarkPopulation`` manifest, never pinned via content-addressed
revision, and never substituted into ``v2_baseline_corpus.json`` or any
other frozen benchmark. It exists only to be swapped into a small, disposable,
separately-executed corpus alongside the real, untouched Core Tracker, so
Phase 7 can compare the two without altering anything Phase 0-6 committed.

Everything below this note, other than the renamed class/factory and the
one ``expand_cursor`` line inside ``act()``, is copied unmodified from
``reference_agents/core_tracker/agent.py`` -- including its own historical
design-rationale docstring, preserved here so a diff against the original
shows exactly one substantive change.

---

Original module docstring (``core_tracker/agent.py``), reproduced verbatim
below for lineage:

Core Tracker -- a v2.0.0-alpha.8 "Vulnerable Core" reference agent.

Experimental/reference only, not a claim of optimal strategy -- see
docs/V2_0_ALPHA8_PLACEMENT_AGNOSTIC_OFFENSE.md for the research question
this agent exists to probe: can an ordinary Agent API v1 entrant locate and
pressure a vulnerable core across substantially different, arbitrary start
placements -- not just the handful of fixed absolute addresses the original
Core Seeker's own schedule happens to pass near -- using only the same
``READ``/``WRITE`` primitives every other agent in this file already uses?

Three states, cycled by a small, traceable state machine (``self.mode``):

    "scan"    -- default. One action in every ``SCAN_EVERY`` is a ``READ``
                 at a slowly advancing scan cursor; the rest are an
                 ordinary outward claiming ``WRITE``.
    "probe"   -- entered the instant a coarse scan ``READ`` returns a
                 foreign-looking byte. Issues a small, fixed set of
                 additional ``READ``s at offsets near that first hit.
    "assault" -- a fixed ``ASSAULT_ACTIONS``-action ``WRITE`` burst across
                 a window centered on the refined estimate from the probe
                 evidence.

See the real ``core_tracker/agent.py`` for the full design rationale
(coarse-to-fine search, echo-lock avoidance, RNG-seeded scan anchor, cost
accounting, and the alpha.11/beta1 self-core filtering revision this
agent's own ``_looks_foreign`` also carries forward unchanged).
"""

from battle_engine.agent_api import ActionKind, AgentAction, MatchContext, Observation

CORE_SIZE_HINT = 8  # public ruleset knowledge (bytefray-rules-2-alpha1's CORE_SIZE)
SCAN_EVERY = 3  # 1 action in every 3 scans; the other 2 expand -- matches core_seeker's cost
PROBE_OFFSETS: tuple[int, ...] = (-8, -4, 4, 8)  # relative offsets probed around a candidate hit
CONFIRM_MIN_HITS = 2  # candidate hit + at least this many total foreign observations to assault
ASSAULT_WINDOW = 16  # width of the WRITE burst once confirmed (> CORE_SIZE_HINT)
ASSAULT_ACTIONS = 16


class CoreTrackerOffsetAgent:
    def reset(self, context: MatchContext) -> None:
        self.rng = context.rng
        self.arena_size = context.arena_size
        self.signature = 0xA5
        self.own_core_start: int | None = None
        # Stride: a fixed, well-tested equidistribution constant (see this
        # module's docstring for why it is deliberately distinct from both
        # core_seeker's 0.381_966_011 and hunter's 0.618_033_988_749_895).
        self.scan_stride = (int(context.arena_size * 0.4142135623730951) | 1) or 1
        # Anchor: drawn from this match's own RNG, not a fixed arena-size
        # convention -- the structural change that decorrelates this
        # agent's reachable/unreachable set from arena_size alone.
        self.scan_cursor = context.rng.randrange(context.arena_size)
        self.expand_stride = 157
        self.expand_cursor = 0
        self._expand_cursor_initialized = False

        self.mode = "scan"
        self.actions_taken = 0
        self._pending_read_addr: int | None = None

        self.candidate_hit_addr: int | None = None
        self.probe_offsets_remaining: list[int] = []
        self.probe_confirmed_offsets: list[int] = []
        self._pending_probe_offset: int | None = None

        self.assault_cursor = 0
        self.assault_remaining = 0

    def act(self, observation: Observation) -> AgentAction:
        if not self._expand_cursor_initialized:
            # First call, before this agent has ever moved its own pc:
            # observation.pc is exactly this entrant's original spawn
            # address (see core_defender/agent.py's identical technique).
            #
            # THE ONE CHANGE from real core_tracker/agent.py: the real
            # agent sets ``self.expand_cursor = observation.pc %
            # self.arena_size`` here -- no offset, so its very first
            # non-scan action always lands on its own core_start + 0. This
            # control offsets the expansion sweep's starting point past its
            # own core, mirroring core_defender/agent.py's own
            # ``expand_cursor = core_start + DEFENDED_RADIUS`` precedent
            # exactly, so the defended/core-adjacent cells and the
            # expansion sweep never share ground at the moment expansion
            # begins.
            self.own_core_start = observation.pc % self.arena_size
            self.expand_cursor = (self.own_core_start + CORE_SIZE_HINT) % self.arena_size
            self._expand_cursor_initialized = True

        read_addr: int | None = None
        read_result: int | None = None
        if self._pending_read_addr is not None:
            read_addr = self._pending_read_addr
            read_result = observation.last_read
            self._pending_read_addr = None  # consumed exactly once

        if self.mode == "assault":
            return self._assault_step()
        if self.mode == "probe":
            return self._probe_step(read_addr, read_result)
        return self._scan_step(read_addr, read_result)

    # -- scan --------------------------------------------------------------

    def _scan_step(self, read_addr: int | None, read_result: int | None) -> AgentAction:
        if read_addr is not None and self._looks_foreign(read_addr, read_result):
            return self._begin_probe(read_addr)

        self.actions_taken += 1
        if self.actions_taken % SCAN_EVERY == 0:
            address = self.scan_cursor
            self.scan_cursor = (self.scan_cursor + self.scan_stride) % self.arena_size
            self._pending_read_addr = address
            return AgentAction(ActionKind.READ, address)

        address = self.expand_cursor
        self.expand_cursor = (self.expand_cursor + self.expand_stride) % self.arena_size
        return AgentAction(ActionKind.WRITE, address, self.signature)

    # -- probe (coarse-to-fine confirmation) --------------------------------

    def _begin_probe(self, hit_addr: int) -> AgentAction:
        self.mode = "probe"
        self.candidate_hit_addr = hit_addr
        self.probe_confirmed_offsets = [0]  # the original hit counts as evidence
        self.probe_offsets_remaining = list(PROBE_OFFSETS)
        return self._probe_issue_next()

    def _probe_issue_next(self) -> AgentAction:
        offset = self.probe_offsets_remaining.pop(0)
        assert self.candidate_hit_addr is not None
        address = (self.candidate_hit_addr + offset) % self.arena_size
        self._pending_read_addr = address
        self._pending_probe_offset = offset
        return AgentAction(ActionKind.READ, address)

    def _probe_step(self, read_addr: int | None, read_result: int | None) -> AgentAction:
        if read_addr is not None:
            if (
                self._looks_foreign(read_addr, read_result)
                and self._pending_probe_offset is not None
            ):
                self.probe_confirmed_offsets.append(self._pending_probe_offset)
            self._pending_probe_offset = None

        if self.probe_offsets_remaining:
            return self._probe_issue_next()

        if len(self.probe_confirmed_offsets) >= CONFIRM_MIN_HITS:
            return self._begin_assault()
        self._abandon_candidate()
        return self._scan_step(None, None)

    def _abandon_candidate(self) -> None:
        self.mode = "scan"
        self.candidate_hit_addr = None
        self.probe_confirmed_offsets = []
        self.probe_offsets_remaining = []

    # -- assault -------------------------------------------------------------

    def _begin_assault(self) -> AgentAction:
        assert self.candidate_hit_addr is not None
        mid_offset = (
            min(self.probe_confirmed_offsets) + max(self.probe_confirmed_offsets)
        ) // 2
        anchor = (self.candidate_hit_addr + mid_offset) % self.arena_size
        self.candidate_hit_addr = None
        self.probe_confirmed_offsets = []
        self.probe_offsets_remaining = []
        self.mode = "assault"
        self.assault_cursor = (anchor - ASSAULT_WINDOW // 2) % self.arena_size
        self.assault_remaining = ASSAULT_ACTIONS
        return self._assault_step()

    def _assault_step(self) -> AgentAction:
        address = self.assault_cursor
        self.assault_cursor = (self.assault_cursor + 1) % self.arena_size
        self.assault_remaining -= 1
        if self.assault_remaining <= 0:
            self.mode = "scan"
        return AgentAction(ActionKind.WRITE, address, self.signature)

    # -- shared --------------------------------------------------------------

    def _in_own_core(self, address: int) -> bool:
        """Whether ``address`` falls inside this entrant's own core region."""

        if self.own_core_start is None:
            return False
        offset = (address - self.own_core_start) % self.arena_size
        return offset < CORE_SIZE_HINT

    def _looks_foreign(self, address: int, value: int | None) -> bool:
        """Whether a ``READ`` result is worth treating as attacker evidence.

        Unchanged from real core_tracker: a hit inside this agent's own
        core is never foreign (self-core beacon filtering, carried forward
        from that agent's own beta1 revision unmodified).
        """

        if value is None or value == 0 or value == self.signature:
            return False
        return not self._in_own_core(address)


def create_agent() -> CoreTrackerOffsetAgent:
    return CoreTrackerOffsetAgent()
