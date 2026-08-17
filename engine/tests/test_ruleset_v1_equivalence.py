"""Golden equivalence corpus for behavior-preserving engine work.

These compact scenarios intentionally pin Ruleset-v1 outcomes and canonical
artifacts before the v1.4 ownership-accounting optimization. A legitimate
ruleset, Agent API, RNG, methodology, or schema change must version its
contract instead of refreshing these values in place.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from battle_engine.agents import resolve_agent
from battle_engine.builtins import build_agent
from battle_engine.config import Config, Weights
from battle_engine.instructions import HALT, JMP, MOV, STORE, enc
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.replay import ReplayHeader, TickSnapshot, iter_replay

RANDOM_WRITER = b"""from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        self.rng = context.rng
        self.arena_size = context.arena_size
        self.calls = 0

    def act(self, observation):
        self.calls += 1
        if self.calls == 4:
            return AgentAction(ActionKind.HALT)
        return AgentAction(
            ActionKind.WRITE,
            self.rng.randrange(-self.arena_size, self.arena_size * 2),
            self.rng.randrange(256),
        )

def create_agent():
    return Agent()
"""

WRAPPING_WRITER = b"""from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        self.calls = 0

    def act(self, observation):
        self.calls += 1
        return AgentAction(ActionKind.WRITE, -self.calls, 0xA0 + self.calls)

def create_agent():
    return Agent()
"""

FORFEITER = b"""from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        self.calls = 0

    def act(self, observation):
        self.calls += 1
        if self.calls == 2:
            raise RuntimeError("frozen corpus forfeit")
        return AgentAction(ActionKind.NOP)

def create_agent():
    return Agent()
"""


def _python_entrant(
    root: Path, agent_id: str, source: bytes, *, slot: int
) -> MatchEntrant:
    directory = root / "agents" / agent_id
    directory.mkdir(parents=True)
    manifest = {
        "kind": "python",
        "api_version": 1,
        "entrypoint": "agent.py:create_agent",
        "name": agent_id,
        "display": agent_id.title(),
        "version": "1.0",
    }
    directory.joinpath("agent.yaml").write_bytes(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    directory.joinpath("agent.py").write_bytes(source)
    return MatchEntrant.python(agent_id.upper(), agent_id, slot * 19, resolve_agent(root, agent_id))


def _final_arena_fingerprints(replay_path: Path) -> tuple[str, str]:
    arena = bytearray()
    owners: list[str | None] = []
    for record in iter_replay(replay_path):
        if isinstance(record, ReplayHeader):
            arena = bytearray(record.config.arena_size)
            owners = [None] * record.config.arena_size
        elif isinstance(record, TickSnapshot):
            for diff in record.memory_diffs:
                for offset, value in enumerate(diff.values):
                    address = (diff.address + offset) % len(arena)
                    arena[address] = value
                    owners[address] = diff.owner
    owner_bytes = json.dumps(owners, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(arena).hexdigest(), hashlib.sha256(owner_bytes).hexdigest()


def _snapshot(request: MatchRequest) -> dict[str, object]:
    result = NativeMatchService().run(request)
    arena_sha256, ownership_sha256 = _final_arena_fingerprints(result.replay_path)
    return {
        "match_id": result.match_id,
        "result_id": result.result_id,
        # Text-mode newline translation differs by host. Pin the canonical
        # JSONL content after normalizing only that transport detail.
        "normalized_replay_sha256": hashlib.sha256(
            result.replay_path.read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest(),
        "winner": result.winner,
        "termination_reason": result.termination_reason.value,
        "ticks_run": result.ticks_run,
        "score": dict(result.score),
        "arena_sha256": arena_sha256,
        "ownership_sha256": ownership_sha256,
        "agents": [
            {
                "agent_id": agent.agent_id,
                "alive": agent.alive,
                "score": agent.score,
                "alive_ticks": agent.alive_ticks,
                "kills": agent.kills,
                "deaths": agent.deaths,
                "cpu_total": agent.cpu_total,
                "mem_writes": agent.mem_writes,
                "territory_last": agent.territory_last,
                "territory_max": agent.territory_max,
                "territory_avg": agent.territory_avg,
                "termination_reason": agent.termination_reason,
                "diagnostic_code": agent.diagnostic.code if agent.diagnostic else None,
            }
            for agent in result.agents
        ],
    }


def _vm_overlap_request(root: Path) -> MatchRequest:
    first = b"".join((enc(MOV, 0x5A), enc(STORE, 31), enc(JMP, 29), enc(HALT)))
    second = b"".join((enc(MOV, 0xC3), enc(STORE, 31), enc(JMP, 4), enc(HALT)))
    return MatchRequest(
        Config(
            arena_size=32,
            instr_per_tick=2,
            seed=17,
            weights=Weights(alive=2, kill=7, territory=3, territory_bucket=5),
        ),
        (
            MatchEntrant("A", "wrap-store", 29, first),
            MatchEntrant("B", "overlap-store", 4, second),
        ),
        max_ticks=7,
        replay_path=root / "vm-overlap" / "replay.jsonl",
        verbose=False,
    )


def _vm_three_way_request(root: Path) -> MatchRequest:
    return MatchRequest(
        Config(arena_size=128, instr_per_tick=3, seed=991),
        (
            MatchEntrant("A", "writer", 0, build_agent("writer", 0, offset=97, byte=0x31)),
            MatchEntrant("B", "seeker", 43, build_agent("seeker", 43, ptr=121)),
            MatchEntrant("C", "runner", 86, build_agent("runner", 86)),
        ),
        max_ticks=11,
        replay_path=root / "vm-three-way" / "replay.jsonl",
        verbose=False,
    )


def _python_two_way_request(root: Path) -> MatchRequest:
    agent_root = root / "python-two-way"
    return MatchRequest(
        Config(arena_size=53, instr_per_tick=2, seed=2024),
        (
            _python_entrant(agent_root, "alpha", RANDOM_WRITER, slot=0),
            _python_entrant(agent_root, "beta", RANDOM_WRITER, slot=1),
        ),
        max_ticks=6,
        replay_path=agent_root / "run" / "replay.jsonl",
        verbose=False,
    )


def _python_three_way_request(root: Path) -> MatchRequest:
    agent_root = root / "python-three-way"
    return MatchRequest(
        Config(
            arena_size=47,
            instr_per_tick=2,
            seed=73,
            weights=Weights(alive=1, kill=5, territory=2, territory_bucket=7),
        ),
        (
            _python_entrant(agent_root, "alpha", RANDOM_WRITER, slot=0),
            _python_entrant(agent_root, "beta", WRAPPING_WRITER, slot=1),
            _python_entrant(agent_root, "gamma", FORFEITER, slot=2),
        ),
        max_ticks=5,
        replay_path=agent_root / "run" / "replay.jsonl",
        verbose=False,
    )


EXPECTED: dict[str, dict[str, object]] = {
    "vm_overlap": {
        "snapshot_sha256": "e9b32ce0b585130df3eb6a7e2bb44f192309a2bd5eb5ad1dc8646ababbf1de8e",
        "match_id": "match_5d8e4982539e5699ea52b33e",
        "result_id": "result_06d8ccec80457ad12839d563",
        "winner": "B",
        "termination_reason": "tick_limit",
        "ticks_run": 7,
    },
    "vm_three_way": {
        "snapshot_sha256": "d556596fe6edc35248cd4961926f1301dff9a7c784ec5cb4b9906f1a52929bbe",
        "match_id": "match_b8892d4576cb3ede42c04f48",
        "result_id": "result_b3541db4395cdf6405c76d51",
        "winner": "A",
        "termination_reason": "tick_limit",
        "ticks_run": 11,
    },
    "python_two_way": {
        "snapshot_sha256": "3a284f349ac73138b9df238c4c63cb78e144c4c62ad7538f5d01740aa42fa984",
        "match_id": "match_37f7d9caa516a5797303cbd1",
        "result_id": "result_5405eeb31aa8b925a9a69de8",
        "winner": "tie",
        "termination_reason": "all_agents_dead",
        "ticks_run": 2,
    },
    "python_three_way": {
        "snapshot_sha256": "7766804e9a412a75fd5f674309ed9b572ac60d4727c16b528a172b0847a313f4",
        "match_id": "match_f6680bb4d957b3965f6ce3b8",
        "result_id": "result_d4fad2b4ca1f33ce5583ea8d",
        "winner": "BETA",
        "termination_reason": "last_agent_standing",
        "ticks_run": 2,
    },
}


def _snapshot_digest(snapshot: dict[str, object]) -> str:
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@pytest.mark.parametrize(
    ("name", "request_factory"),
    [
        ("vm_overlap", _vm_overlap_request),
        ("vm_three_way", _vm_three_way_request),
        ("python_two_way", _python_two_way_request),
        ("python_three_way", _python_three_way_request),
    ],
)
def test_ruleset_v1_golden_equivalence(name, request_factory, tmp_path):
    snapshot = _snapshot(request_factory(tmp_path))
    expected = EXPECTED[name]
    assert _snapshot_digest(snapshot) == expected["snapshot_sha256"]
    for key in ("match_id", "result_id", "winner", "termination_reason", "ticks_run"):
        assert snapshot[key] == expected[key]
