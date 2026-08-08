"""Replay iteration and renderer lifecycle orchestration.

Two playback models coexist here, deliberately kept separate rather than
forced through one shared abstraction:

``ReplayPlayer`` is unchanged since Phase 7a Slice 1/2: a one-shot forward
stream of ``ReplayRecord``s pushed into an ``AbstractRenderer``. It fits
``HeadlessRenderer`` (and any future stream-only consumer) well, and stays
the CLI's headless-mode driver.

``PlaybackController`` is new in Phase 7a Slice 3, for the interactive
Pygame viewer. Bolting seek/restart/backward-navigation onto
``ReplayPlayer``'s forward-only iterator contract would fundamentally
fight it -- an iterator cannot be asked to "go back". Interactive playback
instead drives a ``ReplaySession`` directly: ``ReplaySession`` remains the
sole source of reconstructed state (see its module docstring);
``PlaybackController`` owns only play/pause/speed and wall-clock time
accumulation, translating elapsed real time and discrete navigation
commands into calls to the session's ``step_forward``/``seek``/
``restart``. It never reconstructs state itself and never sleeps or
blocks -- a caller (the Pygame render loop) calls
``update(elapsed_seconds)`` once per frame, so the UI stays responsive
while paused and a speed change takes effect on the very next frame.
"""

from __future__ import annotations

import bisect
from collections.abc import Iterable
from typing import Any

from battle_engine.replay import ReplayRecord

from battle_client.renderers.base import AbstractRenderer
from battle_client.session import ReplaySession, ReplayState


class ReplayPlayer:
    """Deliver replay records through one explicit renderer lifecycle."""

    def __init__(self, renderer: AbstractRenderer):
        self.renderer = renderer

    def play(
        self,
        records: Iterable[ReplayRecord],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        renderer = self.renderer
        try:
            renderer.setup(metadata)
            renderer.wait_for_start()

            # Keep iteration here, separate from presentation. A one-record
            # lookahead lets completion be detected without blocking a paused
            # interactive renderer after the final record.
            iterator = iter(records)
            try:
                pending = next(iterator)
            except StopIteration:
                pending = None

            while pending is not None:
                renderer.wait_until_ready()
                renderer.on_event(pending)
                renderer.update()
                try:
                    pending = next(iterator)
                except StopIteration:
                    pending = None

            renderer.on_complete()
            renderer.hold_open()
        finally:
            renderer.teardown()


SPEEDS: tuple[float, ...] = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0)
DEFAULT_SPEED_INDEX = SPEEDS.index(1.0)
DEFAULT_TICK_INTERVAL = 0.05  # seconds per tick at 1x, if the caller supplies none


class PlaybackController:
    """Play/pause/speed/navigation over a loaded ``ReplaySession``.

    Deterministic replay reconstruction stays entirely in ``ReplaySession``;
    this class only decides *when* to call it, and only ever asks it for a
    tick that is genuinely recorded -- never a guessed tick number that
    might fall in a sparse legacy replay's gap. ``update(elapsed_seconds)``
    is the sole time-driven entry point: call it once per frame with the
    real elapsed time since the previous call, and it advances at most as
    many ticks as the current speed and elapsed time justify. There is no
    ``time.sleep`` anywhere in this class.

    Every discrete navigation command (step, seek, restart, jump-to-end)
    pauses automatic playback first -- a manual navigation action while
    auto-playing would otherwise immediately be overridden by the next
    ``update()`` call, which is confusing. Playback only resumes when
    ``play()`` is called explicitly.
    """

    def __init__(
        self,
        session: ReplaySession,
        *,
        tick_interval: float = DEFAULT_TICK_INTERVAL,
        playing: bool = True,
    ) -> None:
        self.session = session
        self.tick_interval = tick_interval if tick_interval > 0 else DEFAULT_TICK_INTERVAL
        self.playing = playing and not session.at_end
        self._speed_index = DEFAULT_SPEED_INDEX
        self._accumulated = 0.0

    @property
    def speed(self) -> float:
        return SPEEDS[self._speed_index]

    # ---------- play/pause ----------

    def play(self) -> None:
        """Start (or resume) automatic playback.

        Pressing play at the final tick restarts from the first tick and
        begins playing. This is an explicit, user-initiated action (not
        automatic looping): the session never resumes or restarts on its
        own without a ``play()`` call.
        """
        if self.session.at_end:
            self.session.restart()
        self.playing = True
        self._accumulated = 0.0

    def pause(self) -> None:
        self.playing = False

    def toggle_play_pause(self) -> None:
        if self.playing:
            self.pause()
        else:
            self.play()

    # ---------- speed ----------

    def speed_up(self) -> None:
        self._speed_index = min(len(SPEEDS) - 1, self._speed_index + 1)

    def speed_down(self) -> None:
        self._speed_index = max(0, self._speed_index - 1)

    def set_speed(self, value: float) -> None:
        """Snap to the closest supported speed in ``SPEEDS``.

        There is no arbitrary floating-point speed entry; this just picks
        the nearest fixed step, so an out-of-range or off-step request
        (for example from a CLI ``--speed`` flag) degrades gracefully
        instead of being rejected.
        """
        self._speed_index = min(range(len(SPEEDS)), key=lambda i: abs(SPEEDS[i] - value))

    # ---------- discrete navigation (always pauses first) ----------

    def step_forward(self) -> ReplayState:
        """Advance exactly one recorded tick. A safe no-op at the final tick."""
        self.pause()
        self._accumulated = 0.0
        if self.session.at_end:
            return self.session.current_state
        return self.session.step_forward()

    def step_backward(self) -> ReplayState:
        """Move to the previous recorded tick. A safe no-op at the first tick."""
        self.pause()
        self._accumulated = 0.0
        target = self._adjacent_recorded_tick(-1)
        if target is None:
            return self.session.current_state
        return self.session.seek(target)

    def seek_relative(self, delta: int) -> ReplayState:
        """Seek by roughly ``delta`` ticks (negative for backward).

        The target tick number is clamped to the replay's recorded range
        and, for a sparse legacy replay, snapped to the nearest recorded
        tick in the requested direction -- it never calls
        ``ReplaySession.seek`` with a tick that isn't actually recorded.
        """
        self.pause()
        self._accumulated = 0.0
        target = self._nearest_recorded_tick(self.session.current_tick + delta, delta)
        if target == self.session.current_tick:
            return self.session.current_state
        return self.session.seek(target)

    def restart(self) -> ReplayState:
        self.pause()
        self._accumulated = 0.0
        return self.session.restart()

    def jump_to_end(self) -> ReplayState:
        self.pause()
        self._accumulated = 0.0
        final = self.session.final_tick
        if final is None:
            return self.session.current_state
        return self.session.seek(final)

    # ---------- frame-driven auto-advance ----------

    def update(self, elapsed_seconds: float) -> None:
        """Advance playback by ``elapsed_seconds`` of real time, if playing.

        Call once per frame with the real elapsed time since the previous
        call (for example, a Pygame clock's tick delta in seconds). Pauses
        automatically on reaching the final tick, rather than stopping
        silently with no further indication.
        """
        if not self.playing or self.session.at_end:
            return
        self._accumulated += max(0.0, elapsed_seconds) * self.speed
        interval = self.tick_interval
        while self._accumulated >= interval and not self.session.at_end:
            self._accumulated -= interval
            self.session.step_forward()
        if self.session.at_end:
            self.playing = False
            self._accumulated = 0.0

    # ---------- internals: recorded-tick-aware navigation ----------

    def _adjacent_recorded_tick(self, direction: int) -> int | None:
        """The previous (``direction < 0``) or next (``direction > 0``)
        recorded tick relative to the session's current tick, or ``None``
        if there isn't one (already at the first/last recorded tick).
        """
        ticks = self.session.recorded_ticks
        current = self.session.current_tick
        if direction < 0:
            index = bisect.bisect_left(ticks, current) - 1
            return ticks[index] if index >= 0 else None
        index = bisect.bisect_right(ticks, current)
        return ticks[index] if index < len(ticks) else None

    def _nearest_recorded_tick(self, target: int, direction: int) -> int:
        """Snap ``target`` to a recorded tick, biased toward ``direction``
        when ``target`` itself falls in a sparse-replay gap, and always
        clamped into the replay's recorded range.
        """
        ticks = self.session.recorded_ticks
        first, last = ticks[0], ticks[-1]
        target = max(first, min(last, target))
        index = bisect.bisect_left(ticks, target)
        if index < len(ticks) and ticks[index] == target:
            return target
        if direction >= 0:
            return ticks[index] if index < len(ticks) else ticks[-1]
        return ticks[index - 1] if index > 0 else ticks[0]
