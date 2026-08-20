"""Beta1 promotion-equivalence corpus: ``bytefray-rules-2-alpha11`` vs
``bytefray-rules-2``.

Phase 1C of docs/V2_0_BETA1_PLAN.md: v2.0.0-beta1 promotes alpha.11's
evidence-backed candidate semantics into the permanent ``bytefray-rules-2``
identity rather than inventing new gameplay. This file is the direct proof:
for each representative scenario below, running byte-identical inputs under
the two Ruleset identities must produce identical semantic output --
winner, every per-agent statistic, final arena content, final ownership,
and every replay event -- differing *only* in the identity fields that are
expected to differ (the Ruleset identity itself, and the canonical
match/result/replay ids derived from it).

Scenarios, matching the governing task's minimum list:

* Claimer vs Core Tracker (starter vs reference offense benchmark)
* Hunter vs Core Tracker
* Core Tracker vs Core Defender
* Core Tracker vs Reactive Core Defender
* one 3-entrant match
* a wraparound core
* a deterministic capture case
* a deterministic non-capture case
* more than one seed for Core Tracker (seeds vary the search outcome, per
  docs/V2_0_ALPHA11_RULESET_V2_CANDIDATE_RESOLUTION.md Sec 17)
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
from battle_engine.agents import resolve_agent
from battle_engine.config import Config
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.reference_agents import reference_agent_spec
from battle_engine.replay import ReplayHeader, TickSnapshot, iter_replay
from battle_engine.result_model import read_result
from battle_engine.ruleset_policy import (
    BYTEFRAY_RULESET_V2_ALPHA11_ID,
    BYTEFRAY_RULESET_V2_ID,
)
from battle_engine.starters import ensure_starter_agents

ALPHA11 = BYTEFRAY_RULESET_V2_ALPHA11_ID
V2 = BYTEFRAY_RULESET_V2_ID


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


def _scripted_entrant(root: Path, agent_id: str, source: bytes, *, slot: str, start: int):
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


def _scripted_writer_source(addresses: list[int], value: int = 0xAA) -> bytes:
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


def _run(
    tmp_path: Path,
    entrants,
    *,
    ruleset_id: str,
    run_name: str,
    arena_size: int = 4096,
    instr_per_tick: int = 8,
    max_ticks: int = 200,
    seed: int = 1,
):
    request = MatchRequest(
        Config(arena_size=arena_size, instr_per_tick=instr_per_tick, seed=seed),
        entrants,
        max_ticks=max_ticks,
        replay_path=tmp_path / run_name / "replay.jsonl",
        verbose=False,
        ruleset_id=ruleset_id,
    )
    return NativeMatchService().run(request)


def _agent_snapshot(result) -> dict[str, tuple]:
    """Every semantically meaningful per-agent field, excluding nothing
    ruleset-identity-derived (``NativeAgentResult`` carries no such field)."""

    return {
        agent.agent_id: (
            agent.alive,
            agent.score,
            agent.alive_ticks,
            agent.kills,
            agent.deaths,
            agent.cpu_total,
            agent.mem_writes,
            agent.territory_last,
            agent.territory_max,
            round(agent.territory_avg, 9),
            agent.termination_reason,
        )
        for agent in result.agents
    }


def _final_arena_and_owners(result, arena_size: int) -> tuple[dict[int, int], dict[int, str | None]]:
    arena: dict[int, int] = {}
    owners: dict[int, str | None] = {}
    for record in iter_replay(result.replay_path):
        if not isinstance(record, TickSnapshot):
            continue
        for diff in record.memory_diffs:
            for offset, value in enumerate(diff.values):
                arena[(diff.address + offset) % arena_size] = value
            for offset in range(diff.length):
                owners[(diff.address + offset) % arena_size] = diff.owner
    return arena, owners


def _events(result) -> list[tuple[int, str, dict[str, Any]]]:
    """Every replay event, normalized to a plain, order-preserving tuple
    list -- includes the tick it occurred on so timing equivalence (not
    just event content) is part of the equivalence check."""

    out: list[tuple[int, str, dict[str, Any]]] = []
    for record in iter_replay(result.replay_path):
        if not isinstance(record, TickSnapshot):
            continue
        for event in record.events:
            out.append((record.tick, type(event).__name__, asdict(event)))
    return out


def _assert_semantically_equivalent(alpha11_result, v2_result, *, arena_size: int) -> None:
    # Identity fields are *expected* to differ.
    alpha11_header = next(
        r for r in iter_replay(alpha11_result.replay_path) if isinstance(r, ReplayHeader)
    )
    v2_header = next(r for r in iter_replay(v2_result.replay_path) if isinstance(r, ReplayHeader))
    assert alpha11_header.ruleset_id == ALPHA11
    assert v2_header.ruleset_id == V2
    assert alpha11_header.match_id != v2_header.match_id
    assert alpha11_result.result_id != v2_result.result_id
    alpha11_envelope = read_result(alpha11_result.result_path)
    v2_envelope = read_result(v2_result.result_path)
    assert alpha11_envelope.ruleset_id == ALPHA11
    assert v2_envelope.ruleset_id == V2

    # Everything else must be identical.
    assert alpha11_result.winner == v2_result.winner
    assert alpha11_result.ticks_run == v2_result.ticks_run
    assert alpha11_result.termination_reason == v2_result.termination_reason
    assert dict(alpha11_result.score) == dict(v2_result.score)
    assert _agent_snapshot(alpha11_result) == _agent_snapshot(v2_result)

    alpha11_arena, alpha11_owners = _final_arena_and_owners(alpha11_result, arena_size)
    v2_arena, v2_owners = _final_arena_and_owners(v2_result, arena_size)
    assert alpha11_arena == v2_arena
    assert alpha11_owners == v2_owners

    assert _events(alpha11_result) == _events(v2_result)


def _matched_pair(tmp_path: Path, build_entrants, **run_kwargs):
    """Run ``build_entrants()`` (a zero-arg factory, since ``MatchEntrant``
    resolution is not always reusable across two separate roots) once under
    each Ruleset and assert full semantic equivalence."""

    arena_size = run_kwargs.get("arena_size", 4096)
    alpha11_result = _run(
        tmp_path, build_entrants(tmp_path / "alpha11"), ruleset_id=ALPHA11, run_name="alpha11", **run_kwargs
    )
    v2_result = _run(tmp_path, build_entrants(tmp_path / "v2"), ruleset_id=V2, run_name="v2", **run_kwargs)
    _assert_semantically_equivalent(alpha11_result, v2_result, arena_size=arena_size)


# ---------------------------------------------------------------------------
# Reference-agent matchups, multiple seeds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_claimer_vs_core_tracker_equivalent_across_seeds(tmp_path: Path, seed: int) -> None:
    def build(root: Path):
        ensure_starter_agents(data_root=root)
        claimer = resolve_agent(root, "claimer")
        tracker = reference_agent_spec("core_tracker")
        return (
            MatchEntrant.python("A", "claimer", 0, claimer),
            MatchEntrant.python("B", "core_tracker", 2048, tracker),
        )

    _matched_pair(tmp_path, build, seed=seed)


@pytest.mark.parametrize("seed", [1, 2])
def test_hunter_vs_core_tracker_equivalent_across_seeds(tmp_path: Path, seed: int) -> None:
    def build(root: Path):
        ensure_starter_agents(data_root=root)
        hunter = resolve_agent(root, "hunter")
        tracker = reference_agent_spec("core_tracker")
        return (
            MatchEntrant.python("A", "hunter", 0, hunter),
            MatchEntrant.python("B", "core_tracker", 2048, tracker),
        )

    _matched_pair(tmp_path, build, seed=seed)


def test_core_tracker_vs_core_defender_equivalent(tmp_path: Path) -> None:
    def build(root: Path):
        tracker = reference_agent_spec("core_tracker")
        defender = reference_agent_spec("core_defender")
        return (
            MatchEntrant.python("A", "core_tracker", 0, tracker),
            MatchEntrant.python("B", "core_defender", 2048, defender),
        )

    _matched_pair(tmp_path, build, seed=4)


def test_core_tracker_vs_reactive_core_defender_equivalent(tmp_path: Path) -> None:
    def build(root: Path):
        tracker = reference_agent_spec("core_tracker")
        reactive = reference_agent_spec("reactive_core_defender")
        return (
            MatchEntrant.python("A", "core_tracker", 0, tracker),
            MatchEntrant.python("B", "reactive_core_defender", 2048, reactive),
        )

    _matched_pair(tmp_path, build, seed=5)


# ---------------------------------------------------------------------------
# 3-entrant match
# ---------------------------------------------------------------------------


def test_three_entrant_match_equivalent(tmp_path: Path) -> None:
    def build(root: Path):
        ensure_starter_agents(data_root=root)
        claimer = resolve_agent(root, "claimer")
        tracker = reference_agent_spec("core_tracker")
        defender = reference_agent_spec("core_defender")
        return (
            MatchEntrant.python("A", "claimer", 0, claimer),
            MatchEntrant.python("B", "core_tracker", 1365, tracker),
            MatchEntrant.python("C", "core_defender", 2730, defender),
        )

    _matched_pair(tmp_path, build, seed=2)


# ---------------------------------------------------------------------------
# Deterministic, scripted scenarios: wraparound core, capture, non-capture
# ---------------------------------------------------------------------------


def test_wraparound_core_equivalent(tmp_path: Path) -> None:
    arena_size = 128
    start = arena_size - 3  # core spans 125,126,127,0,1,2,3,4

    def build(root: Path):
        return (
            _scripted_entrant(root, "wrapper", NOP_SOURCE, slot="A", start=start),
            _scripted_entrant(root, "other", NOP_SOURCE, slot="B", start=60),
        )

    _matched_pair(tmp_path, build, arena_size=arena_size, max_ticks=5, seed=1)


def test_deterministic_capture_case_equivalent(tmp_path: Path) -> None:
    arena_size = 128
    core = [start_addr for start_addr in range(20, 28)]

    def build(root: Path):
        return (
            _scripted_entrant(root, "victim", NOP_SOURCE, slot="A", start=20),
            _scripted_entrant(
                root, "attacker", _scripted_writer_source(core), slot="B", start=60
            ),
        )

    _matched_pair(tmp_path, build, arena_size=arena_size, max_ticks=20, seed=1)


def test_deterministic_non_capture_case_equivalent(tmp_path: Path) -> None:
    arena_size = 128

    def build(root: Path):
        return (
            _scripted_entrant(root, "idle_a", NOP_SOURCE, slot="A", start=20),
            _scripted_entrant(root, "idle_b", NOP_SOURCE, slot="B", start=60),
        )

    _matched_pair(tmp_path, build, arena_size=arena_size, max_ticks=10, seed=1)


# ---------------------------------------------------------------------------
# Explicit non-equivalence check: the equivalence corpus does not silently
# also make v1/alpha1 look the same -- only alpha11 vs v2 are expected to
# match, never anything else.
# ---------------------------------------------------------------------------


def test_permanent_v2_still_differs_from_ruleset_v1_and_alpha1(tmp_path: Path) -> None:
    """The equivalence corpus above proves alpha11-vs-v2 sameness; this
    proves it is not vacuous -- v1 and alpha1 remain genuinely,
    behaviorally distinct from v2, not merely differently labeled."""

    from battle_engine.python_runtime import CORE_BEACON_BYTE, core_addresses
    from battle_engine.rules import BYTEFRAY_RULESET_ID
    from battle_engine.ruleset_policy import BYTEFRAY_RULESET_V2_ALPHA1_ID

    def build(root: Path):
        return (
            _scripted_entrant(root, "idle_a", NOP_SOURCE, slot="A", start=20),
            _scripted_entrant(root, "idle_b", NOP_SOURCE, slot="B", start=60),
        )

    v1_result = _run(
        tmp_path,
        build(tmp_path / "v1"),
        ruleset_id=BYTEFRAY_RULESET_ID,
        run_name="v1",
        arena_size=128,
        max_ticks=3,
    )
    alpha1_result = _run(
        tmp_path,
        build(tmp_path / "alpha1"),
        ruleset_id=BYTEFRAY_RULESET_V2_ALPHA1_ID,
        run_name="alpha1",
        arena_size=128,
        max_ticks=3,
    )
    v2_result = _run(
        tmp_path, build(tmp_path / "v2"), ruleset_id=V2, run_name="v2", arena_size=128, max_ticks=3
    )
    v1_arena, _ = _final_arena_and_owners(v1_result, 128)
    alpha1_arena, _ = _final_arena_and_owners(alpha1_result, 128)
    v2_arena, _ = _final_arena_and_owners(v2_result, 128)
    core = core_addresses(20, 128)

    # v1: no core mechanic at all -- no diffs published, nothing seeded.
    assert not any(address in v1_arena for address in core)
    # alpha1: core is seeded, but with a blank byte -- invisible to search.
    assert all(alpha1_arena[address] == 0 for address in core)
    # permanent v2: promotes alpha.11's observable seed -- the beacon.
    assert all(v2_arena[address] == CORE_BEACON_BYTE for address in core)
