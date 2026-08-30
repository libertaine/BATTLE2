"""Focused characterization tests for suspected v3.0.0 preflight issues.

Investigates:
1. Issue A: Core-capture attribution in N>=3 cases involving:
   - ownership loss,
   - same-tick reclamation,
   - subsequent ownership loss,
   demonstrating that ``_attribute_core_capture`` decrements the reconstructed
   owner count on loss without restoring it on reclamation, misattributing the kill.

2. Issue B: Captured-entrant territory scoring, characterizing the exact behavior
   of ``ScoringPolicy.score_territory`` vs the docstring and ``RULES_V2.md`` text
   regarding territory credit on the tick of death.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from battle_engine.config import Config, Weights
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.python_runtime import (
    _attribute_core_capture,
    core_addresses,
)
from battle_engine.ruleset_policy import BYTEFRAY_RULESET_V2_ALPHA1_ID
from battle_engine.vm import VM

ALPHA = BYTEFRAY_RULESET_V2_ALPHA1_ID


# ---------------------------------------------------------------------------
# Test helpers
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


# ---------------------------------------------------------------------------
# Issue A: Core-capture attribution characterization
# ---------------------------------------------------------------------------


def test_issue_a_attribute_core_capture_direct_unit() -> None:
    """Direct characterization of _attribute_core_capture with intra-tick reclaim.

    Setup:
    - Arena size 4096, Defender core at start=0 (addresses 0..7).
    - At start of tick, Defender owns only cell 0: ("A", None, None, None, None, None, None, None).
    - Sequence of writes within the tick:
      1. Attacker B writes to address 0 (claims it).
      2. Defender A writes to address 0 (reclaims it).
      3. Attacker C writes to address 0 (fatal un-reclaimed blow).
    - End of tick: Attacker C owns address 0. Defender A owns 0 core cells.

    Expected semantics:
    - Defender A lost cell 0 to B, reclaimed it from B, and then lost it to C.
    - C delivered the final, fatal write.
    - Expected killer: "C".

    Actual v3.0.0 implementation behavior:
    - _attribute_core_capture sees B's write, decrements remaining from 1 to 0,
      and immediately returns "B".
    - Actual killer returned: "B".
    """
    vm = VM(4096)
    core_addrs = core_addresses(0, 4096)
    before_owners = ("A", None, None, None, None, None, None, None)

    state = SimpleNamespace(agent_id="A")

    # Simulate VM writes in order during the tick
    vm.clear_tick_diffs()
    vm._wr8(0, 0x11, "B")
    vm._wr8(0, 0x22, "A")
    vm._wr8(0, 0x33, "C")

    actual_killer = _attribute_core_capture(state, core_addrs, before_owners, vm)  # type: ignore[arg-type]

    # Document the actual defect behavior:
    assert actual_killer == "B", (
        "Demonstrates v3.0.0 defect: B is returned because remaining decremented on B's write "
        "and was not incremented when Defender reclaimed cell 0."
    )
    # The expected correct captor is C
    expected_killer = "C"
    assert actual_killer != expected_killer


def test_issue_a_attribute_core_capture_end_to_end_match(tmp_path: Path) -> None:
    """End-to-end 3-entrant match demonstrating misattribution and score contamination.

    Roster order:
    1. Attacker B (slot A)
    2. Defender (slot B, core at 1000..1007)
    3. Attacker C (slot C)

    In tick 0:
    - Attacker B writes to 1001..1007, leaving only 1000 for Defender.
    In tick 1:
    - Attacker B writes to 1000 (claims last cell).
    - Defender writes to 1000 (reclaims last cell).
    - Attacker C writes to 1000 (final fatal write).

    End of tick 1:
    - Defender is core-captured (owned_now == 0).
    - Under v3.0.0, Attacker B receives 5.0 kill points instead of Attacker C.
    """
    src_b = b"""from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, ctx):
        self.call = 0
    def act(self, obs):
        c = self.call
        self.call += 1
        if c < 7:
            return AgentAction(ActionKind.WRITE, 1001 + c, 0xBB)
        if c == 8:  # Tick 1, slot 0
            return AgentAction(ActionKind.WRITE, 1000, 0xBB)
        return AgentAction(ActionKind.NOP)
def create_agent():
    return Agent()
"""
    src_a = b"""from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, ctx):
        self.call = 0
    def act(self, obs):
        c = self.call
        self.call += 1
        if c == 8:  # Tick 1, slot 0
            return AgentAction(ActionKind.WRITE, 1000, 0xAA)
        return AgentAction(ActionKind.NOP)
def create_agent():
    return Agent()
"""
    src_c = b"""from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, ctx):
        self.call = 0
    def act(self, obs):
        c = self.call
        self.call += 1
        if c == 8:  # Tick 1, slot 0
            return AgentAction(ActionKind.WRITE, 1000, 0xCC)
        return AgentAction(ActionKind.NOP)
def create_agent():
    return Agent()
"""
    entrants = (
        _python_entrant(tmp_path, "attacker_b", src_b, slot="A", start=0),
        _python_entrant(tmp_path, "defender", src_a, slot="B", start=1000),
        _python_entrant(tmp_path, "attacker_c", src_c, slot="C", start=2000),
    )
    config = Config(
        arena_size=4096,
        instr_per_tick=8,
        seed=1337,
        win_mode="score_fallback",
        weights=Weights(alive=1.0, kill=5.0, territory=0.0),
    )
    request = MatchRequest(
        config=config,
        entrants=entrants,
        max_ticks=3,
        replay_path=tmp_path / "replay.jsonl",
        ruleset_id=ALPHA,
        verbose=False,
    )
    result = NativeMatchService().run(request)

    # Confirm Defender died from core capture
    defender_res = result.agents_by_id["B"]
    assert defender_res.alive is False
    assert defender_res.termination_reason == "core_captured"

    # In actual v3.0.0 implementation, Attacker B was awarded the kill (defect):
    attacker_b_res = result.agents_by_id["A"]
    attacker_c_res = result.agents_by_id["C"]
    assert attacker_b_res.score > attacker_c_res.score  # B got +5.0 kill points
    assert attacker_b_res.kills == 1
    assert attacker_c_res.kills == 0


# ---------------------------------------------------------------------------
# Issue B: Captured-entrant territory scoring characterization
# ---------------------------------------------------------------------------


def test_issue_b_captured_entrant_territory_scoring(tmp_path: Path) -> None:
    """Characterize territory scoring for an entrant on the tick it is core-captured.

    Setup:
    - Entrant A (Defender) claims 128 cells in tick 0 (2 buckets of 64).
    - Entrant B (Attacker) writes to Defender A's core in tick 0 (after A writes), capturing it.

    Findings:
    - On Tick 0 (tick of capture):
      - alive points: 0.0 (score_alive checks state.alive, which was set to False).
      - territory points: 2.0 (score_territory has NO alive check and awards 2.0 points
        based on ownership of the 128 non-core cells).
      - Total score at tick 0: 2.0 points.

    Documented vs Implemented:
    - Documented (RULES_V2.md): "a captured entrant receives no alive/territory credit
      for the tick it dies on".
    - Implemented: alive credit is denied, but territory credit continues to accrue
      on the tick of capture (and subsequent ticks if play continues).
    - Winner safeguard: resolve_winner ignores dead entrants' accumulated scores
      when any living entrant survives.
    """
    # Entrant A claims addresses 200..327 (128 cells) in tick 0
    src_a = b"""from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, ctx):
        self.idx = 0
    def act(self, obs):
        if self.idx < 128:
            addr = 200 + self.idx
            self.idx += 1
            return AgentAction(ActionKind.WRITE, addr, 0xAA)
        return AgentAction(ActionKind.NOP)
def create_agent():
    return Agent()
"""
    # Entrant B attacks Entrant A's core (start=1000) on tick 0
    src_b = b"""from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, ctx):
        self.idx = 0
    def act(self, obs):
        if self.idx < 8:
            addr = 1000 + self.idx
            self.idx += 1
            return AgentAction(ActionKind.WRITE, addr, 0xBB)
        return AgentAction(ActionKind.NOP)
def create_agent():
    return Agent()
"""
    entrants = (
        _python_entrant(tmp_path, "defender_a", src_a, slot="A", start=1000),
        _python_entrant(tmp_path, "attacker_b", src_b, slot="B", start=3000),
    )
    # Set instr_per_tick=128 so A claims all 128 cells in tick 0, B takes core in tick 0
    config = Config(
        arena_size=4096,
        instr_per_tick=128,
        seed=1337,
        win_mode="score_fallback",
        weights=Weights(alive=1.0, kill=5.0, territory=1.0, territory_bucket=64),
    )
    request = MatchRequest(
        config=config,
        entrants=entrants,
        max_ticks=3,
        replay_path=tmp_path / "replay.jsonl",
        ruleset_id=ALPHA,
        verbose=False,
    )
    result = NativeMatchService().run(request)

    # Defender A is dead at tick 0
    assert result.agents_by_id["A"].alive is False
    assert result.agents_by_id["A"].termination_reason == "core_captured"

    # Attacker B is alive
    assert result.agents_by_id["B"].alive is True

    # Characterize the score breakdown for Defender A:
    # alive points: 0.0 (alive check in score_alive)
    # territory points: 2.0 (no alive check in score_territory)
    # Total score is 2.0 (if territory had an alive check, it would be 0.0).
    assert result.agents_by_id["A"].score == 2.0

    # Winner resolution: Attacker B is the sole survivor and wins
    assert result.winner == "B"

