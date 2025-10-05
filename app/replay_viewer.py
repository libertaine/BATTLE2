"""Battle2 Replay Viewer launcher."""
import sys

def _run():
    # 1) Prefer client's CLI if available (adjust flags if you have a viewer mode)
    try:
        from battle_client import cli as bc_cli
        if hasattr(bc_cli, "main"):
            return int(bc_cli.main(["--mode", "replay-viewer"]))
    except Exception:
        pass

    # 2) Try a direct pygame renderer entry
    try:
        from battle_client.renderers.pygame_renderer import main as renderer_main
        return int(renderer_main())
    except Exception:
        pass

    # 3) Fallback minimal window
    try:
        import pygame
        pygame.init()
        screen = pygame.display.set_mode((960, 540))
        pygame.display.set_caption("Battle Replay Viewer (fallback)")
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
            screen.fill((20, 20, 50))
            pygame.display.flip()
        pygame.quit()
        return 0
    except Exception as e:
        print("Failed to launch Replay Viewer:", e, file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(_run())
