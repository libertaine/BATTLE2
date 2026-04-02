import sys
import click

# Internal imports - these require running via 'python -m battle_engine.cli'
from .engine import Engine
from .config import Config
from .agents import resolve_agent


def parse_args(argv):
    @click.command()
    @click.option("--arena-size", default=100, help="Size of the battle grid.")
    @click.option("--instr-per-tick", default=10, help="Instructions per engine tick.")
    @click.option("--seed", default=None, type=int, help="Random seed.")
    @click.option("--win-mode", default="last_man", help="Win condition logic.")
    @click.option("--alive-w", default=1.0, type=float, help="Weight for being alive.")
    @click.option("--kill-w", default=10.0, type=float, help="Weight per kill.")
    @click.option(
        "--territory-w", default=2.0, type=float, help="Weight for territory."
    )
    @click.option("--a-type", required=True, help="Agent A identifier or path.")
    @click.option("--b-type", required=True, help="Agent B identifier or path.")
    @click.option("--output", type=click.Path(), help="Path to save JSONL replay.")
    def command(**kwargs):
        return kwargs

    return command.main(args=argv, standalone_mode=False)


def main(argv=None):
    # Pass sys.argv[1:] if no argv provided to ensure CLI interaction works
    args = parse_args(argv if argv is not None else sys.argv[1:])
    if not args:
        return 1

    weights = {
        "alive": args.get("alive_w"),
        "kill": args.get("kill_w"),
        "territory": args.get("territory_w"),
    }

    try:
        config = Config(
            arena_size=args.get("arena_size"),
            instr_per_tick=args.get("instr_per_tick"),
            seed=args.get("seed"),
            win_mode=args.get("win_mode"),
            weights=weights,
        )
    except TypeError as e:
        click.secho(f"Configuration Error: {e}", fg="red", err=True)
        return 1

    try:
        agent_a = resolve_agent(args.get("a_type"))
        agent_b = resolve_agent(args.get("b_type"))
    except Exception as e:
        click.secho(f"Agent Error: {e}", fg="red", err=True)
        return 1

    engine = Engine(config=config, agent_a=agent_a, agent_b=agent_b)
    click.echo(f"Engine initialized with seed: {config.seed}")

    # Cleaned up unused 'results' variable
    engine.run()

    if args.get("output"):
        engine.save_replay(args.get("output"))
        click.echo(f"Replay saved to {args.get('output')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
