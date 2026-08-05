"""In-memory match statistics collection."""

from __future__ import annotations

from collections import Counter
from typing import TypeAlias

from battle_engine.agent_state import Agent


AgentStatistics: TypeAlias = dict[str, int]
StatisticsMap: TypeAlias = dict[str, AgentStatistics]


class StatisticsCollector:
    def initialize_agent(self, statistics: StatisticsMap, agent_id: str) -> None:
        statistics[agent_id] = {
            "alive_ticks": 0,
            "total_cpu": 0,
            "total_mem_writes": 0,
            "kills": 0,
            "deaths": 0,
            "territory_max": 0,
            "territory_sum": 0,
            "territory_last": 0,
        }

    def record_tick(
        self,
        statistics: StatisticsMap,
        agents: list[Agent],
        ownership: list[str | None],
    ) -> None:
        for agent in agents:
            state = statistics[agent.agent_id]
            if agent.alive:
                state["alive_ticks"] += 1
            state["total_cpu"] += agent.cpu_used
            state["total_mem_writes"] = agent.mem_writes

        own_counts = Counter(ownership)
        for agent in agents:
            cells = own_counts.get(agent.agent_id, 0)
            state = statistics[agent.agent_id]
            state["territory_last"] = cells
            state["territory_sum"] += cells
            if cells > state["territory_max"]:
                state["territory_max"] = cells

    def record_death(
        self,
        statistics: StatisticsMap,
        victim: str,
        killer: str | None = None,
    ) -> None:
        statistics[victim]["deaths"] += 1
        if killer is not None:
            statistics[killer]["kills"] += 1
