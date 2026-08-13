"""Scoring policy for match state; no VM execution or persistence."""

from __future__ import annotations

from collections import Counter
from typing import TypeAlias

from battle_engine.agent_state import Agent
from battle_engine.config import Weights

ScoreMap: TypeAlias = dict[str, int | float]


class ScoringPolicy:
    def __init__(self, weights: Weights):
        self.weights = weights

    def score_alive(self, score: ScoreMap, agents: list[Agent]) -> None:
        for agent in agents:
            if agent.alive:
                score[agent.agent_id] = score.get(agent.agent_id, 0) + self.weights.alive

    def score_territory(
        self,
        score: ScoreMap,
        agents: list[Agent],
        ownership: list[str | None],
    ) -> None:
        if self.weights.territory <= 0:
            return
        own_counts = Counter(ownership)
        for agent in agents:
            cells = own_counts.get(agent.agent_id, 0)
            buckets = cells // max(1, self.weights.territory_bucket)
            if buckets:
                score[agent.agent_id] = (
                    score.get(agent.agent_id, 0) + buckets * self.weights.territory
                )

    def score_kill(self, score: ScoreMap, killer: str) -> None:
        score[killer] = score.get(killer, 0) + self.weights.kill
