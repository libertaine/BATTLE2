"""v4 research: characterization and qualification tests for interleaved scheduling.

Tests:
1. Direct unit verification of ``run_interleaved_quota``: round-robin order,
   mid-tick death handling, quota=1 parity with sequential quota.
2. Ruleset policy dispatch: ``BYTEFRAY_RULESET_V4_ALPHA1_ID`` dispatches to
   ``run_interleaved_quota`` while all v1/v2/v3 policies retain sequential quota.
3. End-to-end match execution under ``bytefray-rules-4-alpha1``:
   - interleaved action sequence verification
   - strict determinism (repeatable match outcome and replay digest)
   - replay readability
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

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
from battle_engine.scheduler import run_interleaved_quota, run_sequential_quota

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
    """Confirm that existing rulesets use sequential and v4 uses interleaved."""
    policy_v1 = resolve_ruleset_policy(BYTEFRAY_RULESET_ID)
    policy_v2 = resolve_ruleset_policy(BYTEFRAY_RULESET_V2_ID)
    policy_v3 = resolve_ruleset_policy(BYTEFRAY_RULESET_V3_ALPHA1_ID)
    policy_v4 = resolve_ruleset_policy(BYTEFRAY_RULESET_V4_ALPHA1_ID)

    assert policy_v1.scheduler_mode == "sequential"
    assert policy_v2.scheduler_mode == "sequential"
    assert policy_v3.scheduler_mode == "sequential"
    assert policy_v4.scheduler_mode == "interleaved"

    # Verify run_scheduler execution
    states = [_MockState("A"), _MockState("B")]
    calls_v2: list[tuple[str, int]] = []
    calls_v4: list[tuple[str, int]] = []

    policy_v2.run_scheduler(states, 2, lambda s, slot: calls_v2.append((s.agent_id, slot)))
    policy_v4.run_scheduler(states, 2, lambda s, slot: calls_v4.append((s.agent_id, slot)))

    assert calls_v2 == [("A", 0), ("A", 1), ("B", 0), ("B", 1)]
    assert calls_v4 == [("A", 0), ("B", 0), ("A", 1), ("B", 1)]


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


def test_interleaved_end_to_end_match_interleaving_and_determinism(tmp_path: Path) -> None:
    """Run a match under bytefray-rules-4-alpha1 and verify interleaving and determinism."""
    # Entrant A writes 100, 101, 102
    src_a = b"""from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, ctx):
        self.idx = 0
    def act(self, obs):
        addr = 100 + self.idx
        self.idx += 1
        return AgentAction(ActionKind.WRITE, addr, 0x11)
def create_agent():
    return Agent()
"""
    # Entrant B writes 200, 201, 202
    src_b = b"""from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, ctx):
        self.idx = 0
    def act(self, obs):
        addr = 200 + self.idx
        self.idx += 1
        return AgentAction(ActionKind.WRITE, addr, 0x22)
def create_agent():
    return Agent()
"""
    entrants1 = (
        _python_entrant(tmp_path / "run1", "agent_a", src_a, slot="A", start=0),
        _python_entrant(tmp_path / "run1", "agent_b", src_b, slot="B", start=2000),
    )
    config = Config(
        arena_size=4096,
        instr_per_tick=4,
        seed=42,
        win_mode="score_fallback",
        weights=Weights(alive=1.0, kill=5.0, territory=1.0, territory_bucket=64),
    )
    req1 = MatchRequest(
        config=config,
        entrants=entrants1,
        max_ticks=2,
        replay_path=tmp_path / "run1" / "replay.jsonl",
        ruleset_id=V4_INTERLEAVED,
        verbose=False,
    )
    service = NativeMatchService()
    res1 = service.run(req1)

    # Re-run for determinism check
    entrants2 = (
        _python_entrant(tmp_path / "run2", "agent_a", src_a, slot="A", start=0),
        _python_entrant(tmp_path / "run2", "agent_b", src_b, slot="B", start=2000),
    )
    req2 = MatchRequest(
        config=config,
        entrants=entrants2,
        max_ticks=2,
        replay_path=tmp_path / "run2" / "replay.jsonl",
        ruleset_id=V4_INTERLEAVED,
        verbose=False,
    )
    res2 = service.run(req2)

    # Determinism checks
    assert res1.winner == res2.winner
    assert res1.score == res2.score
    assert res1.replay_sha256 == res2.replay_sha256
    assert res1.ticks_run == res2.ticks_run == 2

    # Verify replay contents
    snapshots = [s for s in iter_replay(tmp_path / "run1" / "replay.jsonl") if isinstance(s, TickSnapshot)]
    # Snapshot 0 is tick 0 (init), snapshot 1 is tick 1, snapshot 2 is tick 2
    assert len(snapshots) == 3
    # Check that in tick 1, memory_diffs interleaves A and B writes:
    # A wrote 100, B wrote 200, A wrote 101, B wrote 201, A wrote 102, B wrote 202, A wrote 103, B wrote 203
    tick1_diffs = snapshots[1].memory_diffs
    assert len(tick1_diffs) == 8
    expected_diff_owners = ["A", "B", "A", "B", "A", "B", "A", "B"]
    actual_diff_owners = [diff.owner for diff in tick1_diffs]
    assert actual_diff_owners == expected_diff_owners

