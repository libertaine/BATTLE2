"""Headless CLI adapter for ``TournamentService``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from battle_engine.agent_api import AgentValidationError
from battle_engine.agents import resolve_agent
from battle_engine.builtins import SUPPORTED, build_agent
from battle_engine.config import Config, Weights
from battle_engine.match_service import MatchEntrant
from battle_engine.paths import get_data_root
from battle_engine.rules import BYTEFRAY_RULESET_ID
from battle_engine.ruleset_policy import (
    BYTEFRAY_RULESET_V2_ID,
    BYTEFRAY_RULESET_V4_ALPHA1_ID,
    BYTEFRAY_RULESET_V4_ALPHA2_ID,
    BYTEFRAY_RULESET_V4_ID,
    resolve_omitted_ruleset_for_agents,
)
from battle_engine.starters import describe_bootstrap_errors, ensure_starter_agents
from battle_engine.tournament_service import (
    TournamentConfigurationError,
    TournamentRequest,
    TournamentService,
)


def _positive(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bytefray tournament",
        description="Run or resume a homogeneous native round-robin tournament.",
    )
    parser.add_argument("agents", nargs="+", help="two or more discovered or built-in agents")
    parser.add_argument("--rounds", type=_positive, default=1)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--ticks", type=_positive, default=3000)
    parser.add_argument("--arena", type=_positive, default=4096)
    parser.add_argument("--quota", type=_positive, default=8)
    parser.add_argument(
        "--win-mode",
        choices=["survival", "score", "score_fallback"],
        default="score_fallback",
    )
    parser.add_argument("--alive-w", type=float, default=1.0)
    parser.add_argument("--kill-w", type=float, default=5.0)
    parser.add_argument("--territory-w", type=float, default=1.0)
    parser.add_argument("--territory-bucket", type=_positive, default=64)
    parser.add_argument(
        "--ruleset",
        choices=[
            BYTEFRAY_RULESET_ID,
            BYTEFRAY_RULESET_V2_ID,
            BYTEFRAY_RULESET_V4_ALPHA1_ID,
            BYTEFRAY_RULESET_V4_ALPHA2_ID,
            BYTEFRAY_RULESET_V4_ID,
        ],
        default=None,
        help=(
            "gameplay Ruleset identity. If omitted, Agent API v1 Python-only "
            f"rosters use {BYTEFRAY_RULESET_V2_ID}, Agent API v2 Python-only "
            f"rosters use {BYTEFRAY_RULESET_V4_ID}, and VM/blob-only "
            f"rosters use {BYTEFRAY_RULESET_ID}; a mixed Python/VM roster "
            f"without an explicit choice uses {BYTEFRAY_RULESET_ID}. "
            f"{BYTEFRAY_RULESET_V2_ID}, {BYTEFRAY_RULESET_V4_ID}, and both v4 "
            "alphas support Python entrants only; every v4 identity requires "
            f"Agent API v2. {BYTEFRAY_RULESET_V4_ID} is the current, "
            "permanent v4 gameplay contract and is what an omitted Ruleset "
            "selects for an Agent API v2 roster; v4 alpha1/alpha2 remain "
            f"selectable by name to reproduce historical prerelease matches. "
            f"Under {BYTEFRAY_RULESET_V4_ID} (as under both v4 alphas) each "
            "scheduled pairing is placed from its own derived match seed "
            "rather than from the roster-wide seat spacing. "
            "Affects gameplay semantics and is recorded in each match's "
            "result/replay artifacts."
        ),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    return parser


def _default_output(root: Path, names: list[str], seed: int) -> Path:
    label = "-vs-".join(names)
    safe = "".join(
        character if character.isalnum() or character in "-_." else "_"
        for character in label
    )
    return root / "runs" / "tournaments" / f"{safe}-seed-{seed}"


def _resolve_entrant(root: Path, name: str, start: int) -> MatchEntrant:
    try:
        spec = resolve_agent(root, name)
    except SystemExit:
        spec = None
    if spec is not None and spec.kind == "python":
        return MatchEntrant.python(name, spec.display or name, start, spec)
    if spec is not None and spec.blob is not None and spec.blob.is_file():
        return MatchEntrant(name, spec.display or name, start, spec.blob.read_bytes())
    if name in SUPPORTED:
        return MatchEntrant(
            name,
            spec.display if spec is not None else name,
            start,
            build_agent(name, start),
        )
    raise TournamentConfigurationError(
        f"Agent {name!r} is not an executable Python agent, blob, or built-in."
    )


def _print_result(result) -> None:
    counts = {status: 0 for status in ("completed", "failed", "rejected", "corrupted")}
    for match in result.matches:
        counts[match.status] = counts.get(match.status, 0) + 1
    print(f"Tournament: {result.tournament_id}")
    print(
        f"Matches: completed={counts['completed']} "
        f"failed={counts['failed']} rejected={counts['rejected']} "
        f"corrupted={counts['corrupted']}"
    )
    print("Standings:")
    print("entrant              played  wins  losses  ties  score")
    for row in result.standings:
        print(
            f"{row.agent_id:20} {row.played:6} {row.wins:5} "
            f"{row.losses:7} {row.ties:5} {row.score_total:g}"
        )
    print(f"State: {result.state_path}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if len(args.agents) < 2:
        print("ERROR: tournament requires at least two agents", file=sys.stderr)
        return 2
    if len(set(args.agents)) != len(args.agents):
        print("ERROR: tournament agent names must be unique", file=sys.stderr)
        return 2

    root = get_data_root()
    try:
        bootstrap = ensure_starter_agents(data_root=root)
        warning = describe_bootstrap_errors(bootstrap)
        if warning:
            print(f"WARNING: {warning}", file=sys.stderr)
        spacing = max(1, args.arena // len(args.agents))
        entrants = tuple(
            _resolve_entrant(root, name, index * spacing)
            for index, name in enumerate(args.agents)
        )
        # RC1 default-Ruleset-defect fix, made Agent-API-aware: resolve an
        # omitted --ruleset from the resolved roster's own compatibility
        # metadata -- runtime kind *and*, for a Python entrant, the Agent
        # API version its manifest declares -- mirroring `bytefray run`'s
        # own resolution. An explicit --ruleset is returned unchanged.
        resolved_ruleset_id = resolve_omitted_ruleset_for_agents(
            args.ruleset,
            [
                {
                    "agent_id": entrant.agent_id,
                    "kind": entrant.kind,
                    "api_version": getattr(entrant.python_spec, "api_version", None),
                }
                for entrant in entrants
            ],
        )
        output = (
            args.output.expanduser().resolve()
            if args.output is not None
            else _default_output(root, args.agents, args.seed).resolve()
        )
        result = TournamentService().run(
            TournamentRequest(
                entrants=entrants,
                config=Config(
                    arena_size=args.arena,
                    instr_per_tick=args.quota,
                    seed=args.seed,
                    win_mode=args.win_mode,
                    weights=Weights(
                        alive=args.alive_w,
                        kill=args.kill_w,
                        territory=args.territory_w,
                        territory_bucket=args.territory_bucket,
                    ),
                ),
                rounds=args.rounds,
                max_ticks=args.ticks,
                output_dir=output,
                seed=args.seed,
                retry_failures=args.retry_failed,
                verbose=False,
                ruleset_id=resolved_ruleset_id,
            )
        )
    except (AgentValidationError, TournamentConfigurationError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not args.quiet:
        _print_result(result)
    return 1 if any(match.status != "completed" for match in result.matches) else 0
