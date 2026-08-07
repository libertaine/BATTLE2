"""Primary ``bytefray`` command dispatcher.

``battle2`` is retained as a deprecated compatibility alias for the project's
former name (see :func:`battle2_main`); both names dispatch to :func:`main`
and behave identically apart from the alias printing a deprecation notice.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Sequence


COMMANDS = ("run", "tournament", "replay", "design", "agents")

BATTLE2_DEPRECATION_NOTICE = (
    "BATTLE2 has been renamed Bytefray. The 'battle2' command is deprecated; "
    "use 'bytefray' instead."
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bytefray",
        description="Bytefray engine, replay, designer, and agent tools.",
    )
    subcommands = parser.add_subparsers(dest="command")
    subcommands.add_parser(
        "run", add_help=False, help="run a native Bytefray or pMARS match"
    )
    subcommands.add_parser(
        "tournament", add_help=False, help="run or resume a native round-robin tournament"
    )
    subcommands.add_parser(
        "replay", add_help=False, help="play a replay using headless or Pygame output"
    )
    subcommands.add_parser(
        "design", add_help=False, help="open the optional PySide6 agent designer"
    )
    subcommands.add_parser(
        "agents", add_help=False, help="list discovered agent manifests"
    )
    return parser


def _simple_help(command: str, description: str) -> int:
    parser = argparse.ArgumentParser(prog=f"bytefray {command}", description=description)
    parser.print_help()
    return 0


def _design(argv: list[str]) -> int:
    if argv == ["--help"] or argv == ["-h"]:
        return _simple_help(
            "design",
            "Open the optional PySide6 agent designer. Install with: "
            "pip install 'bytefray[designer]'",
        )
    if argv:
        parser = argparse.ArgumentParser(prog="bytefray design", add_help=False)
        parser.error(f"unrecognized arguments: {' '.join(argv)}")
    try:
        module = importlib.import_module("app.agent_designer")
    except ModuleNotFoundError as exc:
        if exc.name and (exc.name == "PySide6" or exc.name.startswith("PySide6.")):
            print(
                "bytefray design requires the optional designer dependencies; "
                "install with: pip install 'bytefray[designer]'",
                file=sys.stderr,
            )
            return 2
        raise
    return int(module.main())


def _agents(argv: list[str]) -> int:
    if argv == ["--help"] or argv == ["-h"]:
        return _simple_help(
            "agents", "List agents discovered under the configured Bytefray agents directory."
        )
    if argv:
        parser = argparse.ArgumentParser(prog="bytefray agents", add_help=False)
        parser.error(f"unrecognized arguments: {' '.join(argv)}")
    from battle_engine.cli import main as engine_main

    return engine_main(["--list-agents"])


def _tournament(argv: list[str]) -> int:
    from battle_engine.tournament_cli import main as tournament_main

    return tournament_main(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = _parser()
    namespace, remainder = parser.parse_known_args(arguments)
    if namespace.command is None:
        parser.print_help()
        return 0

    if namespace.command == "run":
        from battle_engine.cli import main as engine_main

        return engine_main(remainder)
    if namespace.command == "tournament":
        return _tournament(remainder)
    if namespace.command == "replay":
        from battle_client.cli import main as replay_main

        return replay_main(remainder)
    if namespace.command == "design":
        return _design(remainder)
    if namespace.command == "agents":
        return _agents(remainder)
    parser.error(f"unknown command: {namespace.command}")
    return 2


def battle2_main(argv: Sequence[str] | None = None) -> int:
    """Deprecated ``battle2`` alias; dispatches to :func:`main` unchanged.

    Prints a one-line deprecation notice to stderr and otherwise produces
    identical behavior, output, and exit codes to invoking ``bytefray``
    directly with the same arguments.
    """
    print(BATTLE2_DEPRECATION_NOTICE, file=sys.stderr)
    return main(argv)
