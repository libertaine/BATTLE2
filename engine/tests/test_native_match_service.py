from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from battle_engine.builtins import build_agent
from battle_engine.config import Config, Weights
from battle_engine.core import HALT, NOP, Kernel, enc
from battle_engine.match_service import (
    MatchEntrant,
    MatchRequest,
    NativeMatchService,
    UnsupportedMatchCompositionError,
)
from battle_engine.replay import TickSnapshot, iter_replay, record_to_dict
from battle_engine.results import build_summary
from battle_engine.ruleset_policy import TerminationReason, UnknownRulesetError
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

    legacy_ticks = [record for record in iter_replay(legacy_replay) if isinstance(record, TickSnapshot)]
    service_ticks = [record for record in iter_replay(service_replay) if isinstance(record, TickSnapshot)]
    def payload(record):
        value = record_to_dict(record)
        value.pop("schema_version")
        return value

    assert [payload(record) for record in service_ticks] == [
        payload(record) for record in legacy_ticks
    ]
    assert result.result_path == service_replay.with_name("result.json")
    assert result.result_path.is_file()
    assert result.match_id and result.result_id and len(result.replay_sha256) == 64
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


def test_vm_termination_reasons_for_one_survivor_all_dead_and_tick_limit(tmp_path):
    """Direct ``NativeMatchResult.termination_reason`` coverage for the VM path.

    ``test_ruleset_v1_equivalence.py``'s golden corpus exercises all three
    VM scenarios but every one of them happens to end via ``tick_limit``
    (see Phase 1's baseline) -- it never directly proves ``last_agent_
    standing``/``all_agents_dead`` for VM the way ``test_python_runtime.
    py::test_halt_and_tick_limit_have_explicit_termination_reasons`` already
    does for Python. This pins all three VM reason values explicitly.
    """

    config = _config()

    survivor = NativeMatchService().run(
        MatchRequest(
            config,
            (
                MatchEntrant("A", "halts", 0, enc(HALT)),
                MatchEntrant("B", "loops", 16, enc(NOP)),
            ),
            5,
            tmp_path / "survivor.jsonl",
            False,
        )
    )
    assert survivor.termination_reason is TerminationReason.LAST_AGENT_STANDING
    assert survivor.ticks_run == 1

    all_dead = NativeMatchService().run(
        MatchRequest(
            config,
            (
                MatchEntrant("A", "halts-a", 0, enc(HALT)),
                MatchEntrant("B", "halts-b", 16, enc(HALT)),
            ),
            5,
            tmp_path / "all_dead.jsonl",
            False,
        )
    )
    assert all_dead.termination_reason is TerminationReason.ALL_AGENTS_DEAD
    assert all_dead.ticks_run == 1

    tick_limit = NativeMatchService().run(
        MatchRequest(
            config,
            (
                MatchEntrant("A", "loops-a", 0, enc(NOP)),
                MatchEntrant("B", "loops-b", 16, enc(NOP)),
            ),
            3,
            tmp_path / "tick_limit.jsonl",
            False,
        )
    )
    assert tick_limit.termination_reason is TerminationReason.TICK_LIMIT
    assert tick_limit.ticks_run == 3


def test_duplicate_vm_entrant_ids_are_rejected(tmp_path):
    entrants = (
        MatchEntrant("A", "first", 0, build_agent("runner", 0)),
        MatchEntrant("A", "second", 16, build_agent("runner", 16)),
    )

    with pytest.raises(UnsupportedMatchCompositionError, match="unique"):
        NativeMatchService().run(
            MatchRequest(_config(), entrants, 2, tmp_path / "replay.jsonl", False)
        )
    # Nothing should have been written for a request rejected before execution.
    assert not (tmp_path / "replay.jsonl").exists()


def test_duplicate_python_entrant_ids_are_rejected(tmp_path):
    import json as _json

    from battle_engine.agents import resolve_agent

    directory = tmp_path / "agents" / "solo"
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text(
        _json.dumps(
            {
                "kind": "python",
                "api_version": 1,
                "entrypoint": "agent.py:create_agent",
                "name": "solo",
                "display": "Solo",
                "version": "1.0",
            }
        ),
        encoding="utf-8",
    )
    (directory / "agent.py").write_text(
        "from battle_engine.agent_api import ActionKind, AgentAction\n"
        "class Agent:\n"
        "    def reset(self, context): pass\n"
        "    def act(self, observation): return AgentAction(ActionKind.NOP)\n"
        "def create_agent(): return Agent()\n",
        encoding="utf-8",
    )
    spec = resolve_agent(tmp_path, "solo")
    entrants = (
        MatchEntrant.python("A", "solo", 0, spec),
        MatchEntrant.python("A", "solo", 32, spec),
    )

    with pytest.raises(UnsupportedMatchCompositionError, match="unique"):
        NativeMatchService().run(
            MatchRequest(_config(), entrants, 2, tmp_path / "replay.jsonl", False)
        )


class _FailOnRunKernel:
    """Stand-in for Kernel whose ``run`` fails after entrants are spawned."""

    def __init__(self, *args, **kwargs):
        self.agents = []
        self.cfg = args[0]

    def spawn(self, agent_id, entry, code):
        self.agents.append(agent_id)

    def run(self, max_ticks, verbose):
        raise RuntimeError("simulated mid-run engine failure")


def test_vm_engine_failure_leaves_no_partial_replay(tmp_path, monkeypatch):
    replay = tmp_path / "replay.jsonl"
    monkeypatch.setattr("battle_engine.match_service.Kernel", _FailOnRunKernel)

    with pytest.raises(RuntimeError, match="simulated mid-run engine failure"):
        NativeMatchService().run(
            MatchRequest(_config(), _entrants(), 5, replay, False)
        )

    assert not replay.exists()
    assert not list(tmp_path.glob(".replay.jsonl.*.tmp"))


def test_vm_writer_failure_leaves_no_partial_or_temporary_replay(tmp_path, monkeypatch):
    replay = tmp_path / "replay.jsonl"

    class FailingSink:
        def __init__(self, path):
            self.path = path

        def emit(self, record):
            raise OSError("disk unavailable")

        def close(self):
            pass

    monkeypatch.setattr("battle_engine.match_service.JSONLSink", FailingSink)

    with pytest.raises(OSError, match="disk unavailable"):
        NativeMatchService().run(
            MatchRequest(_config(), _entrants(), 5, replay, False)
        )

    assert not replay.exists()
    assert not list(tmp_path.glob(".replay.jsonl.*.tmp"))


def test_vm_stale_prior_artifacts_are_removed_even_when_the_new_run_fails(
    tmp_path, monkeypatch
):
    replay = tmp_path / "replay.jsonl"
    summary = tmp_path / "summary.json"
    result_json = tmp_path / "result.json"
    replay.write_text('{"stale": true}\n', encoding="utf-8")
    summary.write_text('{"stale": true}', encoding="utf-8")
    result_json.write_text('{"stale": true}', encoding="utf-8")

    monkeypatch.setattr("battle_engine.match_service.Kernel", _FailOnRunKernel)

    with pytest.raises(RuntimeError):
        NativeMatchService().run(
            MatchRequest(_config(), _entrants(), 5, replay, False)
        )

    # A failed attempt must not leave the OLD artifacts behind either --
    # they no longer describe anything real once a new attempt was made.
    assert not replay.exists()
    assert not summary.exists()
    assert not result_json.exists()


def test_vm_replay_publication_is_atomic_on_success(tmp_path):
    replay = tmp_path / "replay.jsonl"

    result = NativeMatchService().run(
        MatchRequest(_config(), _entrants(), 5, replay, False)
    )

    assert replay.is_file()
    assert result.result_path is not None and result.result_path.is_file()
    # No leftover temporary file from the write-then-rename sequence.
    assert not list(tmp_path.glob(".replay.jsonl.*.tmp"))
    assert not list(tmp_path.glob(".replay.jsonl.*.canonical.tmp"))


def test_unknown_ruleset_id_fails_closed_before_any_runtime_executes(tmp_path, monkeypatch):
    """A Ruleset that fails to resolve must abort before any gameplay runs.

    Simulates a future ``resolve_ruleset_policy`` rejecting the currently
    frozen ID (the resolver itself is fail-closed by construction -- see
    ``test_ruleset_policy.py``); this proves the *call site* on the native
    match boundary is on the critical path before ``Kernel``/entrant
    construction, not merely available and unused. No replay/result
    artifact is written, matching every other pre-execution rejection in
    this file.
    """

    replay = tmp_path / "replay.jsonl"

    def _fail_resolution(ruleset_id: str) -> None:
        raise UnknownRulesetError(ruleset_id)

    monkeypatch.setattr("battle_engine.match_service.resolve_ruleset_policy", _fail_resolution)

    with pytest.raises(UnknownRulesetError):
        NativeMatchService().run(
            MatchRequest(_config(), _entrants(), 5, replay, False)
        )

    assert not replay.exists()
    assert not replay.with_name("result.json").exists()
    assert not replay.with_name("summary.json").exists()


def test_vm_canonicalization_failure_leaves_no_artifacts(tmp_path, monkeypatch):
    replay = tmp_path / "replay.jsonl"
    summary = tmp_path / "summary.json"

    def fail_write(_path, _records):
        raise OSError("canonical write failed")

    monkeypatch.setattr("battle_engine.match_service.write_replay", fail_write)

    with pytest.raises(OSError, match="canonical write failed"):
        NativeMatchService().run(
            MatchRequest(_config(), _entrants(), 5, replay, False)
        )

    assert not replay.exists()
    assert not summary.exists()
    assert not replay.with_name("result.json").exists()
    assert not list(tmp_path.glob(".replay.jsonl.*.tmp"))
    assert not list(tmp_path.glob(".replay.jsonl.*.canonical.tmp"))
