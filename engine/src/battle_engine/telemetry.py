"""Replay, summary, and legacy-renderer output ports and adapters."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Protocol

from battle_engine.agent_state import Agent
from battle_engine.config import Config
from battle_engine.scoring import ScoreMap
from battle_engine.vm import VM


class ReplaySink(Protocol):
    def emit(self, record: dict[str, Any]) -> None: ...
    def close(self) -> None: ...


class SummarySink(Protocol):
    def write(self, summary: dict[str, Any]) -> None: ...


class JSONLSink:
    def __init__(self, path: str = "replay.jsonl"):
        self._f = open(path, "w", buffering=1)

    def emit(self, record: dict[str, Any]) -> None:
        self._f.write(json.dumps(record, separators=(",", ":")) + "\n")

    def close(self) -> None:
        self._f.close()


class JSONSummarySink:
    def __init__(self, path: str | Path = "summary.json"):
        self.path = Path(path)

    def write(self, summary: dict[str, Any]) -> None:
        with self.path.open("w") as stream:
            json.dump(summary, stream, indent=2)


def build_snapshot(
    tick: int,
    agents: list[Agent],
    score: ScoreMap,
    vm: VM,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "tick": tick,
        "agents": [
            {
                "id": agent.agent_id,
                "pc": agent.pc,
                "alive": agent.alive,
                "cpu_used": agent.cpu_used,
                "mem_writes": agent.mem_writes,
                "region": [agent.region[0], agent.region[1]],
            }
            for agent in agents
        ],
        "score": dict(score),
        "events": events,
        "memory_diffs": [
            {"addr": address, "len": length, "owner": owner}
            for address, length, owner in vm.tick_diffs
        ],
    }


class ReplayPublisher:
    def __init__(self, sink: ReplaySink):
        self.sink = sink

    def publish_header(self, config: Config) -> None:
        self.sink.emit({"tick": 0, "ver": 6, "config": asdict(config)})

    def publish_tick(
        self,
        tick: int,
        agents: list[Agent],
        score: ScoreMap,
        vm: VM,
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        snapshot = build_snapshot(tick, agents, score, vm, events)
        self.sink.emit(snapshot)
        return snapshot

    def close(self) -> None:
        close = getattr(self.sink, "close", None)
        if callable(close):
            close()


class LegacyRendererObserver:
    """Keep renderer-specific callbacks outside match-domain services."""

    def __init__(self, renderer: object | None, kernel: object):
        self.renderer = renderer
        self.kernel = kernel

    def start(self) -> None:
        if self.renderer:
            self.renderer.on_init(self.kernel)  # type: ignore[attr-defined]

    def publish_tick(
        self, tick: int, snapshot: dict[str, Any], config: Config, vm: VM
    ) -> None:
        if self.renderer:
            self.renderer.on_tick(  # type: ignore[attr-defined]
                tick,
                {**snapshot, "config": asdict(config), "__owners__": vm.writer},
            )

    def close(self) -> None:
        if self.renderer:
            self.renderer.on_close()  # type: ignore[attr-defined]

    def publish_result(self, summary: dict[str, Any]) -> None:
        if self.renderer and hasattr(self.renderer, "on_game_over"):
            try:
                self.renderer.on_game_over(summary)  # type: ignore[attr-defined]
            except Exception:
                # v0.1 compatibility: optional final renderer pages never fail a match.
                pass
