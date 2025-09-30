import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple, Optional

from battle_engine.core import Kernel, Config, JSONLSink
from battle_engine.builtins import build_agent, SUPPORTED

# New: dynamic agents helper (stdlib only)
from .agents import AgentSpec, discover_agents, resolve_agent


# ----------------------------
# Helpers
# ----------------------------


def _final_from_replay(replay_path: Path) -> dict[str, int]:
    """Return dict with final A_score, B_score, A_alive_ticks, B_alive_ticks if present."""
    A_last = B_last = None
    A_alive = B_alive = 0
    seen_ticks = set()

    with replay_path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if not isinstance(ev, dict):
                continue

            # scores (last wins)
            sc = ev.get("score")
            if isinstance(sc, dict):
                if isinstance(sc.get("A"), int):
                    A_last = sc["A"]
                if isinstance(sc.get("B"), int):
                    B_last = sc["B"]

            # alive ticks (count per tick if agent listed as alive)
            tick = ev.get("tick")
            alive_list = ev.get("alive")
            if isinstance(tick, int) and isinstance(alive_list, list):
                if tick not in seen_ticks:
                    seen_ticks.add(tick)
                    if "A" in alive_list:
                        A_alive += 1
                    if "B" in alive_list:
                        B_alive += 1

    return {
        "A_score": int(A_last or 0),
        "B_score": int(B_last or 0),
        "A_alive_ticks": A_alive,
        "B_alive_ticks": B_alive,
    }


def _battle_root() -> Path:
    env = os.environ.get("BATTLE_ROOT")
    if env:
        return Path(env).expanduser().resolve()

    here = Path(__file__).resolve()
    # .../engine/src/battle_engine/cli.py
    # parents[0]=battle_engine, [1]=src, [2]=engine, [3]=BATTLE2 (repo root)
    cand = None
    try:
        cand = here.parents[3]
    except IndexError:
        cand = None

    def valid(p: Path) -> bool:
        return (p / "engine").is_dir() and (p / "agents").is_dir()

    if cand and valid(cand):
        return cand

    # Fallback: walk up to find a directory that has engine/ and agents/
    p = here
    for _ in range(8):
        if valid(p):
            return p
        p = p.parent

    # Last resort: current working directory
    return Path.cwd()


def _parse_env_json(varname: str) -> Dict[str, Any]:
    """
    Read JSON object from environment variable. Return {} on empty/missing.
    Produce a helpful error on malformed input.
    """
    raw = os.environ.get(varname, "").strip()
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
    except Exception as e:
        raise SystemExit(f"Malformed JSON in ${varname}: {e}\nValue: {raw[:200]}...")
    if not isinstance(obj, dict):
        raise SystemExit(
            f"${varname} must be a JSON object (got {type(obj).__name__})."
        )
    return obj


def _merge_params(
    defaults: Dict[str, Any], overrides: Dict[str, Any]
) -> Dict[str, Any]:
    """Shallow merge: overrides win on conflicting keys."""
    merged = dict(defaults or {})
    merged.update(overrides or {})
    return merged


def _keys_preview(d: Dict[str, Any]) -> str:
    """For concise logging: show only top-level param keys."""
    return "{" + ", ".join(sorted(map(str, (d or {}).keys()))) + "}"


def read_blob(path: str | os.PathLike[str]) -> bytes:
    """Load raw bytes for model blobs."""
    p = Path(path).expanduser().resolve()
    return p.read_bytes()


def _load_agents_spec_from_env() -> Tuple[Dict[str, Any], Optional[Path]]:
    """
    Back-compat: load a JSON 'agents spec' from env:BATTLE_AGENTS_JSON.
    Optional keys:
      {
        "A": {"type": "blob", "path": "agents/replicator/model.blob", "name": "replicator"},
        "B": {"type": "builtin", "id": "runner"}
      }
    Returns (spec_dict, base_dir_for_relative_paths).
    """
    raw = os.environ.get("BATTLE_AGENTS_JSON", "").strip()
    if not raw:
        return {}, None
    try:
        spec = json.loads(raw)
    except Exception as e:
        raise SystemExit(f"Malformed JSON in $BATTLE_AGENTS_JSON: {e}")
    if not isinstance(spec, dict):
        raise SystemExit("$BATTLE_AGENTS_JSON must be a JSON object.")
    # If the caller also set BATTLE_AGENTS_DIR, use it for resolving relative paths
    base = os.environ.get("BATTLE_AGENTS_DIR", "").strip()
    base_dir = Path(base).expanduser().resolve() if base else _battle_root()
    return spec, base_dir


# ----------------------------
# CLI
# ----------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="BATTLE",
        description=(
            "Battle engine CLI. Choose built-ins or point to discovered agents under <root>/agents/<name>/."
        ),
    )

    # Run/replay basics
    p.add_argument("--ticks", type=int, default=3000)
    p.add_argument("--replay", default="replay.jsonl")

    # kept for backward-compat, but ignored (no client import here)
    p.add_argument(
        "--pygame",
        action="store_true",
        help="(deprecated/no-op) rendering moved to the client; use battle-client",
    )

    # config overrides
    p.add_argument("--seed", type=int)
    p.add_argument("--arena", type=int)
    p.add_argument("--quota", type=int)
    p.add_argument("--alive-w", type=int)
    p.add_argument("--kill-w", type=int)
    p.add_argument("--territory-w", type=int, help="points per territory bucket")
    p.add_argument(
        "--territory-bucket", type=int, help="cells per bucket for territory scoring"
    )
    p.add_argument(
        "--win-mode",
        choices=["survival", "score", "score_fallback"],
        help="winner resolution mode at timeout",
    )

    # agent types (used if no blob provided and no BATTLE_AGENTS_JSON provided)
    # NOTE: choices removed; any string is accepted and resolved via discovery or built-ins
    p.add_argument(
        "--a-type",
        type=str,
        default="writer",
        help="Agent name for side A (folder under <root>/agents/> or builtin)",
    )
    p.add_argument(
        "--b-type",
        type=str,
        default="runner",
        help="Agent name for side B (folder under <root>/agents/> or builtin)",
    )
    p.add_argument(
        "--c-type",
        type=str,
        default="",
        help="Optional agent name for side C (folder under <root>/agents/> or builtin)",
    )

    # raw blob paths (override type/params for that agent) — used if no agents.json
    p.add_argument("--a-blob")
    p.add_argument("--b-blob")
    p.add_argument("--c-blob")

    # Optional: list discovered agents and exit
    p.add_argument(
        "--list-agents",
        action="store_true",
        help="List discovered agents under <root>/agents and exit",
    )

    # agent entry positions (default 0 unless overridden)
    p.add_argument("--a-start", type=int, default=0)
    p.add_argument("--b-start", type=int, default=0)
    p.add_argument("--c-start", type=int, default=0)

    # common agent params (used by built-in assemblers)
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
    p.add_argument("--step", type=int, help="spiral: initial stride step")
    p.add_argument("--delta", type=int, help="spiral: stride delta per loop")
    p.add_argument(
        "--target", type=lambda x: int(x, 0), help="seeker: target byte to find"
    )
    p.add_argument(
        "--attack-byte",
        type=lambda x: int(x, 0),
        help="optional alias for --byte (overrides it if provided)",
    )

    # quiet mode
    p.add_argument("--quiet", action="store_true")

    return p.parse_args()


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
) -> Tuple[Optional[bytes], str, int]:
    """
    Resolve an agent for slot letter ('A'/'B'/'C') returning (code_bytes, agent_name, start_pos).

    Precedence:
      1) spec[letter] from agents.json via env (BATTLE_AGENTS_JSON)   [back-compat]
      2) --{letter}-blob
      3) agents/<name> discovery with optional per-side env JSON (BATTLE_AGENT_{A|B|C}_PARAMS_JSON)
      4) built-in by name (if name matches SUPPORTED)
    """
    start = getattr(args, f"{letter.lower()}_start")

    # 1) agents.json
    if spec and letter in spec:
        s = spec[letter]
        ttype = s.get("type")
        if ttype == "blob":
            path = s["path"]
            if spec_dir is not None and not os.path.isabs(path):
                path = str((spec_dir / path).resolve())
            code = read_blob(path)
            name = s.get("name") or f"{letter}_blob"
            return code, name, start
        elif ttype == "builtin":
            agent_id = s["id"]
            code = build_agent(agent_id, start, **common_kwargs)
            return code, agent_id, start
        else:
            print(f"ERROR: unknown agent type for {letter}: {ttype}", file=sys.stderr)
            sys.exit(2)

    # 2) direct blob flag
    blob = getattr(args, f"{letter.lower()}_blob")
    if blob:
        code = read_blob(blob)
        return code, f"{letter}_blob", start

    # 3) discovery
    agent_name = getattr(args, f"{letter.lower()}_type")
    if not agent_name:
        return None, "", start

    root = _battle_root()
    spec_obj = None
    try:
        spec_obj = resolve_agent(root, agent_name)
    except SystemExit:
        spec_obj = None  # allow fallback

    if spec_obj is not None:
        side_env = _parse_env_json(f"BATTLE_AGENT_{letter}_PARAMS_JSON")
        merged = _merge_params(spec_obj.defaults, side_env)

        blob_path: Optional[Path] = None
        env_blob = side_env.get("blob_path")
        if isinstance(env_blob, str) and env_blob:
            pth = Path(env_blob).expanduser()
            blob_path = (
                (root / pth).resolve() if not pth.is_absolute() else pth.resolve()
            )
        else:
            blob_path = spec_obj.blob

        if not (spec_obj.dir / "agent.py").exists():
            if blob_path is None or not blob_path.exists():
                raise SystemExit(
                    f"No blob specified for agent '{agent_name}'. "
                    f"Provide model.blob in agents/{agent_name}/ or pass via env JSON key 'blob_path' "
                    f"in $BATTLE_AGENT_{letter}_PARAMS_JSON or use --{letter.lower()}-blob."
                )

        if blob_path is not None and blob_path.exists():
            code = read_blob(str(blob_path))
            return code, agent_name, start

    # 4) fall back to built-in
    if agent_name in SUPPORTED:
        code = build_agent(agent_name, start, **common_kwargs)
        return code, agent_name, start

    print(
        f"ERROR: Unknown agent '{agent_name}'. "
        f"Expected a built-in ({', '.join(SUPPORTED)}) or a folder {root/'agents'/agent_name} with agent.yaml (JSON) or agent.py",
        file=sys.stderr,
    )
    sys.exit(2)


# ----------------------------
# Main
# ----------------------------
def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args()

    # Optional listing mode
    if getattr(args, "list_agents", False):
        root = _battle_root()
        specs = discover_agents(root)
        if not specs:
            print(f"No agents found under {root / 'agents'}")
            return 0
        print("Discovered agents:")
        for name, spec in sorted(specs.items()):
            disp = f"{spec.display}" if spec.display and spec.display != name else ""
            blob = spec.blob.name if spec.blob else "—"
            print(f"  - {name:20} {disp:20} blob={blob}")
        return 0

    # config
    cfg_kwargs: Dict[str, Any] = {}
    if args.seed is not None:
        cfg_kwargs["seed"] = args.seed
    if args.arena is not None:
        cfg_kwargs["arena_size"] = args.arena
    if args.quota is not None:
        cfg_kwargs["quota"] = args.quota
    if args.win_mode:
        cfg_kwargs["win_mode"] = args.win_mode
    if args.alive_w is not None:
        cfg_kwargs["alive_w"] = args.alive_w
    if args.kill_w is not None:
        cfg_kwargs["kill_w"] = args.kill_w
    if args.territory_w is not None:
        cfg_kwargs["territory_w"] = args.territory_w
    if args.territory_bucket is not None:
        cfg_kwargs["territory_bucket"] = args.territory_bucket

    cfg = Config(**cfg_kwargs)

    # replay / summary paths
    replay_path = Path(args.replay).expanduser().resolve()
    replay_path.parent.mkdir(parents=True, exist_ok=True)
    sink = JSONLSink(str(replay_path))

    # kernel
    k = Kernel(cfg, sink)

    # attack-byte is an alias for byte (if provided)
    byte = args.byte
    if args.attack_byte is not None:
        byte = args.attack_byte

    # Common knobs for built-in codegen (omit None so registry defaults apply)
    common_kwargs = {
        "byte": byte,
        "offset": args.offset,
        "stride": args.stride,
        "ptr": args.ptr,
        "writes": args.writes,
        "step": args.step,
        "delta": args.delta,
        "target": args.target,  # may be None
    }
    common_kwargs = {k: v for k, v in common_kwargs.items() if v is not None}

    # Resolve agents via env spec or CLI
    spec, spec_dir = _load_agents_spec_from_env()
    codeA, nameA, startA = _resolve_agent("A", spec, spec_dir, args, cfg, common_kwargs)
    codeB, nameB, startB = _resolve_agent("B", spec, spec_dir, args, cfg, common_kwargs)
    codeC, nameC, startC = _resolve_agent("C", spec, spec_dir, args, cfg, common_kwargs)

    # Concise startup summary (keys only; best-effort)
    try:
        root = _battle_root()
        a_env = _parse_env_json("BATTLE_AGENT_A_PARAMS_JSON")
        b_env = _parse_env_json("BATTLE_AGENT_B_PARAMS_JSON")
        c_env = _parse_env_json("BATTLE_AGENT_C_PARAMS_JSON")

        def _try_resolve(name: str | None):
            if not name:
                return None
            try:
                return resolve_agent(root, name)
            except SystemExit:
                return None

        a_spec = _try_resolve(args.a_type)
        b_spec = _try_resolve(args.b_type)
        c_spec = _try_resolve(args.c_type)

        def keys(d):
            return _keys_preview(d or {})

        print("Agents:")
        print(
            f"  A: {nameA}  params={keys((a_spec.defaults if a_spec else {}) | (a_env or {}))}"
        )
        print(
            f"  B: {nameB}  params={keys((b_spec.defaults if b_spec else {}) | (b_env or {}))}"
        )
        if nameC:
            print(
                f"  C: {nameC}  params={keys((c_spec.defaults if c_spec else {}) | (c_env or {}))}"
            )
    except Exception:
        pass

    # Spawn required agents
    if codeA is None or codeB is None:
        print(
            "ERROR: agents A and B must be specified (builtin or blob)", file=sys.stderr
        )
        return 2

    k.spawn("A", startA % cfg.arena_size, codeA)
    k.spawn("B", startB % cfg.arena_size, codeB)
    if codeC is not None and nameC:
        k.spawn("C", startC % cfg.arena_size, codeC)

    winner = k.run(max_ticks=args.ticks, verbose=not args.quiet)

    # After: winner = k.run(max_ticks=args.ticks, verbose=not args.quiet)

    # Prefer replay-derived numbers (Kernel attrs may not reflect log state)
    finals = _final_from_replay(replay_path)

    # If win-mode is score and kernel returned None but scores differ, decide here
    effective_winner = winner
    if not effective_winner and args.win_mode in (None, "score", "score_fallback"):
        if finals["A_score"] > finals["B_score"]:
            effective_winner = "A"
        elif finals["B_score"] > finals["A_score"]:
            effective_winner = "B"

    summary_path = replay_path.with_name("summary.json")
    params = {
        "arena": cfg.arena_size,
        "ticks": args.ticks,
        "win_mode": cfg.win_mode,
        "territory_w": getattr(cfg, "territory_w", None),
        "territory_bucket": getattr(cfg, "territory_bucket", None),
    }
    summary = {
        "version": 1,
        "seed": getattr(cfg, "seed", None),
        "ticks": args.ticks,
        "winner": effective_winner or "tie",
        "A_score": finals["A_score"],
        "B_score": finals["B_score"],
        "A_alive_ticks": finals["A_alive_ticks"],
        "B_alive_ticks": finals["B_alive_ticks"],
        "A_territory": getattr(
            k, "A_territory", 0
        ),  # keep if kernel provides it; else 0
        "B_territory": getattr(k, "B_territory", 0),
        "params": params,
        "agents": {"A": nameA, "B": nameB, **({"C": nameC} if nameC else {})},
    }
    summary_path.write_text(json.dumps(summary, indent=2))

    if not args.quiet:
        print(
            f"Winner: {winner or 'tie'}; replay: {replay_path}; summary: {summary_path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
