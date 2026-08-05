"""Primary ``battle2`` command dispatcher."""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Sequence


COMMANDS = ("run", "replay", "design", "agents")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="battle2",
        description="BATTLE2 engine, replay, designer, and agent tools.",
    )
    subcommands = parser.add_subparsers(dest="command")
    subcommands.add_parser(
        "run", add_help=False, help="run a native BATTLE2 or pMARS match"
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
    parser = argparse.ArgumentParser(prog=f"battle2 {command}", description=description)
    parser.print_help()
    return 0


def _design(argv: list[str]) -> int:
    if argv == ["--help"] or argv == ["-h"]:
        return _simple_help(
            "design",
            "Open the optional PySide6 agent designer. Install with: pip install 'battle2[designer]'",
        )
    if argv:
        parser = argparse.ArgumentParser(prog="battle2 design", add_help=False)
        parser.error(f"unrecognized arguments: {' '.join(argv)}")
    try:
        module = importlib.import_module("app.agent_designer")
    except ModuleNotFoundError as exc:
        if exc.name and (exc.name == "PySide6" or exc.name.startswith("PySide6.")):
            print(
                "battle2 design requires the optional designer dependencies; "
                "install with: pip install 'battle2[designer]'",
                file=sys.stderr,
            )
            return 2
        raise
    return int(module.main())


def _agents(argv: list[str]) -> int:
    if argv == ["--help"] or argv == ["-h"]:
        return _simple_help(
            "agents", "List agents discovered under the configured BATTLE2 agents directory."
        )
    if argv:
        parser = argparse.ArgumentParser(prog="battle2 agents", add_help=False)
        parser.error(f"unrecognized arguments: {' '.join(argv)}")
    from battle_engine.cli import main as engine_main

    return engine_main(["--list-agents"])


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
    if namespace.command == "replay":
        from battle_client.cli import main as replay_main

        return replay_main(remainder)
    if namespace.command == "design":
        return _design(remainder)
    if namespace.command == "agents":
        return _agents(remainder)
    parser.error(f"unknown command: {namespace.command}")
    return 2
