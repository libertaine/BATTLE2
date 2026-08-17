"""Repeatable, non-CI scaling benchmarks for Bytefray's v1.4 work.

Run from an installed/editable checkout with::

    python tools/benchmark_platform_scaling.py

The benchmark uses medians, reports its exact workload, and writes nothing
outside an automatically removed temporary directory. Wall-clock results are
environment evidence, not correctness thresholds and not CI pass/fail gates.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

from battle_client.analysis import compute_territory_history
from battle_client.session import ReplaySession
from battle_engine.agent_state import Agent
from battle_engine.agents import resolve_agent
from battle_engine.builtins import build_agent
from battle_engine.config import Config, Weights
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.replay import iter_replay, write_replay
from battle_engine.scoring import ScoringPolicy
from battle_engine.statistics import StatisticsCollector
from battle_engine.vm import VM

PYTHON_WRITER = b"""from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        self.rng = context.rng

    def act(self, observation):
        return AgentAction(ActionKind.WRITE, self.rng.randrange(1 << 30), observation.tick)

def create_agent():
    return Agent()
"""


def _median_ms(operation, repeats: int) -> float:
    samples: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        operation()
        samples.append((time.perf_counter() - started) * 1000.0)
    return statistics.median(samples)


def _territory_tick(arena_size: int, target_cells: int) -> dict[str, Any]:
    vm = VM(arena_size)
    split = arena_size // 2
    for address in range(arena_size):
        vm._wr8(address, address, "A" if address < split else "B")
    vm.clear_tick_diffs()
    agents = [Agent("A", 0, (0, 0)), Agent("B", split, (split, split))]
    collector = StatisticsCollector()
    statistics_map: dict[str, dict[str, int]] = {}
    for agent in agents:
        collector.initialize_agent(statistics_map, agent.agent_id)
    scorer = ScoringPolicy(Weights(territory=1, territory_bucket=64))
    score: dict[str, int | float] = {"A": 0, "B": 0}
    ownership = getattr(vm, "ownership_counts", vm.writer)
    iterations = max(8, target_cells // arena_size)

    def operation() -> None:
        for _ in range(iterations):
            scorer.score_territory(score, agents, ownership)
            collector.record_tick(statistics_map, agents, ownership)

    return {
        "arena_size": arena_size,
        "iterations": iterations,
        "median_ms": _median_ms(operation, 5),
    }


def _python_entrant(root: Path, agent_id: str, slot: int) -> MatchEntrant:
    directory = root / "agents" / agent_id
    directory.mkdir(parents=True)
    manifest = {
        "kind": "python",
        "api_version": 1,
        "entrypoint": "agent.py:create_agent",
        "name": agent_id,
        "display": agent_id.title(),
        "version": "1.0",
    }
    directory.joinpath("agent.yaml").write_bytes(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    directory.joinpath("agent.py").write_bytes(PYTHON_WRITER)
    return MatchEntrant.python(agent_id.upper(), agent_id, slot * 1024, resolve_agent(root, agent_id))


def _match_benchmark(root: Path, arena_size: int, ticks: int, kind: str) -> dict[str, Any]:
    if kind == "vm":
        entrants = (
            MatchEntrant("A", "writer", 0, build_agent("writer", 0, offset=3071)),
            MatchEntrant("B", "seeker", arena_size // 3, build_agent("seeker", arena_size // 3)),
            MatchEntrant("C", "runner", arena_size * 2 // 3, build_agent("runner", arena_size * 2 // 3)),
        )
    else:
        agent_root = root / f"python-agents-{arena_size}"
        entrants = tuple(
            _python_entrant(agent_root, name, slot)
            for slot, name in enumerate(("alpha", "beta", "gamma"))
        )
    sample = 0

    def operation() -> None:
        nonlocal sample
        sample += 1
        replay = root / f"{kind}-{arena_size}-{sample}" / "replay.jsonl"
        NativeMatchService().run(
            MatchRequest(
                Config(arena_size=arena_size, instr_per_tick=4, seed=1337),
                entrants,
                ticks,
                replay,
                False,
            )
        )

    return {
        "kind": kind,
        "entrants": 3,
        "arena_size": arena_size,
        "ticks": ticks,
        "median_ms": _median_ms(operation, 3),
    }


def _replay_benchmark(root: Path, arena_size: int, ticks: int) -> dict[str, Any]:
    replay = root / "replay-scaling" / "replay.jsonl"
    entrants = (
        MatchEntrant("A", "writer", 0, build_agent("writer", 0, offset=arena_size - 17)),
        MatchEntrant("B", "writer", arena_size // 2, build_agent("writer", arena_size // 2, offset=19)),
    )
    NativeMatchService().run(
        MatchRequest(
            Config(arena_size=arena_size, instr_per_tick=4, seed=1337),
            entrants,
            ticks,
            replay,
            False,
        )
    )

    def load() -> None:
        session = ReplaySession()
        session.load(replay)

    session = ReplaySession()
    session.load(replay)
    records = tuple(iter_replay(replay))
    rewrite_sample = 0

    def rewrite() -> None:
        nonlocal rewrite_sample
        rewrite_sample += 1
        write_replay(root / "replay-scaling" / f"rewrite-{rewrite_sample}.jsonl", records)

    final_tick = session.final_tick
    assert final_tick is not None
    targets = (final_tick, final_tick // 4, final_tick * 3 // 4, final_tick // 10, final_tick)

    def seeks() -> None:
        session.restart()
        for target in targets:
            session.seek(target)

    def territory_history() -> None:
        session.restart()
        compute_territory_history(session)

    return {
        "arena_size": arena_size,
        "ticks": final_tick,
        "bytes": replay.stat().st_size,
        "canonical_rewrite_median_ms": _median_ms(rewrite, 3),
        "load_median_ms": _median_ms(load, 5),
        "mixed_seek_median_ms": _median_ms(seeks, 5),
        "territory_history_median_ms": _median_ms(territory_history, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="Use shorter match/replay workloads.")
    args = parser.parse_args()
    target_cells = 4_194_304 if args.quick else 16_777_216
    match_ticks = 80 if args.quick else 300
    replay_ticks = 500 if args.quick else 3000
    report: dict[str, Any] = {
        "environment": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "python": platform.python_version(),
        },
        "workload": {
            "territory_target_cells": target_cells,
            "match_ticks": match_ticks,
            "replay_ticks": replay_ticks,
        },
    }
    with tempfile.TemporaryDirectory(prefix="bytefray-scaling-") as temporary:
        root = Path(temporary)
        report["territory_tick"] = [
            _territory_tick(size, target_cells) for size in (4096, 16384, 65536, 262144)
        ]
        report["matches"] = [
            _match_benchmark(root, size, match_ticks, kind)
            for kind in ("vm", "python")
            for size in (4096, 65536)
        ]
        report["replay"] = _replay_benchmark(root, 16384, replay_ticks)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
