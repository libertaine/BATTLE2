from __future__ import annotations

import math
import time
from typing import Any, ClassVar

from battle_engine.replay import (
    AgentEvent,
    KillDeathEvent,
    MatchResult,
    ReplayHeader,
    ReplayRecord,
    TickSnapshot,
)

from .base import AbstractRenderer, RendererDependencyError


class PygameRenderer(AbstractRenderer):
    """
    Pygame visualizer for BATTLE Client.

    Visual layers:
      - Ownership grid (per-cell agent possession tint)
      - Processing flashes (recently touched cells)
      - Agent markers and optional trails
      - HUD with tick and basic status

    Controls:
      - Esc / Q : quit
      - Space   : pause / resume
      - N       : step one event while paused
      - + / -   : change scale (resizes window)
      - T       : toggle trails
    """

    # Color palette
    AGENT_COLORS: ClassVar[dict[str, tuple[int, int, int]]] = {
        "A": (220, 70, 70),  # red-ish
        "B": (70, 120, 220),  # blue-ish
        "C": (80, 200, 120),  # green-ish
        "D": (200, 180, 70),  # amber
    }
    GRID_BG: ClassVar[tuple[int, int, int]] = (12, 12, 14)
    GRID_LINE: ClassVar[tuple[int, int, int]] = (26, 26, 30)
    OWNERSHIP_TINT: ClassVar[dict[str, tuple[int, int, int]]] = {
        "A": (120, 30, 30),
        "B": (30, 60, 120),
        "C": (30, 110, 70),
        "D": (110, 95, 30),
    }
    PROCESS_FLASH: ClassVar[dict[str, tuple[int, int, int]]] = {
        "A": (255, 80, 80),
        "B": (80, 140, 255),
        "C": (90, 255, 170),
        "D": (255, 230, 100),
    }

    def __init__(self, scale: int = 4, title: str = "BATTLE - Pygame") -> None:
        super().__init__()
        self.scale = max(1, int(scale))
        self.title = title

        # pygame handles
        self.pg: Any = None
        self.screen: Any = None
        self.grid_surf: Any = None

        # world state
        self.arena: int = 0
        self.grid_cols: int = 0
        self.grid_rows: int = 0
        self.owner: list[list[str | None]] = []
        self.agents_pos: dict[str, tuple[int, int]] = {}
        self.trail_pts: dict[str, list[tuple[int, int]]] = {}
        self.flash: dict[tuple[int, int], tuple[tuple[int, int, int], int]] = {}

        # runtime
        self.paused: bool = False
        self.step_once: bool = False
        self.trails: bool = True

        # HUD / timing
        self.total_ticks: int = 0
        self.last_tick: int = 0
        self.processed_events: int = 0
        self.start_wall: float = 0.0

        # fonts
        self.font: Any = None
        self.font_big: Any = None

    # ---------- lifecycle ----------

    def _resolve_grid_dims(
        self, metadata: dict[str, Any] | None, arena_cells: int
    ) -> tuple[int, int]:
        """Pick cols/rows for 1D arena indices; prefer explicit metadata first."""
        params = ((metadata or {}).get("params", {}) or {}) if metadata else {}

        cols = (metadata or {}).get("grid_cols") or params.get("grid_cols")
        rows = (metadata or {}).get("grid_rows") or params.get("grid_rows")
        if cols and rows:
            try:
                c, r = int(cols), int(rows)
                if c > 0 and r > 0 and c * r >= arena_cells:
                    return c, r
            except (TypeError, ValueError, OverflowError):
                # Invalid explicit dimensions fall back to inferred dimensions.
                pass

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

    # ---------- lifecycle ----------

    def setup(self, metadata: dict[str, Any] | None = None) -> None:
        try:
            import pygame  # type: ignore
        except ImportError as e:
            raise RendererDependencyError(
                "Pygame not available. Install pygame or choose --renderer headless."
            ) from e

        self.pg = pygame
        self.pg.init()

        # Summary metadata is normalized by the reader boundary.
        self.arena = int((metadata or {}).get("arena") or 512)
        self.grid_cols, self.grid_rows = self._resolve_grid_dims(metadata, self.arena)
        self.total_ticks = int((metadata or {}).get("ticks") or 0)

        # Windowed + resizable, auto-fit to ~90% of current display
        try:
            di = self.pg.display.Info()
            max_w, max_h = int(di.current_w * 0.90), int(di.current_h * 0.90)
        except (pygame.error, AttributeError, TypeError, ValueError):
            # Fallback for headless or display-less environments
            max_w, max_h = 1920, 1080

        logical_w = self.grid_cols
        logical_h = self.grid_rows

        # Choose an integer scale that fits; clamp any pre-set scale to fit
        fit_scale = max(1, min(max_w // logical_w, max_h // logical_h))
        self.scale = max(1, min(self.scale, fit_scale))

        window_size = (logical_w * self.scale, logical_h * self.scale)
        self.screen = self.pg.display.set_mode(
            (0, 0),
            self.pg.FULLSCREEN,
        )
        self.screen = self.pg.display.set_mode(window_size, self.pg.RESIZABLE)
        self.pg.display.set_caption(self.title)

        # Offscreen logical grid surface
        self.grid_surf = self.pg.Surface((logical_w, logical_h))

        # Fonts
        self.font = self.pg.font.SysFont("consolas", 14)
        self.font_big = self.pg.font.SysFont("consolas", 18)

        # Ownership grid + base gridlines
        self.owner = [
            [None for _ in range(self.grid_cols)] for _ in range(self.grid_rows)
        ]
        self._draw_full_grid()

        # HUD timing
        self.start_wall = time.time()

        super().setup(metadata)

    def teardown(self) -> None:
        if self.pg:
            self.pg.quit()

    def wait_for_start(self) -> None:
        """Show an initial prompt and wait before replay events are consumed."""
        clock = self.pg.time.Clock()
        prompt_font = self.pg.font.SysFont("consolas", 28, bold=True)
        hint_font = self.pg.font.SysFont("consolas", 16)

        while True:
            for event in self.pg.event.get():
                if event.type == self.pg.QUIT:
                    raise SystemExit(0)
                if event.type == self.pg.KEYDOWN:
                    if event.key == self.pg.K_SPACE:
                        self.start_wall = time.time()
                        return
                    if event.key in (self.pg.K_ESCAPE, self.pg.K_q):
                        raise SystemExit(0)

            self._draw_full_grid()
            scaled = self.pg.transform.scale(self.grid_surf, self.screen.get_size())
            self.screen.blit(scaled, (0, 0))

            shade = self.pg.Surface(self.screen.get_size(), flags=self.pg.SRCALPHA)
            shade.fill((0, 0, 0, 150))
            self.screen.blit(shade, (0, 0))

            prompt = prompt_font.render("HIT SPACEBAR TO START MATCH", True, (255, 255, 255))
            hint = hint_font.render("ESC or Q to close", True, (190, 200, 215))
            center_x, center_y = self.screen.get_rect().center
            self.screen.blit(prompt, prompt.get_rect(center=(center_x, center_y - 12)))
            self.screen.blit(hint, hint.get_rect(center=(center_x, center_y + 22)))

            self.pg.display.flip()
            clock.tick(30)

    def wait_until_ready(self) -> None:
        """Park replay delivery while paused; allow one record for a step."""
        self._pump_events()
        while self.paused and not self.step_once:
            self.pg.time.wait(10)
            self._pump_events()

    # ---------- event ingestion ----------

    def on_event(self, record: ReplayRecord) -> None:
        """
        Consume only canonical replay models. Legacy/native dictionaries are
        normalized by ``battle_engine.replay`` before this method is called.
        """
        # ``app.match_runner`` historically forwards raw window-system events to
        # this method. They are live UI input, not replay data; its outer event
        # loop already handles them.
        if isinstance(record, dict):
            return
        # A step permit applies to exactly one record, including headers/results.
        self.step_once = False

        if isinstance(record, ReplayHeader):
            if record.config.arena_size != self.arena:
                self._configure_arena(record.config.arena_size)
            return
        if isinstance(record, MatchResult):
            self.last_tick = record.ticks
            return

        event = self._snapshot_dict(record)
        et = event.get("type")
        who = event.get("who")
        tick = record.tick

        # HUD counters
        self.processed_events += 1
        self.last_tick = tick

        def _apply_cells(cells: list[tuple[int, int]], owner: str | None) -> None:
            if not cells:
                return
            if owner is not None:
                for x, y in cells:
                    if 0 <= x < self.grid_cols and 0 <= y < self.grid_rows:
                        self.owner[y][x] = owner
            self._flash(cells, owner)

        if et == "spawn":
            pos = self._to_xy(event.get("pos"))
            if pos and isinstance(who, str):
                self.agents_pos[who] = pos
                if self.trails:
                    self.trail_pts.setdefault(who, []).append(pos)
                self._flash([pos], who)

        elif et == "move":
            to_pos = self._to_xy(event.get("to"))
            if to_pos and isinstance(who, str):
                self.agents_pos[who] = to_pos
                if self.trails:
                    self.trail_pts.setdefault(who, []).append(to_pos)
                self._flash([to_pos], who)

        elif et in ("territory", "claim"):
            cells = self._cells_from_event(event)  # expects "cells": [[x,y],...]
            _apply_cells(cells, who)

        elif et in ("death", "die", "kill"):
            dead = event.get("victim", who)
            if isinstance(dead, str):
                pos = self.agents_pos.pop(dead, None)
                if pos:
                    self._flash([pos], dead)

        elif isinstance(event.get("agents"), list):
            self._apply_snapshot(event)

        elif et == "tick":
            # optional positions map
            pos_map = event.get("positions") or {}
            if isinstance(pos_map, dict):
                for agent_id, p in pos_map.items():
                    xy = self._to_xy(p)
                    if xy:
                        self.agents_pos[agent_id] = xy
                        if self.trails:
                            self.trail_pts.setdefault(agent_id, []).append(xy)

            # optional batched writes/claims
            batch = event.get("writes") or event.get("claims")
            if isinstance(batch, list):
                batch_cells: list[tuple[int, int]] = []
                for c in batch:
                    xy = self._to_xy(c)
                    if xy:
                        batch_cells.append(xy)
                _apply_cells(batch_cells, event.get("who"))

            # fallback: single-letter agent keys with [x,y]
            for k, v in list(event.items()):
                if k in ("type", "tick", "positions", "writes", "claims", "who"):
                    continue
                if isinstance(k, str) and len(k) == 1 and k.isalpha():
                    xy = self._to_xy(v)
                    if xy:
                        self.agents_pos[k] = xy
                        if self.trails:
                            self.trail_pts.setdefault(k, []).append(xy)

    def _snapshot_dict(self, record: TickSnapshot) -> dict[str, Any]:
        """Translate canonical model values to the renderer's drawing inputs."""
        event: dict[str, Any] = {
            "tick": record.tick,
            "agents": [
                {
                    "id": agent.agent_id,
                    "pc": agent.pc,
                    "alive": agent.alive,
                    "cpu_used": agent.cpu_used,
                    "mem_writes": agent.mem_writes,
                    "region": agent.region,
                }
                for agent in record.agents
            ],
            "score": dict(record.score),
            "memory_diffs": [
                {"addr": diff.address, "len": diff.length, "owner": diff.owner}
                for diff in record.memory_diffs
            ],
            "events": [],
        }
        for item in record.events:
            if isinstance(item, KillDeathEvent):
                event["events"].append(
                    {"type": item.event_type, "victim": item.victim, "by": item.killer}
                )
            elif isinstance(item, AgentEvent):
                # A historical one-event record has no snapshot state. Promote
                # it to the top-level drawing action after boundary conversion.
                event.update(
                    type=item.event_type,
                    who=item.agent_id,
                    pos=item.position,
                    to=item.position,
                    **{"from": item.previous_position},
                    cells=list(item.cells),
                    count=item.cell_count,
                )
        return event

    def _configure_arena(self, arena: int) -> None:
        """Rebuild logical surfaces when replay metadata arrives in-band."""
        self.arena = max(1, arena)
        self.grid_cols, self.grid_rows = self._resolve_grid_dims(None, self.arena)
        self.owner = [
            [None for _ in range(self.grid_cols)] for _ in range(self.grid_rows)
        ]
        self.grid_surf = self.pg.Surface((self.grid_cols, self.grid_rows))
        self._fit_to_display()

    def _apply_snapshot(self, event: dict[str, Any]) -> None:
        for agent in event.get("agents", []):
            if not isinstance(agent, dict) or not isinstance(agent.get("id"), str):
                continue
            agent_id = agent["id"]
            if not agent.get("alive", True):
                self.agents_pos.pop(agent_id, None)
                continue
            xy = self._to_xy(agent.get("pc"))
            if xy:
                self.agents_pos[agent_id] = xy
                if self.trails:
                    pts = self.trail_pts.setdefault(agent_id, [])
                    if not pts or pts[-1] != xy:
                        pts.append(xy)

        for diff in event.get("memory_diffs", []):
            if not isinstance(diff, dict):
                continue
            owner = diff.get("owner")
            try:
                addr, length = int(diff["addr"]), int(diff.get("len", 1))
            except (KeyError, TypeError, ValueError):
                continue
            cells = [self._to_xy(addr + offset) for offset in range(max(0, length))]
            valid = [xy for xy in cells if xy is not None]
            if isinstance(owner, str):
                for x, y in valid:
                    self.owner[y][x] = owner
            self._flash(valid, owner if isinstance(owner, str) else None)

        for nested in event.get("events", []):
            if not isinstance(nested, dict):
                continue
            dead = (
                nested.get("victim")
                if nested.get("type") in ("death", "kill")
                else None
            )
            if isinstance(dead, str):
                pos = self.agents_pos.pop(dead, None)
                if pos:
                    self._flash([pos], dead)

    # ---------- drawing helpers ----------

    def _to_xy(self, p) -> tuple[int, int] | None:
        if isinstance(p, int):
            if self.arena <= 0 or self.grid_cols <= 0:
                return None
            a = p % self.arena
            return (a % self.grid_cols, a // self.grid_cols)
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            return None
        try:
            x, y = int(p[0]), int(p[1])
        except (TypeError, ValueError, OverflowError):
            return None
        return (x, y)

    def _cells_from_event(self, event: dict[str, Any]) -> list[tuple[int, int]]:
        cells = event.get("cells")
        out: list[tuple[int, int]] = []
        if isinstance(cells, list):
            for c in cells:
                xy = self._to_xy(c)
                if xy:
                    out.append(xy)
        return out

    def _blend(
        self, a: tuple[int, int, int], b: tuple[int, int, int], alpha: float
    ) -> tuple[int, int, int]:
        # alpha in [0..1]
        return (
            int(a[0] * (1 - alpha) + b[0] * alpha),
            int(a[1] * (1 - alpha) + b[1] * alpha),
            int(a[2] * (1 - alpha) + b[2] * alpha),
        )

    def _draw_full_grid(self) -> None:
        """Background + light grid lines for orientation."""
        gs = self.grid_surf
        pg = self.pg
        gs.fill(self.GRID_BG)

        max_dim = max(self.grid_cols, self.grid_rows)
        step = max(1, max_dim // 32)  # avoid too many lines for large grids
        line_color = self.GRID_LINE
        for x in range(0, self.grid_cols, step):
            pg.draw.line(gs, line_color, (x, 0), (x, self.grid_rows - 1))
        for y in range(0, self.grid_rows, step):
            pg.draw.line(gs, line_color, (0, y), (self.grid_cols - 1, y))

    def _redraw(self, tick: int) -> None:
        pg = self.pg
        gs = self.grid_surf

        # Rebuild the logical surface so expired flashes do not burn in.
        self._draw_full_grid()

        # 1) Ownership fill
        tint_alpha = 0.65
        for y in range(self.grid_rows):
            row = self.owner[y]
            for x in range(self.grid_cols):
                who = row[x]
                if who is None:
                    continue
                tint = self.OWNERSHIP_TINT.get(who, (80, 80, 80))
                gs.set_at((x, y), self._blend(self.GRID_BG, tint, tint_alpha))

        # 2) Processing flashes (fade)
        to_del = []
        for (x, y), (color, ttl) in self.flash.items():
            if 0 <= x < self.grid_cols and 0 <= y < self.grid_rows:
                gs.set_at((x, y), color)
            ttl -= 1
            if ttl <= 0:
                to_del.append((x, y))
            else:
                dim = self._blend(color, self.GRID_BG, 0.35)
                self.flash[(x, y)] = (dim, ttl)
        for k in to_del:
            self.flash.pop(k, None)

        # 3) Scale grid to window and blit
        scaled = pg.transform.scale(gs, self.screen.get_size())
        self.screen.blit(scaled, (0, 0))

        # 4) Agents
        for who, pos in self.agents_pos.items():
            col = self.AGENT_COLORS.get(who, (200, 200, 200))
            self._draw_agent_marker(pos, col)

        # 5) Trails (last N points)
        if self.trails:
            for who, pts in self.trail_pts.items():
                if len(pts) > 1:
                    col = self._blend(
                        self.AGENT_COLORS.get(who, (200, 200, 200)),
                        (255, 255, 255),
                        0.25,
                    )
                    self._draw_polyline(pts[-200:], col)

        # 6) HUD
        self._draw_overlay(tick)

        pg.display.flip()

    def _draw_agent_marker(
        self, pos: tuple[int, int], col: tuple[int, int, int]
    ) -> None:
        x, y = pos
        sx, sy = self._screen_xy(x, y)
        cell_scale = min(
            self.screen.get_width() / self.grid_cols,
            self.screen.get_height() / self.grid_rows,
        )
        r = max(3, int(0.7 * cell_scale))
        self.pg.draw.circle(self.screen, col, (sx, sy), r)
        self.pg.draw.circle(self.screen, (0, 0, 0), (sx, sy), r, 1)  # outline

        # label with agent id if we can find it quickly (few agents)
        if self.font:
            label = None
            for aid, p in self.agents_pos.items():
                if p == pos:
                    label = aid
                    break
            if label:
                ts = self.font.render(label, True, (255, 255, 255))
                rect = ts.get_rect(center=(sx, sy - r - 8))
                self.screen.blit(ts, rect)

    def _draw_polyline(
        self, pts: list[tuple[int, int]], col: tuple[int, int, int]
    ) -> None:
        if len(pts) < 2:
            return
        spts = [self._screen_xy(x, y) for (x, y) in pts]
        width = max(
            1, min(self.screen.get_size()) // max(self.grid_cols, self.grid_rows) // 3
        )
        self.pg.draw.lines(self.screen, col, False, spts, width)

    def _screen_xy(self, x: int, y: int) -> tuple[int, int]:
        w, h = self.screen.get_size()
        return (
            int((x + 0.5) * w / self.grid_cols),
            int((y + 0.5) * h / self.grid_rows),
        )

    def _draw_overlay(self, tick: int) -> None:
        # simple top-left HUD with tick/progress
        w, _ = self.screen.get_size()
        hud_h = 44
        hud = self.pg.Surface((w, hud_h), flags=self.pg.SRCALPHA)
        hud.fill((0, 0, 0, 140))

        total = max(1, self.total_ticks or tick or 1)
        pct = min(1.0, float(tick) / float(total))
        elapsed = time.time() - self.start_wall

        f1 = self.font_big or self.font
        f2 = self.font or f1

        line1 = f"tick {tick}/{total}  ({pct*100:.1f}%)   paused={self.paused}"
        line2 = f"events={self.processed_events}   elapsed={elapsed:.2f}s   scale={self.scale}"

        t1 = f1.render(line1, True, (240, 240, 240))
        t2 = f2.render(line2, True, (220, 220, 220))
        hud.blit(t1, (10, 6))
        hud.blit(t2, (10, 24))

        # thin progress bar
        bar_margin = 10
        bar_y = hud_h - 8
        bar_w = w - 2 * bar_margin
        bar_h = 4
        self.pg.draw.rect(
            hud, (70, 70, 80, 220), (bar_margin, bar_y, bar_w, bar_h), border_radius=2
        )
        self.pg.draw.rect(
            hud,
            (120, 190, 255, 255),
            (bar_margin, bar_y, int(bar_w * pct), bar_h),
            border_radius=2,
        )

        self.screen.blit(hud, (0, 0))

    def _flash(self, cells: list[tuple[int, int]], who: str | None) -> None:
        color = self.PROCESS_FLASH.get(who or "", (255, 255, 255))
        for xy in cells:
            self.flash[xy] = (color, 6)  # ~6 frames

    # ---------- input ----------

    def _pump_events(self) -> None:
        for ev in self.pg.event.get():
            if ev.type == self.pg.QUIT:
                raise SystemExit(0)
            if ev.type == self.pg.KEYDOWN:
                k = ev.key
                if k in (self.pg.K_ESCAPE, self.pg.K_q):
                    raise SystemExit(0)
                elif k == self.pg.K_SPACE:
                    self.paused = not self.paused
                elif k == self.pg.K_n:
                    self.step_once = True
                elif k in (self.pg.K_PLUS, self.pg.K_EQUALS):  # '+' or '='
                    old = self.scale
                    self.scale = min(16, self.scale + 1)
                    if self.scale != old:
                        self._resize_window()
                elif k in (self.pg.K_MINUS, self.pg.K_UNDERSCORE):
                    old = self.scale
                    self.scale = max(1, self.scale - 1)
                    if self.scale != old:
                        self._resize_window()
                elif k == self.pg.K_t:
                    self.trails = not self.trails
                elif k == self.pg.K_0:  # press '0' to auto-fit to monitor
                    self._fit_to_display()

            # Handle OS/window resizes (keep it square and within monitor)
            if ev.type in (
                self.pg.VIDEORESIZE,
                getattr(self.pg, "WINDOWRESIZED", 32769),
            ):
                # Compute a new integer scale that fits the resized window
                w, h = getattr(ev, "size", self.screen.get_size())
                new_scale = max(1, min(w // self.grid_cols, h // self.grid_rows))
                if new_scale != self.scale:
                    self.scale = new_scale
                    self._resize_window()

    def update(self) -> None:
        """Pump input and refresh the current frame for GUI integrations."""
        self._pump_events()
        self._redraw(self.last_tick)

    def on_complete(self) -> None:
        """Completion rendering remains in ``hold_open`` for visible parity."""

    def _resize_window(self) -> None:
        size = (self.grid_cols * self.scale, self.grid_rows * self.scale)
        self.screen = self.pg.display.set_mode(size, self.pg.RESIZABLE)
        self.pg.display.set_caption(self.title)

    def _fit_to_display(self) -> None:
        """Clamp self.scale so arena*scale fits within ~90% of the current display, then resize."""
        try:
            di = self.pg.display.Info()
            max_w, max_h = int(di.current_w * 0.90), int(di.current_h * 0.90)
        except (self.pg.error, AttributeError, TypeError, ValueError):
            # Fallback for headless or display-less environments
            max_w, max_h = 1920, 1080
        fit_scale = max(1, min(max_w // self.grid_cols, max_h // self.grid_rows))
        old = self.scale
        self.scale = max(1, min(self.scale, fit_scale))
        if self.scale != old or self.screen.get_size() != (
            self.grid_cols * self.scale,
            self.grid_rows * self.scale,
        ):
            self._resize_window()

    def hold_open(self) -> None:
        font = self.pg.font.SysFont(None, 24)
        clock = self.pg.time.Clock()
        waiting = True
        while waiting:
            for event in self.pg.event.get():
                if (
                    event.type == self.pg.QUIT
                    or event.type == self.pg.KEYDOWN
                    and event.key
                    in (
                        self.pg.K_SPACE,
                        self.pg.K_ESCAPE,
                    )
                ):
                    waiting = False
            self._redraw(self.last_tick)
            text = font.render(
                "Match complete - Press SPACE to close", True, (255, 255, 255)
            )
            self.screen.blit(text, (20, 50))
            self.pg.display.flip()
            clock.tick(30)
