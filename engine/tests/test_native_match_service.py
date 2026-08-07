from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from battle_engine.builtins import build_agent
from battle_engine.config import Config, Weights
from battle_engine.core import Kernel
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.results import build_summary
from battle_engine.telemetry import JSONLSink, NullSummarySink


def _config() -> Config:
    return Config(
        arena_size=128,
        instr_per_tick=4,
        seed=73,
        win_mode="score_fallback",
        weights=Weights(alive=0.25, kill=3.5, territory=0.5, territory_bucket=16),
    )


def _entrants() -> tuple[MatchEntrant, ...]:
    return (
        MatchEntrant("A", "writer", 0, build_agent("writer", 0, offset=80, byte=0x99)),
        MatchEntrant("B", "runner", 64, build_agent("runner", 64)),
    )


def _legacy_effective_winner(
    kernel_winner: str, score: dict[str, int | float], win_mode: str
) -> str:
    if kernel_winner:
        return kernel_winner
    if win_mode in ("score", "score_fallback"):
        ranked = sorted(score.items(), key=lambda item: (-item[1], item[0]))
        if ranked and (len(ranked) == 1 or ranked[0][1] > ranked[1][1]):
            return ranked[0][0]
    return "tie"


def test_service_is_identical_to_former_direct_kernel_orchestration(tmp_path):
    legacy_replay = tmp_path / "legacy" / "replay.jsonl"
    service_replay = tmp_path / "service" / "replay.jsonl"
    legacy_replay.parent.mkdir()
    legacy_sink = JSONLSink(str(legacy_replay))
    legacy_kernel = Kernel(_config(), legacy_sink, summary_sink=NullSummarySink())
    for entrant in _entrants():
        legacy_kernel.spawn(
            entrant.agent_id,
            entrant.start % legacy_kernel.cfg.arena_size,
            entrant.code,
        )
    legacy_winner = legacy_kernel.run(max_ticks=25, verbose=False)
    legacy_sink.close()
    legacy_summary = build_summary(
        legacy_kernel.cfg,
        legacy_kernel.tick,
        legacy_kernel.agents,
        legacy_kernel.score,
        legacy_kernel.stats,
        legacy_winner,
    )

    result = NativeMatchService().run(
        MatchRequest(
            config=_config(),
            entrants=_entrants(),
            max_ticks=25,
            replay_path=service_replay,
            verbose=False,
        )
    )

    assert service_replay.read_bytes() == legacy_replay.read_bytes()
    assert result.ticks_run == legacy_kernel.tick
    assert dict(result.score) == legacy_kernel.score
    assert result.winner == _legacy_effective_winner(
        legacy_winner, legacy_kernel.score, legacy_kernel.cfg.win_mode
    )
    assert [agent.agent_id for agent in result.agents] == ["A", "B"]
    legacy_agents = {agent["id"]: agent for agent in legacy_summary["agents"]}
    for agent in result.agents:
        actual = agent.as_legacy_statistics()
        assert actual.pop("name") == agent.name
        assert actual == {
            key: value for key, value in legacy_agents[agent.agent_id].items() if key != "id"
        }


def test_request_and_internal_results_are_frozen(tmp_path):
    request = MatchRequest(_config(), _entrants(), 1, tmp_path / "replay.jsonl", False)
    with pytest.raises(FrozenInstanceError):
        request.max_ticks = 2  # type: ignore[misc]

    result = NativeMatchService().run(request)
    with pytest.raises(TypeError):
        result.score["A"] = 99  # type: ignore[index]


def test_service_preserves_spawn_order_and_wraps_entry_points(tmp_path):
    config = Config(arena_size=32, instr_per_tick=1)
    entrants = (
        MatchEntrant("A", "first", 32, bytes([0])),
        MatchEntrant("B", "second", 48, bytes([7])),
    )

    result = NativeMatchService().run(
        MatchRequest(config, entrants, 2, tmp_path / "replay.jsonl", False)
    )

    assert [agent.agent_id for agent in result.agents] == ["A", "B"]
    assert result.agents[0].alive is True
    assert result.agents[1].alive is False
    assert result.winner == "A"
