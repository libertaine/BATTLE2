"""Interactive Pygame replay viewer, driven entirely by ``ReplaySession``.

``PygameRenderer`` is no longer an ``AbstractRenderer`` subclass and is not
driven by ``ReplayPlayer``'s one-shot forward stream: it is interactive
(play/pause/step/seek/restart/speed), and a forward-only record iterator
cannot represent "go back". Instead, ``PygameRenderer.run(session, ...)``
owns a normal Pygame event/render loop and reads reconstructed state
directly from a ``battle_client.session.ReplaySession`` on every frame via
``session.current_state`` -- there is no second, renderer-owned
reconstruction of arena bytes, ownership, agent state, or score anywhere
in this module. The only per-frame state this renderer keeps for itself is
purely visual and transient (recent write flashes, agent trails); both are
cleared on any non-linear tick change (a seek/restart, as opposed to a
plain forward step), so they never imply history that didn't actually
happen at the tick currently on screen.

``HeadlessRenderer`` (a different renderer, in ``renderers/headless.py``)
is unaffected by any of this and still uses the original
``ReplayPlayer``/``AbstractRenderer`` streaming path.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from battle_client.player import PlaybackController
from battle_client.renderers.base import RendererDependencyError
from battle_client.session import ReplaySession, ReplayState

FLASH_TTL = 6
TRAIL_LENGTH = 200

# Color palette (unchanged from the prior renderer).
AGENT_COLORS: dict[str, tuple[int, int, int]] = {
    "A": (220, 70, 70),  # red-ish
    "B": (70, 120, 220),  # blue-ish
    "C": (80, 200, 120),  # green-ish
    "D": (200, 180, 70),  # amber
}
GRID_BG: tuple[int, int, int] = (12, 12, 14)
GRID_LINE: tuple[int, int, int] = (26, 26, 30)
OWNERSHIP_TINT: dict[str, tuple[int, int, int]] = {
    "A": (120, 30, 30),
    "B": (30, 60, 120),
    "C": (30, 110, 70),
    "D": (110, 95, 30),
}
PROCESS_FLASH: dict[str, tuple[int, int, int]] = {
    "A": (255, 80, 80),
    "B": (80, 140, 255),
    "C": (90, 255, 170),
    "D": (255, 230, 100),
}
DEFAULT_TINT = (80, 80, 80)
DEFAULT_FLASH = (255, 255, 255)
DEFAULT_AGENT_COLOR = (200, 200, 200)

HELP_TEXT = (
    "Space play/pause  Right/Left step  Shift+Right/Left seek 10  "
    "Home/End first/last  +/- speed  [/] zoom  T trails  Esc/Q quit"
)


# ---------------------------------------------------------------------------
# HUD content: pure functions over ReplaySession/PlaybackController/
# ReplayState, deliberately kept free of any Pygame dependency so they can
# be unit tested without opening a window.
# ---------------------------------------------------------------------------
def _agent_display_line(
    agent_id: str,
    display_name: str,
    state: ReplayState,
) -> str:
    """One HUD line for one entrant, labeled for its actual runtime kind.

    VM: ``pc`` is a real fetch address, ``cpu_used`` an instruction count,
    ``region`` a real code-load footprint. Python: the controller value is
    never called "pc"/labeled as a source location, ``cpu_used`` is
    labeled as an action/callback count, and the always-degenerate
    ``(0, 0)`` region is never presented as a meaningful footprint -- see
    the runtime-kind semantics table in docs/REPLAY_SCHEMA.md.
    """
    agent = state.agents.get(agent_id)
    if agent is None:
        return f"{agent_id} ({display_name})  no data at this tick"

    status = "alive" if agent.alive else "dead"
    score = state.score.get(agent_id, 0)

    if state.runtime_kind == "python":
        position_label = f"ctrl={agent.pc}"
        cpu_label = f"actions={agent.cpu_used}"
        region_label = "region=n/a (python controller)"
    else:
        position_label = f"pc={agent.pc}"
        cpu_label = f"cpu={agent.cpu_used}"
        region_label = f"region={list(agent.region)}" if agent.region else "region=?"

    return (
        f"{agent_id} ({display_name})  {status}  score={score:g}  "
        f"{cpu_label}  writes={agent.mem_writes}  {position_label}  {region_label}"
    )


def build_hud_lines(
    session: ReplaySession,
    controller: PlaybackController,
) -> list[str]:
    """The HUD's text content for the session/controller's current state.

    Kept readable rather than exhaustive: one status line, one line per
    entrant, and winner/termination once the replay's terminal record
    establishes them -- which is independent of the current playback
    position, since that metadata comes straight from the canonical
    replay's own terminal ``MatchResult``, not from scrubbing to the end.
    """
    state = session.current_state
    runtime_label = state.runtime_kind or "unknown"
    status = "PLAYING" if controller.playing else "PAUSED"
    if session.at_end:
        status = "PAUSED (end)" if not controller.playing else status

    lines = [
        f"Bytefray Replay -- runtime: {runtime_label}",
        f"Tick {state.tick} / {session.final_tick}   [{status}]   speed {controller.speed:g}x",
        "",
    ]

    agent_names = dict(session.header.agents) if session.header is not None else {}
    for agent_id in sorted(state.agents):
        display_name = agent_names.get(agent_id, agent_id)
        lines.append(_agent_display_line(agent_id, display_name, state))

    if session.result is not None:
        winner = session.winner or "tie"
        lines.append("")
        lines.append(f"Winner: {winner}   Termination: {session.termination_reason}")

    lines.append("")
    lines.append(HELP_TEXT)
    return lines


# ---------------------------------------------------------------------------
# Keyboard dispatch: pure mapping from a Pygame key/modifier pair to a
# PlaybackController command. Uses real Pygame key constants (plain
# integers -- importing them does not require a display or pygame.init()),
# so this is directly unit-testable without opening a window.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class KeyAction:
    """The result of dispatching one keypress: what to do, if anything."""

    quit_requested: bool = False
    toggle_trails: bool = False
    rescale: int = 0  # +1/-1 window scale step
    fit_to_display: bool = False


def dispatch_key(
    pygame_module: Any,
    key: int,
    mods: int,
    controller: PlaybackController,
) -> KeyAction:
    """Apply one keypress to ``controller`` and report any renderer-local
    (non-controller) action the caller should also perform.
    """
    pg = pygame_module
    shift = bool(mods & pg.KMOD_SHIFT)

    if key in (pg.K_ESCAPE, pg.K_q):
        return KeyAction(quit_requested=True)
    if key == pg.K_SPACE:
        controller.toggle_play_pause()
    elif key == pg.K_RIGHT:
        controller.seek_relative(10) if shift else controller.step_forward()
    elif key == pg.K_LEFT:
        controller.seek_relative(-10) if shift else controller.step_backward()
    elif key == pg.K_HOME:
        controller.restart()
    elif key == pg.K_END:
        controller.jump_to_end()
    elif key in (pg.K_PLUS, pg.K_EQUALS, pg.K_PAGEUP):
        controller.speed_up()
    elif key in (pg.K_MINUS, pg.K_UNDERSCORE, pg.K_PAGEDOWN):
        controller.speed_down()
    elif key == pg.K_LEFTBRACKET:
        return KeyAction(rescale=-1)
    elif key == pg.K_RIGHTBRACKET:
        return KeyAction(rescale=1)
    elif key == pg.K_t:
        return KeyAction(toggle_trails=True)
    elif key == pg.K_0:
        return KeyAction(fit_to_display=True)
    return KeyAction()


class PygameRenderer:
    """Interactive Pygame replay viewer over a ``ReplaySession``."""

    def __init__(self, scale: int = 4, title: str = "Bytefray - Replay") -> None:
        self.scale = max(1, int(scale))
        self.title = title

        self.pg: Any = None
        self.screen: Any = None
        self.grid_surf: Any = None
        self.font: Any = None
        self.hud_font: Any = None

        self.arena = 0
        self.grid_cols = 0
        self.grid_rows = 0

        # Purely visual, transient state -- never authoritative. Cleared on
        # any non-linear tick change (see _advance_transient_effects).
        self.trails_enabled = True
        self._trail_points: dict[str, list[tuple[int, int]]] = {}
        self._flash: dict[tuple[int, int], tuple[tuple[int, int, int], int]] = {}
        self._last_rendered_tick: int | None = None
        self._last_owners: tuple[str | None, ...] | None = None

    # ---------- grid geometry (pure, presentation-only) ----------

    def _resolve_grid_dims(self, arena_cells: int) -> tuple[int, int]:
        if arena_cells <= 0:
            return 1, 1
        root = int(math.sqrt(arena_cells))
        for c in range(root, 0, -1):
            if arena_cells % c == 0:
                r = arena_cells // c
                return max(c, r), min(c, r)
        c = math.ceil(math.sqrt(arena_cells))
        r = math.ceil(arena_cells / c)
        return c, r

    def _to_xy(self, address: int) -> tuple[int, int] | None:
        if self.arena <= 0 or self.grid_cols <= 0:
            return None
        a = address % self.arena
        return (a % self.grid_cols, a // self.grid_cols)

    def _screen_xy(self, x: int, y: int) -> tuple[int, int]:
        w, h = self.screen.get_size()
        return (
            int((x + 0.5) * w / self.grid_cols),
            int((y + 0.5) * h / self.grid_rows),
        )

    # ---------- lifecycle ----------

    def run(
        self,
        session: ReplaySession,
        *,
        tick_interval: float,
        start_tick: int | None = None,
        start_paused: bool = False,
        initial_speed: float | None = None,
    ) -> None:
        """Open an interactive window and play ``session`` until the user
        quits. Blocks until then. Raises ``RendererDependencyError`` if
        Pygame is not installed.
        """
        try:
            import pygame
        except ImportError as exc:
            raise RendererDependencyError(
                "Pygame not available. Install pygame or choose --renderer headless."
            ) from exc
        self.pg = pygame
        pygame.init()

        self.arena = session.header.config.arena_size if session.header else 0
        self.grid_cols, self.grid_rows = self._resolve_grid_dims(self.arena)
        self._configure_window()

        controller = PlaybackController(
            session, tick_interval=tick_interval, playing=not start_paused
        )
        if initial_speed is not None:
            controller.set_speed(initial_speed)
        if start_tick is not None:
            controller.seek_relative(start_tick - session.current_tick)

        try:
            self._loop(controller)
        finally:
            pygame.quit()

    def _configure_window(self) -> None:
        pg = self.pg
        try:
            di = pg.display.Info()
            max_w, max_h = int(di.current_w * 0.90), int(di.current_h * 0.90)
        except (pg.error, AttributeError, TypeError, ValueError):
            max_w, max_h = 1920, 1080

        fit_scale = max(1, min(max_w // self.grid_cols, max_h // self.grid_rows))
        self.scale = max(1, min(self.scale, fit_scale))
        window_size = (self.grid_cols * self.scale, self.grid_rows * self.scale)
        self.screen = pg.display.set_mode(window_size, pg.RESIZABLE)
        pg.display.set_caption(self.title)
        self.grid_surf = pg.Surface((self.grid_cols, self.grid_rows))
        self.font = pg.font.SysFont("consolas", 14)
        self.hud_font = pg.font.SysFont("consolas", 13)

    def _resize_window(self) -> None:
        size = (self.grid_cols * self.scale, self.grid_rows * self.scale)
        self.screen = self.pg.display.set_mode(size, self.pg.RESIZABLE)
        self.pg.display.set_caption(self.title)

    def _fit_to_display(self) -> None:
        pg = self.pg
        try:
            di = pg.display.Info()
            max_w, max_h = int(di.current_w * 0.90), int(di.current_h * 0.90)
        except (pg.error, AttributeError, TypeError, ValueError):
            max_w, max_h = 1920, 1080
        fit_scale = max(1, min(max_w // self.grid_cols, max_h // self.grid_rows))
        old = self.scale
        self.scale = max(1, min(self.scale, fit_scale))
        if self.scale != old:
            self._resize_window()

    # ---------- main loop ----------

    def _loop(self, controller: PlaybackController) -> None:
        pg = self.pg
        clock = pg.time.Clock()
        running = True
        while running:
            elapsed_ms = clock.tick(60)
            for event in pg.event.get():
                if event.type == pg.QUIT:
                    running = False
                    break
                if event.type == pg.KEYDOWN:
                    action = dispatch_key(pg, event.key, event.mod, controller)
                    if action.quit_requested:
                        running = False
                        break
                    if action.toggle_trails:
                        self.trails_enabled = not self.trails_enabled
                    if action.rescale:
                        old = self.scale
                        self.scale = max(1, min(16, self.scale + action.rescale))
                        if self.scale != old:
                            self._resize_window()
                    if action.fit_to_display:
                        self._fit_to_display()
                elif event.type in (pg.VIDEORESIZE, getattr(pg, "WINDOWRESIZED", 32769)):
                    w, h = getattr(event, "size", self.screen.get_size())
                    new_scale = max(1, min(w // self.grid_cols, h // self.grid_rows))
                    if new_scale != self.scale:
                        self.scale = new_scale
                        self._resize_window()
            if not running:
                break

            controller.update(elapsed_ms / 1000.0)
            self._advance_transient_effects(controller.session.current_state)
            self._redraw(controller)
            pg.display.flip()

    # ---------- transient (visual-only) effect bookkeeping ----------

    def _advance_transient_effects(self, state: ReplayState) -> None:
        """Update flashes/trails for the newly-current ``state``.

        A genuine single-tick forward step extends them; anything else
        (a seek, a restart, the very first frame) clears them first, so a
        backward seek never shows a flash or trail implying activity that
        hasn't happened yet relative to the tick now on screen.
        """
        is_linear_step = (
            self._last_rendered_tick is not None and state.tick == self._last_rendered_tick + 1
        )
        if not is_linear_step:
            self._trail_points.clear()
            self._flash.clear()

        if is_linear_step and self._last_owners is not None:
            for address, (old, new) in enumerate(zip(self._last_owners, state.owners)):
                if new is not None and new != old:
                    xy = self._to_xy(address)
                    if xy is not None:
                        self._flash[xy] = (PROCESS_FLASH.get(new, DEFAULT_FLASH), FLASH_TTL)

        if self.trails_enabled and (is_linear_step or self._last_rendered_tick is None):
            for agent_id, agent in state.agents.items():
                if not agent.alive:
                    continue
                xy = self._to_xy(agent.pc) if state.runtime_kind == "vm" else None
                if xy is None:
                    continue
                points = self._trail_points.setdefault(agent_id, [])
                if not points or points[-1] != xy:
                    points.append(xy)
                    del points[:-TRAIL_LENGTH]

        # Fade existing flashes regardless of step linearity.
        expired = []
        for xy, (color, ttl) in self._flash.items():
            ttl -= 1
            if ttl <= 0:
                expired.append(xy)
            else:
                self._flash[xy] = (color, ttl)
        for xy in expired:
            del self._flash[xy]

        self._last_rendered_tick = state.tick
        self._last_owners = state.owners

    # ---------- drawing ----------

    def _redraw(self, controller: PlaybackController) -> None:
        pg = self.pg
        gs = self.grid_surf
        state = controller.session.current_state

        gs.fill(GRID_BG)
        max_dim = max(self.grid_cols, self.grid_rows)
        step = max(1, max_dim // 32)
        for x in range(0, self.grid_cols, step):
            pg.draw.line(gs, GRID_LINE, (x, 0), (x, self.grid_rows - 1))
        for y in range(0, self.grid_rows, step):
            pg.draw.line(gs, GRID_LINE, (0, y), (self.grid_cols - 1, y))

        for address, owner in enumerate(state.owners):
            if owner is None:
                continue
            xy = self._to_xy(address)
            if xy is None:
                continue
            tint = OWNERSHIP_TINT.get(owner, DEFAULT_TINT)
            gs.set_at(xy, self._blend(GRID_BG, tint, 0.65))

        for xy, (color, _ttl) in self._flash.items():
            if 0 <= xy[0] < self.grid_cols and 0 <= xy[1] < self.grid_rows:
                gs.set_at(xy, color)

        scaled = pg.transform.scale(gs, self.screen.get_size())
        self.screen.blit(scaled, (0, 0))

        if self.trails_enabled:
            for agent_id, points in self._trail_points.items():
                if len(points) < 2:
                    continue
                color = self._blend(
                    AGENT_COLORS.get(agent_id, DEFAULT_AGENT_COLOR), (255, 255, 255), 0.25
                )
                self._draw_polyline(points[-TRAIL_LENGTH:], color)

        for agent_id, agent in state.agents.items():
            if not agent.alive:
                continue
            xy = self._to_xy(agent.pc) if state.runtime_kind == "vm" else None
            if xy is None:
                continue
            self._draw_agent_marker(agent_id, xy)

        self._draw_hud(controller)

    def _blend(
        self, a: tuple[int, int, int], b: tuple[int, int, int], alpha: float
    ) -> tuple[int, int, int]:
        return (
            int(a[0] * (1 - alpha) + b[0] * alpha),
            int(a[1] * (1 - alpha) + b[1] * alpha),
            int(a[2] * (1 - alpha) + b[2] * alpha),
        )

    def _draw_agent_marker(self, agent_id: str, pos: tuple[int, int]) -> None:
        color = AGENT_COLORS.get(agent_id, DEFAULT_AGENT_COLOR)
        x, y = pos
        sx, sy = self._screen_xy(x, y)
        cell_scale = min(
            self.screen.get_width() / self.grid_cols,
            self.screen.get_height() / self.grid_rows,
        )
        r = max(3, int(0.7 * cell_scale))
        self.pg.draw.circle(self.screen, color, (sx, sy), r)
        self.pg.draw.circle(self.screen, (0, 0, 0), (sx, sy), r, 1)
        label = self.font.render(agent_id, True, (255, 255, 255))
        self.screen.blit(label, label.get_rect(center=(sx, sy - r - 8)))

    def _draw_polyline(self, points: list[tuple[int, int]], color: tuple[int, int, int]) -> None:
        screen_points = [self._screen_xy(x, y) for (x, y) in points]
        width = max(1, min(self.screen.get_size()) // max(self.grid_cols, self.grid_rows) // 3)
        self.pg.draw.lines(self.screen, color, False, screen_points, width)

    def _draw_hud(self, controller: PlaybackController) -> None:
        lines = build_hud_lines(controller.session, controller)
        w, _ = self.screen.get_size()
        line_height = 16
        hud_h = line_height * len(lines) + 12
        hud = self.pg.Surface((w, hud_h), flags=self.pg.SRCALPHA)
        hud.fill((0, 0, 0, 150))
        for index, text in enumerate(lines):
            rendered = self.hud_font.render(text, True, (235, 235, 235))
            hud.blit(rendered, (10, 6 + index * line_height))
        self.screen.blit(hud, (0, 0))
