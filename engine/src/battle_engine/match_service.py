"""Application service for resolved native BATTLE2 VM matches.

The service owns VM construction, spawning, execution, and partial-artifact
cleanup.  Agent discovery, CLI parsing, pMARS, and external result persistence
remain outside this native-only boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from battle_engine.config import Config
from battle_engine.core import Kernel
from battle_engine.scoring import ScoreMap
from battle_engine.telemetry import JSONLSink, NullSummarySink


@dataclass(frozen=True)
class MatchEntrant:
    """Resolved VM entrant ready to be spawned without further discovery."""

    agent_id: str
    name: str
    start: int
    code: bytes


@dataclass(frozen=True)
class MatchRequest:
    """Complete input required to execute one resolved native VM match."""

    config: Config
    entrants: tuple[MatchEntrant, ...]
    max_ticks: int
    replay_path: Path
    verbose: bool = True


@dataclass(frozen=True)
class NativeAgentResult:
    """Persistence-neutral final state and statistics for one entrant."""

    agent_id: str
    name: str
    alive: bool
    score: int | float
    alive_ticks: int
    kills: int
    deaths: int
    cpu_total: int
    mem_writes: int
    territory_last: int
    territory_max: int
    territory_avg: float
    territory_pct_last: float
    territory_pct_max: float
    territory_pct_avg: float

    def as_legacy_statistics(self) -> dict[str, object]:
        """Return the v0.2 CLI agent-statistics shape during migration."""

        return {
            "name": self.name,
            "alive": self.alive,
            "score": self.score,
            "alive_ticks": self.alive_ticks,
            "kills": self.kills,
            "deaths": self.deaths,
            "cpu_total": self.cpu_total,
            "mem_writes": self.mem_writes,
            "territory_last": self.territory_last,
            "territory_max": self.territory_max,
            "territory_avg": self.territory_avg,
            "territory_pct_last": self.territory_pct_last,
            "territory_pct_max": self.territory_pct_max,
            "territory_pct_avg": self.territory_pct_avg,
        }


@dataclass(frozen=True)
class NativeMatchResult:
    """Canonical internal result of one native VM match."""

    winner: str
    ticks_run: int
    score: Mapping[str, int | float]
    agents: tuple[NativeAgentResult, ...]
    replay_path: Path

    @property
    def agents_by_id(self) -> Mapping[str, NativeAgentResult]:
        return MappingProxyType({agent.agent_id: agent for agent in self.agents})


def _effective_winner(kernel_winner: str | None, score: ScoreMap, win_mode: str) -> str:
    if kernel_winner:
        return kernel_winner
    if win_mode in ("score", "score_fallback"):
        ranked = sorted(score.items(), key=lambda item: (-item[1], item[0]))
        if not ranked:
            return "tie"
        if len(ranked) == 1:
            return ranked[0][0]
        if ranked[0][1] > ranked[1][1]:
            return ranked[0][0]
    return "tie"


def _build_result(
    kernel: Kernel,
    entrants: tuple[MatchEntrant, ...],
    kernel_winner: str,
    replay_path: Path,
) -> NativeMatchResult:
    ticks_run = int(kernel.tick or 0)
    arena_size = int(kernel.cfg.arena_size or 0)
    names = {entrant.agent_id: entrant.name for entrant in entrants}
    agent_results: list[NativeAgentResult] = []
    for agent in kernel.agents:
        statistics = kernel.stats.get(agent.agent_id, {})
        territory_sum = int(statistics.get("territory_sum", 0) or 0)
        territory_last = int(statistics.get("territory_last", 0) or 0)
        territory_max = int(statistics.get("territory_max", 0) or 0)
        territory_avg = territory_sum / max(1, ticks_run)
        agent_results.append(
            NativeAgentResult(
                agent_id=agent.agent_id,
                name=names.get(agent.agent_id, agent.agent_id),
                alive=bool(agent.alive),
                score=kernel.score.get(agent.agent_id, 0),
                alive_ticks=int(statistics.get("alive_ticks", 0) or 0),
                kills=int(statistics.get("kills", 0) or 0),
                deaths=int(statistics.get("deaths", 0) or 0),
                cpu_total=int(statistics.get("total_cpu", 0) or 0),
                mem_writes=int(statistics.get("total_mem_writes", 0) or 0),
                territory_last=territory_last,
                territory_max=territory_max,
                territory_avg=territory_avg,
                territory_pct_last=(territory_last * 100.0 / arena_size if arena_size else 0.0),
                territory_pct_max=(territory_max * 100.0 / arena_size if arena_size else 0.0),
                territory_pct_avg=(territory_avg * 100.0 / arena_size if arena_size else 0.0),
            )
        )
    score = MappingProxyType(dict(kernel.score))
    return NativeMatchResult(
        winner=_effective_winner(kernel_winner, dict(score), kernel.cfg.win_mode),
        ticks_run=ticks_run,
        score=score,
        agents=tuple(agent_results),
        replay_path=replay_path,
    )


class NativeMatchService:
    """Execute resolved bytecode entrants through the existing Kernel unchanged."""

    def run(self, request: MatchRequest) -> NativeMatchResult:
        replay_path = request.replay_path.resolve()
        summary_path = replay_path.with_name("summary.json")
        replay_path.parent.mkdir(parents=True, exist_ok=True)
        sink = JSONLSink(str(replay_path))
        try:
            kernel = Kernel(request.config, sink, summary_sink=NullSummarySink())
            for entrant in request.entrants:
                kernel.spawn(
                    entrant.agent_id,
                    entrant.start % request.config.arena_size,
                    entrant.code,
                )
            kernel_winner = kernel.run(max_ticks=request.max_ticks, verbose=request.verbose)
        except BaseException:
            sink.close()
            replay_path.unlink(missing_ok=True)
            summary_path.unlink(missing_ok=True)
            raise
        finally:
            sink.close()
        return _build_result(kernel, request.entrants, kernel_winner, replay_path)


__all__ = [
    "MatchEntrant",
    "MatchRequest",
    "NativeAgentResult",
    "NativeMatchResult",
    "NativeMatchService",
]
