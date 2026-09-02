"""Client integration for the deterministic Fight Night presentation layer.

``battle_engine.spectator_fight_night`` computes a :class:`FightNightPlan` --
a pure function of a derivation, a view mode and a config, with no wall-clock
state and no runtime accumulation anywhere in it. This module is the thin
client seam over it, deliberately mirroring
:class:`battle_client.director.DirectorManager`'s shape so the two integrate
into the renderer the same way: one cached plan per view mode (Broadcast, and
each entrant's Perspective), built lazily from an already-computed
``SpectatorDerivation`` so no second ``analyze_pair`` pass is ever paid.

Unlike the Director there is **no runtime class here at all**. A Director
needs a clock to decide whether an impact hold has finished waiting; Fight
Night needs nothing but the current tick. Everything a frame draws --
which ribbon entries are showing, whether the opening or result card is up --
is a pure function of ``(plan, tick)``, which is what makes seeking,
restarting and mode-switching produce identical presentation with no state to
clear (Phase 8 brief Sec. 42/43/44).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from battle_engine.spectator_derivation import SpectatorDerivation
from battle_engine.spectator_fight_night import (
    DEFAULT_FIGHT_NIGHT_CONFIG,
    FightNightConfig,
    FightNightError,
    FightNightEvent,
    FightNightMode,
    FightNightPlan,
    build_fight_night_plan,
)

BROADCAST_MODE = "broadcast"


class FightNightPhase(str, Enum):
    """Which card, if any, the presentation is showing at a tick.

    Derived from the tick alone -- never from a timer, an animation, or how
    playback arrived at the tick. ``OPENING`` is therefore shown exactly at
    the match's first tick and nowhere else: a restart returns to that tick
    and shows it again, a seek into mid-match never does, and any step or
    play leaves it immediately, so an opening card can never trap the viewer
    behind an animation (Phase 8 brief Sec. 39/44).
    """

    OPENING = "OPENING"
    LIVE = "LIVE"
    RESULT = "RESULT"


@dataclass(frozen=True)
class FightNightAvailability:
    """Availability status of Fight Night, mirroring `DirectorAvailability`."""

    available: bool
    status_message: str


@dataclass(frozen=True)
class FightNightState:
    """Everything a renderer needs to draw Fight Night for one tick.

    Deliberately presentation-ready and inert: the renderer decides where and
    how to draw these, never whether they are true. ``visibility_basis``
    states which information domain produced them, so the on-screen chrome can
    say so out loud rather than leaving a viewer to guess whether a ribbon is
    showing broadcast facts or the selected entrant's own knowledge.
    """

    phase: FightNightPhase
    visibility_basis: str
    entrants: tuple[str, ...]
    ribbon: tuple[FightNightEvent, ...]
    winner: str | None
    termination_reason: str | None
    result_ticks: int


class FightNightManager:
    """Builds and caches one `FightNightPlan` per view mode.

    Constructed from an already-computed ``SpectatorDerivation`` (typically
    ``PerspectiveManager.derivation``, the same object
    :class:`~battle_client.director.DirectorManager` consumes), so enabling
    Fight Night never repeats the expensive ``verify_pair``/``derive_events``
    pass. When no derivation is available, Fight Night becomes unavailable
    with a clear status rather than presenting a match it cannot describe.
    """

    def __init__(
        self,
        derivation: SpectatorDerivation | None,
        *,
        config: FightNightConfig = DEFAULT_FIGHT_NIGHT_CONFIG,
        unavailable_reason: str | None = None,
    ) -> None:
        self._derivation = derivation
        self._config = config
        self._plans: dict[str, FightNightPlan] = {}
        if derivation is not None:
            self._availability = FightNightAvailability(
                available=True,
                status_message=(
                    "Fight Night available "
                    f"({len(derivation.binding.entrant_identities)} entrants)."
                ),
            )
        else:
            self._availability = FightNightAvailability(
                available=False,
                status_message=unavailable_reason or "Fight Night unavailable: no trace supplied.",
            )

    @property
    def available(self) -> bool:
        return self._availability.available

    @property
    def status_message(self) -> str:
        return self._availability.status_message

    @staticmethod
    def _fight_night_mode(mode: str) -> tuple[FightNightMode, str | None]:
        if mode == BROADCAST_MODE:
            return FightNightMode.BROADCAST, None
        return FightNightMode.PERSPECTIVE, mode

    def plan_for(self, mode: str) -> FightNightPlan | None:
        """The cached plan for ``mode`` ('broadcast' or an entrant id), or
        None if Fight Night is unavailable or ``mode`` cannot be planned."""

        if not self.available or self._derivation is None:
            return None
        if mode not in self._plans:
            fight_night_mode, entrant_id = self._fight_night_mode(mode)
            try:
                self._plans[mode] = build_fight_night_plan(
                    self._derivation,
                    mode=fight_night_mode,
                    entrant_id=entrant_id,
                    config=self._config,
                )
            except FightNightError:
                return None
        return self._plans[mode]

    def state_at_tick(self, mode: str, tick: int) -> FightNightState | None:
        """The full presentation state for ``mode`` at ``tick``.

        A pure function of the cached plan and the tick, so two calls with the
        same arguments always agree no matter what playback did in between --
        there is no residue for a mode switch or a seek to clear.
        """

        plan = self.plan_for(mode)
        if plan is None:
            return None
        if tick >= plan.result_ticks:
            phase = FightNightPhase.RESULT
        elif tick <= plan.first_tick:
            phase = FightNightPhase.OPENING
        else:
            phase = FightNightPhase.LIVE
        return FightNightState(
            phase=phase,
            visibility_basis=plan.visibility_basis,
            entrants=plan.entrants,
            ribbon=plan.ribbon_at_tick(tick),
            winner=plan.winner,
            termination_reason=plan.termination_reason,
            result_ticks=plan.result_ticks,
        )


__all__ = [
    "BROADCAST_MODE",
    "FightNightAvailability",
    "FightNightManager",
    "FightNightPhase",
    "FightNightState",
]
