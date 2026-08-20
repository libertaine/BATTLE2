from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from battle_engine.config import Config
from battle_engine.core import NOP, enc
from battle_engine.match_service import MatchEntrant
from battle_engine.replay import MatchConfiguration, ReplayHeader, write_replay
from battle_engine.result_model import ReplayReference, ResultEnvelope
from battle_engine.tournament_cli import _print_result
from battle_engine.tournament_cli import main as tournament_cli_main
from battle_engine.tournament_service import (
    TournamentConfigurationError,
    TournamentMatch,
    TournamentRequest,
    TournamentService,
    _resumed_result_mismatch,
    derive_match_seed,
)


def _entrants(count: int = 3):
    return tuple(
        MatchEntrant(chr(65 + index), f"Agent {index}", index * 32, enc(NOP))
        for index in range(count)
    )


def test_tie_is_a_reserved_entrant_id(tmp_path):
    entrants = (
        MatchEntrant("tie", "Agent 0", 0, enc(NOP)),
        MatchEntrant("B", "Agent 1", 32, enc(NOP)),
    )
    with pytest.raises(TournamentConfigurationError, match="reserved"):
        TournamentService().run(_request(tmp_path, entrants=entrants))

    # Reservation is case-insensitive: "Tie" is just as ambiguous as "tie".
    entrants = (
        MatchEntrant("Tie", "Agent 0", 0, enc(NOP)),
        MatchEntrant("B", "Agent 1", 32, enc(NOP)),
    )
    with pytest.raises(TournamentConfigurationError, match="reserved"):
        TournamentService().run(_request(tmp_path, entrants=entrants))


def test_cli_status_reports_corrupted_matches(capsys):
    result = SimpleNamespace(
        tournament_id="tournament_x",
        matches=(SimpleNamespace(status="corrupted"),),
        standings=(),
        state_path=Path("tournament.json"),
    )

    _print_result(result)

    assert "corrupted=1" in capsys.readouterr().out

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


def test_ruleset_id_omitted_defaults_to_v1(tmp_path):
    result = TournamentService().run(_request(tmp_path, entrants=_entrants(2), rounds=1))
    envelope = json.loads((result.matches[0].artifact_dir / "result.json").read_text())
    assert envelope["ruleset_id"] == "bytefray-rules-1"


def test_permanent_v2_rejects_vm_entrants_per_match_with_no_artifacts(tmp_path):
    result = TournamentService().run(
        _request(
            tmp_path,
            entrants=_entrants(2),
            rounds=1,
            ruleset_id="bytefray-rules-2",
        )
    )
    assert len(result.matches) == 1
    match = result.matches[0]
    assert match.status == "rejected"
    assert match.error_code == "ruleset_runtime_unsupported"
    assert "Python entrants only" in match.error_message
    assert not match.artifact_dir.exists()


def test_cli_help_lists_ruleset_choices_but_not_alpha_ids(capsys):
    with pytest.raises(SystemExit):
        tournament_cli_main(["--help"])
    out = capsys.readouterr().out
    assert "--ruleset" in out
    assert "bytefray-rules-1" in out
    assert "bytefray-rules-2" in out
    assert "alpha" not in out


def test_cli_ruleset_flag_unknown_value_fails_closed(capsys):
    with pytest.raises(SystemExit) as caught:
        tournament_cli_main(["writer", "runner", "--ruleset", "bytefray-rules-99"])
    assert caught.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


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


# ---------------------------------------------------------------------------
# Failed vs. rejected classification (closed set, not substring matching)
# ---------------------------------------------------------------------------
class _Diagnostic:
    def __init__(self, code):
        self.code = code


class _DiagnosticError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.diagnostic = _Diagnostic(code)


def test_agent_loading_failure_codes_are_classified_rejected(tmp_path):
    class RejectingService:
        def run(self, request):
            raise _DiagnosticError("agent_manifest_invalid")

    result = TournamentService(RejectingService()).run(
        _request(tmp_path, entrants=_entrants(2), rounds=1)
    )
    assert result.matches[0].status == "rejected"
    assert result.matches[0].error_code == "agent_manifest_invalid"


def test_infrastructure_failure_code_containing_a_rejected_substring_stays_failed(tmp_path):
    # Regression: the old classifier matched "reset" as a *substring* of any
    # code, so a transient infra failure like this would have been wrongly
    # bucketed as "rejected" (non-retryable) even though it has nothing to
    # do with agent loading or configuration.
    class FlakyInfraService:
        def run(self, request):
            raise _DiagnosticError("connection_reset_by_peer")

    result = TournamentService(FlakyInfraService()).run(
        _request(tmp_path, entrants=_entrants(2), rounds=1)
    )
    assert result.matches[0].status == "failed"
    assert result.matches[0].error_code == "connection_reset_by_peer"


# ---------------------------------------------------------------------------
# Resume validation: unit coverage of _resumed_result_mismatch
# ---------------------------------------------------------------------------
def _envelope(entrant_ids, seed, replay=None):
    return ResultEnvelope(
        result_id="result_x",
        match_id="match_x",
        mode="b2",
        winner="tie",
        termination_reason="tick_limit",
        ticks=2,
        score={},
        entrants=tuple({"agent_id": agent_id} for agent_id in entrant_ids),
        reproducibility={"seed": seed},
        replay=replay,
    )


def _scheduled(entrant_ids, seed):
    return TournamentMatch(
        schedule_id="schedule_x",
        round_number=1,
        entrant_ids=entrant_ids,
        seed=seed,
        artifact_dir=Path("unused"),
        status="completed",
    )


def test_resumed_result_mismatch_detects_different_entrant_order(tmp_path):
    envelope = _envelope(
        ["B", "A"], seed=5, replay=ReplayReference("r", "0" * 64, "replay.jsonl")
    )
    reason = _resumed_result_mismatch(
        envelope, _scheduled(("A", "B"), seed=5), tmp_path / "replay.jsonl", "match_x"
    )
    assert reason is not None and "order" in reason


def test_resumed_result_mismatch_detects_wrong_seed(tmp_path):
    envelope = _envelope(
        ["A", "B"], seed=99, replay=ReplayReference("r", "0" * 64, "replay.jsonl")
    )
    reason = _resumed_result_mismatch(
        envelope, _scheduled(("A", "B"), seed=5), tmp_path / "replay.jsonl", "match_x"
    )
    assert reason is not None and "seed" in reason


def test_resumed_result_mismatch_detects_missing_replay_reference(tmp_path):
    envelope = _envelope(["A", "B"], seed=5, replay=None)
    reason = _resumed_result_mismatch(
        envelope, _scheduled(("A", "B"), seed=5), tmp_path / "replay.jsonl", "match_x"
    )
    assert reason is not None and "replay" in reason


def test_resumed_result_mismatch_accepts_a_genuinely_matching_result(tmp_path):
    replay_path = tmp_path / "replay.jsonl"
    write_replay(
        replay_path,
        [ReplayHeader(MatchConfiguration(64), match_id="match_x", result_id="result_x")],
    )
    digest = hashlib.sha256(replay_path.read_bytes()).hexdigest()
    envelope = _envelope(["A", "B"], seed=5, replay=ReplayReference("r", digest, "replay.jsonl"))
    assert _resumed_result_mismatch(
        envelope, _scheduled(("A", "B"), seed=5), replay_path, "match_x"
    ) is None


def test_resumed_result_mismatch_detects_ruleset_id_divergence(tmp_path):
    """v0.10 Phase 4.13: a resumed result whose recorded ``ruleset_id``
    disagrees with its own replay header's ``ruleset_id`` must never be
    silently trusted -- this is the same "cannot internally contradict
    itself" check already applied to match_id/result_id.
    """

    replay_path = tmp_path / "replay.jsonl"
    write_replay(
        replay_path,
        [
            ReplayHeader(
                MatchConfiguration(64),
                match_id="match_x",
                result_id="result_x",
                ruleset_id="bytefray-rules-1",
            )
        ],
    )
    digest = hashlib.sha256(replay_path.read_bytes()).hexdigest()
    envelope = ResultEnvelope(
        result_id="result_x",
        match_id="match_x",
        mode="b2",
        winner="tie",
        termination_reason="tick_limit",
        ticks=2,
        score={},
        entrants=tuple({"agent_id": agent_id} for agent_id in ("A", "B")),
        reproducibility={"seed": 5},
        replay=ReplayReference("r", digest, "replay.jsonl"),
        ruleset_id="corrupted-ruleset-id",
    )
    reason = _resumed_result_mismatch(
        envelope, _scheduled(("A", "B"), seed=5), replay_path, "match_x"
    )
    assert reason is not None and "ruleset_id" in reason


def test_resumed_result_mismatch_accepts_matching_ruleset_id(tmp_path):
    replay_path = tmp_path / "replay.jsonl"
    write_replay(
        replay_path,
        [
            ReplayHeader(
                MatchConfiguration(64),
                match_id="match_x",
                result_id="result_x",
                ruleset_id="bytefray-rules-1",
            )
        ],
    )
    digest = hashlib.sha256(replay_path.read_bytes()).hexdigest()
    envelope = ResultEnvelope(
        result_id="result_x",
        match_id="match_x",
        mode="b2",
        winner="tie",
        termination_reason="tick_limit",
        ticks=2,
        score={},
        entrants=tuple({"agent_id": agent_id} for agent_id in ("A", "B")),
        reproducibility={"seed": 5},
        replay=ReplayReference("r", digest, "replay.jsonl"),
        ruleset_id="bytefray-rules-1",
    )
    assert _resumed_result_mismatch(
        envelope, _scheduled(("A", "B"), seed=5), replay_path, "match_x"
    ) is None


# ---------------------------------------------------------------------------
# Resume validation: end-to-end integration
# ---------------------------------------------------------------------------
def test_resume_rejects_result_copied_from_another_tournament(tmp_path):
    donor_dir = tmp_path / "donor"
    victim_dir = tmp_path / "victim"
    donor_entrants = (
        MatchEntrant("X", "Agent X", 0, enc(NOP)),
        MatchEntrant("Y", "Agent Y", 32, enc(NOP)),
    )

    donor = TournamentService().run(_request(donor_dir, entrants=donor_entrants, rounds=1))
    victim = TournamentService().run(_request(victim_dir, entrants=_entrants(2), rounds=1))

    donor_match = donor.matches[0]
    victim_match = victim.matches[0]
    (victim_match.artifact_dir / "result.json").write_bytes(
        (donor_match.artifact_dir / "result.json").read_bytes()
    )
    (victim_match.artifact_dir / "replay.jsonl").write_bytes(
        (donor_match.artifact_dir / "replay.jsonl").read_bytes()
    )

    resumed = TournamentService().run(_request(victim_dir, entrants=_entrants(2), rounds=1))
    resumed_match = resumed.matches[0]
    assert resumed_match.status == "corrupted"
    assert resumed_match.error_code == "resumed_result_mismatch"
    assert "entrant IDs" in resumed_match.error_message
    assert all(row.played == 0 for row in resumed.standings)


def test_resume_rejects_result_with_wrong_seed_for_same_entrant_names(tmp_path):
    donor_dir = tmp_path / "donor"
    victim_dir = tmp_path / "victim"

    donor = TournamentService().run(_request(donor_dir, entrants=_entrants(2), rounds=1, seed=1))
    victim = TournamentService().run(_request(victim_dir, entrants=_entrants(2), rounds=1, seed=2))
    donor_match = donor.matches[0]
    victim_match = victim.matches[0]
    assert donor_match.entrant_ids == victim_match.entrant_ids
    assert donor_match.seed != victim_match.seed

    (victim_match.artifact_dir / "result.json").write_bytes(
        (donor_match.artifact_dir / "result.json").read_bytes()
    )
    (victim_match.artifact_dir / "replay.jsonl").write_bytes(
        (donor_match.artifact_dir / "replay.jsonl").read_bytes()
    )

    resumed = TournamentService().run(_request(victim_dir, entrants=_entrants(2), rounds=1, seed=2))
    resumed_match = resumed.matches[0]
    assert resumed_match.status == "corrupted"
    assert "seed" in resumed_match.error_message
    assert all(row.played == 0 for row in resumed.standings)


def test_resume_rejects_malformed_result_json(tmp_path):
    first = TournamentService().run(_request(tmp_path, entrants=_entrants(2), rounds=1))
    match = first.matches[0]
    (match.artifact_dir / "result.json").write_text("{not valid json", encoding="utf-8")

    resumed = TournamentService().run(_request(tmp_path, entrants=_entrants(2), rounds=1))
    resumed_match = resumed.matches[0]
    assert resumed_match.status == "corrupted"
    assert resumed_match.error_code == "resumed_result_mismatch"
    assert all(row.played == 0 for row in resumed.standings)


def test_resume_rejects_result_whose_replay_was_truncated(tmp_path):
    first = TournamentService().run(_request(tmp_path, entrants=_entrants(2), rounds=1))
    match = first.matches[0]
    replay_path = match.artifact_dir / "replay.jsonl"
    original = replay_path.read_bytes()
    replay_path.write_bytes(original[: len(original) // 2])

    resumed = TournamentService().run(_request(tmp_path, entrants=_entrants(2), rounds=1))
    resumed_match = resumed.matches[0]
    assert resumed_match.status == "corrupted"
    assert "replay verification failed" in resumed_match.error_message
    assert all(row.played == 0 for row in resumed.standings)


def test_resume_still_accepts_a_valid_unmodified_result(tmp_path):
    first = TournamentService().run(_request(tmp_path, rounds=1))

    class NoRunService:
        def run(self, request):
            raise AssertionError("a valid completed match must not be rerun")

    resumed = TournamentService(NoRunService()).run(_request(tmp_path, rounds=1))
    assert all(match.status == "completed" for match in resumed.matches)
    assert resumed.standings == first.standings


def test_corrupted_match_is_retried_when_retry_failures_is_set(tmp_path):
    first = TournamentService().run(_request(tmp_path, rounds=1))
    match = first.matches[0]
    (match.artifact_dir / "result.json").write_text("{not valid json", encoding="utf-8")

    corrupted = TournamentService().run(_request(tmp_path, rounds=1))
    assert corrupted.matches[0].status == "corrupted"

    retried = TournamentService().run(_request(tmp_path, rounds=1, retry_failures=True))
    assert retried.matches[0].status == "completed"


def test_newly_discovered_corruption_is_retried_immediately(tmp_path):
    first = TournamentService().run(_request(tmp_path, entrants=_entrants(2), rounds=1))
    (first.matches[0].artifact_dir / "result.json").write_text("{bad", encoding="utf-8")

    retried = TournamentService().run(
        _request(tmp_path, entrants=_entrants(2), rounds=1, retry_failures=True)
    )

    assert retried.matches[0].status == "completed"


def test_resume_rejects_foreign_result_with_same_entrants_seed_different_config(
    tmp_path,
):
    donor = TournamentService().run(
        _request(tmp_path / "donor", entrants=_entrants(2), rounds=1)
    )
    victim_request = _request(
        tmp_path / "victim",
        entrants=_entrants(2),
        rounds=1,
        config=Config(arena_size=256, instr_per_tick=1),
    )
    victim = TournamentService().run(victim_request)
    donor_match, victim_match = donor.matches[0], victim.matches[0]
    (victim_match.artifact_dir / "result.json").write_bytes(
        (donor_match.artifact_dir / "result.json").read_bytes()
    )
    (victim_match.artifact_dir / "replay.jsonl").write_bytes(
        (donor_match.artifact_dir / "replay.jsonl").read_bytes()
    )

    resumed = TournamentService().run(victim_request)

    assert resumed.matches[0].status == "corrupted"
    assert "match ID" in resumed.matches[0].error_message


def test_resume_rejects_replay_header_identity_mismatch(tmp_path):
    first = TournamentService().run(_request(tmp_path, entrants=_entrants(2), rounds=1))
    match = first.matches[0]
    result_path = match.artifact_dir / "result.json"
    replay_path = match.artifact_dir / "replay.jsonl"
    envelope = json.loads(result_path.read_text(encoding="utf-8"))
    records = replay_path.read_text(encoding="utf-8").splitlines()
    header = json.loads(records[0])
    header["result_id"] = "result_foreign"
    records[0] = json.dumps(header, sort_keys=True, separators=(",", ":"))
    replay_path.write_text("\n".join(records) + "\n", encoding="utf-8")
    envelope["replay"]["sha256"] = hashlib.sha256(replay_path.read_bytes()).hexdigest()
    result_path.write_text(json.dumps(envelope), encoding="utf-8")

    resumed = TournamentService().run(_request(tmp_path, entrants=_entrants(2), rounds=1))

    assert resumed.matches[0].status == "corrupted"
    assert "result ID" in resumed.matches[0].error_message
