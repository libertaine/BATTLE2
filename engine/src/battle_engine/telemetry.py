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


class NullSummarySink:
    """Accept an in-memory match summary without persisting another artifact."""

    def write(self, summary: dict[str, Any]) -> None:
        del summary


def _agent_snapshot(agent: Any) -> dict[str, Any]:
    """Build one per-tick agent dict, tolerant of VM ``Agent`` and Python
    ``PythonEntrantState`` shapes (see ``python_runtime.PythonEntrantState``).

    Both runtimes track A/P/Z-shaped register state; the VM keeps it in a
    ``regs`` mapping while the Python runtime keeps flat attributes. Only
    the Python runtime tracks ``last_read`` and a per-entrant termination
    reason, so those are ``None`` for VM agents.
    """

    register_a: int | None
    register_p: int | None
    zero_flag: bool | None
    last_read: int | None
    termination_reason: str | None
    regs = getattr(agent, "regs", None)
    if regs is not None:
        register_a = regs.get("A")
        register_p = regs.get("P")
        zero_flag = bool(regs.get("Z", 0))
        last_read = None
        termination_reason = None
    else:
        register_a = getattr(agent, "register_a", None)
        register_p = getattr(agent, "register_p", None)
        zero_flag = getattr(agent, "zero_flag", None)
        last_read = getattr(agent, "last_read", None)
        termination_reason = getattr(agent, "entrant_termination", None)
    return {
        "id": agent.agent_id,
        "pc": agent.pc,
        "alive": agent.alive,
        "cpu_used": agent.cpu_used,
        "mem_writes": agent.mem_writes,
        "region": [agent.region[0], agent.region[1]],
        "register_a": register_a,
        "register_p": register_p,
        "zero_flag": zero_flag,
        "last_read": last_read,
        "termination_reason": termination_reason,
    }


def build_snapshot(
    tick: int,
    agents: list[Agent],
    score: ScoreMap,
    vm: VM,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "tick": tick,
        "agents": [_agent_snapshot(agent) for agent in agents],
        "score": dict(score),
        "events": events,
        "memory_diffs": [
            {"addr": address, "len": length, "owner": owner, "values": values}
            for address, length, owner, values in vm.tick_diffs
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
