# app/match_runner.py
import sys, inspect, os
from pathlib import Path

def main() -> int:
    try:
        import pygame
    except ImportError:
        print("pygame not installed. Try `pip install .[gui]` or `pip install pygame`.", file=sys.stderr)
        return 1


    # Import the real Pygame renderer
    try:
        from battle_client.renderers.pygame_renderer import PygameRenderer
    except Exception as e:
        print("match_runner error: cannot import PygameRenderer:", e, file=sys.stderr)
        return 1

    pygame.init()
    try:
        screen = pygame.display.set_mode((960, 540))
        pygame.display.set_caption("BATTLE – Pygame Runner")

        # Instantiate renderer (defaults OK; adjust kwargs if you use them)
        renderer = PygameRenderer()

        # Call setup() — accept either 0-arg or (screen)
        try:
            sig = inspect.signature(renderer.setup)
        except Exception:
            sig = None
        try:
            if sig and len(sig.parameters) >= 2:
                renderer.setup(screen)
            else:
                renderer.setup()
        except TypeError:
            renderer.setup(screen)

        # Event loop — adapt pygame events to dicts (renderer expects .get())
        clock, running = pygame.time.Clock(), True
        while running:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
                    break
                ev_payload = {"type": ev.type}
                try:
                    ev_payload.update(getattr(ev, "dict", {}) or {})
                except Exception:
                    pass
                renderer.on_event(ev_payload)

            pygame.display.flip()
            clock.tick(60)

        try:
            renderer.teardown()
        except Exception:
            pass
        pygame.quit()
        return 0

    except Exception as e:
        print("match_runner error:", e, file=sys.stderr)
        try: pygame.quit()
        except Exception: pass
        return 1

if __name__ == "__main__":
    sys.exit(main())
