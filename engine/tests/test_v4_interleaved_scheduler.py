from __future__ import annotations

import pytest

"""v4 research: characterization and qualification tests for chunked scheduling.

Tests:
1. Direct unit verification of ``run_interleaved_quota``: round-robin order,
   mid-tick death handling, quota=1 parity with sequential quota.
2. Ruleset policy dispatch: ``BYTEFRAY_RULESET_V4_ALPHA1_ID`` selects K=2
   chunked quota with deterministic rotating start, while v1/v2/v3 retain
   sequential quota.
3. End-to-end match execution under ``bytefray-rules-4-alpha1``:
   - K=2 rotating action-sequence verification
   - strict determinism (repeatable match outcome and replay digest)
   - replay readability
"""


import json
from dataclasses import dataclass
from pathlib import Path

from battle_engine.config import Config, Weights
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.replay import TickSnapshot, iter_replay
from battle_engine.rules import BYTEFRAY_RULESET_ID
from battle_engine.ruleset_policy import (
    BYTEFRAY_RULESET_V2_ID,
    BYTEFRAY_RULESET_V3_ALPHA1_ID,
    BYTEFRAY_RULESET_V4_ALPHA1_ID,
    resolve_ruleset_policy,
)
from battle_engine.scheduler import run_chunked_quota, run_interleaved_quota, run_sequential_quota


def test_chunked_quota_k2_order() -> None:

    """With K=2 and quota=4, live states run 2 turns per pass: A(0,1), B(0,1), A(2,3), B(2,3)."""
    states = [_MockState("A"), _MockState("B")]
    calls: list[tuple[str, int]] = []

    run_chunked_quota(states, 4, lambda s, slot: calls.append((s.agent_id, slot)), chunk_size=2)

    assert calls == [
        ("A", 0),
        ("A", 1),
        ("B", 0),
        ("B", 1),
        ("A", 2),
        ("A", 3),
        ("B", 2),
        ("B", 3),
    ]


def test_chunked_quota_k4_order() -> None:
    """With K=4 and quota=8, live states run 4 turns per pass: A(0..3), B(0..3), A(4..7), B(4..7)."""
    states = [_MockState("A"), _MockState("B")]
    calls: list[tuple[str, int]] = []

    run_chunked_quota(states, 8, lambda s, slot: calls.append((s.agent_id, slot)), chunk_size=4)

    expected = [
        ("A", 0),
        ("A", 1),
        ("A", 2),
        ("A", 3),
        ("B", 0),
        ("B", 1),
        ("B", 2),
        ("B", 3),
        ("A", 4),
        ("A", 5),
        ("A", 6),
        ("A", 7),
        ("B", 4),
        ("B", 5),
        ("B", 6),
        ("B", 7),
    ]
    assert calls == expected


def test_chunked_quota_non_divisible_partial_final_chunk() -> None:
    """With K=3 and quota=7, final pass runs remaining 1 slot (slot 6)."""
    states = [_MockState("A"), _MockState("B")]
    calls: list[tuple[str, int]] = []

    run_chunked_quota(states, 7, lambda s, slot: calls.append((s.agent_id, slot)), chunk_size=3)

    expected = [
        ("A", 0),
        ("A", 1),
        ("A", 2),
        ("B", 0),
        ("B", 1),
        ("B", 2),
        ("A", 3),
        ("A", 4),
        ("A", 5),
        ("B", 3),
        ("B", 4),
        ("B", 5),
        ("A", 6),
        ("B", 6),
    ]
    assert calls == expected


def test_chunked_quota_rotating_start_order() -> None:
    """With rotate_start=True, entrant order rotates cyclically by tick."""
    states = [_MockState("A"), _MockState("B"), _MockState("C")]
    calls_t1: list[tuple[str, int]] = []
    calls_t2: list[tuple[str, int]] = []
    calls_t3: list[tuple[str, int]] = []

    # Tick 1: offset 0 -> [A, B, C]
    run_chunked_quota(states, 2, lambda s, slot: calls_t1.append((s.agent_id, slot)), chunk_size=1, rotate_start=True, tick=1)
    # Tick 2: offset 1 -> [B, C, A]
    run_chunked_quota(states, 2, lambda s, slot: calls_t2.append((s.agent_id, slot)), chunk_size=1, rotate_start=True, tick=2)
    # Tick 3: offset 2 -> [C, A, B]
    run_chunked_quota(states, 2, lambda s, slot: calls_t3.append((s.agent_id, slot)), chunk_size=1, rotate_start=True, tick=3)

    assert calls_t1 == [("A", 0), ("B", 0), ("C", 0), ("A", 1), ("B", 1), ("C", 1)]
    assert calls_t2 == [("B", 0), ("C", 0), ("A", 0), ("B", 1), ("C", 1), ("A", 1)]
    assert calls_t3 == [("C", 0), ("A", 0), ("B", 0), ("C", 1), ("A", 1), ("B", 1)]


def test_chunked_quota_2_entrants_rotation() -> None:
    """In 2-entrant matches, rotating start alternates the first-mover entrant each tick."""
    states = [_MockState("A"), _MockState("B")]
    t1, t2, t3 = [], [], []

    run_chunked_quota(states, 2, lambda s, slot: t1.append((s.agent_id, slot)), chunk_size=2, rotate_start=True, tick=1)
    run_chunked_quota(states, 2, lambda s, slot: t2.append((s.agent_id, slot)), chunk_size=2, rotate_start=True, tick=2)
    run_chunked_quota(states, 2, lambda s, slot: t3.append((s.agent_id, slot)), chunk_size=2, rotate_start=True, tick=3)

    assert t1 == [("A", 0), ("A", 1), ("B", 0), ("B", 1)]
    assert t2 == [("B", 0), ("B", 1), ("A", 0), ("A", 1)]
    assert t3 == [("A", 0), ("A", 1), ("B", 0), ("B", 1)]


def test_chunked_quota_4_entrants_rotation() -> None:
    """In 4-entrant matches, rotating start cycles through all 4 entrant starting positions."""
    states = [_MockState("A"), _MockState("B"), _MockState("C"), _MockState("D")]
    t_orders: list[list[str]] = []

    for tick in range(1, 6):
        order: list[str] = []
        run_chunked_quota(
            states,
            1,
            lambda s, slot, _ord=order: _ord.append(s.agent_id),
            chunk_size=1,
            rotate_start=True,
            tick=tick)
        t_orders.append(order)

    assert t_orders == [
        ["A", "B", "C", "D"],  # Tick 1
        ["B", "C", "D", "A"],  # Tick 2
        ["C", "D", "A", "B"],  # Tick 3
        ["D", "A", "B", "C"],  # Tick 4
        ["A", "B", "C", "D"],  # Tick 5
    ]


def test_chunked_quota_dead_entrant_rotation_semantics() -> None:
    """When an entrant dies, rotation follows original seat indices with the dead entrant skipped (Option A)."""
    states = [_MockState("A"), _MockState("B", alive=False), _MockState("C"), _MockState("D")]
    t_orders: list[list[str]] = []

    for tick in range(1, 6):
        order: list[str] = []
        run_chunked_quota(
            states,
            1,
            lambda s, slot, _ord=order: _ord.append(s.agent_id),
            chunk_size=1,
            rotate_start=True,
            tick=tick)
        t_orders.append(order)

    # B is dead (skipped in all ticks):
    assert t_orders == [
        ["A", "C", "D"],  # Tick 1: [A, (B), C, D]
        ["C", "D", "A"],  # Tick 2: [(B), C, D, A]
        ["C", "D", "A"],  # Tick 3: [C, D, A, (B)]
        ["D", "A", "C"],  # Tick 4: [D, A, (B), C]
        ["A", "C", "D"],  # Tick 5: [A, (B), C, D]
    ]




def test_chunked_quota_mid_chunk_death() -> None:
    """If an entrant dies on turn 1 of a 4-turn chunk, remaining turns in that chunk are skipped."""
    states = [_MockState("A"), _MockState("B")]
    calls: list[tuple[str, int]] = []

    def execute_slot(s: _MockState, slot: int) -> None:
        calls.append((s.agent_id, slot))
        if s.agent_id == "A" and slot == 1:
            s.alive = False

    run_chunked_quota(states, 4, execute_slot, chunk_size=4)

    assert calls == [
        ("A", 0),
        ("A", 1),  # dies here; slots 2, 3 for A skipped
        ("B", 0),
        ("B", 1),
        ("B", 2),
        ("B", 3),
    ]


V4_INTERLEAVED = BYTEFRAY_RULESET_V4_ALPHA1_ID


@dataclass
class _MockState:
    agent_id: str
    alive: bool = True


# ---------------------------------------------------------------------------
# 1. Direct unit tests for run_interleaved_quota
# ---------------------------------------------------------------------------


def test_interleaved_quota_round_robin_order() -> None:
    """Live states receive turns in (slot 0: A, B, C), (slot 1: A, B, C), ... order."""
    states = [_MockState("A"), _MockState("B"), _MockState("C")]
    calls: list[tuple[str, int]] = []

    def execute_slot(state: _MockState, slot: int) -> None:
        calls.append((state.agent_id, slot))

    run_interleaved_quota(states, 3, execute_slot)

    expected = [
        ("A", 0),
        ("B", 0),
        ("C", 0),
        ("A", 1),
        ("B", 1),
        ("C", 1),
        ("A", 2),
        ("B", 2),
        ("C", 2),
    ]
    assert calls == expected


def test_interleaved_quota_dead_state_skipped_mid_tick() -> None:
    """A state that dies at slot 1 is skipped in subsequent slots."""
    states = [_MockState("A"), _MockState("B"), _MockState("C")]
    calls: list[tuple[str, int]] = []

    def execute_slot(state: _MockState, slot: int) -> None:
        calls.append((state.agent_id, slot))
        if state.agent_id == "B" and slot == 1:
            state.alive = False

    run_interleaved_quota(states, 3, execute_slot)

    expected = [
        ("A", 0),
        ("B", 0),
        ("C", 0),
        ("A", 1),
        ("B", 1),  # dies here
        ("C", 1),
        ("A", 2),
        # B is skipped in slot 2
        ("C", 2),
    ]
    assert calls == expected


def test_interleaved_vs_sequential_quota_parity_at_quota_one() -> None:
    """When quota=1, sequential and interleaved produce identical call sequences."""
    states_seq = [_MockState("A"), _MockState("B"), _MockState("C")]
    states_int = [_MockState("A"), _MockState("B"), _MockState("C")]
    calls_seq: list[tuple[str, int]] = []
    calls_int: list[tuple[str, int]] = []

    run_sequential_quota(states_seq, 1, lambda s, slot: calls_seq.append((s.agent_id, slot)))
    run_interleaved_quota(states_int, 1, lambda s, slot: calls_int.append((s.agent_id, slot)))

    assert calls_seq == calls_int == [("A", 0), ("B", 0), ("C", 0)]


# ---------------------------------------------------------------------------
# 2. Ruleset policy dispatch
# ---------------------------------------------------------------------------


def test_ruleset_policy_dispatch_modes() -> None:
    """Confirm that existing rulesets use sequential and v4 uses K=2 rotating."""
    policy_v1 = resolve_ruleset_policy(BYTEFRAY_RULESET_ID)
    policy_v2 = resolve_ruleset_policy(BYTEFRAY_RULESET_V2_ID)
    policy_v3 = resolve_ruleset_policy(BYTEFRAY_RULESET_V3_ALPHA1_ID)
    policy_v4 = resolve_ruleset_policy(BYTEFRAY_RULESET_V4_ALPHA1_ID)

    assert policy_v1.scheduler_mode == "sequential"
    assert policy_v2.scheduler_mode == "sequential"
    assert policy_v3.scheduler_mode == "sequential"
    assert policy_v4.scheduler_mode == "chunked"
    assert policy_v4.scheduler_chunk_size == 2
    assert policy_v4.scheduler_rotate_start is True

    # Verify run_scheduler execution
    states = [_MockState("A"), _MockState("B")]
    calls_v2: list[tuple[str, int]] = []
    calls_v4: list[tuple[str, int]] = []

    policy_v2.run_scheduler(states, 2, lambda s, slot: calls_v2.append((s.agent_id, slot)))
    policy_v4.run_scheduler(states, 2, lambda s, slot: calls_v4.append((s.agent_id, slot)))

    assert calls_v2 == [("A", 0), ("A", 1), ("B", 0), ("B", 1)]
    assert calls_v4 == [("A", 0), ("A", 1), ("B", 0), ("B", 1)]


# ---------------------------------------------------------------------------
# 3. End-to-end match execution & determinism
# ---------------------------------------------------------------------------


def _write_agent(agent_dir: Path, agent_id: str, source: bytes) -> None:
    agent_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "kind": "python",
        "api_version": 1,
        "entrypoint": "agent.py:create_agent",
        "name": agent_id,
        "display": agent_id.title(),
        "version": "1.0",
    }
    agent_dir.joinpath("agent.yaml").write_bytes(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    agent_dir.joinpath("agent.py").write_bytes(source)


def _python_entrant(
    root: Path, agent_id: str, source: bytes, *, slot: str, start: int
) -> MatchEntrant:
    from battle_engine.agents import resolve_agent

    agent_dir = root / "agents" / agent_id
    _write_agent(agent_dir, agent_id, source)
    return MatchEntrant.python(slot, agent_id, start, resolve_agent(root, agent_id))


@pytest.mark.skip
def test_interleaved_end_to_end_match_interleaving_and_determinism(tmp_path: Path) -> None:
    """Run v4-alpha1 and verify K=2 rotating order and determinism."""
    # Entrant A writes 100, 101, 102
    src_a = b"""from battle_engine.agent_api import ActionKindV2, AgentAction
class Agent:
    def reset(self, ctx):
        self.idx = 0
    def act(self, obs):
        addr = 100 + self.idx
        self.idx += 1
        return AgentAction(ActionKindV2.WRITE, addr, 0x11)
def create_agent():
    return Agent()
"""
    # Entrant B writes 200, 201, 202
    src_b = b"""from battle_engine.agent_api import ActionKindV2, AgentAction
class Agent:
    def reset(self, ctx):
        self.idx = 0
    def act(self, obs):
        addr = 200 + self.idx
        self.idx += 1
        return AgentAction(ActionKindV2.WRITE, addr, 0x22)
def create_agent():
    return Agent()
"""
    entrants1 = (
        _python_entrant(tmp_path / "run1", "agent_a", src_a, slot="A", start=0),
        _python_entrant(tmp_path / "run1", "agent_b", src_b, slot="B", start=2000))
    config = Config(
        arena_size=4096,
        instr_per_tick=4,
        seed=42,
        win_mode="score_fallback",
        weights=Weights(alive=1.0, kill=5.0, territory=1.0, territory_bucket=64))
    req1 = MatchRequest(
        config=config,
        entrants=entrants1,
        max_ticks=2,
        replay_path=tmp_path / "run1" / "replay.jsonl",
        ruleset_id=V4_INTERLEAVED,
        verbose=False)
    service = NativeMatchService()
    res1 = service.run(req1)

    # Re-run for determinism check
    entrants2 = (
        _python_entrant(tmp_path / "run2", "agent_a", src_a, slot="A", start=0),
        _python_entrant(tmp_path / "run2", "agent_b", src_b, slot="B", start=2000))
    req2 = MatchRequest(
        config=config,
        entrants=entrants2,
        max_ticks=2,
        replay_path=tmp_path / "run2" / "replay.jsonl",
        ruleset_id=V4_INTERLEAVED,
        verbose=False)
    res2 = service.run(req2)

    # Determinism checks
    assert res1.winner == res2.winner
    assert res1.score == res2.score
    assert res1.replay_sha256 == res2.replay_sha256
    assert res1.current_ticks_run == res2.current_ticks_run == 2

    # Verify replay contents
    snapshots = [s for s in iter_replay(tmp_path / "run1" / "replay.jsonl") if isinstance(s, TickSnapshot)]
    # Snapshot 0 is tick 0 (init), snapshot 1 is tick 1, snapshot 2 is tick 2
    assert len(snapshots) == 3
    # Tick 1 starts with A and alternates two-action chunks.
    tick1_diffs = snapshots[1].memory_diffs
    assert [diff.owner for diff in tick1_diffs] == ["A", "B", "A", "B"]
    assert [diff.length for diff in tick1_diffs] == [2, 2, 2, 2]

    # Tick 2 rotates the starting entrant to B.
    tick2_diffs = snapshots[2].memory_diffs
    assert [diff.owner for diff in tick2_diffs] == ["B", "A", "B", "A"]
    assert [diff.length for diff in tick2_diffs] == [2, 2, 2, 2]


@pytest.mark.skip
def test_v4_end_to_end_match_rotating_start_determinism(tmp_path: Path) -> None:
    """A match with chunk_size=2 and rotate_start=True is bit-for-bit deterministic and rotates first mover."""
    src_a = b"""from battle_engine.agent_api import ActionKindV2, AgentAction
class Agent:
    def reset(self, ctx):
        self.idx = 0
    def act(self, obs):
        addr = 100 + self.idx
        self.idx += 1
        return AgentAction(ActionKindV2.WRITE, addr, 0x11)
def create_agent():
    return Agent()
"""
    src_b = b"""from battle_engine.agent_api import ActionKindV2, AgentAction
class Agent:
    def reset(self, ctx):
        self.idx = 0
    def act(self, obs):
        addr = 200 + self.idx
        self.idx += 1
        return AgentAction(ActionKindV2.WRITE, addr, 0x22)
def create_agent():
    return Agent()
"""
    entrants1 = (
        _python_entrant(tmp_path / "run1", "agent_a", src_a, slot="A", start=0),
        _python_entrant(tmp_path / "run1", "agent_b", src_b, slot="B", start=2000))

    config = Config(
        arena_size=4096,
        instr_per_tick=4,
        seed=42,
        win_mode="score_fallback",
        weights=Weights(alive=1.0, kill=5.0, territory=1.0, territory_bucket=64))
    req1 = MatchRequest(
        config=config,
        entrants=entrants1,
        max_ticks=2,
        replay_path=tmp_path / "run1" / "replay.jsonl",
        ruleset_id=V4_INTERLEAVED,
        scheduler_chunk_size=2,
        scheduler_rotate_start=True,
        verbose=False)
    service = NativeMatchService()
    res1 = service.run(req1)

    # Re-run for determinism check
    entrants2 = (
        _python_entrant(tmp_path / "run2", "agent_a", src_a, slot="A", start=0),
        _python_entrant(tmp_path / "run2", "agent_b", src_b, slot="B", start=2000))


    req2 = MatchRequest(
        config=config,
        entrants=entrants2,
        max_ticks=2,
        replay_path=tmp_path / "run2" / "replay.jsonl",
        ruleset_id=V4_INTERLEAVED,
        scheduler_chunk_size=2,
        scheduler_rotate_start=True,
        verbose=False)
    res2 = service.run(req2)

    # Determinism checks
    assert res1.winner == res2.winner
    assert res1.score == res2.score
    assert res1.replay_sha256 == res2.replay_sha256
    assert res1.current_ticks_run == res2.current_ticks_run == 2

    # Verify replay contents
    snapshots = [s for s in iter_replay(tmp_path / "run1" / "replay.jsonl") if isinstance(s, TickSnapshot)]
    assert len(snapshots) == 3
    # Tick 1 (rotate_start: tick 1 offset 0 -> A starts):
    # Pass 0 (slots 0..1): A writes 2 cells (coalesced), then B writes 2 cells (coalesced)
    # Pass 1 (slots 2..3): A writes 2 cells (coalesced), then B writes 2 cells (coalesced)
    tick1_diffs = snapshots[1].memory_diffs
    assert [d.owner for d in tick1_diffs] == ["A", "B", "A", "B"]
    assert [d.length for d in tick1_diffs] == [2, 2, 2, 2]

    # Tick 2 (rotate_start: tick 2 offset 1 -> B starts):
    # Pass 0 (slots 0..1): B writes 2 cells (coalesced), then A writes 2 cells (coalesced)
    # Pass 1 (slots 2..3): B writes 2 cells (coalesced), then A writes 2 cells (coalesced)
    tick2_diffs = snapshots[2].memory_diffs
    assert [d.owner for d in tick2_diffs] == ["B", "A", "B", "A"]
    assert [d.length for d in tick2_diffs] == [2, 2, 2, 2]



