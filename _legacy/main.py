# main.py — Milestone-6: blob support + config overrides + extra agent knobs
import argparse, json, os, sys
from core import Kernel, Config, JSONLSink
from agents import build_agent, SUPPORTED
from renderers import PygameRenderer


def parse_args():
    p = argparse.ArgumentParser(prog="BATTLE")
    p.add_argument("--config", "-c", default="")
    p.add_argument("--ticks", type=int, default=3000)
    p.add_argument("--replay", default="replay.jsonl")
    p.add_argument("--pygame", action="store_true", help="enable Pygame visualization")

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

    # agent types (used only if no blob provided)
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

    # NEW extra knobs (5 flags)
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

    # raw blob paths (override type/params for that agent)
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
    if not os.path.exists(path):
        print(f"ERROR: blob not found: {path}", file=sys.stderr)
        sys.exit(2)
    with open(path, "rb") as f:
        return f.read()


if __name__ == "__main__":
    args = parse_args()
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

    # decide effective byte value (allow --attack-byte to override --byte)
    eff_byte = args.attack_byte if args.attack_byte is not None else args.byte

    sink = JSONLSink(args.replay)
    renderer = PygameRenderer() if args.pygame else None
    k = Kernel(cfg, sink=sink, renderer=renderer)

    # common kwargs for built-in assemblers (passed through to agents.build_agent)
    common_kwargs = {
        "offset": args.offset,
        "byte": eff_byte,
        "stride": args.stride,
        "ptr": args.ptr,
        "writes": args.writes,
        "step": args.step,
        "delta": args.delta,
        "target": args.target,
    }

    # Agent A
    if args.a_blob:
        codeA = read_blob(args.a_blob)
    else:
        codeA = build_agent(args.a_type, args.a_start, **common_kwargs)
    k.spawn("A", args.a_start % cfg.arena_size, codeA)

    # Agent B
    if args.b_blob:
        codeB = read_blob(args.b_blob)
    else:
        # nudge default pointer for variety between agents
        kwargsB = dict(common_kwargs)
        if kwargsB.get("ptr") is not None:
            kwargsB["ptr"] = (kwargsB["ptr"] + 128) % cfg.arena_size
        codeB = build_agent(args.b_type, args.b_start, **kwargsB)
    k.spawn("B", args.b_start % cfg.arena_size, codeB)

    # Agent C (optional)
    if args.c_blob or args.c_type:
        if args.c_blob:
            codeC = read_blob(args.c_blob)
        else:
            kwargsC = dict(common_kwargs)
            if kwargsC.get("ptr") is not None:
                kwargsC["ptr"] = (kwargsC["ptr"] + 256) % cfg.arena_size
            codeC = build_agent(args.c_type, args.c_start, **kwargsC)
        k.spawn("C", args.c_start % cfg.arena_size, codeC)

    winner = k.run(max_ticks=args.ticks, verbose=not args.quiet)
    print(f"Winner: {winner or 'tie'}; replay: {args.replay}")
