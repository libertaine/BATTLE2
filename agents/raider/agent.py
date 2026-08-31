"""Raider -- searches for an enemy core and attacks it.

Provenance: derived for product use from the frozen Core Tracker research
agent (``battle_engine/data/reference_agents/core_tracker``). This starter
is independently maintained and is not that benchmark artifact -- it has
its own identity and its own signature byte, and may change without any
effect on the frozen v2 benchmark population.

Strategy:
Every other bundled starter wins ground by claiming it. Raider does
something none of them do: it goes looking for the opponent's *vulnerable
core* and overwrites it. Under Ruleset v2 (``bytefray-rules-2``) each
entrant owns a fixed, ``CORE_SIZE_HINT``-cell core region, and an entrant
whose core is taken from it is eliminated -- so a successful raid ends the
match outright instead of slowly out-claiming anyone.

The hard part is that ``Observation`` exposes no ownership map and no
opponent state. The only way to learn anything about the arena is a
``READ``, which returns one raw byte, not an owner. Raider therefore
treats any byte that is neither blank (``0``) nor its own signature as
"foreign-looking" -- evidence *something else* wrote there, without
knowing what or whom -- and works in three modes:

    scan     -- the default. One action in every ``SCAN_EVERY`` is a
                ``READ`` at a slowly advancing cursor; the other two are an
                ordinary outward claiming ``WRITE``, so time spent looking
                is never pure loss when nothing is found.
    probe    -- entered the moment a scan ``READ`` comes back foreign. A
                single foreign byte is weak evidence: it could be one
                incidental cell from any opponent's expansion sweep passing
                through. So Raider spends a few more ``READ``s at nearby
                offsets (``PROBE_OFFSETS``) before committing. A real core
                is ``CORE_SIZE_HINT`` contiguous cells, so several nearby
                foreign hits look like a core and one isolated hit does
                not. If the evidence does not hold up, the candidate is
                abandoned and scanning resumes exactly where it left off.
    assault  -- a fixed ``ASSAULT_ACTIONS``-action ``WRITE`` burst across a
                window centred on the refined estimate. There is no special
                "attack" action in this Ruleset: an assault is the same
                ``WRITE`` every other agent uses to claim territory, aimed
                at an evidence-derived location instead of at empty ground.

This costs real budget, deliberately. Scanning gives up one action in
three; every candidate costs several more dedicated ``READ``s with no
claiming interleaved; a confirmed cluster costs a whole burst. Raider
usually holds less territory than Claimer or Hunter -- it is trading
steady accumulation for the chance at a decisive win. Watch a replay: it
claims unremarkably for a while, then suddenly hammers one narrow band of
the arena.

Important Agent API behavior this agent demonstrates:
``observation.last_read`` reflects whichever ``READ`` most recently
completed and is **never cleared** between actions. An agent that checks it
on every call will re-observe the same stale value over and over and
mistake one hit for several. Raider avoids that structurally rather than by
convention: every ``READ`` it issues records the exact address it is
waiting on in ``_pending_read_addr``, and the very next ``act()`` call
consumes that result and clears the marker before doing anything else. A
given read result is therefore interpreted exactly once. This is the single
most common correctness mistake in Agent API v1 agents -- copy the pattern.

Important state this agent tracks:
- ``signature``: this agent's own claim byte.
- ``mode``: which of the three modes above it is in.
- ``scan_cursor``/``scan_stride`` and ``expand_cursor``/``expand_stride``:
  independent sweep positions, so searching and claiming never interfere
  with each other's coverage. The scan anchor is drawn from ``context.rng``
  so which part of the arena gets searched depends on the match seed, not
  only on the arena size.
- ``own_core_start``: this agent's own core anchor, captured once from
  ``observation.pc`` on the first ``act()`` call -- ordinary
  self-knowledge, not a privileged read of anyone else. Used to avoid
  wasting a probe/assault cycle on its own core beacon.
- ``candidate_hit_addr``/``probe_offsets_remaining``/
  ``probe_confirmed_offsets``: the candidate currently under investigation
  and the evidence gathered so far.
- ``assault_cursor``/``assault_remaining``: where the current burst is and
  how much of it is left.
- ``_pending_read_addr``: the one outstanding ``READ`` result not yet
  consumed, or ``None`` -- see above.

What you might reasonably change:
- ``SCAN_EVERY``: scanning more often finds cores sooner but claims less.
- ``PROBE_OFFSETS``/``CONFIRM_MIN_HITS``: a wider probe set or a lower
  confirmation threshold commits more readily (more wasted bursts on
  decoys); a stricter one is the reverse.
- ``ASSAULT_WINDOW``/``ASSAULT_ACTIONS``: a wider burst tolerates a worse
  anchor guess at the cost of more actions per commitment.

Not a claim of optimal strategy. A core nobody has written near is
byte-for-byte indistinguishable from untouched arena, so Raider's success
depends on some entrant's ordinary writes having reached the vicinity
first. It will not find every opponent in every match, and against a pure
expansion agent it often loses on territory instead.
"""

from battle_engine.agent_api import ActionKind, AgentAction, MatchContext, Observation

CORE_SIZE_HINT = 8  # public Ruleset knowledge: a vulnerable core is 8 contiguous cells
SCAN_EVERY = 3  # 1 action in every 3 scans; the other 2 claim
PROBE_OFFSETS: tuple[int, ...] = (-8, -4, 4, 8)  # offsets probed around a candidate hit
CONFIRM_MIN_HITS = 2  # candidate hit + this many total foreign observations to assault
ASSAULT_WINDOW = 16  # width of the WRITE burst once confirmed (> CORE_SIZE_HINT)
ASSAULT_ACTIONS = 16


class RaiderAgent:
    def reset(self, context: MatchContext) -> None:
        self.rng = context.rng
        self.arena_size = context.arena_size
        self.signature = 0x7A
        self.own_core_start: int | None = None
        # An equidistribution-friendly irrational scaled to the arena and
        # forced odd, so the scan sequence stays coprime with a power-of-two
        # arena and spreads evenly instead of clustering.
        self.scan_stride = (int(context.arena_size * 0.4142135623730951) | 1) or 1
        # Drawn from this match's RNG so the searched region depends on the
        # seed, not only on arena_size -- a fixed anchor would make the same
        # placements permanently invisible in every match forever.
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
            # observation.pc is exactly this entrant's spawn address, which
            # is also where its own core sits.
            self.expand_cursor = observation.pc % self.arena_size
            self.own_core_start = self.expand_cursor
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

    # -- scan ----------------------------------------------------------------

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

    # -- probe ---------------------------------------------------------------

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
        """Whether ``address`` is inside this agent's own core region.

        Under Ruleset v2 a living entrant's own core always carries a
        non-zero beacon, which would otherwise look exactly like a real
        opponent core and waste a probe/assault cycle on cells this agent
        already owns.
        """

        if self.own_core_start is None:
            return False
        offset = (address - self.own_core_start) % self.arena_size
        return offset < CORE_SIZE_HINT

    def _looks_foreign(self, address: int, value: int | None) -> bool:
        """Whether a ``READ`` result is worth treating as evidence of a target."""

        if value is None or value == 0 or value == self.signature:
            return False
        return not self._in_own_core(address)


def create_agent() -> RaiderAgent:
    return RaiderAgent()
