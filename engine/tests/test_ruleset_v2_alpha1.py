"""``bytefray-rules-2-alpha1`` "Vulnerable Core" -- focused mechanic tests.

Covers the Phase 8 checklist from the governing v2.0.0-alpha.1 task: Ruleset
dispatch, ``MatchRequest.ruleset_id``, fixed core geometry (including arena
wrap), core ownership accounting, capture/no-premature-capture/deterministic
timing, kill attribution (including the one edge case where it cannot be
determined), Ruleset-v1 non-interference, distinct-start support, and
replay/result identity persistence. Reference-agent (Core Defender/Core
Seeker) validation lives in ``test_reference_agents.py``.

Every scripted agent below is a small, fully deterministic Python source
string (mirroring ``test_ruleset_v1_equivalence.py``'s own
``RANDOM_WRITER``/``FORFEITER`` pattern) rather than a real starter agent,
so each scenario's exact tick-by-tick ownership sequence is knowable in
advance and the test can assert on it precisely.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from battle_engine.agent_test import test_agent as run_agent_test
from battle_engine.agents import resolve_agent
from battle_engine.config import Config
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.python_runtime import CORE_SIZE, core_addresses
from battle_engine.replay import ReplayHeader, TickSnapshot, iter_replay
from battle_engine.result_model import read_result
from battle_engine.rules import BYTEFRAY_RULESET_ID
from battle_engine.ruleset_policy import BYTEFRAY_RULESET_V2_ALPHA1_ID, UnknownRulesetError
from battle_engine.starters import ensure_starter_agents

ALPHA = BYTEFRAY_RULESET_V2_ALPHA1_ID


def _write_agent(agent_dir: Path, agent_id: str, source: bytes) -> None:
    agent_dir.mkdir(parents=True)
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


def _python_entrant(root: Path, agent_id: str, source: bytes, *, slot: str, start: int) -> MatchEntrant:
    agent_dir = root / "agents" / agent_id
    _write_agent(agent_dir, agent_id, source)
    return MatchEntrant.python(slot, agent_id, start, resolve_agent(root, agent_id))


NOP_SOURCE = b"""from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        pass

    def act(self, observation):
        return AgentAction(ActionKind.NOP)

def create_agent():
    return Agent()
"""

HALT_SOURCE = b"""from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        pass

    def act(self, observation):
        return AgentAction(ActionKind.HALT)

def create_agent():
    return Agent()
"""


def _scripted_writer_source(addresses: list[int], value: int = 0xAA) -> bytes:
    """A deterministic agent that writes ``addresses`` in order, one per
    ``act()`` call, then NOPs forever once the list is exhausted."""

    return (
        "from battle_engine.agent_api import ActionKind, AgentAction\n\n"
        f"ADDRESSES = {addresses!r}\n\n"
        "class Agent:\n"
        "    def reset(self, context):\n"
        "        self.index = 0\n\n"
        "    def act(self, observation):\n"
        "        if self.index < len(ADDRESSES):\n"
        "            addr = ADDRESSES[self.index]\n"
        "            self.index += 1\n"
        f"            return AgentAction(ActionKind.WRITE, addr, {value})\n"
        "        return AgentAction(ActionKind.NOP)\n\n"
        "def create_agent():\n"
        "    return Agent()\n"
    ).encode()


def _always_write_source(address: int, value: int = 0x11) -> bytes:
    """A deterministic agent that writes the same single address every
    ``act()`` call (used to demonstrate reclaiming a lost core cell)."""

    return (
        "from battle_engine.agent_api import ActionKind, AgentAction\n\n"
        "class Agent:\n"
        "    def reset(self, context):\n"
        "        pass\n\n"
        "    def act(self, observation):\n"
        f"        return AgentAction(ActionKind.WRITE, {address}, {value})\n\n"
        "def create_agent():\n"
        "    return Agent()\n"
    ).encode()


# ---------------------------------------------------------------------------
# Fixed core geometry
# ---------------------------------------------------------------------------


def test_core_addresses_uses_ordinary_arena_wrap() -> None:
    assert core_addresses(0, 16) == (0, 1, 2, 3, 4, 5, 6, 7)


def test_core_addresses_wraps_across_arena_end() -> None:
    # CORE_SIZE == 8; a core anchored 3 cells before the arena end must
    # wrap around to address 0, exactly like every other arena access.
    assert core_addresses(16 - 3, 16) == (13, 14, 15, 0, 1, 2, 3, 4)


def test_core_size_is_the_documented_experimental_constant() -> None:
    assert CORE_SIZE == 8


# ---------------------------------------------------------------------------
# MatchRequest.ruleset_id / dispatch
# ---------------------------------------------------------------------------


def test_match_request_ruleset_id_defaults_to_none() -> None:
    request = MatchRequest(Config(), (), max_ticks=1, replay_path=Path("x"))
    assert request.ruleset_id is None


def test_unknown_ruleset_id_on_match_request_fails_closed(tmp_path) -> None:
    entrants = (
        _python_entrant(tmp_path, "alpha", NOP_SOURCE, slot="A", start=0),
        _python_entrant(tmp_path, "beta", NOP_SOURCE, slot="B", start=0),
    )
    request = MatchRequest(
        Config(arena_size=64),
        entrants,
        max_ticks=3,
        replay_path=tmp_path / "run" / "replay.jsonl",
        verbose=False,
        ruleset_id="bytefray-rules-3",  # never registered -- must not silently run as v1
    )
    with pytest.raises(UnknownRulesetError):
        NativeMatchService().run(request)


# ---------------------------------------------------------------------------
# Core ownership accounting / capture / attribution
# ---------------------------------------------------------------------------


def _core_capture_request(
    tmp_path: Path,
    *,
    victim_start: int,
    attacker_source: bytes,
    victim_source: bytes = NOP_SOURCE,
    arena_size: int = 128,
    instr_per_tick: int = 8,
    max_ticks: int = 20,
) -> MatchRequest:
    entrants = (
        _python_entrant(tmp_path, "victim", victim_source, slot="A", start=victim_start),
        _python_entrant(tmp_path, "attacker", attacker_source, slot="B", start=0),
    )
    return MatchRequest(
        Config(arena_size=arena_size, instr_per_tick=instr_per_tick),
        entrants,
        max_ticks=max_ticks,
        replay_path=tmp_path / "run" / "replay.jsonl",
        verbose=False,
        ruleset_id=ALPHA,
    )


def test_seeding_establishes_full_initial_core_ownership(tmp_path) -> None:
    request = _core_capture_request(
        tmp_path, victim_start=20, attacker_source=NOP_SOURCE, max_ticks=1
    )
    result = NativeMatchService().run(request)
    victim = result.agents_by_id["A"]
    assert victim.alive is True
    for record in iter_replay(result.replay_path):
        if isinstance(record, TickSnapshot) and record.tick == 0:
            owned = sum(
                1
                for diff in record.memory_diffs
                for offset in range(diff.length)
                if diff.owner == "A" and (diff.address + offset) % request.config.arena_size in
                core_addresses(20, request.config.arena_size)
            )
            assert owned == CORE_SIZE


def test_full_capture_within_one_tick_kills_immediately_with_attribution(tmp_path) -> None:
    core = list(core_addresses(20, 128))
    request = _core_capture_request(tmp_path, victim_start=20, attacker_source=_scripted_writer_source(core))
    result = NativeMatchService().run(request)
    victim = result.agents_by_id["A"]
    attacker = result.agents_by_id["B"]
    assert victim.alive is False
    assert victim.termination_reason == "core_captured"
    assert attacker.kills == 1
    assert victim.deaths == 1
    assert result.winner == "B"
    assert result.termination_reason.value == "last_agent_standing"

    kill_ticks = [
        record.tick
        for record in iter_replay(result.replay_path)
        if isinstance(record, TickSnapshot)
        for event in record.events
        if getattr(event, "event_type", None) == "kill"
    ]
    assert kill_ticks == [1]  # instr_per_tick=8 covers all 8 core cells in tick 1


def test_no_premature_capture_while_defender_still_owns_a_cell(tmp_path) -> None:
    core = list(core_addresses(20, 128))
    request = _core_capture_request(
        tmp_path, victim_start=20, attacker_source=_scripted_writer_source(core[:-1])
    )
    result = NativeMatchService().run(request)
    victim = result.agents_by_id["A"]
    assert victim.alive is True
    assert victim.termination_reason is None


def test_deterministic_capture_timing_spreads_across_ticks(tmp_path) -> None:
    """With a low per-tick action budget, capture happens on the exact tick
    the last core cell flips -- not before, not with an extra turn after."""

    core = list(core_addresses(20, 128))
    request = _core_capture_request(
        tmp_path,
        victim_start=20,
        attacker_source=_scripted_writer_source(core),
        instr_per_tick=2,
        max_ticks=10,
    )
    result = NativeMatchService().run(request)
    victim = result.agents_by_id["A"]
    assert victim.alive is False
    assert victim.termination_reason == "core_captured"

    kill_events = [
        (record.tick, event)
        for record in iter_replay(result.replay_path)
        if isinstance(record, TickSnapshot)
        for event in record.events
        if getattr(event, "event_type", None) == "kill"
    ]
    # 8 core cells at 2 writes/tick -> the 8th (final) cell flips on tick 4.
    assert len(kill_events) == 1
    assert kill_events[0][0] == 4
    assert kill_events[0][1].victim == "A"
    assert kill_events[0][1].killer == "B"


def test_final_cell_changing_ownership_triggers_capture_that_tick(tmp_path) -> None:
    """"Opponent captures all but one cell" then "the final cell changes
    ownership" on a later, separate tick -- exercised together since the
    second is only meaningful given the first."""

    core = list(core_addresses(20, 128))
    request = _core_capture_request(
        tmp_path,
        victim_start=20,
        attacker_source=_scripted_writer_source(core),
        instr_per_tick=1,
        max_ticks=20,
    )
    result = NativeMatchService().run(request)
    victim = result.agents_by_id["A"]
    assert victim.alive is False
    # One write/tick, 8 addresses -> the final (8th) write, and the capture
    # it causes, land on tick 8. Ticks 1-7 must show the victim still alive
    # and owning at least one core cell.
    tick_by_number = {
        record.tick: record for record in iter_replay(result.replay_path) if isinstance(record, TickSnapshot)
    }
    for tick in range(1, 8):
        agents = {agent.agent_id: agent for agent in tick_by_number[tick].agents}
        assert agents["A"].alive is True
    final_agents = {agent.agent_id: agent for agent in tick_by_number[8].agents}
    assert final_agents["A"].alive is False
    assert final_agents["A"].termination_reason == "core_captured"


def test_entrant_writing_into_its_own_core_never_self_captures(tmp_path) -> None:
    core0 = core_addresses(20, 128)[0]
    request = _core_capture_request(
        tmp_path,
        victim_start=20,
        attacker_source=NOP_SOURCE,
        victim_source=_always_write_source(core0),
        max_ticks=5,
    )
    result = NativeMatchService().run(request)
    victim = result.agents_by_id["A"]
    assert victim.alive is True
    assert victim.termination_reason is None


def test_ownership_changes_away_and_back_without_completing_capture(tmp_path) -> None:
    """Cell 20 (the victim's own core[0]) is taken by the attacker on tick
    1, reclaimed by the victim on tick 2, taken again on tick 3, and so on
    -- the victim always keeps at least the other 7 core cells, so a
    capture must never fire despite this cell's ownership fluctuating."""

    victim_source = _always_write_source(20, value=0x22)
    attacker_actions = (
        b"from battle_engine.agent_api import ActionKind, AgentAction\n\n"
        b"class Agent:\n"
        b"    def reset(self, context):\n"
        b"        self.tick = 0\n\n"
        b"    def act(self, observation):\n"
        b"        self.tick += 1\n"
        b"        if self.tick % 2 == 1:\n"
        b"            return AgentAction(ActionKind.WRITE, 20, 0x33)\n"
        b"        return AgentAction(ActionKind.NOP)\n\n"
        b"def create_agent():\n"
        b"    return Agent()\n"
    )
    request = _core_capture_request(
        tmp_path,
        victim_start=20,
        attacker_source=attacker_actions,
        victim_source=victim_source,
        instr_per_tick=1,
        max_ticks=6,
    )
    result = NativeMatchService().run(request)
    victim = result.agents_by_id["A"]
    assert victim.alive is True
    assert victim.termination_reason is None


def test_capture_attribution_unattributed_when_core_already_lost_before_the_tick(tmp_path) -> None:
    """Two entrants spawned with fully overlapping cores (a pathological,
    non-recommended configuration): the second entrant's seeding overwrites
    the first's core ownership entirely before tick one even begins, so
    there is no single attributable write this alpha's attribution scheme
    can point to -- an unattributed death, not an invented killer."""

    entrants = (
        _python_entrant(tmp_path, "first", NOP_SOURCE, slot="A", start=5),
        _python_entrant(tmp_path, "second", NOP_SOURCE, slot="B", start=5),
    )
    request = MatchRequest(
        Config(arena_size=128, instr_per_tick=1),
        entrants,
        max_ticks=2,
        replay_path=tmp_path / "run" / "replay.jsonl",
        verbose=False,
        ruleset_id=ALPHA,
    )
    result = NativeMatchService().run(request)
    first = result.agents_by_id["A"]
    assert first.alive is False
    assert first.termination_reason == "core_captured"
    assert first.deaths == 1
    second = result.agents_by_id["B"]
    assert second.kills == 0  # unattributed: "second" gets no kill credit


def test_match_terminates_for_another_reason_before_any_capture(tmp_path) -> None:
    request = _core_capture_request(
        tmp_path, victim_start=20, attacker_source=NOP_SOURCE, victim_source=HALT_SOURCE, max_ticks=5
    )
    result = NativeMatchService().run(request)
    victim = result.agents_by_id["A"]
    assert victim.termination_reason == "normal_halt"
    assert result.termination_reason.value == "last_agent_standing"


def test_self_match_is_supported_under_the_alpha_ruleset(tmp_path) -> None:
    ensure_starter_agents(data_root=tmp_path)
    entrants = (
        MatchEntrant.python("A", "claimer", 0, resolve_agent(tmp_path, "claimer")),
        MatchEntrant.python("B", "claimer", 2048, resolve_agent(tmp_path, "claimer")),
    )
    request = MatchRequest(
        Config(),
        entrants,
        max_ticks=5,
        replay_path=tmp_path / "run" / "replay.jsonl",
        verbose=False,
        ruleset_id=ALPHA,
    )
    result = NativeMatchService().run(request)
    assert result.termination_reason.value in {"tick_limit", "last_agent_standing", "all_agents_dead"}


# ---------------------------------------------------------------------------
# Ruleset v1 non-interference
# ---------------------------------------------------------------------------


def test_v1_python_matches_never_core_capture_even_when_fully_overwritten(tmp_path) -> None:
    """Same scripted attack that captures under the alpha ruleset must be a
    complete no-op mortality-wise under Ruleset v1 -- v1 Python entrants
    have no core seeding and no capture check at all."""

    core = list(core_addresses(20, 128))
    entrants = (
        _python_entrant(tmp_path, "victim", NOP_SOURCE, slot="A", start=20),
        _python_entrant(tmp_path, "attacker", _scripted_writer_source(core), slot="B", start=0),
    )
    request = MatchRequest(
        Config(arena_size=128, instr_per_tick=8),
        entrants,
        max_ticks=5,
        replay_path=tmp_path / "run" / "replay.jsonl",
        verbose=False,
        # ruleset_id left at its default (None) -> resolves to v1.
    )
    result = NativeMatchService().run(request)
    victim = result.agents_by_id["A"]
    assert victim.alive is True
    assert victim.termination_reason is None
    assert victim.kills == 0
    assert result.agents_by_id["B"].kills == 0


# ---------------------------------------------------------------------------
# Start placement (agent_test.py) and replay/result identity persistence
# ---------------------------------------------------------------------------


def test_agent_test_default_start_placement_is_unchanged(tmp_path) -> None:
    """Every existing agent_test.py caller must still see both entrants at
    the identical shared address 0, under the frozen v1 identity, exactly
    as before ruleset_id/agent_start/opponent_start existed."""

    ensure_starter_agents(data_root=tmp_path)
    outcome = run_agent_test(
        "claimer", opponent="hunter", data_root=tmp_path, run_dir=tmp_path / "run", ticks=3, trace=False
    )
    records = list(iter_replay(outcome.match_result.replay_path))
    header = records[0]
    assert isinstance(header, ReplayHeader)
    assert header.ruleset_id == BYTEFRAY_RULESET_ID
    tick_zero = next(r for r in records if isinstance(r, TickSnapshot) and r.tick == 0)
    starting_pcs = {agent.agent_id: agent.pc for agent in tick_zero.agents}
    assert starting_pcs == {"A": 0, "B": 0}


def test_agent_test_supports_distinct_starts_and_alpha_ruleset(tmp_path) -> None:
    ensure_starter_agents(data_root=tmp_path)
    outcome = run_agent_test(
        "claimer",
        opponent="hunter",
        data_root=tmp_path,
        run_dir=tmp_path / "run",
        ticks=5,
        trace=False,
        ruleset_id=ALPHA,
        agent_start=0,
        opponent_start=2048,
    )
    result = outcome.match_result
    assert result.result_path is not None
    envelope = read_result(result.result_path)
    assert envelope.ruleset_id == ALPHA
    header = next(iter_replay(result.replay_path))
    assert isinstance(header, ReplayHeader)
    assert header.ruleset_id == ALPHA


def test_alpha_and_v1_produce_different_match_identity_for_equivalent_inputs(tmp_path) -> None:
    entrants = (
        _python_entrant(tmp_path, "alpha_side", NOP_SOURCE, slot="A", start=0),
        _python_entrant(tmp_path, "beta_side", NOP_SOURCE, slot="B", start=64),
    )
    base = {
        "config": Config(arena_size=128, instr_per_tick=2),
        "entrants": entrants,
        "max_ticks": 3,
        "verbose": False,
    }
    v1_result = NativeMatchService().run(
        MatchRequest(**base, replay_path=tmp_path / "v1" / "replay.jsonl")
    )
    alpha_result = NativeMatchService().run(
        MatchRequest(**base, replay_path=tmp_path / "alpha" / "replay.jsonl", ruleset_id=ALPHA)
    )
    assert v1_result.match_id != alpha_result.match_id
    assert v1_result.result_id != alpha_result.result_id

    v1_envelope = read_result(v1_result.result_path)
    alpha_envelope = read_result(alpha_result.result_path)
    assert v1_envelope.ruleset_id == BYTEFRAY_RULESET_ID
    assert alpha_envelope.ruleset_id == ALPHA
