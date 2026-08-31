"""Beta1 Phase 3: ``battle_client.replay_status`` acceptance coverage.

Two fixture styles, mirroring the project's existing convention (see
``test_analysis.py`` and ``engine/tests/test_ruleset_v2.py``):

* **Hand-built replays** (``_replay`` / ``_header`` / ``_core_seed_diff``
  helpers below) give precise, deterministic control over ownership at
  each tick -- used for the byte-content-independence, reclaim,
  wraparound, unattributed-capture, and N-entrant scenarios the governing
  task calls out explicitly.
* **Real matches** via ``NativeMatchService`` (``_python_entrant`` et al.,
  duplicated from ``engine/tests/test_ruleset_v2.py`` rather than shared
  across the two separate test roots) prove the hand-built fixtures'
  assumed tick-0 diff shape actually matches what the engine produces, for
  every historical/permanent core-having Ruleset identity.
"""

from __future__ import annotations

import json
from pathlib import Path

from battle_client.replay_status import CoreStatus, EntrantReplayStatus, get_entrant_statuses
from battle_client.session import ReplaySession
from battle_engine.python_runtime import CORE_BEACON_BYTE, CORE_SIZE, core_addresses
from battle_engine.replay import (
    SCHEMA_VERSION,
    AgentState,
    KillDeathEvent,
    MatchConfiguration,
    MatchResult,
    MemoryDiff,
    ReplayHeader,
    RuntimeEvent,
    TickSnapshot,
    write_replay,
)
from battle_engine.rules import BYTEFRAY_RULESET_ID
from battle_engine.ruleset_policy import (
    BYTEFRAY_RULESET_V2_ALPHA1_ID,
    BYTEFRAY_RULESET_V2_ALPHA11_ID,
    BYTEFRAY_RULESET_V2_ID,
)

V1 = BYTEFRAY_RULESET_ID
ALPHA1 = BYTEFRAY_RULESET_V2_ALPHA1_ID
ALPHA11 = BYTEFRAY_RULESET_V2_ALPHA11_ID
V2 = BYTEFRAY_RULESET_V2_ID


# ---------------------------------------------------------------------------
# Hand-built replay fixtures
# ---------------------------------------------------------------------------
def _agent(agent_id, alive=True, termination_reason=None, pc=0):
    return AgentState(agent_id=agent_id, pc=pc, alive=alive, termination_reason=termination_reason)


def _core_seed_diff(agent_id: str, start: int, arena_size: int) -> tuple[MemoryDiff, ...]:
    """The tick-0 ``MemoryDiff`` record(s) a real ``seed_core_ownership``
    call would produce for one entrant -- one merged diff for a
    non-wrapping core, or two for a core that crosses the arena boundary
    (mirrors ``VM._wr8``'s own merge-continuation rule exactly).
    """
    addresses = core_addresses(start, arena_size)
    runs: list[tuple[int, int]] = []
    for address in addresses:
        if runs and runs[-1][0] + runs[-1][1] == address:
            runs[-1] = (runs[-1][0], runs[-1][1] + 1)
        else:
            runs.append((address, 1))
    return tuple(
        MemoryDiff(address=a, length=length, owner=agent_id, values=(CORE_BEACON_BYTE,) * length)
        for a, length in runs
    )


def _header(
    entrants: tuple[str, ...],
    *,
    arena_size: int,
    ruleset_id: str | None,
    runtime_kind: str = "python",
) -> ReplayHeader:
    return ReplayHeader(
        MatchConfiguration(arena_size=arena_size),
        {agent_id: agent_id.title() for agent_id in entrants},
        runtime_kind=runtime_kind,
        ruleset_id=ruleset_id,
        entrants=tuple({"agent_id": agent_id, "name": agent_id.title()} for agent_id in entrants),
        schema_version=SCHEMA_VERSION,
    )


def _load(tmp_path: Path, name: str, records) -> ReplaySession:
    path = tmp_path / name
    write_replay(path, records)
    session = ReplaySession()
    session.load(path)
    return session


# ---------------------------------------------------------------------------
# Ruleset v1: no core semantics, ever
# ---------------------------------------------------------------------------
def test_v1_replay_returns_no_core_semantics(tmp_path):
    header = _header(("A", "B"), arena_size=32, ruleset_id=V1)
    tick0 = TickSnapshot(0, agents=(_agent("A"), _agent("B")), score={"A": 0, "B": 0})
    tick1 = TickSnapshot(1, agents=(_agent("A"), _agent("B")), score={"A": 1, "B": 1})
    session = _load(tmp_path, "v1.jsonl", [header, tick0, tick1])

    statuses = get_entrant_statuses(session)
    assert len(statuses) == 2
    for status in statuses:
        assert isinstance(status, EntrantReplayStatus)
        assert status.core is None
        assert status.start_address is None


def test_v1_reconstruction_unchanged_alive_score_still_reported(tmp_path):
    header = _header(("A", "B"), arena_size=32, ruleset_id=V1)
    tick0 = TickSnapshot(0, agents=(_agent("A"), _agent("B")), score={"A": 0, "B": 0})
    tick1 = TickSnapshot(
        1,
        agents=(_agent("A"), _agent("B", alive=False, termination_reason="normal_halt")),
        score={"A": 1, "B": 0},
        events=(KillDeathEvent("death", "B", None),),
    )
    session = _load(tmp_path, "v1b.jsonl", [header, tick0, tick1])
    session.seek(1)

    statuses = {status.agent_id: status for status in get_entrant_statuses(session)}
    assert statuses["A"].alive is True
    assert statuses["B"].alive is False
    assert statuses["B"].death_reason == "normal_halt"
    assert statuses["B"].killer_id is None
    assert statuses["B"].core is None


# ---------------------------------------------------------------------------
# Core integrity: ownership only, never byte content
# ---------------------------------------------------------------------------
def test_initial_integrity_is_8_of_8(tmp_path):
    header = _header(("A", "B"), arena_size=64, ruleset_id=V2)
    tick0 = TickSnapshot(
        0,
        agents=(_agent("A"), _agent("B")),
        score={"A": 0, "B": 0},
        memory_diffs=_core_seed_diff("A", 0, 64) + _core_seed_diff("B", 32, 64),
    )
    session = _load(tmp_path, "init.jsonl", [header, tick0])

    statuses = {status.agent_id: status for status in get_entrant_statuses(session)}
    for agent_id, start in (("A", 0), ("B", 32)):
        core = statuses[agent_id].core
        assert isinstance(core, CoreStatus)
        assert core.total_cells == CORE_SIZE == 8
        assert core.intact_cells == 8
        assert core.damaged_cells == 0
        assert core.integrity_fraction == 1.0
        assert core.captured is False
        assert core.core_addresses == core_addresses(start, 64)
        assert statuses[agent_id].start_address == start


def test_one_ownership_loss_is_7_of_8(tmp_path):
    header = _header(("A", "B"), arena_size=64, ruleset_id=V2)
    tick0 = TickSnapshot(
        0, agents=(_agent("A"), _agent("B")), score={"A": 0, "B": 0},
        memory_diffs=_core_seed_diff("A", 0, 64),
    )
    tick1 = TickSnapshot(
        1, agents=(_agent("A"), _agent("B")), score={"A": 1, "B": 0},
        memory_diffs=(MemoryDiff(address=2, length=1, owner="B", values=(0x11,)),),
    )
    session = _load(tmp_path, "loss.jsonl", [header, tick0, tick1])
    session.seek(1)

    core = get_entrant_statuses(session)[0].core
    assert core is not None
    assert core.intact_cells == 7
    assert core.damaged_cells == 1
    assert core.captured is False


def test_several_losses_reflected(tmp_path):
    header = _header(("A", "B"), arena_size=64, ruleset_id=V2)
    tick0 = TickSnapshot(
        0, agents=(_agent("A"), _agent("B")), score={"A": 0, "B": 0},
        memory_diffs=_core_seed_diff("A", 0, 64),
    )
    tick1 = TickSnapshot(
        1, agents=(_agent("A"), _agent("B")), score={"A": 1, "B": 0},
        memory_diffs=(MemoryDiff(address=0, length=3, owner="B", values=(1, 2, 3)),),
    )
    session = _load(tmp_path, "losses.jsonl", [header, tick0, tick1])
    session.seek(1)

    core = get_entrant_statuses(session)[0].core
    assert core is not None
    assert core.intact_cells == 5
    assert core.damaged_cells == 3


def test_owner_reclaim_restores_integrity(tmp_path):
    header = _header(("A", "B"), arena_size=64, ruleset_id=V2)
    tick0 = TickSnapshot(
        0, agents=(_agent("A"), _agent("B")), score={"A": 0, "B": 0},
        memory_diffs=_core_seed_diff("A", 0, 64),
    )
    tick1 = TickSnapshot(
        1, agents=(_agent("A"), _agent("B")), score={"A": 1, "B": 0},
        memory_diffs=(MemoryDiff(address=3, length=1, owner="B", values=(0xAA,)),),
    )
    tick2 = TickSnapshot(
        2, agents=(_agent("A"), _agent("B")), score={"A": 2, "B": 0},
        memory_diffs=(MemoryDiff(address=3, length=1, owner="A", values=(CORE_BEACON_BYTE,)),),
    )
    session = _load(tmp_path, "reclaim.jsonl", [header, tick0, tick1, tick2])

    session.seek(1)
    assert get_entrant_statuses(session)[0].core.intact_cells == 7

    session.seek(2)
    core = get_entrant_statuses(session)[0].core
    assert core.intact_cells == 8
    assert core.captured is False


def test_all_lost_is_0_of_8_and_captured(tmp_path):
    header = _header(("A", "B"), arena_size=64, ruleset_id=V2)
    tick0 = TickSnapshot(
        0, agents=(_agent("A"), _agent("B")), score={"A": 0, "B": 0},
        memory_diffs=_core_seed_diff("A", 0, 64),
    )
    tick1 = TickSnapshot(
        1,
        agents=(_agent("A", alive=False, termination_reason="core_captured"), _agent("B")),
        score={"A": 0, "B": 5},
        memory_diffs=(MemoryDiff(address=0, length=8, owner="B", values=(0xAA,) * 8),),
        events=(KillDeathEvent("kill", "A", "B"),),
    )
    session = _load(tmp_path, "captured.jsonl", [header, tick0, tick1])
    session.seek(1)

    status = get_entrant_statuses(session)[0]
    assert status.alive is False
    assert status.core.intact_cells == 0
    assert status.core.captured is True
    assert status.core.capture_tick == 1
    assert status.killer_id == "B"
    assert status.death_reason == "core_captured"


def test_byte_content_does_not_determine_integrity(tmp_path):
    """Beacon-overwritten-by-owner stays intact; foreign non-zero content
    with lost ownership is damaged -- ownership is the only signal, never
    the byte value (docs/V2_0_BETA1_PHASE3_REPLAY_SEMANTICS.md's core
    governing rule).
    """
    header = _header(("A", "B"), arena_size=64, ruleset_id=V2)
    tick0 = TickSnapshot(
        0, agents=(_agent("A"), _agent("B")), score={"A": 0, "B": 0},
        memory_diffs=_core_seed_diff("A", 0, 64),
    )
    # A writes 0x00 over its own cell 0 (blanking it) but keeps ownership;
    # B writes a large non-zero value to cell 1 and takes ownership.
    tick1 = TickSnapshot(
        1, agents=(_agent("A"), _agent("B")), score={"A": 1, "B": 0},
        memory_diffs=(
            MemoryDiff(address=0, length=1, owner="A", values=(0x00,)),
            MemoryDiff(address=1, length=1, owner="B", values=(0xFF,)),
        ),
    )
    session = _load(tmp_path, "content.jsonl", [header, tick0, tick1])
    session.seek(1)

    core = get_entrant_statuses(session)[0].core
    assert core is not None
    # cell 0: blanked but still owned by A -> intact; cell 1: non-zero but
    # owned by B -> damaged. 6 of the remaining 8 cells untouched.
    assert core.intact_cells == 7
    assert core.damaged_cells == 1


def test_owner_non_beacon_content_remains_intact(tmp_path):
    header = _header(("A", "B"), arena_size=64, ruleset_id=V2)
    tick0 = TickSnapshot(
        0, agents=(_agent("A"), _agent("B")), score={"A": 0, "B": 0},
        memory_diffs=_core_seed_diff("A", 0, 64),
    )
    # A overwrites its own cell with its own non-beacon signature byte.
    tick1 = TickSnapshot(
        1, agents=(_agent("A"), _agent("B")), score={"A": 1, "B": 0},
        memory_diffs=(MemoryDiff(address=0, length=1, owner="A", values=(0xD3,)),),
    )
    session = _load(tmp_path, "signature.jsonl", [header, tick0, tick1])
    session.seek(1)

    core = get_entrant_statuses(session)[0].core
    assert core.intact_cells == 8


def test_attacker_nonzero_content_counts_damaged_if_ownership_lost(tmp_path):
    header = _header(("A", "B"), arena_size=64, ruleset_id=V2)
    tick0 = TickSnapshot(
        0, agents=(_agent("A"), _agent("B")), score={"A": 0, "B": 0},
        memory_diffs=_core_seed_diff("A", 0, 64),
    )
    tick1 = TickSnapshot(
        1, agents=(_agent("A"), _agent("B")), score={"A": 1, "B": 0},
        memory_diffs=(MemoryDiff(address=5, length=1, owner="B", values=(0x01,)),),
    )
    session = _load(tmp_path, "attacker.jsonl", [header, tick0, tick1])
    session.seek(1)

    core = get_entrant_statuses(session)[0].core
    assert core.intact_cells == 7
    assert core.damaged_cells == 1


def test_wraparound_core_correct(tmp_path):
    arena_size = 16
    start = 12  # wraps: 12,13,14,15,0,1,2,3
    header = _header(("A", "B"), arena_size=arena_size, ruleset_id=V2)
    diffs = _core_seed_diff("A", start, arena_size)
    assert len(diffs) == 2  # confirms the fixture itself actually wraps
    tick0 = TickSnapshot(0, agents=(_agent("A"), _agent("B")), score={"A": 0, "B": 0}, memory_diffs=diffs)
    session = _load(tmp_path, "wrap.jsonl", [header, tick0])

    status = get_entrant_statuses(session)[0]
    assert status.start_address == start
    assert status.core.core_addresses == core_addresses(start, arena_size)
    assert status.core.intact_cells == 8


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
def test_alive_before_and_dead_after_capture(tmp_path):
    header = _header(("A", "B"), arena_size=64, ruleset_id=V2)
    tick0 = TickSnapshot(
        0, agents=(_agent("A"), _agent("B")), score={"A": 0, "B": 0},
        memory_diffs=_core_seed_diff("A", 0, 64),
    )
    tick1 = TickSnapshot(1, agents=(_agent("A"), _agent("B")), score={"A": 1, "B": 0})
    tick2 = TickSnapshot(
        2,
        agents=(_agent("A", alive=False, termination_reason="core_captured"), _agent("B")),
        score={"A": 0, "B": 5},
        memory_diffs=(MemoryDiff(address=0, length=8, owner="B", values=(0xAA,) * 8),),
        events=(KillDeathEvent("kill", "A", "B"),),
    )
    session = _load(tmp_path, "lifecycle.jsonl", [header, tick0, tick1, tick2])

    session.seek(1)
    assert get_entrant_statuses(session)[0].alive is True
    assert get_entrant_statuses(session)[0].death_tick is None

    session.seek(2)
    status = get_entrant_statuses(session)[0]
    assert status.alive is False
    assert status.death_tick == 2


def test_unattributed_capture_has_no_killer(tmp_path):
    header = _header(("A", "B"), arena_size=64, ruleset_id=V2)
    tick0 = TickSnapshot(
        0, agents=(_agent("A"), _agent("B")), score={"A": 0, "B": 0},
        memory_diffs=_core_seed_diff("A", 0, 64),
    )
    tick1 = TickSnapshot(
        1,
        agents=(_agent("A", alive=False, termination_reason="core_captured"), _agent("B")),
        score={"A": 0, "B": 0},
        memory_diffs=(MemoryDiff(address=0, length=8, owner="B", values=(0xAA,) * 8),),
        events=(KillDeathEvent("death", "A", None),),
    )
    session = _load(tmp_path, "unattributed.jsonl", [header, tick0, tick1])
    session.seek(1)

    status = get_entrant_statuses(session)[0]
    assert status.core.captured is True
    assert status.killer_id is None


def test_termination_reason_represented_correctly_for_forfeit(tmp_path):
    header = _header(("A", "B"), arena_size=64, ruleset_id=V2)
    tick0 = TickSnapshot(
        0, agents=(_agent("A"), _agent("B")), score={"A": 0, "B": 0},
        memory_diffs=_core_seed_diff("A", 0, 64),
    )
    tick1 = TickSnapshot(
        1,
        agents=(_agent("A", alive=False, termination_reason="forfeit"), _agent("B")),
        score={"A": 0, "B": 0},
        events=(RuntimeEvent("forfeit", "A", "invalid_action"),),
    )
    session = _load(tmp_path, "forfeit.jsonl", [header, tick0, tick1])
    session.seek(1)

    status = get_entrant_statuses(session)[0]
    assert status.death_reason == "forfeit"
    assert status.killer_id is None
    assert status.death_tick == 1
    # A forfeit is not a capture even though the core mechanic is active.
    assert status.core.captured is False


# ---------------------------------------------------------------------------
# Timeline / tick semantics
# ---------------------------------------------------------------------------
def test_tick_zero_semantics_correct(tmp_path):
    header = _header(("A", "B"), arena_size=64, ruleset_id=V2)
    tick0 = TickSnapshot(
        0, agents=(_agent("A"), _agent("B")), score={"A": 0, "B": 0},
        memory_diffs=_core_seed_diff("A", 0, 64) + _core_seed_diff("B", 32, 64),
    )
    session = _load(tmp_path, "tick0.jsonl", [header, tick0])

    for status in get_entrant_statuses(session):
        assert status.tick == 0
        assert status.alive is True
        assert status.core.intact_cells == 8


def test_final_state_correct(tmp_path):
    header = _header(("A", "B"), arena_size=64, ruleset_id=V2)
    tick0 = TickSnapshot(
        0, agents=(_agent("A"), _agent("B")), score={"A": 0, "B": 0},
        memory_diffs=_core_seed_diff("A", 0, 64),
    )
    tick1 = TickSnapshot(
        1,
        agents=(_agent("A", alive=False, termination_reason="core_captured"), _agent("B")),
        score={"A": 0, "B": 5},
        memory_diffs=(MemoryDiff(address=0, length=8, owner="B", values=(0xAA,) * 8),),
        events=(KillDeathEvent("kill", "A", "B"),),
    )
    result = MatchResult(winner="B", win_mode="score", ticks=1, score={"A": 0, "B": 5})
    session = _load(tmp_path, "final.jsonl", [header, tick0, tick1, result])
    session.seek(session.final_tick)

    statuses = {status.agent_id: status for status in get_entrant_statuses(session)}
    assert statuses["A"].core.captured is True
    assert statuses["B"].score == 5
    assert session.winner == "B"


# ---------------------------------------------------------------------------
# N-entrant (3+): ordering, one dead/two alive, third-party attribution
# ---------------------------------------------------------------------------
def test_three_entrants_returned_in_recorded_order(tmp_path):
    header = _header(("C", "A", "B"), arena_size=96, ruleset_id=V2)
    tick0 = TickSnapshot(
        0,
        agents=(_agent("C"), _agent("A"), _agent("B")),
        score={"C": 0, "A": 0, "B": 0},
        memory_diffs=(
            _core_seed_diff("C", 0, 96) + _core_seed_diff("A", 32, 96) + _core_seed_diff("B", 64, 96)
        ),
    )
    session = _load(tmp_path, "three.jsonl", [header, tick0])

    statuses = get_entrant_statuses(session)
    assert len(statuses) == 3
    assert [status.agent_id for status in statuses] == ["C", "A", "B"]
    assert [status.order for status in statuses] == [0, 1, 2]


def test_one_dead_two_alive_third_party_attribution(tmp_path):
    """A's core ends up split between B (5 cells) and C (3 cells), but the
    engine's own recorded event says C's write was the one that actually
    took A's last cell -- attribution must follow the event, not "whoever
    owns the most of the captured core" (docs/V2_0_BETA1_PHASE3_REPLAY_
    SEMANTICS.md's multi-entrant capture note).
    """
    arena_size = 96
    a_core = core_addresses(0, arena_size)
    header = _header(("A", "B", "C"), arena_size=arena_size, ruleset_id=V2)
    tick0 = TickSnapshot(
        0,
        agents=(_agent("A"), _agent("B"), _agent("C")),
        score={"A": 0, "B": 0, "C": 0},
        memory_diffs=_core_seed_diff("A", 0, arena_size)
        + _core_seed_diff("B", 32, arena_size)
        + _core_seed_diff("C", 64, arena_size),
    )
    tick1 = TickSnapshot(
        1,
        agents=(
            _agent("A", alive=False, termination_reason="core_captured"),
            _agent("B"),
            _agent("C"),
        ),
        score={"A": 0, "B": 0, "C": 3},
        memory_diffs=(
            MemoryDiff(address=a_core[0], length=5, owner="B", values=(0xAA,) * 5),
            MemoryDiff(address=a_core[5], length=3, owner="C", values=(0xBB,) * 3),
        ),
        events=(KillDeathEvent("kill", "A", "C"),),
    )
    session = _load(tmp_path, "third_party.jsonl", [header, tick0, tick1])
    session.seek(1)

    statuses = {status.agent_id: status for status in get_entrant_statuses(session)}
    assert statuses["A"].alive is False
    assert statuses["A"].core.intact_cells == 0
    assert statuses["A"].core.captured is True
    assert statuses["A"].killer_id == "C"  # not "B", despite owning more cells
    assert statuses["B"].alive is True
    assert statuses["C"].alive is True


# ---------------------------------------------------------------------------
# Schema: v4 process state requires an explicit replay schema bump
# ---------------------------------------------------------------------------
def test_v4_replay_schema_bump_is_exposed_to_the_client():
    assert SCHEMA_VERSION == 4


# ---------------------------------------------------------------------------
# Real matches: prove the hand-built fixtures' assumed tick-0 shape matches
# genuine engine output, for every core-having historical/permanent identity.
# ---------------------------------------------------------------------------
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


def _python_entrant(root: Path, agent_id: str, source: bytes, *, slot: str, start: int):
    from battle_engine.agents import resolve_agent
    from battle_engine.match_service import MatchEntrant

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


def _run_real_match(tmp_path: Path, *, ruleset_id: str, attack: bool = False):
    from battle_engine.config import Config
    from battle_engine.match_service import MatchRequest, NativeMatchService

    core = list(core_addresses(20, 128))
    attacker_source = _scripted_writer_source(core) if attack else NOP_SOURCE
    entrants = (
        _python_entrant(tmp_path, "victim", NOP_SOURCE, slot="A", start=20),
        _python_entrant(tmp_path, "attacker", attacker_source, slot="B", start=60),
    )
    request = MatchRequest(
        Config(arena_size=128, instr_per_tick=8),
        entrants,
        max_ticks=20,
        replay_path=tmp_path / "run" / "replay.jsonl",
        verbose=False,
        ruleset_id=ruleset_id,
    )
    result = NativeMatchService().run(request)
    session = ReplaySession()
    session.load(result.replay_path)
    session.seek(session.final_tick)
    return session, core


def test_real_permanent_v2_capture_matches_engine_ground_truth(tmp_path):
    # ``_python_entrant``'s ``slot`` ("A"/"B") becomes ``MatchEntrant.agent_id``;
    # "victim"/"attacker" becomes its display ``name`` -- see
    # ``engine/tests/test_ruleset_v2.py``'s identical ``agents_by_id["A"]``
    # convention, which this mirrors.
    session, _core = _run_real_match(tmp_path, ruleset_id=V2, attack=True)

    statuses = {status.agent_id: status for status in get_entrant_statuses(session)}
    victim, attacker = statuses["A"], statuses["B"]
    assert victim.name == "victim"
    assert attacker.name == "attacker"
    assert victim.alive is False
    assert victim.core.captured is True
    assert victim.core.intact_cells == 0
    assert victim.killer_id == "B"
    assert attacker.alive is True
    assert attacker.core.intact_cells == 8


def test_real_alpha1_core_derived_without_beacon_assumption(tmp_path):
    session, _core = _run_real_match(tmp_path, ruleset_id=ALPHA1, attack=True)

    statuses = {status.agent_id: status for status in get_entrant_statuses(session)}
    victim = statuses["A"]
    assert victim.core is not None
    assert victim.core.captured is True
    assert victim.core.core_addresses == core_addresses(20, 128)


def test_real_alpha11_and_v2_both_work_and_stay_distinct(tmp_path):
    session_11, _ = _run_real_match(tmp_path / "a11", ruleset_id=ALPHA11)
    session_v2, _ = _run_real_match(tmp_path / "v2", ruleset_id=V2)

    for session in (session_11, session_v2):
        statuses = get_entrant_statuses(session)
        for status in statuses:
            assert status.core is not None
            assert status.core.intact_cells == 8

    assert session_11.header.ruleset_id == ALPHA11
    assert session_v2.header.ruleset_id == V2
    assert session_11.header.match_id != session_v2.header.match_id
