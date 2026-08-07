"""Winner resolution and persistence-neutral summary construction."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Protocol, Sequence

from battle_engine.agent_state import Agent
from battle_engine.config import Config
from battle_engine.scoring import ScoreMap
from battle_engine.statistics import StatisticsMap

# The single canonical "no winner" sentinel used across ``NativeMatchResult``,
# ``result.json``, and the compatibility summary. Reserved from the entrant
# identifier namespace by ``TournamentService`` so it can never collide with
# a real agent ID (see ``tournament_service._validate``).
WINNER_TIE_SENTINEL = "tie"


class HasAgentIdentity(Protocol):
    """Structural shape ``resolve_winner`` needs from either runtime's state.

    Both the native VM's ``Agent`` and the Python runtime's
    ``PythonEntrantState`` satisfy this without inheritance -- winner
    resolution only ever needs to know who is still alive and how to name
    them, so it should not be coupled to either concrete state class.
    """

    agent_id: str
    alive: bool


def resolve_winner(
    agents: Sequence[HasAgentIdentity], score: ScoreMap, win_mode: str
) -> str:
    """Resolve the winner, or ``""`` when there is no single winner.

    This is the one authoritative winner-resolution implementation shared
    by the VM (``core.Kernel.run``) and Python (``python_runtime``)
    paths. Callers that need a display-friendly "no winner" value (rather
    than an empty string) should apply ``WINNER_TIE_SENTINEL`` themselves;
    keeping that mapping out of this function lets it stay agnostic of
    presentation concerns.
    """

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
