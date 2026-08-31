"""Viper -- an asymmetric phase-switching infiltrator for Ruleset v2.

Strategy:
Viper runs three phases plus one standing interrupt, switching among them by
what it has actually observed rather than by a fixed schedule:

    Phase 0 -- Opening & Expansion. A claiming sweep like Claimer's, but
        stepped by a stride that is always coprime with the arena size
        (default EXPANSION_STRIDE = 13, nudged upward -- staying odd -- if
        the arena size ever happens to share a factor with it) so the sweep
        touches every cell exactly once before it ever repeats, instead of
        cycling through a small subset the way a non-coprime stride would
        under a composite arena size.
    Phase 1 -- Probing & Triangulation. One action in every SCAN_EVERY,
        interleaved with expansion, is a READ at a slowly advancing scan
        cursor instead of a claiming WRITE. A single foreign-looking byte
        (neither blank nor Viper's own signature, and outside Viper's own
        core) is weak evidence on its own, so a hit opens a short
        triangulation burst -- READs at PROBE_OFFSETS around the hit -- and
        only a cluster of CONFIRM_MIN_HITS or more foreign cells is treated
        as a located hostile core.
    Phase 2 -- Assault / Kill-Lock. Once triangulated, Viper commits: every
        offensive action for the rest of the match is a WRITE somewhere in
        the confirmed target window, cycling through it and never returning
        to scanning. Ruleset v2's Agent API gives no elimination signal --
        no agent ever learns that an opponent has died (see
        docs/AGENT_API_V1.md / docs/RULES_V2.md) -- so "until elimination"
        is realized as "forever" rather than as a countdown: there is no
        stopping condition Viper could check even if it wanted one, so it
        never voluntarily leaves the lock once acquired.
    Interrupt -- Reactive Core Defense. Independent of the expand and
        assault phases, one action in every DEFENSE_EVERY is a READ of the
        next cell of Viper's own core in rotation, taking priority over
        whatever that phase would otherwise have done. Only if that cell
        comes back neither blank, nor the public CORE_BEACON_BYTE, nor
        Viper's own signature -- i.e. actually overwritten by someone else
        -- does Viper spend its very next action repairing exactly that
        cell before resuming whatever phase it was in. The one exception is
        Phase 1's short, bounded triangulation burst (at most
        ``len(PROBE_OFFSETS)`` consecutive calls): a candidate under active
        triangulation is investigated to completion before the defense
        cadence is consulted again, so a compromised cell is patched within
        DEFENSE_EVERY actions of the check that finds it, plus at most one
        triangulation burst's delay if that burst happens to be in flight
        when the check would otherwise have fired.

Why Ruleset v2 (``bytefray-rules-2``) and Agent API v1, rather than Ruleset
v4 alpha1 and Agent API v2: this design's home-core defense and
enemy-core assault both depend on the Vulnerable Core mechanic
(docs/RULES_V2.md), which is a ``bytefray-rules-2`` gameplay rule realized
entirely as ordinary arena bytes under Agent API v1 -- there is no
``core_status`` observation field under any Ruleset (see "Important Agent
API behavior" below). Agent API v2's ``ObservationV2``
(docs/AGENT_API_V2.md) exposes an entrant's own core location/size for
movement purposes but has no opposing-core or elimination concept at all,
and its Ruleset (``bytefray-rules-4-alpha1``) cannot run in the same match
as an Agent API v1 opponent such as ``claimer`` (API v1 and API v2 entrants
cannot be mixed) -- so ``bytefray-rules-2`` is the only one of the two that
actually supports both this strategy and the requested
``--opponent claimer`` development test.

Important Agent API behavior this agent demonstrates:
``observation.pc``, read on the very first ``act()`` call before this agent
has ever issued a ``JUMP``, is exactly this entrant's own spawn address --
which is also where its own core sits (see ``agents/sentinel``,
``agents/raider``). Every ``READ`` this agent issues records the exact
address (and, while triangulating, offset) it is waiting on, so the very
next ``act()`` call consumes ``observation.last_read`` exactly once, never
mistaking one stale value for several. ``Observation`` carries no ownership
map and no ``arena_size`` -- Viper reads ``arena_size`` once from
``MatchContext`` at ``reset()`` and uses a signature byte to recognize its
own already-claimed cells.

Important state this agent tracks:
- ``signature``: this agent's own claim byte (0x76), written to every cell
  it claims and to its own core when repairing it.
- ``core_start``: this agent's own core anchor, captured once from
  ``observation.pc``.
- ``phase``: ``"expand"``, ``"probe"``, or ``"assault"`` -- Phases 0/1/2
  above; the defense interrupt is not itself a phase, it pre-empts whichever
  phase is current for exactly one action at a time.
- ``expand_cursor``/``expand_stride``: the coprime-stride claiming sweep.
- ``scan_cursor``/``scan_stride``: an independent sweep used only for
  probing READs, seeded from ``context.rng`` so which part of the arena
  gets searched depends on the match seed.
- ``candidate_hit_addr``/``probe_offsets_remaining``/
  ``probe_confirmed_offsets``: the candidate currently under triangulation.
- ``assault_window_start``/``assault_cursor``: where the permanent
  kill-lock burst is currently writing.
- ``defend_index``: which of the ``CORE_SIZE`` own core cells the next
  reactive defense check will read.
- ``_pending_read``: ``(tag, address)`` for the one outstanding ``READ``
  not yet consumed, or ``None``; ``tag`` is ``"scan"``, ``"probe"``, or
  ``"defense"`` so the same one-read-in-flight slot serves all three
  READ-issuing behaviors above without conflating their results.

What you might reasonably change:
- ``EXPANSION_STRIDE``: the Phase 0 sweep step (auto-adjusted to stay
  coprime with ``arena_size``).
- ``SCAN_EVERY``/``PROBE_OFFSETS``/``CONFIRM_MIN_HITS``: how eagerly Phase 1
  commits to a candidate, exactly like Raider's own dials.
- ``DEFENSE_EVERY``: how often the standing interrupt checks home-core
  integrity; smaller catches an attack sooner at a higher cost in
  expansion/assault throughput, exactly like Sentinel's ``REFRESH_EVERY``.

Not a claim of optimal strategy: committing permanently to one confirmed
target (Phase 2) means Viper cannot recover from ever misjudging a
triangulated location, and the reactive defense interrupt costs real budget
on every check whether or not anything is actually wrong -- the same
honest trade-offs Sentinel and Raider each document independently, now
combined in one agent.
"""

from __future__ import annotations

import math

from battle_engine.agent_api import ActionKind, AgentAction, MatchContext, Observation

CORE_SIZE = 8  # public Ruleset knowledge: a vulnerable core is 8 contiguous cells
CORE_BEACON_BYTE = 0xCE  # public Ruleset knowledge: an owned, undefended core cell reads this

EXPANSION_STRIDE = 13  # Phase 0: default coprime stride
SCAN_EVERY = 5  # Phase 1: 1 action in every 5 probes instead of expanding
PROBE_OFFSETS: tuple[int, ...] = (-8, -4, 4, 8)  # triangulation offsets around a hit
CONFIRM_MIN_HITS = 2  # candidate hit + this many total foreign observations to assault
ASSAULT_WINDOW = 16  # width of the Phase 2 kill-lock window (> CORE_SIZE)
DEFENSE_EVERY = 6  # Interrupt: 1 action in every 6 checks home-core integrity


def _coprime_stride(base: int, modulus: int) -> int:
    """Smallest value >= ``base`` (odd-stepped) that is coprime with ``modulus``.

    ``modulus`` (``arena_size``) is fixed per match and always >= 2 in
    practice, so this always terminates: odd steps alone reach a coprime
    value in at most ``modulus`` iterations.
    """

    if modulus <= 1:
        return base
    stride = base if base % 2 else base + 1
    while math.gcd(stride, modulus) != 1:
        stride += 2
    return stride


class ViperAgent:
    def reset(self, context: MatchContext) -> None:
        self.rng = context.rng
        self.arena_size = context.arena_size
        self.signature = 0x76

        self.core_start: int | None = None
        self.expand_cursor = 0
        self.expand_stride = _coprime_stride(EXPANSION_STRIDE, context.arena_size)

        # An equidistribution-friendly irrational scaled to the arena, then
        # nudged coprime -- the scan sequence spreads evenly instead of
        # clustering or repeating early.
        scan_seed = int(context.arena_size * 0.4142135623730951) or 1
        self.scan_stride = _coprime_stride(scan_seed, context.arena_size)
        # Drawn from this match's RNG so the searched region depends on the
        # seed, not only on arena_size.
        self.scan_cursor = context.rng.randrange(context.arena_size)

        self.phase = "expand"
        self.actions_taken = 0

        self.candidate_hit_addr: int | None = None
        self.probe_offsets_remaining: list[int] = []
        self.probe_confirmed_offsets: list[int] = []
        self._pending_probe_offset: int | None = None

        self.assault_window_start: int | None = None
        self.assault_cursor = 0

        self.defend_index = 0

        self._pending_read: tuple[str, int] | None = None

    def act(self, observation: Observation) -> AgentAction:
        if self.core_start is None:
            # First call, before this agent has ever moved its own pc:
            # observation.pc is exactly this entrant's spawn address, which
            # is also where its own core sits.
            self.core_start = observation.pc % self.arena_size
            self.expand_cursor = (self.core_start + CORE_SIZE) % self.arena_size

        tag: str | None = None
        read_addr: int | None = None
        read_value: int | None = None
        if self._pending_read is not None:
            tag, read_addr = self._pending_read
            read_value = observation.last_read
            self._pending_read = None  # consumed exactly once

        if tag == "defense":
            assert read_addr is not None  # tag is only set alongside its address
            if self._is_core_compromised(read_value):
                return self._repair(read_addr)
        elif tag == "scan":
            assert read_addr is not None  # tag is only set alongside its address
            if self._is_enemy_evidence(read_addr, read_value):
                return self._begin_probe(read_addr)
        elif tag == "probe":
            action = self._continue_probe(read_addr, read_value)
            if action is not None:
                return action
            # else: candidate abandoned, phase reset to "expand" -- fall
            # through to this call's ordinary cadence below.

        self.actions_taken += 1
        if self.actions_taken % DEFENSE_EVERY == 0:
            return self._issue_defense_check()

        if self.phase == "assault":
            return self._assault_step()

        if self.actions_taken % SCAN_EVERY == 0:
            return self._issue_scan()
        return self._expand_step()

    # -- Phase 0: expansion ----------------------------------------------------

    def _expand_step(self) -> AgentAction:
        address = self.expand_cursor
        self.expand_cursor = (self.expand_cursor + self.expand_stride) % self.arena_size
        return AgentAction(ActionKind.WRITE, address, self.signature)

    # -- Phase 1: probing & triangulation ---------------------------------------

    def _issue_scan(self) -> AgentAction:
        address = self.scan_cursor
        self.scan_cursor = (self.scan_cursor + self.scan_stride) % self.arena_size
        self._pending_read = ("scan", address)
        return AgentAction(ActionKind.READ, address)

    def _begin_probe(self, hit_addr: int) -> AgentAction:
        self.phase = "probe"
        self.candidate_hit_addr = hit_addr
        self.probe_confirmed_offsets = [0]  # the original hit counts as evidence
        self.probe_offsets_remaining = list(PROBE_OFFSETS)
        return self._issue_probe_next()

    def _issue_probe_next(self) -> AgentAction:
        assert self.candidate_hit_addr is not None
        offset = self.probe_offsets_remaining.pop(0)
        address = (self.candidate_hit_addr + offset) % self.arena_size
        self._pending_read = ("probe", address)
        self._pending_probe_offset = offset
        return AgentAction(ActionKind.READ, address)

    def _continue_probe(
        self, read_addr: int | None, read_value: int | None
    ) -> AgentAction | None:
        if read_addr is not None:
            if (
                self._is_enemy_evidence(read_addr, read_value)
                and self._pending_probe_offset is not None
            ):
                self.probe_confirmed_offsets.append(self._pending_probe_offset)
            self._pending_probe_offset = None

        if self.probe_offsets_remaining:
            return self._issue_probe_next()

        if len(self.probe_confirmed_offsets) >= CONFIRM_MIN_HITS:
            return self._begin_assault()

        self.phase = "expand"
        self.candidate_hit_addr = None
        self.probe_confirmed_offsets = []
        return None

    # -- Phase 2: assault / kill-lock -------------------------------------------

    def _begin_assault(self) -> AgentAction:
        assert self.candidate_hit_addr is not None
        mid_offset = (
            min(self.probe_confirmed_offsets) + max(self.probe_confirmed_offsets)
        ) // 2
        anchor = (self.candidate_hit_addr + mid_offset) % self.arena_size
        self.candidate_hit_addr = None
        self.probe_confirmed_offsets = []
        self.probe_offsets_remaining = []
        self.phase = "assault"
        self.assault_window_start = (anchor - ASSAULT_WINDOW // 2) % self.arena_size
        self.assault_cursor = 0
        return self._assault_step()

    def _assault_step(self) -> AgentAction:
        assert self.assault_window_start is not None
        address = (self.assault_window_start + self.assault_cursor) % self.arena_size
        self.assault_cursor = (self.assault_cursor + 1) % ASSAULT_WINDOW
        return AgentAction(ActionKind.WRITE, address, self.signature)

    # -- Interrupt: reactive home-core defense ----------------------------------

    def _issue_defense_check(self) -> AgentAction:
        assert self.core_start is not None
        address = (self.core_start + self.defend_index) % self.arena_size
        self.defend_index = (self.defend_index + 1) % CORE_SIZE
        self._pending_read = ("defense", address)
        return AgentAction(ActionKind.READ, address)

    def _repair(self, address: int) -> AgentAction:
        return AgentAction(ActionKind.WRITE, address, self.signature)

    # -- shared ------------------------------------------------------------------

    def _in_own_core(self, address: int) -> bool:
        if self.core_start is None:
            return False
        offset = (address - self.core_start) % self.arena_size
        return offset < CORE_SIZE

    def _is_enemy_evidence(self, address: int | None, value: int | None) -> bool:
        """Whether a Phase 1 ``READ`` result is worth treating as hostile evidence.

        Deliberately does *not* exclude ``CORE_BEACON_BYTE``: a living
        opponent's own undefended core reads exactly that value (see
        docs/RULES_V2.md), and content-based searches are meant to observe
        it as suspicious for free.
        """

        if address is None or value is None:
            return False
        if value == 0 or value == self.signature:
            return False
        return not self._in_own_core(address)

    def _is_core_compromised(self, value: int | None) -> bool:
        """Whether an Interrupt ``READ`` of one of Viper's own core cells shows
        someone else's write.

        Blank (``0``) is deliberately not treated as compromised: Ruleset
        v2 restores a still-owned core cell's blank byte to
        ``CORE_BEACON_BYTE`` at end of tick without Viper spending an
        action, so a blank reading is either transient or already handled.
        """

        if value is None:
            return False
        return value not in (0, self.signature, CORE_BEACON_BYTE)


def create_agent() -> ViperAgent:
    return ViperAgent()
