"""Primary ``bytefray`` command dispatcher."""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Sequence

COMMANDS = ("run", "tournament", "replay", "design", "agents")

def _version_string() -> str:
    from battle_engine.project_info import get_project_info

    info = get_project_info()
    return (
        f"{info.project_name} {info.version}, "
        f"Agent API v{info.agent_api_version}, "
        f"result schema v{info.result_schema_version}, "
        f"replay schema v{info.replay_schema_version}, "
        f"Python {info.python_version}"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bytefray",
        description="Bytefray engine, replay, designer, and agent tools.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=_version_string(),
        help="show the installed Bytefray version and active API/schema versions and exit",
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
    if argv and argv[0] == "create":
        from battle_engine.agent_scaffold import main as scaffold_main

        return scaffold_main(argv[1:])
    if argv and argv[0] == "validate":
        from battle_engine.agent_validation import main as validate_main

        return validate_main(argv[1:])
    if argv and argv[0] == "test":
        from battle_engine.agent_test import main as test_main

        return test_main(argv[1:])
    if argv and argv[0] == "evaluate":
        from battle_engine.agent_evaluation import main as evaluate_main

        return evaluate_main(argv[1:])
    if argv and argv[0] == "evaluations":
        from battle_engine.evaluation_history.cli import main as evaluations_main

        return evaluations_main(argv[1:])
    if argv and argv[0] == "revisions":
        from battle_engine.agent_revisions_cli import main as revisions_main

        return revisions_main(argv[1:])
    if argv and argv[0] == "export":
        from battle_engine.agent_package_cli import export_main

        return export_main(argv[1:])
    if argv and argv[0] == "import":
        from battle_engine.agent_package_cli import import_main

        return import_main(argv[1:])
    if argv and argv[0] == "package":
        from battle_engine.agent_package_cli import package_main

        return package_main(argv[1:])
    if argv and argv[0] == "inspect":
        from battle_engine.agent_inspect import inspect_main

        return inspect_main(argv[1:])
    if argv and argv[0] == "diverge":
        from battle_engine.agent_inspect import diverge_main

        return diverge_main(argv[1:])
    if argv and argv[0] == "_worker":
        # Internal, undocumented: a hidden supervised-execution worker
        # subprocess (docs/specs/agent_lab.md §6), reached only by
        # battle_engine.agent_worker.AgentWorkerHandle spawning another
        # invocation of this same executable. Never invoked directly by a
        # user and deliberately omitted from --help text.
        from battle_engine.agent_worker import main as worker_main

        return worker_main(argv[1:])
    if argv == ["--help"] or argv == ["-h"]:
        return _simple_help(
            "agents",
            "List agents discovered under the configured Bytefray agents "
            "directory, 'agents create <agent-id>' to scaffold a new one, "
            "'agents validate <agent-id>' to dry-run one Python agent, "
            "'agents test <agent-id>' to run a short development match, "
            "'agents inspect <run-dir>' to inspect a development trace, "
            "'agents diverge <run-a> <run-b>' to find the first tick two "
            "traces disagree, 'agents evaluate <candidate-id>' to run a "
            "deterministic candidate/baseline evaluation matrix, "
            "'agents evaluations list|show|compare' to inspect past evaluation "
            "runs, 'agents revisions list|show|restore' to inspect/restore "
            "durably preserved agent source revisions, 'agents export <agent-id>' "
            "to package an agent into a portable .bytefray-agent file, 'agents "
            "package show <file>' to inspect one without executing it, or "
            "'agents import <file>' to import one into this installation.",
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
        if remainder:
            parser.error(f"unrecognized arguments: {' '.join(remainder)}")
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
