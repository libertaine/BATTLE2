from __future__ import annotations
from typing import Any, Dict, Optional

from .base import AbstractRenderer

class PygameRenderer(AbstractRenderer):
    """
    Lightweight placeholder so CLI can select 'pygame'.
    Implement actual drawing later without touching engine code.
    """

    def __init__(self, scale: int = 2, title: str = "BATTLE - Pygame") -> None:
        super().__init__()
        self.scale = scale
        self.title = title
        self.pg = None
        self.screen = None
        self.arena = 0

    def setup(self, metadata: Optional[Dict[str, Any]] = None) -> None:
        try:
            import pygame  # type: ignore
        except Exception as e:
            raise RuntimeError("Pygame not available. Install pygame or choose --renderer headless.") from e

        self.pg = pygame
        self.pg.init()
        self.arena = int((metadata or {}).get("arena", 512))
        size = self.arena * self.scale
        self.screen = self.pg.display.set_mode((size, size))
        pygame.display.set_caption(self.title)
        self.screen.fill((0, 0, 0))
        self.pg.display.flip()
        super().setup(metadata)

    def on_event(self, event: Dict[str, Any]) -> None:
        # Minimal heartbeat to keep window responsive; implement drawing later.
        for ev in self.pg.event.get():
            if ev.type == self.pg.QUIT:
                raise SystemExit(0)

    def teardown(self) -> None:
        if self.pg:
            self.pg.quit()
