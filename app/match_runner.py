# app/match_runner.py
import sys


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
    renderer = None
    try:
        screen = pygame.display.set_mode((960, 540))
        pygame.display.set_caption("BATTLE – Pygame Runner")

        # Instantiate renderer (defaults OK; adjust kwargs if you use them)
        renderer = PygameRenderer()

        renderer.setup()

        clock, running = pygame.time.Clock(), True
        while running:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
                    break
            renderer.update()
            clock.tick(60)

        renderer.on_complete()
        return 0
    except Exception as e:
        print("match_runner error:", e, file=sys.stderr)
        return 1
    finally:
        try:
            if renderer is not None:
                renderer.teardown()
        except Exception:
            pass
        pygame.quit()

if __name__ == "__main__":
    sys.exit(main())
