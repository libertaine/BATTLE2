"""Renderer-independent replay-analysis session.

Loads a canonical (or legacy-compatible) replay file into memory once and
exposes a steppable, seekable cursor over engine-observable reconstructed
state -- arena bytes, ownership, and per-entrant ``AgentState`` -- without
rerunning any agent. This is the reusable reconstruction procedure
documented in ``docs/REPLAY_SCHEMA.md``'s "Memory reconstruction" section:
start from an all-zero ``arena_size`` byte array and apply each tick's
``memory_diffs`` values in tick order. Legacy v0.1/v0.2 diffs never
captured byte content (``MemoryDiff.values`` is empty for them), so arena
bytes cannot be reconstructed for a legacy replay -- but ``owner``/
``address``/``length`` are still present, so ownership reconstruction
still works for one.

``ReplaySession`` only depends on ``battle_engine.replay``'s public typed
reader (``iter_replay``); it does not parse JSONL itself and does not know
about any renderer or timing/pacing concern -- it is a synchronous,
deterministic state-navigation model only.

Tick identity: canonical native replays (``match.py``/``python_runtime.py``)
publish every integer tick from 0 through the match's actual final tick
with no gaps, so ``seek`` can reach any tick in range on a canonical
replay. ``load`` requires tick numbers to be strictly increasing (a
duplicate or decreasing tick number is rejected as a corrupt/hand-edited
replay -- see ``ReplaySessionError``), but does not require *contiguity*:
a legacy v0.1/v0.2 replay may legitimately record a sparse subset of ticks
(e.g. only ticks with an event), and ``seek`` to a tick number that falls
in a gap between two recorded ticks raises rather than fabricating
interpolated state.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from battle_engine.replay import (
    AgentState,
    EngineEvent,
    MatchResult,
    ReplayHeader,
    RuntimeKind,
    TickSnapshot,
    iter_replay,
)


class ReplaySessionError(ValueError):
    """A replay could not be loaded into, or navigated within, a session."""


@dataclass(frozen=True)
class ReplayState:
    """Reconstructed engine-observable state at one tick.

    ``agents`` and ``score`` are read-only views (``MappingProxyType``)
    over a private copy: mutating them raises ``TypeError``, and even a
    successful in-place mutation of ``arena``/``owners`` (immutable
    ``bytes``/``tuple`` already) could not affect the session's own
    internal state or any later ``step_forward``/``seek``/``restart``,
    since every field here is copied out of the session on access.

    ``runtime_kind`` makes the state self-describing: a consumer (for
    example a future renderer) can tell whether ``AgentState.pc``/
    ``region``/``cpu_used`` mean the VM's real fetch address/code
    footprint/instruction count, or the Python runtime's controller
    bookkeeping/degenerate marker/callback count, without a separate call
    back into the session -- see the runtime-kind semantics table in
    ``docs/REPLAY_SCHEMA.md``.
    """

    tick: int
    arena: bytes
    owners: tuple[str | None, ...]
    agents: Mapping[str, AgentState]
    score: Mapping[str, int | float]
    runtime_kind: RuntimeKind | None


class ReplaySession:
    """One explicit playback cursor over a fully buffered canonical replay.

    Matches at v0.3 scale (a few thousand ticks, a few KB of arena) are
    small enough that full buffering is both simple and fast; see the Phase
    7 readiness review for the sizing rationale. ``step_forward`` applies
    only the next tick's diffs on top of the existing reconstructed state
    (O(1) amortized), rather than replaying from tick 0 on every call.
    ``seek`` generalizes this: a forward seek (target tick at or after the
    current one) applies only the intervening ticks; a backward seek resets
    to the canonical tick-0 state and replays forward. Either way, the
    resulting state depends only on the target tick, never on how the
    cursor got there -- there is deliberately no per-tick snapshot cache or
    separate cursor/timeline/index class; full buffering plus incremental
    replay from the nearest known state is simple, correct, and fast
    enough at this scale without one.
    """

    def __init__(self) -> None:
        self.header: ReplayHeader | None = None
        self.result: MatchResult | None = None
        self._ticks: tuple[TickSnapshot, ...] = ()
        self._tick_index: dict[int, int] = {}
        self._cursor: int = -1
        self._arena = bytearray()
        self._owners: list[str | None] = []
        self._agents: dict[str, AgentState] = {}
        self._score: dict[str, int | float] = {}

    # ---------- loading ----------

    def load(self, path: str | Path) -> None:
        """Read every record from ``path`` and position at its first tick.

        Raises ``ReplaySessionError`` if the replay has no header record,
        more than one header/result record, or a tick number that is not
        strictly greater than the tick before it (a duplicate or
        out-of-order tick -- with ``seek`` now available, tick numbers must
        identify exactly one deterministic state, so this is treated as a
        corrupt/hand-edited replay rather than tolerated). Gaps between
        strictly-increasing tick numbers are allowed: canonical replays
        never have them, but a legacy replay legitimately can.

        Malformed JSON or an unsupported/truncated record propagates the
        reader's own ``battle_engine.replay.ReplayFormatError`` unchanged --
        this method never swallows a read failure into a partial,
        silently-incomplete session. On any error, any previously loaded
        session state is left untouched, since the new state is only
        installed after a full, successful read.
        """
        header: ReplayHeader | None = None
        ticks: list[TickSnapshot] = []
        result: MatchResult | None = None
        for record in iter_replay(path):
            if isinstance(record, ReplayHeader):
                if header is not None:
                    raise ReplaySessionError(f"{path}: replay has more than one header record")
                header = record
            elif isinstance(record, TickSnapshot):
                if ticks and record.tick <= ticks[-1].tick:
                    raise ReplaySessionError(
                        f"{path}: tick {record.tick} is not strictly greater than "
                        f"the preceding recorded tick {ticks[-1].tick} "
                        "(duplicate or out-of-order ticks are rejected)"
                    )
                ticks.append(record)
            elif isinstance(record, MatchResult):
                if result is not None:
                    raise ReplaySessionError(f"{path}: replay has more than one result record")
                result = record
        if header is None:
            raise ReplaySessionError(f"{path}: replay has no header record")

        self.header = header
        self.result = result
        self._ticks = tuple(ticks)
        # Tick numbers are strictly increasing (validated above), so each
        # one maps to exactly one index into `_ticks`.
        self._tick_index = {snapshot.tick: index for index, snapshot in enumerate(ticks)}
        self._reset_state()
        if self._ticks:
            self._apply(0)

    @property
    def loaded(self) -> bool:
        return self.header is not None

    # ---------- state ----------

    @property
    def current_state(self) -> ReplayState:
        self._require_loaded()
        return ReplayState(
            tick=self.current_tick,
            arena=bytes(self._arena),
            owners=tuple(self._owners),
            agents=MappingProxyType(dict(self._agents)),
            score=MappingProxyType(dict(self._score)),
            runtime_kind=self.runtime_kind,
        )

    @property
    def current_tick(self) -> int:
        """The tick number the session is currently positioned at.

        ``0`` before any tick has been applied (an empty, header-only
        replay), matching the "tick 0 is the initial state" convention --
        even though, in that specific edge case, there is no actual tick-0
        *record* to point at.
        """
        self._require_loaded()
        return self._ticks[self._cursor].tick if self._cursor >= 0 else 0

    @property
    def final_tick(self) -> int | None:
        """The last recorded tick number, or ``None`` if the replay has no
        tick records at all."""
        self._require_loaded()
        return self._ticks[-1].tick if self._ticks else None

    @property
    def recorded_ticks(self) -> tuple[int, ...]:
        """All recorded tick numbers, in increasing order.

        For a canonical replay this is exactly every integer from 0 through
        ``final_tick`` (see the module docstring); for a sparse legacy
        replay it may have gaps. Exposed so a UI/playback controller can
        navigate to the previous/next *recorded* tick -- e.g. for arrow-key
        stepping through a replay that might be sparse -- without guessing
        a tick number and catching ``ReplaySessionError`` from ``seek``.
        """
        self._require_loaded()
        return tuple(snapshot.tick for snapshot in self._ticks)

    @property
    def at_end(self) -> bool:
        self._require_loaded()
        return self._cursor >= len(self._ticks) - 1

    @property
    def winner(self) -> str | None:
        return None if self.result is None else self.result.winner

    @property
    def termination_reason(self) -> str | None:
        return None if self.result is None else self.result.termination_reason

    @property
    def runtime_kind(self) -> RuntimeKind | None:
        return None if self.header is None else self.header.runtime_kind

    def events_at_tick(self, tick: int) -> tuple[EngineEvent, ...]:
        self._require_loaded()
        index = self._tick_index.get(tick)
        if index is None:
            raise ReplaySessionError(f"no tick {tick} in this replay")
        return self._ticks[index].events

    # ---------- playback ----------

    def step_forward(self) -> ReplayState:
        """Advance exactly one recorded tick, applying only its diffs."""
        self._require_loaded()
        if self.at_end:
            raise ReplaySessionError("already at the final tick")
        self._apply(self._cursor + 1)
        return self.current_state

    def seek(self, tick: int) -> ReplayState:
        """Move the cursor to the exact recorded tick ``tick``.

        A forward seek (``tick`` at or after the current one) applies only
        the intervening ticks' diffs on top of the existing state. A
        backward seek resets to the canonical tick-0 state and replays
        forward to ``tick``. Either way, the resulting state is fully
        determined by ``tick`` alone -- never by the cursor's prior
        history (see the determinism tests in ``test_replay_session.py``).

        Raises ``ReplaySessionError`` if the replay has no tick records,
        if ``tick`` is outside the replay's recorded range (below the
        first recorded tick or above the last), or if ``tick`` falls in a
        gap between two recorded ticks -- possible only for a sparse
        legacy replay, since canonical replays record every integer tick
        with no gaps. No state is fabricated for an unrecorded tick.
        """
        self._require_loaded()
        if not self._ticks:
            raise ReplaySessionError("replay has no tick records to seek within")
        first_tick = self._ticks[0].tick
        last_tick = self._ticks[-1].tick
        if tick < first_tick or tick > last_tick:
            raise ReplaySessionError(
                f"tick {tick} is outside the replay's recorded range "
                f"[{first_tick}, {last_tick}]"
            )
        target_index = self._tick_index.get(tick)
        if target_index is None:
            raise ReplaySessionError(
                f"tick {tick} was not recorded in this replay (sparse legacy replay)"
            )

        if target_index >= self._cursor:
            for index in range(self._cursor + 1, target_index + 1):
                self._apply(index)
        else:
            self._reset_state()
            for index in range(target_index + 1):
                self._apply(index)
        return self.current_state

    def restart(self) -> ReplayState:
        """Reset the cursor to the replay's first tick (its published
        initial state), or to a synthesized empty tick 0 for a replay with
        no tick records at all.
        """
        self._require_loaded()
        self._reset_state()
        if self._ticks:
            self._apply(0)
        return self.current_state

    # ---------- internals ----------

    def _require_loaded(self) -> None:
        if self.header is None:
            raise ReplaySessionError("no replay loaded")

    def _reset_state(self) -> None:
        assert self.header is not None
        arena_size = self.header.config.arena_size
        self._arena = bytearray(arena_size)
        self._owners = [None] * arena_size
        self._agents = {}
        self._score = {}
        self._cursor = -1

    def _apply(self, index: int) -> None:
        """Apply ``self._ticks[index]``'s diffs on top of the current state."""
        snapshot = self._ticks[index]
        arena_size = len(self._arena)
        for diff in snapshot.memory_diffs:
            if diff.values:
                for offset, value in enumerate(diff.values):
                    address = (diff.address + offset) % arena_size
                    self._arena[address] = value
                    self._owners[address] = diff.owner
            else:
                # Legacy v0.1/v0.2 diffs never captured byte content, so
                # arena bytes cannot be reconstructed for them -- but
                # address/length/owner are still known, so ownership can be.
                for offset in range(diff.length):
                    address = (diff.address + offset) % arena_size
                    self._owners[address] = diff.owner
        for agent in snapshot.agents:
            self._agents[agent.agent_id] = agent
        self._score = dict(snapshot.score)
        self._cursor = index
