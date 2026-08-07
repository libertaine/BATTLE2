import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

from battle_engine.agent_api import AgentValidationError
from battle_engine.agents import discover_agents, resolve_agent
from battle_engine.builtins import SUPPORTED, build_agent
from battle_engine.core import Config, Weights
from battle_engine.match_service import (
    MatchEntrant,
    MatchRequest,
    NativeMatchService,
    PythonMatchExecutionError,
    UnsupportedMatchCompositionError,
)
from battle_engine.paths import get_data_root
from battle_engine.pmars import PMarsError, run_pmars
from battle_engine.result_model import ResultEnvelope, stable_id, write_json_atomic
from battle_engine.python_runtime import PythonEntrantInitializationError
from battle_engine.starters import ensure_starter_agents

DEFAULT_REPLAY_RELATIVE_PATH = Path("runs") / "_loose" / "replay.jsonl"

# ----------------------------
# Helpers
# ----------------------------


def _pmars_arguments(
    red_a: Path,
    red_b: Path,
    *,
    core_size: int,
    max_cycles: int,
    max_processes: int,
    max_len: int,
    min_dist: int,
    rounds: int,
) -> list[str]:
    """Build pMARS arguments without resolving or invoking the executable."""
    return [
        "-b",
        "-r",
        str(rounds),
        "-s",
        str(core_size),
        "-c",
        str(max_cycles),
        "-p",
        str(max_processes),
        "-l",
        str(max_len),
        "-d",
        str(min_dist),
        str(red_a),
        str(red_b),
    ]



def _battle_root() -> Path:
    """Compatibility wrapper for the shared writable data-root resolver."""
    return get_data_root()


def _resolve_replay_path(value: str | None) -> Path:
    """Resolve the default under the data root or an explicit path from the CWD."""
    if value is None:
        return (_battle_root() / DEFAULT_REPLAY_RELATIVE_PATH).resolve()
    return Path(value).expanduser().resolve()


def _parse_env_json(varname: str) -> Dict[str, Any]:
    """
    Read JSON object from environment variable.
    Return {} on empty/missing.
    """
    raw = os.environ.get(varname, "").strip()
    if not raw:
        return {}

    try:
        obj = json.loads(raw)
    except Exception as exc:
        raise SystemExit(f"Malformed JSON in ${varname}: {exc}\nValue: {raw[:200]}...")

    if not isinstance(obj, dict):
        raise SystemExit(
            f"${varname} must be a JSON object (got {type(obj).__name__})."
        )

    return obj


def _merge_params(
    defaults: Dict[str, Any], overrides: Dict[str, Any]
) -> Dict[str, Any]:
    merged = dict(defaults or {})
    merged.update(overrides or {})
    return merged


def _keys_preview(d: Dict[str, Any]) -> str:
    return "{" + ", ".join(sorted(map(str, (d or {}).keys()))) + "}"


def read_blob(path: str | os.PathLike[str]) -> bytes:
    p = Path(path).expanduser().resolve()
    return p.read_bytes()


def _load_agents_spec_from_env() -> Tuple[Dict[str, Any], Optional[Path]]:
    """
    Back-compat:
      BATTLE_AGENTS_JSON='{"A":{"type":"blob","path":"agents/x/model.blob"}}'
    """
    raw = os.environ.get("BATTLE_AGENTS_JSON", "").strip()
    if not raw:
        return {}, None

    try:
        spec = json.loads(raw)
    except Exception as exc:
        raise SystemExit(f"Malformed JSON in $BATTLE_AGENTS_JSON: {exc}")

    if not isinstance(spec, dict):
        raise SystemExit("$BATTLE_AGENTS_JSON must be a JSON object.")

    base = os.environ.get("BATTLE_AGENTS_DIR", "").strip()
    base_dir = Path(base).expanduser().resolve() if base else _battle_root()
    return spec, base_dir


# ----------------------------
# CLI
# ----------------------------


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="BATTLE",
        description=(
            "Battle engine CLI. Choose built-ins or point to discovered agents "
            "under /agents/<name>/."
        ),
    )

    # Run/replay basics
    p.add_argument("--ticks", type=int, default=3000)
    p.add_argument(
        "--replay",
        default=None,
        help=(
            "replay output path; explicit relative paths use the current working "
            "directory (default: <data-root>/runs/_loose/replay.jsonl)"
        ),
    )
    p.add_argument(
        "--pygame",
        action="store_true",
        help="(deprecated/no-op) rendering moved to the client; use battle-client",
    )

    # Config overrides
    p.add_argument("--seed", type=int)
    p.add_argument("--arena", type=int)
    p.add_argument("--quota", type=_positive_int, help="instructions per agent per tick")
    p.add_argument("--alive-w", type=float)
    p.add_argument("--kill-w", type=float)
    p.add_argument("--territory-w", type=float, help="points per territory bucket")
    p.add_argument(
        "--territory-bucket",
        type=int,
        help="cells per bucket for territory scoring",
    )
    p.add_argument(
        "--win-mode",
        choices=["survival", "score", "score_fallback"],
        help="winner resolution mode at timeout",
    )

    # Agent selection
    p.add_argument(
        "--a-type",
        type=str,
        default="writer",
        help="Agent name for side A (folder under /agents/<name> or builtin)",
    )
    p.add_argument(
        "--b-type",
        type=str,
        default="runner",
        help="Agent name for side B (folder under /agents/<name> or builtin)",
    )
    p.add_argument(
        "--c-type",
        type=str,
        default="",
        help="Optional agent name for side C (folder under /agents/<name> or builtin)",
    )

    # Direct blob overrides
    p.add_argument("--a-blob")
    p.add_argument("--b-blob")
    p.add_argument("--c-blob")

    p.add_argument(
        "--list-agents",
        action="store_true",
        help="List discovered agents under /agents and exit",
    )

    # Entry positions
    p.add_argument("--a-start", type=int, default=0)
    p.add_argument("--b-start", type=int, default=0)
    p.add_argument("--c-start", type=int, default=0)

    # Common agent params
    p.add_argument(
        "--byte",
        type=lambda x: int(x, 0),
        default="0x99",
        help="general byte value used by agents",
    )
    p.add_argument("--offset", type=int, default=128, help="writer offset from entry")
    p.add_argument("--stride", type=int, default=64, help="bomber/seeker stride")
    p.add_argument(
        "--ptr", type=int, default=512, help="initial pointer for pointer-based agents"
    )
    p.add_argument("--writes", type=int, help="flooder: writes per loop")
    p.add_argument("--step", type=int, help="spiral: fixed pointer step")
    p.add_argument(
        "--delta",
        type=int,
        help="spiral: A-register delta per loop (does not change pointer step)",
    )
    p.add_argument(
        "--target", type=lambda x: int(x, 0), help="seeker: target byte to find"
    )
    p.add_argument(
        "--attack-byte",
        type=lambda x: int(x, 0),
        help="optional alias for --byte (overrides it if provided)",
    )

    # ICWS'94 / pMARS backend flags
    p.add_argument(
        "--mode",
        choices=["b2", "redcode94"],
        default="b2",
        help="Engine mode: 'b2' for built-in BATTLE agents (default) or 'redcode94' to run pMARS.",
    )
    p.add_argument(
        "--red-a", type=str, help="Warrior A file (.red or .load) for redcode94 mode"
    )
    p.add_argument(
        "--red-b", type=str, help="Warrior B file (.red or .load) for redcode94 mode"
    )
    p.add_argument("--core-size", type=int, default=8000, help="ICWS'94 core size")
    p.add_argument("--max-cycles", type=int, default=80000, help="Max cycles per round")
    p.add_argument(
        "--max-processes", type=int, default=8000, help="Max processes per warrior"
    )
    p.add_argument("--max-len", type=int, default=100, help="Max warrior length")
    p.add_argument(
        "--min-dist",
        type=int,
        default=100,
        help="Minimum initial distance between warriors",
    )
    p.add_argument("--rounds", type=int, default=1, help="Number of rounds to run")

    p.add_argument("--quiet", action="store_true")
    return p.parse_args(argv)


# ----------------------------
# Agent Resolution
# ----------------------------


def _resolve_agent(
    letter: str,
    spec: Dict[str, Any],
    spec_dir: Optional[Path],
    args: argparse.Namespace,
    cfg: Config,
    common_kwargs: Dict[str, Any],
) -> Tuple[Optional[bytes], str, int, Any | None]:
    """
    Resolve an agent for slot A/B/C.

    Precedence:
      1) BATTLE_AGENTS_JSON
      2) --a-blob / --b-blob / --c-blob
      3) discovered agent under /agents
      4) built-in by name
    """
    del cfg  # currently unused here, kept for compatibility
    start = getattr(args, f"{letter.lower()}_start")

    # 1) env agents spec
    if spec and letter in spec:
        s = spec[letter]
        ttype = s.get("type")

        if ttype == "blob":
            path = s["path"]
            if spec_dir is not None and not os.path.isabs(path):
                path = str((spec_dir / path).resolve())
            code = read_blob(path)
            name = s.get("name") or f"{letter}_blob"
            return code, name, start, None

        if ttype == "builtin":
            agent_id = s["id"]
            code = build_agent(agent_id, start, **common_kwargs)
            return code, agent_id, start, None

        print(f"ERROR: unknown agent type for {letter}: {ttype}", file=sys.stderr)
        sys.exit(2)

    # 2) direct blob flag
    blob = getattr(args, f"{letter.lower()}_blob")
    if blob:
        code = read_blob(blob)
        return code, f"{letter}_blob", start, None

    # 3) discovery agent
    agent_name = getattr(args, f"{letter.lower()}_type")
    if not agent_name:
        return None, "", start, None

    root = _battle_root()

    try:
        spec_obj = resolve_agent(root, agent_name)
    except AgentValidationError as exc:
        raise SystemExit(str(exc)) from exc
    except SystemExit:
        spec_obj = None

    if spec_obj is not None:
        side_env = _parse_env_json(f"BATTLE_AGENT_{letter}_PARAMS_JSON")
        _merged = _merge_params(spec_obj.defaults, side_env)

        if spec_obj.kind == "python":
            return None, agent_name, start, spec_obj

        env_blob = side_env.get("blob_path")
        blob_path: Optional[Path]
        if isinstance(env_blob, str) and env_blob:
            blob_path = Path(env_blob).expanduser()
            if not blob_path.is_absolute():
                blob_path = (root / blob_path).resolve()
            else:
                blob_path = blob_path.resolve()
        else:
            blob_path = spec_obj.blob

        # Manifest-only starter agents may intentionally select an existing
        # built-in implementation. Other discovered agents still require code.
        if (
            not (spec_obj.dir / "agent.py").exists()
            and agent_name not in SUPPORTED
            and (blob_path is None or not blob_path.exists())
        ):
            raise SystemExit(
                f"No blob specified for agent '{agent_name}'. "
                f"Provide model.blob in agents/{agent_name}/ or pass via env JSON "
                f"key 'blob_path' in $BATTLE_AGENT_{letter}_PARAMS_JSON or use "
                f"--{letter.lower()}-blob."
            )

        if blob_path is not None and blob_path.exists():
            code = read_blob(str(blob_path))
            return code, agent_name, start, None

    # 4) built-in fallback
    if agent_name in SUPPORTED:
        code = build_agent(agent_name, start, **common_kwargs)
        return code, agent_name, start, None

    print(
        f"ERROR: Unknown agent '{agent_name}'. "
        f"Expected a built-in ({', '.join(SUPPORTED)}) or a folder "
        f"{root / 'agents' / agent_name} with agent.yaml (JSON) or agent.py",
        file=sys.stderr,
    )
    sys.exit(2)


# ----------------------------
# Main
# ----------------------------


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)

    if getattr(args, "list_agents", False):
        root = _battle_root()
        try:
            ensure_starter_agents(data_root=root)
        except (FileNotFoundError, OSError, ValueError) as exc:
            print(f"ERROR: Could not initialize starter agents: {exc}", file=sys.stderr)
            return 2
        try:
            specs = discover_agents(root)
        except AgentValidationError as exc:
            print(f"ERROR: Could not discover agents: {exc}", file=sys.stderr)
            return 2
        if not specs:
            print(f"No agents found under {root / 'agents'}")
            return 0

        print("Discovered agents:")
        for name, spec in sorted(specs.items()):
            disp = f"{spec.display}" if spec.display and spec.display != name else ""
            blob = spec.blob.name if spec.blob else "—"
            print(f" - {name:20} {disp:20} blob={blob}")
        return 0

    # Build current Config correctly against Config.weights
    cfg_kwargs: Dict[str, Any] = {}
    if args.seed is not None:
        cfg_kwargs["seed"] = args.seed
    if args.arena is not None:
        cfg_kwargs["arena_size"] = args.arena
    if args.win_mode:
        cfg_kwargs["win_mode"] = args.win_mode
    if args.quota is not None:
        cfg_kwargs["instr_per_tick"] = args.quota

    cfg = Config(**cfg_kwargs)

    # Preserve defaults unless caller overrides them.
    cfg.weights = Weights(
        alive=args.alive_w if args.alive_w is not None else cfg.weights.alive,
        kill=args.kill_w if args.kill_w is not None else cfg.weights.kill,
        territory=(
            args.territory_w if args.territory_w is not None else cfg.weights.territory
        ),
        territory_bucket=(
            args.territory_bucket
            if args.territory_bucket is not None
            else cfg.weights.territory_bucket
        ),
    )

    replay_path = _resolve_replay_path(args.replay)
    summary_path = replay_path.with_name("summary.json")

    if args.mode == "redcode94":
        replay_path.parent.mkdir(parents=True, exist_ok=True)
        if not args.red_a or not args.red_b:
            print("redcode94 mode requires --red-a and --red-b", file=sys.stderr)
            return 2

        a_path = Path(args.red_a)
        b_path = Path(args.red_b)

        if not a_path.exists() or not b_path.exists():
            missing = a_path if not a_path.exists() else b_path
            print(f"Warrior file missing: {missing}", file=sys.stderr)
            return 2

        # Redcode mode currently produces a summary but no BATTLE replay.
        # Remove an artifact from an earlier invocation before starting pMARS.
        replay_path.unlink(missing_ok=True)
        summary_path.with_name("result.json").unlink(missing_ok=True)
        try:
            result = run_pmars(
                _pmars_arguments(
                    a_path,
                    b_path,
                    core_size=args.core_size,
                    max_cycles=args.max_cycles,
                    max_processes=args.max_processes,
                    max_len=args.max_len,
                    min_dist=args.min_dist,
                    rounds=args.rounds,
                )
            )
        except PMarsError as exc:
            replay_path.unlink(missing_ok=True)
            summary_path.unlink(missing_ok=True)
            summary_path.with_name("result.json").unlink(missing_ok=True)
            print(f"pMARS error: {exc}", file=sys.stderr)
            return exc.exit_code

        summary = {
            "version": 2,
            "mode": "redcode94",
            "ticks": args.max_cycles,
            "winner": result.winner,
            "A_score": None,
            "B_score": None,
            "A_alive_ticks": None,
            "B_alive_ticks": None,
            "A_territory": None,
            "B_territory": None,
            "params": {
                "core_size": args.core_size,
                "max_cycles": args.max_cycles,
                "max_processes": args.max_processes,
                "max_len": args.max_len,
                "min_dist": args.min_dist,
                "rounds": args.rounds,
            },
            "agents": {"A": str(a_path), "B": str(b_path)},
            "backend": {
                "cmd": list(result.command),
                "returncode": result.returncode,
            },
        }

        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        reproducibility = {
            **summary["params"],
            "entrants": [
                {
                    "agent_id": "A",
                    "source_sha256": hashlib.sha256(a_path.read_bytes()).hexdigest(),
                },
                {
                    "agent_id": "B",
                    "source_sha256": hashlib.sha256(b_path.read_bytes()).hexdigest(),
                },
            ],
        }
        match_id = stable_id("match", {"mode": "redcode94", **reproducibility})
        result_id = stable_id("result", {"match_id": match_id, "winner": result.winner})
        envelope = ResultEnvelope(
            result_id=result_id,
            match_id=match_id,
            mode="redcode94",
            winner=result.winner,
            termination_reason="backend_completed",
            ticks=args.max_cycles,
            entrants=tuple(reproducibility["entrants"]),
            reproducibility=reproducibility,
            replay=None,
            backend={"name": "pMARS", "returncode": result.returncode},
        )
        write_json_atomic(summary_path.with_name("result.json"), envelope.as_dict())

        if not args.quiet:
            print(
                f"Winner: {summary['winner']}; "
                f"result: {summary_path.with_name('result.json')}; "
                f"summary: {summary_path}; replay: none"
            )
        return 0

    byte = args.byte
    if args.attack_byte is not None:
        byte = args.attack_byte

    common_kwargs = {
        "byte": byte,
        "offset": args.offset,
        "stride": args.stride,
        "ptr": args.ptr,
        "writes": args.writes,
        "step": args.step,
        "delta": args.delta,
        "target": args.target,
    }
    common_kwargs = {
        key: value for key, value in common_kwargs.items() if value is not None
    }

    env_spec, spec_dir = _load_agents_spec_from_env()

    codeA, nameA, startA, pythonA = _resolve_agent(
        "A", env_spec, spec_dir, args, cfg, common_kwargs
    )
    codeB, nameB, startB, pythonB = _resolve_agent(
        "B", env_spec, spec_dir, args, cfg, common_kwargs
    )
    codeC, nameC, startC, pythonC = _resolve_agent(
        "C", env_spec, spec_dir, args, cfg, common_kwargs
    )

    try:
        root = _battle_root()
        a_env = _parse_env_json("BATTLE_AGENT_A_PARAMS_JSON")
        b_env = _parse_env_json("BATTLE_AGENT_B_PARAMS_JSON")
        c_env = _parse_env_json("BATTLE_AGENT_C_PARAMS_JSON")

        def _try_resolve(name: Optional[str]):
            if not name:
                return None
            try:
                return resolve_agent(root, name)
            except (SystemExit, AgentValidationError):
                return None

        a_spec = _try_resolve(args.a_type)
        b_spec = _try_resolve(args.b_type)
        c_spec = _try_resolve(args.c_type)

        def keys(d: Dict[str, Any]) -> str:
            return _keys_preview(d or {})

        print("Agents:")
        print(
            f" A: {nameA} params={keys((a_spec.defaults if a_spec else {}) | (a_env or {}))}"
        )
        print(
            f" B: {nameB} params={keys((b_spec.defaults if b_spec else {}) | (b_env or {}))}"
        )
        if nameC:
            print(
                f" C: {nameC} params={keys((c_spec.defaults if c_spec else {}) | (c_env or {}))}"
            )
    except Exception:
        pass

    if (codeA is None and pythonA is None) or (codeB is None and pythonB is None):
        print(
            "ERROR: agents A and B must be executable built-in, blob, or Python agents",
            file=sys.stderr,
        )
        return 2

    # Agent validation above must complete before this owned output is opened;
    # otherwise an invalid invocation could truncate an existing replay.
    entrants = [
        (
            MatchEntrant.python("A", nameA, startA, pythonA)
            if pythonA is not None
            else MatchEntrant("A", nameA, startA, codeA)
        ),
        (
            MatchEntrant.python("B", nameB, startB, pythonB)
            if pythonB is not None
            else MatchEntrant("B", nameB, startB, codeB)
        ),
    ]
    if nameC and (codeC is not None or pythonC is not None):
        entrants.append(
            MatchEntrant.python("C", nameC, startC, pythonC)
            if pythonC is not None
            else MatchEntrant("C", nameC, startC, codeC)
        )
    try:
        match_result = NativeMatchService().run(
            MatchRequest(
                config=cfg,
                entrants=tuple(entrants),
                max_ticks=args.ticks,
                replay_path=replay_path,
                verbose=not args.quiet,
            )
        )
    except (
        UnsupportedMatchCompositionError,
        PythonEntrantInitializationError,
        PythonMatchExecutionError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    agent_stats = {
        agent.agent_id: agent.as_legacy_statistics() for agent in match_result.agents
    }
    score_map = dict(match_result.score)
    effective_winner = match_result.winner

    summary = {
        "version": 2,
        "mode": "b2",
        "seed": getattr(cfg, "seed", None),
        "ticks": match_result.ticks_run,
        "winner": effective_winner,
        "A_score": score_map.get("A", 0),
        "B_score": score_map.get("B", 0),
        "A_alive_ticks": agent_stats.get("A", {}).get("alive_ticks", 0),
        "B_alive_ticks": agent_stats.get("B", {}).get("alive_ticks", 0),
        "A_territory": agent_stats.get("A", {}).get("territory_last", 0),
        "B_territory": agent_stats.get("B", {}).get("territory_last", 0),
        "params": {
            "arena": cfg.arena_size,
            "ticks_requested": args.ticks,
            "ticks_run": match_result.ticks_run,
            "win_mode": cfg.win_mode,
            "alive_w": cfg.weights.alive,
            "kill_w": cfg.weights.kill,
            "territory_w": cfg.weights.territory,
            "territory_bucket": cfg.weights.territory_bucket,
        },
        "agents": {
            "A": nameA,
            "B": nameB,
            **({"C": nameC} if nameC else {}),
        },
        "score": score_map,
        "agent_stats": agent_stats,
    }

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if not args.quiet:
        print(
            f"Winner: {effective_winner}; "
            f"result: {match_result.result_path}; "
            f"replay: {replay_path}; "
            f"summary: {summary_path}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
