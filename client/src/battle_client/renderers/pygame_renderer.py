from __future__ import annotations
from typing import Any, Dict, Optional, Tuple, List
import time

from .base import AbstractRenderer


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
    AGENT_COLORS = {
        "A": (220, 70, 70),    # red-ish
        "B": (70, 120, 220),   # blue-ish
        "C": (80, 200, 120),   # green-ish
        "D": (200, 180, 70),   # amber
    }
    GRID_BG = (12, 12, 14)
    GRID_LINE = (26, 26, 30)
    OWNERSHIP_TINT = {
        "A": (120, 30, 30),
        "B": (30, 60, 120),
        "C": (30, 110, 70),
        "D": (110, 95, 30),
    }
    PROCESS_FLASH = {
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
        self.pg = None
        self.screen = None
        self.grid_surf = None

        # world state
        self.arena: int = 0
        self.owner: List[List[Optional[str]]] = []
        self.agents_pos: Dict[str, Tuple[int, int]] = {}
        self.trail_pts: Dict[str, List[Tuple[int, int]]] = {}
        self.flash: Dict[Tuple[int, int], Tuple[Tuple[int, int, int], int]] = {}

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
        self.font = None
        self.font_big = None

    # ---------- lifecycle ----------


    def setup(self, metadata: Optional[Dict[str, Any]] = None) -> None:
        try:
            import pygame  # type: ignore
        except Exception as e:
            raise RuntimeError("Pygame not available. Install pygame or choose --renderer headless.") from e

        self.pg = pygame
        self.pg.init()

        # Arena/ticks from summary (prefer top-level, then params.*)
        self.arena = int(
            (metadata or {}).get("arena")
            or ((metadata or {}).get("params", {}) or {}).get("arena", 512)
        )
        self.total_ticks = int(
            (metadata or {}).get("ticks")
            or ((metadata or {}).get("params", {}) or {}).get("ticks", 0)
        )

        # Windowed + resizable, auto-fit to ~90% of current display
        di = self.pg.display.Info()
        max_w, max_h = int(di.current_w * 0.90), int(di.current_h * 0.90)

        logical_w = self.arena
        logical_h = self.arena

        # Choose an integer scale that fits; clamp any pre-set scale to fit
        fit_scale = max(1, min(max_w // logical_w, max_h // logical_h))
        self.scale = max(1, min(self.scale, fit_scale))

        window_size = (logical_w * self.scale, logical_h * self.scale)
        self.screen = self.pg.display.set_mode(window_size, self.pg.RESIZABLE)
        self.pg.display.set_caption(self.title)

        # Offscreen logical grid surface
        self.grid_surf = self.pg.Surface((logical_w, logical_h))

        # Fonts
        self.font = self.pg.font.SysFont("consolas", 14)
        self.font_big = self.pg.font.SysFont("consolas", 18)

        # Ownership grid + base gridlines
        self.owner = [[None for _ in range(self.arena)] for _ in range(self.arena)]
        self._draw_full_grid()

        # HUD timing
        self.start_wall = time.time()

        super().setup(metadata)


    def teardown(self) -> None:
        if self.pg:
            self.pg.quit()

    # ---------- event ingestion ----------

    def on_event(self, event: Dict[str, Any]) -> None:
        """
        Supported shapes:
          {"type":"spawn","tick":t,"who":"A","pos":[x,y]}
          {"type":"move","tick":t,"who":"A","from":..., "to":[x,y]}
          {"type":"territory","tick":t,"who":"A","cells":[[x,y],...]}
          {"type":"claim", ...}
          {"type":"death","tick":t,"who":"A"}
          {"type":"tick","tick":t, "positions":{"A":[x,y],...}, "writes":[[x,y],...]}  # optional
        """
        # keep window responsive
        self._pump_events()

        et = event.get("type")
        who = event.get("who")
        tick = int(event.get("tick", 0))

        # HUD counters
        self.processed_events += 1
        self.last_tick = tick

        # pause gating
        if self.paused and not self.step_once:
            return
        self.step_once = False

        def _apply_cells(cells: List[Tuple[int, int]], owner: Optional[str]) -> None:
            if not cells:
                return
            if owner is not None:
                for (x, y) in cells:
                    if 0 <= x < self.arena and 0 <= y < self.arena:
                        self.owner[y][x] = owner
            self._flash(cells, owner)

        if et == "spawn":
            pos = self._to_xy(event.get("pos"))
            if pos:
                self.agents_pos[who] = pos
                if self.trails:
                    self.trail_pts.setdefault(who, []).append(pos)
                self._flash([pos], who)

        elif et == "move":
            to_pos = self._to_xy(event.get("to"))
            if to_pos:
                self.agents_pos[who] = to_pos
                if self.trails:
                    self.trail_pts.setdefault(who, []).append(to_pos)
                self._flash([to_pos], who)

        elif et in ("territory", "claim"):
            cells = self._cells_from_event(event)  # expects "cells": [[x,y],...]
            _apply_cells(cells, who)

        elif et in ("death", "die"):
            pos = self.agents_pos.get(who)
            if pos:
                self._flash([pos], who)

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
                cells: List[Tuple[int, int]] = []
                for c in batch:
                    xy = self._to_xy(c)
                    if xy:
                        cells.append(xy)
                _apply_cells(cells, event.get("who"))

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

        # redraw after processing
        self._redraw(tick)

    # ---------- drawing helpers ----------

    def _to_xy(self, p) -> Optional[Tuple[int, int]]:
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            return None
        try:
            x, y = int(p[0]), int(p[1])
        except Exception:
            return None
        return (x, y)

    def _cells_from_event(self, event: Dict[str, Any]) -> List[Tuple[int, int]]:
        cells = event.get("cells")
        out: List[Tuple[int, int]] = []
        if isinstance(cells, list):
            for c in cells:
                xy = self._to_xy(c)
                if xy:
                    out.append(xy)
        return out

    def _blend(self, a: Tuple[int, int, int], b: Tuple[int, int, int], alpha: float) -> Tuple[int, int, int]:
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

        step = max(16, self.arena // 32)  # avoid too many lines for large arenas
        line_color = self.GRID_LINE
        for x in range(0, self.arena, step):
            pg.draw.line(gs, line_color, (x, 0), (x, self.arena - 1))
        for y in range(0, self.arena, step):
            pg.draw.line(gs, line_color, (0, y), (self.arena - 1, y))

    def _redraw(self, tick: int) -> None:
        pg = self.pg
        gs = self.grid_surf

        # 1) Ownership fill
        tint_alpha = 0.65
        for y in range(self.arena):
            row = self.owner[y]
            for x in range(self.arena):
                who = row[x]
                if who is None:
                    continue
                tint = self.OWNERSHIP_TINT.get(who, (80, 80, 80))
                gs.set_at((x, y), self._blend(self.GRID_BG, tint, tint_alpha))

        # 2) Processing flashes (fade)
        to_del = []
        for (x, y), (color, ttl) in self.flash.items():
            if 0 <= x < self.arena and 0 <= y < self.arena:
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
                    col = self._blend(self.AGENT_COLORS.get(who, (200, 200, 200)), (255, 255, 255), 0.25)
                    self._draw_polyline(pts[-200:], col)

        # 6) HUD
        self._draw_overlay(tick)

        pg.display.flip()

    def _draw_agent_marker(self, pos: Tuple[int, int], col: Tuple[int, int, int]) -> None:
        x, y = pos
        sx = int((x + 0.5) * self.scale)
        sy = int((y + 0.5) * self.scale)
        r = max(3, int(0.7 * self.scale))
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

    def _draw_polyline(self, pts: List[Tuple[int, int]], col: Tuple[int, int, int]) -> None:
        if len(pts) < 2:
            return
        spts = [(int((x + 0.5) * self.scale), int((y + 0.5) * self.scale)) for (x, y) in pts]
        self.pg.draw.lines(self.screen, col, False, spts, max(1, self.scale // 3))

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
        self.pg.draw.rect(hud, (70, 70, 80, 220), (bar_margin, bar_y, bar_w, bar_h), border_radius=2)
        self.pg.draw.rect(hud, (120, 190, 255, 255),
                          (bar_margin, bar_y, int(bar_w * pct), bar_h), border_radius=2)

        self.screen.blit(hud, (0, 0))

    def _flash(self, cells: List[Tuple[int, int]], who: Optional[str]) -> None:
        color = self.PROCESS_FLASH.get(who or "", (255, 255, 255))
        for xy in cells:
            self.flash[xy] = (color, 6)  # ~6 frames

    # ---------- input ----------

    def _pump_events(self) -> None:
        """Process window and keyboard; resize window if scale changes."""
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
            if ev.type in (self.pg.VIDEORESIZE, getattr(self.pg, "WINDOWRESIZED", 32769)):
                # Compute a new integer scale that fits the resized window
                w, h = getattr(ev, "size", self.screen.get_size())
                new_scale = max(1, min(w // self.arena, h // self.arena))
                if new_scale != self.scale:
                    self.scale = new_scale
                    self._resize_window()


     
    def _resize_window(self) -> None:
        size = (self.arena * self.scale, self.arena * self.scale)
        self.screen = self.pg.display.set_mode(size, self.pg.RESIZABLE)
        self.pg.display.set_caption(self.title)

    def _fit_to_display(self) -> None:
        """Clamp self.scale so arena*scale fits within ~90% of the current display, then resize."""
        di = self.pg.display.Info()
        max_w, max_h = int(di.current_w * 0.90), int(di.current_h * 0.90)
        fit_scale = max(1, min(max_w // self.arena, max_h // self.arena))
        old = self.scale
        self.scale = max(1, min(self.scale, fit_scale))
        if self.scale != old:
            self._resize_window()

