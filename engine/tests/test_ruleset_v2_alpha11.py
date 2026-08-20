"""``bytefray-rules-2-alpha11`` "Consistent Core Observability" -- focused tests.

Covers the Phase A5/A6/A7/A9 checklist from the governing v2.0.0-alpha.11
task: Ruleset dispatch for all three registered identities plus fail-closed
rejection of an unregistered one; the beacon-seeding and non-blank
maintenance semantics; that the footprint exists for every primary agent
*without that agent writing its own core*; that it is reachable only through
an ordinary ``READ``; that no opponent-core metadata leaks into the Agent API
surface; arena wrap; that observability does not confer invulnerability; and
that Ruleset v1 and the historical ``bytefray-rules-2-alpha1`` semantics are
both completely unchanged by any of it.

Scripted agents below are small deterministic Python source strings, exactly
as ``test_ruleset_v2_alpha1.py`` and ``test_ruleset_v1_equivalence.py``
already do, so each scenario's tick-by-tick ownership/content sequence is
knowable in advance.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from battle_engine.agent_api import MatchContext, Observation
from battle_engine.agents import resolve_agent
from battle_engine.config import Config
from battle_engine.match_service import (
    MatchEntrant,
    MatchRequest,
    NativeMatchService,
    canonical_match_id,
)
from battle_engine.python_runtime import (
    CORE_BEACON_BYTE,
    CORE_SEED_BYTE_ALPHA1,
    CORE_SIZE,
    OBSERVABLE_CORE_RULESET_IDS,
    VULNERABLE_CORE_RULESET_IDS,
    core_addresses,
    core_seed_byte,
    has_observable_core,
    has_vulnerable_core,
)
from battle_engine.reference_agents import reference_agent_spec
from battle_engine.replay import TickSnapshot, iter_replay
from battle_engine.result_model import read_result
from battle_engine.rules import BYTEFRAY_RULESET_ID
from battle_engine.ruleset_policy import (
    BYTEFRAY_RULESET_V2_ALPHA1_ID,
    BYTEFRAY_RULESET_V2_ALPHA11_ID,
    UnknownRulesetError,
    resolve_ruleset_policy,
)
from battle_engine.starters import ensure_starter_agents

ALPHA1 = BYTEFRAY_RULESET_V2_ALPHA1_ID
ALPHA11 = BYTEFRAY_RULESET_V2_ALPHA11_ID

# Every signature byte written by a bundled starter or reference agent. The
# beacon must differ from all of them -- an agent whose own signature equalled
# the beacon would be blinded to every beacon by its own
# ``value != self.signature`` self-filter.
BUNDLED_AGENT_SIGNATURES = {
    0x99,  # adaptive
    0xC1,  # claimer
    0xE3,  # hunter
    0xC2,  # strider
    0x2C,  # wanderer
    0xD3,  # core_defender
    0x5E,  # core_seeker
    0xA5,  # core_tracker
    0xC7,  # reactive_core_defender
}


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


def _python_entrant(
    root: Path, agent_id: str, source: bytes, *, slot: str, start: int
) -> MatchEntrant:
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


def _self_blanking_source(addresses: list[int]) -> bytes:
    """Writes ``0`` over its own core cells forever -- the "hide my core"
    strategy the alpha.11 maintenance rule exists to close."""

    return (
        "from battle_engine.agent_api import ActionKind, AgentAction\n\n"
        f"ADDRESSES = {addresses!r}\n\n"
        "class Agent:\n"
        "    def reset(self, context):\n"
        "        self.index = 0\n\n"
        "    def act(self, observation):\n"
        "        addr = ADDRESSES[self.index % len(ADDRESSES)]\n"
        "        self.index += 1\n"
        "        return AgentAction(ActionKind.WRITE, addr, 0)\n\n"
        "def create_agent():\n"
        "    return Agent()\n"
    ).encode()


def _reader_source(read_address: int, report_address: int) -> bytes:
    """READs ``read_address`` once, then WRITEs whatever ordinary
    ``Observation.last_read`` reported to ``report_address`` forever.

    The only channel used is the documented Agent API v1 one: a ``READ``
    action followed by ``observation.last_read`` on the next call. Nothing
    inspects engine state.
    """

    return (
        "from battle_engine.agent_api import ActionKind, AgentAction\n\n"
        "class Agent:\n"
        "    def reset(self, context):\n"
        "        self.done_read = False\n\n"
        "    def act(self, observation):\n"
        "        if not self.done_read:\n"
        "            self.done_read = True\n"
        f"            return AgentAction(ActionKind.READ, {read_address})\n"
        "        value = observation.last_read\n"
        "        if value is None:\n"
        "            value = 0\n"
        f"        return AgentAction(ActionKind.WRITE, {report_address}, value)\n\n"
        "def create_agent():\n"
        "    return Agent()\n"
    ).encode()


def _request(
    tmp_path: Path,
    entrants: tuple[MatchEntrant, ...],
    *,
    ruleset_id: str | None,
    arena_size: int = 128,
    instr_per_tick: int = 8,
    max_ticks: int = 20,
    run_name: str = "run",
) -> MatchRequest:
    return MatchRequest(
        Config(arena_size=arena_size, instr_per_tick=instr_per_tick),
        entrants,
        max_ticks=max_ticks,
        replay_path=tmp_path / run_name / "replay.jsonl",
        verbose=False,
        ruleset_id=ruleset_id,
    )


def _final_arena(result, arena_size: int) -> dict[int, int]:
    """Reconstruct final arena content from the canonical replay's diffs."""

    arena: dict[int, int] = {}
    for record in iter_replay(result.replay_path):
        if not isinstance(record, TickSnapshot):
            continue
        for diff in record.memory_diffs:
            for offset, value in enumerate(diff.values):
                arena[(diff.address + offset) % arena_size] = value
    return arena


def _final_owners(result, arena_size: int) -> dict[int, str | None]:
    owners: dict[int, str | None] = {}
    for record in iter_replay(result.replay_path):
        if not isinstance(record, TickSnapshot):
            continue
        for diff in record.memory_diffs:
            for offset in range(diff.length):
                owners[(diff.address + offset) % arena_size] = diff.owner
    return owners


# ---------------------------------------------------------------------------
# Ruleset dispatch (Phase A9 items 1-4)
# ---------------------------------------------------------------------------


def test_alpha11_ruleset_resolves_explicitly() -> None:
    assert resolve_ruleset_policy(ALPHA11).ruleset_id == ALPHA11


def test_historical_alpha1_ruleset_still_resolves() -> None:
    assert resolve_ruleset_policy(ALPHA1).ruleset_id == ALPHA1


def test_ruleset_v1_still_resolves() -> None:
    assert resolve_ruleset_policy(BYTEFRAY_RULESET_ID).ruleset_id == BYTEFRAY_RULESET_ID


@pytest.mark.parametrize(
    "unknown",
    [
        "bytefray-rules-2",
        "bytefray-rules-2-alpha12",
        "bytefray-rules-2-alpha1x",
        "BYTEFRAY-RULES-2-ALPHA11",
        "",
    ],
)
def test_unregistered_ruleset_ids_fail_closed(unknown: str) -> None:
    with pytest.raises(UnknownRulesetError):
        resolve_ruleset_policy(unknown)


def test_alpha11_is_not_a_ruleset_alias_of_anything() -> None:
    from battle_engine.rules import normalize_ruleset_id

    assert normalize_ruleset_id(ALPHA11) == ALPHA11
    assert normalize_ruleset_id(ALPHA1) == ALPHA1


# ---------------------------------------------------------------------------
# Mechanic gating: alpha11 is strictly narrower than "has a vulnerable core"
# ---------------------------------------------------------------------------


def test_observable_core_is_a_strict_subset_of_vulnerable_core() -> None:
    assert OBSERVABLE_CORE_RULESET_IDS < VULNERABLE_CORE_RULESET_IDS
    assert has_vulnerable_core(ALPHA1) and not has_observable_core(ALPHA1)
    assert has_vulnerable_core(ALPHA11) and has_observable_core(ALPHA11)
    assert not has_vulnerable_core(BYTEFRAY_RULESET_ID)
    assert not has_observable_core(BYTEFRAY_RULESET_ID)


def test_core_seed_byte_per_ruleset() -> None:
    assert core_seed_byte(ALPHA1) == CORE_SEED_BYTE_ALPHA1 == 0x00
    assert core_seed_byte(ALPHA11) == CORE_BEACON_BYTE
    assert core_seed_byte(BYTEFRAY_RULESET_ID) == CORE_SEED_BYTE_ALPHA1


def test_beacon_byte_is_non_zero_and_collides_with_no_bundled_signature() -> None:
    assert CORE_BEACON_BYTE != 0
    assert 0 < CORE_BEACON_BYTE <= 0xFF
    assert CORE_BEACON_BYTE not in BUNDLED_AGENT_SIGNATURES


# ---------------------------------------------------------------------------
# Footprint existence (Phase A9 items 5-9, 12)
# ---------------------------------------------------------------------------


def test_core_footprint_exists_under_alpha11(tmp_path) -> None:
    entrants = (
        _python_entrant(tmp_path, "idle_a", NOP_SOURCE, slot="A", start=20),
        _python_entrant(tmp_path, "idle_b", NOP_SOURCE, slot="B", start=60),
    )
    request = _request(tmp_path, entrants, ruleset_id=ALPHA11, max_ticks=3)
    result = NativeMatchService().run(request)
    arena = _final_arena(result, 128)
    for address in core_addresses(20, 128):
        assert arena[address] == CORE_BEACON_BYTE
    for address in core_addresses(60, 128):
        assert arena[address] == CORE_BEACON_BYTE


def test_alpha1_core_has_no_footprint(tmp_path) -> None:
    """The exact historical behavior alpha.11 exists to change, pinned so it
    can never silently drift into the alpha1 identity."""

    entrants = (
        _python_entrant(tmp_path, "idle_a", NOP_SOURCE, slot="A", start=20),
        _python_entrant(tmp_path, "idle_b", NOP_SOURCE, slot="B", start=60),
    )
    request = _request(tmp_path, entrants, ruleset_id=ALPHA1, max_ticks=3)
    result = NativeMatchService().run(request)
    arena = _final_arena(result, 128)
    for address in core_addresses(20, 128):
        assert arena[address] == 0
    for address in core_addresses(60, 128):
        assert arena[address] == 0


def test_core_footprint_wraps_across_the_arena_end(tmp_path) -> None:
    start = 128 - 3  # core spans 125,126,127,0,1,2,3,4
    entrants = (
        _python_entrant(tmp_path, "wrapper", NOP_SOURCE, slot="A", start=start),
        _python_entrant(tmp_path, "other", NOP_SOURCE, slot="B", start=60),
    )
    request = _request(tmp_path, entrants, ruleset_id=ALPHA11, max_ticks=3)
    result = NativeMatchService().run(request)
    arena = _final_arena(result, 128)
    addresses = core_addresses(start, 128)
    assert addresses == (125, 126, 127, 0, 1, 2, 3, 4)
    for address in addresses:
        assert arena[address] == CORE_BEACON_BYTE


@pytest.mark.parametrize(
    "agent_name",
    ["claimer", "hunter", "core_defender", "reactive_core_defender"],
)
def test_footprint_exists_for_every_primary_agent(tmp_path, agent_name: str) -> None:
    """Phase A9 items 6-9: the footprint is a Ruleset property, so it exists
    for the two expanders (which never write their own core deliberately)
    exactly as it does for the two defenders (which do)."""

    ensure_starter_agents()
    starter_names = {"claimer", "hunter"}
    if agent_name in starter_names:
        from battle_engine.paths import get_data_root

        spec = resolve_agent(get_data_root(), agent_name)
    else:
        spec = reference_agent_spec(agent_name)

    entrants = (
        MatchEntrant.python("A", agent_name, 2000, spec),
        _python_entrant(tmp_path, "idle_b", NOP_SOURCE, slot="B", start=3000),
    )
    request = _request(
        tmp_path, entrants, ruleset_id=ALPHA11, arena_size=4096, max_ticks=6
    )
    result = NativeMatchService().run(request)
    arena = _final_arena(result, 4096)
    core = core_addresses(2000, 4096)
    # The invariant, identically for all four: every cell of this entrant's
    # own core is non-zero, i.e. observable by an ordinary content-based
    # search, regardless of whether this agent ever writes there.
    assert all(arena[address] != 0 for address in core)
    # And the *source* of that non-zero content is exactly the distinction the
    # asymmetry used to turn on: an expander's core still carries the engine's
    # beacon (it never writes its own core), while a defender's core carries
    # that defender's own signature (it does). Both are equally findable --
    # which is the whole point.
    if agent_name in starter_names:
        assert all(arena[address] == CORE_BEACON_BYTE for address in core)
    else:
        assert CORE_BEACON_BYTE not in {arena[address] for address in core}


def test_expander_core_is_invisible_under_alpha1_but_visible_under_alpha11(
    tmp_path,
) -> None:
    """The exact informational defect, in one matched pair of matches."""

    ensure_starter_agents()
    from battle_engine.paths import get_data_root

    claimer = resolve_agent(get_data_root(), "claimer")
    observed: dict[str, set[int]] = {}
    for label, ruleset in (("alpha1", ALPHA1), ("alpha11", ALPHA11)):
        entrants = (
            MatchEntrant.python("A", "claimer", 2000, claimer),
            _python_entrant(
                tmp_path / label, "idle_b", NOP_SOURCE, slot="B", start=3000
            ),
        )
        request = _request(
            tmp_path,
            entrants,
            ruleset_id=ruleset,
            arena_size=4096,
            max_ticks=3,
            run_name=f"run_{label}",
        )
        result = NativeMatchService().run(request)
        arena = _final_arena(result, 4096)
        core = core_addresses(2000, 4096)
        observed[label] = {arena[address] for address in core}

    assert observed["alpha1"] == {0}
    assert observed["alpha11"] == {CORE_BEACON_BYTE}


# ---------------------------------------------------------------------------
# Ordinary-read visibility and information boundary (Phase A9 items 10-11)
# ---------------------------------------------------------------------------


def test_footprint_is_visible_through_an_ordinary_read_action(tmp_path) -> None:
    victim_start = 20
    probe_address = core_addresses(victim_start, 128)[3]
    report_address = 100
    entrants = (
        _python_entrant(tmp_path, "victim", NOP_SOURCE, slot="A", start=victim_start),
        _python_entrant(
            tmp_path,
            "searcher",
            _reader_source(probe_address, report_address),
            slot="B",
            start=60,
        ),
    )
    request = _request(tmp_path, entrants, ruleset_id=ALPHA11, max_ticks=3)
    result = NativeMatchService().run(request)
    arena = _final_arena(result, 128)
    # The searcher used only READ + Observation.last_read, and what it read
    # back was the beacon.
    assert arena[report_address] == CORE_BEACON_BYTE


def test_same_read_under_alpha1_returns_a_blank_cell(tmp_path) -> None:
    victim_start = 20
    probe_address = core_addresses(victim_start, 128)[3]
    report_address = 100
    entrants = (
        _python_entrant(tmp_path, "victim", NOP_SOURCE, slot="A", start=victim_start),
        _python_entrant(
            tmp_path,
            "searcher",
            _reader_source(probe_address, report_address),
            slot="B",
            start=60,
        ),
    )
    request = _request(tmp_path, entrants, ruleset_id=ALPHA1, max_ticks=3)
    result = NativeMatchService().run(request)
    arena = _final_arena(result, 128)
    assert arena[report_address] == 0


def test_no_opponent_core_metadata_is_exposed_to_agents() -> None:
    """Phase A9 item 11: alpha.11 adds no Agent API surface at all. The
    observation/context contracts must still expose nothing about any other
    entrant -- no identity, no position, no core address, no ownership."""

    observation_fields = set(Observation.__dataclass_fields__)
    context_fields = set(MatchContext.__dataclass_fields__)
    assert observation_fields == {
        "tick",
        "agent_id",
        "pc",
        "register_a",
        "register_p",
        "zero_flag",
        "last_read",
        "alive",
    }
    assert context_fields == {
        "agent_id",
        "seed",
        "arena_size",
        "tick_limit",
        "action_budget",
        "rng",
    }
    forbidden = ("core", "owner", "ownership", "opponent", "enemy", "beacon", "start")
    for field in observation_fields | context_fields:
        assert not any(token in field for token in forbidden), field


# ---------------------------------------------------------------------------
# Observability is not invulnerability (Phase A7, Phase A9 items 13-14)
# ---------------------------------------------------------------------------


def test_ordinary_writes_still_capture_a_core_under_alpha11(tmp_path) -> None:
    core = list(core_addresses(20, 128))
    entrants = (
        _python_entrant(tmp_path, "victim", NOP_SOURCE, slot="A", start=20),
        _python_entrant(
            tmp_path, "attacker", _scripted_writer_source(core), slot="B", start=60
        ),
    )
    request = _request(tmp_path, entrants, ruleset_id=ALPHA11)
    result = NativeMatchService().run(request)
    victim = result.agents_by_id["A"]
    attacker = result.agents_by_id["B"]
    assert victim.alive is False
    assert victim.termination_reason == "core_captured"
    assert attacker.kills == 1
    assert result.winner == "B"


def test_maintenance_never_reverts_an_attackers_write(tmp_path) -> None:
    """Only the *last* core cell is left alone, so the victim survives and the
    match runs on -- proving the seven attacker-owned cells keep the attacker's
    own byte and owner tick after tick, rather than being restored."""

    core = list(core_addresses(20, 128))
    attacked = core[:-1]
    entrants = (
        _python_entrant(tmp_path, "victim", NOP_SOURCE, slot="A", start=20),
        _python_entrant(
            tmp_path,
            "attacker",
            _scripted_writer_source(attacked, value=0xAA),
            slot="B",
            start=60,
        ),
    )
    request = _request(tmp_path, entrants, ruleset_id=ALPHA11, max_ticks=15)
    result = NativeMatchService().run(request)
    victim = result.agents_by_id["A"]
    assert victim.alive is True

    arena = _final_arena(result, 128)
    owners = _final_owners(result, 128)
    for address in attacked:
        assert arena[address] == 0xAA, address
        assert owners[address] == "B", address
    assert arena[core[-1]] == CORE_BEACON_BYTE
    assert owners[core[-1]] == "A"


def test_maintenance_does_not_restore_ownership_or_territory(tmp_path) -> None:
    core = list(core_addresses(20, 128))
    entrants = (
        _python_entrant(tmp_path, "victim", NOP_SOURCE, slot="A", start=20),
        _python_entrant(
            tmp_path, "attacker", _scripted_writer_source(core[:-1]), slot="B", start=60
        ),
    )
    request = _request(tmp_path, entrants, ruleset_id=ALPHA11, max_ticks=15)
    result = NativeMatchService().run(request)
    victim = result.agents_by_id["A"]
    # Started owning 8 core cells, lost 7 to the attacker, and maintenance
    # never gave any of them back.
    assert victim.territory_last == 1


def test_maintenance_stops_once_the_owner_is_dead(tmp_path) -> None:
    """A dead entrant's core is not maintained: after capture, the cells hold
    the attacker's content and the attacker's ownership, permanently."""

    core = list(core_addresses(20, 128))
    entrants = (
        _python_entrant(tmp_path, "victim", NOP_SOURCE, slot="A", start=20),
        _python_entrant(
            tmp_path,
            "attacker",
            _scripted_writer_source(core, value=0xAA),
            slot="B",
            start=60,
        ),
    )
    request = _request(tmp_path, entrants, ruleset_id=ALPHA11)
    result = NativeMatchService().run(request)
    arena = _final_arena(result, 128)
    owners = _final_owners(result, 128)
    assert result.agents_by_id["A"].alive is False
    for address in core:
        assert arena[address] == 0xAA, address
        assert owners[address] == "B", address


# ---------------------------------------------------------------------------
# Non-blank maintenance semantics (Phase A6/A3 invariant)
# ---------------------------------------------------------------------------


def test_owner_cannot_hide_its_core_by_blanking_it(tmp_path) -> None:
    """The whole point of the maintenance half of the rule: writing ``0`` over
    your own still-owned core cells does not restore alpha1's invisibility."""

    core = list(core_addresses(20, 128))
    entrants = (
        _python_entrant(
            tmp_path, "hider", _self_blanking_source(core), slot="A", start=20
        ),
        _python_entrant(tmp_path, "idle_b", NOP_SOURCE, slot="B", start=60),
    )
    request = _request(tmp_path, entrants, ruleset_id=ALPHA11, max_ticks=10)
    result = NativeMatchService().run(request)
    arena = _final_arena(result, 128)
    owners = _final_owners(result, 128)
    for address in core:
        assert arena[address] == CORE_BEACON_BYTE, address
        assert owners[address] == "A", address
    assert result.agents_by_id["A"].alive is True


def test_owner_can_hide_its_core_under_alpha1(tmp_path) -> None:
    """Same agent, historical Ruleset: the hide works, which is exactly why
    the maintenance half of the alpha.11 rule is needed rather than seeding
    alone."""

    core = list(core_addresses(20, 128))
    entrants = (
        _python_entrant(
            tmp_path, "hider", _self_blanking_source(core), slot="A", start=20
        ),
        _python_entrant(tmp_path, "idle_b", NOP_SOURCE, slot="B", start=60),
    )
    request = _request(tmp_path, entrants, ruleset_id=ALPHA1, max_ticks=10)
    result = NativeMatchService().run(request)
    arena = _final_arena(result, 128)
    for address in core:
        assert arena[address] == 0, address


def test_maintenance_leaves_the_owners_own_non_zero_content_alone(tmp_path) -> None:
    """Only ``0`` is repaired. A defender's own core signature survives, so
    its READ-then-compare repair logic is not disturbed."""

    core = list(core_addresses(20, 128))
    signed = core * 4  # keep rewriting its own core with its own signature
    entrants = (
        _python_entrant(
            tmp_path,
            "signer",
            _scripted_writer_source(signed, value=0xD3),
            slot="A",
            start=20,
        ),
        _python_entrant(tmp_path, "idle_b", NOP_SOURCE, slot="B", start=60),
    )
    request = _request(tmp_path, entrants, ruleset_id=ALPHA11, max_ticks=10)
    result = NativeMatchService().run(request)
    arena = _final_arena(result, 128)
    for address in core:
        assert arena[address] == 0xD3, address


def test_maintenance_writes_are_published_into_the_replay(tmp_path) -> None:
    """Replay reconstructability: an engine maintenance write is an ordinary
    diff in the tick it happened, not hidden state."""

    core = list(core_addresses(20, 128))
    entrants = (
        _python_entrant(
            tmp_path, "hider", _self_blanking_source(core), slot="A", start=20
        ),
        _python_entrant(tmp_path, "idle_b", NOP_SOURCE, slot="B", start=60),
    )
    request = _request(tmp_path, entrants, ruleset_id=ALPHA11, max_ticks=4)
    result = NativeMatchService().run(request)
    beacon_writes_after_tick_zero = [
        (record.tick, diff.address, value)
        for record in iter_replay(result.replay_path)
        if isinstance(record, TickSnapshot) and record.tick > 0
        for diff in record.memory_diffs
        for offset, value in enumerate(diff.values)
        if value == CORE_BEACON_BYTE
        and (diff.address + offset) % 128 in set(core)
        and diff.owner == "A"
    ]
    assert beacon_writes_after_tick_zero


def test_initial_beacon_does_not_change_initial_territory_or_ownership(
    tmp_path,
) -> None:
    """Only the seeded *content* differs between alpha1 and alpha11; the
    ownership it establishes -- and therefore territory scoring -- is
    identical."""

    per_ruleset = {}
    for label, ruleset in (("alpha1", ALPHA1), ("alpha11", ALPHA11)):
        entrants = (
            _python_entrant(
                tmp_path / label, "idle_a", NOP_SOURCE, slot="A", start=20
            ),
            _python_entrant(
                tmp_path / label, "idle_b", NOP_SOURCE, slot="B", start=60
            ),
        )
        request = _request(
            tmp_path, entrants, ruleset_id=ruleset, max_ticks=5, run_name=f"r_{label}"
        )
        result = NativeMatchService().run(request)
        per_ruleset[label] = {
            agent_id: (agent.territory_last, agent.score)
            for agent_id, agent in result.agents_by_id.items()
        }
    assert per_ruleset["alpha1"] == per_ruleset["alpha11"]
    assert per_ruleset["alpha11"]["A"][0] == CORE_SIZE


# ---------------------------------------------------------------------------
# Artifact identity (Phase A4, Phase A9 items 15-17)
# ---------------------------------------------------------------------------


def test_replay_and_result_record_the_alpha11_ruleset_identity(tmp_path) -> None:
    entrants = (
        _python_entrant(tmp_path, "idle_a", NOP_SOURCE, slot="A", start=20),
        _python_entrant(tmp_path, "idle_b", NOP_SOURCE, slot="B", start=60),
    )
    request = _request(tmp_path, entrants, ruleset_id=ALPHA11, max_ticks=3)
    result = NativeMatchService().run(request)

    headers = [
        record for record in iter_replay(result.replay_path) if not isinstance(record, TickSnapshot)
    ]
    assert headers and headers[0].ruleset_id == ALPHA11
    assert result.result_path is not None
    assert read_result(result.result_path).ruleset_id == ALPHA11


def test_canonical_match_identity_differs_across_the_three_rulesets(tmp_path) -> None:
    entrants = (
        _python_entrant(tmp_path, "idle_a", NOP_SOURCE, slot="A", start=20),
        _python_entrant(tmp_path, "idle_b", NOP_SOURCE, slot="B", start=60),
    )
    ids = {
        ruleset: canonical_match_id(
            _request(tmp_path, entrants, ruleset_id=ruleset, max_ticks=3)
        )
        for ruleset in (None, ALPHA1, ALPHA11)
    }
    assert len(set(ids.values())) == 3


def test_historical_alpha1_outcome_is_unchanged_by_alpha11(tmp_path) -> None:
    """A full historical alpha1 scenario: the capture happens on exactly the
    same tick, with the same attribution, as ``test_ruleset_v2_alpha1.py``
    already pins independently."""

    core = list(core_addresses(20, 128))
    entrants = (
        _python_entrant(tmp_path, "victim", NOP_SOURCE, slot="A", start=20),
        _python_entrant(
            tmp_path, "attacker", _scripted_writer_source(core), slot="B", start=0
        ),
    )
    request = _request(
        tmp_path, entrants, ruleset_id=ALPHA1, instr_per_tick=2, max_ticks=10
    )
    result = NativeMatchService().run(request)
    kill_events = [
        (record.tick, event.victim, event.killer)
        for record in iter_replay(result.replay_path)
        if isinstance(record, TickSnapshot)
        for event in record.events
        if getattr(event, "event_type", None) == "kill"
    ]
    assert kill_events == [(4, "A", "B")]
    arena = _final_arena(result, 128)
    # No alpha.11 beacon leaked into the historical Ruleset anywhere.
    assert CORE_BEACON_BYTE not in set(arena.values())


def test_ruleset_v1_python_matches_get_no_core_state_at_all(tmp_path) -> None:
    """Phase A5: Ruleset v1 remains frozen -- no seeding, no beacon, no
    maintenance, no capture, and an empty tick-zero diff exactly as before."""

    core = list(core_addresses(20, 128))
    entrants = (
        _python_entrant(tmp_path, "victim", NOP_SOURCE, slot="A", start=20),
        _python_entrant(
            tmp_path, "attacker", _scripted_writer_source(core), slot="B", start=60
        ),
    )
    request = _request(tmp_path, entrants, ruleset_id=None)
    result = NativeMatchService().run(request)
    assert result.agents_by_id["A"].alive is True
    assert result.agents_by_id["A"].termination_reason is None
    tick_zero = [
        record
        for record in iter_replay(result.replay_path)
        if isinstance(record, TickSnapshot) and record.tick == 0
    ]
    assert tick_zero and tick_zero[0].memory_diffs == ()
    arena = _final_arena(result, 128)
    assert CORE_BEACON_BYTE not in set(arena.values())
