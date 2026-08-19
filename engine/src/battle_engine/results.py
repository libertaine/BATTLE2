"""Winner resolution and persistence-neutral summary construction."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict
from typing import Any, Protocol

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

    ``agent_id`` is declared read-only (a property, not a plain attribute)
    because both concrete state classes expose it as a compatibility
    property backed by their stored ``EntrantIdentity`` -- see
    ``docs/V1_5_PHASE5_ENTRANT_IDENTITY_EXECUTION_STATE.md``. A plain
    ``agent_id: str`` attribute declaration here would reject that read-only
    property under structural typing even though the runtime value is
    identical.
    """

    @property
    def agent_id(self) -> str: ...

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

    Survivor eligibility (v2.0.0-alpha.4.1): a dead entrant can never win
    while at least one entrant is still alive, regardless of accumulated
    score -- the direct N-entrant generalization of the pre-existing
    1v1/single-survivor rule below, not a new rule. With exactly one
    entrant alive, that entrant wins outright (unchanged). With two or
    more alive, ``score_fallback`` compares only the alive entrants --
    dead entrants keep their historical score (nothing here mutates
    ``score``) but are excluded from winner eligibility. With zero alive,
    there is no survivor to prefer, so comparison falls back to every
    entrant, dead or alive, exactly as it always has -- see
    ``docs/V2_0_ALPHA4_1_WINNER_SEMANTICS.md`` for why the zero-survivor
    case is deliberately not given its own special rule.
    """

    alive = [agent.agent_id for agent in agents if agent.alive]
    mode = (win_mode or "score_fallback").lower()
    if len(alive) == 1:
        return alive[0]
    if mode == "survival":
        return ""
    eligible = set(alive) if alive else {agent.agent_id for agent in agents}
    if score:
        top = sorted(
            (item for item in score.items() if item[0] in eligible),
            key=lambda item: (-item[1], item[0]),
        )
        if top and (len(top) == 1 or top[0][1] > top[1][1]):
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
