# renderers.py — richer visualization + GAME OVER page
import pygame, math, hashlib


def _color_for(agent_id: str):
    h = hashlib.sha256(agent_id.encode()).digest()
    return (64 + h[0] % 192, 64 + h[9] % 192, 64 + h[17] % 192)


class PygameRenderer:
    def __init__(self, width=1000, height=760):
        self.width, self.height = width, height
        self.screen = None
        self.font = None
        self.clock = None
        self.center = (width // 2, height // 2)
        self.r_out = 300
        self._last_points = []

    def on_init(self, kernel):
        pygame.init()
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption("BATTLE")
        self.font = pygame.font.SysFont("DejaVu Sans Mono", 14)
        self.clock = pygame.time.Clock()

    def _draw_ring(self, snapshot):
        arena_size = snapshot["config"]["arena_size"]
        owners = snapshot.get("__owners__")
        if not owners:
            return
        cx, cy = self.center
        r = self.r_out
        step = max(1, arena_size // 2000)
        for a in range(0, arena_size, step):
            col = _color_for(owners[a]) if owners[a] else (80, 80, 80)
            ang = 2 * math.pi * (a / arena_size)
            x = cx + r * math.cos(ang)
            y = cy + r * math.sin(ang)
            pygame.draw.circle(self.screen, col, (int(x), int(y)), 2)

        # decay trail
        for x, y, col, life in self._last_points:
            if life > 0:
                pygame.draw.circle(self.screen, col, (int(x), int(y)), 3)
        self._last_points = [
            (x, y, c, life - 1) for (x, y, c, life) in self._last_points if life > 1
        ]

        # add new diffs to trail
        for d in snapshot.get("memory_diffs", []):
            addr, ln, owner = d["addr"], d["len"], d.get("owner")
            col = _color_for(owner) if owner else (160, 160, 160)
            for i in range(ln):
                a = (addr + i) % arena_size
                ang = 2 * math.pi * (a / arena_size)
                x = cx + r * math.cos(ang)
                y = cy + r * math.sin(ang)
                self._last_points.append((x, y, col, 5))

    def _draw_sidebar(self, tick, snapshot):
        self.screen.fill((18, 18, 22))
        y = 20
        t = self.font.render(f"Tick {tick}", True, (220, 220, 230))
        self.screen.blit(t, (20, y))
        y += 24

        scores = snapshot.get("score", {})
        agents = snapshot.get("agents", [])
        owners = snapshot.get("__owners__")
        counts = {}
        if owners:
            for o in owners:
                if o:
                    counts[o] = counts.get(o, 0) + 1
        arena_size = snapshot["config"]["arena_size"]

        for a in agents:
            aid = a["id"]
            col = _color_for(aid)
            alive = a["alive"]
            sc = scores.get(aid, 0)
            own = counts.get(aid, 0)
            pct = (own * 100.0 / arena_size) if arena_size else 0.0
            label = self.font.render(
                f"{aid} {'(dead)' if not alive else ''}  s:{sc}  own:{pct:.1f}%",
                True,
                col,
            )
            self.screen.blit(label, (20, y))
            y += 18
            # bar
            bar_w = 320
            bar_h = 10
            filled = int(bar_w * pct / 100.0)
            pygame.draw.rect(
                self.screen, (60, 60, 70), (20, y, bar_w, bar_h), border_radius=3
            )
            pygame.draw.rect(self.screen, col, (20, y, filled, bar_h), border_radius=3)
            y += 16

    def on_tick(self, tick, snapshot):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                raise SystemExit
        self._draw_sidebar(tick, snapshot)
        self._draw_ring(snapshot)
        pygame.display.flip()
        self.clock.tick(60)

    def on_close(self):
        pygame.quit()

    def on_game_over(self, summary: dict):
        if self.screen is None:
            pygame.init()
            self.screen = pygame.display.set_mode((self.width, self.height))
            self.font = pygame.font.SysFont("DejaVu Sans Mono", 14)
            self.clock = pygame.time.Clock()

        self.screen.fill((15, 15, 18))
        title = pygame.font.SysFont("DejaVu Sans Mono", 24, bold=True)
        t = title.render("GAME OVER", True, (240, 240, 255))
        self.screen.blit(t, (20, 20))

        win = summary.get("winner", "")
        wm = summary.get("win_mode", "score_fallback")
        ticks = summary.get("ticks", 0)
        arena = summary.get("arena_size", 0)
        line1 = self.font.render(
            f"Winner: {win or 'tie'}   Mode: {wm}   Ticks: {ticks}   Arena: {arena}",
            True,
            (230, 230, 230),
        )
        self.screen.blit(line1, (20, 60))

        y = 100
        hdr = self.font.render(
            "Leaderboard (score, kills, territory max/avg %):", True, (200, 200, 210)
        )
        self.screen.blit(hdr, (20, y))
        y += 20

        for a in summary.get("agents", []):
            aid = a["id"]
            col = _color_for(aid)
            s = a["score"]
            k = a["kills"]
            tmax = a["territory_pct_max"]
            tavg = a["territory_pct_avg"]
            alive = "alive" if a["alive"] else "dead"
            row = self.font.render(
                f"{aid:>6}  s:{s:<6}  k:{k:<2}  own_max:{tmax:5.1f}%  own_avg:{tavg:5.1f}%  {alive}",
                True,
                col,
            )
            self.screen.blit(row, (20, y))
            y += 18

        y += 10
        hint = self.font.render(
            "Press any key or close window to exit.", True, (180, 180, 190)
        )
        self.screen.blit(hint, (20, y))
        pygame.display.flip()

        waiting = True
        while waiting:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    waiting = False
                elif ev.type == pygame.KEYDOWN or ev.type == pygame.MOUSEBUTTONDOWN:
                    waiting = False
            self.clock.tick(30)
