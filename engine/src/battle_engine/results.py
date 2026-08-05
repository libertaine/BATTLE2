"""Winner resolution and persistence-neutral summary construction."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from battle_engine.agent_state import Agent
from battle_engine.config import Config
from battle_engine.scoring import ScoreMap
from battle_engine.statistics import StatisticsMap


def resolve_winner(
    agents: list[Agent], score: ScoreMap, win_mode: str
) -> str:
    alive = [agent.agent_id for agent in agents if agent.alive]
    mode = (win_mode or "score_fallback").lower()
    if len(alive) == 1:
        return alive[0]
    if mode == "survival":
        return ""
    if score:
        top = sorted(score.items(), key=lambda item: (-item[1], item[0]))
        if len(top) == 1 or top[0][1] > top[1][1]:
            return top[0][0]
    return ""


def build_summary(
    config: Config,
    ticks_run: int,
    agents: list[Agent],
    score: ScoreMap,
    statistics: StatisticsMap,
    winner: str,
) -> dict[str, Any]:
    arena = config.arena_size
    summary_agents: list[dict[str, Any]] = []
    for agent in agents:
        state = statistics[agent.agent_id]
        avg_territory = state["territory_sum"] / max(1, ticks_run)
        summary_agents.append(
            {
                "id": agent.agent_id,
                "alive": agent.alive,
                "score": score.get(agent.agent_id, 0),
                "alive_ticks": state["alive_ticks"],
                "kills": state["kills"],
                "deaths": state["deaths"],
                "cpu_total": state["total_cpu"],
                "mem_writes": state["total_mem_writes"],
                "territory_last": state["territory_last"],
                "territory_max": state["territory_max"],
                "territory_avg": avg_territory,
                "territory_pct_last": (
                    state["territory_last"] * 100.0 / arena if arena else 0.0
                ),
                "territory_pct_max": (
                    state["territory_max"] * 100.0 / arena if arena else 0.0
                ),
                "territory_pct_avg": (
                    avg_territory * 100.0 / arena if arena else 0.0
                ),
            }
        )
    return {
        "winner": winner,
        "win_mode": (config.win_mode or "score_fallback").lower(),
        "ticks": ticks_run,
        "arena_size": arena,
        "config": asdict(config),
        "score": dict(score),
        "agents": sorted(summary_agents, key=lambda item: (-item["score"], item["id"])),
    }
