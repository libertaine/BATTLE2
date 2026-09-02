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
    SpectatorPairError,
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
        self._mode = BROADCAST_MODE

        if self._availability.available and self._availability.derivation is not None:
            derivation = self._availability.derivation
            failed = False
            for entrant_id in derivation.binding.entrant_identities:
                try:
                    projection = project_perspective(derivation, entrant_id)
                    self._projections[entrant_id] = projection
                    self._cursors[entrant_id] = projection.cursor()
                except (SpectatorPairError, PerspectiveError, Exception) as exc:
                    self._availability = PerspectiveAvailability(
                        available=False,
                        status_message=f"Perspective projection failed: {exc}",
                        error=exc,
                    )
                    self._projections.clear()
                    self._cursors.clear()
                    failed = True
                    break

            if (
                not failed
                and initial_mode != BROADCAST_MODE
                and self.is_mode_valid(initial_mode)
            ):
                self._mode = initial_mode

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
        """All entrant identities available for perspective viewing."""
        if not self.available:
            return ()
        return tuple(sorted(self._projections.keys()))

    @property
    def mode(self) -> str:
        """Current view mode: 'broadcast' or an entrant identity string."""
        return self._mode

    def is_mode_valid(self, mode: str) -> bool:
        """Whether `mode` is a supported view mode."""
        if mode == BROADCAST_MODE:
            return True
        return self.available and mode in self._projections

    def set_mode(self, mode: str) -> bool:
        """Set active view mode. Returns True if mode was updated successfully."""
        if not self.is_mode_valid(mode):
            return False
        self._mode = mode
        return True

    def cycle_mode(self) -> str:
        """Cycle through: broadcast -> Entrant 1 -> Entrant 2 -> ... -> broadcast."""
        if not self.available or not self._projections:
            self._mode = BROADCAST_MODE
            return self._mode

        modes = [BROADCAST_MODE, *sorted(self._projections.keys())]
        try:
            current_index = modes.index(self._mode)
            next_index = (current_index + 1) % len(modes)
        except ValueError:
            next_index = 0
        self._mode = modes[next_index]
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