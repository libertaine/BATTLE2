from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from battle_client.renderers.base import AbstractRenderer
from battle_client.renderers.headless import HeadlessRenderer
from battle_client.utils import iter_jsonl, maybe_load_summary, paced

# Pygame renderer is optional; import lazily.
_PYGAME_CLASS: type[AbstractRenderer] | None = None


def _get_pygame_renderer_cls() -> type[AbstractRenderer]:
    global _PYGAME_CLASS
    if _PYGAME_CLASS is None:
        from battle_client.renderers.pygame_renderer import PygameRenderer

        _PYGAME_CLASS = PygameRenderer
    return _PYGAME_CLASS  # type: ignore[return-value]


RENDERERS: dict[str, type[AbstractRenderer] | Callable[[], type[AbstractRenderer]]] = {
    "headless": HeadlessRenderer,
    "pygame": _get_pygame_renderer_cls,  # resolved when selected
}


def _resolve_renderer(name: str) -> type[AbstractRenderer]:
    if name not in RENDERERS:
        raise SystemExit(
            f"Unknown renderer '{name}'. Choose from: {', '.join(sorted(RENDERERS))}"
        )
    cls_or_factory = RENDERERS[name]
    if isinstance(cls_or_factory, type):
        return cls_or_factory
    else:
        return cls_or_factory()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="battle_client",
        description="BATTLE Client — presentation only (replay visualizer)",
    )
    p.add_argument("--replay", required=True, help="Path to replay.jsonl")
    p.add_argument(
        "--renderer",
        default="headless",
        choices=list(RENDERERS.keys()),
        help="Renderer to use (default: headless)",
    )
    p.add_argument(
        "--tick-delay",
        type=float,
        default=0.0,
        help="Optional seconds to sleep between events for pacing (e.g., 0.01)",
    )
    args = p.parse_args(argv)

    replay_path = Path(args.replay).expanduser().resolve()
    if not replay_path.exists():
        raise SystemExit(f"Replay not found: {replay_path}")

    metadata = maybe_load_summary(replay_path)

    RendererClass = _resolve_renderer(args.renderer)
    renderer = RendererClass()  # type: ignore[call-arg]

    try:
        renderer.setup(metadata)

        # Interactive renderers may wait for the viewer before consuming the
        # first replay record. Headless and other renderers start immediately.
        wait_for_start = getattr(renderer, "wait_for_start", None)
        if callable(wait_for_start):
            wait_for_start()

        stream = iter_jsonl(replay_path)
        for ev in paced(stream, args.tick_delay):
            renderer.on_event(ev)

        # Optional post-replay hold for interactive renderers like pygame.
        hold_open = getattr(renderer, "hold_open", None)
        if callable(hold_open):
            hold_open()

        renderer.teardown()

    except KeyboardInterrupt:
        try:
            renderer.teardown()
        finally:
            pass
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 - CLI boundary reports renderer/runtime failures
        renderer.teardown()
        print(f"[battle_client] error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
