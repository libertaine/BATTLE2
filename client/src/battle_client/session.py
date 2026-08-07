"""Renderer-independent replay-analysis session.

Loads a canonical (or legacy-compatible) replay file into memory once and
exposes a steppable cursor over engine-observable reconstructed state --
arena bytes, ownership, and per-entrant ``AgentState`` -- without rerunning
any agent. This is the reusable reconstruction procedure documented in
``docs/REPLAY_SCHEMA.md``'s "Memory reconstruction" section: start from an
all-zero ``arena_size`` byte array and apply each tick's ``memory_diffs``
values in tick order. Legacy v0.1/v0.2 diffs never captured byte content
(``MemoryDiff.values`` is empty for them), so arena bytes cannot be
reconstructed for a legacy replay -- but ``owner``/``address``/``length``
are still present, so ownership reconstruction still works for one.

``ReplaySession`` only depends on ``battle_engine.replay``'s public typed
reader (``iter_replay``); it does not parse JSONL itself and does not know
about any renderer. Seeking to an arbitrary tick is intentionally out of
scope here -- see the Phase 7a slice plan.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

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
    """Reconstructed engine-observable state at one tick."""

    tick: int
    arena: bytes
    owners: tuple[str | None, ...]
    agents: Mapping[str, AgentState]
    score: Mapping[str, int | float]


class ReplaySession:
    """One explicit playback cursor over a fully buffered canonical replay.

    Matches at v0.3 scale (a few thousand ticks, a few KB of arena) are
    small enough that full buffering is both simple and fast; see the Phase
    7 readiness review for the sizing rationale. ``step_forward`` applies
    only the next tick's diffs on top of the existing reconstructed state
    (O(1) amortized), rather than replaying from tick 0 on every call.
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

        Raises ``ReplaySessionError`` if the replay has no header record or
        more than one header/result record. Malformed JSON or an
        unsupported/truncated record propagates the reader's own
        ``battle_engine.replay.ReplayFormatError`` unchanged -- this method
        never swallows a read failure into a partial, silently-incomplete
        session. On any error, any previously loaded session state is left
        untouched, since the new state is only installed after a full,
        successful read.
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
        # Last occurrence wins for a duplicate/out-of-order tick number; the
        # index into `_ticks` (file order), not the tick number, is what
        # step_forward advances through.
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
        tick_number = self._ticks[self._cursor].tick if self._cursor >= 0 else 0
        return ReplayState(
            tick=tick_number,
            arena=bytes(self._arena),
            owners=tuple(self._owners),
            agents=dict(self._agents),
            score=dict(self._score),
        )

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
