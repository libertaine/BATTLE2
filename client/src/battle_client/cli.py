from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from battle_client.renderers.base import AbstractRenderer, RendererDependencyError
from battle_client.renderers.headless import HeadlessRenderer
from battle_client.player import ReplayPlayer
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
        prog="bytefray replay",
        description="Bytefray replay client — presentation only (replay visualizer)",
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
        p.error(f"Replay not found: {replay_path}")

    metadata = maybe_load_summary(replay_path)

    RendererClass = _resolve_renderer(args.renderer)
    renderer = RendererClass()  # type: ignore[call-arg]

    try:
        ReplayPlayer(renderer).play(paced(iter_jsonl(replay_path), args.tick_delay), metadata)
    except KeyboardInterrupt:
        pass
    except SystemExit:
        raise
    except RendererDependencyError as e:
        print(f"[battle_client] dependency error: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 - CLI boundary reports renderer/runtime failures
        print(f"[battle_client] error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
