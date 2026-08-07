from __future__ import annotations

import json

import pytest

from battle_engine.config import Config
from battle_engine.core import NOP, enc
from battle_engine.match_service import MatchEntrant, NativeMatchService
from battle_engine.tournament_service import (
    TournamentConfigurationError,
    TournamentRequest,
    TournamentService,
    derive_match_seed,
)


def _entrants(count: int = 3):
    return tuple(
        MatchEntrant(chr(65 + index), f"Agent {index}", index * 32, enc(NOP))
        for index in range(count)
    )


def _request(tmp_path, **changes):
    values = {
        "entrants": _entrants(),
        "config": Config(arena_size=128, instr_per_tick=1),
        "rounds": 2,
        "max_ticks": 2,
        "output_dir": tmp_path,
        "seed": 91,
        "verbose": False,
    }
    values.update(changes)
    return TournamentRequest(**values)


def test_round_robin_schedule_standings_and_artifacts_are_deterministic(tmp_path):
    result = TournamentService().run(_request(tmp_path))

    assert len(result.matches) == 6
    assert [match.entrant_ids for match in result.matches[:3]] == [
        ("A", "B"),
        ("A", "C"),
        ("B", "C"),
    ]
    assert all(match.status == "completed" for match in result.matches)
    assert all((match.artifact_dir / "result.json").is_file() for match in result.matches)
    assert all((match.artifact_dir / "replay.jsonl").is_file() for match in result.matches)
    assert [(row.agent_id, row.played, row.ties) for row in result.standings] == [
        ("A", 4, 4),
        ("B", 4, 4),
        ("C", 4, 4),
    ]
    state = json.loads(result.state_path.read_text())
    assert state["schema"] == "battle2.tournament"
    assert state["standings"][0]["played"] == 4


def test_resume_consumes_canonical_results_without_rerunning(tmp_path):
    request = _request(tmp_path, rounds=1)
    first = TournamentService().run(request)

    class NoRunService:
        def run(self, request):
            raise AssertionError("completed matches must be resumed")

    resumed = TournamentService(NoRunService()).run(request)
    assert resumed.tournament_id == first.tournament_id
    assert resumed.standings == first.standings
    assert [match.match_id for match in resumed.matches] == [
        match.match_id for match in first.matches
    ]


def test_seed_derivation_is_stable_and_sensitive():
    assert derive_match_seed(7, 1, "A", "B") == derive_match_seed(7, 1, "A", "B")
    assert derive_match_seed(7, 1, "A", "B") != derive_match_seed(7, 2, "A", "B")
    assert derive_match_seed(7, 1, "A", "B") != derive_match_seed(7, 1, "B", "A")


def test_mixed_division_is_rejected_before_artifacts(tmp_path):
    entrants = (
        _entrants(1)[0],
        MatchEntrant.python("P", "Python", 32, object()),
    )
    with pytest.raises(TournamentConfigurationError, match="mixed groups"):
        TournamentService().run(_request(tmp_path, entrants=entrants))
    assert not list(tmp_path.iterdir())


def test_failed_match_is_recorded_and_excluded_from_standings(tmp_path):
    class FailingService:
        def run(self, request):
            raise RuntimeError("backend broke")

    result = TournamentService(FailingService()).run(
        _request(tmp_path, entrants=_entrants(2), rounds=1)
    )
    assert result.matches[0].status == "failed"
    assert result.matches[0].error_code == "match_failed"
    assert [row.played for row in result.standings] == [0, 0]


def test_changed_request_does_not_resume_incompatible_state(tmp_path):
    TournamentService().run(_request(tmp_path, rounds=1))
    with pytest.raises(TournamentConfigurationError, match="does not match"):
        TournamentService().run(_request(tmp_path, rounds=2))
