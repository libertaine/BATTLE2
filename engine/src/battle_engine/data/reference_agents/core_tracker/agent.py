"""Core Tracker -- a v2.0.0-alpha.8 "Vulnerable Core" reference agent.

Experimental/reference only, not a claim of optimal strategy -- see
docs/V2_0_ALPHA8_PLACEMENT_AGNOSTIC_OFFENSE.md for the research question
this agent exists to probe: can an ordinary Agent API v1 entrant locate and
pressure a vulnerable core across substantially different, arbitrary start
placements -- not just the handful of fixed absolute addresses the original
Core Seeker's own schedule happens to pass near -- using only the same
``READ``/``WRITE`` primitives every other agent in this file already uses?

This agent is a distinct, additive sibling of ``core_seeker/agent.py``, not
a replacement or a mutation of it: Core Seeker remains byte-for-byte
unchanged (it is this alpha's historical control, see the docs above), and
both are registered as reference agents so they stay directly comparable in
the same evaluation matrix.

Why a new agent instead of a Core Seeker revision:
alpha.6 (docs/V2_0_ALPHA6_CORE_SEEKER_TIMING.md) and alpha.7
(docs/V2_0_ALPHA7_SPATIAL_CHARACTERIZATION.md) established, by direct
source reading and controlled placement experiments, that Core Seeker's
scan schedule is a fixed absolute permutation of arena addresses
(``scan_cursor0 = arena_size // 3``, stride ``int(arena_size *
0.381_966_011) | 1``) that never depends on anything it observes, its own
spawn, or the current match's seed. Within a 200-tick / 1,600-action
budget that schedule visits at most ~13% of the arena, so it has a genuine,
*reproducible* blind-spot set: the exact same core placements are
unreachable in every single match, regardless of seed, opponent, or
content, purely as a function of ``arena_size``. alpha.7's COLD condition
(three addresses chosen specifically because Core Seeker's own schedule
never gets near them within budget) demonstrated this directly: 0/9
matches produced so much as a partial covering assault window there. This
agent's whole reason for existing is to not have that property.

What "placement-agnostic" means here, precisely, and its real limit:
No non-privileged agent operating under this budget can guarantee finding
every possible core placement -- the arena is far larger than the number
of ``READ``s any agent can afford to spend without abandoning territory
entirely, so *some* coverage ceiling is unavoidable for *any* design, this
one included (see "Search cost and opportunity cost" below). What this
agent changes is *why* a given placement goes undetected: not because it
falls in one fixed, permanently-reproducible gap in an address-only
schedule, but because of an ordinary combination of (a) which subset of
the arena this specific match's scan draws happened to cover, and (b)
whether anything had actually written non-zero content near that placement
by the time this agent's search reached it -- the same fundamental
"content readiness" constraint alpha.6 Sec 13/17 already found governs
Core Seeker's own one success pathway. This agent does not "solve"
content readiness (no non-privileged agent can -- ``Observation`` has no
ownership field, full stop); it changes the *coverage* half of the
equation from "a fixed function of arena_size alone" to "a function of
arena_size and this match's own seed," so the same three addresses are not
permanently invisible to it the way they are to Core Seeker.

The actual information problem (not "find the core" -- "infer a plausible
target from byte content alone"):
``Observation`` exposes no ownership map and no opponent state, only
``last_read``: one raw byte value from this agent's own most recent
``READ``, exactly the same constraint every other agent in this package
already documents (see ``core_seeker/agent.py``'s and
``reactive_core_defender/agent.py``'s docstrings). A single foreign-looking
byte (non-zero, not this agent's own signature) is only very weak evidence
-- it could be one incidental cell from any ordinary entrant's blind
expansion sweep passing through, nowhere near that entrant's actual core.
This agent therefore never commits a full assault burst on one hit alone.
Instead it treats a hit as a *candidate* worth a small number of
additional, genuinely separate ``READ``s at nearby offsets before deciding
whether the evidence looks like a compact region (worth an assault) or an
isolated speck (worth abandoning and resuming the search). This is
imperfect, deliberately: a real opponent's core cell that nothing has ever
written non-zero content to is byte-for-byte indistinguishable from an
untouched arena cell (``python_runtime.seed_core_ownership`` establishes
*ownership* at tick zero by writing the value ``0`` -- see that function's
own docstring), so a core nobody has signed or incidentally overwritten is
invisible to this agent, exactly as it is to Core Seeker and to any other
non-privileged reader. Reported honestly, not hidden: this agent's success
still depends on some entrant's ordinary writes having reached the
vicinity first, same as Core Seeker's one real success pathway.

``CORE_SIZE`` as public ruleset knowledge, used the same way
``core_defender``/``reactive_core_defender`` already use it:
This agent's probe spacing and assault window are sized around
``CORE_SIZE_HINT = 8``, matching ``bytefray-rules-2-alpha1``'s own fixed
``battle_engine.python_runtime.CORE_SIZE``. This is the same "public
knowledge about the Ruleset's rules, not privileged information about any
specific opponent" distinction ``core_defender/agent.py``'s own docstring
already draws for its own ``DEFENDED_RADIUS`` -- an ordinary competitor
reading this Ruleset's own published documentation would know a core is 8
contiguous cells, the same way they would know the arena wraps or how
scoring works. Nothing here reads any opponent's position, identity, or
core address; ``Observation`` exposes none of that, so there would be
nothing to read even if this agent wanted to.

Design chosen, and what was ruled out, in more detail:
Three candidate search shapes were evaluated before this one was written
(see the governing task's own Phase 7 and the alpha.8 doc's design section
for the full comparison): (A) a low-discrepancy broad scan that waits for
two independent hits to fall within a fixed radius before committing --
essentially Core Seeker's own approach, and rejected for the same reason
Core Seeker's own version silently fails: without an explicit
"only-once" rule for a pending read result, an implementation of this
shape reliably degenerates into re-checking the exact same stale
``last_read`` value on every subsequent action (see "Avoiding the
echo-lock defect" below), which is *why* Core Seeker locks onto isolated
noise almost immediately instead of genuinely correlating two separate
hits, and why that root cause has to be fixed structurally, not merely
"used more carefully" in the same broad-scan shape. (C) a "temporal
persistence" design that re-reads the *same* address at two different
times before trusting it, rather than sampling nearby addresses -- ruled
out as strictly weaker evidence for this specific mechanic: a stationary
opponent's core cell does not change value between two re-reads any more
often than it does between one read and a nearby probe, so temporal
re-confirmation buys no extra confidence here while costing an extra
elapsed-time delay a spatial probe does not. (D) continuous "moving-window
reconnaissance" interleaved with ordinary expansion at all times -- not
adopted as a separate, permanently-running mechanism, because the
coarse-to-fine design below already *is* a bounded, on-demand version of
exactly this idea (a short window of extra, spatially-scoped ``READ``s
triggered only when there is already a reason to look closer), without
paying its cost continuously when there is no evidence yet to investigate.
This agent implements (B), coarse-to-fine search, because it is the
design whose false-positive rate and detection latency are both governed
directly by an explicit, inspectable confirmation rule, not by an
accidental implementation quirk of a stale read.

Three states, cycled by a small, traceable state machine (``self.mode``):

    "scan"    -- default. One action in every ``SCAN_EVERY`` is a ``READ``
                 at a slowly advancing scan cursor; the rest are an
                 ordinary outward claiming ``WRITE`` (so scanning is never
                 pure loss when nothing is found -- same trade-off
                 ``core_seeker/agent.py`` already documents for its own
                 scan/expand split). Unlike Core Seeker, this cursor's
                 starting point is drawn from this match's own RNG (see
                 "Why the scan geometry uses RNG" below), not from a fixed
                 arena-size-derived convention.
    "probe"   -- entered the instant a coarse scan ``READ`` returns a
                 foreign-looking byte. Issues a small, fixed set of
                 additional ``READ``s at offsets near that first hit
                 (``PROBE_OFFSETS``) -- coarse-to-fine local investigation,
                 not an immediate commitment. Each probe result is
                 consumed exactly once (see "Avoiding the echo-lock
                 defect"). If at least ``CONFIRM_MIN_HITS`` of the probed
                 addresses (counting the original hit) come back foreign,
                 the evidence is treated as a plausible compact cluster and
                 this agent commits to "assault"; otherwise the candidate
                 is abandoned and ordinary scanning resumes immediately,
                 from exactly where it left off -- never permanently stuck
                 investigating a decoy.
    "assault" -- a fixed ``ASSAULT_ACTIONS``-action ``WRITE`` burst across
                 a window centered on the *refined* estimate from the
                 probe evidence (the midpoint of the confirmed offsets),
                 not just the first raw hit -- one real, if small,
                 advantage coarse-to-fine buys over committing to the very
                 first address that looked foreign. Sized comfortably
                 larger than ``CORE_SIZE_HINT`` to tolerate an imprecise
                 anchor guess, exactly as Core Seeker's own
                 ``ASSAULT_WINDOW`` already does.

Avoiding the echo-lock defect (alpha.6 Sec 4's central finding about the
*existing* Core Seeker, and this alpha's own Phase 8 correctness
requirement):
``observation.last_read`` reflects whichever ``READ`` most recently
completed and is **never cleared** between actions -- confirmed by direct
reading of the same production runtime alpha.6 traced. An implementation
that checks ``last_read`` on every non-scan action (as Core Seeker's own
does) will re-observe the identical stale value on every subsequent call
until the next ``READ`` overwrites it, turning "two independent hits" into
"the same hit re-read against itself" within one or two actions. This
agent avoids that class of bug structurally, not by convention: every
``READ`` this agent issues immediately records the exact address it is
waiting on in ``self._pending_read_addr``; the *very next* ``act()`` call
consumes ``observation.last_read`` as the result for that one specific
address and immediately clears the pending marker before doing anything
else, so a given read result is interpreted exactly once, no matter which
mode this agent is in when the result arrives. Confirmation therefore
always requires a genuinely new ``READ`` at a genuinely different address,
never a re-interpretation of old evidence.

Why the scan geometry uses RNG (Agent API v1 explicitly allows
"deterministic or supplied RNG from MatchContext" for exactly this kind of
choice):
Core Seeker's scan sequence is a pure function of ``arena_size`` --
identical in every match, forever, which is exactly what gives it a fixed,
permanently reproducible blind-spot set (alpha.7's COLD condition). This
agent keeps the same *quality* of scan sequence (a stride coprime to the
arena size, chosen from an equidistribution-friendly irrational -- here
``sqrt(2) - 1``, deliberately a different constant from both Core Seeker's
own ``0.381_966_011`` and Hunter's ``0.618_033_988_749_895``, so this is a
structurally distinct sequence, not a re-tuned copy) but draws its
*starting cursor* from ``context.rng`` at reset time. The stride itself is
deliberately left as the fixed, already-good equidistribution constant
rather than also randomized, because a stride chosen without that
property could accidentally have poor spread (e.g. a rational multiplier
close to a low-order fraction of the arena size clusters visited
addresses instead of spreading them) -- randomizing only the anchor keeps
the proven spread quality while still making the reachable/unreachable set
a function of this match's seed, not of ``arena_size`` alone. This is
still fully deterministic and reproducible for a fixed seed (Phase 6's
"Reproducible" design goal), exactly like every other agent in this
package that seeds anything from ``context.rng``.

Search cost and opportunity cost (Phase 6's "strategically costly" design
goal, deliberately not hidden):
The base scan/expand split (``SCAN_EVERY = 3``) spends exactly the same
one-in-three-actions rate on investigation that Core Seeker's own does, so
the two are directly comparable on baseline cost. On top of that, every
genuine candidate costs ``len(PROBE_OFFSETS)`` further dedicated ``READ``
actions with *no* expansion writes interleaved -- unlike Core Seeker's own
design, where the foreign-check and an ordinary expand write happen in the
very same action, so a false-positive lock is nearly free. A confirmed
cluster then costs a further ``ASSAULT_ACTIONS`` pure-``WRITE`` burst. Both
costs are real, measurable, and reported in this alpha's research
instrumentation (search actions vs. assault actions vs. expansion actions)
rather than asserted.

Important state this agent tracks:
- ``mode``: which of the three states above this agent is in.
- ``scan_cursor``/``scan_stride``, ``expand_cursor``/``expand_stride``:
  independent sweep positions, exactly as ``core_seeker/agent.py`` already
  separates its own scan and expand cursors so neither interferes with the
  other's coverage. ``expand_cursor`` starts at this agent's own spawn
  (``observation.pc``, read once on the first ``act()`` call, exactly the
  technique ``core_defender``/``reactive_core_defender`` already use for
  their own core address) rather than a fixed address, so this agent's own
  expansion does not retrace another bundled agent's exact path.
- ``candidate_hit_addr``: the address of the current unconfirmed
  candidate's first hit, or ``None`` if not currently investigating one.
- ``probe_offsets_remaining`` / ``probe_confirmed_offsets``: which of
  ``PROBE_OFFSETS`` are still queued, and which (relative to
  ``candidate_hit_addr``) have come back foreign so far (``0`` -- the
  original hit -- is always the first entry).
- ``assault_cursor`` / ``assault_remaining``: where the current assault
  burst is and how much of it is left, exactly the same shape as Core
  Seeker's own fields.
- ``_pending_read_addr``: the address of the one outstanding ``READ``
  result this agent has not yet consumed, or ``None`` -- see "Avoiding the
  echo-lock defect" above; this is the field that makes single-use
  consumption structural rather than a matter of remembering to check it.

What you might reasonably change:
- ``PROBE_OFFSETS``/``CONFIRM_MIN_HITS``: a wider probe set or a lower
  confirmation threshold detects more compact regions (fewer missed
  detections) at the cost of more false-positive assaults; a narrower one
  is the reverse.
- ``ASSAULT_WINDOW``/``ASSAULT_ACTIONS``: as in Core Seeker, a wider burst
  tolerates a worse anchor guess at the cost of more actions per
  commitment.
"""

from battle_engine.agent_api import ActionKind, AgentAction, MatchContext, Observation

CORE_SIZE_HINT = 8  # public ruleset knowledge (bytefray-rules-2-alpha1's CORE_SIZE)
SCAN_EVERY = 3  # 1 action in every 3 scans; the other 2 expand -- matches core_seeker's cost
PROBE_OFFSETS: tuple[int, ...] = (-8, -4, 4, 8)  # relative offsets probed around a candidate hit
CONFIRM_MIN_HITS = 2  # candidate hit + at least this many total foreign observations to assault
ASSAULT_WINDOW = 16  # width of the WRITE burst once confirmed (> CORE_SIZE_HINT)
ASSAULT_ACTIONS = 16


class CoreTrackerAgent:
    def reset(self, context: MatchContext) -> None:
        self.rng = context.rng
        self.arena_size = context.arena_size
        self.signature = 0xA5
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
            self.expand_cursor = observation.pc % self.arena_size
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
        if read_addr is not None and self._looks_foreign(read_result):
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
            if self._looks_foreign(read_result) and self._pending_probe_offset is not None:
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

    def _looks_foreign(self, value: int | None) -> bool:
        return value is not None and value != 0 and value != self.signature


def create_agent() -> CoreTrackerAgent:
    return CoreTrackerAgent()
