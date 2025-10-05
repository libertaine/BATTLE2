"""Shared GUI launcher utilities for BATTLE2 (pygame-based stubs).

This module exposes:
  - run_pygame_app(title, size, rgb_bg) -> int
  - main(title="BATTLE2", size=(800, 600), rgb_bg=(32, 32, 32)) -> None

Both `app/agent_designer.py` and `app/replay_viewer.py` should import:
    from app.main import main
and then call:
    if __name__ == "__main__":
        main(title="...", size=(W, H), rgb_bg=(R, G, B))
"""

from __future__ import annotations

import sys


def run_pygame_app(title: str, size=(800, 600), rgb_bg=(32, 32, 32)) -> int:
    """Start a minimal pygame loop with a solid background."""
    try:
        import pygame
    except ImportError:
        print(
            "pygame not installed. Install extras: `pip install .[gui]` or `pip install pygame`.",
            file=sys.stderr,
        )
        return 1

    pygame.init()
    try:
        screen = pygame.display.set_mode(size)
        pygame.display.set_caption(title)
        running = True
        clock = pygame.time.Clock()
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

            screen.fill(rgb_bg)
            pygame.display.flip()
            clock.tick(60)
    finally:
        pygame.quit()

    return 0


def main(title: str = "BATTLE2", size=(800, 600), rgb_bg=(32, 32, 32)) -> None:
    """Convenience entry — runs the pygame loop and exits with its code."""
    sys.exit(run_pygame_app(title, size=size, rgb_bg=rgb_bg))


if __name__ == "__main__":
    main()

