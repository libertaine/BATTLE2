"""End-to-end Agent Lab tests: determinism and replay/trace correlation.

Runs real matches through :class:`~battle_engine.match_service.NativeMatchService`
-- the exact production boundary -- rather than driving the runtime
classes directly, so these tests prove the properties an agent author
actually depends on: supervised and unsupervised runs of the same input
produce the same match, and a trace's decision ticks line up with the
canonical replay's tick records the way ``docs/specs/agent_lab.md`` §5
promises.
"""

from __future__ import annotations

import json
from pathlib import Path

from _hang_safety import hang_safety_timeout
from battle_engine.agent_trace import read_trace
from battle_engine.agents import resolve_agent
from battle_engine.config import Config
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.replay import TickSnapshot, iter_replay

DETERMINISTIC_SOURCE = """
from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        self.n = 0

    def act(self, observation):
        self.n += 1
        return AgentAction(ActionKind.WRITE, self.n % 4096, self.n % 256)

def create_agent():
    return Agent()
"""

FORFEITS_AT_TICK_3_SOURCE = """
from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        pass

    def act(self, observation):
        if observation.tick == 3:
            raise RuntimeError("scripted failure")
        return AgentAction(ActionKind.NOP)

def create_agent():
    return Agent()
"""


def _spec(root: Path, name: str, source: str):
    directory = root / "agents" / name
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text(
        json.dumps(
            {"kind": "python", "api_version": 1, "entrypoint": "agent.py:create_agent", "version": "1.0"}
        ),
        encoding="utf-8",
    )
    (directory / "agent.py").write_text(source, encoding="utf-8")
    return resolve_agent(root, name)


def _run(
    tmp_path: Path,
    label: str,
    *,
    source_a: str = DETERMINISTIC_SOURCE,
    source_b: str = DETERMINISTIC_SOURCE,
    agent_call_timeout: float | None,
    ticks: int = 15,
):
    entrants = (
        MatchEntrant.python("A", "a", 0, _spec(tmp_path, f"{label}_a", source_a)),
        MatchEntrant.python("B", "b", 0, _spec(tmp_path, f"{label}_b", source_b)),
    )
    replay_path = tmp_path / label / "replay.jsonl"
    trace_path = tmp_path / label / "trace.jsonl"
    request = MatchRequest(
        config=Config(seed=1337),
        entrants=entrants,
        max_ticks=ticks,
        replay_path=replay_path,
        verbose=False,
        trace_path=trace_path,
        agent_call_timeout=agent_call_timeout,
    )
    result = NativeMatchService().run(request)
    return result, replay_path, trace_path


def _replay_records_excluding_timing(path: Path) -> list:
    """Replay content has no wall-clock/PID fields, so a plain equality
    check (once records are namedtuple-like dataclasses) is exactly the
    right determinism bar -- no exclusions actually needed, but the
    ticks are read into a list for a clear diff on failure."""

    return list(iter_replay(path))


def test_supervised_and_unsupervised_produce_identical_replay(tmp_path: Path) -> None:
    with hang_safety_timeout(60):
        unsupervised_result, unsupervised_replay, _ = _run(
            tmp_path, "unsupervised", agent_call_timeout=None
        )
        supervised_result, supervised_replay, _ = _run(
            tmp_path, "supervised", agent_call_timeout=5.0
        )

    assert unsupervised_result.winner == supervised_result.winner
    assert unsupervised_result.termination_reason == supervised_result.termination_reason
    assert unsupervised_result.score == supervised_result.score
    assert unsupervised_result.match_id == supervised_result.match_id
    assert unsupervised_result.result_id == supervised_result.result_id
    assert unsupervised_result.replay_sha256 == supervised_result.replay_sha256

    unsupervised_records = _replay_records_excluding_timing(unsupervised_replay)
    supervised_records = _replay_records_excluding_timing(supervised_replay)
    assert unsupervised_records == supervised_records


def test_two_supervised_runs_of_same_input_do_not_diverge(tmp_path: Path) -> None:
    with hang_safety_timeout(60):
        _, _, trace_a = _run(tmp_path, "run_a", agent_call_timeout=5.0)
        _, _, trace_b = _run(tmp_path, "run_b", agent_call_timeout=5.0)

    from battle_engine.agent_trace import first_divergence

    divergence = first_divergence(read_trace(trace_a), read_trace(trace_b))
    assert divergence is None


def test_trace_decision_tick_matches_replay_forfeit_tick(tmp_path: Path) -> None:
    """Prove the tick-meaning contract in docs/specs/agent_lab.md §5:
    a trace decision's diagnostic at tick N corresponds to the forfeit
    RuntimeEvent recorded in the canonical replay's TickSnapshot N for the
    same agent -- not N-1 or N+1."""

    with hang_safety_timeout(60):
        _result, replay_path, trace_path = _run(
            tmp_path, "correlation",
            source_a=FORFEITS_AT_TICK_3_SOURCE, source_b=DETERMINISTIC_SOURCE,
            agent_call_timeout=5.0, ticks=10,
        )

    document = read_trace(trace_path)
    failing_decisions = [d for d in document.decisions if d.diagnostic is not None]
    assert len(failing_decisions) == 1
    assert failing_decisions[0].tick == 3
    assert failing_decisions[0].agent_id == "A"
    assert failing_decisions[0].diagnostic.code == "agent_action_failed"

    forfeit_ticks = []
    for record in iter_replay(replay_path):
        if isinstance(record, TickSnapshot):
            for event in record.events:
                if getattr(event, "event_type", None) == "forfeit" and event.victim == "A":
                    forfeit_ticks.append(record.tick)
    assert forfeit_ticks == [3]


WRITES_ADDRESS_7_ON_TICK_2_SOURCE = """
from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        pass

    def act(self, observation):
        if observation.tick == 2:
            return AgentAction(ActionKind.WRITE, 7, 99)
        return AgentAction(ActionKind.NOP)

def create_agent():
    return Agent()
"""


def test_trace_write_decision_tick_matches_replay_memory_diff_tick(tmp_path: Path) -> None:
    """A second, success-path correlation case alongside the forfeit one
    above: a trace decision recording a successful WRITE action at tick N
    corresponds to the *same* tick N's canonical replay MemoryDiff -- the
    tick a decision is recorded under already reflects that tick's
    post-action engine state (docs/specs/agent_lab.md §5's documented
    before/after semantics), not tick N-1 or N+1.
    """

    with hang_safety_timeout(60):
        _result, replay_path, trace_path = _run(
            tmp_path, "write_correlation",
            source_a=WRITES_ADDRESS_7_ON_TICK_2_SOURCE, source_b=DETERMINISTIC_SOURCE,
            agent_call_timeout=5.0, ticks=5,
        )

    document = read_trace(trace_path)
    # The agent repeats the same WRITE for every action slot of tick 2
    # (the default action budget is 8 per tick), so several identical
    # decision records are expected -- what matters for tick-correlation
    # is that every one of them is recorded under tick 2, never 1 or 3.
    write_decisions = [
        d for d in document.decisions
        if d.agent_id == "A" and d.action is not None and d.action.kind == "write"
    ]
    assert write_decisions
    assert {d.tick for d in write_decisions} == {2}
    assert all(d.action.operand == 7 and d.action.value == 99 for d in write_decisions)

    diff_ticks_for_address_7 = []
    for record in iter_replay(replay_path):
        if isinstance(record, TickSnapshot):
            for diff in record.memory_diffs:
                if diff.address == 7 and diff.owner == "A":
                    diff_ticks_for_address_7.append(record.tick)
    assert diff_ticks_for_address_7
    assert set(diff_ticks_for_address_7) == {2}
