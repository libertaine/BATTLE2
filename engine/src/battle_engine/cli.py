import argparse
import json
import os
import sys
from pathlib import Path

from battle_engine.core import Kernel, Config, JSONLSink
from battle_engine.builtins import build_agent, SUPPORTED


def parse_args():
    p = argparse.ArgumentParser(
        prog="BATTLE",
        description=(
            "Deterministic BATTLE engine. Produces replay.jsonl and a summary.json.\n"
            "Agents may be specified via CLI flags or BATTLE_AGENTS_JSON (preferred).\n"
            "Rendering has moved to the client; this CLI is headless."
        ),
    )
    p.add_argument("--config", "-c", default="")
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

    # agent types (used only if no blob provided and no agents.json provided)
    p.add_argument("--a-type", default="writer", choices=SUPPORTED)
    p.add_argument("--b-type", default="runner", choices=SUPPORTED)
    p.add_argument("--c-type", default="", choices=SUPPORTED + ("",))

    # spawn starts
    p.add_argument("--a-start", type=int, default=128)
    p.add_argument("--b-start", type=int, default=2048)
    p.add_argument("--c-start", type=int, default=3072)

    # common agent params (built-in assemblers)
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

    # extra knobs
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

    # raw blob paths (override type/params for that agent) — used if no agents.json
    p.add_argument("--a-blob")
    p.add_argument("--b-blob")
    p.add_argument("--c-blob")

    p.add_argument("--quiet", action="store_true")
    return p.parse_args()


def load_config(path: str) -> Config:
    if not path or not os.path.exists(path):
        return Config()
    with open(path, "r") as f:
        return Config.from_dict(json.load(f))


def read_blob(path: str) -> bytes:
    # Support resolving blob path relative to the agents.json location later if needed:
    if not os.path.exists(path):
        print(f"ERROR: blob not found: {path}", file=sys.stderr)
        sys.exit(2)
    with open(path, "rb") as f:
        return f.read()


def _load_agents_spec_from_env():
    """Return (spec_dict, base_dir) if BATTLE_AGENTS_JSON is set; else ({}, None)."""
    p = os.environ.get("BATTLE_AGENTS_JSON")
    if not p:
        return {}, None
    with open(p, "r") as f:
        spec = json.load(f)
    base = Path(p).parent
    return spec, base


def _resolve_agent(letter: str, spec: dict, spec_dir: Path | None, args, cfg, common_kwargs):
    """
    Resolve an agent for slot letter ('A'/'B'/'C') returning (code_bytes, agent_name, start_pos).
    Precedence:
      1) spec[letter] from agents.json via env
      2) --{letter}-blob
      3) --{letter}-type with builtins
    """
    # defaults
    start = getattr(args, f"{letter.lower()}_start")
    # 1) agents.json
    if spec and letter in spec:
        s = spec[letter]
        t = s.get("type")
        if t == "blob":
            path = s["path"]
            if spec_dir is not None and not os.path.isabs(path):
                path = str((spec_dir / path).resolve())
            code = read_blob(path)
            name = s.get("name") or f"{letter}_blob"
            # entry/header are metadata; VM/dispatcher should already handle ABI if needed
            return code, name, start
        elif t == "builtin":
            agent_id = s["id"]
            code = build_agent(agent_id, start, **common_kwargs)
            return code, agent_id, start
        else:
            print(f"ERROR: unknown agent type for {letter}: {t}", file=sys.stderr)
            sys.exit(2)

    # 2) direct blob flag
    blob = getattr(args, f"{letter.lower()}_blob")
    if blob:
        code = read_blob(blob)
        return code, f"{letter}_blob", start

    # 3) builtin type flag
    agent_type = getattr(args, f"{letter.lower()}_type")
    if not agent_type:
        # empty string for C means "not used"
        return None, "", start
    code = build_agent(agent_type, start, **common_kwargs)
    return code, agent_type, start


if __name__ == "__main__":
    args = parse_args()
    if args.pygame:
        print("warn: --pygame is ignored here; use the client to render replays", file=sys.stderr)

    cfg = load_config(args.config)

    # apply overrides
    if args.seed is not None:
        cfg.seed = args.seed
    if args.arena is not None:
        cfg.arena_size = args.arena
    if args.quota is not None:
        cfg.instr_per_tick = args.quota
    if args.alive_w is not None:
        cfg.weights.alive = args.alive_w
    if args.kill_w is not None:
        cfg.weights.kill = args.kill_w
    if args.territory_w is not None:
        cfg.weights.territory = args.territory_w
    if args.territory_bucket is not None:
        cfg.weights.territory_bucket = args.territory_bucket
    if args.win_mode is not None:
        cfg.win_mode = args.win_mode

    # effective general byte
    eff_byte = args.attack_byte if args.attack_byte is not None else args.byte

    # replay sink
    replay_path = Path(args.replay)
    replay_path.parent.mkdir(parents=True, exist_ok=True)
    sink = JSONLSink(str(replay_path))

    # renderer removed from engine (headless)
    k = Kernel(cfg, sink=sink, renderer=None)

    # common kwargs for built-in assemblers
    common_kwargs = {
        "offset": args.offset,
        "byte": eff_byte,
        "stride": args.stride,
        "ptr": args.ptr,
        "writes": args.writes,
        "step": args.step,
        "delta": args.delta,
        "target": args.target,   # may be None
    }
    # NEW: drop None-valued keys so registry defaults apply
    common_kwargs = {k: v for k, v in common_kwargs.items() if v is not None}

    # Resolve agents via env spec or CLI
    spec, spec_dir = _load_agents_spec_from_env()

    codeA, nameA, startA = _resolve_agent("A", spec, spec_dir, args, cfg, common_kwargs)
    codeB, nameB, startB = _resolve_agent("B", spec, spec_dir, args, cfg, common_kwargs)
    codeC, nameC, startC = _resolve_agent("C", spec, spec_dir, args, cfg, common_kwargs)

    # Spawn required agents
    if codeA is None or codeB is None:
        print("ERROR: agents A and B must be specified (builtin or blob)", file=sys.stderr)
        sys.exit(2)

    k.spawn("A", startA % cfg.arena_size, codeA)
    k.spawn("B", startB % cfg.arena_size, codeB)
    if codeC is not None and nameC:
        k.spawn("C", startC % cfg.arena_size, codeC)

    winner = k.run(max_ticks=args.ticks, verbose=not args.quiet)

    # Write summary.json next to replay
    summary_path = replay_path.with_name("summary.json")
    params = {
        "arena": cfg.arena_size,
        "ticks": args.ticks,
        "win_mode": getattr(cfg, "win_mode", None),
        "territory_w": getattr(cfg.weights, "territory", None),
        "territory_bucket": getattr(cfg.weights, "territory_bucket", None),
    }
    # kernel stats are implementation-specific; guard via getattr
    summary = {
        "version": 1,
        "seed": getattr(cfg, "seed", None),
        "ticks": args.ticks,
        "winner": winner or "tie",
        "A_score": getattr(k, "A_score", 0),
        "B_score": getattr(k, "B_score", 0),
        "A_alive_ticks": getattr(k, "A_alive", 0),
        "B_alive_ticks": getattr(k, "B_alive", 0),
        "A_territory": getattr(k, "A_territory", 0),
        "B_territory": getattr(k, "B_territory", 0),
        "params": params,
        "agents": {"A": nameA, "B": nameB, **({"C": nameC} if nameC else {})},
    }
    summary_path.write_text(json.dumps(summary, indent=2))

    if not args.quiet:
        print(f"Winner: {winner or 'tie'}; replay: {replay_path}; summary: {summary_path}")

