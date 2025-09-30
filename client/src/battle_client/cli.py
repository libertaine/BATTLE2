from __future__ import annotations
import argparse
import sys
from pathlib import Path
from typing import Dict, Any, Optional, Type

from battle_client.renderers.base import AbstractRenderer
from battle_client.renderers.headless import HeadlessRenderer
from battle_client.utils import iter_jsonl, maybe_load_summary, paced

# Pygame renderer is optional; import lazily.
_PYGAME_CLASS: Optional[Type[AbstractRenderer]] = None
def _get_pygame_renderer_cls() -> Type[AbstractRenderer]:
    global _PYGAME_CLASS
    if _PYGAME_CLASS is None:
        from battle_client.renderers.pygame_renderer import PygameRenderer
        _PYGAME_CLASS = PygameRenderer
    return _PYGAME_CLASS  # type: ignore[return-value]

RENDERERS: Dict[str, Type[AbstractRenderer]] = {
    "headless": HeadlessRenderer,
    "pygame": _get_pygame_renderer_cls,  # resolved when selected
}

def _resolve_renderer(name: str) -> Type[AbstractRenderer]:
    if name not in RENDERERS:
        raise SystemExit(f"Unknown renderer '{name}'. Choose from: {', '.join(sorted(RENDERERS))}")
    cls_or_factory = RENDERERS[name]
    if callable(cls_or_factory) and getattr(cls_or_factory, "__name__", "") == "_get_pygame_renderer_cls":
        return cls_or_factory()  # type: ignore[misc]
    return cls_or_factory  # type: ignore[return-value]

def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="battle_client",
        description="BATTLE Client — presentation only (replay visualizer)"
    )
    p.add_argument("--replay", required=True, help="Path to replay.jsonl")
    p.add_argument("--renderer", default="headless", choices=list(RENDERERS.keys()),
                   help="Renderer to use (default: headless)")
    p.add_argument("--tick-delay", type=float, default=0.0,
                   help="Optional seconds to sleep between events for pacing (e.g., 0.01)")
    args = p.parse_args(argv)

    replay_path = Path(args.replay).expanduser().resolve()
    if not replay_path.exists():
        raise SystemExit(f"Replay not found: {replay_path}")

    # Load optional metadata (summary.json)
    metadata = maybe_load_summary(replay_path)

    # Instantiate renderer
    RendererClass = _resolve_renderer(args.renderer)
    renderer = RendererClass()  # type: ignore[call-arg]

    try:
        renderer.setup(metadata)
        stream = iter_jsonl(replay_path)
        for ev in paced(stream, args.tick_delay):
            renderer.on_event(ev)
        renderer.teardown()
    except KeyboardInterrupt:
        # Graceful exit
        try:
            renderer.teardown()
        finally:
            pass
    except SystemExit:
        # Bubble up
        raise
    except Exception as e:
        # Ensure teardown runs even on errors
        try:
            renderer.teardown()
        finally:
            print(f"[battle_client] error: {e}", file=sys.stderr)
            return 1

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
