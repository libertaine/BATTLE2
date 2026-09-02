"""Client-side Spectator Director: wall-clock runtime over a deterministic plan.

``battle_engine.spectator_director`` computes a :class:`DirectorPlan` --
a pure function of a replay/trace pair, a view mode, and a config, with no
wall-clock state anywhere in it. This module is deliberately the only place
that lets real elapsed time touch a Director decision: :class:`
PlaybackDirectorRuntime` consumes an injectable clock (real ``time.monotonic``
by default, a fake counter in tests) to decide *whether an impact hold has
finished waiting yet*, and :class:`DirectorManager` builds and caches one
plan and one runtime per view mode (Broadcast, and each entrant's
Perspective), so cutting between modes mid-match neither shares nor resets
another mode's own hold-consumption history.

Manual playback control always wins. ``PlaybackDirectorRuntime.update`` is
the only Director entry point that touches ``PlaybackController`` state, and
it mirrors ``PlaybackController.update``'s own guard: if the user has
paused, or the session is already at its end, this call does nothing at all
-- it never fights a paused controller back into motion, and every discrete
navigation method on ``PlaybackController`` (step, seek, restart, jump-to-
end) remains completely untouched by the Director, called directly by the
renderer's key-dispatch exactly as it already is without a Director present.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from battle_engine.spectator_derivation import SpectatorDerivation
from battle_engine.spectator_director import (
    DEFAULT_DIRECTOR_CONFIG,
    DirectorConfig,
    DirectorDecision,
    DirectorError,
    DirectorMode,
    DirectorPlan,
    build_director_plan,
)

from battle_client.player import PlaybackController

BROADCAST_MODE = "broadcast"

Clock = Callable[[], float]


@dataclass(frozen=True)
class DirectorAvailability:
    """Availability status of Director pacing, mirroring `PerspectiveAvailability`."""

    available: bool
    status_message: str


class PlaybackDirectorRuntime:
    """Wall-clock playback pacing driven by one deterministic `DirectorPlan`.

    Owns exactly two pieces of mutable, non-deterministic state: which tick
    (if any) currently has an impact hold in progress, and when that hold
    started (via the injected clock). Everything else -- which state a tick
    is in, what rate it plays at, whether it holds at all -- comes from the
    plan and never changes here.
    """

    def __init__(self, plan: DirectorPlan, *, clock: Clock = time.monotonic) -> None:
        self._plan = plan
        self._clock = clock
        self._consumed_holds: set[int] = set()
        self._active_hold_tick: int | None = None
        self._active_hold_started_at: float | None = None

    @property
    def plan(self) -> DirectorPlan:
        return self._plan

    def decision_for_tick(self, tick: int) -> DirectorDecision:
        return self._plan.decision_for_tick(tick)

    def restart(self) -> None:
        """Clear all runtime hold state. The plan itself is unaffected.

        Call when the underlying replay restarts to tick 0 -- otherwise a
        hold already consumed during a previous traversal would stay marked
        consumed forever, even though playback is starting over.
        """
        self._consumed_holds.clear()
        self._active_hold_tick = None
        self._active_hold_started_at = None

    def hold_remaining_ms(self, tick: int) -> float:
        """Milliseconds left in tick ``tick``'s hold, or 0 if none is active.

        Diagnostic-overlay support (Phase 7 brief Sec. 24) -- never used to
        make a pacing decision, only to display one already made.
        """
        decision = self._plan.decision_for_tick(tick)
        if (
            decision.hold_ms <= 0
            or tick in self._consumed_holds
            or self._active_hold_tick != tick
            or self._active_hold_started_at is None
        ):
            return 0.0
        elapsed_ms = (self._clock() - self._active_hold_started_at) * 1000.0
        return max(0.0, decision.hold_ms - elapsed_ms)

    def update(self, controller: PlaybackController, elapsed_seconds: float) -> None:
        """Advance ``controller`` by ``elapsed_seconds``, honoring the plan.

        Call this once per frame *instead of* ``controller.update()``
        directly, whenever Director pacing is active. Pausing, being at the
        end, a manual step, or a manual seek are all handled by
        ``PlaybackController`` itself and are completely unaffected by this
        method: they never call it, so a hold in progress can never block a
        manual navigation action.
        """
        if not controller.playing or controller.session.at_end:
            return
        tick = controller.session.current_tick

        if self._active_hold_tick is not None and self._active_hold_tick != tick:
            # We've moved to a different tick than the one with an
            # in-progress (not yet consumed) hold -- its partial wait is
            # abandoned outright, regardless of what tick we moved to. This
            # must happen unconditionally, before looking at the new tick's
            # own decision, or a visit to a third tick that has no hold of
            # its own would leave stale bookkeeping behind: a later return
            # to the original held tick would then incorrectly measure
            # elapsed time from the original (now-irrelevant) start instant
            # instead of restarting cleanly.
            self._active_hold_tick = None
            self._active_hold_started_at = None

        decision = self._plan.decision_for_tick(tick)

        if decision.hold_ms > 0 and tick not in self._consumed_holds:
            if self._active_hold_tick != tick or self._active_hold_started_at is None:
                # Either arriving at this tick for the first time this
                # traversal, or returning to it after having left (a manual
                # seek away and back restarts this tick's hold timer from
                # zero -- it does not remember how far the earlier, abandoned
                # attempt got).
                self._active_hold_tick = tick
                self._active_hold_started_at = self._clock()
                controller.reset_accumulator()
            started_at = self._active_hold_started_at
            elapsed_hold_ms = (self._clock() - started_at) * 1000.0
            if elapsed_hold_ms < decision.hold_ms:
                return
            self._consumed_holds.add(tick)
            self._active_hold_tick = None
            self._active_hold_started_at = None
            controller.reset_accumulator()

        controller.tick_interval = 1.0 / decision.rate_tps
        controller.update(elapsed_seconds)


class DirectorManager:
    """Builds and caches one `DirectorPlan`/`PlaybackDirectorRuntime` per view mode.

    Mirrors `battle_client.perspective.PerspectiveManager`'s own
    availability/caching shape deliberately, so the two integrate the same
    way into the renderer. Constructed from an already-computed
    `SpectatorDerivation` (typically `PerspectiveManager.derivation`) rather
    than a replay/trace path pair, so building a Director never repeats the
    expensive `verify_pair`/`derive_events` pass a `PerspectiveManager` (or
    the caller) has already paid for. When no derivation is available (no
    trace, or an invalid/mismatched one), the Director becomes unavailable
    with a clear status rather than fabricating a plan from nothing.
    """

    def __init__(
        self,
        derivation: SpectatorDerivation | None,
        *,
        config: DirectorConfig = DEFAULT_DIRECTOR_CONFIG,
        unavailable_reason: str | None = None,
        clock: Clock = time.monotonic,
    ) -> None:
        self._derivation = derivation
        self._config = config
        self._clock = clock
        self._plans: dict[str, DirectorPlan] = {}
        self._runtimes: dict[str, PlaybackDirectorRuntime] = {}
        if derivation is not None:
            self._availability = DirectorAvailability(
                available=True,
                status_message=(
                    f"Director available ({len(derivation.binding.entrant_identities)} entrants)."
                ),
            )
        else:
            self._availability = DirectorAvailability(
                available=False,
                status_message=unavailable_reason or "Director unavailable: no trace supplied.",
            )

    @property
    def available(self) -> bool:
        return self._availability.available

    @property
    def status_message(self) -> str:
        return self._availability.status_message

    @staticmethod
    def _director_mode(mode: str) -> tuple[DirectorMode, str | None]:
        if mode == BROADCAST_MODE:
            return DirectorMode.BROADCAST, None
        return DirectorMode.PERSPECTIVE, mode

    def plan_for(self, mode: str) -> DirectorPlan | None:
        """The cached plan for ``mode`` ('broadcast' or an entrant id), or
        None if Director is unavailable or ``mode`` cannot be planned."""
        if not self.available or self._derivation is None:
            return None
        if mode not in self._plans:
            director_mode, entrant_id = self._director_mode(mode)
            try:
                self._plans[mode] = build_director_plan(
                    self._derivation,
                    mode=director_mode,
                    entrant_id=entrant_id,
                    config=self._config,
                )
            except DirectorError:
                return None
        return self._plans[mode]

    def runtime_for(self, mode: str) -> PlaybackDirectorRuntime | None:
        """The cached runtime for ``mode``, building its plan on first use."""
        plan = self.plan_for(mode)
        if plan is None:
            return None
        if mode not in self._runtimes:
            self._runtimes[mode] = PlaybackDirectorRuntime(plan, clock=self._clock)
        return self._runtimes[mode]

    def restart(self) -> None:
        """Clear every cached mode's runtime hold state (plans are unaffected)."""
        for runtime in self._runtimes.values():
            runtime.restart()


__all__ = [
    "BROADCAST_MODE",
    "DirectorAvailability",
    "DirectorManager",
    "PlaybackDirectorRuntime",
]
