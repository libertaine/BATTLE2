# core.py — Milestone-6+ with territory scoring + win-mode + GAME OVER summary
from __future__ import annotations

import random
from typing import Any

from battle_engine.agent_state import Agent
from battle_engine.config import Config, Weights
from battle_engine.instructions import (
    ADD,
    ADDP,
    HALT,
    JMP,
    JZ,
    LOAD,
    LOADI,
    MOV,
    MOVP,
    NOP,
    STORE,
    STOREI,
    enc,
)
from battle_engine.vm import VM
from battle_engine.match import MatchRunner
from battle_engine.results import build_summary, resolve_winner
from battle_engine.scoring import ScoreMap, ScoringPolicy
from battle_engine.statistics import StatisticsCollector, StatisticsMap
from battle_engine.telemetry import (
    JSONLSink,
    JSONSummarySink,
    LegacyRendererObserver,
    ReplayPublisher,
    ReplaySink,
    SummarySink,
    build_snapshot,
)


# ----- Kernel -----
class Kernel:
    def __init__(
        self,
        cfg: Config,
        sink: ReplaySink | None = None,
        renderer: object | None = None,
        summary_sink: SummarySink | None = None,
    ):
        self.cfg = cfg
        self.vm = VM(cfg.arena_size)
        self.instr_per_tick = cfg.instr_per_tick
        self.agents: list[Agent] = []
        self.tick = 0
        self.sink = sink or JSONLSink("replay.jsonl")
        self.renderer = renderer
        self.summary_sink = (
            summary_sink if summary_sink is not None else JSONSummarySink("summary.json")
        )
        self.score: ScoreMap = {}
        self._alive_prev: dict[str, bool] = {}
        self.stats: StatisticsMap = {}
        self.rng = random.Random(cfg.seed)
        self.statistics = StatisticsCollector()
        self.scoring = ScoringPolicy(cfg.weights)

    def spawn(self, agent_id: str, entry: int, code: bytes) -> None:
        s, e = self.vm.load_code(entry, code, owner=agent_id)
        a = Agent(agent_id=agent_id, pc=s, region=(s, e))
        self.agents.append(a)
        self.score.setdefault(agent_id, 0)
        self._alive_prev[agent_id] = a.alive
        self.statistics.initialize_agent(self.stats, agent_id)

    def _snapshot(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        return build_snapshot(self.tick, self.agents, self.score, self.vm, events)

    def _apply_territory_scoring(self) -> None:
        self.scoring.score_territory(self.score, self.agents, self.vm.writer)

    def run(self, max_ticks: int = 10000, verbose: bool = True) -> str:
        renderer = LegacyRendererObserver(self.renderer, self)
        runner = MatchRunner(
            self,
            ReplayPublisher(self.sink),
            renderer,
            self.scoring,
            self.statistics,
        )
        runner.run(max_ticks, verbose)

        winner = resolve_winner(self.agents, self.score, self.cfg.win_mode)
        summary = build_summary(
            self.cfg, self.tick, self.agents, self.score, self.stats, winner
        )
        try:
            self.summary_sink.write(summary)
        except Exception:
            # v0.1 compatibility: summary persistence failures were suppressed.
            pass
        renderer.publish_result(summary)
        return winner
