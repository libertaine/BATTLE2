from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from battle_engine.replay import ReplayFormatError

from battle_client.player import DEFAULT_TICK_INTERVAL, SPEEDS, ReplayPlayer
from battle_client.renderers.base import RendererDependencyError
from battle_client.renderers.headless import HeadlessRenderer
from battle_client.session import ReplaySession, ReplaySessionError
from battle_client.utils import iter_jsonl, maybe_load_summary, paced

# Pygame renderer is optional; import lazily. It is intentionally *not*
# AbstractRenderer-shaped (see battle_client.player's module docstring), so
# RENDERERS/_resolve_renderer below are typed loosely (type[Any]) rather
# than falsely claiming every entry is an AbstractRenderer subclass.
_PYGAME_CLASS: type[Any] | None = None


def _get_pygame_renderer_cls() -> type[Any]:
    global _PYGAME_CLASS
    if _PYGAME_CLASS is None:
        from battle_client.renderers.pygame_renderer import PygameRenderer

        _PYGAME_CLASS = PygameRenderer
    return _PYGAME_CLASS


RENDERERS: dict[str, type[Any] | Callable[[], type[Any]]] = {
    "headless": HeadlessRenderer,
    "pygame": _get_pygame_renderer_cls,  # resolved when selected
}


def _resolve_renderer(name: str) -> type[Any]:
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
        description="Bytefray replay client -- presentation only (replay visualizer)",
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
        help=(
            "For --renderer headless: seconds to sleep between streamed "
            "records (0 = no delay). For --renderer pygame: the "
            "interactive viewer's base seconds-per-tick at 1x speed "
            f"(0 defaults to {DEFAULT_TICK_INTERVAL:g}); the viewer's own "
            "in-window speed control scales this at runtime, it does not "
            "replace it."
        ),
    )
    p.add_argument(
        "--start-tick",
        type=int,
        default=None,
        help="--renderer pygame only: open positioned at this tick "
        "(snapped to the nearest recorded tick, clamped to range)",
    )
    p.add_argument(
        "--paused",
        action="store_true",
        help="--renderer pygame only: open paused instead of playing",
    )
    p.add_argument(
        "--speed",
        type=float,
        default=None,
        help="--renderer pygame only: initial playback speed multiplier "
        f"(snapped to the nearest of {list(SPEEDS)})",
    )
    p.add_argument(
        "--trace",
        type=Path,
        default=None,
        help="--renderer pygame only: path to bound API-v2 trace JSONL for perspective viewing",
    )
    p.add_argument(
        "--perspective",
        type=str,
        default=None,
        help="--renderer pygame only: initial entrant perspective ('broadcast' or entrant ID like 'A')",
    )
    args = p.parse_args(argv)

    replay_path = Path(args.replay).expanduser().resolve()
    if not replay_path.exists():
        p.error(f"Replay not found: {replay_path}")

    if args.renderer == "pygame":
        return _run_interactive(args, replay_path)
    return _run_streaming(args, replay_path)


def _run_streaming(args: argparse.Namespace, replay_path: Path) -> int:
    """The original one-shot forward-stream path: headless (and any future
    stream-only renderer registered in RENDERERS).
    """
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
    except Exception as e:
        print(f"[battle_client] error: {e}", file=sys.stderr)
        return 1

    return 0


def _run_interactive(args: argparse.Namespace, replay_path: Path) -> int:
    """The interactive Pygame path: ReplaySession + PlaybackController,
    bypassing ReplayPlayer's forward-only stream entirely (see
    battle_client.player's module docstring for why).
    """
    session = ReplaySession()
    try:
        session.load(replay_path)
    except (ReplaySessionError, ReplayFormatError) as e:
        print(f"[battle_client] error: {e}", file=sys.stderr)
        return 1

    tick_interval = args.tick_delay if args.tick_delay > 0 else DEFAULT_TICK_INTERVAL
    RendererClass = _resolve_renderer("pygame")
    renderer = RendererClass()  # type: ignore[call-arg]

    trace_path: Path | None = None
    if args.trace is not None:
        trace_path = Path(args.trace).expanduser().resolve()
    else:
        candidate = replay_path.with_name("trace.jsonl")
        if candidate.is_file():
            trace_path = candidate

    perspective_manager = None
    if trace_path is not None:
        from battle_client.perspective import PerspectiveManager

        perspective_manager = PerspectiveManager(
            replay_path,
            trace_path,
            initial_mode=args.perspective or "broadcast",
        )

    # An explicitly requested perspective must never fail silently.  The viewer
    # still opens on the canonical replay -- ordinary replay never depends on a
    # trace -- but the user is told why Perspective Cam is not available rather
    # than being dropped into broadcast with no explanation.
    if args.perspective is not None or args.trace is not None:
        if perspective_manager is None:
            print(
                "[battle_client] Perspective Cam unavailable: no trace supplied and no "
                f"companion trace.jsonl beside {replay_path.name}.",
                file=sys.stderr,
            )
        elif not perspective_manager.available:
            print(f"[battle_client] {perspective_manager.status_message}", file=sys.stderr)
        elif args.perspective is not None and not perspective_manager.is_mode_valid(
            args.perspective
        ):
            available = ", ".join(("broadcast", *perspective_manager.entrants))
            print(
                f"[battle_client] Unknown perspective {args.perspective!r}; "
                f"available: {available}. Showing broadcast.",
                file=sys.stderr,
            )
        elif args.perspective is not None and perspective_manager.mode != args.perspective:
            # is_mode_valid passed (a real entrant), but the manager's own
            # attempt to select it during construction did not stick -- that
            # entrant's lazy projection load failed.
            load_error = perspective_manager.load_error_for(args.perspective)
            print(
                f"[battle_client] Perspective {args.perspective!r} unavailable: "
                f"{load_error}. Showing broadcast.",
                file=sys.stderr,
            )

    try:
        renderer.run(
            session,
            tick_interval=tick_interval,
            start_tick=args.start_tick,
            start_paused=args.paused,
            initial_speed=args.speed,
            perspective_manager=perspective_manager,
            initial_perspective=args.perspective,
        )
    except KeyboardInterrupt:
        pass
    except SystemExit:
        raise
    except RendererDependencyError as e:
        print(f"[battle_client] dependency error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"[battle_client] error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
