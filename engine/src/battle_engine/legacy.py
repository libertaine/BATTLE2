"""Compatibility entry points retained throughout the v0.2 transition."""

from __future__ import annotations

import importlib
import argparse
import sys
from collections.abc import Sequence


def battle_cli(argv: Sequence[str] | None = None) -> int:
    from battle_engine.cli import main

    return main(argv)


def _gui_arguments(command: str, description: str, argv: Sequence[str] | None) -> bool:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments in (["--help"], ["-h"]):
        argparse.ArgumentParser(prog=command, description=description).print_help()
        return False
    if arguments:
        parser = argparse.ArgumentParser(prog=command, add_help=False)
        parser.error(f"unrecognized arguments: {' '.join(arguments)}")
    return True


def match_runner(argv: Sequence[str] | None = None) -> int:
    if not _gui_arguments("match-runner", "Launch the legacy Pygame match window.", argv):
        return 0
    from app.match_runner import main

    return int(main())


def agent_designer(argv: Sequence[str] | None = None) -> int:
    if not _gui_arguments(
        "battle-agent-designer", "Launch the legacy PySide6 agent designer.", argv
    ):
        return 0
    try:
        module = importlib.import_module("app.agent_designer")
    except ModuleNotFoundError as exc:
        if exc.name and (exc.name == "PySide6" or exc.name.startswith("PySide6.")):
            print(
                "battle-agent-designer requires optional dependencies; "
                "install with: pip install 'bytefray[designer]'",
                file=sys.stderr,
            )
            return 2
        raise
    return int(module.main())
