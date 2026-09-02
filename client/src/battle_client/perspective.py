"""Client integration and lifecycle management for spectator perspective.

Integrates the qualified Phase 4 deterministic perspective projection into the
replay viewer as an independent, parallel playback state layer. ReplaySession
remains canonical-replay-only and is never modified by this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from battle_engine.spectator_derivation import (
    SpectatorDerivation,
    analyze_pair,
)
from battle_engine.spectator_perspective import (
    ContactKnowledge,
    KnowledgeStatus,
    OwnProcessKnowledge,
    PerspectiveCursor,
    PerspectiveError,
    PerspectiveProjection,
    PerspectiveState,
    ReadKnowledge,
    TickBoundary,
    project_perspective,
)

BROADCAST_MODE = "broadcast"


@dataclass(frozen=True)
class PerspectiveAvailability:
    """Availability status of entrant perspective projection for a replay."""

    available: bool
    status_message: str
    derivation: SpectatorDerivation | None = None
    error: Exception | None = None


class PerspectiveManager:
    """Manages perspective availability, entrant projections, and active view mode.

    ReplaySession remains canonical-replay-only; this class coordinates the
    corresponding perspective projection by tick when a valid bound trace is
    present.

    Availability and the entrant roster come from the cheap, shared
    prerequisite -- ``verify_pair`` plus ``derive_events`` (``analyze_pair``)
    -- which is run once, eagerly, in the constructor. Building one entrant's
    actual knowledge projection (``project_perspective``, which walks every
    one of that entrant's callbacks) is comparatively expensive and scales
    with both match length and entrant count, so it is deferred until that
    entrant is first selected as the active view mode. A projection that is
    built is retained for the life of the manager, so switching back to an
    already-visited entrant never repeats the cost.
    """

    def __init__(
        self,
        replay_path: Path,
        trace_path: Path | None = None,
        *,
        initial_mode: str = BROADCAST_MODE,
    ) -> None:
        self.replay_path = replay_path
        self.trace_path = trace_path
        self._availability = self._probe_availability()
        self._projections: dict[str, PerspectiveProjection] = {}
        self._cursors: dict[str, PerspectiveCursor] = {}
        self._load_errors: dict[str, Exception] = {}
        self._mode = BROADCAST_MODE

        if (
            self._availability.available
            and initial_mode != BROADCAST_MODE
            and self.is_mode_valid(initial_mode)
        ):
            self.set_mode(initial_mode)

    def _probe_availability(self) -> PerspectiveAvailability:
        if self.trace_path is None:
            return PerspectiveAvailability(
                available=False,
                status_message="Perspective Cam unavailable: no trace supplied.",
            )
        if not self.trace_path.exists():
            return PerspectiveAvailability(
                available=False,
                status_message=f"Perspective Cam unavailable: trace not found: {self.trace_path}",
            )
        try:
            derivation = analyze_pair(self.replay_path, self.trace_path)
            entrant_count = len(derivation.binding.entrant_identities)
            return PerspectiveAvailability(
                available=True,
                status_message=f"Perspective Cam available ({entrant_count} entrants).",
                derivation=derivation,
            )
        except Exception as exc:
            return PerspectiveAvailability(
                available=False,
                status_message=f"Perspective Cam unavailable: {exc}",
                error=exc,
            )

    @property
    def available(self) -> bool:
        """Whether a valid matching trace was loaded and projected."""
        return self._availability.available

    @property
    def status_message(self) -> str:
        """Human-readable availability message or failure reason."""
        return self._availability.status_message

    @property
    def error(self) -> Exception | None:
        """Underlying exception if perspective loading failed."""
        return self._availability.error

    @property
    def entrants(self) -> tuple[str, ...]:
        """All entrant identities available for perspective viewing.

        Reflects the trace's validated entrant roster (from the shared,
        eagerly-checked pair binding), independent of whether any given
        entrant's knowledge projection has actually been built yet.
        """
        if not self.available or self._availability.derivation is None:
            return ()
        return tuple(sorted(self._availability.derivation.binding.entrant_identities))

    @property
    def derivation(self) -> SpectatorDerivation | None:
        """The already-verified, already-derived event stream, if available.

        This is the same ``SpectatorDerivation`` produced once by
        ``_probe_availability``'s ``analyze_pair`` call -- exposed so a
        second consumer (the spectator Director) can build its plans from it
        directly instead of re-running ``verify_pair``/``derive_events``,
        which costs seconds on a large match (see the Phase 6 research
        document's `analyze_pair` timing). ``None`` when perspective is
        unavailable.
        """
        return self._availability.derivation

    @property
    def mode(self) -> str:
        """Current view mode: 'broadcast' or an entrant identity string."""
        return self._mode

    def is_mode_valid(self, mode: str) -> bool:
        """Whether `mode` names a real entrant in the bound trace (or broadcast).

        This is a cheap roster-membership check; it does not attempt to
        build that entrant's projection, so it says nothing about whether
        loading it would actually succeed. Use :meth:`set_mode`'s return
        value for that.
        """
        if mode == BROADCAST_MODE:
            return True
        return self.available and mode in self.entrants

    def load_error_for(self, entrant_id: str) -> Exception | None:
        """The lazy-load failure recorded for one entrant, if any."""
        return self._load_errors.get(entrant_id)

    def _ensure_loaded(self, entrant_id: str) -> bool:
        """Lazily build and cache one entrant's projection and cursor.

        Deferred here rather than built eagerly for every entrant: on a long
        match, ``project_perspective`` walks every one of that entrant's
        callbacks, and the interactive viewer usually only ever looks at one
        or two entrants per session. A projection that is built is retained
        for the life of the manager. A load failure is cached too (as a
        recorded error, not retried), so a broken entrant's trace does not
        raise repeatedly on every switch attempt.
        """
        if entrant_id in self._cursors:
            return True
        if entrant_id in self._load_errors:
            return False
        derivation = self._availability.derivation
        if derivation is None:
            return False
        try:
            projection = project_perspective(derivation, entrant_id)
        except Exception as exc:
            self._load_errors[entrant_id] = exc
            return False
        self._projections[entrant_id] = projection
        self._cursors[entrant_id] = projection.cursor()
        return True

    def set_mode(self, mode: str) -> bool:
        """Set active view mode. Returns True if mode was updated successfully.

        For an entrant mode, this triggers that entrant's lazy projection
        load on first selection. Returns False, leaving the mode unchanged,
        if ``mode`` does not name a real entrant or if loading it fails; call
        :meth:`load_error_for` to distinguish the latter case.
        """
        if not self.is_mode_valid(mode):
            return False
        if mode != BROADCAST_MODE and not self._ensure_loaded(mode):
            return False
        self._mode = mode
        return True

    def cycle_mode(self) -> str:
        """Cycle through: broadcast -> Entrant 1 -> Entrant 2 -> ... -> broadcast.

        A candidate entrant whose lazy load fails is skipped back to
        broadcast rather than leaving the cycle stuck on an unusable mode.
        """
        roster = self.entrants
        if not self.available or not roster:
            self._mode = BROADCAST_MODE
            return self._mode

        modes = [BROADCAST_MODE, *roster]
        try:
            current_index = modes.index(self._mode)
            next_index = (current_index + 1) % len(modes)
        except ValueError:
            next_index = 0
        candidate = modes[next_index]
        if not self.set_mode(candidate):
            self.set_mode(BROADCAST_MODE)
        return self._mode

    def state_at_tick(
        self, tick: int, *, boundary: TickBoundary = TickBoundary.END
    ) -> PerspectiveState | None:
        """Return the current entrant's perspective state, or None in broadcast mode."""
        if self._mode == BROADCAST_MODE or not self.available:
            return None
        cursor = self._cursors.get(self._mode)
        if cursor is None:
            return None
        return cursor.state_at_tick(tick, boundary=boundary)

    def projection_for(self, entrant_id: str) -> PerspectiveProjection | None:
        """Return the immutable PerspectiveProjection for one entrant if loaded."""
        return self._projections.get(entrant_id)

    def cursor_for(self, entrant_id: str) -> PerspectiveCursor | None:
        """Return the retained PerspectiveCursor for one entrant if loaded."""
        return self._cursors.get(entrant_id)


__all__ = [
    "BROADCAST_MODE",
    "ContactKnowledge",
    "KnowledgeStatus",
    "OwnProcessKnowledge",
    "PerspectiveAvailability",
    "PerspectiveCursor",
    "PerspectiveError",
    "PerspectiveManager",
    "PerspectiveProjection",
    "PerspectiveState",
    "ReadKnowledge",
    "TickBoundary",
]