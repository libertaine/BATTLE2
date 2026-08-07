"""Windows-friendly launcher for the shared Bytefray replay application."""

from __future__ import annotations

import sys
from collections.abc import Sequence


def replay_arguments(argv: Sequence[str]) -> list[str]:
    """Normalize viewer-friendly arguments for ``battle_client.cli.main``."""
    arguments = list(argv)
    if arguments and not arguments[0].startswith("-"):
        arguments[0:1] = ["--replay", arguments[0]]
    if not any(arg == "--renderer" or arg.startswith("--renderer=") for arg in arguments):
        arguments.extend(("--renderer", "pygame"))
    return arguments


def main(argv: Sequence[str] | None = None) -> int:
    # Importing the shared application is intentionally lazy so --help packaging
    # checks do not initialize Pygame or create a window.
    from battle_client.cli import main as replay_main

    arguments = list(sys.argv[1:] if argv is None else argv)
    return int(replay_main(replay_arguments(arguments)))


if __name__ == "__main__":
    raise SystemExit(main())
