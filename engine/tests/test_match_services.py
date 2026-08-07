from __future__ import annotations

from typing import Any

import pytest

from battle_engine.agent_state import Agent
from battle_engine.config import Config, Weights
from battle_engine.core import HALT, NOP, Kernel, enc
from battle_engine.results import build_summary, resolve_winner
from battle_engine.scoring import ScoringPolicy
from battle_engine.statistics import StatisticsCollector


class RecordingReplaySink:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []
        self.closed = False

    def emit(self, record: dict[str, Any]) -> None:
        self.records.append(record)

    def close(self) -> None:
        self.closed = True


class RecordingSummarySink:
    def __init__(self) -> None:
        self.summary: dict[str, Any] | None = None

    def write(self, summary: dict[str, Any]) -> None:
        self.summary = summary


def _kernel(config: Config) -> tuple[Kernel, RecordingReplaySink, RecordingSummarySink]:
    replay = RecordingReplaySink()
    summary = RecordingSummarySink()
    return (
        Kernel(config, sink=replay, summary_sink=summary),  # type: ignore[arg-type]
        replay,
        summary,
    )


def test_winner_resolution_preserves_survival_score_fallback_and_ties():
    agents = [Agent("A", 0), Agent("B", 1)]
    assert resolve_winner(agents, {"A": 10, "B": 1}, "survival") == ""
    assert resolve_winner(agents, {"A": 10, "B": 1}, "score_fallback") == "A"
    assert resolve_winner(agents, {"A": 10, "B": 10}, "score_fallback") == ""
    agents[1].alive = False
    assert resolve_winner(agents, {"A": 0, "B": 99}, "survival") == "A"


def test_scoring_policy_preserves_alive_and_territory_buckets():
    agents = [Agent("A", 0), Agent("B", 1, alive=False)]
    score: dict[str, int | float] = {"A": 0, "B": 0}
    policy = ScoringPolicy(Weights(alive=1.5, kill=7, territory=2, territory_bucket=3))
    policy.score_alive(score, agents)
    policy.score_territory(score, agents, ["A"] * 7 + ["B"] * 2)
    assert score == {"A": 5.5, "B": 0}
    policy.score_kill(score, "A")
    assert score["A"] == 12.5


def test_kernel_attributes_kill_to_memory_owner():
    kernel, replay, _ = _kernel(
        Config(arena_size=32, instr_per_tick=1, weights=Weights(1, 5, 0))
    )
    kernel.spawn("A", 0, enc(NOP))
    kernel.spawn("B", 16, enc(NOP))
    kernel.vm._wr8(16, 0xFF, "A")

    assert kernel.run(max_ticks=2, verbose=False) == "A"
    assert kernel.score == {"A": 6, "B": 0}
    assert kernel.stats["A"]["kills"] == 1
    assert kernel.stats["B"]["deaths"] == 1
    # records[1] is the tick-0 initial-state snapshot; tick 1 is records[2].
    assert replay.records[2]["events"] == [{"type": "kill", "victim": "B", "by": "A"}]


def test_kernel_records_death_without_attributable_killer():
    kernel, replay, _ = _kernel(
        Config(arena_size=32, instr_per_tick=1, weights=Weights(1, 5, 0))
    )
    kernel.spawn("A", 0, enc(NOP))
    kernel.spawn("B", 16, enc(HALT))

    assert kernel.run(max_ticks=2, verbose=False) == "A"
    assert kernel.score == {"A": 1, "B": 0}
    assert kernel.stats["A"]["kills"] == 0
    assert kernel.stats["B"]["deaths"] == 1
    # records[1] is the tick-0 initial-state snapshot; tick 1 is records[2].
    assert replay.records[2]["events"] == [{"type": "death", "victim": "B"}]


def test_summary_fields_and_agent_statistics_remain_compatible():
    kernel, _, output = _kernel(
        Config(arena_size=32, instr_per_tick=1, seed=99, weights=Weights(1, 5, 0))
    )
    kernel.spawn("A", 0, enc(NOP))
    kernel.spawn("B", 16, enc(HALT))
    kernel.run(max_ticks=2, verbose=False)

    summary = output.summary
    assert summary is not None
    assert set(summary) == {
        "winner",
        "win_mode",
        "ticks",
        "arena_size",
        "config",
        "score",
        "agents",
    }
    assert set(summary["agents"][0]) == {
        "id",
        "alive",
        "score",
        "alive_ticks",
        "kills",
        "deaths",
        "cpu_total",
        "mem_writes",
        "territory_last",
        "territory_max",
        "territory_avg",
        "territory_pct_last",
        "territory_pct_max",
        "territory_pct_avg",
    }
    assert summary["config"]["seed"] == 99


def test_summary_construction_has_no_persistence_dependency():
    config = Config(arena_size=8)
    agent = Agent("A", 0)
    statistics = StatisticsCollector()
    stats = {}
    statistics.initialize_agent(stats, "A")
    summary = build_summary(config, 0, [agent], {"A": 0}, stats, "A")
    assert summary["winner"] == "A"
    assert summary["agents"][0]["territory_avg"] == 0.0


def test_replay_sink_is_closed_on_success():
    kernel, replay, _ = _kernel(Config(arena_size=16, instr_per_tick=1))
    kernel.spawn("A", 0, enc(NOP))
    kernel.run(max_ticks=1, verbose=False)
    assert replay.closed


def test_replay_sink_is_closed_when_publication_fails():
    class FailingSink(RecordingReplaySink):
        def emit(self, record: dict[str, Any]) -> None:
            raise RuntimeError("output failed")

    replay = FailingSink()
    kernel = Kernel(
        Config(arena_size=16),
        sink=replay,  # type: ignore[arg-type]
        summary_sink=RecordingSummarySink(),
    )
    with pytest.raises(RuntimeError, match="output failed"):
        kernel.run(max_ticks=1, verbose=False)
    assert replay.closed
