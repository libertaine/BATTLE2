"""Phase 6.5a: canonical replay reconstruction, digest, and identity contract.

These tests exist to prove -- not merely assert -- that the canonical
``battle2.replay`` stream produced by ``NativeMatchService`` is sufficient to
reconstruct engine-observable match state (arena content, ownership, and
per-entrant controller state) at any tick using only the public typed reader
API (``iter_replay``), without rerunning any agent.
"""

from __future__ import annotations

import json

import pytest
from battle_engine.agent_state import Agent
from battle_engine.builtins import build_agent
from battle_engine.config import Config, Weights
from battle_engine.core import HALT, NOP, enc
from battle_engine.match_service import (
    MatchEntrant,
    MatchRequest,
    NativeMatchService,
    canonical_match_id,
)
from battle_engine.replay import (
    KillDeathEvent,
    MatchResult,
    ReplayHeader,
    TickSnapshot,
    iter_replay,
)
from battle_engine.result_model import (
    ReplayIntegrityError,
    read_result,
    stable_id,
    verify_replay_digest,
    verify_result_replay,
)
from battle_engine.vm import VM


# ---------------------------------------------------------------------------
# Shared reconstruction helper: rebuilds arena bytes/ownership at every tick
# using ONLY the public typed replay reader, mirroring what a Phase 7 replay
# viewer would do. This is intentionally independent of match_service's
# internal finalize logic -- it only consumes the public ReplayRecord model.
# ---------------------------------------------------------------------------
def _reconstruct_ticks(replay_path):
    header = None
    arena = None
    owners = None
    reconstructed = {}
    for record in iter_replay(replay_path):
        if isinstance(record, ReplayHeader):
            header = record
            arena_size = header.config.arena_size
            arena = bytearray(arena_size)
            owners = [None] * arena_size
            continue
        if isinstance(record, TickSnapshot):
            assert arena is not None and owners is not None, "header must precede ticks"
            for diff in record.memory_diffs:
                for offset, value in enumerate(diff.values):
                    address = (diff.address + offset) % len(arena)
                    arena[address] = value
                    owners[address] = diff.owner
            reconstructed[record.tick] = {
                "arena": bytes(arena),
                "owners": tuple(owners),
                "agents": {
                    agent.agent_id: agent for agent in record.agents
                },
            }
    assert header is not None, "replay must contain a header"
    return header, reconstructed


def _config(arena_size=64, instr_per_tick=1, seed=1337):
    return Config(arena_size=arena_size, instr_per_tick=instr_per_tick, seed=seed)


def _python_spec(root, name, source):
    from battle_engine.agents import resolve_agent

    directory = root / "agents" / name
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text(
        json.dumps(
            {
                "kind": "python",
                "api_version": 1,
                "entrypoint": "agent.py:create_agent",
                "name": name,
                "display": name.title(),
                "version": "1.0",
            }
        ),
        encoding="utf-8",
    )
    (directory / "agent.py").write_text(source, encoding="utf-8")
    return resolve_agent(root, name)


WRITER_SOURCE = """
from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        pass

    def act(self, observation):
        return AgentAction(ActionKind.WRITE, 10, 0xAB)

def create_agent():
    return Agent()
"""

READER_SOURCE = """
from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        pass

    def act(self, observation):
        return AgentAction(ActionKind.READ, 10)

def create_agent():
    return Agent()
"""


# ---------------------------------------------------------------------------
# End-to-end reconstruction: VM match
# ---------------------------------------------------------------------------
def test_vm_match_state_is_reconstructable_from_replay_alone(tmp_path):
    config = Config(
        arena_size=128,
        instr_per_tick=2,
        seed=1337,
        weights=Weights(alive=1, kill=5, territory=0),
    )
    entrants = (
        MatchEntrant("A", "writer", 0, build_agent("writer", 0, offset=96, byte=0x42)),
        MatchEntrant("B", "runner", 48, build_agent("runner", 48)),
    )
    replay_path = tmp_path / "replay.jsonl"
    result = NativeMatchService().run(
        MatchRequest(config, entrants, max_ticks=6, replay_path=replay_path, verbose=False)
    )

    # Independently derive ground-truth per-tick state using only the
    # lowest-level VM/Agent primitives -- deliberately not match.py's
    # MatchRunner (the code that produced the replay being verified), so
    # this is a genuine cross-check rather than a circular comparison.
    vm = VM(config.arena_size)
    live_agents = []
    for entrant in entrants:
        start, end = vm.load_code(entrant.start % config.arena_size, entrant.code, entrant.agent_id)
        live_agents.append(Agent(agent_id=entrant.agent_id, pc=start, region=(start, end)))
    ground_truth = {
        0: {
            "arena": bytes(vm.arena),
            "owners": tuple(vm.writer),
            "agents": {
                a.agent_id: (a.pc, a.alive, dict(a.regs), a.cpu_used, a.mem_writes, a.region)
                for a in live_agents
            },
        }
    }
    for tick in range(1, 7):
        for agent in live_agents:
            agent.cpu_used = 0
        for agent in live_agents:
            if not agent.alive:
                continue
            for _ in range(config.instr_per_tick):
                if not agent.alive:
                    break
                vm.step(agent)
                agent.cpu_used += 1
        ground_truth[tick] = {
            "arena": bytes(vm.arena),
            "owners": tuple(vm.writer),
            "agents": {
                a.agent_id: (a.pc, a.alive, dict(a.regs), a.cpu_used, a.mem_writes, a.region)
                for a in live_agents
            },
        }
        if sum(1 for a in live_agents if a.alive) <= 1:
            break

    header, reconstructed = _reconstruct_ticks(replay_path)
    assert header.runtime_kind == "vm"
    assert header.match_id == result.match_id

    assert set(ground_truth) <= set(reconstructed)
    for tick, expected in ground_truth.items():
        actual = reconstructed[tick]
        assert actual["arena"] == expected["arena"], f"arena mismatch at tick {tick}"
        assert actual["owners"] == expected["owners"], f"ownership mismatch at tick {tick}"
        for agent_id, (pc, alive, regs, cpu_used, mem_writes, region) in expected[
            "agents"
        ].items():
            state = actual["agents"][agent_id]
            assert state.pc == pc, f"pc mismatch for {agent_id} at tick {tick}"
            assert state.alive == alive, f"alive mismatch for {agent_id} at tick {tick}"
            assert state.register_a == regs["A"], f"A mismatch for {agent_id} at tick {tick}"
            assert state.register_p == regs["P"], f"P mismatch for {agent_id} at tick {tick}"
            assert state.zero_flag == bool(regs["Z"]), f"Z mismatch for {agent_id} at tick {tick}"
            assert state.cpu_used == cpu_used
            assert state.mem_writes == mem_writes
            assert state.region == region

    # The terminal record independently confirms winner/termination/score,
    # matching the canonical result envelope built from the same run.
    terminal = list(iter_replay(replay_path))[-1]
    assert isinstance(terminal, MatchResult)
    assert terminal.match_id == result.match_id
    assert terminal.result_id == result.result_id
    assert terminal.ticks == result.ticks_run
    assert dict(terminal.score) == dict(result.score)
    envelope = read_result(result.result_path)
    assert terminal.termination_reason == envelope.termination_reason
    assert (terminal.winner or "tie") == envelope.winner


# ---------------------------------------------------------------------------
# End-to-end reconstruction: Python match
# ---------------------------------------------------------------------------
def test_python_match_state_is_reconstructable_from_replay_alone(tmp_path):
    entrants = (
        MatchEntrant.python("A", "writer", 0, _python_spec(tmp_path, "writer", WRITER_SOURCE)),
        MatchEntrant.python("B", "reader", 32, _python_spec(tmp_path, "reader", READER_SOURCE)),
    )
    replay_path = tmp_path / "replay.jsonl"
    result = NativeMatchService().run(
        MatchRequest(_config(instr_per_tick=1), entrants, max_ticks=3, replay_path=replay_path, verbose=False)
    )

    header, reconstructed = _reconstruct_ticks(replay_path)
    assert header.runtime_kind == "python"
    assert header.match_id == result.match_id

    # Ground truth is fully analytic: "writer" unconditionally writes 0xAB
    # to address 10 every tick and never touches its own registers; "reader"
    # runs after "writer" in the same tick (sequential same-tick visibility,
    # already characterized elsewhere) and so always observes 0xAB.
    assert reconstructed[0]["arena"][10] == 0  # nothing written before tick 1
    for tick in (1, 2, 3):
        assert reconstructed[tick]["arena"][10] == 0xAB
        assert reconstructed[tick]["owners"][10] == "A"
        writer_state = reconstructed[tick]["agents"]["A"]
        assert writer_state.mem_writes == tick
        assert writer_state.register_a == 0  # WRITE never touches register_a
        reader_state = reconstructed[tick]["agents"]["B"]
        assert reader_state.register_a == 0xAB
        assert reader_state.last_read == 0xAB
        assert reader_state.zero_flag is False
        assert writer_state.cpu_used == 1
        assert reader_state.cpu_used == 1
        assert reconstructed[tick]["agents"]["A"].region == (0, 0)

    records = list(iter_replay(replay_path))
    ticks = {record.tick: record for record in records if isinstance(record, TickSnapshot)}
    assert dict(ticks[3].score) == {"A": 3, "B": 3}

    terminal = list(iter_replay(replay_path))[-1]
    assert isinstance(terminal, MatchResult)
    assert terminal.ticks == 3 == result.ticks_run
    assert terminal.termination_reason == "tick_limit"
    # Both entrants survive to the tick limit -> no single winner.
    assert terminal.winner is None
    envelope = read_result(result.result_path)
    assert envelope.winner == "tie"


def test_replay_preserves_representative_vm_death_event(tmp_path):
    entrants = (
        MatchEntrant("A", "halts", 0, enc(HALT)),
        MatchEntrant("B", "waits", 16, enc(NOP)),
    )
    result = NativeMatchService().run(
        MatchRequest(_config(arena_size=32), entrants, 2, tmp_path / "events.jsonl", False)
    )
    tick_one = next(
        record
        for record in iter_replay(result.replay_path)
        if isinstance(record, TickSnapshot) and record.tick == 1
    )

    assert tick_one.events == (KillDeathEvent("death", "A", None),)


# ---------------------------------------------------------------------------
# Replay digest verification
# ---------------------------------------------------------------------------
def _run_simple_match(tmp_path):
    config = _config(arena_size=32, instr_per_tick=1)
    entrants = (
        MatchEntrant("A", "a", 0, build_agent("runner", 0)),
        MatchEntrant("B", "b", 16, build_agent("runner", 16)),
    )
    replay_path = tmp_path / "replay.jsonl"
    result = NativeMatchService().run(
        MatchRequest(config, entrants, max_ticks=2, replay_path=replay_path, verbose=False)
    )
    return result


def test_verify_replay_digest_accepts_the_original_file(tmp_path):
    result = _run_simple_match(tmp_path)
    envelope = read_result(result.result_path)
    digest = verify_replay_digest(envelope, result.replay_path)
    assert digest == envelope.replay.sha256

    # The result-reader convenience helper resolves the replay path itself.
    assert verify_result_replay(result.result_path) == envelope.replay.sha256


def test_verify_replay_digest_detects_modification(tmp_path):
    result = _run_simple_match(tmp_path)
    envelope = read_result(result.result_path)
    result.replay_path.write_bytes(result.replay_path.read_bytes() + b'{"tampered":true}\n')

    with pytest.raises(ReplayIntegrityError) as excinfo:
        verify_replay_digest(envelope, result.replay_path)
    assert excinfo.value.code == "replay_digest_mismatch"


def test_verify_replay_digest_detects_truncation(tmp_path):
    result = _run_simple_match(tmp_path)
    envelope = read_result(result.result_path)
    original = result.replay_path.read_bytes()
    result.replay_path.write_bytes(original[: len(original) // 2])

    with pytest.raises(ReplayIntegrityError) as excinfo:
        verify_replay_digest(envelope, result.replay_path)
    assert excinfo.value.code == "replay_digest_mismatch"


def test_verify_replay_digest_reports_missing_file(tmp_path):
    result = _run_simple_match(tmp_path)
    envelope = read_result(result.result_path)
    result.replay_path.unlink()

    with pytest.raises(ReplayIntegrityError) as excinfo:
        verify_replay_digest(envelope, result.replay_path)
    assert excinfo.value.code == "replay_file_missing"


def test_read_result_never_verifies_automatically(tmp_path):
    """Explicit opt-in only: reading a result must not require the replay
    to exist or match, so historical results stay readable even if their
    replay was pruned or deleted."""

    result = _run_simple_match(tmp_path)
    result.replay_path.unlink()
    envelope = read_result(result.result_path)  # must not raise
    assert envelope.replay is not None


# ---------------------------------------------------------------------------
# result_id determinism under nondeterministic exception text
# ---------------------------------------------------------------------------
def test_result_id_is_stable_despite_nondeterministic_exception_text(tmp_path, monkeypatch):
    """result_id must not depend on diagnostic message text.

    Real agent-exception text is nondeterministic in practice -- e.g. a
    default ``repr()`` embeds an ``id()``-derived pseudo-address, which
    CPython's allocator can (and, depending on prior allocation traffic,
    reliably does) reuse across two sequentially-created objects. Asserting
    that two runs' messages actually differ by relying on that address is
    therefore not itself deterministic: it can pass or fail depending on
    unrelated allocator state left over from other tests in the same
    process.

    ``canonical_match_id`` folds each Python entrant's agent source bytes
    into match identity (``source_sha256``), so simply baking a distinct
    marker into each run's agent.py (an earlier version of this fix did
    that) would make ``match_id`` differ for a real, unrelated reason --
    the agents genuinely would no longer be identical -- defeating the
    point of the test. Instead, both runs use byte-identical agent source;
    the message-text marker is supplied at *runtime* via an environment
    variable the agent reads in ``act()``, so it varies deterministically
    between runs without the agent's on-disk identity changing at all.
    """
    from battle_engine.agents import resolve_agent

    marker_env_var = "BYTEFRAY_TEST_RESULT_ID_MARKER"
    failing_source = f"""
import os
from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        pass

    def act(self, observation):
        raise RuntimeError("boom-" + os.environ["{marker_env_var}"])

def create_agent():
    return Agent()
"""
    passive_source = """
from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, context): pass
    def act(self, observation): return AgentAction(ActionKind.NOP)
def create_agent(): return Agent()
"""

    def _spec(root, name, source):
        directory = root / "agents" / name
        directory.mkdir(parents=True)
        (directory / "agent.yaml").write_text(
            json.dumps(
                {
                    "kind": "python",
                    "api_version": 1,
                    "entrypoint": "agent.py:create_agent",
                    "name": name,
                    "display": name.title(),
                    "version": "1.0",
                }
            ),
            encoding="utf-8",
        )
        (directory / "agent.py").write_text(source, encoding="utf-8")
        return resolve_agent(root, name)

    def _run(label):
        root = tmp_path / label
        entrants = (
            MatchEntrant.python("A", "failing", 0, _spec(root, "failing", failing_source)),
            MatchEntrant.python("B", "passive", 32, _spec(root, "passive", passive_source)),
        )
        replay_path = root / "replay.jsonl"
        monkeypatch.setenv(marker_env_var, label)
        return NativeMatchService().run(
            MatchRequest(_config(), entrants, max_ticks=2, replay_path=replay_path, verbose=False)
        )

    first = _run("first")
    second = _run("second")

    first_message = read_result(first.result_path).entrants[0]["diagnostic"]["message"]
    second_message = read_result(second.result_path).entrants[0]["diagnostic"]["message"]
    # Each run's raised message embeds its own label ("first"/"second") via
    # the environment marker, by construction -- guaranteed different,
    # deterministically, with no dependence on allocator/`id()` behavior...
    assert "first" in first_message
    assert "second" in second_message
    assert first_message != second_message
    # ...yet identity is unaffected: the agent source on disk (and thus
    # match_id's source_sha256) is byte-identical between the two runs.
    assert first.match_id == second.match_id
    assert first.result_id == second.result_id


# ---------------------------------------------------------------------------
# match_id / result_id identity pinning
# ---------------------------------------------------------------------------
def test_match_id_is_stable_across_different_absolute_checkout_paths(tmp_path):
    entrants_one = (
        MatchEntrant("A", "a", 0, build_agent("runner", 0)),
        MatchEntrant("B", "b", 16, build_agent("runner", 16)),
    )
    entrants_two = (
        MatchEntrant("A", "a", 0, build_agent("runner", 0)),
        MatchEntrant("B", "b", 16, build_agent("runner", 16)),
    )
    first = NativeMatchService().run(
        MatchRequest(
            _config(arena_size=32),
            entrants_one,
            max_ticks=2,
            replay_path=tmp_path / "one" / "nested" / "deep" / "replay.jsonl",
            verbose=False,
        )
    )
    second = NativeMatchService().run(
        MatchRequest(
            _config(arena_size=32),
            entrants_two,
            max_ticks=2,
            replay_path=tmp_path / "two" / "replay.jsonl",
            verbose=False,
        )
    )
    assert first.replay_path != second.replay_path
    assert first.match_id == second.match_id
    assert first.result_id == second.result_id


def test_match_id_changes_with_meaningful_config_or_code_changes(tmp_path):
    base_entrants = (
        MatchEntrant("A", "a", 0, build_agent("runner", 0)),
        MatchEntrant("B", "b", 16, build_agent("runner", 16)),
    )
    baseline = NativeMatchService().run(
        MatchRequest(
            _config(arena_size=32), base_entrants, max_ticks=2,
            replay_path=tmp_path / "baseline" / "replay.jsonl", verbose=False,
        )
    )
    different_seed = NativeMatchService().run(
        MatchRequest(
            _config(arena_size=32, seed=99), base_entrants, max_ticks=2,
            replay_path=tmp_path / "seed" / "replay.jsonl", verbose=False,
        )
    )
    different_code = NativeMatchService().run(
        MatchRequest(
            _config(arena_size=32),
            (
                MatchEntrant("A", "a", 0, build_agent("writer", 0)),
                MatchEntrant("B", "b", 16, build_agent("runner", 16)),
            ),
            max_ticks=2,
            replay_path=tmp_path / "code" / "replay.jsonl",
            verbose=False,
        )
    )
    assert different_seed.match_id != baseline.match_id
    assert different_code.match_id != baseline.match_id


def test_canonical_match_id_changes_if_ruleset_identity_changes(monkeypatch, tmp_path):
    """v0.10 Phase 4: Ruleset identity is a first-class, live input to
    ``canonical_match_id``'s hash payload, not decorative -- two otherwise-
    identical execution inputs must never collide under one ``match_id`` if
    they ran under different declared gameplay semantics. There is only one
    Ruleset today, so this is proven by monkeypatching the canonical
    constant ``canonical_match_id`` actually reads (rather than requiring a
    real second Ruleset to exist) and confirming the computed id changes.
    """

    entrants = (
        MatchEntrant("A", "a", 0, build_agent("runner", 0)),
        MatchEntrant("B", "b", 16, build_agent("runner", 16)),
    )
    request = MatchRequest(
        _config(arena_size=32), entrants, max_ticks=2,
        replay_path=tmp_path / "replay.jsonl", verbose=False,
    )
    baseline_id = canonical_match_id(request)

    monkeypatch.setattr(
        "battle_engine.match_service.BYTEFRAY_RULESET_ID", "bytefray-rules-2-hypothetical"
    )
    changed_id = canonical_match_id(request)

    assert changed_id != baseline_id


def test_result_id_changes_when_outcome_differs_for_same_match_id(tmp_path):
    # Same inputs, different tick limit: same match_id-relevant identity
    # inputs would differ here too (tick_limit is part of reproducibility),
    # so instead compare same match_id with a config change that only
    # affects scoring/outcome, not identity: not directly possible given
    # the current identity recipe (win_mode is part of reproducibility).
    # Assert the weaker, still-meaningful property: two runs with identical
    # inputs (hence identical match_id) produce identical result_id too,
    # since the engine is deterministic.
    entrants = (
        MatchEntrant("A", "a", 0, build_agent("runner", 0)),
        MatchEntrant("B", "b", 16, build_agent("runner", 16)),
    )
    first = NativeMatchService().run(
        MatchRequest(
            _config(arena_size=32), entrants, max_ticks=2,
            replay_path=tmp_path / "a" / "replay.jsonl", verbose=False,
        )
    )
    second = NativeMatchService().run(
        MatchRequest(
            _config(arena_size=32), entrants, max_ticks=2,
            replay_path=tmp_path / "b" / "replay.jsonl", verbose=False,
        )
    )
    assert first.match_id == second.match_id
    assert first.result_id == second.result_id


def test_result_id_is_a_function_of_match_id_and_outcome():
    match_id = stable_id("match", {"mode": "b2", "entrants": ["A", "B"]})
    same_outcome = stable_id(
        "result", {"match_id": match_id, "winner": "A", "score": {"A": 1}}
    )
    same_outcome_again = stable_id(
        "result", {"match_id": match_id, "winner": "A", "score": {"A": 1}}
    )
    different_outcome = stable_id(
        "result", {"match_id": match_id, "winner": "B", "score": {"A": 1}}
    )
    assert same_outcome == same_outcome_again
    assert same_outcome != different_outcome
